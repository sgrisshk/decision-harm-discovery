"""Persistence services for Policy Candidates (`TASK-030`/`TASK-034`).

`create_draft_policy_candidate`/`transition_policy_candidate`/`cascade_finding_lifecycle_change`
were written internal-only (mirroring `app.findings.persistence`), with `TASK-031`'s generator as
their only intended caller. `TASK-034` is the first consumer that needs reads over HTTP —
`list_policy_candidates`/`get_policy_candidate` below follow `app.findings.service`'s own
route-facing style (raising `HTTPException` directly) rather than the framework-agnostic
`PolicyCandidateError` the write functions above use — `app.policies.routes` is the boundary that
translates the latter into an HTTP response, exactly like `app.findings.routes` does for its own
persistence-layer errors.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from policy_analytics.validation.contract import PolicyReadiness
from policy_schemas.domain import EvidenceLevel, FindingLifecycleStatus, PolicyCandidateStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FindingModel, PolicyCandidateModel, ValidationReportModel
from app.findings.contracts import PatternCondition
from app.policies.contracts import PolicyCandidateCreate, PolicyCandidateEvidenceSnapshot

#: §8's forward-only adjacency. A status not present as a key has no legal outgoing transition
#: (both terminal states, `REJECTED`/`RETIRED`).
_TRANSITIONS: dict[PolicyCandidateStatus, frozenset[PolicyCandidateStatus]] = {
    PolicyCandidateStatus.DRAFT: frozenset({PolicyCandidateStatus.UNDER_REVIEW}),
    PolicyCandidateStatus.UNDER_REVIEW: frozenset(
        {PolicyCandidateStatus.REJECTED, PolicyCandidateStatus.APPROVED_SHADOW}
    ),
    PolicyCandidateStatus.APPROVED_SHADOW: frozenset(
        {PolicyCandidateStatus.APPROVED_FOR_CUSTOMER_DECISION, PolicyCandidateStatus.RETIRED}
    ),
    PolicyCandidateStatus.APPROVED_FOR_CUSTOMER_DECISION: frozenset(
        {PolicyCandidateStatus.RETIRED}
    ),
}

#: §1 — eligibility gate. `HIGH_CONFIDENCE` is structurally allowed but currently unreachable
#: system-wide (no backtest exists to produce it) — a real fact, not enforced here as a second gate.
_ELIGIBLE_READINESS = frozenset({"shadow_policy", "high_confidence"})

_REASON_REQUIRED = frozenset({PolicyCandidateStatus.REJECTED, PolicyCandidateStatus.RETIRED})


class PolicyCandidateError(ValueError):
    """A candidate creation or transition violates the domain model."""


def create_draft_policy_candidate(
    session: Session,
    finding: FindingModel,
    payload: PolicyCandidateCreate,
    *,
    force: bool = False,
) -> PolicyCandidateModel:
    """§1 eligibility, §2 verbatim trigger copy, §3 confounder-scope guardrail, §6/§12 one
    candidate per Finding by default. Raises `PolicyCandidateError` on any violation."""
    if finding.lifecycle_status != FindingLifecycleStatus.ACTIVE.value:
        raise PolicyCandidateError(
            f"finding {finding.id} is {finding.lifecycle_status}, not ACTIVE — "
            "cannot generate a candidate from it"
        )
    if finding.policy_readiness not in _ELIGIBLE_READINESS:
        raise PolicyCandidateError(
            f"finding {finding.id} has policy_readiness={finding.policy_readiness!r}, "
            f"not eligible (§1: requires one of {sorted(_ELIGIBLE_READINESS)})"
        )

    potential_confounders = frozenset(finding.validation_snapshot.get("potential_confounders", ()))
    narrowed_by_confounders = set(payload.scope_narrowing_features) & potential_confounders
    if narrowed_by_confounders:
        raise PolicyCandidateError(
            "scope_narrowing_features may not include a variable the source finding's validation "
            f"flagged as a potential confounder (§3): {sorted(narrowed_by_confounders)}"
        )

    if not force:
        existing = session.scalars(
            select(PolicyCandidateModel).where(PolicyCandidateModel.finding_id == finding.id)
        ).first()
        if existing is not None:
            raise PolicyCandidateError(
                f"finding {finding.id} already has a policy candidate ({existing.id}) — "
                "pass force=True for an explicit additional candidate (§6/§12)"
            )

    trigger_conditions = [
        PatternCondition.model_validate(condition).model_dump(mode="json")
        for condition in finding.pattern_snapshot["conditions"]
    ]

    report = session.get(ValidationReportModel, finding.validation_report_id)
    if report is None:  # pragma: no cover - defense in depth, FK guarantees this can't happen
        raise PolicyCandidateError(f"validation report for finding {finding.id} is missing")
    evidence_snapshot = PolicyCandidateEvidenceSnapshot(
        evidence_level=EvidenceLevel(finding.evidence_level),
        policy_readiness=PolicyReadiness(finding.policy_readiness),
        validation_contract_version=report.contract_version,
        finding_generated_at=finding.generated_at,
    )

    model = PolicyCandidateModel(
        id=uuid4(),
        finding_id=finding.id,
        title=payload.title,
        rationale=payload.rationale,
        trigger_conditions=trigger_conditions,
        effective_population=payload.effective_population,
        scope_narrowing_features=list(payload.scope_narrowing_features),
        mode=payload.mode.value,
        effective_from=payload.effective_from,
        expected_benefit_snapshot=payload.expected_benefit_snapshot.model_dump(mode="json"),
        action_detail=payload.action_detail,
        evidence_snapshot=evidence_snapshot.model_dump(mode="json"),
        backtest_result=None,
        status=PolicyCandidateStatus.DRAFT.value,
    )
    session.add(model)
    session.flush()
    return model


def transition_policy_candidate(
    session: Session,
    candidate: PolicyCandidateModel,
    new_status: PolicyCandidateStatus,
    *,
    reason: str | None = None,
) -> PolicyCandidateModel:
    """Enforces §8's forward-only adjacency plus each transition's entry condition. Raises
    `PolicyCandidateError` on any violation — never silently no-ops or coerces."""
    current = PolicyCandidateStatus(candidate.status)
    legal = _TRANSITIONS.get(current, frozenset())
    if new_status not in legal:
        raise PolicyCandidateError(f"{current} -> {new_status} is not a legal transition (§8)")

    if candidate.blocked_by_source_lifecycle:
        raise PolicyCandidateError(
            f"candidate {candidate.id} is blocked — its source finding is no longer ACTIVE (§6); "
            "a human must review the change before this candidate can advance"
        )

    if new_status == PolicyCandidateStatus.UNDER_REVIEW and not candidate.action_detail:
        raise PolicyCandidateError(
            "action_detail must be human-authored before DRAFT -> UNDER_REVIEW (§8)"
        )

    if new_status in _REASON_REQUIRED and not reason:
        raise PolicyCandidateError(f"a reason is required to transition to {new_status} (§8)")

    candidate.status = new_status.value
    if new_status == PolicyCandidateStatus.REJECTED:
        candidate.rejection_reason = reason
    if new_status == PolicyCandidateStatus.RETIRED:
        candidate.retirement_reason = reason

    session.flush()
    return candidate


def cascade_finding_lifecycle_change(
    session: Session, finding_id: UUID
) -> list[PolicyCandidateModel]:
    """§6: if the source Finding is no longer `ACTIVE`, every referencing candidate is affected —
    `DRAFT`/`UNDER_REVIEW` are blocked from advancing further (never silently changed), and any
    `APPROVED_SHADOW`/`APPROVED_FOR_CUSTOMER_DECISION` is auto-retired.

    **Not wired to any live trigger point today** — nothing in this codebase currently transitions
    a Finding's `lifecycle_status` away from `ACTIVE` (no supersede/withdraw endpoint exists yet).
    This function is built and tested directly so it is ready the moment one does, per
    `HANDOFF-049`'s "service-layer check, not a DB trigger" answer — it is not called from
    anywhere in production yet, and that gap is disclosed, not hidden.
    """
    finding = session.get(FindingModel, finding_id)
    if finding is None or finding.lifecycle_status == FindingLifecycleStatus.ACTIVE.value:
        return []

    affected: list[PolicyCandidateModel] = []
    candidates = session.scalars(
        select(PolicyCandidateModel).where(PolicyCandidateModel.finding_id == finding_id)
    ).all()
    for candidate in candidates:
        status = PolicyCandidateStatus(candidate.status)
        if status in {PolicyCandidateStatus.DRAFT, PolicyCandidateStatus.UNDER_REVIEW}:
            candidate.blocked_by_source_lifecycle = True
            affected.append(candidate)
        elif status in {
            PolicyCandidateStatus.APPROVED_SHADOW,
            PolicyCandidateStatus.APPROVED_FOR_CUSTOMER_DECISION,
        }:
            candidate.status = PolicyCandidateStatus.RETIRED.value
            candidate.retirement_reason = "source finding no longer active"
            affected.append(candidate)
        # REJECTED/RETIRED are already terminal — nothing to do.

    session.flush()
    return affected


def list_policy_candidates(
    session: Session, finding_id: UUID | None = None
) -> list[PolicyCandidateModel]:
    statement = select(PolicyCandidateModel).order_by(PolicyCandidateModel.created_at.desc())
    if finding_id is not None:
        statement = statement.where(PolicyCandidateModel.finding_id == finding_id)
    return list(session.scalars(statement))


def get_policy_candidate(session: Session, candidate_id: UUID) -> PolicyCandidateModel:
    candidate = session.get(PolicyCandidateModel, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy candidate not found"
        )
    return candidate
