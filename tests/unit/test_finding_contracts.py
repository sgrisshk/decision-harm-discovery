from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.findings.contracts import (
    AttributableImpactPersistence,
    CandidateExposureTierPersistence,
    CandidateMetric,
    CandidatePatternPersistence,
    EconomicImpactPersistence,
    EffectEstimatePersistence,
    FindingPromotion,
    GateResultPersistence,
    LineageReference,
    PatternCondition,
    ValidationMetadataPersistence,
)
from policy_analytics.validation.contract import (
    GateId,
    GateOutcome,
    IdentificationDesign,
    PolicyReadiness,
)
from policy_analytics.validation.economic_impact import (
    TIER_1_POPULATION_SCOPE,
    TIER_1_QUANTITY_NAME,
    TIER_2_POPULATION_SCOPE,
    TIER_2_QUANTITY_NAME,
)
from policy_schemas.domain import EvidenceLevel
from pydantic import ValidationError

SHA = "a" * 64


def _effect() -> EffectEstimatePersistence:
    return EffectEstimatePersistence(
        value=-10, ci_low=-15, ci_high=-5, confidence_level=0.95, method="bootstrap", unit="EUR"
    )


def _validation(evidence: EvidenceLevel | None) -> ValidationMetadataPersistence:
    return ValidationMetadataPersistence(
        contract_version="1.0.0",
        outcome_definition_version="1.1.0",
        outcome_definition="contribution_margin_eur",
        exposed_records=100,
        comparison_records=900,
        clustering_key="customer_id",
        raw_effect=_effect(),
        identification_design=IdentificationDesign.OBSERVATIONAL,
        gate_results=(
            GateResultPersistence(
                gate_id=GateId.LINEAGE, outcome=GateOutcome.PASS, detail="lineage verified"
            ),
        ),
        evidence_level=evidence,
        policy_readiness=PolicyReadiness.NOT_READY,
        recommended_validation="Run the remaining preregistered gates.",
        permitted_language="In this dataset and window, these records differ.",
    )


def _tier1(
    *, candidate_exposure: EffectEstimatePersistence | None = None
) -> CandidateExposureTierPersistence:
    return CandidateExposureTierPersistence(
        exposure_contract_version="2.0.0",
        tier=1,
        population_scope=TIER_1_POPULATION_SCOPE,
        quantity_name=TIER_1_QUANTITY_NAME,
        outcome_name="contribution_margin_eur",
        outcome_unit="EUR",
        affected_records=100,
        per_record_effect=_effect(),
        candidate_exposure=candidate_exposure
        or EffectEstimatePersistence(
            value=-1000,
            ci_low=-1500,
            ci_high=-500,
            confidence_level=0.95,
            method="same bootstrap",
            unit="EUR",
        ),
        annualization_justified=False,
        materiality_pass=False,
    )


def _tier2() -> CandidateExposureTierPersistence:
    return CandidateExposureTierPersistence(
        exposure_contract_version="2.0.0",
        tier=2,
        population_scope=TIER_2_POPULATION_SCOPE,
        quantity_name=TIER_2_QUANTITY_NAME,
        outcome_name="contribution_margin_eur",
        outcome_unit="EUR",
        affected_records=40,
        per_record_effect=_effect(),
        candidate_exposure=EffectEstimatePersistence(
            value=-400,
            ci_low=-600,
            ci_high=-200,
            confidence_level=0.95,
            method="stratified_generalized_adjustment_scaled_by_development_split_exposure",
            unit="EUR",
        ),
        annualization_justified=False,
        materiality_pass=False,
    )


def _impact(
    *,
    tier1: CandidateExposureTierPersistence | None = None,
    tier2: CandidateExposureTierPersistence | None = None,
    reportable_tiers: tuple[int, ...] = (1,),
    attributable_impact: AttributableImpactPersistence | None = None,
) -> EconomicImpactPersistence:
    return EconomicImpactPersistence(
        exposure_contract_version="2.0.0",
        tier1=tier1 if tier1 is not None else _tier1(),
        tier2=tier2,
        reportable_tiers=reportable_tiers,
        attributable_impact=attributable_impact,
    )


def test_candidate_contract_preserves_immutable_discovery_payload() -> None:
    candidate = CandidatePatternPersistence(
        id=uuid4(),
        analysis_run_id=uuid4(),
        candidate_key="CAND-001",
        conditions=(PatternCondition(feature="discount_rate", operator="ge", value=0.12),),
        fit_split="development",
        rank=1,
        rank_score=1000,
        actionability="HIGH",
        metrics=(
            CandidateMetric(
                split="development",
                n_population=1000,
                n_exposed=100,
                support=0.1,
                exposed_mean=1,
                comparison_mean=2,
                raw_difference=-1,
                harm_per_booking=1,
                historical_exposure=100,
            ),
        ),
        artifact_sha256=SHA,
        persisted_at=datetime.now(UTC),
        lineage=(LineageReference(kind="candidate_artifact", uri="artifact.json", sha256=SHA),),
    )

    with pytest.raises(ValidationError, match="frozen"):
        candidate.rank = 2  # pyright: ignore[reportAttributeAccessIssue]


def test_rejected_candidate_cannot_be_promoted_to_finding() -> None:
    with pytest.raises(ValidationError, match="rejected candidate"):
        FindingPromotion(
            candidate_id=uuid4(),
            analysis_run_id=uuid4(),
            dataset_id=uuid4(),
            validation=_validation(None),
            impact=_impact(),
            lineage=(LineageReference(kind="validation_report", uri="report.json", sha256=SHA),),
        )


def test_annualized_candidate_exposure_requires_justification() -> None:
    """`v2.0.0`'s annualization gate lives on `CandidateExposureTierPersistence` now (one tier's
    own figure), not on the envelope — same invariant as `v1`'s `annualized_impact`/
    `annualization_justified` pairing, just scoped per tier."""
    with pytest.raises(ValidationError, match="annualized candidate exposure"):
        CandidateExposureTierPersistence(
            exposure_contract_version="2.0.0",
            tier=1,
            population_scope=TIER_1_POPULATION_SCOPE,
            quantity_name=TIER_1_QUANTITY_NAME,
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=100,
            per_record_effect=_effect(),
            candidate_exposure=_effect(),
            annualized_candidate_exposure=_effect(),
            annualization_justified=False,
            materiality_pass=False,
        )


def test_economic_impact_persistence_carries_both_tiers_distinctly() -> None:
    """`TASK-088`: `tier1`/`tier2` are two distinct, both-correct numbers over different
    populations (`E` vs `E_dev`) — never re-flattened into one figure. `reportable_tiers` names
    which of them this candidate's own evidence level actually cleared for display."""
    tier1 = _tier1()
    tier2 = _tier2()
    impact = _impact(tier1=tier1, tier2=tier2, reportable_tiers=(1, 2))

    assert impact.tier1 is not None and impact.tier1.population_scope == "E"
    assert impact.tier2 is not None and impact.tier2.population_scope == "E_dev"
    assert impact.tier1.candidate_exposure.value != impact.tier2.candidate_exposure.value
    assert impact.reportable_tiers == (1, 2)
    assert impact.attributable_impact is None


def test_attributable_impact_tier3_shape() -> None:
    """Tier 3 (`O2`) is a structurally distinct type from tier 1/2 (`O1`), never merged into the
    same field — `AttributableImpactPersistence` carries its own `identification_gate`, never a
    `population_scope`/`quantity_name` borrowed from tiers 1-2."""
    attributable = AttributableImpactPersistence(
        exposure_contract_version="2.0.0",
        outcome_name="contribution_margin_eur",
        outcome_unit="EUR",
        affected_records=25,
        per_record_effect=_effect(),
        attributable_impact=EffectEstimatePersistence(
            value=-250, ci_low=-300, ci_high=-200, confidence_level=0.95, method="iv", unit="EUR"
        ),
        identification_gate=GateId.IDENTIFICATION,
        materiality_pass=True,
    )
    impact = _impact(attributable_impact=attributable)

    assert impact.attributable_impact is not None
    assert impact.attributable_impact.tier == 3
    assert impact.attributable_impact.population_scope == "A"
    assert impact.attributable_impact.identification_gate == GateId.IDENTIFICATION


def test_legacy_v1_shaped_payload_still_loads_as_tier1() -> None:
    """`TASK-088`'s migration requirement (`ADR-015`/`ADR-064` precedent): an already-persisted
    `v1.x` Finding row (`impact_contract_version`/flat `historical_impact`, no `tier1`/`tier2`)
    must remain readable — parsed under its own recorded contract version, wrapped as tier 1
    (`TASK-085` §7's own stated equivalence), never silently reinterpreted as a newly invented
    tier or re-graded under `v2.0.0`."""
    legacy_payload = {
        "impact_contract_version": "1.0.0",
        "outcome_name": "contribution_margin_eur",
        "outcome_unit": "EUR",
        "affected_records": 100,
        "per_record_effect": _effect().model_dump(mode="json"),
        "historical_impact": {
            "value": -1000,
            "ci_low": -1500,
            "ci_high": -500,
            "confidence_level": 0.95,
            "method": "same bootstrap",
            "unit": "EUR",
        },
        "annualized_impact": None,
        "annualization_justified": False,
        "materiality_pass": False,
    }

    impact = EconomicImpactPersistence.model_validate(legacy_payload)

    assert impact.exposure_contract_version == "1.0.0"
    assert impact.tier2 is None
    assert impact.attributable_impact is None
    assert impact.reportable_tiers == (1,)
    tier1 = impact.tier1
    assert tier1 is not None
    assert tier1.tier == 1
    assert tier1.population_scope == TIER_1_POPULATION_SCOPE
    assert tier1.quantity_name == TIER_1_QUANTITY_NAME
    assert tier1.exposure_contract_version == "1.0.0"
    assert tier1.candidate_exposure.value == -1000


def test_legacy_v1_kwargs_construction_also_normalizes() -> None:
    """The same dispatch fires for direct keyword construction (`EconomicImpactPersistence(...)`),
    not only `model_validate` on a dict — pydantic's `model_validator(mode="before")` sees kwargs
    as a plain dict either way. Several other already-existing tests in this project
    (`tests/api/test_policy_backtest.py`, `tests/api/test_policy_candidates.py`, etc.) still build
    `EconomicImpactPersistence` with the old flat kwargs; this is what keeps them passing
    unmodified after `TASK-088`, exactly the same normalization a genuinely old database row gets."""
    impact = EconomicImpactPersistence(
        impact_contract_version="1.0.0",
        outcome_name="contribution_margin_eur",
        outcome_unit="EUR",
        affected_records=10,
        per_record_effect=_effect(),
        historical_impact=_effect(),
        annualization_justified=False,
        materiality_pass=False,
    )

    assert impact.exposure_contract_version == "1.0.0"
    assert impact.tier1 is not None
    assert impact.tier1.tier == 1
    assert impact.reportable_tiers == (1,)


def test_impact_payload_with_neither_version_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="exposure_contract_version"):
        EconomicImpactPersistence.model_validate({"outcome_name": "x"})
