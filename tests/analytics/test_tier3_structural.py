"""`TASK-086` (implementing `TASK-085` §5.2 tier 3, `ADR-089`): the "always-empty slot" proof.

Mirrors `test_g16_structural.py`'s own discipline (`TASK-081`'s "no reachable third state"): this
file proves the *gating logic* -- never evidence_level, never any other proxy, only the real
`G13`/`G14` gate outcomes decide whether tier 3 (`O2`, attributable harmful impact) exists for a
candidate -- and separately proves that, given the real pipeline's own hardcoded `G13`/`G14`
outcomes (`apply.py`: both always `FAIL`), no candidate this project can currently produce ever
reaches a non-`None` tier 3. It contains no diagnostic-correctness assertion about what a real
identification design *would* estimate -- there is no such design in this codebase to test.
"""

from __future__ import annotations

import itertools

import pytest
from policy_analytics.outcomes import OUTCOME_BY_ID
from policy_analytics.validation.contract import GateId, GateOutcome, GateResult
from policy_analytics.validation.economic_impact import (
    AttributableImpactResult,
    MechanismPopulationEstimate,
    build_attributable_impact_result,
    tier3_identification_satisfied,
)
from policy_analytics.validation.report import EffectEstimate

pytestmark = pytest.mark.analytics

_EXCLUDED_TIER3_GATES = (GateId.IDENTIFICATION, GateId.RANDOMIZATION)
_ALL_OTHER_GATE_IDS = tuple(g for g in GateId if g not in _EXCLUDED_TIER3_GATES)


def _outcome():
    return OUTCOME_BY_ID["contribution_margin_eur"]


def _gate(gate_id: GateId, outcome: GateOutcome) -> GateResult:
    return GateResult(gate_id=gate_id, outcome=outcome, detail="synthetic test gate")


def _mechanism_population() -> MechanismPopulationEstimate:
    estimate = EffectEstimate(50.0, 30.0, 70.0, 0.95, "hypothetical_design_estimator", "EUR")
    return MechanismPopulationEstimate(
        affected_records=25,
        per_record_effect=estimate,
        attributable_impact=EffectEstimate(
            1250.0, 750.0, 1750.0, 0.95, "hypothetical_design_estimator", "EUR"
        ),
    )


# --- Exhaustive gate-outcome proof -----------------------------------------------------------


@pytest.mark.parametrize(
    "g13_outcome,g14_outcome",
    list(itertools.product(GateOutcome, GateOutcome)),
)
def test_tier3_identification_satisfied_depends_only_on_real_g13_g14_satisfaction(
    g13_outcome: GateOutcome, g14_outcome: GateOutcome
) -> None:
    """Exhaustive over every `GateOutcome` pair for G13 x G14 (`PASS`/`WARN`/`FAIL`/
    `NOT_EVALUATED`, 16 combinations): the result is non-`None` if and only if at least one of
    G13/G14 is `.satisfied` (`PASS` or `WARN`) -- never a function of any other gate, and never a
    function of anything but these two gates' own real outcomes.
    """
    gate_results = (
        _gate(GateId.IDENTIFICATION, g13_outcome),
        _gate(GateId.RANDOMIZATION, g14_outcome),
    )
    result = tier3_identification_satisfied(gate_results)

    g13_satisfied = g13_outcome in (GateOutcome.PASS, GateOutcome.WARN)
    g14_satisfied = g14_outcome in (GateOutcome.PASS, GateOutcome.WARN)

    if g13_satisfied:
        assert result is GateId.IDENTIFICATION
    elif g14_satisfied:
        assert result is GateId.RANDOMIZATION
    else:
        assert result is None


def test_tier3_identification_satisfied_ignores_every_other_gate() -> None:
    """Flipping every OTHER gate to PASS must never make tier 3 reachable -- only G13/G14 count."""
    gate_results = (
        *(_gate(g, GateOutcome.PASS) for g in _ALL_OTHER_GATE_IDS),
        _gate(GateId.IDENTIFICATION, GateOutcome.FAIL),
        _gate(GateId.RANDOMIZATION, GateOutcome.FAIL),
    )
    assert tier3_identification_satisfied(gate_results) is None


def test_tier3_identification_satisfied_returns_none_when_gates_absent() -> None:
    assert tier3_identification_satisfied(()) is None


# --- build_attributable_impact_result: the same guard, at the result-construction layer -------


def test_build_attributable_impact_result_returns_none_when_neither_gate_satisfied() -> None:
    gate_results = (
        _gate(GateId.IDENTIFICATION, GateOutcome.FAIL),
        _gate(GateId.RANDOMIZATION, GateOutcome.FAIL),
    )
    result = build_attributable_impact_result(
        gate_results=gate_results,
        outcome=_outcome(),
        mechanism_population=_mechanism_population(),
        materiality_pass=True,
    )
    assert result is None


def test_build_attributable_impact_result_returns_a_value_when_g13_genuinely_satisfied() -> None:
    """The mechanism itself is not dead code: given a hand-built `MechanismPopulationEstimate`
    (which nothing in the real pipeline can construct today) and gate results where G13 genuinely
    `PASS`es, the function does return a real, correctly-populated `AttributableImpactResult` --
    proving the gate check is a real precondition, not a permanently-false tautology.
    """
    gate_results = (
        _gate(GateId.IDENTIFICATION, GateOutcome.PASS),
        _gate(GateId.RANDOMIZATION, GateOutcome.FAIL),
    )
    population = _mechanism_population()
    result = build_attributable_impact_result(
        gate_results=gate_results,
        outcome=_outcome(),
        mechanism_population=population,
        materiality_pass=True,
    )
    assert isinstance(result, AttributableImpactResult)
    assert result.identification_gate is GateId.IDENTIFICATION
    assert result.affected_records == population.affected_records
    assert result.attributable_impact.value == pytest.approx(population.attributable_impact.value)


def test_build_attributable_impact_result_returns_a_value_when_g14_genuinely_satisfied() -> None:
    gate_results = (
        _gate(GateId.IDENTIFICATION, GateOutcome.FAIL),
        _gate(GateId.RANDOMIZATION, GateOutcome.WARN),
    )
    result = build_attributable_impact_result(
        gate_results=gate_results,
        outcome=_outcome(),
        mechanism_population=_mechanism_population(),
        materiality_pass=False,
    )
    assert isinstance(result, AttributableImpactResult)
    assert result.identification_gate is GateId.RANDOMIZATION


def test_attributable_impact_result_is_a_structurally_distinct_type() -> None:
    """`O1`/`O2` are never merged into one type (TASK-085 §0). `AttributableImpactResult` has no
    `population_scope`/`quantity_name`/`tier` fields matching `CandidateExposureResult`'s tiers
    1-2 shape, and a `CandidateExposureResult` cannot be constructed with `tier=3` (see
    `test_economic_impact.py::test_candidate_exposure_result_rejects_tier_outside_one_or_two`).
    """
    gate_results = (_gate(GateId.IDENTIFICATION, GateOutcome.PASS),)
    result = build_attributable_impact_result(
        gate_results=gate_results,
        outcome=_outcome(),
        mechanism_population=_mechanism_population(),
        materiality_pass=True,
    )
    assert result is not None
    from policy_analytics.validation.economic_impact import CandidateExposureResult

    assert not isinstance(result, CandidateExposureResult)
    payload = result.to_dict()
    assert payload["tier"] == 3
    assert payload["population_scope"] == "A"
    assert payload["quantity_name"] == "attributable_harmful_impact"


# The real pipeline's own proof that it can never reach tier 3 today lives in
# `test_validation_apply.py::test_tier3_attributable_impact_is_always_none_in_the_real_pipeline`,
# which runs the actual `run_validation` end to end (this file stays a pure unit-level proof of
# the gating *logic*, with no dependency on the real analytical dataset).
