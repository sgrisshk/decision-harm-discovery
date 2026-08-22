import json
from pathlib import Path

import polars as pl
import pytest
from policy_analytics.analytical_dataset import (
    AnalyticalDatasetConfig,
    build_analytical_dataset,
    compute_exposure_group_missingness,
)
from policy_analytics.blind_isolation import prepare_blind_workspace
from policy_analytics.synthetic_benchmark import BenchmarkConfig, generate_benchmark


@pytest.mark.analytics
def test_builder_separates_roles_and_blocks_leakage(tmp_path: Path) -> None:
    benchmark = tmp_path / "benchmark"
    generate_benchmark(benchmark, BenchmarkConfig(row_count=1_000))
    output = tmp_path / "analytical"

    manifest = build_analytical_dataset(
        benchmark / "reference/travel_bookings_clean.csv",
        benchmark / "metadata/feature_timing.json",
        output,
    )
    root = output / AnalyticalDatasetConfig().dataset_version
    features = pl.read_csv(root / "features.csv")
    outcomes = pl.read_csv(root / "outcomes.csv")
    identifiers = pl.read_csv(root / "identifiers.csv")
    metadata = pl.read_csv(root / "metadata.csv")

    assert manifest["schema_version"] == "travel-bookings-analytical-schema-v1.1.0"
    assert manifest["canonical_schema_version"] == "travel-booking-canonical-v1.0.0"
    assert manifest["primary_outcome"] == "contribution_margin_eur"
    assert manifest["outcome_contract"]["status"] == "ATTACHED"
    assert manifest["outcome_contract"]["owner"] == "STATISTICS"
    assert "contribution_margin_eur" not in features.columns
    assert "support_cases" not in features.columns
    assert "travel_month" in features.columns
    assert features["travel_month"].to_list() == [
        int(value.split("-")[1]) for value in features["travel_date"].to_list()
    ]
    assert manifest["feature_timing"]["travel_month"] == {
        "classification": "DECISION_TIME",
        "discovery_feature_allowed": True,
        "leakage_risk": "LOW",
    }
    lineage = manifest["derived_feature_lineage"]["travel_month"]
    assert lineage["source_columns"] == ["travel_date"]
    assert lineage["transformation_version"] == "1.1.0"
    assert "contribution_margin_eur" in outcomes.columns
    assert identifiers.columns == ["booking_id", "customer_id"]
    assert metadata.columns == ["source_row_number", "split_label", "source_currency"]
    assert set(metadata["split_label"]) == {"development", "validation", "future_holdout"}
    assert all(frame.height == 1_000 for frame in (features, outcomes, identifiers, metadata))
    assert (root / "feature_manifest.json").exists()
    assert (root / "outcome_columns_manifest.json").exists()
    assert (root / "excluded_columns_manifest.json").exists()
    assert (root / "version_metadata.json").exists()


@pytest.mark.analytics
def test_travel_month_boundaries_and_invalid_dates_fail_closed(tmp_path: Path) -> None:
    benchmark = tmp_path / "benchmark"
    generate_benchmark(benchmark, BenchmarkConfig(row_count=200))
    source = benchmark / "reference/travel_bookings_clean.csv"
    frame = pl.read_csv(source, try_parse_dates=False)
    frame = frame.with_columns(
        pl.Series(
            "travel_date",
            ["2024-01-31", "2024-02-01", *frame["travel_date"].to_list()[2:]],
        )
    )
    boundary_source = tmp_path / "boundary.csv"
    frame.write_csv(boundary_source)
    output = tmp_path / "boundary-output"
    build_analytical_dataset(
        boundary_source,
        benchmark / "metadata/feature_timing.json",
        output,
    )
    features = pl.read_csv(output / AnalyticalDatasetConfig().dataset_version / "features.csv")
    assert features["travel_month"].head(2).to_list() == [1, 2]

    for bad_value in (None, "2024-02-30"):
        invalid = frame.with_columns(
            pl.Series("travel_date", [bad_value, *frame["travel_date"].to_list()[1:]])
        )
        invalid_source = tmp_path / f"invalid-{bad_value}.csv"
        invalid.write_csv(invalid_source)
        with pytest.raises(ValueError, match="calendar source column"):
            build_analytical_dataset(
                invalid_source,
                benchmark / "metadata/feature_timing.json",
                tmp_path / f"invalid-output-{bad_value}",
            )


@pytest.mark.analytics
def test_builder_is_reproducible_and_manifest_has_lineage(tmp_path: Path) -> None:
    benchmark = tmp_path / "benchmark"
    generate_benchmark(benchmark, BenchmarkConfig(row_count=500))
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = build_analytical_dataset(
        benchmark / "reference/travel_bookings_clean.csv",
        benchmark / "metadata/feature_timing.json",
        first,
    )
    second_manifest = build_analytical_dataset(
        benchmark / "reference/travel_bookings_clean.csv",
        benchmark / "metadata/feature_timing.json",
        second,
    )

    assert first_manifest["dataset_identity_sha256"] == second_manifest["dataset_identity_sha256"]
    for role in ("features", "outcomes", "identifiers", "metadata"):
        assert (
            first_manifest["partitions"][role]["sha256"]
            == second_manifest["partitions"][role]["sha256"]
        )
    stored = json.loads(
        (first / AnalyticalDatasetConfig().dataset_version / "manifest.json").read_text()
    )
    assert stored["source"]["sha256"]
    assert stored["clustering"]["column"] == "customer_id"
    assert stored["partitions"]["features"]["path"] == "features.csv"

    with pytest.raises(FileExistsError):
        build_analytical_dataset(
            benchmark / "reference/travel_bookings_clean.csv",
            benchmark / "metadata/feature_timing.json",
            first,
        )

    changed = build_analytical_dataset(
        benchmark / "reference/travel_bookings_clean.csv",
        benchmark / "metadata/feature_timing.json",
        tmp_path / "changed",
        AnalyticalDatasetConfig(transformation_version="1.0.1"),
    )
    assert changed["dataset_identity_sha256"] != first_manifest["dataset_identity_sha256"]


@pytest.mark.analytics
def test_candidate_exposure_missingness_requires_aligned_boolean_groups() -> None:
    frame = pl.DataFrame({"outcome": [1.0, None, 2.0, None]})
    result = compute_exposure_group_missingness(
        frame, pl.Series("exposure", [True, True, False, False])
    )

    assert result["exposed"]["outcome"] == 50.0
    assert result["unexposed"]["outcome"] == 50.0
    with pytest.raises(ValueError, match="boolean series"):
        compute_exposure_group_missingness(frame, pl.Series("bad", [1, 0]))


@pytest.mark.analytics
def test_travel_month_is_visible_in_allowlisted_blind_workspace(tmp_path: Path) -> None:
    repository = Path(__file__).parents[2]
    workspace = tmp_path / "blind-workspace"
    prepare_blind_workspace(
        repository,
        workspace,
        b"calendar-feature-test-evaluator-key-at-least-32-bytes",
    )
    root = workspace / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
    features = pl.read_csv(root / "features.csv")
    timing = json.loads((workspace / "public/feature_timing.json").read_text())
    assert "travel_month" in features.columns
    assert timing["columns"]["travel_month"]["classification"] == "DECISION_TIME"
    assert not (workspace / "synthetic_data/evaluation").exists()
