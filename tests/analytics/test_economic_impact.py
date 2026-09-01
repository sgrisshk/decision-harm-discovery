"""`TASK-086` (implementing `TASK-085`'s design, `ADR-089`): the `O1`-honest exposure ladder.

Tier 1 tests reproduce the pre-rename `v1.0.0` numbers exactly (unchanged computation, renamed
fields only). Tier 2 tests are the `ADR-089` Check 3 regression proof: `E_dev`'s own count, never
the combined-window `exposed_total`. Migration tests prove a legacy `v1.x` payload still parses,
under its own recorded version, as exactly what `TASK-085` §7 says it always was.
"""

import pytest
from policy_analytics.outcomes import OUTCOME_BY_ID
from policy_analytics.validation.economic_impact import (
    ECONOMIC_IMPACT_CONTRACT_VERSION,
    LEGACY_ECONOMIC_IMPACT_CONTRACT_VERSION,
    CandidateExposureResult,
    EconomicImpactResult,
    build_candidate_exposure_result_tier1,
    build_candidate_exposure_result_tier2,
    build_economic_impact_result,
    load_candidate_exposure_result,
)
from policy_analytics.validation.report import EffectEstimate

pytestmark = pytest.mark.analytics


def _outcome():
    return OUTCOME_BY_ID["contribution_margin_eur"]


# --- Tier 1 ---------------------------------------------------------------------------------


def test_build_tier1_matches_hand_computation() -> None:
    result = build_candidate_exposure_result_tier1(
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
    assert result.exposure_contract_version == ECONOMIC_IMPACT_CONTRACT_VERSION
    assert result.tier == 1
    assert result.population_scope == "E"
    assert result.quantity_name == "candidate_exposure"
    assert result.outcome_name == "contribution_margin_eur"
    assert result.affected_records == 142
    assert result.per_record_effect.value == pytest.approx(998.35)
    assert result.candidate_exposure.value == pytest.approx(141765.41)
    assert result.materiality_pass is True
    assert result.annualization_justified is False
    assert result.annualized_candidate_exposure is None


def test_build_tier1_widens_intervals_to_contain_the_point_estimate() -> None:
    # Point estimate falls outside the raw percentile CI on both sides; the result must widen,
    # never narrow or drop the point, matching apply.py's identical treatment of dev_effect.
    result = build_candidate_exposure_result_tier1(
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
    assert result.candidate_exposure.ci_low <= 5000.0 <= result.candidate_exposure.ci_high


def test_candidate_exposure_result_rejects_negative_affected_records() -> None:
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="affected_records"):
        CandidateExposureResult(
            exposure_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
            tier=1,
            population_scope="E",
            quantity_name="candidate_exposure",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=-1,
            per_record_effect=estimate,
            candidate_exposure=estimate,
            annualization_justified=False,
            materiality_pass=False,
        )


def test_candidate_exposure_result_rejects_tier_outside_one_or_two() -> None:
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="tier"):
        CandidateExposureResult(
            exposure_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
            tier=3,
            population_scope="A",
            quantity_name="attributable_harmful_impact",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=1,
            per_record_effect=estimate,
            candidate_exposure=estimate,
            annualization_justified=False,
            materiality_pass=False,
        )


def test_candidate_exposure_result_rejects_tier1_labeled_as_e_dev() -> None:
    # A caller must not be able to silently mint a "tier 1" result over the tier-2 population
    # label, or vice versa -- the population_scope/quantity_name must match the declared tier.
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="tier 1 population_scope"):
        CandidateExposureResult(
            exposure_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
            tier=1,
            population_scope="E_dev",
            quantity_name="candidate_exposure",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=1,
            per_record_effect=estimate,
            candidate_exposure=estimate,
            annualization_justified=False,
            materiality_pass=False,
        )


def test_candidate_exposure_result_rejects_tier2_labeled_as_e() -> None:
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="tier 2 population_scope"):
        CandidateExposureResult(
            exposure_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
            tier=2,
            population_scope="E",
            quantity_name="adjustment_consistent_candidate_exposure_dev_scope",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=1,
            per_record_effect=estimate,
            candidate_exposure=estimate,
            annualization_justified=False,
            materiality_pass=False,
        )


def test_candidate_exposure_result_gates_annualized_exposure_on_the_justified_flag() -> None:
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="annualized_candidate_exposure must be present"):
        CandidateExposureResult(
            exposure_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
            tier=1,
            population_scope="E",
            quantity_name="candidate_exposure",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=1,
            per_record_effect=estimate,
            candidate_exposure=estimate,
            annualization_justified=True,
            materiality_pass=False,
            annualized_candidate_exposure=None,
        )


def test_candidate_exposure_result_never_permits_annualization() -> None:
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="annualization is not implemented"):
        CandidateExposureResult(
            exposure_contract_version=ECONOMIC_IMPACT_CONTRACT_VERSION,
            tier=1,
            population_scope="E",
            quantity_name="candidate_exposure",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=1,
            per_record_effect=estimate,
            candidate_exposure=estimate,
            annualization_justified=True,
            materiality_pass=False,
            annualized_candidate_exposure=estimate,
        )


def test_tier1_to_dict_round_trips_every_field() -> None:
    result = build_candidate_exposure_result_tier1(
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
    assert payload["exposure_contract_version"] == ECONOMIC_IMPACT_CONTRACT_VERSION
    assert payload["tier"] == 1
    assert payload["population_scope"] == "E"
    assert payload["affected_records"] == 5
    assert payload["per_record_effect"]["value"] == pytest.approx(100.0)
    assert payload["candidate_exposure"]["value"] == pytest.approx(500.0)
    assert payload["annualized_candidate_exposure"] is None
    assert payload["annualization_justified"] is False
    assert payload["materiality_pass"] is True


def test_sign_convention_positive_means_harm_matches_outcome_contract() -> None:
    # A candidate more profitable than its comparison group (a legitimate, if unusual, outcome)
    # must show a negative candidate_exposure, not be clipped to zero or hidden.
    result = build_candidate_exposure_result_tier1(
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
    assert result.candidate_exposure.value < 0
    assert result.materiality_pass is False


# --- Tier 2 -----------------------------------------------------------------------------------


def test_build_tier2_reuses_adjusted_effect_without_recomputation() -> None:
    adjusted_effect = EffectEstimate(120.0, 90.0, 150.0, 0.95, "stratified_generalized_adjustment", "EUR")
    result = build_candidate_exposure_result_tier2(
        outcome=_outcome(),
        dev_exposed_records=200,
        adjusted_effect=adjusted_effect,
        materiality_pass=True,
    )
    assert result.tier == 2
    assert result.population_scope == "E_dev"
    assert result.quantity_name == "adjustment_consistent_candidate_exposure_dev_scope"
    assert result.affected_records == 200
    # per_record_effect is exactly G06's own adjusted_effect -- not recomputed.
    assert result.per_record_effect.value == pytest.approx(120.0)
    assert result.per_record_effect.ci_low == pytest.approx(90.0)
    assert result.per_record_effect.ci_high == pytest.approx(150.0)


def test_tier2_uses_e_dev_not_combined_exposed_total() -> None:
    """The `ADR-089` Check 3 regression proof at the builder level: construct a scenario where
    the development-only population (`E_dev`, 50 records) and a wider combined-window population
    (`E`, 500 records) genuinely differ, and confirm the aggregated `candidate_exposure` uses only
    the `E_dev` count passed in -- never a wider count the caller might have (incorrectly) also
    had lying around.
    """
    adjusted_effect = EffectEstimate(10.0, 8.0, 12.0, 0.95, "stratified_generalized_adjustment", "EUR")
    dev_exposed_records = 50
    combined_exposed_records = 500  # deliberately different and much larger

    result = build_candidate_exposure_result_tier2(
        outcome=_outcome(),
        dev_exposed_records=dev_exposed_records,
        adjusted_effect=adjusted_effect,
        materiality_pass=True,
    )

    correct_value = adjusted_effect.value * dev_exposed_records  # 500.0
    wrong_value_if_combined_used = adjusted_effect.value * combined_exposed_records  # 5000.0

    assert result.affected_records == dev_exposed_records
    assert result.candidate_exposure.value == pytest.approx(correct_value)
    assert result.candidate_exposure.value != pytest.approx(wrong_value_if_combined_used)


def test_tier2_interval_scales_linearly_with_e_dev_and_widens_to_contain_the_point() -> None:
    adjusted_effect = EffectEstimate(-40.0, -60.0, -20.0, 0.95, "stratified_generalized_adjustment", "EUR")
    result = build_candidate_exposure_result_tier2(
        outcome=_outcome(),
        dev_exposed_records=25,
        adjusted_effect=adjusted_effect,
        materiality_pass=False,
    )
    assert result.candidate_exposure.value == pytest.approx(-1000.0)
    assert result.candidate_exposure.ci_low <= result.candidate_exposure.value
    assert result.candidate_exposure.value <= result.candidate_exposure.ci_high
    assert result.candidate_exposure.ci_low == pytest.approx(-1500.0)
    assert result.candidate_exposure.ci_high == pytest.approx(-500.0)


# --- Migration / backward compatibility ---------------------------------------------------


def test_load_legacy_v1_payload_parses_as_tier1_under_its_own_version() -> None:
    """A pre-`TASK-086` `v1.0.0` payload (`impact_contract_version`/`historical_impact`) — the
    exact shape `EconomicImpactResult.to_dict()` used to emit — must still parse, under its own
    recorded version, never re-graded and never silently reinterpreted as a new tier.
    """
    legacy_payload = {
        "impact_contract_version": LEGACY_ECONOMIC_IMPACT_CONTRACT_VERSION,
        "outcome_name": "contribution_margin_eur",
        "outcome_unit": "EUR",
        "affected_records": 142,
        "per_record_effect": {
            "value": 998.35,
            "ci_low": 850.0,
            "ci_high": 1100.0,
            "confidence_level": 0.95,
            "method": "cluster_bootstrap_customer_id_combined_window",
            "unit": "EUR",
        },
        "historical_impact": {
            "value": 141765.41,
            "ci_low": 120000.0,
            "ci_high": 155000.0,
            "confidence_level": 0.95,
            "method": "cluster_bootstrap_customer_id_combined_window",
            "unit": "EUR",
        },
        "annualized_impact": None,
        "annualization_justified": False,
        "materiality_pass": True,
    }

    result = load_candidate_exposure_result(legacy_payload)

    # Its own recorded version is preserved verbatim -- not upgraded, not rewritten.
    assert result.exposure_contract_version == LEGACY_ECONOMIC_IMPACT_CONTRACT_VERSION
    assert result.exposure_contract_version != ECONOMIC_IMPACT_CONTRACT_VERSION
    # Interpreted as exactly tier 1's own quantity (TASK-085 §7's stated equivalence).
    assert result.tier == 1
    assert result.population_scope == "E"
    assert result.affected_records == 142
    assert result.candidate_exposure.value == pytest.approx(141765.41)
    assert result.per_record_effect.value == pytest.approx(998.35)
    assert result.materiality_pass is True


def test_load_v2_payload_round_trips() -> None:
    built = build_candidate_exposure_result_tier1(
        outcome=_outcome(),
        affected_records=7,
        per_record_value=100.0,
        per_record_ci_low=90.0,
        per_record_ci_high=110.0,
        confidence_level=0.95,
        historical_value=700.0,
        historical_ci_low=630.0,
        historical_ci_high=770.0,
        materiality_pass=True,
    )
    loaded = load_candidate_exposure_result(built.to_dict())
    assert loaded == built


def test_load_v2_tier2_payload_round_trips() -> None:
    adjusted_effect = EffectEstimate(10.0, 8.0, 12.0, 0.95, "stratified_generalized_adjustment", "EUR")
    built = build_candidate_exposure_result_tier2(
        outcome=_outcome(),
        dev_exposed_records=50,
        adjusted_effect=adjusted_effect,
        materiality_pass=True,
    )
    loaded = load_candidate_exposure_result(built.to_dict())
    assert loaded == built
    assert loaded.tier == 2
    assert loaded.population_scope == "E_dev"


def test_load_payload_without_any_recognized_version_key_raises() -> None:
    with pytest.raises(ValueError, match="cannot determine which contract version"):
        load_candidate_exposure_result({"some_unrelated_key": True})


# --- Backward-compatible aliases (TASK-084's frozen forensic scripts) -----------------------


def test_legacy_alias_names_still_resolve_and_stay_readable() -> None:
    assert EconomicImpactResult is CandidateExposureResult
    assert build_economic_impact_result is build_candidate_exposure_result_tier1

    result = build_economic_impact_result(
        outcome=_outcome(),
        affected_records=1,
        per_record_value=10.0,
        per_record_ci_low=5.0,
        per_record_ci_high=15.0,
        confidence_level=0.95,
        historical_value=10.0,
        historical_ci_low=5.0,
        historical_ci_high=15.0,
        materiality_pass=False,
    )
    # Deprecated attribute-read aliases, used by scripts/review_task084_*.py /
    # scripts/diagnose_task084_branch4_controls.py (TASK-084 frozen forensic artifacts).
    assert result.historical_impact is result.candidate_exposure
    assert result.impact_contract_version == result.exposure_contract_version
    assert result.annualized_impact is result.annualized_candidate_exposure
