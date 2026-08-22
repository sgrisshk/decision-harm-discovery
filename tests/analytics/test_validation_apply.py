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
    _adjustment_pool,
    _binned_adjustment_frame,
    _binned_group_label,
    _evaluated_hypotheses,
    _quantile_breakpoints,
    _select_adjustment_columns,
    _stratified_adjustment,
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
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS, GateId

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
    cells = cluster_cells(frame, mask, "outcome", "customer_id")
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

    adjusted_diff, coverage = _stratified_adjustment(frame, mask, outcome, ("manager",))
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
    adjusted_diff, coverage = _stratified_adjustment(frame, mask, outcome, ("manager",))
    assert adjusted_diff == pytest.approx(-30.0)
    assert coverage == pytest.approx(1.0)


# --- G06 generalization: adjustment-set selection (TASK-063, ADR-036/ADR-042) -------------------
#
# Synthetic fixtures only, deliberately neutral column names (never "manager"/"supplier"/
# "acquisition_channel" or any other real feature/trap identity) — this proves the *rule*
# generalizes, not that it was special-cased for one known trap.


def test_adjustment_pool_excludes_condition_features_from_manifest_eligibility() -> None:
    eligible = frozenset({"neutral_a", "neutral_b", "neutral_c"})
    pool = _adjustment_pool(eligible, frozenset({"neutral_b"}))
    assert "neutral_b" not in pool
    assert "neutral_a" in pool
    assert "neutral_c" in pool
    assert pool == tuple(sorted(pool))  # deterministic order


def test_quantile_breakpoints_split_a_known_list_into_even_thirds() -> None:
    values = list(range(1, 31))  # 1..30
    breakpoints = _quantile_breakpoints(values, bins=3)
    assert len(breakpoints) == 2
    # index-based, same convention as percentile_ci: cut near the 1/3 and 2/3 marks.
    assert breakpoints[0] == 11
    assert breakpoints[1] == 21


def test_binned_group_label_bins_a_high_cardinality_numeric_column() -> None:
    frame = pl.DataFrame({"spend": [float(i) for i in range(40)]})
    label = _binned_group_label(frame, "spend")
    assert label is not None
    assert label.n_unique() <= 4  # ADJUSTMENT_QUANTILE_BINS


def test_binned_group_label_passes_through_a_low_cardinality_numeric_column() -> None:
    frame = pl.DataFrame({"installments_like": [1, 2, 3, 4] * 10})
    assert _binned_group_label(frame, "installments_like") is None


def test_binned_group_label_passes_through_a_categorical_column() -> None:
    frame = pl.DataFrame({"channel_like": ["a", "b", "c"] * 10})
    assert _binned_group_label(frame, "channel_like") is None


def test_binned_adjustment_frame_only_touches_columns_that_need_binning() -> None:
    frame = pl.DataFrame(
        {
            "spend": [float(i) for i in range(40)],
            "channel_like": ["a", "b"] * 20,
        }
    )
    binned = _binned_adjustment_frame(frame, ("spend", "channel_like"))
    assert binned["spend"].n_unique() <= 4
    assert binned["channel_like"].to_list() == frame["channel_like"].to_list()


def _confounded_trap_fixture() -> tuple[pl.DataFrame, pl.Series]:
    """200 synthetic rows where `flag_feature` (the candidate's own condition — analogous to a
    trap's apparent_feature) has *zero* true direct effect on the outcome, but is disproportionately
    common when `real_confound == "hi"`, and `real_confound` alone fully determines the outcome
    (100.0 when "hi", 50.0 when "lo", no noise — deterministic so the adjusted result is exact, not
    approximate). `irrelevant_a`/`irrelevant_b` are present, low-cardinality, and genuinely
    unrelated to both `flag_feature` and the outcome — standing in for whatever a fixed, narrow,
    hand-picked adjustment pair might have been, to show that adjusting for *only* them does not
    catch this confound, while the general "every eligible covariate" selection does.
    """
    rows = []
    for i in range(200):
        real_confound = "hi" if i < 100 else "lo"
        flag = i % 3 == 0 if real_confound == "hi" else i % 10 == 0  # 34/100 vs 10/100 true
        outcome_value = 100.0 if real_confound == "hi" else 50.0
        rows.append(
            {
                "flag_feature": flag,
                "real_confound": real_confound,
                "irrelevant_a": "x" if i % 2 == 0 else "y",
                "irrelevant_b": "p" if i % 4 < 2 else "q",
                "contribution_margin_eur": outcome_value,
            }
        )
    frame = pl.DataFrame(rows)
    mask = frame["flag_feature"]
    return frame, mask


def test_a_fixed_narrow_adjustment_pair_does_not_catch_the_synthetic_confound() -> None:
    """The old-style failure mode: adjusting only for two columns that happen not to include the
    real confounder leaves the spurious raw association almost entirely intact.
    """
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    frame, mask = _confounded_trap_fixture()
    raw_diff, _ = _stratified_adjustment(frame, mask, outcome, ())
    assert raw_diff == pytest.approx(17.4825, abs=1e-3)  # real, meaningful spurious raw effect

    narrow_diff, narrow_coverage = _stratified_adjustment(
        frame, mask, outcome, ("irrelevant_a", "irrelevant_b")
    )
    assert narrow_coverage > 0  # strata are usable...
    assert narrow_diff == pytest.approx(raw_diff, abs=2.0)  # ...but the confound is still there


def test_select_adjustment_columns_discovers_a_confound_outside_a_narrow_fixed_guess() -> None:
    """The actual regression: given the full eligible pool (not told which column matters),
    `_select_adjustment_columns` finds and includes `real_confound`, and the resulting joint
    adjustment removes the spurious effect entirely — proving the *general* rule catches a
    confounder a fixed, hand-picked pair would have missed, without ever being told its name.
    """
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    frame, mask = _confounded_trap_fixture()
    pool = ("irrelevant_a", "irrelevant_b", "real_confound")

    selected = _select_adjustment_columns(
        frame, mask, outcome, pool, DEFAULT_THRESHOLDS.min_confounder_stratum_coverage
    )
    assert "real_confound" in selected

    adjusted_diff, coverage = _stratified_adjustment(frame, mask, outcome, selected)
    # Within each real_confound stratum the outcome is constant regardless of flag_feature, so the
    # confound-adjusted effect is exactly zero, not merely attenuated.
    assert adjusted_diff == pytest.approx(0.0, abs=1e-9)
    assert coverage >= DEFAULT_THRESHOLDS.min_confounder_stratum_coverage


def test_select_adjustment_columns_tries_lower_cardinality_columns_first() -> None:
    """Ascending-cardinality ordering, verified directly rather than only inferred from the result:
    a 2-level column must be selected before a 6-level column when both would otherwise fit,
    because the selection order itself (not just the outcome) is a claim this test makes.
    """
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    rows = []
    for i in range(120):
        rows.append(
            {
                "low_card": "a" if i % 2 == 0 else "b",
                "high_card": f"g{i % 6}",
                "contribution_margin_eur": 10.0 if i % 2 == 0 else 12.0,
            }
        )
    frame = pl.DataFrame(rows)
    mask = pl.Series([i % 3 == 0 for i in range(120)])
    binned = _binned_adjustment_frame(frame, ("low_card", "high_card"))
    selected = _select_adjustment_columns(
        binned, mask, outcome, ("high_card", "low_card"), min_coverage=0.0
    )
    assert selected.index("low_card") < selected.index("high_card")


def test_select_adjustment_columns_stops_before_coverage_collapses() -> None:
    """A column whose strata are too small to clear MIN_STRATUM_CELL on both sides must not be
    added even though it is in the pool — the greedy process should leave it out rather than let
    coverage collapse.
    """
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    # "sparse" has 40 distinct levels over 40 rows: every stratum has exactly 1 row, so no stratum
    # can ever clear MIN_STRATUM_CELL=5 on both sides once it's included.
    rows = [
        {
            "sparse": f"level_{i}",
            "contribution_margin_eur": 10.0 if i % 2 == 0 else 12.0,
        }
        for i in range(40)
    ]
    frame = pl.DataFrame(rows)
    mask = pl.Series([i % 2 == 0 for i in range(40)])
    selected = _select_adjustment_columns(
        frame, mask, outcome, ("sparse",), DEFAULT_THRESHOLDS.min_confounder_stratum_coverage
    )
    assert selected == ()


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
    # TASK-066 regression pin: manifest-owned roles must preserve the immediately preceding
    # validation-v1.2.0 travel behavior exactly. The v1.0.0 frozen dry-run report predates G05/G06
    # contract changes and is intentionally not the comparison baseline here.
    assert {result.candidate_id: result.verdict for result in results} == {
        "CAND-001": Verdict.DOWNGRADE,
        "CAND-002": Verdict.DOWNGRADE,
        "CAND-003": Verdict.DOWNGRADE,
        "CAND-004": Verdict.PASS,
        "CAND-005": Verdict.DOWNGRADE,
        "CAND-006": Verdict.DOWNGRADE,
        "CAND-007": Verdict.PASS,
        "CAND-008": Verdict.DOWNGRADE,
        "CAND-009": Verdict.PASS,
        "CAND-010": Verdict.PASS,
        "CAND-011": Verdict.DOWNGRADE,
        "CAND-012": Verdict.DOWNGRADE,
        "CAND-013": Verdict.DOWNGRADE,
        "CAND-014": Verdict.DOWNGRADE,
        "CAND-015": Verdict.PASS,
    }


# --- Blind-agent output schema compatibility (TASK-019 closing-run readiness) --------------------
#
# The blind pipeline (`blind/`, `tools/blind_agent/`) produces a materially different candidate
# document shape than the original discovery engine's `artifacts/discovery/task-015-candidates.json`
# (schema in `tools/blind_agent/models.py`, `OUTPUT_SCHEMA_VERSION = "1.1.0"`): no per-split
# breakdown on each candidate, and `evaluated_hypotheses` lives in a sibling
# `discovery_metrics.json`, not inline. These tests build a schema-*valid* document using the real
# Pydantic models (not a hand-typed guess at the shape) and run it through the same
# `run_validation` a closing run will use, so schema compatibility is verified before a real blind
# artifact exists, not discovered for the first time against one.


def _blind_schema_models():
    from tools.blind_agent.models import Candidate as BlindCandidate
    from tools.blind_agent.models import CandidatesDocument, MetricsDocument
    from tools.blind_agent.models import Condition as BlindCondition

    return BlindCandidate, CandidatesDocument, BlindCondition, MetricsDocument


def test_evaluated_hypotheses_reads_the_old_inline_shape() -> None:
    payload = {"search": {"evaluated_hypotheses": 6945}}
    assert _evaluated_hypotheses(payload, metrics_path=None) == 6945


def test_evaluated_hypotheses_reads_the_new_sibling_metrics_file(tmp_path: Path) -> None:
    metrics_path = tmp_path / "discovery_metrics.json"
    metrics_path.write_text(json.dumps({"evaluated_hypotheses": 4321}), encoding="utf-8")
    assert _evaluated_hypotheses({}, metrics_path=metrics_path) == 4321


def test_evaluated_hypotheses_raises_without_either_source() -> None:
    with pytest.raises(ValueError, match="evaluated_hypotheses"):
        _evaluated_hypotheses({}, metrics_path=None)


@pytest.mark.skipif(not REAL_DATASET.exists(), reason="delivered analytical dataset not present")
def test_run_validation_accepts_a_schema_valid_blind_agent_candidates_document(
    tmp_path: Path,
) -> None:
    """A schema-valid `CandidatesDocument` + `MetricsDocument`, built from the real Pydantic
    models the blind agent must satisfy, must parse and grade cleanly through `run_validation` —
    the same function a genuine closing run will use. This is a readiness check, not evidence:
    the candidate itself is synthetic and invented for this test, unrelated to any real pattern."""
    Candidate, CandidatesDocument, BlindCondition, MetricsDocument = _blind_schema_models()
    outcome = primary_outcome()

    manifest = json.loads((REAL_DATASET / "manifest.json").read_text(encoding="utf-8"))
    identity = manifest["dataset_identity_sha256"]

    condition = BlindCondition(feature="discount_rate", operator="ge", value=0.12)
    candidates = [
        Candidate(
            candidate_id=f"BLIND-{index:03d}",
            conditions=[condition],
            outcome=outcome.outcome_id,
            sample_size=1,  # not trusted by run_validation; recomputed from the dataset
            support=0.01,
            raw_effect=0.0,
            economic_exposure=0.0,
            discovery_method="test-fixture",
            description="synthetic test candidate; not a real discovery result",
        )
        for index in range(1, 11)  # CandidatesDocument requires 10-20 for PERSISTED
    ]
    document = CandidatesDocument(
        schema_version="1.1.0",
        run_id="test-run",
        status="PERSISTED",
        blind_bundle_id="a" * 64,
        run_contract_version="1.0.0",
        dataset_version=manifest["dataset_version"],
        dataset_identity_sha256=identity,
        outcome_contract_version="1.1.0",
        discovery_contract_version="1.1.0",
        discovery_method_version="test-fixture-1.0.0",
        search_fit_split="development",
        diagnostic_only_splits=["validation", "future_holdout"],
        selection_used_only_fit_split=True,
        input_provenance_hashes={},
        feature_timing_classes={},
        candidates=candidates,
    )
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(document.model_dump_json(), encoding="utf-8")

    metrics = MetricsDocument(
        schema_version="1.1.0",
        run_id="test-run",
        evaluated_hypotheses=500,
        random_seed=1,
        run_contract_version="1.0.0",
        dataset_identity_sha256=identity,
        discovery_method_version="test-fixture-1.0.0",
        search_fit_split="development",
        selection_used_only_fit_split=True,
    )
    metrics_path = tmp_path / "discovery_metrics.json"
    metrics_path.write_text(metrics.model_dump_json(), encoding="utf-8")

    results, run_manifest = run_validation(
        dataset_root=REAL_DATASET,
        candidates_path=candidates_path,
        outcome=outcome,
        dataset_version=manifest["dataset_version"],
        outcome_definition_version="1.1.0",
        analysis_run_id="schema-compat-test",
        metrics_path=metrics_path,
    )

    assert run_manifest["family_size"] == 500
    assert run_manifest["family_size_source"] == "metrics_path"
    assert len(results) == 10
    for result in results:
        assert result.verdict in (Verdict.PASS, Verdict.DOWNGRADE, Verdict.REJECT)
        assert {g.gate_id for g in result.report.gate_results} == set(GateId)


@pytest.mark.skipif(not REAL_DATASET.exists(), reason="delivered analytical dataset not present")
def test_run_validation_rejects_a_candidate_targeting_a_different_outcome(tmp_path: Path) -> None:
    Candidate, CandidatesDocument, BlindCondition, MetricsDocument = _blind_schema_models()
    outcome = primary_outcome()
    manifest = json.loads((REAL_DATASET / "manifest.json").read_text(encoding="utf-8"))

    wrong_outcome_candidate = Candidate(
        candidate_id="BLIND-999",
        conditions=[BlindCondition(feature="discount_rate", operator="ge", value=0.12)],
        outcome="gross_profit_eur",  # not the primary outcome this run is grading
        sample_size=1,
        support=0.01,
        raw_effect=0.0,
        economic_exposure=0.0,
        discovery_method="test-fixture",
        description="synthetic test candidate",
    )
    candidates = [wrong_outcome_candidate] * 10
    document = CandidatesDocument(
        schema_version="1.1.0",
        run_id="test-run",
        status="PERSISTED",
        blind_bundle_id="a" * 64,
        run_contract_version="1.0.0",
        dataset_version=manifest["dataset_version"],
        dataset_identity_sha256=manifest["dataset_identity_sha256"],
        outcome_contract_version="1.1.0",
        discovery_contract_version="1.1.0",
        discovery_method_version="test-fixture-1.0.0",
        search_fit_split="development",
        diagnostic_only_splits=["validation", "future_holdout"],
        selection_used_only_fit_split=True,
        input_provenance_hashes={},
        feature_timing_classes={},
        candidates=candidates,
    )
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(document.model_dump_json(), encoding="utf-8")
    metrics_path = tmp_path / "discovery_metrics.json"
    metrics_path.write_text(json.dumps({"evaluated_hypotheses": 500}), encoding="utf-8")

    with pytest.raises(ValueError, match="gross_profit_eur"):
        run_validation(
            dataset_root=REAL_DATASET,
            candidates_path=candidates_path,
            outcome=outcome,
            dataset_version=manifest["dataset_version"],
            outcome_definition_version="1.1.0",
            analysis_run_id="schema-compat-test",
            metrics_path=metrics_path,
        )


def test_run_validation_raises_a_clear_error_for_insufficient_candidates(tmp_path: Path) -> None:
    payload = {
        "status": "INSUFFICIENT_CANDIDATES",
        "insufficiency_reason": "fewer than 10 candidates qualified",
        "candidates": [],
    }
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="INSUFFICIENT_CANDIDATES"):
        run_validation(
            dataset_root=REAL_DATASET,
            candidates_path=candidates_path,
            outcome=primary_outcome(),
            dataset_version="x",
            outcome_definition_version="1.1.0",
            analysis_run_id="x",
        )
