"""Regression tests for the G05 multiplicity fix (ADR-014/ADR-015, validation contract v1.1.0).

Everything here is synthetic and mathematical — seeded RNG draws and hand-constructed replicate
sets, never real candidate data, never `hidden_ground_truth.json` or `synthetic_benchmark.py`. The
point of this file is to prove the defect and the fix as *general* mathematical properties of the
estimators, independent of any specific candidate or dataset, exactly so no synthetic-pattern
knowledge could have shaped it.
"""

from __future__ import annotations

import itertools
import random

import pytest
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS
from policy_analytics.validation.grading import (
    benjamini_hochberg_adjusted,
    bootstrap_standard_error,
    bootstrap_two_sided_p,
    normal_approx_two_sided_p,
)

pytestmark = pytest.mark.analytics

FDR_ALPHA = DEFAULT_THRESHOLDS.fdr_alpha  # 0.10, unchanged by this fix
REALISTIC_FAMILY_SIZE = 6_945  # the actual TASK-015 dry-run family size, used only as an example
LARGE_FUTURE_FAMILY_SIZE = 100_000  # a generous upper bound for future, larger discovery runs
BOOTSTRAP_REPS = 2_000  # the contract's bootstrap_resamples


def _rng() -> random.Random:
    return random.Random(20260814)


# --- 1. Formal description of the old defect, reproduced mathematically --------------------------


def test_old_method_cannot_distinguish_a_modest_effect_from_an_enormous_one() -> None:
    """The empirical count-based p-value is a function of *sign agreement only*, not magnitude,
    once every replicate shares a sign — so it cannot tell a barely-detectable effect from an
    astronomically large one. This is the exact mechanism behind the ADR-014 defect."""
    modest_effect_replicates = [1.0] * BOOTSTRAP_REPS
    enormous_effect_replicates = [1.0e12] * BOOTSTRAP_REPS

    p_modest = bootstrap_two_sided_p(modest_effect_replicates)
    p_enormous = bootstrap_two_sided_p(enormous_effect_replicates)

    assert p_modest == p_enormous == pytest.approx(1.0 / (BOOTSTRAP_REPS + 1))


def test_old_method_structurally_fails_bh_correction_at_realistic_family_size() -> None:
    """Even the most significant possible result under the old method (every replicate agrees in
    sign, p at the floor) cannot survive BH correction once family_size is in the low thousands —
    for *any* candidate, regardless of how many are tested or how strong their effects are."""
    floor_p = bootstrap_two_sided_p([1.0] * BOOTSTRAP_REPS)
    assert floor_p == pytest.approx(1.0 / (BOOTSTRAP_REPS + 1))

    # 15 candidates, all at the floor (the worst case for BH is also the most realistic case here:
    # every real TASK-015 candidate actually landed exactly at this floor).
    reported_p_values = [floor_p] * 15
    adjusted = benjamini_hochberg_adjusted(reported_p_values, family_size=REALISTIC_FAMILY_SIZE)

    assert all(value > FDR_ALPHA for value in adjusted), (
        "the old method must fail every candidate at this family size, proving the gate was "
        "unsatisfiable by construction, not by evidence"
    )


def test_old_methods_floor_exceeds_the_bh_requirement_for_any_family_size_above_a_few_hundred() -> (
    None
):
    """General form of the defect: the floor 1/(B+1) beats alpha/family_size (the most lenient,
    rank-1 BH threshold) once family_size exceeds roughly alpha*(B+1). At B=2000, alpha=0.10, that
    crossover is family_size ~= 200 — far below any real discovery search."""
    floor = 1.0 / (BOOTSTRAP_REPS + 1)
    crossover_family_size = FDR_ALPHA * (BOOTSTRAP_REPS + 1)
    assert crossover_family_size == pytest.approx(200.1, abs=1.0)

    for family_size in (500, REALISTIC_FAMILY_SIZE, LARGE_FUTURE_FAMILY_SIZE):
        best_possible_rank1_threshold = FDR_ALPHA * 1 / family_size
        assert floor > best_possible_rank1_threshold, (
            f"at family_size={family_size} the floor should already exceed even the most "
            "lenient possible BH threshold"
        )


# --- 2. Mathematical sufficiency of the replacement method ---------------------------------------


def test_normal_approximation_has_no_resolution_floor() -> None:
    """Unlike the empirical method, doubling the effect (holding SE fixed) keeps shrinking the
    p-value — there is no saturation point reachable by real data."""
    p_values = [
        normal_approx_two_sided_p(point_estimate=z, standard_error=1.0) for z in (3, 6, 12, 24)
    ]
    assert p_values == sorted(p_values, reverse=True)
    assert all(later < earlier for earlier, later in itertools.pairwise(p_values))


def test_normal_approximation_resolves_far_below_bh_requirements_at_any_realistic_family_size() -> (
    None
):
    """Mathematical sufficiency proof (see docs/analytics/validation-contract.md §4a). The
    strictest BH threshold this system could plausibly ever require is alpha/family_size at
    rank 1. Even at a generous future family size of 100,000, that threshold is ~1e-6, reachable
    at about z~4.9 standard errors — and normal_approx_two_sided_p keeps resolving, without
    underflowing to a wrong value, out to roughly z~38 (p on the order of 1e-315), leaving many
    orders of magnitude of headroom."""
    worst_case_threshold = FDR_ALPHA / LARGE_FUTURE_FAMILY_SIZE
    assert worst_case_threshold == pytest.approx(1e-6)

    # A modest z of 5 standard errors — far short of what a real, large-sample cluster-bootstrap
    # effect typically produces — already clears the requirement with margin.
    p_at_z5 = normal_approx_two_sided_p(point_estimate=5.0, standard_error=1.0)
    assert 0.0 < p_at_z5 < worst_case_threshold

    # The function must not silently return an incorrect large value or raise as z grows; it
    # should either resolve a genuinely tiny positive float or cleanly underflow to 0.0 (which
    # still correctly satisfies "below any finite threshold").
    for z in (10.0, 20.0, 40.0, 100.0):
        p = normal_approx_two_sided_p(point_estimate=z, standard_error=1.0)
        assert 0.0 <= p < worst_case_threshold

    # A null effect (z=0) must give exactly p=1, not something that could be mistaken for
    # resolution failure.
    assert normal_approx_two_sided_p(point_estimate=0.0, standard_error=1.0) == pytest.approx(1.0)


def test_bootstrap_standard_error_converges_on_a_known_synthetic_distribution() -> None:
    """Sanity-check the SE estimator against a distribution with a known true standard deviation,
    so the p-value built on top of it is trustworthy."""
    rng = _rng()
    true_sd = 50.0
    replicates = [rng.gauss(300.0, true_sd) for _ in range(BOOTSTRAP_REPS)]
    se = bootstrap_standard_error(replicates)
    assert se == pytest.approx(true_sd, rel=0.1)


# --- 3. The three-part regression the fix must exhibit -------------------------------------------


def _synthetic_bootstrap_replicates(
    rng: random.Random, mean: float, sd: float, n: int
) -> list[float]:
    """A stand-in for a real cluster-bootstrap replicate set: draws from a normal sampling
    distribution with the given mean and spread. Purely synthetic — no dataset, no candidate, no
    hidden pattern involved."""
    return [rng.gauss(mean, sd) for _ in range(n)]


def test_strong_synthetic_effect_fails_under_the_old_method_and_passes_under_the_new_one() -> None:
    """The core regression: a large-sample-style effect (mean far from zero relative to its
    spread — comparable in shape to what a ~1,000-row cluster-bootstrap on a real, strong effect
    produces) must fail G05's old p-value source and pass under the fixed one, at a realistic
    family size."""
    rng = _rng()
    strong_effect_replicates = _synthetic_bootstrap_replicates(
        rng, mean=300.0, sd=45.0, n=BOOTSTRAP_REPS
    )
    # Every replicate should share the point estimate's sign for the empirical method to hit its
    # floor cleanly, matching what every real TASK-015 candidate actually exhibited.
    assert all(value > 0 for value in strong_effect_replicates)

    old_p = bootstrap_two_sided_p(strong_effect_replicates)
    old_adjusted = benjamini_hochberg_adjusted([old_p] * 15, family_size=REALISTIC_FAMILY_SIZE)[0]
    assert old_adjusted > FDR_ALPHA, "the old method must still fail here despite the strong effect"

    se = bootstrap_standard_error(strong_effect_replicates)
    point_estimate = sum(strong_effect_replicates) / len(strong_effect_replicates)
    new_p = normal_approx_two_sided_p(point_estimate, se)
    new_adjusted = benjamini_hochberg_adjusted([new_p] * 15, family_size=REALISTIC_FAMILY_SIZE)[0]
    assert new_adjusted <= FDR_ALPHA, "the fixed method must pass a genuinely strong effect"


def test_null_synthetic_effect_still_fails_under_the_new_method() -> None:
    """The fix must not be a rubber stamp: a synthetic replicate set centered on zero (a null
    effect, with realistic noise) must still fail G05 under the normal-approximation method,
    exactly as it would — and did — under the old one."""
    rng = _rng()
    null_replicates = _synthetic_bootstrap_replicates(rng, mean=0.0, sd=45.0, n=BOOTSTRAP_REPS)

    se = bootstrap_standard_error(null_replicates)
    point_estimate = sum(null_replicates) / len(null_replicates)
    new_p = normal_approx_two_sided_p(point_estimate, se)
    assert new_p > FDR_ALPHA  # not even raw-significant, let alone after correction

    new_adjusted = benjamini_hochberg_adjusted([new_p] * 15, family_size=REALISTIC_FAMILY_SIZE)[0]
    assert new_adjusted > FDR_ALPHA

    # For comparison, the old method on the same null data: with noise this large relative to a
    # near-zero mean, replicates split across both signs, so the old method also correctly fails
    # here — the defect was specifically about *inflating* the floor for strong effects, not about
    # ever wrongly passing weak ones.
    old_p = bootstrap_two_sided_p(null_replicates)
    assert old_p > FDR_ALPHA
