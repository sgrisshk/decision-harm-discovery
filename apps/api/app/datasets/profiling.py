"""Persistence wiring for TASK-007 schema profiling.

The pure computation lives in `policy_analytics.profiling.schema_profiler` (no I/O, no DB) —
this module only reads the already-validated, already-stored CSV bytes and persists the result.
"""

from __future__ import annotations

import logging

import polars as pl
from policy_analytics.profiling.schema_profiler import profile_columns
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.datasets.service import SOURCE_TYPE_CSV_UPLOAD
from app.db.models import DatasetColumnProfileModel, DatasetModel

logger = logging.getLogger("policy_api.datasets")


class ProfilingError(ValueError):
    """Raised for a dataset this module cannot profile (e.g. not a single-CSV upload)."""


def profile_dataset(session: Session, dataset: DatasetModel, settings: Settings) -> None:
    """Profile `dataset`'s stored CSV and persist one `DatasetColumnProfileModel` row per column.

    Raises `ProfilingError` for anything other than a `source_type="csv_upload"` dataset — e.g.
    the multi-file analytical-dataset rows `scripts/promote_findings.py` creates directly, which
    point at a directory, not a single CSV. Callers decide whether a profiling failure should fail
    the whole request; the immutable raw bytes are already safely stored by the time this runs, so
    a profiling failure never implies lost or corrupted data (`TASK-006`'s own guarantee).
    """
    if dataset.source_type != SOURCE_TYPE_CSV_UPLOAD:
        raise ProfilingError(
            f"cannot profile dataset with source_type={dataset.source_type!r}; "
            f"only {SOURCE_TYPE_CSV_UPLOAD!r} datasets are supported"
        )

    csv_path = settings.ingestion_storage_root / dataset.storage_path
    frame = pl.read_csv(csv_path, infer_schema_length=0)
    profiles = profile_columns(frame)

    for profile in profiles:
        session.add(
            DatasetColumnProfileModel(
                dataset_id=dataset.id,
                column_name=profile.name,
                inferred_type=profile.inferred_type,
                row_count=profile.row_count,
                missing_count=profile.missing_count,
                missingness=profile.missingness,
                distinct_count=profile.distinct_count,
                min_value=profile.min_value,
                max_value=profile.max_value,
                semantic_type_guess=profile.semantic_type_guess,
                examples=list(profile.examples),
                examples_suppressed=profile.examples_suppressed,
                suspicious_values=list(profile.suspicious_values),
                suspicious_count=profile.suspicious_count,
            )
        )
    session.flush()
