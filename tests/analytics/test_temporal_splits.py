from pathlib import Path

import polars as pl
import pytest
from policy_analytics.analytical_dataset import build_analytical_dataset
from policy_analytics.synthetic_benchmark import BenchmarkConfig, generate_benchmark
from policy_analytics.temporal_splits import (
    TemporalSplitConfig,
    assign_temporal_splits,
    build_temporal_split_manifest,
)


@pytest.mark.analytics
def test_boundary_behavior_and_chronological_ordering() -> None:
    dates = pl.Series(
        "booking_date",
        ["2024-01-01", "2024-12-31", "2025-01-01", "2025-06-30", "2025-07-01", "2025-12-31"],
    )
    assert assign_temporal_splits(dates).to_list() == [
        "development",
        "development",
        "validation",
        "validation",
        "future_holdout",
        "future_holdout",
    ]


@pytest.mark.analytics
def test_split_is_deterministic_non_overlapping_and_outcomes_final(tmp_path: Path) -> None:
    benchmark = tmp_path / "benchmark"
    generate_benchmark(benchmark, BenchmarkConfig(row_count=1_000))
    analytical = tmp_path / "analytical"
    build_analytical_dataset(
        benchmark / "reference/travel_bookings_clean.csv",
        benchmark / "metadata/feature_timing.json",
        analytical,
    )
    root = analytical / "travel-bookings-analytical-v1.0.0"
    first = build_temporal_split_manifest(root)
    first_bytes = (root / "split_manifest.json").read_bytes()
    second = build_temporal_split_manifest(root)
    membership = pl.read_csv(root / "split_membership.csv")
    assert first == second
    assert first_bytes == (root / "split_manifest.json").read_bytes()
    assert membership["booking_id"].n_unique() == membership.height
    assert membership["split_label"].null_count() == 0
    assert first["assignment_invariants"]["overlap_count"] == 0
    assert first["outcome_availability"]["all_rows_final"] is True
    assert membership["outcomes_final"].all()


@pytest.mark.analytics
def test_invalid_boundaries_and_out_of_window_records_fail() -> None:
    invalid = TemporalSplitConfig(validation_start="2024-12-31")
    with pytest.raises(ValueError, match="contiguous"):
        assign_temporal_splits(pl.Series("booking_date", ["2024-01-01"]), invalid)
    with pytest.raises(ValueError, match="outside"):
        assign_temporal_splits(pl.Series("booking_date", ["2026-01-01"]))
    with pytest.raises(ValueError, match="maturation"):
        assign_temporal_splits(
            pl.Series("booking_date", ["2024-01-01"]),
            TemporalSplitConfig(outcome_availability_mode="LIVE_DATA"),
        )
