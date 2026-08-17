import pytest
from policy_analytics.outcomes import OUTCOME_BY_ID
from policy_analytics.validation.economic_impact import (
    ECONOMIC_IMPACT_CONTRACT_VERSION,
    EconomicImpactResult,
    build_economic_impact_result,
)
from policy_analytics.validation.report import EffectEstimate

pytestmark = pytest.mark.analytics


def _outcome():
    return OUTCOME_BY_ID["contribution_margin_eur"]


def test_build_economic_impact_result_matches_hand_computation() -> None:
    result = build_economic_impact_result(
        outcome=_outcome(),
        affected_records=142,
        per_record_value=998.35,
        per_record_ci_low=850.0,
        per_record_ci_high=1100.0,
        confidence_level=0.95,
        historical_value=141765.41,  # 998.35 * 142, matching HANDOFF-030's verified arithmetic
        historical_ci_low=120000.0,
        historical_ci_high=155000.0,
        materiality_pass=True,
    )
    assert result.impact_contract_version == ECONOMIC_IMPACT_CONTRACT_VERSION
    assert result.outcome_name == "contribution_margin_eur"
    assert result.affected_records == 142
    assert result.per_record_effect.value == pytest.approx(998.35)
    assert result.historical_impact.value == pytest.approx(141765.41)
    assert result.materiality_pass is True
    assert result.annualization_justified is False
    assert result.annualized_impact is None


def test_build_economic_impact_result_widens_intervals_to_contain_the_point_estimate() -> None:
    # Point estimate falls outside the raw percentile CI on both sides; the result must widen,
    # never narrow or drop the point, matching apply.py's identical treatment of dev_effect.
    result = build_economic_impact_result(
        outcome=_outcome(),
        affected_records=10,
        per_record_value=500.0,
        per_record_ci_low=100.0,
        per_record_ci_high=300.0,  # point (500) is above this
        confidence_level=0.95,
        historical_value=5000.0,
        historical_ci_low=6000.0,  # point (5000) is below this
        historical_ci_high=8000.0,
        materiality_pass=False,
    )
    assert result.per_record_effect.ci_low <= 500.0 <= result.per_record_effect.ci_high
    assert result.historical_impact.ci_low <= 5000.0 <= result.historical_impact.ci_high


def test_economic_impact_result_rejects_negative_affected_records() -> None:
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="affected_records"):
        EconomicImpactResult(
            impact_contract_version="1.0.0",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=-1,
            per_record_effect=estimate,
            historical_impact=estimate,
            annualization_justified=False,
            materiality_pass=False,
        )


def test_economic_impact_result_gates_annualized_impact_on_the_justified_flag() -> None:
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="annualized_impact must be present"):
        EconomicImpactResult(
            impact_contract_version="1.0.0",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=1,
            per_record_effect=estimate,
            historical_impact=estimate,
            annualization_justified=True,
            materiality_pass=False,
            annualized_impact=None,
        )


def test_economic_impact_result_v1_never_permits_annualization() -> None:
    # v1.0.0 has no exposure-rate-stability check implemented; annualization_justified=True must
    # be rejected outright even when an annualized_impact estimate is also supplied.
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="not implemented in contract v1.0.0"):
        EconomicImpactResult(
            impact_contract_version="1.0.0",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=1,
            per_record_effect=estimate,
            historical_impact=estimate,
            annualization_justified=True,
            materiality_pass=False,
            annualized_impact=estimate,
        )


def test_to_dict_round_trips_every_field() -> None:
    result = build_economic_impact_result(
        outcome=_outcome(),
        affected_records=5,
        per_record_value=100.0,
        per_record_ci_low=50.0,
        per_record_ci_high=150.0,
        confidence_level=0.95,
        historical_value=500.0,
        historical_ci_low=250.0,
        historical_ci_high=750.0,
        materiality_pass=True,
    )
    payload = result.to_dict()
    assert payload["impact_contract_version"] == ECONOMIC_IMPACT_CONTRACT_VERSION
    assert payload["affected_records"] == 5
    assert payload["per_record_effect"]["value"] == pytest.approx(100.0)
    assert payload["historical_impact"]["value"] == pytest.approx(500.0)
    assert payload["annualized_impact"] is None
    assert payload["annualization_justified"] is False
    assert payload["materiality_pass"] is True


def test_sign_convention_positive_means_harm_matches_outcome_contract() -> None:
    # A candidate more profitable than its comparison group (a legitimate, if unusual, outcome)
    # must show a negative historical_impact, not be clipped to zero or hidden.
    result = build_economic_impact_result(
        outcome=_outcome(),
        affected_records=10,
        per_record_value=-50.0,  # margin *increase* relative to comparison -> not harmful
        per_record_ci_low=-80.0,
        per_record_ci_high=-20.0,
        confidence_level=0.95,
        historical_value=-500.0,
        historical_ci_low=-800.0,
        historical_ci_high=-200.0,
        materiality_pass=False,
    )
    assert result.historical_impact.value < 0
    assert result.materiality_pass is False
