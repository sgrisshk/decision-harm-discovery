import pytest
from policy_analytics.validation import (
    CONTRACT_VERSION,
    GATE_SPECS,
    LEVEL_ORDER,
    LEVEL_REQUIREMENTS,
    EffectEstimate,
    FailureAction,
    GateId,
    GateOutcome,
    GateResult,
    IdentificationDesign,
    PolicyReadiness,
    ValidationReport,
    ValidationThresholds,
    assign_policy_readiness,
    benjamini_hochberg_adjusted,
    bootstrap_two_sided_p,
    classify_evidence_level,
    evidence_ceiling,
    survives_fdr,
)
from policy_schemas.domain import EvidenceLevel

pytestmark = pytest.mark.analytics


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
        "candidate_id": "C-001",
        "analysis_run_id": "run-001",
        "dataset_version": "ds-1.0.0",
        "outcome_definition_version": "outcome-1.0.0",
        "pattern_definition": "supplier=BlueWing AND discount_rate>=0.12",
        "outcome_definition": "contribution_margin_eur",
        "exposed_records": 412,
        "comparison_records": 8_900,
        "clustering_key": "manager",
        "raw_effect": EffectEstimate(-410.0, -520.0, -300.0, 0.95, "cluster_bootstrap", "EUR"),
        "identification_design": IdentificationDesign.OBSERVATIONAL,
        "gate_results": _all_gates(),
        "evidence_level": EvidenceLevel.ADJUSTED_OBSERVATIONAL,
        "policy_readiness": PolicyReadiness.SHADOW_POLICY,
        "recommended_validation": "Run a shadow policy for one quarter before enforcement.",
        "adjusted_effect": EffectEstimate(-355.0, -470.0, -240.0, 0.95, "stratified", "EUR"),
        "controlled_variables": ("destination", "booking_lead_days", "booking_month"),
    }
    return ValidationReport(**(defaults | overrides))  # type: ignore[arg-type]


def test_gate_specification_is_internally_consistent() -> None:
    ids = [spec.gate_id for spec in GATE_SPECS]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(GateId)
    for spec in GATE_SPECS:
        capped = spec.on_failure is FailureAction.CAP_EVIDENCE
        assert capped == (spec.max_level_on_failure is not None)

    graded = set().union(*LEVEL_REQUIREMENTS.values())
    readiness_only = {
        spec.gate_id for spec in GATE_SPECS if spec.on_failure is FailureAction.READINESS_ONLY
    }
    assert graded | readiness_only == set(GateId)
    assert graded.isdisjoint(readiness_only)
    assert LEVEL_REQUIREMENTS[EvidenceLevel.EXPERIMENTAL] == graded


def test_thresholds_reject_incoherent_configuration() -> None:
    assert ValidationThresholds().version == CONTRACT_VERSION
    with pytest.raises(ValueError, match="min_exposed_records"):
        ValidationThresholds(min_exposed_records=10)
    with pytest.raises(ValueError, match="power_target"):
        ValidationThresholds(power_target=0.4)
    with pytest.raises(ValueError, match="bootstrap_resamples"):
        ValidationThresholds(bootstrap_resamples=200)
    with pytest.raises(ValueError, match="fdr_alpha"):
        ValidationThresholds(fdr_alpha=1.0)


def test_benjamini_hochberg_matches_hand_computed_values() -> None:
    # Ranks 1..4 give 0.04, 0.06, 0.0533, 0.20; the step-up minimum drags rank 2 down to 0.0533.
    adjusted = benjamini_hochberg_adjusted([0.01, 0.04, 0.03, 0.20])
    assert adjusted == pytest.approx((0.04, 0.16 / 3, 0.16 / 3, 0.20))
    assert survives_fdr(adjusted, 0.10) == (True, True, True, False)
    assert benjamini_hochberg_adjusted([]) == ()


def test_family_size_penalises_the_unreported_search_space() -> None:
    reported = benjamini_hochberg_adjusted([0.001, 0.02])
    searched = benjamini_hochberg_adjusted([0.001, 0.02], family_size=500)
    assert searched[0] > reported[0]
    assert survives_fdr(searched, 0.10) == (False, False)
    with pytest.raises(ValueError, match="family_size"):
        benjamini_hochberg_adjusted([0.1, 0.2], family_size=1)
    with pytest.raises(ValueError, match="p-values"):
        benjamini_hochberg_adjusted([1.4])


def test_bootstrap_p_value_is_symmetric_and_floored() -> None:
    replicates = [-3.0] * 990 + [1.0] * 10
    assert bootstrap_two_sided_p(replicates) == pytest.approx(0.02)
    assert bootstrap_two_sided_p([-1.0 * value for value in replicates]) == pytest.approx(0.02)
    assert bootstrap_two_sided_p([-1.0] * 1000) == pytest.approx(1 / 1001)
    assert bootstrap_two_sided_p([0.0] * 100) == 1.0
    with pytest.raises(ValueError, match="replicate"):
        bootstrap_two_sided_p([])


def test_observational_data_can_never_exceed_adjusted_observational() -> None:
    results = _all_gates()
    assert classify_evidence_level(results, IdentificationDesign.OBSERVATIONAL) is (
        EvidenceLevel.ADJUSTED_OBSERVATIONAL
    )
    assert classify_evidence_level(results, IdentificationDesign.QUASI_EXPERIMENTAL) is (
        EvidenceLevel.QUASI_CAUSAL
    )
    assert classify_evidence_level(results, IdentificationDesign.RANDOMIZED_PROSPECTIVE) is (
        EvidenceLevel.EXPERIMENTAL
    )


def test_leakage_and_survivorship_failures_reject_the_candidate() -> None:
    for gate in (GateId.TARGET_LEAKAGE, GateId.SURVIVORSHIP, GateId.LINEAGE):
        results = _all_gates({gate: GateOutcome.FAIL})
        assert evidence_ceiling(results, IdentificationDesign.RANDOMIZED_PROSPECTIVE) is None
        assert classify_evidence_level(results, IdentificationDesign.OBSERVATIONAL) is None


@pytest.mark.parametrize(
    ("failed_gate", "expected"),
    [
        (GateId.CONFOUNDING, EvidenceLevel.PREDICTIVE),
        (GateId.POST_TREATMENT, EvidenceLevel.PREDICTIVE),
        (GateId.SELECTION_COLLIDER, EvidenceLevel.PREDICTIVE),
        (GateId.SEASONALITY, EvidenceLevel.PREDICTIVE),
        (GateId.SIMPSON, EvidenceLevel.DESCRIPTIVE),
        (GateId.TEMPORAL_STABILITY, EvidenceLevel.DESCRIPTIVE),
        (GateId.MULTIPLICITY, EvidenceLevel.DESCRIPTIVE),
        (GateId.SAMPLE, EvidenceLevel.DESCRIPTIVE),
        (GateId.UNCERTAINTY, EvidenceLevel.DESCRIPTIVE),
        (GateId.ROBUSTNESS, EvidenceLevel.DESCRIPTIVE),
    ],
)
def test_each_bias_gate_downgrades_to_its_declared_ceiling(
    failed_gate: GateId, expected: EvidenceLevel
) -> None:
    results = _all_gates({failed_gate: GateOutcome.FAIL})
    assert classify_evidence_level(results, IdentificationDesign.OBSERVATIONAL) is expected


def test_unevaluated_gate_is_not_a_passed_gate() -> None:
    results = _all_gates({GateId.CONFOUNDING: GateOutcome.NOT_EVALUATED})
    assert classify_evidence_level(results, IdentificationDesign.OBSERVATIONAL) is (
        EvidenceLevel.PREDICTIVE
    )


def test_warnings_do_not_change_the_level_but_are_reported() -> None:
    results = _all_gates({GateId.SEASONALITY: GateOutcome.WARN})
    assert classify_evidence_level(results, IdentificationDesign.OBSERVATIONAL) is (
        EvidenceLevel.ADJUSTED_OBSERVATIONAL
    )
    report = _report(gate_results=results)
    assert any(GateId.SEASONALITY.value in warning for warning in report.warnings)


def test_incomplete_gate_coverage_is_an_error() -> None:
    partial = tuple(result for result in _all_gates() if result.gate_id is not GateId.ROBUSTNESS)
    with pytest.raises(ValueError, match="missing gate results"):
        classify_evidence_level(partial, IdentificationDesign.OBSERVATIONAL)
    duplicated = (*_all_gates(), GateResult(GateId.SAMPLE, GateOutcome.PASS))
    with pytest.raises(ValueError, match="duplicate gate result"):
        classify_evidence_level(duplicated, IdentificationDesign.OBSERVATIONAL)


def test_policy_readiness_matrix() -> None:
    passing = _all_gates()
    immaterial = _all_gates({GateId.ECONOMIC_MATERIALITY: GateOutcome.FAIL})

    assert (
        assign_policy_readiness(
            EvidenceLevel.ADJUSTED_OBSERVATIONAL, immaterial, operationally_feasible=True
        )
        is PolicyReadiness.NOT_READY
    )
    assert (
        assign_policy_readiness(None, passing, operationally_feasible=True)
        is PolicyReadiness.NOT_READY
    )
    assert (
        assign_policy_readiness(EvidenceLevel.PREDICTIVE, passing, operationally_feasible=True)
        is PolicyReadiness.EXPERIMENT_ONLY
    )
    assert (
        assign_policy_readiness(
            EvidenceLevel.ADJUSTED_OBSERVATIONAL, passing, operationally_feasible=True
        )
        is PolicyReadiness.SHADOW_POLICY
    )
    assert (
        assign_policy_readiness(
            EvidenceLevel.ADJUSTED_OBSERVATIONAL, passing, operationally_feasible=False
        )
        is PolicyReadiness.EXPERIMENT_ONLY
    )
    assert (
        assign_policy_readiness(EvidenceLevel.QUASI_CAUSAL, passing, operationally_feasible=True)
        is PolicyReadiness.SHADOW_POLICY
    )
    assert (
        assign_policy_readiness(
            EvidenceLevel.QUASI_CAUSAL,
            passing,
            operationally_feasible=True,
            backtest_net_positive=True,
        )
        is PolicyReadiness.HIGH_CONFIDENCE
    )


def test_report_refuses_a_level_its_gates_do_not_support() -> None:
    downgraded = _all_gates({GateId.CONFOUNDING: GateOutcome.FAIL})
    with pytest.raises(ValueError, match="not supported by the gate results"):
        _report(gate_results=downgraded)

    with pytest.raises(ValueError, match="not supported by the gate results"):
        _report(
            identification_design=IdentificationDesign.OBSERVATIONAL,
            evidence_level=EvidenceLevel.QUASI_CAUSAL,
        )


def test_report_requires_adjustment_evidence_for_adjusted_levels() -> None:
    with pytest.raises(ValueError, match="adjusted effect estimate"):
        _report(adjusted_effect=None)
    with pytest.raises(ValueError, match="controlled variables"):
        _report(controlled_variables=())


def test_rejected_candidate_cannot_carry_readiness() -> None:
    rejected = _all_gates({GateId.TARGET_LEAKAGE: GateOutcome.FAIL})
    with pytest.raises(ValueError, match="rejected candidate"):
        _report(
            gate_results=rejected,
            evidence_level=None,
            policy_readiness=PolicyReadiness.SHADOW_POLICY,
        )
    report = _report(
        gate_results=rejected,
        evidence_level=None,
        policy_readiness=PolicyReadiness.NOT_READY,
        adjusted_effect=None,
        controlled_variables=(),
    )
    assert report.permitted_language.startswith("Rejected candidate")
    assert report.to_dict()["evidence_level"] is None


def test_estimates_require_a_containing_interval() -> None:
    with pytest.raises(ValueError, match="inside its interval"):
        EffectEstimate(-410.0, -300.0, -520.0, 0.95, "cluster_bootstrap", "EUR")
    with pytest.raises(ValueError, match="method and a unit"):
        EffectEstimate(-410.0, -520.0, -300.0, 0.95, "", "EUR")
    assert EffectEstimate(-410.0, -520.0, -300.0, 0.95, "b", "EUR").excludes_zero
    assert not EffectEstimate(-410.0, -520.0, 40.0, 0.95, "b", "EUR").excludes_zero


def test_report_language_never_exceeds_the_evidence_level() -> None:
    report = _report()
    assert "unmeasured confounding" in report.permitted_language
    payload = report.to_dict()
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["evidence_level"] == EvidenceLevel.ADJUSTED_OBSERVATIONAL.value
    assert payload["permitted_language"] == report.permitted_language
    assert LEVEL_ORDER.index(EvidenceLevel.ADJUSTED_OBSERVATIONAL) < LEVEL_ORDER.index(
        EvidenceLevel.QUASI_CAUSAL
    )
