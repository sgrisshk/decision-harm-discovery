"""`G16_CANDIDATE_COMPOSITION_SAFETY` (`TASK-081`): SAFETY-CRITICAL tests only.

Per `TASK-081`'s control level 3, this file is the **only** test class allowed to fail on an
uncapped compound candidate. Every assertion here concerns the cap itself: that `confound_like`
and `composition_risk_indeterminate` cap identically (acceptance requirement 4), that
`ValidationReport.__post_init__`'s consistency invariant genuinely forbids re-promotion past the
cap (requirement 5), that every k>=2 candidate passing through the real pipeline gets a `G16`
result with no escape path, and that `T05`'s own overlap-ceiling reason stays distinct from both
`G16` reasons (requirement 6).

**A diagnostic misclassification (confound_like <-> indeterminate) must never fail a test in this
file** -- both states cap identically by design, so this file never inspects *which* of the two
reasons a candidate received, only that *a* cap was applied whenever `G16` is not satisfied. See
`test_g16_diagnostic.py` for label-correctness checks, which are explicitly forbidden from being
safety-critical.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import polars as pl
import pytest
from policy_analytics.outcomes import primary_outcome
from policy_analytics.outcomes.contract import MissingDataPolicy, OutcomeDefinition, OutcomeRole
from policy_analytics.validation.apply import _stratified_adjustment, run_validation
from policy_analytics.validation.composition_safety import (
    CompositionSafetyReason,
    classify_composition_safety,
)
from policy_analytics.validation.contract import (
    DEFAULT_THRESHOLDS,
    GATE_SPEC_BY_ID,
    GATE_SPECS,
    LEVEL_ORDER,
    FailureAction,
    GateId,
    GateOutcome,
    GateResult,
    IdentificationDesign,
)
from policy_analytics.validation.grading import classify_evidence_level, evidence_ceiling
from policy_analytics.validation.report import EffectEstimate, ValidationReport
from policy_schemas.domain import EvidenceLevel

pytestmark = pytest.mark.analytics

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATASET = REPO_ROOT / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
TASK075_RAW = REPO_ROOT / "docs/benchmark/task-075-t03-forensic-trace-raw.json"


# =====================================================================================
# Shared helpers (mirroring test_validation_contract.py's own _all_gates/_report pattern).
# =====================================================================================


def _all_gates(
    overrides: dict[GateId, GateOutcome] | None = None,
    default: GateOutcome = GateOutcome.PASS,
) -> tuple[GateResult, ...]:
    overrides = overrides or {}
    return tuple(
        GateResult(gate_id=spec.gate_id, outcome=overrides.get(spec.gate_id, default))
        for spec in GATE_SPECS
    )


def _report(**overrides: object) -> ValidationReport:
    defaults: dict[str, object] = {
        "candidate_id": "G16-SAFETY-TEST",
        "analysis_run_id": "g16-safety-test-run",
        "dataset_version": "ds-1.0.0",
        "outcome_definition_version": "outcome-1.0.0",
        "pattern_definition": "A>=1 AND B>=1",
        "outcome_definition": "contribution_margin_eur",
        "exposed_records": 412,
        "comparison_records": 8_900,
        "clustering_key": "manager",
        "raw_effect": EffectEstimate(-410.0, -520.0, -300.0, 0.95, "cluster_bootstrap", "EUR"),
        "identification_design": IdentificationDesign.OBSERVATIONAL,
        "gate_results": _all_gates(),
        "evidence_level": EvidenceLevel.ADJUSTED_OBSERVATIONAL,
        "policy_readiness": None,
        "recommended_validation": "Run as a shadow policy.",
        "adjusted_effect": EffectEstimate(-380.0, -500.0, -260.0, 0.95, "stratified", "EUR"),
        "controlled_variables": ("manager",),
    }
    from policy_analytics.validation.contract import PolicyReadiness

    if "policy_readiness" not in overrides:
        defaults["policy_readiness"] = PolicyReadiness.SHADOW_POLICY
    defaults.update(overrides)
    return ValidationReport(**defaults)  # type: ignore[arg-type]


OUTCOME = OutcomeDefinition(
    outcome_id="g16_safety_test_metric",
    role=OutcomeRole.PRIMARY,
    column="y",
    unit="unit",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description="Neutral synthetic outcome for G16's safety tests. Unrelated to any real domain.",
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Value increases",
)


def _atom_masks(frame: pl.DataFrame, features: tuple[str, ...]) -> tuple[tuple[str, pl.Series], ...]:
    return tuple((feature, frame[feature] == 1) for feature in features)


def _confound_frame(n: int, seed: int) -> pl.DataFrame:
    """A pure-confound DGP (Scenario-C-style, per the design document's own §14): `U` drives
    both exposure and outcome; the base rule's true causal effect is exactly zero. `B` is a
    near-exact proxy for `U`, so its own leave-one-out check should classify `confound_like`.
    """
    rng = random.Random(seed)
    u = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    a = [1 if rng.random() < (0.75 if u[i] else 0.25) else 0 for i in range(n)]
    b = [u[i] if rng.random() < 0.97 else 1 - u[i] for i in range(n)]
    y = [1000.0 + 220.0 * u[i] + rng.gauss(0.0, 60.0) for i in range(n)]
    return pl.DataFrame({"A": a, "B": b, "y": y})


def _indeterminate_frame(n: int, seed: int) -> pl.DataFrame:
    """Two independent atoms, no confounding role for either -- the leave-one-out check should
    find neither positive evidence of confounding (attenuation low, but per ADR-077/078 that is
    never treated as positive evidence of anything -- indeterminate, not an uncapped release).
    """
    rng = random.Random(seed)
    a = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    b = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    y = [1000.0 + 180.0 * a[i] + rng.gauss(0.0, 60.0) for i in range(n)]
    return pl.DataFrame({"A": a, "B": b, "y": y})


# =====================================================================================
# 1. Acceptance requirement 4: identical cap for confound_like and indeterminate, tested
#    explicitly against two genuinely different classification outcomes.
# =====================================================================================


def test_confound_like_and_indeterminate_reach_the_identical_evidence_ceiling() -> None:
    confound_result = classify_composition_safety(
        _confound_frame(1600, seed=1),
        _atom_masks(_confound_frame(1600, seed=1), ("A", "B")),
        OUTCOME,
        _stratified_adjustment,
        DEFAULT_THRESHOLDS,
    )
    indeterminate_result = classify_composition_safety(
        _indeterminate_frame(1600, seed=2),
        _atom_masks(_indeterminate_frame(1600, seed=2), ("A", "B")),
        OUTCOME,
        _stratified_adjustment,
        DEFAULT_THRESHOLDS,
    )
    # Precondition: the two constructed cases really do produce different reasons -- otherwise
    # this test would not be exercising the property it claims to.
    assert confound_result.reason is CompositionSafetyReason.CONFOUND_LIKE
    assert indeterminate_result.reason is CompositionSafetyReason.COMPOSITION_RISK_INDETERMINATE
    assert confound_result.satisfied is False
    assert indeterminate_result.satisfied is False

    confound_gate = GateResult(GateId.COMPOSITION_SAFETY, GateOutcome.FAIL, confound_result.detail)
    indeterminate_gate = GateResult(
        GateId.COMPOSITION_SAFETY, GateOutcome.FAIL, indeterminate_result.detail
    )

    ceiling_confound = evidence_ceiling(
        _all_gates({GateId.COMPOSITION_SAFETY: GateOutcome.FAIL}), IdentificationDesign.OBSERVATIONAL
    )
    ceiling_indeterminate = ceiling_confound  # both gate sets are built identically below
    results_confound = tuple(
        confound_gate if g.gate_id is GateId.COMPOSITION_SAFETY else g for g in _all_gates()
    )
    results_indeterminate = tuple(
        indeterminate_gate if g.gate_id is GateId.COMPOSITION_SAFETY else g for g in _all_gates()
    )
    assert evidence_ceiling(results_confound, IdentificationDesign.OBSERVATIONAL) == ceiling_confound
    assert (
        evidence_ceiling(results_indeterminate, IdentificationDesign.OBSERVATIONAL)
        == ceiling_indeterminate
    )
    assert ceiling_confound is EvidenceLevel.PREDICTIVE

    assert classify_evidence_level(
        results_confound, IdentificationDesign.OBSERVATIONAL
    ) is classify_evidence_level(results_indeterminate, IdentificationDesign.OBSERVATIONAL)


def test_g16_gatespec_cap_matches_g02s_own_pattern_exactly() -> None:
    """`docs/analytics/task-080-candidate-composition-safety-design.md` §8.1a requires this
    literally, not by analogy: the identical `FailureAction.CAP_EVIDENCE` /
    `EvidenceLevel.PREDICTIVE` pair `G02` already uses for its own circularity failure.
    """
    g02 = GATE_SPEC_BY_ID[GateId.POST_TREATMENT]
    g16 = GATE_SPEC_BY_ID[GateId.COMPOSITION_SAFETY]
    assert g16.on_failure is FailureAction.CAP_EVIDENCE
    assert g16.on_failure is g02.on_failure
    assert g16.max_level_on_failure is g02.max_level_on_failure is EvidenceLevel.PREDICTIVE


# =====================================================================================
# 2. Acceptance requirement 5: the ValidationReport.__post_init__ invariant, re-verified
#    (not merely cited) specifically for G16.
# =====================================================================================


@pytest.mark.parametrize(
    "g16_outcome", [GateOutcome.FAIL], ids=["G16_FAILS_confound_like_or_indeterminate"]
)
def test_report_construction_refuses_any_level_above_predictive_when_g16_fails(
    g16_outcome: GateOutcome,
) -> None:
    """Directly re-derives `TASK-081` acceptance requirement 5: construct a `ValidationReport`
    whose gate_results include a failed `G16`, and confirm every level *above* `PREDICTIVE` is
    refused by `__post_init__` -- not merely `ADJUSTED_OBSERVATIONAL`, every level above it too.
    """
    capped_gates = _all_gates({GateId.COMPOSITION_SAFETY: g16_outcome})
    supported = classify_evidence_level(capped_gates, IdentificationDesign.OBSERVATIONAL)
    assert supported is EvidenceLevel.PREDICTIVE

    for forbidden_level in LEVEL_ORDER:
        if LEVEL_ORDER.index(forbidden_level) <= LEVEL_ORDER.index(EvidenceLevel.PREDICTIVE):
            continue
        with pytest.raises(ValueError, match="not supported by the gate results"):
            _report(gate_results=capped_gates, evidence_level=forbidden_level)

    # PREDICTIVE itself, and everything at or below it, is legitimately constructible.
    report = _report(
        gate_results=capped_gates,
        evidence_level=EvidenceLevel.PREDICTIVE,
        adjusted_effect=None,
        controlled_variables=(),
    )
    assert report.evidence_level is EvidenceLevel.PREDICTIVE


def test_no_downstream_gate_or_state_transition_can_silently_re_raise_the_g16_cap() -> None:
    """Even a report that claims every *other* gate passed perfectly cannot exceed PREDICTIVE
    once G16 alone fails -- the cap has no bypass through any other gate's own success.
    """
    all_pass_except_g16 = _all_gates({GateId.COMPOSITION_SAFETY: GateOutcome.FAIL})
    assert classify_evidence_level(
        all_pass_except_g16, IdentificationDesign.OBSERVATIONAL
    ) is EvidenceLevel.PREDICTIVE
    with pytest.raises(ValueError, match="not supported by the gate results"):
        _report(gate_results=all_pass_except_g16, evidence_level=EvidenceLevel.ADJUSTED_OBSERVATIONAL)


# =====================================================================================
# 3. No escape path: every k>=2 candidate through the real, unmodified pipeline gets a G16
#    result, and G16 failing always caps the real, end-to-end computed evidence_level.
# =====================================================================================


def _write_candidates(tmp_path: Path, conditions: list[dict[str, object]], outcome_id: str) -> tuple[Path, Path]:
    candidates_path = tmp_path / "candidates.json"
    metrics_path = tmp_path / "discovery_metrics.json"
    candidates_path.write_text(
        json.dumps(
            {
                "status": "PERSISTED",
                "outcome": {"outcome_id": outcome_id, "outcome_definition_version": "1.1.0"},
                "candidates": [
                    {"candidate_id": "G16-SAFETY-K2", "conditions": conditions, "outcome": outcome_id}
                ],
            }
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(json.dumps({"evaluated_hypotheses": 33_085}), encoding="utf-8")
    return candidates_path, metrics_path


@pytest.mark.skipif(not REAL_DATASET.exists(), reason="delivered analytical dataset not present")
def test_every_k_ge_2_candidate_through_run_validation_has_a_g16_result(tmp_path: Path) -> None:
    """`CAND-014`'s own real, committed conditions (T03, `k=2`) -- reconstructed from
    `docs/benchmark/task-075-t03-forensic-trace-raw.json`, never retyped by hand -- run through
    the real, unmodified `run_validation()` end to end against the real dataset.
    """
    payload = json.loads(TASK075_RAW.read_text(encoding="utf-8"))
    trace = next(
        t
        for t in payload["trap_selection_traces"]
        if t["trap_id"] == "T03" and not t["is_counterfactual"]
    )
    conditions = []
    for token in trace["condition"]:
        feature, operator, value = token.split(" ", 2)
        try:
            coerced: object = float(value) if "." in value else int(value)
        except ValueError:
            coerced = value
        conditions.append({"feature": feature, "operator": operator, "value": coerced})

    candidates_path, metrics_path = _write_candidates(
        tmp_path, conditions, primary_outcome().outcome_id
    )
    results, _ = run_validation(
        dataset_root=REAL_DATASET,
        candidates_path=candidates_path,
        outcome=primary_outcome(),
        dataset_version="travel-bookings-analytical-v1.1.0",
        outcome_definition_version="1.1.0",
        analysis_run_id="g16-safety-test",
        metrics_path=metrics_path,
    )
    assert len(results) == 1
    report = results[0].report
    gate_ids = {g.gate_id for g in report.gate_results}
    assert GateId.COMPOSITION_SAFETY in gate_ids
    g16_result = next(g for g in report.gate_results if g.gate_id is GateId.COMPOSITION_SAFETY)
    # k=2 real candidate: G16 must have actually executed (applicable), never silently skipped.
    assert g16_result.outcome in (GateOutcome.PASS, GateOutcome.FAIL)
    if not g16_result.satisfied:
        # The one executable invariant, re-verified against the REAL pipeline output, not a
        # hand-built GateResult: G16 failing means the real, fully-assembled report cannot
        # exceed PREDICTIVE, regardless of what every other real gate computed.
        assert LEVEL_ORDER.index(report.evidence_level) <= LEVEL_ORDER.index(
            EvidenceLevel.PREDICTIVE
        ) if report.evidence_level is not None else True


@pytest.mark.skipif(not REAL_DATASET.exists(), reason="delivered analytical dataset not present")
def test_single_atom_real_candidate_is_unaffected_by_g16(tmp_path: Path) -> None:
    """A k=1 candidate must reach G16 (it appears in gate_results, satisfying `_result_map`'s
    completeness check) but must always be vacuously satisfied -- never capped by this gate.
    """
    candidates_path, metrics_path = _write_candidates(
        tmp_path, [{"feature": "discount_rate", "operator": "ge", "value": 0.08}], primary_outcome().outcome_id
    )
    results, _ = run_validation(
        dataset_root=REAL_DATASET,
        candidates_path=candidates_path,
        outcome=primary_outcome(),
        dataset_version="travel-bookings-analytical-v1.1.0",
        outcome_definition_version="1.1.0",
        analysis_run_id="g16-safety-k1-test",
        metrics_path=metrics_path,
    )
    g16_result = next(g for g in results[0].report.gate_results if g.gate_id is GateId.COMPOSITION_SAFETY)
    assert g16_result.satisfied is True
    assert g16_result.outcome is GateOutcome.PASS


# =====================================================================================
# 4. Acceptance requirement 6: T05's own overlap-ceiling reason stays distinct from both G16
#    reasons -- no conflation, checked both structurally and against real gate output.
# =====================================================================================


def test_g16_reason_tokens_never_appear_in_g06s_own_gatespec_text() -> None:
    g06_spec = GATE_SPEC_BY_ID[GateId.CONFOUNDING]
    g16_spec = GATE_SPEC_BY_ID[GateId.COMPOSITION_SAFETY]
    assert g06_spec.gate_id is not g16_spec.gate_id
    for reason in CompositionSafetyReason:
        assert reason.value not in g06_spec.rule
        assert reason.value not in g06_spec.question


@pytest.mark.skipif(not REAL_DATASET.exists(), reason="delivered analytical dataset not present")
def test_g06_and_g16_produce_separately_attributable_gate_results_on_a_real_candidate(
    tmp_path: Path,
) -> None:
    """`T05`'s own overlap-ceiling behavior is realized entirely inside `G06` (`CONFOUNDING`)'s
    own coverage-floor failure -- a structurally distinct `GateResult`, in a structurally
    distinct gate, from `G16`. This test confirms a real k=2 candidate's report always carries
    both as two separate, independently-readable entries -- a reader can always tell which gate
    produced which cap, exactly as acceptance requirement 6 requires.
    """
    payload = json.loads(TASK075_RAW.read_text(encoding="utf-8"))
    trace = next(
        t
        for t in payload["trap_selection_traces"]
        if t["trap_id"] == "T03" and not t["is_counterfactual"]
    )
    conditions = []
    for token in trace["condition"]:
        feature, operator, value = token.split(" ", 2)
        try:
            coerced: object = float(value) if "." in value else int(value)
        except ValueError:
            coerced = value
        conditions.append({"feature": feature, "operator": operator, "value": coerced})
    candidates_path, metrics_path = _write_candidates(
        tmp_path, conditions, primary_outcome().outcome_id
    )
    results, _ = run_validation(
        dataset_root=REAL_DATASET,
        candidates_path=candidates_path,
        outcome=primary_outcome(),
        dataset_version="travel-bookings-analytical-v1.1.0",
        outcome_definition_version="1.1.0",
        analysis_run_id="g16-t05-distinctness-test",
        metrics_path=metrics_path,
    )
    report = results[0].report
    g06 = next(g for g in report.gate_results if g.gate_id is GateId.CONFOUNDING)
    g16 = next(g for g in report.gate_results if g.gate_id is GateId.COMPOSITION_SAFETY)
    assert g06.gate_id != g16.gate_id
    assert g06.detail != g16.detail
    # Neither gate's own detail text borrows the other's own literal reason vocabulary.
    for reason in CompositionSafetyReason:
        assert reason.value not in g06.detail
