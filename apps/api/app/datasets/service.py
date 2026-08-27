import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.datasets.quality import build_and_store_quality_report
from app.datasets.timing import classify_dataset_timing
from app.db.models import DatasetColumnProfileModel, DatasetDeletionModel, DatasetModel
from app.ingestion.storage import (
    UploadTooLargeError,
    delete_immutable_csv,
    read_bounded,
    store_immutable_csv,
)
from app.ingestion.validation import (
    IngestionValidationError,
    sanitize_filename,
    validate_csv_content,
)

logger = logging.getLogger("policy_api.datasets")

SOURCE_TYPE_CSV_UPLOAD = "csv_upload"
_DEFAULT_CONTENT_TYPE = "text/csv"


def create_dataset_from_upload(
    session: Session, name: str, file: UploadFile, settings: Settings
) -> DatasetModel:
    """Validate, content-address, and immutably persist an uploaded CSV.

    Raises `HTTPException` (400/413/409) on any validation, size, or identity conflict.
    See `docs/architecture/ingestion-contract.md` for the full contract.
    """
    try:
        safe_filename = sanitize_filename(file.filename or "")
    except IngestionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        raw = read_bounded(file.file, settings.max_upload_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc

    try:
        validate_csv_content(raw)
    except IngestionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    stored = store_immutable_csv(settings.ingestion_storage_root, raw)

    # Deferred import: app.datasets.profiling imports SOURCE_TYPE_CSV_UPLOAD from this module,
    # so importing it at module load time here would be circular.
    from app.datasets.profiling import profile_dataset

    # Deliberately the *unfiltered* latest row by version, deleted or not: version numbers must
    # keep incrementing per name regardless of intermediate deletions (re-uploading *differing*
    # content after a delete already correctly lands on the next version number, unaffected by
    # this query) -- only the conflict check immediately below needs to ignore a tombstoned row.
    latest = session.scalars(
        select(DatasetModel)
        .where(DatasetModel.name == name)
        .order_by(DatasetModel.version.desc())
        .limit(1)
    ).first()

    # TASK-055 R1 (`HANDOFF-074`): a tombstoned "latest" must never count as a conflict, or
    # deleting a dataset and then re-uploading the exact same content under the same name -- a
    # very plausible real action ("delete this, we'll re-send it") -- is permanently blocked by a
    # 409 referencing a version number that resolves nowhere else in the API.
    if (
        latest is not None
        and latest.deleted_at is None
        and latest.checksum_sha256 == stored.sha256
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"identical content already exists as version {latest.version}",
        )

    dataset = DatasetModel(
        name=name,
        source_filename=safe_filename,
        version=(latest.version + 1) if latest is not None else 1,
        checksum_sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        content_type=file.content_type or _DEFAULT_CONTENT_TYPE,
        source_type=SOURCE_TYPE_CSV_UPLOAD,
        storage_path=stored.storage_path,
    )
    session.add(dataset)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="concurrent upload for this dataset name, retry",
        ) from exc
    session.refresh(dataset)

    # TASK-007/TASK-008/TASK-009: profile the just-stored CSV, classify each column's feature
    # timing, then build the aggregate data-quality report — all from the one in-memory dataframe
    # TASK-007 already loaded. The raw bytes are already immutably persisted at this point
    # (TASK-006's own guarantee), so a failure at any of these stages must not undo or hide the
    # upload — log it and leave the dataset unprofiled/unclassified/unrated rather than fail (or
    # silently half-fail) the request.
    try:
        result = profile_dataset(session, dataset, settings)
        classifications = classify_dataset_timing(dataset, result.profiles)
        build_and_store_quality_report(dataset, result.frame, result.profiles, classifications)
        session.commit()
    except Exception:
        session.rollback()
        logger.warning(
            "dataset_profiling_failed", extra={"fields": {"dataset_id": str(dataset.id)}}
        )

    return dataset


def list_datasets(session: Session) -> list[DatasetModel]:
    return list(
        session.scalars(
            select(DatasetModel)
            .where(DatasetModel.deleted_at.is_(None))
            .order_by(DatasetModel.created_at.desc())
        )
    )


def get_dataset(session: Session, dataset_id: UUID) -> DatasetModel:
    dataset = session.get(DatasetModel, dataset_id)
    if dataset is None or dataset.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset


def delete_dataset(
    session: Session,
    dataset_id: UUID,
    requesting_user_id: UUID,
    reason: str,
    settings: Settings,
) -> DatasetDeletionModel:
    """Tombstone a dataset, redact literal-content derived artifacts, and purge raw bytes when
    safe (`TASK-055`). See `docs/architecture/dataset-deletion-contract.md` for the full contract.

    Never a row delete: every downstream table references `datasets` with `ondelete="RESTRICT"`,
    so this only ever sets `deleted_at` plus writes one `DatasetDeletionModel` audit row. Raw bytes
    are physically unlinked unless another active dataset still shares the same content hash
    (content-addressed dedup) — that disposition is recorded on the audit row, not guessed at
    read time.
    """
    dataset = session.get(DatasetModel, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    if dataset.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Dataset is already deleted"
        )
    if not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A deletion reason is required"
        )

    now = datetime.now(UTC)
    dataset.deleted_at = now

    profiles = list(
        session.scalars(
            select(DatasetColumnProfileModel).where(
                DatasetColumnProfileModel.dataset_id == dataset_id
            )
        )
    )
    for profile in profiles:
        # Only the fields the profiler itself treats as literal source-data content
        # (`policy_analytics.profiling.schema_profiler`'s own PII-conservative-floor design,
        # `examples_suppressed`) are cleared. `min_value`/`max_value`/counts are aggregate
        # statistics by that same design, not raw examples, and are left intact.
        profile.examples = []
        profile.examples_suppressed = True
        profile.suspicious_values = []

    # TASK-055 R2 (`HANDOFF-074`): row-lock every dataset sharing this content hash (this row
    # included) before deciding whether anyone else still references it. Without this, two
    # concurrent deletes of dedup-sibling datasets can each run the "is anyone else still active"
    # check under READ COMMITTED before either's own `deleted_at` update commits -- each sees the
    # other as still active and both independently choose to retain, permanently orphaning bytes
    # nothing points to any more once both commit. `ORDER BY id` fixes a consistent lock
    # acquisition order across concurrent transactions touching the same checksum group, so two
    # overlapping deletes serialize instead of deadlocking. Ordinary Postgres row locking, no new
    # infrastructure.
    session.scalars(
        select(DatasetModel.id)
        .where(DatasetModel.checksum_sha256 == dataset.checksum_sha256)
        .order_by(DatasetModel.id)
        .with_for_update()
    ).all()

    other_active_reference = session.scalars(
        select(DatasetModel.id)
        .where(
            DatasetModel.checksum_sha256 == dataset.checksum_sha256,
            DatasetModel.id != dataset_id,
            DatasetModel.deleted_at.is_(None),
        )
        .limit(1)
    ).first()

    raw_bytes_purged = False
    raw_bytes_retained_reason: str | None = None
    if other_active_reference is None:
        delete_immutable_csv(settings.ingestion_storage_root, dataset.storage_path)
        raw_bytes_purged = True
    else:
        raw_bytes_retained_reason = (
            "content-addressed bytes are still referenced by another active dataset version"
        )

    deletion = DatasetDeletionModel(
        dataset_id=dataset_id,
        requested_by_user_id=requesting_user_id,
        requested_at=now,
        reason=reason,
        raw_bytes_purged=raw_bytes_purged,
        raw_bytes_retained_reason=raw_bytes_retained_reason,
        redacted_column_profile_count=len(profiles),
    )
    session.add(deletion)
    session.commit()
    session.refresh(deletion)

    logger.info(
        "dataset_deleted",
        extra={
            "fields": {
                "dataset_id": str(dataset_id),
                "raw_bytes_purged": raw_bytes_purged,
                "redacted_column_profile_count": len(profiles),
            }
        },
    )
    return deletion
