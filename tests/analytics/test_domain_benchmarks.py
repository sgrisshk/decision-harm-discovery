from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from policy_analytics.domain_benchmarks.common import (
    TRAPS_ONLY_COUNT,
    WEAK_PATTERN_COUNT,
    WEAK_PATTERN_SCALE,
    DomainRunConfig,
    DomainSpec,
    raw_marginal_effect,
    run_domain_benchmark,
    standard_variant_config,
)
from policy_analytics.domain_benchmarks.registry import DOMAIN_REGISTRY

pytestmark = pytest.mark.analytics

DOMAINS = sorted(DOMAIN_REGISTRY.items())
DOMAIN_IDS = [domain_id for domain_id, _ in DOMAINS]

#: Keys that must never appear in a public (raw/reference/metadata) artifact — they only belong in
#: evaluation/hidden_ground_truth.json. Mirrors the leakage vocabulary
#: test_synthetic_benchmark.py checks for the travel benchmark.
RESTRICTED_KEYWORDS = (
    "affected_record_ids",
    "realized_counterfactual_effects",
    "true_effect",
    "confounding_traps",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _small_config(spec: DomainSpec, row_count: int = 400) -> DomainRunConfig:
    return DomainRunConfig(
        seed=1,
        row_count=row_count,
        active_patterns=frozenset(p.id for p in spec.patterns),
        active_traps=frozenset(t.id for t in spec.traps),
    )


# --- structural sanity, every domain -----------------------------------------------------------


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_domain_has_at_least_eight_patterns_and_five_traps(
    domain_id: str, spec: DomainSpec
) -> None:
    assert len(spec.patterns) >= 8, domain_id
    assert len(spec.traps) >= 5, domain_id


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_pattern_and_trap_ids_are_unique(domain_id: str, spec: DomainSpec) -> None:
    pattern_ids = [p.id for p in spec.patterns]
    trap_ids = [t.id for t in spec.traps]
    assert len(pattern_ids) == len(set(pattern_ids)), domain_id
    assert len(trap_ids) == len(set(trap_ids)), domain_id


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_feature_timing_and_declared_types_cover_the_same_columns(
    domain_id: str, spec: DomainSpec
) -> None:
    assert set(spec.feature_timing) == set(spec.declared_types), domain_id
    assert spec.primary_id_column in spec.feature_timing, domain_id
    assert spec.clustering_key in spec.feature_timing, domain_id
    assert spec.decision_timestamp_column in spec.feature_timing, domain_id
    assert spec.primary_outcome_column in spec.outcome_columns, domain_id


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_feature_timing_covers_every_generated_column_exactly_once(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = _small_config(spec)
    run_domain_benchmark(spec, config, tmp_path)
    header = set(_read_csv(tmp_path / "reference" / f"{domain_id}_clean.csv")[0])
    assert header == set(spec.feature_timing), domain_id


# --- reproducibility -----------------------------------------------------------------------------


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_generation_is_reproducible(domain_id: str, spec: DomainSpec, tmp_path: Path) -> None:
    config = _small_config(spec)
    first = run_domain_benchmark(spec, config, tmp_path / "first")
    second = run_domain_benchmark(spec, config, tmp_path / "second")
    repeated = run_domain_benchmark(spec, config, tmp_path / "first")
    assert first == second == repeated


# --- leakage safety --------------------------------------------------------------------------


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_no_restricted_keyword_leaks_into_public_artifacts(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = _small_config(spec)
    run_domain_benchmark(spec, config, tmp_path)
    public_text = "".join(
        path.read_text(encoding="utf-8")
        for directory in ("raw", "reference", "metadata")
        for path in (tmp_path / directory).rglob("*")
        if path.is_file()
    )
    for keyword in RESTRICTED_KEYWORDS:
        assert keyword not in public_text, (domain_id, keyword)


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_checksums_never_reference_the_evaluation_directory(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = _small_config(spec)
    checksums = run_domain_benchmark(spec, config, tmp_path)
    assert all(not key.startswith("evaluation/") for key in checksums), domain_id
    assert (tmp_path / "evaluation" / "hidden_ground_truth.json").exists(), domain_id


# --- identity/clustering invariants -------------------------------------------------------------


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_primary_id_is_unique_and_clustering_key_has_multiple_clusters(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = _small_config(spec)
    run_domain_benchmark(spec, config, tmp_path)
    rows = _read_csv(tmp_path / "reference" / f"{domain_id}_clean.csv")
    ids = [row[spec.primary_id_column] for row in rows]
    assert len(ids) == len(set(ids)), domain_id
    clusters = {row[spec.clustering_key] for row in rows}
    assert len(clusters) >= 5, domain_id


# --- dirty-data variant ------------------------------------------------------------------------


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_dirty_variant_has_duplicates_and_stays_leakage_safe(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = DomainRunConfig(
        seed=1,
        row_count=400,
        active_patterns=frozenset(p.id for p in spec.patterns),
        active_traps=frozenset(t.id for t in spec.traps),
        dirty_duplicate_rows=15,
    )
    run_domain_benchmark(spec, config, tmp_path)
    clean_rows = _read_csv(tmp_path / "reference" / f"{domain_id}_clean.csv")
    dirty_rows = _read_csv(tmp_path / "raw" / f"{domain_id}_dirty.csv")
    assert len(dirty_rows) == len(clean_rows) + 15, domain_id
    manifest = json.loads((tmp_path / "metadata" / "corruption_manifest.json").read_text())
    assert manifest["operations"]["duplicate_source_rows"]["count"] == 15, domain_id


# --- ground-truth arithmetic consistency --------------------------------------------------------


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_realized_economic_impact_matches_realized_effect_times_affected_n(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = DomainRunConfig(
        seed=1,
        row_count=1500,
        active_patterns=frozenset(p.id for p in spec.patterns),
        active_traps=frozenset(t.id for t in spec.traps),
    )
    run_domain_benchmark(spec, config, tmp_path)
    truth = json.loads((tmp_path / "evaluation" / "hidden_ground_truth.json").read_text())
    sign = -1 if spec.harm_direction == "decrease_is_harm" else 1
    for pattern in truth["patterns"]:
        effect = pattern["true_effect"]
        if effect["realized_effect"] is None:
            continue
        expected = round(sign * effect["realized_effect"] * effect["affected_n"], 2)
        assert expected == effect["realized_economic_impact"], (domain_id, pattern["id"])


# --- the four required diversity variants --------------------------------------------------------


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_noise_variant_has_zero_patterns_and_zero_traps(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = standard_variant_config(spec, "noise", seed=1, row_count=400)
    run_domain_benchmark(spec, config, tmp_path)
    truth = json.loads((tmp_path / "evaluation" / "hidden_ground_truth.json").read_text())
    assert truth["patterns"] == []
    assert truth["confounding_traps"] == []


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_traps_only_variant_has_zero_patterns_and_some_traps(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = standard_variant_config(spec, "traps_only", seed=1, row_count=400)
    run_domain_benchmark(spec, config, tmp_path)
    truth = json.loads((tmp_path / "evaluation" / "hidden_ground_truth.json").read_text())
    assert truth["patterns"] == []
    assert len(truth["confounding_traps"]) == min(TRAPS_ONLY_COUNT, len(spec.traps))


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_dominant_weak_variant_scales_only_the_weaker_patterns(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = standard_variant_config(spec, "dominant_weak", seed=1, row_count=3000)
    run_domain_benchmark(spec, config, tmp_path)
    truth = json.loads((tmp_path / "evaluation" / "hidden_ground_truth.json").read_text())
    dominant_id = spec.patterns[0].id
    weak_ids = {p.id for p in spec.patterns[1 : 1 + WEAK_PATTERN_COUNT]}
    by_id = {p["id"]: p for p in truth["patterns"]}
    assert set(by_id) == {dominant_id, *weak_ids}, domain_id

    dominant_effect = by_id[dominant_id]["true_effect"]["configured_effect"]
    original_dominant = spec.patterns[0].configured_effect
    assert dominant_effect == original_dominant, domain_id  # untouched, scale == 1.0

    for pattern in spec.patterns[1 : 1 + WEAK_PATTERN_COUNT]:
        scaled = by_id[pattern.id]["true_effect"]["configured_effect"]
        _assert_every_leaf_scaled(
            pattern.configured_effect, scaled, WEAK_PATTERN_SCALE, (domain_id, pattern.id)
        )


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_comparable_variant_activates_every_pattern_and_trap_unscaled(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = standard_variant_config(spec, "comparable", seed=1, row_count=400)
    run_domain_benchmark(spec, config, tmp_path)
    truth = json.loads((tmp_path / "evaluation" / "hidden_ground_truth.json").read_text())
    assert {p["id"] for p in truth["patterns"]} == {p.id for p in spec.patterns}
    assert {t["id"] for t in truth["confounding_traps"]} == {t.id for t in spec.traps}
    for pattern in truth["patterns"]:
        source = next(p for p in spec.patterns if p.id == pattern["id"])
        assert pattern["true_effect"]["configured_effect"] == source.configured_effect


def _assert_every_leaf_scaled(
    original: object, scaled: object, scale: float, context: object
) -> None:
    """Recursively assert every numeric leaf of `scaled` equals the matching leaf of `original`
    times `scale`, walking both structures by key rather than picking "the first" leaf found by
    traversal order — `hidden_ground_truth.json` round-trips through
    `json.dumps(..., sort_keys=True)`, which alphabetizes keys, so `original` (source-order,
    Python) and `scaled` (alphabetical, JSON-round-tripped) can disagree on which leaf comes
    first even though they describe the same structure. String/bool leaves must be identical,
    never scaled."""
    if isinstance(original, bool):
        assert scaled is original, context
    elif isinstance(original, int | float):
        assert scaled == pytest.approx(original * scale), context
    elif isinstance(original, str):
        assert scaled == original, context
    elif isinstance(original, dict):
        assert isinstance(scaled, dict), context
        assert set(scaled) == set(original), context
        for key, value in original.items():
            _assert_every_leaf_scaled(
                value,
                scaled[key],
                scale,
                (*context, key) if isinstance(context, tuple) else context,
            )
    else:
        raise TypeError(f"unsupported configured_effect leaf type: {original!r}")


# --- HANDOFF-053: every declared trap must be empirically live, and silent when inactive --------
#
# A `confounded_by` list that looks plausible on paper is not evidence it is actually wired —
# domain 1's own traps shipped with exactly this gap (ET02 misattributed to the wrong warehouse,
# ET04/ET05 not wired to their declared variables at all, and *no* trap was actually gated by
# `active_traps` in the first place, so the "0 traps" variant wasn't really trap-free). These two
# tests turn that one-time manual audit into a structural guarantee every future domain inherits
# automatically: compute the real raw marginal effect directly from generated data, never trust
# the declared metadata.

#: |z| beyond this on the `all_traps` sample means the trap is unambiguously live; below this on
#: the `noise` sample means indistinguishable from sampling noise. Verified against ecommerce's 5
#: traps at n=10,000: active traps range 2.56-12.49, inactive/noise traps range 0.25-1.07 — wide
#: separation on both sides of this bar.
LIVE_TRAP_Z_THRESHOLD = 2.0
_TRAP_CHECK_ROW_COUNT = 10_000


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_declared_traps_produce_a_live_raw_marginal_effect(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = DomainRunConfig(
        seed=20260818,
        row_count=_TRAP_CHECK_ROW_COUNT,
        active_patterns=frozenset(),  # patterns off: isolates confounding from pattern signal
        active_traps=frozenset(t.id for t in spec.traps),
    )
    run_domain_benchmark(spec, config, tmp_path)
    rows = _read_csv(tmp_path / "reference" / f"{domain_id}_clean.csv")
    for trap in spec.traps:
        effect = raw_marginal_effect(
            [dict(row) for row in rows], trap.apparent_feature, spec.primary_outcome_column
        )
        assert abs(effect.z_score) > LIVE_TRAP_Z_THRESHOLD, (
            domain_id,
            trap.id,
            trap.apparent_feature,
            effect,
        )


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_noise_variant_produces_no_trap_signal(
    domain_id: str, spec: DomainSpec, tmp_path: Path
) -> None:
    config = DomainRunConfig(
        seed=20260818,
        row_count=_TRAP_CHECK_ROW_COUNT,
        active_patterns=frozenset(),
        active_traps=frozenset(),  # every mechanism must be gated off, not just undocumented
    )
    run_domain_benchmark(spec, config, tmp_path)
    rows = _read_csv(tmp_path / "reference" / f"{domain_id}_clean.csv")
    for trap in spec.traps:
        effect = raw_marginal_effect(
            [dict(row) for row in rows], trap.apparent_feature, spec.primary_outcome_column
        )
        assert abs(effect.z_score) < LIVE_TRAP_Z_THRESHOLD, (
            domain_id,
            trap.id,
            trap.apparent_feature,
            effect,
        )


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_trap_apparent_features_use_the_column_equals_value_shape(
    domain_id: str, spec: DomainSpec
) -> None:
    """`raw_marginal_effect`'s parser requires this exact shape from every domain, forever."""
    for trap in spec.traps:
        assert "=" in trap.apparent_feature, (domain_id, trap.id)
        column, _, _value = trap.apparent_feature.partition("=")
        assert column.strip() in spec.feature_timing, (domain_id, trap.id, column)


# --- validation guards -----------------------------------------------------------------------


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_unknown_pattern_id_is_rejected(domain_id: str, spec: DomainSpec, tmp_path: Path) -> None:
    config = DomainRunConfig(seed=1, row_count=200, active_patterns=frozenset(["NOT_A_PATTERN"]))
    with pytest.raises(ValueError, match="unknown active_patterns"):
        run_domain_benchmark(spec, config, tmp_path)


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_unknown_trap_id_is_rejected(domain_id: str, spec: DomainSpec, tmp_path: Path) -> None:
    config = DomainRunConfig(
        seed=1, row_count=200, active_patterns=frozenset(), active_traps=frozenset(["NOT_A_TRAP"])
    )
    with pytest.raises(ValueError, match="unknown active_traps"):
        run_domain_benchmark(spec, config, tmp_path)


@pytest.mark.parametrize("domain_id,spec", DOMAINS, ids=DOMAIN_IDS)
def test_too_few_rows_is_rejected(domain_id: str, spec: DomainSpec, tmp_path: Path) -> None:
    config = DomainRunConfig(seed=1, row_count=50, active_patterns=frozenset())
    with pytest.raises(ValueError, match="at least 180 rows"):
        run_domain_benchmark(spec, config, tmp_path)
