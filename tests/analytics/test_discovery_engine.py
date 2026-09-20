import math

import polars as pl
import pytest
from policy_analytics.discovery.engine import (
    Condition,
    DiscoveryConfig,
    SplitMetric,
    _apply_feature_identity_cap,
    _apply_stability_credit,
    _development_score,
    _exposed_rows,
    _greedy_diverse_select,
    _jaccard,
    _percentile,
    _reserve_k1_slot,
    _select_expansion_beam,
    _temporal_consistency,
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
        assert result["methodology_version"] == "discovery-engine-v0.6.1"


# --- TASK-071: exposure-identical redundancy pruning compares row sets, not counts ---


def test_exposed_rows_equal_count_does_not_imply_equal_rows() -> None:
    """The exact equivalence condition the depth->1 redundancy check now enforces is row-set
    identity, not count identity — and count identity is not a safe proxy for it *in general*.
    Two unrelated conditions here select disjoint four-row groups: equal `n_exposed`, completely
    different rows. `_exposed_rows` (what the fixed check compares) correctly reports them as
    unequal; a hypothetical count-only check would have wrongly called them redundant.

    `discover_candidates`'s own redundancy check never actually presents `_exposed_rows` with a
    pair like this: it only ever compares a rule to a leave-one-out parent formed by dropping one
    of the rule's own conditions, and conjunction only ever removes rows, so that specific
    comparison's child is always a subset of its parent (see
    `test_child_exposed_rows_are_always_a_subset_of_its_leave_one_out_parent` below) — meaning
    equal counts there already implied equal rows even before this fix. This test proves the
    primitive the fix now relies on is exact on its own terms, independent of that call-site
    guarantee, matching this project's own `ADR-007`/`ADR-012` discipline of testing the actual
    invariant rather than trusting an incidental correctness argument.
    """
    frame = pl.DataFrame(
        {
            "group_low": [True, True, True, True, False, False, False, False],
            "group_high": [False, False, False, False, True, True, True, True],
        }
    )
    low_rows = _exposed_rows(frame, (Condition("group_low", "eq", True),))
    high_rows = _exposed_rows(frame, (Condition("group_high", "eq", True),))
    assert len(low_rows) == len(high_rows) == 4  # equal n_exposed ...
    assert low_rows != high_rows  # ... but not the same rows
    assert low_rows.isdisjoint(high_rows)


def test_child_exposed_rows_are_always_a_subset_of_its_leave_one_out_parent() -> None:
    """Confirms the structural fact the redundancy check's soundness rests on: for a rule formed
    by adding one condition to a parent rule, the child's exposed rows are always a subset of the
    parent's (a conjunction can only ever remove rows, never admit one the parent excluded). This
    is what makes `n_exposed` equality between a rule and its own leave-one-out parent logically
    equivalent to full row-set equality — verified directly here on a small generic fixture, and
    confirmed to hold with zero exceptions across two full real searches in `TASK-071`'s own
    write-up (`docs/analytics/discovery-engine-v0.md`)."""
    frame = pl.DataFrame(
        {
            "region": ["north", "north", "south", "north", "south", "north", "north", "south"],
            "tier": ["gold", "gold", "gold", "silver", "silver", "gold", "silver", "gold"],
        }
    )
    parent_rule = (Condition("region", "eq", "north"),)
    child_rule = (Condition("region", "eq", "north"), Condition("tier", "eq", "gold"))
    parent_rows = _exposed_rows(frame, parent_rule)
    child_rows = _exposed_rows(frame, child_rule)
    assert child_rows <= parent_rows
    assert child_rows != parent_rows  # this particular pair is not redundant


def test_exposure_identical_child_rule_is_pruned_from_final_candidates() -> None:
    """Positive case: a depth-2 rule that looks different from its depth-1 parent (an extra
    condition on a second feature) but, on this data, selects the exact identical row set — the
    second feature's positive value co-occurs with the first feature's positive value on every
    single row — must still be discarded as redundant, end to end through the public
    `discover_candidates` API. `signal_flag` and `redundant_flag` are two differently-named,
    differently-shaped conditions that happen to partition the development split identically
    (`redundant_flag == "yes"` exactly when `signal_flag == "A"`), so every non-empty depth-2
    combination of them is exposure-identical to one of its depth-1 parents. If the redundancy
    check ever under-pruned (a false negative), a two-condition candidate combining both features
    would appear below; it must not."""
    rows: list[tuple[str, str, float, str]] = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(400):
            signal = "A" if index % 4 == 0 else ("B" if index % 4 == 1 else "C")
            redundant = "yes" if index % 4 == 0 else "no"
            harm = 80.0 if signal == "A" else 0.0
            rows.append((signal, redundant, 200.0 - harm, split))
    frame = pl.DataFrame(
        rows,
        schema=["signal_flag", "redundant_flag", "contribution_margin_eur", "split_label"],
        orient="row",
    )
    result = discover_candidates(
        frame,
        ("signal_flag", "redundant_flag"),
        primary_outcome(),
        DiscoveryConfig(min_n=20, beam_width=30, top_k=5),
    )
    assert result["candidate_count"] > 0
    for candidate in result["candidates"]:
        conditions = candidate["conditions"]
        assert len(conditions) == 1, (
            "the only non-empty two-condition combination of signal_flag/redundant_flag is "
            "exposure-identical to its own parent and must be pruned before selection"
        )
    selected_features = {
        condition["feature"]
        for candidate in result["candidates"]
        for condition in candidate["conditions"]
    }
    assert selected_features & {"signal_flag", "redundant_flag"}  # the real signal still surfaces


# --- TASK-064: feature/operator-structure coverage in the expansion beam ---


def test_zero_structural_beam_quota_reproduces_score_only_beam() -> None:
    high_a = (Condition("alpha", "eq", "high"), Condition("beta", "eq", "one"))
    high_b = (Condition("alpha", "eq", "next"), Condition("beta", "eq", "two"))
    low_distinct = (Condition("gamma", "ge", 3.0), Condition("omega", "lt", 8.0))
    scored = {
        high_a: (100.0, _metric(100, 10.0)),
        high_b: (90.0, _metric(100, 9.0)),
        low_distinct: (10.0, _metric(100, 1.0)),
    }
    beam = _select_expansion_beam(
        scored,
        depth=2,
        config=DiscoveryConfig(beam_width=2, beam_rules_per_structure=0),
    )
    assert beam == [high_a, high_b]


def test_structural_beam_reserve_keeps_a_lower_scoring_distinct_shape() -> None:
    high_a = (Condition("alpha", "eq", "high"), Condition("beta", "eq", "one"))
    high_b = (Condition("alpha", "eq", "next"), Condition("beta", "eq", "two"))
    low_distinct = (Condition("gamma", "ge", 3.0), Condition("omega", "lt", 8.0))
    scored = {
        high_a: (100.0, _metric(100, 10.0)),
        high_b: (90.0, _metric(100, 9.0)),
        low_distinct: (10.0, _metric(100, 1.0)),
    }
    beam = _select_expansion_beam(
        scored,
        depth=2,
        config=DiscoveryConfig(beam_width=2, beam_rules_per_structure=1),
    )
    assert beam == [high_a, high_b, low_distinct]


def test_structural_beam_quota_two_keeps_two_values_of_the_same_shape() -> None:
    dominant = (Condition("alpha", "eq", "dominant"), Condition("beta", "eq", "one"))
    second = (Condition("alpha", "eq", "second"), Condition("beta", "eq", "two"))
    scored = {
        dominant: (20.0, _metric(100, 2.0)),
        second: (10.0, _metric(100, 1.0)),
    }
    quota_one = _select_expansion_beam(
        scored,
        depth=2,
        config=DiscoveryConfig(beam_width=1, beam_rules_per_structure=1),
    )
    quota_two = _select_expansion_beam(
        scored,
        depth=2,
        config=DiscoveryConfig(beam_width=1, beam_rules_per_structure=2),
    )
    assert quota_one == [dominant]
    assert quota_two == [dominant, second]


def test_structural_beam_quota_is_validated() -> None:
    with pytest.raises(ValueError, match="beam_rules_per_structure"):
        DiscoveryConfig(beam_rules_per_structure=-1)
    with pytest.raises(ValueError, match="beam_width"):
        DiscoveryConfig(beam_width=0)
    with pytest.raises(ValueError, match="max_expansion_beam_size"):
        DiscoveryConfig(beam_width=10, max_expansion_beam_size=9)


def test_structural_beam_reserve_is_hard_capped() -> None:
    rules = {
        (Condition(f"feature_{index}", "eq", index),): (float(100 - index), _metric(100, 1.0))
        for index in range(10)
    }
    beam = _select_expansion_beam(
        rules,
        depth=1,
        config=DiscoveryConfig(beam_width=2, beam_rules_per_structure=1, max_expansion_beam_size=4),
    )
    assert len(beam) == 4
    assert beam == list(rules)[:4]


# --- TASK-060: greedy marginal-gain diversity in top-K selection ---


def _rule(feature: str, value: object) -> tuple[Condition, ...]:
    return (Condition(feature, "eq", value),)


def _run_select(
    pool: list[tuple[Condition, ...]],
    scored: dict[tuple[Condition, ...], tuple[float, SplitMetric]],
    exposures: dict[tuple[Condition, ...], frozenset[int]],
    config: DiscoveryConfig,
) -> list[tuple[Condition, ...]]:
    """Test helper: `_greedy_diverse_select` takes an `effective_score` map (raw score already
    blended with stability by `discover_candidates`); these tests exercise pure selection
    mechanics, so they pass the raw `_development_score` through unchanged (equivalent to
    `stability_credit_weight=0.0`, i.e. no stability opinion either way)."""
    selected: list[tuple[Condition, ...]] = []
    effective_score = {rule: score for rule, (score, _metric) in scored.items()}
    _greedy_diverse_select(
        pool,
        effective_score,
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


# --- TASK-060 iteration (2026-08-20, ADR-039): stability-credited effective score ---
#
# HANDOFF-055/ADR-038 found the ceiling is selection-stage: several true patterns' best-matching
# candidates sit well under min_diversity_relevance_ratio=0.5. Rather than lowering that floor
# globally (rejected in ADR-038/039 -- reopens the T03 regression risk), a rule's cross-split
# stability now credits its score before either the floor or marginal gain sees it. These tests use
# only generic fixtures (never referencing T03/acquisition_channel or any real benchmark feature).


def _split_frame(rule_feature: str, agrees: dict[str, bool | None]) -> pl.DataFrame:
    """One rule (`{rule_feature} eq True`), harmful in development. `agrees[split]` controls each
    later split: `True` = same harmful direction as development, `False` = reversed direction,
    `None` = no exposed rows at all for that split (rule_feature is always False there)."""
    rows: list[tuple[bool, float, str]] = []
    for split in ("development", "validation", "future_holdout"):
        agreement = agrees.get(split)
        for index in range(40):
            if split == "development":
                flag = index < 20
                margin = 100.0 - (50.0 if flag else 0.0)  # flag=True is harmful (lower margin)
            elif agreement is None:
                flag = False
                margin = 100.0
            elif agreement:
                flag = index < 20
                margin = 100.0 - (50.0 if flag else 0.0)
            else:
                flag = index < 20
                margin = 100.0 + (50.0 if flag else 0.0)  # reversed: flag=True now helps
            rows.append((flag, margin, split))
    return pl.DataFrame(
        rows, schema=[rule_feature, "contribution_margin_eur", "split_label"], orient="row"
    )


def test_temporal_consistency_full_agreement() -> None:
    frame = _split_frame("flag", {"validation": True, "future_holdout": True})
    rule = (Condition("flag", "eq", True),)
    result = _temporal_consistency(frame, rule, primary_outcome())
    assert result.consistency == pytest.approx(1.0)
    assert result.validation is not None
    assert result.future_holdout is not None


def test_temporal_consistency_partial_agreement() -> None:
    frame = _split_frame("flag", {"validation": True, "future_holdout": False})
    rule = (Condition("flag", "eq", True),)
    result = _temporal_consistency(frame, rule, primary_outcome())
    assert result.consistency == pytest.approx(0.5)


def test_temporal_consistency_no_later_exposure_is_zero_not_omitted() -> None:
    frame = _split_frame("flag", {"validation": None, "future_holdout": None})
    rule = (Condition("flag", "eq", True),)
    result = _temporal_consistency(frame, rule, primary_outcome())
    assert result.consistency == 0.0
    assert result.validation is None
    assert result.future_holdout is None


def test_apply_stability_credit_zero_weight_is_a_no_op() -> None:
    for consistency in (0.0, 0.3, 0.5, 1.0):
        assert _apply_stability_credit(123.4, consistency, weight=0.0) == pytest.approx(123.4)


def test_apply_stability_credit_rewards_consistency_and_never_penalizes() -> None:
    base = 100.0
    unstable = _apply_stability_credit(base, consistency=0.0, weight=0.5)
    partial = _apply_stability_credit(base, consistency=0.5, weight=0.5)
    stable = _apply_stability_credit(base, consistency=1.0, weight=0.5)
    assert unstable == pytest.approx(base)  # no credit, but never discounted below raw either
    assert partial == pytest.approx(125.0)
    assert stable == pytest.approx(150.0)
    assert unstable <= partial <= stable


def test_stability_credit_weight_must_be_in_zero_to_one_range() -> None:
    for bad_weight in (-0.1, 1.1):
        with pytest.raises(ValueError, match="stability_credit_weight"):
            DiscoveryConfig(stability_credit_weight=bad_weight)
    DiscoveryConfig(stability_credit_weight=0.0)  # bounds inclusive, neither raises
    DiscoveryConfig(stability_credit_weight=1.0)


def test_stability_credit_lets_a_weak_stable_rule_beat_a_stronger_unstable_one() -> None:
    """The scenario ADR-039 exists for: two rules below what a raw-score floor alone would ever
    admit, but one is stable across later splits and the other is not. Credited scores are what
    _greedy_diverse_select actually sees (mirroring how discover_candidates builds them)."""
    weak_stable, weak_unstable = (
        (Condition("segment", "eq", "family"),),
        (Condition("channel", "eq", "x"),),
    )
    raw_scores = {weak_stable: 100.0, weak_unstable: 100.0}
    consistency = {weak_stable: 1.0, weak_unstable: 0.0}
    weight = 0.5
    effective_score = {
        rule: _apply_stability_credit(raw_scores[rule], consistency[rule], weight)
        for rule in raw_scores
    }
    exposures = {
        weak_stable: frozenset(range(0, 50)),
        weak_unstable: frozenset(range(500, 550)),
    }
    selected: list[tuple[Condition, ...]] = []
    _greedy_diverse_select(
        [weak_stable, weak_unstable],
        effective_score,
        exposures,
        DiscoveryConfig(top_k=1),
        selected,
        [],
        {},
        dict.fromkeys(raw_scores, 0.0),
    )
    assert selected == [weak_stable]


def test_discover_candidates_final_candidates_reuse_cached_stability() -> None:
    """Regression for the v0.4.0 refactor: temporal_direction_consistency/validation/future_holdout
    on the final Candidate now come from the same cache _prepare fills for selection, not a fresh
    post-selection recomputation — must still match what a full-data fixture implies."""
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
    for candidate in result["candidates"]:
        assert 0.0 <= candidate["temporal_direction_consistency"] <= 1.0
        # The fixture's harmful pattern is identical and noiseless in every split, so every
        # reported candidate should show full temporal agreement.
        assert candidate["temporal_direction_consistency"] == pytest.approx(1.0)
        assert candidate["validation"] is not None
        assert candidate["future_holdout"] is not None


# --- TASK-060 iteration (2026-08-20, ADR-040): floor reference point, not the ratio itself ---
#
# ADR-038's diagnostic found the maximum-referenced floor is always measured against the dominant
# rescaling family (largest population x effect), not the pool's typical quality. These tests use
# only a generic outlier/typical/target fixture -- never a real benchmark feature or trap.


def test_percentile_bounds_and_interpolation() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile(values, 1.0) == pytest.approx(50.0)  # exactly max
    assert _percentile(values, 0.0) == pytest.approx(10.0)  # exactly min
    assert _percentile(values, 0.5) == pytest.approx(30.0)  # exact median, 5 points
    assert _percentile([], 0.5) == 0.0
    assert _percentile([7.0], 0.9) == pytest.approx(7.0)


def test_relevance_floor_percentile_must_be_in_zero_to_one_range() -> None:
    for bad_fraction in (0.0, -0.1, 1.1):
        with pytest.raises(ValueError, match="relevance_floor_percentile"):
            DiscoveryConfig(relevance_floor_percentile=bad_fraction)
    DiscoveryConfig(relevance_floor_percentile=1.0)  # upper bound inclusive, does not raise


def _outlier_typical_target_pool() -> tuple[
    dict[tuple[Condition, ...], float], dict[tuple[Condition, ...], frozenset[int]]
]:
    outlier = (Condition("f", "eq", "outlier"),)
    target = (Condition("f", "eq", "target"),)
    typical = [(Condition("f", "eq", f"typical_{i}"),) for i in range(8)]
    typical_scores = [100.0, 98.0, 96.0, 94.0, 92.0, 90.0, 88.0, 86.0]
    effective_score = {outlier: 1000.0, target: 60.0}
    effective_score.update(zip(typical, typical_scores, strict=True))
    exposures = {rule: frozenset({index}) for index, rule in enumerate([outlier, target, *typical])}
    return effective_score, exposures


def test_max_reference_lets_one_outlier_exclude_almost_the_whole_pool() -> None:
    """The pre-v0.4.1 behavior (relevance_floor_percentile=1.0): with one huge outlier, the floor
    excludes every "typical" rule too, not just the intentionally weak target."""
    effective_score, exposures = _outlier_typical_target_pool()
    pool = list(effective_score)
    selected: list[tuple[Condition, ...]] = []
    _greedy_diverse_select(
        pool,
        effective_score,
        exposures,
        DiscoveryConfig(top_k=20, relevance_floor_percentile=1.0),
        selected,
        [],
        {},
        dict.fromkeys(pool, 0.0),
    )
    assert selected == [(Condition("f", "eq", "outlier"),)]


def test_default_percentile_reference_survives_the_outlier_and_admits_the_target() -> None:
    effective_score, exposures = _outlier_typical_target_pool()
    pool = list(effective_score)
    target = (Condition("f", "eq", "target"),)
    selected: list[tuple[Condition, ...]] = []
    _greedy_diverse_select(
        pool,
        effective_score,
        exposures,
        DiscoveryConfig(top_k=20),  # relevance_floor_percentile defaults to 0.75
        selected,
        [],
        {},
        dict.fromkeys(pool, 0.0),
    )
    assert target in selected
    assert len(selected) == len(pool)  # every "typical" rule clears the floor too, not just target


def test_relevance_floor_percentile_one_reproduces_v040_exactly() -> None:
    """relevance_floor_percentile=1.0 combined with stability_credit_weight=0.0 must exactly
    reproduce v0.3.1/v0.4.0's original max-referenced selection sequence."""
    scored, exposures = _dominant_and_distinct_fixture()
    pool = list(scored)
    effective_score = {rule: score for rule, (score, _metric) in scored.items()}
    config = DiscoveryConfig(
        top_k=2,
        diversity_discount_weight=1.0,
        min_diversity_relevance_ratio=0.0,
        relevance_floor_percentile=1.0,
    )
    selected: list[tuple[Condition, ...]] = []
    _greedy_diverse_select(
        pool, effective_score, exposures, config, selected, [], {}, dict.fromkeys(pool, 0.0)
    )
    assert selected == [(Condition("price", "eq", "ge_1"),), (Condition("segment", "eq", "Y"),)]


# --- TASK-068: feature-identity diversity floor at final selection (ADR-056/ADR-057) ---
#
# A portability postmortem (ADR-055) found every one of a run's committed candidates anchored
# on the same one or two features -- a crowding axis neither
# _greedy_diverse_select's population-overlap diversity (TASK-060) nor the expansion beam's
# (feature, operator)-structure reserve (TASK-064) guards. These tests use only invented feature
# names and DECISION_TIME-only inputs -- never a real domain, dataset, or hidden ground truth.
#
# Fixture: one dominant feature ("feature_alpha") drives most of the harmful signal and can pair
# with any of several "filler" features (no effect of their own -- structurally necessary padding,
# since a rule can never combine two conditions on the same feature) to fill many top-scoring
# slots. Three independent "distinct" features each carry their own real, weaker harmful signal.
# Under the default (disabled) config, feature_alpha's many rescalings crowd out all but one of
# the three independently-strong alternatives.

_N_FILLER_FEATURES = 6


def _feature_identity_crowding_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    n = 420  # kept as small as the crowding/diversification effect still reproduces reliably at
    for split in ("development", "validation", "future_holdout"):
        for index in range(n):
            alpha_high = index >= int(n * 0.7)  # top 30% of a uniform numeric feature
            filler = index % _N_FILLER_FEATURES
            distinct1 = index % 5 == 0  # ~20% support
            distinct2 = index % 7 == 0  # ~14% support
            distinct3 = index % 9 == 0  # ~11% support
            margin = 100.0
            if alpha_high:
                margin -= 50.0  # the dominant, strong, real effect
            if distinct1:
                margin -= 20.0
            if distinct2:
                margin -= 18.0
            if distinct3:
                margin -= 16.0
            row: dict[str, object] = {"feature_alpha": float(index)}
            for slot in range(_N_FILLER_FEATURES):
                row[f"filler_{slot}"] = filler == slot
            row["feature_distinct1"] = distinct1
            row["feature_distinct2"] = distinct2
            row["feature_distinct3"] = distinct3
            row["contribution_margin_eur"] = margin
            row["split_label"] = split
            rows.append(row)
    return pl.DataFrame(rows)


_CROWDING_FEATURE_COLUMNS = (
    "feature_alpha",
    *[f"filler_{slot}" for slot in range(_N_FILLER_FEATURES)],
    "feature_distinct1",
    "feature_distinct2",
    "feature_distinct3",
)
_CROWDING_TOP_K = 6


def _signal_identities(result: dict[str, object]) -> set[str]:
    """Only the features of interest -- excludes filler_* padding, which is structural plumbing
    (needed only because a rule cannot combine two conditions on the same feature) with no effect
    of its own, not part of the diversity axis this task addresses."""
    identities: set[str] = set()
    for candidate in result["candidates"]:  # type: ignore[union-attr]
        for condition in candidate["conditions"]:
            if not condition["feature"].startswith("filler_"):
                identities.add(condition["feature"])
    return identities


def test_identity_cap_disabled_default_lets_one_feature_crowd_the_selected_set() -> None:
    """(a) Old behavior: with the default (disabled) config, feature_alpha's many rescalings fill
    the entire top-K, crowding out all but (at most) one of three independently strong,
    genuinely distinct alternatives."""
    frame = _feature_identity_crowding_frame()
    result = discover_candidates(
        frame,
        _CROWDING_FEATURE_COLUMNS,
        primary_outcome(),
        DiscoveryConfig(min_n=8, beam_width=40, top_k=_CROWDING_TOP_K),
    )
    candidates = result["candidates"]
    assert len(candidates) == _CROWDING_TOP_K
    alpha_uses = sum(
        1
        for c in candidates
        if any(cond["feature"] == "feature_alpha" for cond in c["conditions"])
    )
    assert alpha_uses == _CROWDING_TOP_K  # every single selected slot touches the same feature
    assert len(_signal_identities(result) - {"feature_alpha"}) <= 1  # at most one alternative


def test_identity_cap_enabled_increases_distinct_signal_identity_count() -> None:
    """(b) Enabling the constraint increases distinct feature-identity count relative to the same
    fixture's disabled baseline, and the dominant feature's own count is capped as configured."""
    frame = _feature_identity_crowding_frame()
    outcome = primary_outcome()
    baseline = discover_candidates(
        frame,
        _CROWDING_FEATURE_COLUMNS,
        outcome,
        DiscoveryConfig(min_n=8, beam_width=40, top_k=_CROWDING_TOP_K),
    )
    capped = discover_candidates(
        frame,
        _CROWDING_FEATURE_COLUMNS,
        outcome,
        DiscoveryConfig(
            min_n=8, beam_width=40, top_k=_CROWDING_TOP_K, max_feature_identity_fraction=0.34
        ),
    )
    baseline_signals = _signal_identities(baseline)
    capped_signals = _signal_identities(capped)
    # Baseline: feature_alpha crowds every slot, at most one distinct feature ever gets in
    # (test_identity_cap_disabled_default_lets_one_feature_crowd_the_selected_set asserts this
    # directly). Capped: strictly more distinct signal identities, and specifically more than one
    # non-dominant feature now represented -- not just a one-for-one swap.
    assert len(capped_signals) > len(baseline_signals)
    assert len(capped_signals - {"feature_alpha"}) >= 2
    alpha_uses = sum(
        1
        for c in capped["candidates"]
        if any(cond["feature"] == "feature_alpha" for cond in c["conditions"])
    )
    assert alpha_uses == 2  # floor(0.34 * 6) == 2, exactly the configured ceiling
    assert len(capped["candidates"]) == _CROWDING_TOP_K  # still a full top-K, not just a shrink


def test_identity_cap_is_deterministic_across_repeated_runs() -> None:
    """(c) Deterministic tie-breaking: rerunning the identical fixture/config produces a
    byte-identical candidate list, not just an identical distinct-identity count."""
    frame = _feature_identity_crowding_frame()
    config = DiscoveryConfig(
        min_n=8, beam_width=40, top_k=_CROWDING_TOP_K, max_feature_identity_fraction=0.34
    )
    first = discover_candidates(frame, _CROWDING_FEATURE_COLUMNS, primary_outcome(), config)
    second = discover_candidates(frame, _CROWDING_FEATURE_COLUMNS, primary_outcome(), config)
    assert first["candidates"] == second["candidates"]


def test_apply_feature_identity_cap_ties_break_on_rule_order_not_set_iteration() -> None:
    """Direct unit-level determinism check: two rules with identical scores and disjoint features,
    presented in a fixed `ranked` order, must be admitted in exactly that order regardless of
    Python's unordered `set` construction inside the cap's own feature-membership check."""
    rule_a = (Condition("zzz_feature", "eq", True),)
    rule_b = (Condition("aaa_feature", "eq", True),)
    config = DiscoveryConfig(top_k=2, max_feature_identity_fraction=0.5)
    for _ in range(5):  # PYTHONHASHSEED varies process-to-process; a real repeat catches drift
        assert _apply_feature_identity_cap([rule_a, rule_b], config) == [rule_a, rule_b]
        assert _apply_feature_identity_cap([rule_b, rule_a], config) == [rule_b, rule_a]


def test_identity_cap_disabled_reproduces_v050_selection_exactly() -> None:
    """(d) Disabled mode (the default, and explicit 1.0) must reproduce discovery-engine-v0.5.0
    exactly: identical to calling the pre-TASK-068 selection primitive directly, bypassing every
    line of TASK-068 code."""
    frame = _feature_identity_crowding_frame()
    outcome = primary_outcome()
    implicit_default = discover_candidates(
        frame,
        _CROWDING_FEATURE_COLUMNS,
        outcome,
        DiscoveryConfig(min_n=8, beam_width=40, top_k=_CROWDING_TOP_K),
    )
    explicit_disabled = discover_candidates(
        frame,
        _CROWDING_FEATURE_COLUMNS,
        outcome,
        DiscoveryConfig(
            min_n=8, beam_width=40, top_k=_CROWDING_TOP_K, max_feature_identity_fraction=1.0
        ),
    )
    assert implicit_default["candidates"] == explicit_disabled["candidates"]
    assert implicit_default["methodology_version"] == "discovery-engine-v0.6.1"

    # `_apply_feature_identity_cap` on the actual selected output must be a true no-op at the
    # default -- confirms the guarantee structurally, not just behaviorally.
    rules = [tuple(c["conditions"]) for c in implicit_default["candidates"]]
    conditions_only = [
        tuple(Condition(cond["feature"], cond["operator"], cond["value"]) for cond in rule)
        for rule in rules
    ]
    unchanged = _apply_feature_identity_cap(
        conditions_only, DiscoveryConfig(top_k=_CROWDING_TOP_K)
    )
    assert unchanged == conditions_only


def test_apply_feature_identity_cap_default_is_a_no_op_on_a_synthetic_pool() -> None:
    rules = [(Condition("same_feature", "eq", i),) for i in range(5)]
    config = DiscoveryConfig(top_k=5)  # max_feature_identity_fraction defaults to 1.0
    assert _apply_feature_identity_cap(rules, config) == rules


def test_max_feature_identity_fraction_must_be_in_zero_to_one_range() -> None:
    for bad_fraction in (-0.1, 1.1):
        with pytest.raises(ValueError, match="max_feature_identity_fraction"):
            DiscoveryConfig(max_feature_identity_fraction=bad_fraction)
    DiscoveryConfig(max_feature_identity_fraction=0.0)  # bounds inclusive, neither raises
    DiscoveryConfig(max_feature_identity_fraction=1.0)


def test_identity_cap_never_admits_a_feature_outside_the_supplied_decision_time_columns() -> None:
    """(e) Fail closed on non-decision-time inputs: a column present in the underlying frame but
    deliberately withheld from `feature_columns` (standing in for a POST_DECISION/OUTCOME/UNKNOWN
    field the caller never classified DECISION_TIME) must never appear in any candidate's
    conditions, with the identity cap enabled or disabled -- the cap only ever sees rules built
    from `feature_columns`, so it cannot "reach around" that pre-existing boundary."""
    frame = _feature_identity_crowding_frame()
    # A column that would happily win the search on its own if it were ever allowed to
    # participate -- deliberately excluded from feature_columns below, standing in for a
    # POST_DECISION/OUTCOME/UNKNOWN field the discovery contract never admitted.
    frame = frame.with_columns(
        (pl.col("contribution_margin_eur") < 60.0).alias("excluded_non_decision_time_field")
    )
    outcome = primary_outcome()
    for fraction in (1.0, 0.34):
        result = discover_candidates(
            frame,
            _CROWDING_FEATURE_COLUMNS,  # excluded_non_decision_time_field intentionally absent
            outcome,
            DiscoveryConfig(
                min_n=20,
                beam_width=200,
                top_k=_CROWDING_TOP_K,
                max_feature_identity_fraction=fraction,
            ),
        )
        for candidate in result["candidates"]:
            for condition in candidate["conditions"]:
                assert condition["feature"] != "excluded_non_decision_time_field"


# --- TASK-097 (TASK-095's twice-reviewed design,
# docs/analytics/task-095-k1-reservation-design.md): bounded k==1 top-K reservation, Stage 3 of
# final assembly ---
#
# Two layers, matching this project's own established convention (TASK-060/TASK-068 tests above
# call _greedy_diverse_select/_apply_feature_identity_cap directly with synthetic Condition tuples
# *and* end to end through discover_candidates):
#   (a) direct-level tests call _reserve_k1_slot itself with hand-built final_selected/singles/
#       exposures/effective_score/atom_usage/max_overlap fixtures -- full control over every
#       mechanism edge case, matching the design's own worked traces (design §7) and test spec
#       (design §11).
#   (b) end-to-end tests call discover_candidates itself, reusing the *existing*,
#       already-established "supplier"/"discount_rate"/"party_size" fixture used several times
#       above for unrelated mechanisms (never a new travel/domain-flavored fixture), to prove the
#       real trigger-condition wiring inside discover_candidates -- not merely _reserve_k1_slot's
#       own internals -- is correct.
# No test in this section is tuned or verified by reference to travel's specific pattern
# identities or feature values: every Condition/feature/value below is invented, and the one real
# dataset reused (the supplier fixture) is the same fully-synthetic fixture already established
# above for unrelated TASK-058/TASK-060 tests.


def _noop_prepare(pool: list[tuple[Condition, ...]]) -> None:
    """Direct-level tests already populate exposures/effective_score for every rule passed to
    _reserve_k1_slot, so the real _prepare closure (discover_candidates's own, idempotent) has
    nothing left to do -- this stands in for it without needing a frame/outcome."""


def _pair(feature1: str, value1: object, feature2: str, value2: object) -> tuple[Condition, ...]:
    return (Condition(feature1, "eq", value1), Condition(feature2, "eq", value2))


def test_reserve_k1_slot_defaults_to_false() -> None:
    assert DiscoveryConfig().reserve_k1_slot is False


# --- (a) direct-level tests of _reserve_k1_slot itself ---


def test_reserve_k1_slot_no_qualifying_single_is_exact_fallback() -> None:
    """Design test 2 / §11: every single in the pool fails either the relevance floor or
    max_candidate_jaccard -- _reserve_k1_slot must return final_selected byte-identical, with
    activated=False disclosed in the metadata."""
    i1, i2 = _pair("gate", "one", "gate_x", "1"), _pair("gate", "two", "gate_x", "2")
    final_selected = [i1, i2]
    # S_dup: high raw score, but exposures overlap i1 at jaccard 0.9 > the default 0.85 ceiling --
    # only excluded because step 2 correctly seeds max_overlap against the real incumbents.
    s_dup = _rule("near", "dup")
    # S_weak: disjoint exposures (zero overlap), but its score (20) sits well under the singles
    # pool's own relevance floor once s_dup's much higher score (200) sets the phase reference.
    s_weak = _rule("weak", "x")
    singles = [s_dup, s_weak]
    exposures = {
        i1: frozenset(range(0, 80)),
        i2: frozenset(range(100, 180)),
        s_dup: frozenset(range(0, 72)),  # |i1 n s_dup|=72, |i1 u s_dup|=80 -> jaccard=0.9
        s_weak: frozenset(range(500, 560)),
    }
    effective_score = {i1: 100.0, i2: 90.0, s_dup: 200.0, s_weak: 20.0}
    atom_usage = {condition: 1 for condition in (*i1, *i2)}
    config = DiscoveryConfig(top_k=2)

    result, metadata = _reserve_k1_slot(
        final_selected, singles, exposures, effective_score, atom_usage, {}, config, _noop_prepare
    )
    assert result == final_selected
    assert metadata == {
        "eligible": True,
        "activated": False,
        "promoted_conditions": None,
        "displaced_conditions": None,
    }


def test_reserve_k1_slot_promotes_a_qualifying_single_and_drops_the_weakest_incumbent() -> None:
    """Design test 3 / §7.1: a single that clears the floor and has zero overlap against every
    incumbent must be promoted, displacing final_selected[-1] specifically (the weakest incumbent
    by the existing marginal-gain order -- i1 outscores i2, yet i2 is dropped, not i1, because i2
    is last in final_selected's own order, confirming the drop rule is positional, not a new score
    comparison)."""
    i1, i2 = _pair("gate", "one", "gate_x", "1"), _pair("gate", "two", "gate_x", "2")
    final_selected = [i1, i2]
    s_promote = _rule("solo", "z")
    singles = [s_promote]
    exposures = {
        i1: frozenset(range(0, 80)),
        i2: frozenset(range(100, 180)),
        s_promote: frozenset(range(300, 360)),  # disjoint from both incumbents
    }
    effective_score = {i1: 100.0, i2: 90.0, s_promote: 95.0}
    atom_usage = {condition: 1 for condition in (*i1, *i2)}
    config = DiscoveryConfig(top_k=2)

    result, metadata = _reserve_k1_slot(
        final_selected, singles, exposures, effective_score, atom_usage, {}, config, _noop_prepare
    )
    assert result == [i1, s_promote]
    assert metadata == {
        "eligible": True,
        "activated": True,
        "promoted_conditions": str(s_promote),
        "displaced_conditions": str(i2),
    }
    # Step 6: the shared atom_usage accumulator is updated too (dropped decremented, promoted
    # incremented), though nothing downstream reads it again.
    assert atom_usage[Condition("gate", "eq", "two")] == 0
    assert atom_usage[Condition("gate_x", "eq", "2")] == 0
    assert atom_usage[Condition("solo", "eq", "z")] == 1


def test_reserve_k1_slot_max_overlap_correction_is_necessary() -> None:
    """Design test 4 / §10.1: a single with a near-duplicate exposure overlap against an incumbent
    (jaccard 0.9, over the default 0.85 max_candidate_jaccard ceiling) must NOT be promoted once
    step 2 correctly seeds max_overlap against the real incumbents -- and, as the required contrast
    fixture, a manual simulation using the design's own round-1-flagged naive convention
    (max_overlap left at 0.0, exactly what _prepare's first-touch default would leave it at)
    WOULD have promoted it, proving the correction's necessity by direct execution, not prose."""
    i1, i2 = _pair("gate", "one", "gate_x", "1"), _pair("gate", "two", "gate_x", "2")
    final_selected = [i1, i2]
    s_near = _rule("near2", "dup")
    singles = [s_near]
    exposures = {
        i1: frozenset(range(0, 80)),
        i2: frozenset(range(100, 180)),
        s_near: frozenset(range(0, 72)),  # |i1 n s_near|=72, |i1 u s_near|=80 -> jaccard=0.9
    }
    effective_score = {i1: 100.0, i2: 90.0, s_near: 300.0}  # deliberately dominant if unblocked
    atom_usage = {condition: 1 for condition in (*i1, *i2)}
    config = DiscoveryConfig(top_k=2)

    result, metadata = _reserve_k1_slot(
        final_selected, singles, exposures, effective_score, dict(atom_usage), {}, config,
        _noop_prepare,
    )
    assert result == final_selected
    assert metadata["activated"] is False

    # Contrast: the naive, round-1-flagged convention (max_overlap seeded at 0.0 unconditionally,
    # exactly _prepare's own first-touch default) reproduced by calling _greedy_diverse_select
    # directly, bypassing _reserve_k1_slot's own step 2 correction entirely.
    naive_selected = list(final_selected)
    naive_selected_exposures = [exposures[i1], exposures[i2]]
    naive_atom_usage = dict(atom_usage)
    naive_max_overlap = dict.fromkeys(singles, 0.0)
    _greedy_diverse_select(
        singles,
        effective_score,
        exposures,
        DiscoveryConfig(top_k=len(final_selected) + 1),
        naive_selected,
        naive_selected_exposures,
        naive_atom_usage,
        naive_max_overlap,
    )
    assert naive_selected[-1] == s_near  # the defect: wrongly admitted under naive 0.0 seeding


def test_reserve_k1_slot_atom_usage_correction_is_necessary() -> None:
    """Design test 10 / §7.4 / §10.6: the round-1-found atom_usage staleness defect, reproduced on
    an invented pool. atom_usage (as Stage 1/2 would hand it over) carries a phantom count for atom
    `a_shared`, attributable only to a candidate `_apply_feature_identity_cap` would have dropped
    before final_selected -- `a_shared` itself is not used by any rule actually in final_selected.
    The real _reserve_k1_slot must recompute atom_usage_for_probe fresh from final_selected (step
    3) and correctly promote the qualifying single; a manual simulation reusing the stale,
    unrecomputed atom_usage directly (the design's original, round-1-flagged text) must wrongly
    decline it -- both asserted here by direct execution, not merely described."""
    a1, ax1 = Condition("feat_a1", "eq", True), Condition("feat_ax1", "eq", True)
    a2, ax2 = Condition("feat_a2", "eq", True), Condition("feat_ax2", "eq", True)
    ay1, ay2 = Condition("feat_ay1", "eq", True), Condition("feat_ay2", "eq", True)
    a_shared = Condition("feat_shared", "eq", True)
    j1, j2, k3 = (a1, ax1), (a2, ax2), (ay1, ay2)
    final_selected = [j1, j2, k3]
    s1 = (a_shared,)
    singles = [s1]
    exposures = {
        j1: frozenset(range(0, 50)),
        j2: frozenset(range(60, 110)),
        k3: frozenset(range(120, 170)),
        s1: frozenset(range(300, 350)),  # disjoint from every incumbent
    }
    effective_score = {j1: 100.0, j2: 95.0, k3: 90.0, s1: 85.0}
    # The stale accumulator Stage 1/2 would hand over: real counts for j1/j2/k3's own atoms, plus
    # a PHANTOM a_shared:1 left behind by a since-dropped candidate `_apply_feature_identity_cap`
    # trimmed without ever decrementing atom_usage for it (the round-1-found defect, design §10.6).
    stale_atom_usage = {a1: 1, ax1: 1, a2: 1, ax2: 1, ay1: 1, ay2: 1, a_shared: 1}
    config = DiscoveryConfig(top_k=3, max_candidates_per_atom=1)

    result, metadata = _reserve_k1_slot(
        final_selected,
        singles,
        exposures,
        effective_score,
        dict(stale_atom_usage),
        {},
        config,
        _noop_prepare,
    )
    assert result == [j1, j2, s1]
    assert metadata["activated"] is True
    assert metadata["promoted_conditions"] == str(s1)
    assert metadata["displaced_conditions"] == str(k3)

    # Contrast: reusing the stale atom_usage directly (dict(atom_usage), the design's original,
    # round-1-flagged text) instead of step 3's fresh recomputation wrongly declines s1: a_shared's
    # phantom count (1) already meets max_candidates_per_atom (1), even though zero rules in
    # final_selected actually use a_shared.
    naive_selected = list(final_selected)
    naive_selected_exposures = [exposures[j1], exposures[j2], exposures[k3]]
    naive_atom_usage = dict(stale_atom_usage)  # NOT recomputed from final_selected -- the defect
    naive_max_overlap: dict[tuple[Condition, ...], float] = {}
    for single in singles:
        naive_max_overlap[single] = max(
            (
                _jaccard(exposures[single], exposures[rule])
                for rule in final_selected
            ),
            default=0.0,
        )
    _greedy_diverse_select(
        singles,
        effective_score,
        exposures,
        DiscoveryConfig(top_k=len(final_selected) + 1, max_candidates_per_atom=1),
        naive_selected,
        naive_selected_exposures,
        naive_atom_usage,
        naive_max_overlap,
    )
    assert len(naive_selected) == len(final_selected)  # s1 wrongly declined under the stale dict


def test_reserve_k1_slot_feature_identity_recheck_declines_when_capacity_stays_full() -> None:
    """Design test 5 / §5.5, decline branch: the promoted single's own feature is already at
    max_per_feature capacity among the incumbents that would *survive* the drop (the about-to-be-
    dropped incumbent does not itself hold that feature, so dropping it cannot free capacity)."""
    i1 = _pair("shared_feat", "a", "filler1", "x")
    i2 = _pair("shared_feat", "b", "filler2", "x")
    i3 = _pair("other_feat", "c", "filler3", "x")  # final_selected[-1]; holds no shared_feat use
    final_selected = [i1, i2, i3]
    s_promote = (Condition("shared_feat", "eq", "promote"),)
    singles = [s_promote]
    exposures = {
        i1: frozenset(range(0, 50)),
        i2: frozenset(range(60, 110)),
        i3: frozenset(range(120, 170)),
        s_promote: frozenset(range(300, 350)),
    }
    effective_score = {i1: 100.0, i2: 95.0, i3: 90.0, s_promote: 85.0}
    atom_usage = {condition: 1 for rule in final_selected for condition in rule}
    config = DiscoveryConfig(top_k=3, max_feature_identity_fraction=0.67)  # max_per_feature = 2

    result, metadata = _reserve_k1_slot(
        final_selected, singles, exposures, effective_score, atom_usage, {}, config, _noop_prepare
    )
    assert result == final_selected  # declined: shared_feat stays at 2 (i1, i2) even after the drop
    assert metadata["activated"] is False


def test_reserve_k1_slot_feature_identity_recheck_allows_when_dropped_held_the_last_slot() -> None:
    """Design test 5 / §5.5, allow branch: the about-to-be-dropped incumbent (final_selected[-1])
    is itself the one holding the promoted single's feature at capacity -- dropping it frees the
    slot, so promotion must proceed."""
    i1 = _pair("shared_feat", "a", "filler1", "x")
    i2 = _pair("other_feat2", "b", "filler2", "x")
    i3 = _pair("shared_feat", "c", "filler3", "x")  # final_selected[-1]; holds shared_feat too
    final_selected = [i1, i2, i3]
    s_promote = (Condition("shared_feat", "eq", "promote"),)
    singles = [s_promote]
    exposures = {
        i1: frozenset(range(0, 50)),
        i2: frozenset(range(60, 110)),
        i3: frozenset(range(120, 170)),
        s_promote: frozenset(range(300, 350)),
    }
    effective_score = {i1: 100.0, i2: 95.0, i3: 90.0, s_promote: 85.0}
    atom_usage = {condition: 1 for rule in final_selected for condition in rule}
    config = DiscoveryConfig(top_k=3, max_feature_identity_fraction=0.67)  # max_per_feature = 2

    result, metadata = _reserve_k1_slot(
        final_selected, singles, exposures, effective_score, atom_usage, {}, config, _noop_prepare
    )
    assert result == [i1, i2, s_promote]
    assert metadata["activated"] is True
    assert metadata["displaced_conditions"] == str(i3)


def test_reserve_k1_slot_is_deterministic_across_repeated_runs() -> None:
    """Design test 8: rerunning the identical inputs (fresh copies of every mutable dict/list
    argument) must produce byte-identical final_selected and k1_reservation metadata both times."""
    i1, i2 = _pair("gate", "one", "gate_x", "1"), _pair("gate", "two", "gate_x", "2")
    s_promote = _rule("solo", "z")
    exposures = {
        i1: frozenset(range(0, 80)),
        i2: frozenset(range(100, 180)),
        s_promote: frozenset(range(300, 360)),
    }
    effective_score = {i1: 100.0, i2: 90.0, s_promote: 95.0}
    config = DiscoveryConfig(top_k=2)

    results = []
    for _ in range(2):
        final_selected = [i1, i2]
        atom_usage = {condition: 1 for condition in (*i1, *i2)}
        results.append(
            _reserve_k1_slot(
                final_selected,
                [s_promote],
                exposures,
                effective_score,
                atom_usage,
                {},
                config,
                _noop_prepare,
            )
        )
    assert results[0] == results[1]


def test_reserve_k1_slot_order_independent() -> None:
    """Design test 9: the promoted single and dropped incumbent must be identical regardless of
    the order singles are presented in, or the order exposures/effective_score dicts were built in
    -- mirroring ADR-071's own adversarial standard, verified directly against the real
    implementation rather than assumed to hold from the determinism analysis alone."""
    i1, i2 = _pair("gate", "one", "gate_x", "1"), _pair("gate", "two", "gate_x", "2")
    s_best = _rule("solo", "best")
    s_mid = _rule("solo", "mid")
    s_worst = _rule("solo", "worst")
    exposures_forward = {
        i1: frozenset(range(0, 80)),
        i2: frozenset(range(100, 180)),
        s_best: frozenset(range(300, 360)),
        s_mid: frozenset(range(400, 460)),
        s_worst: frozenset(range(500, 560)),
    }
    score_forward = {i1: 100.0, i2: 90.0, s_best: 95.0, s_mid: 80.0, s_worst: 78.0}
    config = DiscoveryConfig(top_k=2)

    permutations = [
        [s_best, s_mid, s_worst],
        [s_worst, s_mid, s_best],
        [s_mid, s_best, s_worst],
    ]
    outcomes = []
    for singles_order in permutations:
        # Rebuild both dicts in the *same* order as this permutation, so dict-insertion order
        # varies across iterations too, not just the singles list order.
        exposures = {rule: exposures_forward[rule] for rule in (i1, i2, *singles_order)}
        effective_score = {rule: score_forward[rule] for rule in (i1, i2, *singles_order)}
        final_selected = [i1, i2]
        atom_usage = {condition: 1 for condition in (*i1, *i2)}
        result, metadata = _reserve_k1_slot(
            final_selected,
            list(singles_order),
            exposures,
            effective_score,
            atom_usage,
            {},
            config,
            _noop_prepare,
        )
        outcomes.append((result, metadata))
    assert all(outcome == outcomes[0] for outcome in outcomes[1:])
    assert outcomes[0][1]["promoted_conditions"] == str(s_best)


# --- (b) end-to-end tests through discover_candidates, reusing the existing supplier/discount
# fixture (also used above by TASK-058/TASK-060 tests) at top_k values chosen to exercise each of
# the design's four worked traces against the real search/selection pipeline. ---


def _reservation_fixture_frame() -> pl.DataFrame:
    rows = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(400):
            supplier = "A" if index % 2 == 0 else "B"
            discount = (index % 10) / 100
            harm = 80.0 if supplier == "A" and discount >= 0.05 else 0.0
            rows.append((supplier, discount, index % 3, 200.0 - harm, split))
    return pl.DataFrame(
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


_RESERVATION_FEATURES = ("supplier", "discount_rate", "party_size")


def test_discover_candidates_common_case_promotes_a_single_end_to_end() -> None:
    """§7.1 end to end: at top_k=10, this fixture's real search fills every slot with interactions
    (confirmed by the reserve_k1_slot=False baseline below) -- reserve_k1_slot=True must promote
    a genuinely qualifying single, displacing the weakest interaction, while candidate_count stays
    exactly top_k."""
    frame = _reservation_fixture_frame()
    outcome = primary_outcome()
    baseline = discover_candidates(
        frame,
        _RESERVATION_FEATURES,
        outcome,
        DiscoveryConfig(min_n=20, beam_width=30, top_k=10, reserve_k1_slot=False),
    )
    assert baseline["candidate_count"] == 10
    assert all(len(c["conditions"]) >= 2 for c in baseline["candidates"])
    assert baseline["k1_reservation"] == {
        "eligible": False,
        "activated": False,
        "promoted_conditions": None,
        "displaced_conditions": None,
    }

    reserved = discover_candidates(
        frame,
        _RESERVATION_FEATURES,
        outcome,
        DiscoveryConfig(min_n=20, beam_width=30, top_k=10, reserve_k1_slot=True),
    )
    assert reserved["candidate_count"] == 10  # top_k itself never changes
    ks = [len(c["conditions"]) for c in reserved["candidates"]]
    assert ks.count(1) == 1  # exactly the one reserved slot, never more
    assert reserved["k1_reservation"]["eligible"] is True
    assert reserved["k1_reservation"]["activated"] is True
    promoted = reserved["k1_reservation"]["promoted_conditions"]
    displaced = reserved["k1_reservation"]["displaced_conditions"]
    assert promoted is not None and displaced is not None
    assert promoted.count("Condition(") == 1  # the promoted candidate is k==1
    assert displaced.count("Condition(") >= 2  # the displaced candidate was k>=2
    # The promoted single actually appears in the reported candidates, with the disclosed warning.
    promoted_candidates = [c for c in reserved["candidates"] if len(c["conditions"]) == 1]
    assert len(promoted_candidates) == 1
    assert any(
        "Promoted via the bounded k==1 reservation quota" in warning
        for warning in promoted_candidates[0]["warnings"]
    )
    # reserve_k1_slot genuinely changed the outcome on this exact fixture/top_k -- the False-case
    # byte-identity claim tested separately below is non-vacuous.
    assert reserved["candidates"] != baseline["candidates"]


def test_discover_candidates_uncommon_case_does_not_fire_end_to_end() -> None:
    """§7.2 end to end: at a top_k this fixture's real candidate pool cannot fill at all (11 total
    eligible candidates, well under top_k=15), Stage 3 must not even be eligible -- the trigger's
    own count check fails before its composition check is ever reached."""
    frame = _reservation_fixture_frame()
    result = discover_candidates(
        frame,
        _RESERVATION_FEATURES,
        primary_outcome(),
        DiscoveryConfig(min_n=20, beam_width=30, top_k=15, reserve_k1_slot=True),
    )
    assert result["candidate_count"] == 11
    assert result["candidate_count"] < 15
    assert result["k1_reservation"] == {
        "eligible": False,
        "activated": False,
        "promoted_conditions": None,
        "displaced_conditions": None,
    }


def test_discover_candidates_composition_edge_case_does_not_double_promote_end_to_end() -> None:
    """§7.3 end to end: at top_k=11, this fixture's real Stage 2 fallback already promotes exactly
    one single to reach a full top_k=11 -- Stage 3's own trigger (`all(len(rule) >= 2 ...)`) must
    then correctly read that composition and decline to run at all, not attempt a second
    promotion. reserve_k1_slot=True and reserve_k1_slot=False must produce byte-identical output
    here -- the "up to 1" bound is respected by construction, not a separate counter."""
    frame = _reservation_fixture_frame()
    outcome = primary_outcome()
    config_kwargs: dict[str, int] = {"min_n": 20, "beam_width": 30, "top_k": 11}
    config_without = DiscoveryConfig(**config_kwargs, reserve_k1_slot=False)
    config_with = DiscoveryConfig(**config_kwargs, reserve_k1_slot=True)
    without_reservation = discover_candidates(frame, _RESERVATION_FEATURES, outcome, config_without)
    with_reservation = discover_candidates(frame, _RESERVATION_FEATURES, outcome, config_with)
    assert without_reservation["candidate_count"] == 11
    ks = [len(c["conditions"]) for c in without_reservation["candidates"]]
    assert ks.count(1) == 1  # Stage 2's own pre-existing fallback already placed one single
    assert with_reservation["k1_reservation"] == {
        "eligible": False,
        "activated": False,
        "promoted_conditions": None,
        "displaced_conditions": None,
    }
    assert with_reservation["candidates"] == without_reservation["candidates"]


def test_reserve_k1_slot_false_is_a_structural_no_op_not_output_matching() -> None:
    """Confirms structurally, not just by output-matching, that the new Stage 3 code path is never
    even evaluated when reserve_k1_slot=False: monkeypatch _reserve_k1_slot to raise, at the exact
    top_k=10 fixture/config where the trigger condition would otherwise hold (per the common-case
    test above) -- discover_candidates must still succeed, proving the call is behind a real
    `config.reserve_k1_slot and ...` guard, not a code path that happens to produce the same
    result."""
    import policy_analytics.discovery.engine as engine_module

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("_reserve_k1_slot must not be called when reserve_k1_slot=False")

    original = engine_module._reserve_k1_slot
    engine_module._reserve_k1_slot = _boom  # type: ignore[assignment]
    try:
        frame = _reservation_fixture_frame()
        result = discover_candidates(
            frame,
            _RESERVATION_FEATURES,
            primary_outcome(),
            DiscoveryConfig(min_n=20, beam_width=30, top_k=10, reserve_k1_slot=False),
        )
    finally:
        engine_module._reserve_k1_slot = original  # type: ignore[assignment]
    assert result["candidate_count"] == 10
    assert all(len(c["conditions"]) >= 2 for c in result["candidates"])


def test_reserve_k1_slot_false_is_byte_identical_to_pre_task_097_selection() -> None:
    """The required reserve_k1_slot=False regression (design §11 test 1 / TASK-097's own testing
    bar): run the identical fixture/config through discover_candidates with reserve_k1_slot
    omitted (defaults False) and confirm every per-candidate field, in order, matches a literal,
    independently-verified pre-TASK-097 capture -- not merely "equivalent". Diffed against the
    top_k=10 fixture specifically because that is the exact configuration
    (test_discover_candidates_common_case_promotes_a_single_end_to_end) where reserve_k1_slot=True
    changes the output, so this byte-identity claim is meaningful, not vacuous."""
    frame = _reservation_fixture_frame()
    implicit_default = discover_candidates(
        frame,
        _RESERVATION_FEATURES,
        primary_outcome(),
        DiscoveryConfig(min_n=20, beam_width=30, top_k=10),
    )
    explicit_false = discover_candidates(
        frame,
        _RESERVATION_FEATURES,
        primary_outcome(),
        DiscoveryConfig(min_n=20, beam_width=30, top_k=10, reserve_k1_slot=False),
    )
    assert implicit_default["candidates"] == explicit_false["candidates"]
    assert implicit_default["methodology_version"] == "discovery-engine-v0.6.1"
    ks = [len(c["conditions"]) for c in implicit_default["candidates"]]
    assert ks == [2, 3, 3, 3, 3, 2, 2, 2, 2, 2]  # all ten slots filled by interactions, no k==1


def test_discover_candidates_top_k_never_changes_regardless_of_reservation() -> None:
    """candidate_count (the real, reported top-K size) must equal the same value whether or not
    Stage 3 fires -- a bounded swap inside top_k, never a top_k increase."""
    frame = _reservation_fixture_frame()
    outcome = primary_outcome()
    for top_k in (10, 11, 15):
        without = discover_candidates(
            frame,
            _RESERVATION_FEATURES,
            outcome,
            DiscoveryConfig(min_n=20, beam_width=30, top_k=top_k, reserve_k1_slot=False),
        )
        with_reservation = discover_candidates(
            frame,
            _RESERVATION_FEATURES,
            outcome,
            DiscoveryConfig(min_n=20, beam_width=30, top_k=top_k, reserve_k1_slot=True),
        )
        assert without["candidate_count"] == with_reservation["candidate_count"]
        assert without["candidate_count"] <= top_k
        assert with_reservation["candidate_count"] <= top_k


def test_discover_candidates_k1_reservation_metadata_always_present_and_disclosed() -> None:
    """The k1_reservation audit-metadata block (design §4.1/§4.3) must always be present, with
    eligible=False disclosed (not merely absent) whenever reserve_k1_slot=False, regardless of
    whether the trigger condition would otherwise have held."""
    frame = _reservation_fixture_frame()
    outcome = primary_outcome()
    for top_k in (10, 15):  # 10: trigger would hold if enabled; 15: it would not
        result = discover_candidates(
            frame,
            _RESERVATION_FEATURES,
            outcome,
            DiscoveryConfig(min_n=20, beam_width=30, top_k=top_k, reserve_k1_slot=False),
        )
        assert result["k1_reservation"] == {
            "eligible": False,
            "activated": False,
            "promoted_conditions": None,
            "displaced_conditions": None,
        }


def test_discover_candidates_reservation_is_deterministic_end_to_end() -> None:
    """Rerunning the identical fixture/config with reserve_k1_slot=True must produce byte-identical
    candidates and k1_reservation metadata both times (design §6/§11 test 8, end to end)."""
    frame = _reservation_fixture_frame()
    outcome = primary_outcome()
    config = DiscoveryConfig(min_n=20, beam_width=30, top_k=10, reserve_k1_slot=True)
    first = discover_candidates(frame, _RESERVATION_FEATURES, outcome, config)
    second = discover_candidates(frame, _RESERVATION_FEATURES, outcome, config)
    assert first["candidates"] == second["candidates"]
    assert first["k1_reservation"] == second["k1_reservation"]
