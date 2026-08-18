"""Persistence wiring for TASK-008 feature-timing classification.

The pure computation lives in `policy_analytics.profiling.feature_timing` (no I/O, no DB) — this
module only takes the profiles `TASK-007` already computed and writes the result to
`DatasetModel.columns` (the `DatasetColumn` list `TASK-007` deliberately left empty).
"""

from __future__ import annotations

from policy_analytics.profiling.feature_timing import FeatureTimingClassification, classify_columns
from policy_analytics.profiling.schema_profiler import ColumnProfile
from policy_schemas.domain import DatasetColumn

from app.db.models import DatasetModel


def classify_dataset_timing(
    dataset: DatasetModel, profiles: tuple[ColumnProfile, ...]
) -> tuple[FeatureTimingClassification, ...]:
    """Classify `profiles`, set `dataset.columns` in place, and return the classifications so
    callers can chain `TASK-009`'s data-quality report without reclassifying. Does not commit.

    A profiling failure upstream already leaves `dataset.columns` at its empty default (`TASK-007`
    never calls this when it raises), so a dataset can legitimately have profiles with no timing
    classification yet, but never a timing classification without profiles.
    """
    classifications = classify_columns(profiles)
    dataset.columns = [
        DatasetColumn(
            name=classification.column_name,
            data_type=profile.inferred_type,
            timing=classification.timing,
            nullable=profile.missing_count > 0,
        ).model_dump(mode="json")
        for classification, profile in zip(classifications, profiles, strict=True)
    ]
    return classifications
