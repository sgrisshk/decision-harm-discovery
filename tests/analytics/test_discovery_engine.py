import math

import polars as pl
import pytest
from policy_analytics.discovery.engine import (
    Condition,
    DiscoveryConfig,
    SplitMetric,
    _development_score,
    _greedy_diverse_select,
    discover_candidates,
)
from policy_analytics.outcomes import primary_outcome

pytestmark = pytest.mark.analytics


def _metric(n_exposed: int, harm_per_booking: float) -> SplitMetric:
    return SplitMetric(
        split="development",
        n_population=10_000,
        n_exposed=n_exposed,
        support=n_exposed / 10_000,
        exposed_mean=0.0,
        comparison_mean=0.0,
        raw_difference=0.0,
        harm_per_booking=harm_per_booking,
        historical_exposure=harm_per_booking * n_exposed,
    )


def test_discovers_interaction_and_records_full_search_family() -> None:
    rows = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(400):
            supplier = "A" if index % 2 == 0 else "B"
            discount = (index % 10) / 100
            harm = 80.0 if supplier == "A" and discount >= 0.05 else 0.0
            rows.append((supplier, discount, index % 3, 200.0 - harm, split))
    frame = pl.DataFrame(
        rows,
        schema=[
            "supplier",
            "discount_rate",
            "party_size",
            "contribution_margin_eur",
            "split_label",
        ],
        orient="row",
    )
    result = discover_candidates(
        frame,
        ("supplier", "discount_rate", "party_size"),
        primary_outcome(),
        DiscoveryConfig(min_n=20, beam_width=30, top_k=5),
    )
    assert result["search"]["evaluated_hypotheses"] > result["candidate_count"]
    assert all(len(candidate["conditions"]) >= 2 for candidate in result["candidates"])
    assert any(
        {condition["feature"] for condition in candidate["conditions"]}
        >= {"supplier", "discount_rate"}
        for candidate in result["candidates"]
    )
    assert all(candidate["fit_split"] == "development" for candidate in result["candidates"])


def test_rejects_missing_primary_outcome() -> None:
    frame = pl.DataFrame(
        {
            "supplier": ["A", "B"],
            "contribution_margin_eur": [1.0, None],
            "split_label": ["development", "development"],
        }
    )
    with pytest.raises(ValueError, match="contains missing"):
        discover_candidates(frame, ("supplier",), primary_outcome())


# --- TASK-058 (HANDOFF-043 remediation part 2): precision term on the beam-survival score ---


def test_population_score_exponent_of_one_reproduces_old_pure_exposure_ranking() -> None:
    """`population_score_exponent=1.0` must exactly reproduce `discovery-engine-v0.1.0`'s ranking:
    linear in `n_exposed`, i.e. identical to sorting by `historical_exposure` alone."""
    broad = _metric(n_exposed=2000, harm_per_booking=50.0)
    narrow = _metric(n_exposed=100, harm_per_booking=700.0)
    config = DiscoveryConfig(population_score_exponent=1.0)
    broad_score = _development_score(broad, condition_count=2, config=config)
    narrow_score = _development_score(narrow, condition_count=2, config=config)
    assert broad_score == pytest.approx(broad.historical_exposure / 1.15)
    assert narrow_score == pytest.approx(narrow.historical_exposure / 1.15)
    assert broad_score > narrow_score  # broad wins on raw total exposure alone (100,000 > 70,000)


def test_default_population_score_exponent_prefers_the_purer_rule_at_comparable_exposure() -> None:
    """The exact mechanism HANDOFF-043 diagnosed: a broad, diluted rule (large N, modest
    per-booking harm) outscores a narrow, purer rule (small N, strong per-booking harm) under
    linear population scaling even when the narrow rule's total exposure is smaller — but the
    default `population_score_exponent=0.5` must flip that preference once the narrow rule's
    per-booking effect is proportionally large enough, without ever opening real benchmark data."""
    broad = _metric(n_exposed=2000, harm_per_booking=50.0)  # historical_exposure = 100,000
    narrow = _metric(n_exposed=100, harm_per_booking=700.0)  # historical_exposure = 70,000
    config = DiscoveryConfig()  # default population_score_exponent = 0.5
    assert config.population_score_exponent == pytest.approx(0.5)
    broad_score = _development_score(broad, condition_count=2, config=config)
    narrow_score = _development_score(narrow, condition_count=2, config=config)
    # sqrt-scaled: broad = 50*sqrt(2000)/1.15, narrow = 700*sqrt(100)/1.15
    assert broad_score == pytest.approx(50.0 * math.sqrt(2000) / 1.15)
    assert narrow_score == pytest.approx(700.0 * math.sqrt(100) / 1.15)
    assert narrow_score > broad_score  # preference reversed relative to the exponent=1.0 case


def test_population_score_exponent_must_be_in_zero_to_one_range() -> None:
    for bad_exponent in (0.0, -0.5, 1.5):
        with pytest.raises(ValueError, match="population_score_exponent"):
            DiscoveryConfig(population_score_exponent=bad_exponent)
    DiscoveryConfig(population_score_exponent=1.0)  # upper bound is inclusive, does not raise


def test_discover_candidates_with_exponent_one_matches_manual_pure_exposure_reproduction() -> None:
    """End-to-end sanity check: run the full search twice on the same tiny fixture, once at the
    old linear exponent and once at the new default, and confirm both still return valid,
    development-only-fit candidates (the precision term changes ranking, not eligibility)."""
    rows = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(400):
            supplier = "A" if index % 2 == 0 else "B"
            discount = (index % 10) / 100
            harm = 80.0 if supplier == "A" and discount >= 0.05 else 0.0
            rows.append((supplier, discount, index % 3, 200.0 - harm, split))
    frame = pl.DataFrame(
        rows,
        schema=[
            "supplier",
            "discount_rate",
            "party_size",
            "contribution_margin_eur",
            "split_label",
        ],
        orient="row",
    )
    for exponent in (1.0, 0.5):
        result = discover_candidates(
            frame,
            ("supplier", "discount_rate", "party_size"),
            primary_outcome(),
            DiscoveryConfig(min_n=20, beam_width=30, top_k=5, population_score_exponent=exponent),
        )
        assert result["candidate_count"] > 0
        assert all(candidate["fit_split"] == "development" for candidate in result["candidates"])
        assert result["methodology_version"] == "discovery-engine-v0.3.1"


# --- TASK-060: greedy marginal-gain diversity in top-K selection ---


def _rule(feature: str, value: object) -> tuple[Condition, ...]:
    return (Condition(feature, "eq", value),)


def _run_select(
    pool: list[tuple[Condition, ...]],
    scored: dict[tuple[Condition, ...], tuple[float, SplitMetric]],
    exposures: dict[tuple[Condition, ...], frozenset[int]],
    config: DiscoveryConfig,
) -> list[tuple[Condition, ...]]:
    selected: list[tuple[Condition, ...]] = []
    _greedy_diverse_select(
        pool,
        scored,
        exposures,
        config,
        selected,
        [],
        {},
        dict.fromkeys(pool, 0.0),
    )
    return selected


def _dominant_and_distinct_fixture() -> tuple[
    dict[tuple[Condition, ...], tuple[float, SplitMetric]],
    dict[tuple[Condition, ...], frozenset[int]],
]:
    # D1/D2: same underlying mechanism at two thresholds, 80% pairwise Jaccard (below the 0.85
    # hard cap, so the old score-only selection happily keeps both). W: a smaller but genuinely
    # distinct, disjoint pattern with a lower raw score than either duplicate.
    d1, d2, w = _rule("price", "ge_1"), _rule("price", "ge_2"), _rule("segment", "Y")
    scored = {
        d1: (100.0, _metric(80, 10.0)),
        d2: (95.0, _metric(64, 10.0)),
        w: (50.0, _metric(60, 10.0)),
    }
    exposures = {
        d1: frozenset(range(0, 80)),
        d2: frozenset(range(0, 64)),  # |D1 n D2| = 64, |D1 u D2| = 80 -> jaccard = 0.8
        w: frozenset(range(500, 560)),  # disjoint from D1/D2
    }
    return scored, exposures


def test_diversity_weight_one_prefers_distinct_pattern_over_a_near_duplicate() -> None:
    """Full-strength diversity (v0.3.0's original default) still has this correct property in
    isolation — the TASK-060 iteration lowered the default, it did not invalidate the mechanism."""
    scored, exposures = _dominant_and_distinct_fixture()
    pool = list(scored)
    config = DiscoveryConfig(
        top_k=2, diversity_discount_weight=1.0, min_diversity_relevance_ratio=0.0
    )
    selected = _run_select(pool, scored, exposures, config)
    assert selected == [_rule("price", "ge_1"), _rule("segment", "Y")]


def test_diversity_weight_zero_reproduces_pure_score_and_hard_cap_selection() -> None:
    scored, exposures = _dominant_and_distinct_fixture()
    pool = list(scored)
    config = DiscoveryConfig(
        top_k=2, diversity_discount_weight=0.0, min_diversity_relevance_ratio=0.0
    )
    selected = _run_select(pool, scored, exposures, config)
    assert selected == [_rule("price", "ge_1"), _rule("price", "ge_2")]


def test_max_candidate_jaccard_hard_cap_applies_regardless_of_diversity_weight() -> None:
    d1, d2, w = _rule("price", "ge_1"), _rule("price", "ge_2"), _rule("segment", "Y")
    scored = {
        d1: (100.0, _metric(80, 10.0)),
        d2: (95.0, _metric(72, 10.0)),
        w: (50.0, _metric(60, 10.0)),
    }
    exposures = {
        d1: frozenset(range(0, 80)),
        d2: frozenset(range(0, 72)),  # |D1 n D2| = 72, |D1 u D2| = 80 -> jaccard = 0.9 > 0.85
        w: frozenset(range(500, 560)),
    }
    pool = list(scored)
    for weight in (0.0, 1.0):
        config = DiscoveryConfig(
            top_k=2, diversity_discount_weight=weight, min_diversity_relevance_ratio=0.0
        )
        selected = _run_select(pool, scored, exposures, config)
        assert d2 not in selected  # over the hard ceiling either way, never merely deprioritized
        assert selected == [d1, w]


def test_diversity_discount_weight_must_be_in_zero_to_one_range() -> None:
    for bad_weight in (-0.1, 1.1):
        with pytest.raises(ValueError, match="diversity_discount_weight"):
            DiscoveryConfig(diversity_discount_weight=bad_weight)
    DiscoveryConfig(diversity_discount_weight=0.0)  # bounds inclusive, neither raises
    DiscoveryConfig(diversity_discount_weight=1.0)


# --- TASK-060 iteration (2026-08-20): relevance floor, less aggressive default weight ---
#
# A live TASK-019/TASK-028 run against task-060-remediation-20260818-001 found the original
# full-strength mechanism let a statistically thin, low-overlap-only candidate into the top-K
# (Top-10 precision 90%->40%, a confounding trap reached PASS — ADR-036, HANDOFF-052). These tests
# use only generic fixtures (a "strong distinct pattern" and a "weak disjoint noise" rule), never
# referencing that trap's specific features, matching the ADR's own discipline of not tuning to a
# result seen after opening hidden_ground_truth.json.


def test_default_config_still_prefers_a_strong_distinct_pattern() -> None:
    d1, d2, w_strong = _rule("price", "ge_1"), _rule("price", "ge_2"), _rule("segment", "Y")
    scored = {
        d1: (100.0, _metric(80, 10.0)),
        d2: (95.0, _metric(64, 10.0)),  # jaccard vs d1 = 0.8
        w_strong: (90.0, _metric(60, 10.0)),  # distinct, disjoint, and nearly as strong as d1
    }
    exposures = {
        d1: frozenset(range(0, 80)),
        d2: frozenset(range(0, 64)),
        w_strong: frozenset(range(500, 560)),
    }
    selected = _run_select(list(scored), scored, exposures, DiscoveryConfig(top_k=2))
    assert selected == [d1, w_strong]


def test_default_config_relevance_floor_blocks_weak_disjoint_noise() -> None:
    d1, d2, weak_noise = _rule("price", "ge_1"), _rule("price", "ge_2"), _rule("segment", "Y")
    scored = {
        d1: (100.0, _metric(80, 10.0)),
        d2: (95.0, _metric(64, 10.0)),  # jaccard vs d1 = 0.8
        weak_noise: (20.0, _metric(60, 10.0)),  # disjoint, but far too weak on its own merits
    }
    exposures = {
        d1: frozenset(range(0, 80)),
        d2: frozenset(range(0, 64)),
        weak_noise: frozenset(range(500, 560)),
    }
    pool = list(scored)

    # Default (weight=0.5, floor=0.5): the floor excludes weak_noise (20 < 0.5*100) before
    # selection even starts, so the near-duplicate D2 is kept over the noise.
    selected_default = _run_select(pool, scored, exposures, DiscoveryConfig(top_k=2))
    assert weak_noise not in selected_default
    assert selected_default == [d1, d2]

    # Contrast with the original v0.3.0 full-strength, no-floor configuration: weak_noise's zero
    # overlap lets it outrank d2's discounted score (19 < 20) purely for being untouched — exactly
    # the failure mode the live evaluation caught.
    original_config = DiscoveryConfig(
        top_k=2, diversity_discount_weight=1.0, min_diversity_relevance_ratio=0.0
    )
    selected_original = _run_select(pool, scored, exposures, original_config)
    assert selected_original == [d1, weak_noise]


def test_min_diversity_relevance_ratio_must_be_in_zero_to_one_range() -> None:
    for bad_ratio in (-0.1, 1.1):
        with pytest.raises(ValueError, match="min_diversity_relevance_ratio"):
            DiscoveryConfig(min_diversity_relevance_ratio=bad_ratio)
    DiscoveryConfig(min_diversity_relevance_ratio=0.0)  # bounds inclusive, neither raises
    DiscoveryConfig(min_diversity_relevance_ratio=1.0)


def test_discover_candidates_still_prefers_interactions_with_default_diversity() -> None:
    """End-to-end: the pre-TASK-060 "interactions fill the top-K before any singleton"
    discipline must survive the two-phase greedy-diverse rewrite."""
    rows = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(400):
            supplier = "A" if index % 2 == 0 else "B"
            discount = (index % 10) / 100
            harm = 80.0 if supplier == "A" and discount >= 0.05 else 0.0
            rows.append((supplier, discount, index % 3, 200.0 - harm, split))
    frame = pl.DataFrame(
        rows,
        schema=[
            "supplier",
            "discount_rate",
            "party_size",
            "contribution_margin_eur",
            "split_label",
        ],
        orient="row",
    )
    result = discover_candidates(
        frame,
        ("supplier", "discount_rate", "party_size"),
        primary_outcome(),
        DiscoveryConfig(min_n=20, beam_width=30, top_k=5),
    )
    assert result["candidate_count"] > 0
    assert all(len(candidate["conditions"]) >= 2 for candidate in result["candidates"])
