from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import polars as pl
import pytest
from policy_analytics.profiling.feature_timing import classify_columns
from policy_analytics.profiling.quality_report import (
    MIN_ROWS_FOR_READY,
    build_quality_report,
)
from policy_analytics.profiling.schema_profiler import profile_columns
from policy_schemas.domain import DataQualityRating

pytestmark = pytest.mark.analytics

REPOSITORY = Path(__file__).resolve().parents[2]
BENCHMARK_CSV = REPOSITORY / "synthetic_data/raw/travel_bookings_dirty.csv"


def _report(frame: pl.DataFrame):
    profiles = profile_columns(frame)
    classifications = classify_columns(profiles)
    return build_quality_report(frame, profiles, classifications)


def _frame(rows: Sequence[Mapping[str, str | None]]) -> pl.DataFrame:
    # profile_columns/build_quality_report both require an all-Utf8 frame (see
    # schema_profiler.profile_columns' own precondition) — cast explicitly rather than relying on
    # inference, matching how the real pipeline reads CSVs with `infer_schema_length=0`.
    return pl.DataFrame(rows).select(pl.all().cast(pl.Utf8))


def _clean_frame(n: int = 60) -> pl.DataFrame:
    """A dataset that should clear every limitation: enough rows, no missingness, no duplicates,
    no suspicious values, at least one decision-time and one outcome column."""
    return _frame(
        [
            {
                "booking_id": f"B{i}",
                "destination": "Rome" if i % 2 == 0 else "Tokyo",
                "cancellation": "True" if i % 5 == 0 else "False",
            }
            for i in range(n)
        ]
    )


def test_clean_dataset_rates_ready() -> None:
    report = _report(_clean_frame())
    assert report.rating is DataQualityRating.READY
    assert report.duplicate_row_count == 0
    assert report.total_suspicious_values == 0
    assert report.unknown_columns == ()
    assert "booking_id" not in report.usable_decision_variables  # identifier, not a variable
    assert "destination" in report.usable_decision_variables
    assert "cancellation" in report.available_outcomes


def test_row_count_below_floor_is_not_ready() -> None:
    frame = _frame(
        [{"destination": "Rome", "cancellation": "True"} for _ in range(MIN_ROWS_FOR_READY - 1)]
    )
    report = _report(frame)
    assert report.rating is DataQualityRating.NOT_READY
    assert any("rows" in reason for reason in report.rating_reasons)


def test_no_outcome_column_is_not_ready() -> None:
    frame = _frame([{"destination": "Rome", "manager": "Manager 1"} for _ in range(60)])
    report = _report(frame)
    assert report.rating is DataQualityRating.NOT_READY
    assert any("outcome" in reason for reason in report.rating_reasons)


def test_no_decision_time_column_is_not_ready() -> None:
    """Every column is either an outcome or excluded — nothing left to explain with."""
    frame = _frame([{"cancellation": "True", "refund_date": "2025-01-01"} for _ in range(60)])
    report = _report(frame)
    assert report.rating is DataQualityRating.NOT_READY
    assert any("decision-time" in reason for reason in report.rating_reasons)


def test_unknown_column_downgrades_to_ready_with_limitations() -> None:
    rows = [
        {"destination": "Rome" if i % 2 == 0 else "Tokyo", "cancellation": "True", "x_field": "9"}
        for i in range(60)
    ]
    report = _report(_frame(rows))
    assert report.rating is DataQualityRating.READY_WITH_LIMITATIONS
    assert "x_field" in report.unknown_columns
    assert any("UNKNOWN" in reason for reason in report.rating_reasons)


def test_high_missingness_downgrades_to_ready_with_limitations() -> None:
    rows = [
        {
            "destination": "Rome" if i % 2 == 0 else "Tokyo",
            "cancellation": "True",
            "installments": None if i < 40 else "1",  # 40/60 = 66% missing, over the threshold
        }
        for i in range(60)
    ]
    report = _report(_frame(rows))
    assert "installments" in report.columns_with_high_missingness
    assert report.rating is DataQualityRating.READY_WITH_LIMITATIONS


def test_high_duplicate_ratio_downgrades_to_ready_with_limitations() -> None:
    unique_rows = [
        {
            "booking_id": f"B{i}",
            "destination": "Rome" if i % 2 == 0 else "Tokyo",
            "cancellation": "True",
        }
        for i in range(55)
    ]
    duplicated = unique_rows + unique_rows[:10]  # 10/65 ≈ 15%, over HIGH_DUPLICATE_ROW_RATIO
    report = _report(_frame(duplicated))
    assert report.duplicate_row_count == 10
    assert report.distinct_row_count == 55
    assert report.rating is DataQualityRating.READY_WITH_LIMITATIONS


def test_constant_decision_variable_downgrades_to_ready_with_limitations() -> None:
    rows = [
        {"destination": "Rome", "cancellation": "True" if i % 5 == 0 else "False"}
        for i in range(60)
    ]
    report = _report(_frame(rows))
    assert "destination" in report.constant_decision_variables
    assert report.rating is DataQualityRating.READY_WITH_LIMITATIONS


def test_currency_column_values_are_detected() -> None:
    rows = [
        {"destination": "Rome", "cancellation": "True", "currency": "EUR" if i < 40 else "USD"}
        for i in range(60)
    ]
    report = _report(_frame(rows))
    assert report.detected_currencies == ("EUR", "USD")
    # currency is METADATA, never a usable decision variable or leakage-relevant outcome
    assert "currency" not in report.usable_decision_variables
    assert "currency" not in report.available_outcomes


def test_date_coverage_reports_min_and_max_per_date_column() -> None:
    rows = [
        {
            "booking_date": d,
            "destination": "Rome",
            "cancellation": "True",
        }
        for d in ("2024-01-01", "2024-06-15", "2024-12-31")
    ]
    report = _report(_frame(rows))
    coverage = {c.column_name: c for c in report.date_coverage}
    assert coverage["booking_date"].min_date == "2024-01-01"
    assert coverage["booking_date"].max_date == "2024-12-31"


def test_mismatched_profiles_and_classifications_length_raises() -> None:
    frame = _clean_frame()
    profiles = profile_columns(frame)
    with pytest.raises(ValueError, match="same columns"):
        build_quality_report(frame, profiles, classify_columns(profiles)[:1])


@pytest.mark.skipif(not BENCHMARK_CSV.exists(), reason="synthetic benchmark artifact not present")
def test_benchmark_report_is_internally_consistent() -> None:
    """Not a ground-truth comparison (no reference quality report exists for this artifact) —
    just proves the report is coherent and sane against real, deliberately dirty data."""
    frame = pl.read_csv(BENCHMARK_CSV, infer_schema_length=0)
    report = _report(frame)

    assert report.row_count == frame.height
    assert report.column_count == len(frame.columns)
    assert report.distinct_row_count + report.duplicate_row_count == report.row_count
    assert set(report.usable_decision_variables) | {
        e.column_name for e in report.excluded_columns
    } == set(frame.columns)
    assert report.detected_currencies == ("EUR",)
    # This artifact is deliberately dirty (docs/benchmark/simulation-report.md) — it must not
    # score a false-clean READY.
    assert report.rating is not DataQualityRating.READY
