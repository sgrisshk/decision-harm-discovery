from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from app.db.models import AnalysisRunModel, DatasetModel
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
from app.policies.service import create_draft_policy_candidate, transition_policy_candidate
from fastapi.testclient import TestClient
from policy_schemas.domain import PolicyCandidateStatus
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Known-real, verified-live against the actual analytical dataset (see the TASK-034 commit): 570
# future_holdout rows match, 108 avoided-bad / 462 suppressed-good.
_REAL_CONDITIONS = (
    PatternCondition(feature="customer_price_eur", operator="lt", value=3817.99),
    PatternCondition(feature="discount_rate", operator="ge", value=0.12),
)


def _effect() -> EffectEstimatePersistence:
    return EffectEstimatePersistence(
        value=10.0, ci_low=5.0, ci_high=15.0, confidence_level=0.95, method="test", unit="EUR"
    )


def _seed_approved_candidate(
    session: Session, conditions: tuple[PatternCondition, ...] = _REAL_CONDITIONS
) -> str:
    dataset = DatasetModel(
        name=f"policy-backtest-test-{uuid4().hex}",
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
            conditions=conditions,
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

    payload = PolicyCandidateCreate(
        title="Flag high-discount bookings for review",
        rationale="test",
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
        action_detail="Require a second manager approval.",
    )
    policy_candidate = create_draft_policy_candidate(session, finding, payload)
    transition_policy_candidate(session, policy_candidate, PolicyCandidateStatus.UNDER_REVIEW)
    transition_policy_candidate(session, policy_candidate, PolicyCandidateStatus.APPROVED_SHADOW)
    session.commit()
    return str(policy_candidate.id)


def test_trigger_backtest_matches_a_direct_engine_call(
    db_client: TestClient, postgres_session: Session
) -> None:
    candidate_id = _seed_approved_candidate(postgres_session)

    response = db_client.post(f"/api/v1/policy-candidates/{candidate_id}/backtest", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    result = body["backtest_result"]
    # Known-real values, independently re-verified against a direct run_backtest() call in this
    # commit's own live verification pass (not re-derived here — pinning the real number is the
    # regression guard).
    assert result["affected_decisions"] == 570
    assert result["avoided_bad_outcomes"] == 108
    assert result["suppressed_good_outcomes"] == 462
    assert result["window"] == "future_holdout"
    assert result["benefit_is_adjusted"] is False
    assert result["operational_cost"] is None
    assert result["net_effect_is_cost_exclusive"] is True


def test_rerunning_creates_a_new_row_not_an_overwrite(
    db_client: TestClient, postgres_session: Session
) -> None:
    candidate_id = _seed_approved_candidate(postgres_session)
    first = db_client.post(f"/api/v1/policy-candidates/{candidate_id}/backtest", json={})
    second = db_client.post(f"/api/v1/policy-candidates/{candidate_id}/backtest", json={})
    assert first.json()["id"] != second.json()["id"]

    history = db_client.get(f"/api/v1/policy-candidates/{candidate_id}/backtest").json()
    ids = {row["id"] for row in history}
    assert {first.json()["id"], second.json()["id"]} <= ids


def test_cost_per_review_is_echoed_back_and_netted(
    db_client: TestClient, postgres_session: Session
) -> None:
    candidate_id = _seed_approved_candidate(postgres_session)
    response = db_client.post(
        f"/api/v1/policy-candidates/{candidate_id}/backtest",
        json={"cost_per_review_eur": 5.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cost_per_review_eur"] == 5.0
    result = body["backtest_result"]
    assert result["operational_cost"] is not None
    assert result["operational_cost_per_review_eur"] == 5.0
    assert result["net_effect_is_cost_exclusive"] is False
    assert result["net_effect"]["value"] < result["benefit"]["value"]


def test_backtest_on_a_draft_candidate_is_rejected(
    db_client: TestClient, postgres_session: Session
) -> None:
    # _seed_approved_candidate always transitions through to APPROVED_SHADOW; build a DRAFT one
    # here by stopping short of that, to exercise §1's eligibility gate directly.
    dataset = DatasetModel(
        name=f"policy-backtest-draft-test-{uuid4().hex}",
        source_filename="fixture.csv",
        checksum_sha256="a" * 64,
        size_bytes=10,
        content_type="text/csv",
        source_type="csv_upload",
        storage_path="ab/aaaa.csv",
    )
    postgres_session.add(dataset)
    postgres_session.flush()
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
    postgres_session.add(run)
    postgres_session.flush()
    candidate_row = persist_candidate_pattern(
        postgres_session,
        CandidatePatternPersistence(
            id=uuid4(),
            analysis_run_id=run.id,
            candidate_key=f"CAND-{uuid4().hex}",
            conditions=_REAL_CONDITIONS,
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
        postgres_session, candidate_row.id, metadata, generated_at=datetime.now(UTC)
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
        postgres_session,
        dataset_id=dataset.id,
        analysis_run_id=run.id,
        candidate=candidate_row,
        report=report,
        validation=metadata,
        impact=impact,
        harm_direction_phrase="Contribution margin drops",
        generated_at=datetime.now(UTC),
        lineage=(),
    )
    payload = PolicyCandidateCreate(
        title="Flag high-discount bookings for review",
        rationale="test",
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
    draft_candidate = create_draft_policy_candidate(postgres_session, finding, payload)
    postgres_session.commit()

    response = db_client.post(f"/api/v1/policy-candidates/{draft_candidate.id}/backtest", json={})
    assert response.status_code == 409


def test_backtest_on_unknown_candidate_404s(db_client: TestClient) -> None:
    response = db_client.post(f"/api/v1/policy-candidates/{uuid4()}/backtest", json={})
    assert response.status_code == 404
