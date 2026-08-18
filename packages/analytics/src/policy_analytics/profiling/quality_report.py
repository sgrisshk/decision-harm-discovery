"""Deterministic Data Quality Report (TASK-009).

Aggregates `TASK-007` (`ColumnProfile`) and `TASK-008` (`FeatureTimingClassification`) output plus
a small set of row-level facts computed directly from the same in-memory dataframe those stages
already loaded — never a second, independent guess at column meaning. Produces the machine- and
customer-readable report `agents/DATA_ENGINEER.md` requires: row/column counts, duplicates, date
coverage, missingness, suspicious values, currencies, leakage risks, available outcomes, usable
decision variables, schema warnings, and exactly one overall rating.

No ML/black-box scoring (`ADR-004`): the rating is a disclosed threshold decision tree over
already-computed facts, not a learned or opaque score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl
from policy_schemas.domain import DataQualityRating, FeatureTiming

from policy_analytics.profiling.feature_timing import FeatureTimingClassification
from policy_analytics.profiling.schema_profiler import ColumnProfile

#: Below this row count, statistical validation and discovery cannot do anything meaningful —
#: aligned with the validation contract's own gate G03 `min_exposed_records` floor
#: (`docs/analytics/validation-contract.md`), not a second, independently invented number.
MIN_ROWS_FOR_READY = 50

#: A column missing more than this fraction of its values is a real, disclosed limitation.
HIGH_MISSINGNESS_THRESHOLD = 0.30

#: A dataset with more than this fraction of exact-duplicate rows suggests an export/ingestion
#: problem worth surfacing, not silent acceptance.
HIGH_DUPLICATE_ROW_RATIO = 0.05

#: Column-name signal for currency-coded fields, aligned with
#: `feature_timing._METADATA_NAME_HINTS`'s "currency" hint (small deliberate duplication, not a
#: private cross-module import).
_CURRENCY_COLUMN_NAME_HINTS = frozenset({"currency"})


@dataclass(frozen=True, slots=True)
class DateCoverage:
    column_name: str
    min_date: str
    max_date: str


@dataclass(frozen=True, slots=True)
class ExcludedColumn:
    """Every column not usable as a `DECISION_TIME` explanatory feature, with why."""

    column_name: str
    timing: FeatureTiming
    reason: str


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    row_count: int
    column_count: int
    duplicate_row_count: int
    distinct_row_count: int
    date_coverage: tuple[DateCoverage, ...]
    detected_currencies: tuple[str, ...]
    total_missing_cells: int
    overall_missingness: float
    columns_with_high_missingness: tuple[str, ...]
    total_suspicious_values: int
    columns_with_suspicious_values: tuple[str, ...]
    excluded_columns: tuple[ExcludedColumn, ...]
    available_outcomes: tuple[str, ...]
    usable_decision_variables: tuple[str, ...]
    unknown_columns: tuple[str, ...]
    constant_decision_variables: tuple[str, ...]
    schema_warnings: tuple[str, ...]
    rating: DataQualityRating
    rating_reasons: tuple[str, ...] = field(default_factory=tuple)


def _duplicate_row_counts(frame: pl.DataFrame) -> tuple[int, int]:
    distinct_row_count = frame.n_unique()
    duplicate_row_count = frame.height - distinct_row_count
    return duplicate_row_count, distinct_row_count


def _date_coverage(profiles: tuple[ColumnProfile, ...]) -> tuple[DateCoverage, ...]:
    return tuple(
        DateCoverage(column_name=p.name, min_date=p.min_value, max_date=p.max_value)
        for p in profiles
        if p.inferred_type == "date" and p.min_value is not None and p.max_value is not None
    )


def _detected_currencies(
    frame: pl.DataFrame, profiles: tuple[ColumnProfile, ...]
) -> tuple[str, ...]:
    values: set[str] = set()
    for profile in profiles:
        if profile.name.lower() not in _CURRENCY_COLUMN_NAME_HINTS:
            continue
        column_values = frame[profile.name].drop_nulls().unique().to_list()
        values.update(str(v) for v in column_values)
    return tuple(sorted(values))


def build_quality_report(
    frame: pl.DataFrame,
    profiles: tuple[ColumnProfile, ...],
    classifications: tuple[FeatureTimingClassification, ...],
) -> DataQualityReport:
    """Build the report. `profiles` and `classifications` must be the same length, in the same
    column order, as produced by `TASK-007`/`TASK-008` for this exact `frame`."""
    if len(profiles) != len(classifications):
        raise ValueError("profiles and classifications must describe the same columns")
    timing_by_column = {c.column_name: c for c in classifications}

    row_count = frame.height
    column_count = len(profiles)
    duplicate_row_count, distinct_row_count = _duplicate_row_counts(frame)

    total_missing_cells = sum(p.missing_count for p in profiles)
    total_cells = row_count * column_count
    overall_missingness = total_missing_cells / total_cells if total_cells else 0.0
    columns_with_high_missingness = tuple(
        p.name for p in profiles if p.missingness > HIGH_MISSINGNESS_THRESHOLD
    )

    total_suspicious_values = sum(p.suspicious_count for p in profiles)
    columns_with_suspicious_values = tuple(p.name for p in profiles if p.suspicious_count > 0)

    excluded_columns = tuple(
        ExcludedColumn(column_name=c.column_name, timing=c.timing, reason=c.reason)
        for c in classifications
        if c.timing is not FeatureTiming.DECISION_TIME
    )
    available_outcomes = tuple(
        c.column_name for c in classifications if c.timing is FeatureTiming.OUTCOME
    )
    usable_decision_variables = tuple(
        c.column_name for c in classifications if c.timing is FeatureTiming.DECISION_TIME
    )
    unknown_columns = tuple(
        c.column_name for c in classifications if c.timing is FeatureTiming.UNKNOWN
    )
    constant_decision_variables = tuple(
        p.name
        for p in profiles
        if timing_by_column[p.name].timing is FeatureTiming.DECISION_TIME and p.distinct_count <= 1
    )

    reasons: list[str] = []

    if row_count < MIN_ROWS_FOR_READY:
        reasons.append(f"only {row_count} rows, below the {MIN_ROWS_FOR_READY}-row usability floor")
    if not usable_decision_variables:
        reasons.append("no column was classified as a usable decision-time variable")
    if not available_outcomes:
        reasons.append("no column was classified as an available outcome")

    if reasons:
        rating = DataQualityRating.NOT_READY
    else:
        limitation_reasons: list[str] = []
        if unknown_columns:
            limitation_reasons.append(
                f"{len(unknown_columns)} column(s) require manual review (UNKNOWN)"
            )
        if columns_with_high_missingness:
            limitation_reasons.append(
                f"{len(columns_with_high_missingness)} column(s) exceed "
                f"{HIGH_MISSINGNESS_THRESHOLD:.0%} missingness"
            )
        if row_count and duplicate_row_count / row_count > HIGH_DUPLICATE_ROW_RATIO:
            limitation_reasons.append(
                f"{duplicate_row_count} duplicate row(s) exceed the "
                f"{HIGH_DUPLICATE_ROW_RATIO:.0%} threshold"
            )
        if columns_with_suspicious_values:
            limitation_reasons.append(
                f"{len(columns_with_suspicious_values)} column(s) contain suspicious values"
            )
        if constant_decision_variables:
            limitation_reasons.append(
                f"{len(constant_decision_variables)} decision-time column(s) are constant "
                "(no variance, unusable for discovery)"
            )

        if limitation_reasons:
            rating = DataQualityRating.READY_WITH_LIMITATIONS
            reasons = limitation_reasons
        else:
            rating = DataQualityRating.READY
            reasons = [
                "no missingness, duplicate, suspicious-value, or unknown-column limitations found"
            ]

    return DataQualityReport(
        row_count=row_count,
        column_count=column_count,
        duplicate_row_count=duplicate_row_count,
        distinct_row_count=distinct_row_count,
        date_coverage=_date_coverage(profiles),
        detected_currencies=_detected_currencies(frame, profiles),
        total_missing_cells=total_missing_cells,
        overall_missingness=overall_missingness,
        columns_with_high_missingness=columns_with_high_missingness,
        total_suspicious_values=total_suspicious_values,
        columns_with_suspicious_values=columns_with_suspicious_values,
        excluded_columns=excluded_columns,
        available_outcomes=available_outcomes,
        usable_decision_variables=usable_decision_variables,
        unknown_columns=unknown_columns,
        constant_decision_variables=constant_decision_variables,
        schema_warnings=tuple(reasons),
        rating=rating,
        rating_reasons=tuple(reasons),
    )
