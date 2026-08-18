from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.models import AnalysisRunModel, DatasetModel, FindingModel, PolicyCandidateModel
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
from app.policies.generation import generate_policy_candidates
from sqlalchemy import select
from sqlalchemy.orm import Session

import scripts.promote_findings as promote_findings_script

REPOSITORY = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration

_CLOSING_RUN_ARTIFACTS = (
    promote_findings_script.DEFAULT_CANDIDATES_PATH,
    promote_findings_script.DEFAULT_METRICS_PATH,
    promote_findings_script.DEFAULT_RANKING_PATH,
    promote_findings_script.DEFAULT_VALIDATION_PATH,
)


def _effect() -> EffectEstimatePersistence:
    return EffectEstimatePersistence(
        value=10.0, ci_low=5.0, ci_high=15.0, confidence_level=0.95, method="test", unit="EUR"
    )


def _seed_finding(session: Session, *, policy_readiness: str = "shadow_policy") -> FindingModel:
    """Mirrors `tests/api/test_policy_candidates.py`'s `_seed_finding`."""
    dataset = DatasetModel(
        name=f"generate-candidates-test-{uuid4().hex}",
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
        policy_readiness=policy_readiness,  # type: ignore[arg-type]
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


def test_creates_one_candidate_per_eligible_finding_and_skips_the_rest(
    postgres_session: Session,
) -> None:
    eligible = _seed_finding(postgres_session, policy_readiness="shadow_policy")
    ineligible = _seed_finding(postgres_session, policy_readiness="experiment_only")

    report = generate_policy_candidates(postgres_session)

    created_finding_ids = {
        candidate.finding_id
        for candidate in (postgres_session.get(PolicyCandidateModel, cid) for cid in report.created)
        if candidate is not None
    }
    assert eligible.id in created_finding_ids
    skipped_ids = {skip.finding_id for skip in report.skipped}
    assert ineligible.id in skipped_ids
    skipped_reason = next(s.reason for s in report.skipped if s.finding_id == ineligible.id)
    assert "not eligible" in skipped_reason


def test_generated_candidate_fields_are_deterministic_and_match_the_finding(
    postgres_session: Session,
) -> None:
    finding = _seed_finding(postgres_session)
    report = generate_policy_candidates(postgres_session, finding_ids=(finding.id,))

    assert len(report.created) == 1
    candidate = postgres_session.get(PolicyCandidateModel, report.created[0])
    assert candidate is not None
    assert candidate.title == finding.title
    assert candidate.rationale == finding.summary
    assert candidate.mode == "SHADOW"
    assert candidate.action_detail is None
    assert candidate.effective_population is None
    assert candidate.scope_narrowing_features == []
    assert candidate.status == "DRAFT"


def test_batch_rerun_is_idempotent(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    first = generate_policy_candidates(postgres_session)
    first_created_finding_ids = {
        candidate.finding_id
        for candidate in (postgres_session.get(PolicyCandidateModel, cid) for cid in first.created)
        if candidate is not None
    }
    assert finding.id in first_created_finding_ids

    # A persistent (non-ephemeral) database may carry other ACTIVE findings from earlier tests —
    # assert only that nothing new was created overall (every eligible finding already covered by
    # call 1 stays covered), and that this specific finding is reported as already-covered, rather
    # than asserting every skip in the whole batch shares one reason (other findings may be
    # skipped for a different reason, e.g. ineligibility, and that's not a contradiction).
    second = generate_policy_candidates(postgres_session)
    assert second.created == ()
    this_finding_reason = next(s.reason for s in second.skipped if s.finding_id == finding.id)
    assert "already has a policy candidate" in this_finding_reason


def test_unknown_finding_id_is_reported_as_skipped_not_raised(postgres_session: Session) -> None:
    missing_id = uuid4()
    report = generate_policy_candidates(postgres_session, finding_ids=(missing_id,))
    assert report.created == ()
    assert len(report.skipped) == 1
    assert report.skipped[0].finding_id == missing_id
    assert "no finding" in report.skipped[0].reason


def test_force_creates_an_explicit_additional_candidate(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    first = generate_policy_candidates(postgres_session, finding_ids=(finding.id,))
    assert len(first.created) == 1

    without_force = generate_policy_candidates(postgres_session, finding_ids=(finding.id,))
    assert without_force.created == ()

    with_force = generate_policy_candidates(postgres_session, finding_ids=(finding.id,), force=True)
    assert len(with_force.created) == 1
    assert with_force.created[0] != first.created[0]


@pytest.mark.skipif(
    not all(path.exists() for path in _CLOSING_RUN_ARTIFACTS),
    reason="task-058-remediation-20260817-001 closing-run artifacts are gitignored (regenerable "
    "via scripts/rank_candidates.py) and not present on this checkout",
)
def test_generate_script_against_the_real_closing_run(postgres_session: Session) -> None:
    # generate_policy_candidates.py's default (no-args) batch mode scans every ACTIVE Finding in
    # the whole database, not just this run's 15 — a persistent (non-ephemeral) database could
    # carry Findings from earlier tests/runs too. Diff run IDs before/after (same rerun-safety
    # lesson as test_promote_findings.py), then check only this run's own 15 Findings ended up
    # with the right fate, rather than asserting a fragile global stdout count.
    existing_run_ids = set(postgres_session.scalars(select(AnalysisRunModel.id)).all())

    env = dict(os.environ)
    env["DATABASE_URL"] = env["TEST_DATABASE_URL"]

    promote_result = subprocess.run(
        [sys.executable, "scripts/promote_findings.py"],
        cwd=REPOSITORY,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert promote_result.returncode == 0, promote_result.stderr

    all_run_ids = set(postgres_session.scalars(select(AnalysisRunModel.id)).all())
    new_run_ids = all_run_ids - existing_run_ids
    assert len(new_run_ids) == 1
    run_findings = postgres_session.scalars(
        select(FindingModel).where(FindingModel.analysis_run_id == new_run_ids.pop())
    ).all()
    assert len(run_findings) == 15

    generate_result = subprocess.run(
        [sys.executable, "scripts/generate_policy_candidates.py"],
        cwd=REPOSITORY,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert generate_result.returncode == 0, generate_result.stderr

    postgres_session.expire_all()
    shadow_policy_findings = [f for f in run_findings if f.policy_readiness == "shadow_policy"]
    experiment_only_findings = [f for f in run_findings if f.policy_readiness == "experiment_only"]
    assert len(shadow_policy_findings) == 6
    assert len(experiment_only_findings) == 9

    for finding in shadow_policy_findings:
        candidate = postgres_session.scalars(
            select(PolicyCandidateModel).where(PolicyCandidateModel.finding_id == finding.id)
        ).first()
        assert candidate is not None, f"expected a candidate for eligible finding {finding.id}"
        assert candidate.title == finding.title

    for finding in experiment_only_findings:
        candidate = postgres_session.scalars(
            select(PolicyCandidateModel).where(PolicyCandidateModel.finding_id == finding.id)
        ).first()
        assert candidate is None, f"finding {finding.id} is not eligible, got a candidate anyway"
