import hashlib
import json
from pathlib import Path

import polars as pl
import pytest
from policy_analytics.analytical_dataset import build_analytical_dataset
from policy_analytics.domain_benchmarks.analytical_bridge import (
    analytical_dataset_config,
    provisional_outcome_contract,
    temporal_split_config,
)
from policy_analytics.domain_benchmarks.common import (
    run_domain_benchmark,
    standard_variant_config,
)
from policy_analytics.domain_benchmarks.registry import DOMAIN_REGISTRY
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
    root = analytical / "travel-bookings-analytical-v1.1.0"
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


@pytest.mark.analytics
def test_b2b_split_contract_is_public_deterministic_and_development_only(tmp_path: Path) -> None:
    spec = DOMAIN_REGISTRY["b2b_sales"]
    raw_root = tmp_path / "b2b_sales" / "comparable"
    run_domain_benchmark(
        spec,
        standard_variant_config(spec, "comparable", seed=20260820, row_count=500),
        raw_root,
    )
    analytical_root = tmp_path / "analytical"
    analytical = build_analytical_dataset(
        raw_root / "reference/b2b_sales_clean.csv",
        raw_root / "metadata/feature_timing.json",
        analytical_root,
        analytical_dataset_config(spec),
        provisional_outcome_contract(spec),
    )
    root = analytical_root / analytical["dataset_version"]
    config = temporal_split_config(spec)

    first = build_temporal_split_manifest(root, config)
    first_manifest_bytes = (root / "split_manifest.json").read_bytes()
    first_membership_bytes = (root / "split_membership.csv").read_bytes()
    second = build_temporal_split_manifest(root, config)
    membership = pl.read_csv(root / "split_membership.csv")

    assert first == second
    assert first_manifest_bytes == (root / "split_manifest.json").read_bytes()
    assert first_membership_bytes == (root / "split_membership.csv").read_bytes()
    assert membership.columns == ["deal_id", "deal_created_date", "split_label", "outcomes_final"]
    assert membership["deal_id"].n_unique() == membership.height == 500
    assert membership["split_label"].null_count() == 0
    assert set(membership["split_label"]) == {
        "development",
        "validation",
        "future_holdout",
    }
    assert first["discovery_usage"] == {
        "search_fit_split": "development",
        "diagnostic_only_splits": ["validation", "future_holdout"],
        "permitted_development_rows": first["splits"]["development"]["row_count"],
    }
    assert first["analytical_dataset_identity_sha256"] == analytical["dataset_identity_sha256"]
    assert (
        first["membership_artifact"]["sha256"] == hashlib.sha256(first_membership_bytes).hexdigest()
    )
    stored = json.loads((root / "split_manifest.json").read_text())
    assert stored["outcome_availability"]["contract_version"] == "0.1.0-provisional"
    assert stored["reproducibility_command"].endswith("--domain b2b_sales")
