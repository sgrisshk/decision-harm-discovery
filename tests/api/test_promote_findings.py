from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.models import AnalysisRunModel, CandidatePatternModel, DatasetModel, FindingModel
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
    PromotionError,
    persist_candidate_pattern,
    persist_validation_report,
    promote_finding,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

REPOSITORY = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


def _effect() -> EffectEstimatePersistence:
    return EffectEstimatePersistence(
        value=10.0, ci_low=5.0, ci_high=15.0, confidence_level=0.95, method="test", unit="EUR"
    )


def _unevaluated_metadata() -> ValidationMetadataPersistence:
    """A report that was graded and rejected/never reached a level — `evidence_level=None`."""
    return ValidationMetadataPersistence(
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
                outcome="fail",  # type: ignore[arg-type]
                detail="did not pass",
            ),
        ),
        evidence_level=None,
        policy_readiness="not_ready",  # type: ignore[arg-type]
        recommended_validation="more data",
        permitted_language="descriptive only",
    )


def _seed_run_and_dataset(session: Session) -> AnalysisRunModel:
    dataset = DatasetModel(
        name=f"promotion-invariant-test-{uuid4().hex}",
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
    return run


def test_promote_finding_rejects_a_report_without_evidence_level(
    postgres_session: Session,
) -> None:
    run = _seed_run_and_dataset(postgres_session)
    candidate = persist_candidate_pattern(
        postgres_session,
        CandidatePatternPersistence(
            id=uuid4(),
            analysis_run_id=run.id,
            candidate_key="CAND-TEST",
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
    metadata = _unevaluated_metadata()
    report = persist_validation_report(
        postgres_session, candidate.id, metadata, generated_at=datetime.now(UTC)
    )

    with pytest.raises(PromotionError, match="cannot be promoted"):
        promote_finding(
            postgres_session,
            dataset_id=run.dataset_id,
            analysis_run_id=run.id,
            candidate=candidate,
            report=report,
            validation=metadata,
            impact=EconomicImpactPersistence(
                impact_contract_version="1.0.0",
                outcome_name="test",
                outcome_unit="EUR",
                affected_records=10,
                per_record_effect=_effect(),
                historical_impact=_effect(),
                annualization_justified=False,
                materiality_pass=False,
            ),
            harm_direction_phrase="Test drops",
            generated_at=datetime.now(UTC),
        )

    # the rejected report is still persisted for audit, but produced no Finding
    findings = postgres_session.scalars(
        select(FindingModel).where(FindingModel.candidate_pattern_id == candidate.id)
    ).all()
    assert list(findings) == []


def test_promote_findings_script_against_real_closing_run(
    postgres_session: Session, db_client: TestClient
) -> None:
    # The script is not idempotent (see its own docstring) and `_ensure_analytical_dataset` reuses
    # an existing dataset row by checksum, but always inserts a fresh AnalysisRun — so a rerun
    # against a persistent (non-ephemeral) database would add a second run rather than replace the
    # first. Diff run IDs before/after rather than assuming this is the only run in the database,
    # matching the rerun-safety lesson from `tests/api/test_datasets_upload.py`.
    existing_run_ids = set(postgres_session.scalars(select(AnalysisRunModel.id)).all())

    env = dict(os.environ)
    env["DATABASE_URL"] = env["TEST_DATABASE_URL"]
    result = subprocess.run(
        [sys.executable, "scripts/promote_findings.py"],
        cwd=REPOSITORY,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    # Per docs/product/finding-product-contract.md §0, a Finding is any graded candidate output
    # (evidence + impact), not only a PASS-verdict one — none of the 15 REJECT on this run, so all
    # 15 promote. The PASS/DOWNGRADE split lives in evidence_level/policy_readiness per Finding.
    assert "promoted 15 findings" in result.stdout

    all_run_ids = set(postgres_session.scalars(select(AnalysisRunModel.id)).all())
    new_run_ids = all_run_ids - existing_run_ids
    assert len(new_run_ids) == 1
    run = postgres_session.get(AnalysisRunModel, new_run_ids.pop())
    assert run is not None
    # The script's default now points at task-058-remediation-20260817-001 — the current
    # PROMISING-verdict closing run (`ADR-025`) — not the superseded, FAILED-graded
    # task-015-official-20260816-015 this test originally asserted against.
    assert run.evaluated_hypotheses == 6557
    assert run.random_seed == 1729

    candidates = postgres_session.scalars(
        select(CandidatePatternModel).where(CandidatePatternModel.analysis_run_id == run.id)
    ).all()
    assert len(candidates) == 15

    findings = postgres_session.scalars(
        select(FindingModel).where(FindingModel.analysis_run_id == run.id)
    ).all()
    assert len(findings) == 15
    shadow_policy_keys = set()
    experiment_only_keys = set()
    for finding in findings:
        assert finding.lifecycle_status == "ACTIVE"
        key = finding.pattern_snapshot["candidate_key"]
        if finding.policy_readiness == "shadow_policy":
            assert finding.evidence_level == "adjusted_observational_association"
            shadow_policy_keys.add(key)
        else:
            assert finding.policy_readiness == "experiment_only"
            # DOWNGRADE candidates on this run land at two different evidence levels
            # (descriptive_observation or predictive_association), unlike task-015's — both are
            # still capped short of adjusted_observational_association, which is what
            # experiment_only readiness actually gates on.
            assert finding.evidence_level in {"descriptive_observation", "predictive_association"}
            experiment_only_keys.add(key)
    assert shadow_policy_keys == {
        "CAND-003",
        "CAND-006",
        "CAND-007",
        "CAND-011",
        "CAND-013",
        "CAND-015",
    }
    assert len(experiment_only_keys) == 9
    assert shadow_policy_keys | experiment_only_keys == {f"CAND-{i:03d}" for i in range(1, 16)}

    # API surface: all 15 ACTIVE findings from this run are listed (superset-safe — a persistent,
    # non-ephemeral database could carry findings from an earlier rerun too, same rationale as
    # above), with the required-for-MVP shape.
    listed = db_client.get("/api/v1/findings").json()
    listed_from_this_run = [item for item in listed if item["analysis_run_id"] == str(run.id)]
    assert len(listed_from_this_run) == 15
    assert {item["pattern"]["candidate_key"] for item in listed_from_this_run} == (
        shadow_policy_keys | experiment_only_keys
    )
    # Any shadow_policy candidate demonstrates the adjusted_effect shape below — picked from the
    # set derived above rather than a hardcoded key, so this doesn't go stale if the default run
    # changes again.
    shadow_policy_key = next(iter(shadow_policy_keys))
    sample = next(
        item
        for item in listed_from_this_run
        if item["pattern"]["candidate_key"] == shadow_policy_key
    )
    assert sample["title"].startswith("Contribution margin drops when")
    assert sample["evidence"]["adjusted_effect"] is not None
    assert set(sample["evidence"]["adjusted_effect"]) == {
        "value",
        "ci_low",
        "ci_high",
        "confidence_level",
        "method",
        "unit",
    }
    assert sample["impact"]["affected_records"] > sample["exposed_records"]
    assert "min_material_annual_impact" not in str(sample["impact"])
    assert sample["impact"]["materiality_pass"] is True

    detail = db_client.get(f"/api/v1/findings/{sample['id']}").json()
    assert detail["id"] == sample["id"]

    # adjusted_effect is only guaranteed *required* at adjusted_observational_association+ (§1) —
    # not guaranteed *absent* below it, since adjustment is computed independently of which gate
    # capped the final evidence level. Only raw_effect and the evidence-level/readiness pairing
    # are guaranteed here.
    experiment_only_key = next(iter(experiment_only_keys))
    weak = next(
        item
        for item in listed_from_this_run
        if item["pattern"]["candidate_key"] == experiment_only_key
    )
    assert weak["evidence"]["raw_effect"] is not None
    assert weak["evidence_level"] in {"descriptive_observation", "predictive_association"}
    assert weak["policy_readiness"] == "experiment_only"
