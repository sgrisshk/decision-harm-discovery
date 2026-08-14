import json
import math
import random
from pathlib import Path

import polars as pl
import pytest
from policy_analytics.outcomes import OUTCOME_BY_ID, primary_outcome
from policy_analytics.validation.apply import (
    ClusterCell,
    Condition,
    Verdict,
    _stratified_two_way_adjustment,
    cluster_bootstrap_replicates,
    cluster_cells,
    e_value,
    minimum_detectable_effect,
    percentile_ci,
    rule_expr,
    run_validation,
    split_stats,
    verdict_for,
)
from policy_analytics.validation.contract import GateId

pytestmark = pytest.mark.analytics

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATASET = REPO_ROOT / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
REAL_CANDIDATES = REPO_ROOT / "artifacts/discovery/task-015-candidates.json"


def _rng() -> random.Random:
    return random.Random(1234)


def test_rule_expr_matches_conjunction() -> None:
    frame = pl.DataFrame(
        {"discount_rate": [0.05, 0.15, 0.20], "manual_exception": [False, False, True]}
    )
    conditions = (
        Condition("discount_rate", "ge", 0.12),
        Condition("manual_exception", "eq", False),
    )
    mask = frame.select(rule_expr(conditions).alias("m"))["m"]
    assert mask.to_list() == [False, True, False]


def test_cluster_cells_and_bootstrap_replicates_recover_the_true_difference() -> None:
    # Two clusters, no within-cluster mixing: cluster A is entirely exposed at mean 100, cluster
    # B is entirely comparison at mean 50. The bootstrap must reproduce the exact 50-unit gap.
    frame = pl.DataFrame(
        {
            "customer_id": ["A"] * 10 + ["B"] * 10,
            "outcome": [100.0] * 10 + [50.0] * 10,
        }
    )
    mask = frame["customer_id"] == "A"
    cells = cluster_cells(frame, mask, "outcome")
    assert cells["A"] == ClusterCell(
        exposed_sum=1000.0, exposed_n=10, comparison_sum=0.0, comparison_n=0
    )
    assert cells["B"] == ClusterCell(
        exposed_sum=0.0, exposed_n=0, comparison_sum=500.0, comparison_n=10
    )

    replicates = cluster_bootstrap_replicates(cells, reps=500, rng=_rng())
    # Every bootstrap draw resamples only from {A, B}; whenever both appear the difference is
    # always exactly 100 - 50 = 50 regardless of how many times each cluster is drawn.
    assert replicates
    assert all(math.isclose(r, 50.0) for r in replicates)


def test_percentile_ci_bounds_and_empty_input() -> None:
    values = [float(v) for v in range(1, 101)]  # 1..100
    low, high = percentile_ci(values, confidence_level=0.95)
    assert low == pytest.approx(3.0, abs=1.0)
    assert high == pytest.approx(98.0, abs=1.0)
    assert percentile_ci([], 0.95) == (0.0, 0.0)


def test_minimum_detectable_effect_shrinks_with_sample_size() -> None:
    small = minimum_detectable_effect(exposed_n=30, comparison_n=30, pooled_sd=100.0)
    large = minimum_detectable_effect(exposed_n=3000, comparison_n=3000, pooled_sd=100.0)
    assert large < small
    assert minimum_detectable_effect(0, 10, 100.0) == math.inf


def test_e_value_increases_with_standardized_effect() -> None:
    weak = e_value(harm_per_booking=10.0, pooled_sd=100.0)
    strong = e_value(harm_per_booking=300.0, pooled_sd=100.0)
    assert strong > weak
    assert e_value(10.0, 0.0) == math.inf
    # A null effect should produce the minimum possible E-value (RR=1 -> E-value=1).
    assert e_value(0.0, 100.0) == pytest.approx(1.0)


def test_split_stats_computes_signed_harm_and_pooled_sd() -> None:
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]  # higher_is_worse=False
    frame = pl.DataFrame({"contribution_margin_eur": [100.0, 100.0, 300.0, 300.0]})
    mask = pl.Series([True, True, False, False])  # exposed mean 100, comparison mean 300
    stats = split_stats(frame, mask, outcome, "development")
    assert stats is not None
    assert stats.raw_difference == pytest.approx(-200.0)
    # Margin dropped -> harmful -> harm_per_booking positive despite a negative raw difference.
    assert stats.harm_per_booking == pytest.approx(200.0)
    assert stats.pooled_sd == pytest.approx(0.0)  # no within-group variance in this fixture


def test_split_stats_returns_none_when_a_group_is_empty() -> None:
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    frame = pl.DataFrame({"contribution_margin_eur": [100.0, 200.0]})
    mask = pl.Series([True, True])  # comparison group is empty
    assert split_stats(frame, mask, outcome, "development") is None


def test_stratified_adjustment_removes_a_confound_the_raw_difference_carries() -> None:
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    # Manager X rows are entirely exposed, manager Y rows are entirely comparison, and there is
    # no within-manager effect at all: the huge raw gap is purely manager composition.
    frame = pl.DataFrame(
        {
            "manager": ["X"] * 8 + ["Y"] * 8,
            "contribution_margin_eur": [50.0] * 8 + [500.0] * 8,
        }
    )
    mask = pl.Series([True] * 8 + [False] * 8)
    raw = (
        frame.filter(mask)["contribution_margin_eur"].mean()
        - frame.filter(~mask)["contribution_margin_eur"].mean()
    )
    assert raw is not None and raw < -400  # large apparent raw effect

    adjusted_diff, coverage = _stratified_two_way_adjustment(frame, mask, outcome, ("manager",))
    assert coverage == 0.0  # every manager X row is exposed, every manager Y row is comparison:
    # no stratum contains both exposed and comparison members, so no stratum is usable.
    assert adjusted_diff == 0.0


def test_stratified_adjustment_with_balanced_strata_finds_the_true_effect() -> None:
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    # Two managers, each contributing both exposed and comparison rows; within each manager the
    # exposed rows are exactly 30 lower than comparison rows.
    frame = pl.DataFrame(
        {
            "manager": ["X"] * 20 + ["Y"] * 20,
            "contribution_margin_eur": ([70.0] * 10 + [100.0] * 10 + [170.0] * 10 + [200.0] * 10),
        }
    )
    mask = pl.Series([True] * 10 + [False] * 10 + [True] * 10 + [False] * 10)
    adjusted_diff, coverage = _stratified_two_way_adjustment(frame, mask, outcome, ("manager",))
    assert adjusted_diff == pytest.approx(-30.0)
    assert coverage == pytest.approx(1.0)


def test_verdict_for_reject_when_evidence_level_is_none() -> None:
    class _Stub:
        evidence_level = None
        policy_readiness = None

    assert verdict_for(_Stub()) == Verdict.REJECT  # type: ignore[arg-type]


@pytest.mark.skipif(
    not (REAL_DATASET.exists() and REAL_CANDIDATES.exists()),
    reason="delivered analytical dataset or discovery artifact not present",
)
@pytest.mark.slow
def test_run_validation_against_the_real_frozen_candidates() -> None:
    """End-to-end check against the actual TASK-015 artifact. Opens no ground truth."""
    forbidden_paths = [
        REPO_ROOT / "synthetic_data/evaluation/hidden_ground_truth.json",
        REPO_ROOT / "packages/analytics/src/policy_analytics/synthetic_benchmark.py",
    ]
    for path in forbidden_paths:
        assert path.exists(), "sanity check: the restricted file should exist to prove non-use"

    results, run_manifest = run_validation(
        dataset_root=REAL_DATASET,
        candidates_path=REAL_CANDIDATES,
        outcome=primary_outcome(),
        dataset_version="travel-bookings-analytical-v1.0.0",
        outcome_definition_version="1.1.0",
        analysis_run_id="pytest-run",
    )

    payload = json.loads(REAL_CANDIDATES.read_text(encoding="utf-8"))
    assert len(results) == len(payload["candidates"])
    assert run_manifest["family_size"] == payload["search"]["evaluated_hypotheses"]

    for result in results:
        assert result.verdict in (Verdict.PASS, Verdict.DOWNGRADE, Verdict.REJECT)
        gate_ids = {g.gate_id for g in result.report.gate_results}
        assert gate_ids == set(GateId)
        # No candidate may reach a level above what observational identification permits.
        assert result.report.evidence_level != "quasi_causal_evidence"
        assert result.report.evidence_level != "experimental_evidence"

    # This only exercises the code against real data; it persists nothing and is not evidence
    # about these candidates. The candidate artifact is still not blind-protocol-compliant
    # (ADR-008/TASK-017) and the founder readiness block on TASK-015/016 is still in force — a
    # PASS verdict computed here must never be read as a validated finding. See ADR-014/ADR-015
    # and TASK-019's registry entry.
    #
    # It does demonstrate the G05 fix (ADR-015): the binding p-value is now the normal
    # approximation, not the empirical bootstrap count, and it is dramatically smaller for every
    # candidate — the empirical count-based diagnostic still sits at the 2000-replicate resolution
    # floor (~0.0005) for every candidate, exactly reproducing the pre-fix defect if it were still
    # the binding source.
    passing_candidates = 0
    for result in results:
        binding_p = result.diagnostics["p_value_normal_approx_bootstrap_se"]
        floor_p = result.diagnostics["p_value_empirical_bootstrap_floor_limited"]
        assert floor_p == pytest.approx(1 / 2001, abs=1e-4)
        assert binding_p <= floor_p  # the fix never makes a candidate look weaker than before
        g05 = next(g for g in result.report.gate_results if g.gate_id == GateId.MULTIPLICITY)
        if g05.satisfied:
            passing_candidates += 1
    # At least one real candidate's G05 must actually pass under the fixed method, given effects
    # this large and consistent — otherwise the "fix" would be untested against real data.
    assert passing_candidates > 0
