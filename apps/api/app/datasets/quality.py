"""Persistence wiring for TASK-009 Data Quality Report.

The pure computation lives in `policy_analytics.profiling.quality_report` (no I/O, no DB) — this
module only takes what `TASK-007`/`TASK-008` already computed for this exact upload, plus the same
in-memory dataframe those stages loaded (read once, not re-read from disk here), and persists the
result as a single JSONB document on `DatasetModel.quality_report`.
"""

from __future__ import annotations

import dataclasses

import polars as pl
from policy_analytics.profiling.feature_timing import FeatureTimingClassification
from policy_analytics.profiling.quality_report import DataQualityReport, build_quality_report
from policy_analytics.profiling.schema_profiler import ColumnProfile

from app.db.models import DatasetModel


def build_and_store_quality_report(
    dataset: DatasetModel,
    frame: pl.DataFrame,
    profiles: tuple[ColumnProfile, ...],
    classifications: tuple[FeatureTimingClassification, ...],
) -> DataQualityReport:
    """Build the report and set `dataset.quality_report` in place. Does not commit.

    `FeatureTiming`/`DataQualityRating` are `StrEnum` members, so `dataclasses.asdict` alone
    already yields a JSON-serializable document — no separate manual serializer needed.
    """
    report = build_quality_report(frame, profiles, classifications)
    dataset.quality_report = dataclasses.asdict(report)
    return report
