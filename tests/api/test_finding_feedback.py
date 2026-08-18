from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.auth.security import hash_password
from app.db.models import AnalysisRunModel, DatasetModel, FindingModel, UserModel
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
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _effect() -> EffectEstimatePersistence:
    return EffectEstimatePersistence(
        value=10.0, ci_low=5.0, ci_high=15.0, confidence_level=0.95, method="test", unit="EUR"
    )


def _seed_finding(session: Session) -> FindingModel:
    """Mirrors `tests/api/test_promote_findings.py`'s setup, but grades the report `PASS` so it
    actually promotes — that file only exercises the rejection path."""
    dataset = DatasetModel(
        name=f"feedback-test-{uuid4().hex}",
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
            conditions=(PatternCondition(feature="x", operator="eq", value=True),),
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


def _seed_and_login(db_client: TestClient, session: Session) -> UserModel:
    user = UserModel(
        email=f"reviewer-{uuid4().hex}@example.com",
        password_hash=hash_password("feedback reviewer password"),
        display_name="Feedback Reviewer",
    )
    session.add(user)
    session.commit()
    login_response = db_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "feedback reviewer password"},
    )
    assert login_response.status_code == 200
    return user


def test_posting_feedback_requires_authentication(
    db_client: TestClient, postgres_session: Session
) -> None:
    finding = _seed_finding(postgres_session)

    response = db_client.post(
        f"/api/v1/findings/{finding.id}/feedback",
        json={"review_session": "acme-2026-08-18"},
    )

    assert response.status_code == 401


def test_wrong_tag_without_comment_is_rejected(
    db_client: TestClient, postgres_session: Session
) -> None:
    finding = _seed_finding(postgres_session)
    _seed_and_login(db_client, postgres_session)

    response = db_client.post(
        f"/api/v1/findings/{finding.id}/feedback",
        json={"review_session": "acme-2026-08-18", "tags": ["WRONG"]},
    )

    assert response.status_code == 422


def test_valid_feedback_is_persisted_and_attributed_to_the_authenticated_user(
    db_client: TestClient, postgres_session: Session
) -> None:
    finding = _seed_finding(postgres_session)
    user = _seed_and_login(db_client, postgres_session)

    response = db_client.post(
        f"/api/v1/findings/{finding.id}/feedback",
        json={
            "review_session": "acme-2026-08-18",
            "novelty": "NEW",
            "actionability": "ACTIONABLE",
            "tags": ["INTERESTING"],
            "intended_action": "Tighten the discount threshold",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["finding_id"] == str(finding.id)
    assert body["created_by_user_id"] == str(user.id)
    assert body["novelty"] == "NEW"
    assert body["actionability"] == "ACTIONABLE"
    assert body["tags"] == ["INTERESTING"]


def test_feedback_is_append_only_not_a_single_updated_row(
    db_client: TestClient, postgres_session: Session
) -> None:
    finding = _seed_finding(postgres_session)
    _seed_and_login(db_client, postgres_session)

    first = db_client.post(
        f"/api/v1/findings/{finding.id}/feedback",
        json={"review_session": "acme-2026-08-18", "novelty": "KNOWN_ALREADY"},
    )
    second = db_client.post(
        f"/api/v1/findings/{finding.id}/feedback",
        json={"review_session": "acme-2026-09-01", "novelty": "NEW"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    history = db_client.get(f"/api/v1/findings/{finding.id}/feedback")
    assert history.status_code == 200
    ids = {row["id"] for row in history.json()}
    assert {first.json()["id"], second.json()["id"]} <= ids


def test_list_feedback_for_unknown_finding_404s(db_client: TestClient) -> None:
    response = db_client.get(f"/api/v1/findings/{uuid4()}/feedback")
    assert response.status_code == 404


def test_post_feedback_for_unknown_finding_404s(
    db_client: TestClient, postgres_session: Session
) -> None:
    _seed_and_login(db_client, postgres_session)
    response = db_client.post(
        f"/api/v1/findings/{uuid4()}/feedback", json={"review_session": "acme-2026-08-18"}
    )
    assert response.status_code == 404


def test_feedback_never_changes_the_findings_own_evidence_level(
    db_client: TestClient, postgres_session: Session
) -> None:
    finding = _seed_finding(postgres_session)
    before = db_client.get(f"/api/v1/findings/{finding.id}").json()
    _seed_and_login(db_client, postgres_session)

    db_client.post(
        f"/api/v1/findings/{finding.id}/feedback",
        json={
            "review_session": "acme-2026-08-18",
            "tags": ["WRONG"],
            "customer_comment": "We don't actually have this policy.",
        },
    )

    after = db_client.get(f"/api/v1/findings/{finding.id}").json()
    assert after["evidence_level"] == before["evidence_level"]
    assert after["policy_readiness"] == before["policy_readiness"]
