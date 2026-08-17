import logging
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import DatasetModel
from app.ingestion.storage import UploadTooLargeError, read_bounded, store_immutable_csv
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

    latest = session.scalars(
        select(DatasetModel)
        .where(DatasetModel.name == name)
        .order_by(DatasetModel.version.desc())
        .limit(1)
    ).first()

    if latest is not None and latest.checksum_sha256 == stored.sha256:
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

    # TASK-007: profile the just-stored CSV. The raw bytes are already immutably persisted at this
    # point (TASK-006's own guarantee), so a profiling failure must not undo or hide the upload —
    # log it and leave the dataset unprofiled rather than fail (or silently half-fail) the request.
    try:
        profile_dataset(session, dataset, settings)
        session.commit()
    except Exception:
        session.rollback()
        logger.warning(
            "dataset_profiling_failed", extra={"fields": {"dataset_id": str(dataset.id)}}
        )

    return dataset


def list_datasets(session: Session) -> list[DatasetModel]:
    return list(session.scalars(select(DatasetModel).order_by(DatasetModel.created_at.desc())))


def get_dataset(session: Session, dataset_id: UUID) -> DatasetModel:
    dataset = session.get(DatasetModel, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset
