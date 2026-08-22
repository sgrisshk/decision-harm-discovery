"""TASK-061 follow-up: the analytical-dataset bridge for the 6 non-travel domains.

Parameterized over every domain in `DOMAIN_REGISTRY` — the same shape
`tests/analytics/test_domain_benchmarks.py` already uses — so `analytical_bridge`'s
`AnalyticalDatasetConfig`/`OutcomeContractInputs` derivation and `build_analytical_dataset` itself
are checked against the same leakage/reproducibility guarantees `test_analytical_dataset.py`
already asserts for travel, without a single line of per-domain test code.
"""

from pathlib import Path
from typing import Any

import polars as pl
import pytest
from policy_analytics.analytical_dataset import (
    DATASET_VERSION,
    AnalyticalDatasetConfig,
    build_analytical_dataset,
)
from policy_analytics.discovery.engine import DiscoveryConfig, discover_candidates
from policy_analytics.domain_benchmarks.analytical_bridge import (
    analytical_dataset_config,
    provisional_outcome_contract,
    provisional_primary_outcome,
    temporal_split_config,
)
from policy_analytics.domain_benchmarks.common import (
    DomainSpec,
    run_domain_benchmark,
    standard_variant_config,
)
from policy_analytics.domain_benchmarks.registry import DOMAIN_REGISTRY
from policy_analytics.temporal_splits import build_temporal_split_manifest

DOMAINS = sorted(DOMAIN_REGISTRY.items())
DOMAIN_IDS = [domain_id for domain_id, _ in DOMAINS]
_TEST_ROW_COUNT = 400
_SEED = 20260820


def _build(spec: DomainSpec, tmp_path: Path) -> tuple[dict[str, Any], Path]:
    raw_root = tmp_path / "raw" / spec.domain_id
    config = standard_variant_config(spec, "comparable", seed=_SEED, row_count=_TEST_ROW_COUNT)
    run_domain_benchmark(spec, config, raw_root)
    manifest = build_analytical_dataset(
        raw_root / "reference" / f"{spec.domain_id}_clean.csv",
        raw_root / "metadata" / "feature_timing.json",
        tmp_path / "analytical",
        analytical_dataset_config(spec),
        provisional_outcome_contract(spec),
    )
    root = tmp_path / "analytical" / manifest["dataset_version"]
    build_temporal_split_manifest(root, temporal_split_config(spec))
    return manifest, root


@pytest.mark.analytics
@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_bridge_separates_roles_and_blocks_leakage(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    manifest, root = _build(spec, tmp_path)
    features = pl.read_csv(root / "features.csv")
    outcomes = pl.read_csv(root / "outcomes.csv")
    identifiers = pl.read_csv(root / "identifiers.csv")
    metadata = pl.read_csv(root / "metadata.csv")

    assert manifest["dataset_version"] == f"{domain_id}-analytical-v1.0.0"
    assert manifest["schema_version"] == spec.schema_version
    assert manifest["primary_outcome"] == spec.primary_outcome_column
    # PROVISIONAL, never ATTACHED — this is the load-bearing distinction from travel's real,
    # STATISTICS-reviewed TASK-013 contract; a manifest reader must never confuse the two.
    assert manifest["outcome_contract"]["status"] == "PROVISIONAL"
    assert manifest["outcome_contract"]["owner"] == "DATA_ENGINEER"

    post_decision = {
        name
        for name, (classification, _) in spec.feature_timing.items()
        if classification == "POST_DECISION"
    }
    assert spec.primary_outcome_column not in features.columns
    assert not post_decision & set(features.columns)
    assert spec.primary_outcome_column in outcomes.columns
    assert set(identifiers.columns) == {spec.primary_id_column, spec.clustering_key}
    assert "split_label" in metadata.columns
    assert "source_currency" in metadata.columns  # every TASK-061 domain has a currency column
    assert set(metadata["split_label"]) == {"development", "validation", "future_holdout"}
    assert all(
        frame.height == _TEST_ROW_COUNT for frame in (features, outcomes, identifiers, metadata)
    )
    assert (root / "split_manifest.json").is_file()
    assert (root / "split_membership.csv").is_file()


@pytest.mark.analytics
@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_bridge_is_reproducible(domain_id: str, spec: DomainSpec, tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    config = standard_variant_config(spec, "comparable", seed=_SEED, row_count=_TEST_ROW_COUNT)
    run_domain_benchmark(spec, config, raw_root)
    source_csv = raw_root / "reference" / f"{domain_id}_clean.csv"
    feature_timing_path = raw_root / "metadata" / "feature_timing.json"

    first = build_analytical_dataset(
        source_csv,
        feature_timing_path,
        tmp_path / "first",
        analytical_dataset_config(spec),
        provisional_outcome_contract(spec),
    )
    second = build_analytical_dataset(
        source_csv,
        feature_timing_path,
        tmp_path / "second",
        analytical_dataset_config(spec),
        provisional_outcome_contract(spec),
    )
    assert first["dataset_identity_sha256"] == second["dataset_identity_sha256"]
    for role in ("features", "outcomes", "identifiers", "metadata"):
        assert first["partitions"][role]["sha256"] == second["partitions"][role]["sha256"]

    with pytest.raises(FileExistsError):
        build_analytical_dataset(
            source_csv,
            feature_timing_path,
            tmp_path / "first",
            analytical_dataset_config(spec),
            provisional_outcome_contract(spec),
        )


@pytest.mark.analytics
def test_bridge_never_touches_the_travel_default_config() -> None:
    """`analytical_dataset_config`/`provisional_outcome_contract` are TASK-061-only helpers; the
    travel path (`build_analytical_dataset` called with no `config`/`outcome_contract`) must still
    resolve to its own unchanged defaults, not anything from this bridge."""
    default = AnalyticalDatasetConfig()
    assert default.dataset_version == DATASET_VERSION == "travel-bookings-analytical-v1.1.0"
    assert default.identifier_column == "booking_id"
    assert default.currency_column == "currency"
    assert default.calendar_source_column == "travel_date"


@pytest.mark.analytics
def test_local_discovery_runs_end_to_end_on_one_domain(tmp_path: Path) -> None:
    """Proof-of-concept required by the task: at least one TASK-061 domain must actually be valid
    `discover_candidates` input, not merely produce files that compile. Insurance chosen
    arbitrarily — the bridge is domain-agnostic, this is not a claim any one domain is special."""
    spec = DOMAIN_REGISTRY["insurance"]
    manifest, root = _build(spec, tmp_path)

    features = pl.read_csv(root / "features.csv")
    outcomes = pl.read_csv(root / "outcomes.csv")
    metadata = pl.read_csv(root / "metadata.csv")
    frame = pl.concat([features, outcomes, metadata.select("split_label")], how="horizontal")

    outcome = provisional_primary_outcome(spec)
    assert outcome.column == manifest["primary_outcome"]
    result = discover_candidates(
        frame,
        tuple(features.columns),
        outcome,
        DiscoveryConfig(min_n=10, min_support=0.01, max_support=0.9),
    )
    assert result["outcome"]["column"] == spec.primary_outcome_column
    assert result["search"]["evaluated_hypotheses"] > 0
    # Not asserting candidate_count > 0: this is a small (400-row), unseeded-for-discovery smoke
    # sample, not a claim any particular pattern is recoverable — that is TASK-015/016's job, on
    # real full-scale data. The assertion that matters here is structural: the engine ran to
    # completion against real TASK-061 columns/splits without any adaptation on its side.
