from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from app.db.models import AnalysisRunModel, DatasetModel, FindingModel
from app.findings.contracts import (
    CandidateMetric,
    CandidatePatternPersistence,
    EconomicImpactPersistence,
    EffectEstimatePersistence,
    GateResultPersistence,
    LineageReference,
    PatternCondition,
    ValidationMetadataPersistence,
)
from app.findings.persistence import (
    persist_candidate_pattern,
    persist_validation_report,
    promote_finding,
)
from app.policies.contracts import PolicyCandidateCreate
from app.policies.service import create_draft_policy_candidate
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _effect() -> EffectEstimatePersistence:
    return EffectEstimatePersistence(
        value=10.0, ci_low=5.0, ci_high=15.0, confidence_level=0.95, method="test", unit="EUR"
    )


def _seed_finding(session: Session) -> FindingModel:
    dataset = DatasetModel(
        name=f"policy-routes-test-{uuid4().hex}",
        source_filename="fixture.csv",
        checksum_sha256="a" * 64,
        size_bytes=10,
        content_type="text/csv",
        source_type="csv_upload",
        storage_path="ab/aaaa.csv",
    )
    session.add(dataset)
    session.flush()
    run = AnalysisRunModel(
        dataset_id=dataset.id,
        dataset_version=1,
        analytical_dataset_version="v1",
        analytical_dataset_identity_sha256="b" * 64,
        code_version="test",
        discovery_methodology_version="test",
        outcome_definition_version="test",
        validation_contract_version="test",
        configuration={},
        random_seed=1,
        evaluated_hypotheses=1,
        lineage=[],
    )
    session.add(run)
    session.flush()

    candidate = persist_candidate_pattern(
        session,
        CandidatePatternPersistence(
            id=uuid4(),
            analysis_run_id=run.id,
            candidate_key=f"CAND-{uuid4().hex}",
            conditions=(PatternCondition(feature="discount_rate", operator="ge", value=0.1),),
            fit_split="development",
            rank=1,
            rank_score=0.5,
            actionability="HIGH",
            metrics=(
                CandidateMetric(
                    split="development",
                    n_population=100,
                    n_exposed=10,
                    support=0.1,
                    exposed_mean=1.0,
                    comparison_mean=2.0,
                    raw_difference=-1.0,
                    harm_per_booking=1.0,
                    historical_exposure=10.0,
                ),
            ),
            warnings=(),
            artifact_sha256="c" * 64,
            persisted_at=datetime.now(UTC),
            lineage=(
                LineageReference(kind="candidate_artifact", uri="test://fixture", sha256="d" * 64),
            ),
        ),
    )
    metadata = ValidationMetadataPersistence(
        contract_version="1.1.0",
        outcome_definition_version="1.1.0",
        outcome_definition="test outcome",
        exposed_records=10,
        comparison_records=90,
        clustering_key="customer_id",
        raw_effect=_effect(),
        identification_design="observational",  # type: ignore[arg-type]
        gate_results=(
            GateResultPersistence(
                gate_id="G05_MULTIPLE_COMPARISONS",  # type: ignore[arg-type]
                outcome="pass",  # type: ignore[arg-type]
                detail="passed",
            ),
        ),
        evidence_level="descriptive_observation",  # type: ignore[arg-type]
        policy_readiness="shadow_policy",  # type: ignore[arg-type]
        recommended_validation="none",
        permitted_language="descriptive only",
    )
    report = persist_validation_report(
        session, candidate.id, metadata, generated_at=datetime.now(UTC)
    )
    impact = EconomicImpactPersistence(
        impact_contract_version="1.0.0",
        outcome_name="contribution_margin_eur",
        outcome_unit="EUR/booking",
        affected_records=10,
        per_record_effect=_effect(),
        historical_impact=_effect(),
        annualization_justified=False,
        materiality_pass=True,
    )
    finding = promote_finding(
        session,
        dataset_id=dataset.id,
        analysis_run_id=run.id,
        candidate=candidate,
        report=report,
        validation=metadata,
        impact=impact,
        harm_direction_phrase="Contribution margin drops",
        generated_at=datetime.now(UTC),
        lineage=(),
    )
    session.commit()
    return finding


def _seed_candidate(session: Session) -> tuple[FindingModel, str]:
    finding = _seed_finding(session)
    payload = PolicyCandidateCreate(
        title="Flag high-discount bookings for review",
        rationale="Contribution margin drops when discount_rate is at least 0.1.",
        effective_from=date(2026, 9, 1),
        expected_benefit_snapshot=EconomicImpactPersistence(
            impact_contract_version="1.0.0",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR/booking",
            affected_records=10,
            per_record_effect=_effect(),
            historical_impact=_effect(),
            annualization_justified=False,
            materiality_pass=True,
        ),
    )
    candidate = create_draft_policy_candidate(session, finding, payload)
    session.commit()
    return finding, str(candidate.id)


def test_list_and_get_policy_candidate(db_client: TestClient, postgres_session: Session) -> None:
    finding, candidate_id = _seed_candidate(postgres_session)

    listed = db_client.get(f"/api/v1/policy-candidates?finding_id={finding.id}").json()
    assert {item["id"] for item in listed} == {candidate_id}

    detail = db_client.get(f"/api/v1/policy-candidates/{candidate_id}").json()
    assert detail["status"] == "DRAFT"
    assert detail["mode"] == "SHADOW"
    assert detail["action_detail"] is None
    assert detail["trigger_conditions"] == [
        {"feature": "discount_rate", "operator": "ge", "value": 0.1}
    ]


def test_get_unknown_candidate_404s(db_client: TestClient) -> None:
    response = db_client.get(f"/api/v1/policy-candidates/{uuid4()}")
    assert response.status_code == 404


def test_transition_to_under_review_requires_action_detail(
    db_client: TestClient, postgres_session: Session
) -> None:
    _, candidate_id = _seed_candidate(postgres_session)

    missing = db_client.post(
        f"/api/v1/policy-candidates/{candidate_id}/transition",
        json={"new_status": "UNDER_REVIEW"},
    )
    assert missing.status_code == 409

    ok = db_client.post(
        f"/api/v1/policy-candidates/{candidate_id}/transition",
        json={
            "new_status": "UNDER_REVIEW",
            "action_detail": "Require a second manager approval.",
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["status"] == "UNDER_REVIEW"
    assert body["action_detail"] == "Require a second manager approval."


def test_illegal_transition_is_rejected(db_client: TestClient, postgres_session: Session) -> None:
    _, candidate_id = _seed_candidate(postgres_session)
    response = db_client.post(
        f"/api/v1/policy-candidates/{candidate_id}/transition",
        json={"new_status": "APPROVED_SHADOW"},
    )
    assert response.status_code == 409


def test_rejection_requires_a_reason(db_client: TestClient, postgres_session: Session) -> None:
    _, candidate_id = _seed_candidate(postgres_session)
    db_client.post(
        f"/api/v1/policy-candidates/{candidate_id}/transition",
        json={"new_status": "UNDER_REVIEW", "action_detail": "Some human-authored action."},
    )

    missing_reason = db_client.post(
        f"/api/v1/policy-candidates/{candidate_id}/transition",
        json={"new_status": "REJECTED"},
    )
    assert missing_reason.status_code == 409

    ok = db_client.post(
        f"/api/v1/policy-candidates/{candidate_id}/transition",
        json={"new_status": "REJECTED", "reason": "Customer has no operational lever."},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "REJECTED"
    assert ok.json()["rejection_reason"] == "Customer has no operational lever."
