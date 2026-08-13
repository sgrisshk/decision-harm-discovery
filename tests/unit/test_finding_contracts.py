from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.findings.contracts import (
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


def _impact() -> EconomicImpactPersistence:
    return EconomicImpactPersistence(
        impact_contract_version="pending-task-023",
        outcome_name="contribution_margin_eur",
        outcome_unit="EUR",
        affected_records=100,
        per_record_effect=_effect(),
        historical_impact=EffectEstimatePersistence(
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


def test_annualized_impact_requires_justification() -> None:
    with pytest.raises(ValidationError, match="annualized impact"):
        EconomicImpactPersistence(
            impact_contract_version="pending-task-023",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            affected_records=100,
            per_record_effect=_effect(),
            historical_impact=_effect(),
            annualized_impact=_effect(),
            annualization_justified=False,
            materiality_pass=False,
        )
