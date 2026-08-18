"""HTTP surface for Policy Candidates and their backtest runs (`TASK-034`).

First public routes for this package — `TASK-030`/`TASK-031`'s persistence/generator stayed
internal on purpose (`app.policies.service`'s own module docstring); this is the first real
consumer (the candidate detail and backtest screens) that needs one. No auth on any route here —
matches `ADR-027`'s deliberately narrow protected surface: nothing here was asked to carry
attribution the way `TASK-035` feedback explicitly was.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from policy_schemas.domain import PolicyCandidateStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import PolicyBacktestRunRead, PolicyCandidateRead
from app.db.models import PolicyBacktestRunModel
from app.db.session import get_db
from app.policies import service
from app.policies.backtest_service import trigger_backtest
from app.policies.contracts import PolicyBacktestTriggerRequest, PolicyCandidateTransitionRequest
from app.policies.service import PolicyCandidateError

router = APIRouter(prefix="/policy-candidates", tags=["policy-candidates"])


@router.get("", response_model=list[PolicyCandidateRead])
def list_policy_candidates(
    finding_id: UUID | None = None, session: Session = Depends(get_db)
) -> list[PolicyCandidateRead]:
    return [
        PolicyCandidateRead.model_validate(item)
        for item in service.list_policy_candidates(session, finding_id)
    ]


@router.get("/{candidate_id}", response_model=PolicyCandidateRead)
def get_policy_candidate(
    candidate_id: UUID, session: Session = Depends(get_db)
) -> PolicyCandidateRead:
    return PolicyCandidateRead.model_validate(service.get_policy_candidate(session, candidate_id))


@router.post("/{candidate_id}/transition", response_model=PolicyCandidateRead)
def transition_policy_candidate(
    candidate_id: UUID,
    payload: PolicyCandidateTransitionRequest,
    session: Session = Depends(get_db),
) -> PolicyCandidateRead:
    candidate = service.get_policy_candidate(session, candidate_id)
    if payload.new_status == PolicyCandidateStatus.UNDER_REVIEW and payload.action_detail:
        candidate.action_detail = payload.action_detail
    try:
        service.transition_policy_candidate(
            session, candidate, payload.new_status, reason=payload.reason
        )
    except PolicyCandidateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    return PolicyCandidateRead.model_validate(candidate)


@router.post("/{candidate_id}/backtest", response_model=PolicyBacktestRunRead)
def create_backtest_run(
    candidate_id: UUID,
    payload: PolicyBacktestTriggerRequest,
    session: Session = Depends(get_db),
) -> PolicyBacktestRunRead:
    candidate = service.get_policy_candidate(session, candidate_id)
    run = trigger_backtest(session, candidate, cost_per_review_eur=payload.cost_per_review_eur)
    session.commit()
    return PolicyBacktestRunRead.model_validate(run)


@router.get("/{candidate_id}/backtest", response_model=list[PolicyBacktestRunRead])
def list_backtest_runs(
    candidate_id: UUID, session: Session = Depends(get_db)
) -> list[PolicyBacktestRunRead]:
    service.get_policy_candidate(session, candidate_id)  # 404s if the candidate doesn't exist
    runs = session.scalars(
        select(PolicyBacktestRunModel)
        .where(PolicyBacktestRunModel.policy_candidate_id == candidate_id)
        .order_by(PolicyBacktestRunModel.created_at.desc())
    ).all()
    return [PolicyBacktestRunRead.model_validate(run) for run in runs]
