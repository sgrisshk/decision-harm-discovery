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
from app.policies.contracts import PolicyCandidateBacktestSnapshot, PolicyCandidateCreate
from app.policies.service import (
    PolicyCandidateError,
    cascade_finding_lifecycle_change,
    create_draft_policy_candidate,
    transition_policy_candidate,
)
from policy_schemas.domain import FindingLifecycleStatus, PolicyCandidateMode, PolicyCandidateStatus
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _effect() -> EffectEstimatePersistence:
    return EffectEstimatePersistence(
        value=10.0, ci_low=5.0, ci_high=15.0, confidence_level=0.95, method="test", unit="EUR"
    )


def _seed_finding(
    session: Session,
    *,
    evidence_level: str = "descriptive_observation",
    policy_readiness: str = "shadow_policy",
    potential_confounders: tuple[str, ...] = (),
) -> FindingModel:
    """Mirrors `tests/api/test_finding_feedback.py`'s `_seed_finding`, parametrized on
    evidence/readiness/confounders so both eligible and ineligible Findings can be built."""
    dataset = DatasetModel(
        name=f"policy-candidate-test-{uuid4().hex}",
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
        potential_confounders=potential_confounders,
        identification_design="observational",  # type: ignore[arg-type]
        gate_results=(
            GateResultPersistence(
                gate_id="G05_MULTIPLE_COMPARISONS",  # type: ignore[arg-type]
                outcome="pass",  # type: ignore[arg-type]
                detail="passed",
            ),
        ),
        evidence_level=evidence_level,  # type: ignore[arg-type]
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


def _payload(**overrides: object) -> PolicyCandidateCreate:
    defaults: dict[str, object] = {
        "title": "Flag high-discount bookings for review",
        "rationale": "Contribution margin drops when discount_rate is at least 0.1.",
        "effective_from": date(2026, 9, 1),
        "expected_benefit_snapshot": EconomicImpactPersistence(
            impact_contract_version="1.0.0",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR/booking",
            affected_records=10,
            per_record_effect=_effect(),
            historical_impact=_effect(),
            annualization_justified=False,
            materiality_pass=True,
        ),
    }
    defaults.update(overrides)
    return PolicyCandidateCreate(**defaults)  # type: ignore[arg-type]


def test_ineligible_readiness_is_rejected(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session, policy_readiness="experiment_only")
    with pytest.raises(PolicyCandidateError, match="not eligible"):
        create_draft_policy_candidate(postgres_session, finding, _payload())


def test_trigger_conditions_are_copied_verbatim_from_the_finding(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    candidate = create_draft_policy_candidate(postgres_session, finding, _payload())
    assert candidate.trigger_conditions == finding.pattern_snapshot["conditions"]


def test_scope_narrowing_by_a_confounder_is_rejected(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session, potential_confounders=("manager_id",))
    with pytest.raises(PolicyCandidateError, match="potential confounder"):
        create_draft_policy_candidate(
            postgres_session, finding, _payload(scope_narrowing_features=("manager_id",))
        )


def test_scope_narrowing_by_a_non_confounder_is_accepted(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session, potential_confounders=("manager_id",))
    candidate = create_draft_policy_candidate(
        postgres_session, finding, _payload(scope_narrowing_features=("rollout_cohort",))
    )
    assert candidate.scope_narrowing_features == ["rollout_cohort"]


def test_second_candidate_without_force_is_rejected(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    create_draft_policy_candidate(postgres_session, finding, _payload())
    with pytest.raises(PolicyCandidateError, match="already has a policy candidate"):
        create_draft_policy_candidate(postgres_session, finding, _payload())


def test_second_candidate_with_force_is_accepted(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    first = create_draft_policy_candidate(postgres_session, finding, _payload())
    second = create_draft_policy_candidate(postgres_session, finding, _payload(), force=True)
    assert first.id != second.id


def test_enforcement_proposal_mode_is_rejected_at_the_contract_level() -> None:
    with pytest.raises(ValueError, match="not reachable today"):
        _payload(mode=PolicyCandidateMode.ENFORCEMENT_PROPOSAL)


def test_full_forward_only_transition_sequence(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    candidate = create_draft_policy_candidate(postgres_session, finding, _payload())
    assert candidate.status == "DRAFT"

    with pytest.raises(PolicyCandidateError, match="action_detail must be human-authored"):
        transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.UNDER_REVIEW)

    candidate.action_detail = "Require a second manager approval before applying the discount."
    postgres_session.flush()
    transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.UNDER_REVIEW)
    assert candidate.status == "UNDER_REVIEW"

    with pytest.raises(PolicyCandidateError, match="not a legal transition"):
        transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.DRAFT)

    transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.APPROVED_SHADOW)
    assert candidate.status == "APPROVED_SHADOW"

    with pytest.raises(PolicyCandidateError, match="reason is required"):
        transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.RETIRED)

    transition_policy_candidate(
        postgres_session,
        candidate,
        PolicyCandidateStatus.RETIRED,
        reason="Superseded by a better-scoped candidate.",
    )
    assert candidate.status == "RETIRED"
    assert candidate.retirement_reason == "Superseded by a better-scoped candidate."

    with pytest.raises(PolicyCandidateError, match="not a legal transition"):
        transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.UNDER_REVIEW)


def test_rejection_requires_a_reason(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    candidate = create_draft_policy_candidate(postgres_session, finding, _payload())
    candidate.action_detail = "Flag matching bookings for human review before proceeding."
    postgres_session.flush()
    transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.UNDER_REVIEW)

    with pytest.raises(PolicyCandidateError, match="reason is required"):
        transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.REJECTED)

    transition_policy_candidate(
        postgres_session,
        candidate,
        PolicyCandidateStatus.REJECTED,
        reason="Customer has no operational lever to act on this.",
    )
    assert candidate.status == "REJECTED"
    assert candidate.rejection_reason == "Customer has no operational lever to act on this."


def test_cascade_blocks_draft_and_under_review_candidates(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    blocked_draft = create_draft_policy_candidate(postgres_session, finding, _payload())

    finding.lifecycle_status = FindingLifecycleStatus.SUPERSEDED.value
    postgres_session.flush()

    affected = cascade_finding_lifecycle_change(postgres_session, finding.id)
    assert blocked_draft.id in {c.id for c in affected}
    assert blocked_draft.blocked_by_source_lifecycle is True
    assert blocked_draft.status == "DRAFT"  # cascade never itself changes status

    blocked_draft.action_detail = "Flag matching bookings for human review before proceeding."
    postgres_session.flush()
    with pytest.raises(PolicyCandidateError, match="blocked"):
        transition_policy_candidate(
            postgres_session, blocked_draft, PolicyCandidateStatus.UNDER_REVIEW
        )


def test_cascade_auto_retires_approved_shadow_candidates(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    candidate = create_draft_policy_candidate(postgres_session, finding, _payload())
    candidate.action_detail = "Flag matching bookings for human review before proceeding."
    postgres_session.flush()
    transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.UNDER_REVIEW)
    transition_policy_candidate(postgres_session, candidate, PolicyCandidateStatus.APPROVED_SHADOW)

    finding.lifecycle_status = FindingLifecycleStatus.WITHDRAWN.value
    postgres_session.flush()
    affected = cascade_finding_lifecycle_change(postgres_session, finding.id)

    assert candidate.id in {c.id for c in affected}
    assert candidate.status == "RETIRED"
    assert candidate.retirement_reason == "source finding no longer active"


def test_cascade_is_a_noop_while_the_finding_stays_active(postgres_session: Session) -> None:
    finding = _seed_finding(postgres_session)
    create_draft_policy_candidate(postgres_session, finding, _payload())
    assert cascade_finding_lifecycle_change(postgres_session, finding.id) == []


def test_backtest_result_snapshot_round_trips_a_real_shape() -> None:
    """Mirrors `policy_analytics.backtest.contract.BacktestResult.to_dict()`'s exact shape."""
    snapshot = PolicyCandidateBacktestSnapshot(
        backtest_contract_version="1.0.0",
        outcome_name="contribution_margin_eur",
        outcome_unit="EUR/booking",
        window="future_holdout",
        affected_decisions=100,
        avoided_bad_outcomes=60,
        suppressed_good_outcomes=40,
        bad_outcome_definition="contribution_margin_eur < 0.0",
        benefit=_effect(),
        benefit_is_adjusted=False,
        operational_cost_per_review_eur=None,
        operational_cost=None,
        net_effect=_effect(),
        net_effect_is_cost_exclusive=True,
        no_measurable_net_effect=False,
        methodology_disclosure="mechanical replay against future_holdout, not a forecast",
    )
    assert snapshot.affected_decisions == 100

    with pytest.raises(ValueError, match="must equal affected_decisions"):
        PolicyCandidateBacktestSnapshot(
            backtest_contract_version="1.0.0",
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR/booking",
            window="future_holdout",
            affected_decisions=100,
            avoided_bad_outcomes=60,
            suppressed_good_outcomes=30,
            bad_outcome_definition="contribution_margin_eur < 0.0",
            benefit=_effect(),
            benefit_is_adjusted=False,
            operational_cost_per_review_eur=None,
            operational_cost=None,
            net_effect=_effect(),
            net_effect_is_cost_exclusive=True,
            no_measurable_net_effect=False,
            methodology_disclosure="x",
        )
