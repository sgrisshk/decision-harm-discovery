"""Policy Candidate generation (`TASK-031`).

Implements `docs/product/policy-candidate-domain-model.md` §12's generation procedure exactly:
manually triggered, idempotent per Finding, deterministic per-Finding output, `action_detail`
starts unset, every skipped Finding is disclosed with a reason. Delegates all eligibility/
idempotency/guardrail decisions to `app.policies.service.create_draft_policy_candidate`
(`TASK-030`, `ADR-029`) — this module adds no new rule of its own, only orchestrates batch/single
runs over it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from policy_schemas.domain import FindingLifecycleStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FindingModel
from app.findings.contracts import EconomicImpactPersistence
from app.policies.contracts import PolicyCandidateCreate
from app.policies.service import PolicyCandidateError, create_draft_policy_candidate


@dataclass(frozen=True, slots=True)
class GenerationSkip:
    finding_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class GenerationReport:
    created: tuple[UUID, ...]
    skipped: tuple[GenerationSkip, ...]


def _build_payload(finding: FindingModel) -> PolicyCandidateCreate:
    """§3/§12's literal defaults: `effective_population`/`scope_narrowing_features` unset, `mode`
    fixed to `SHADOW` (the `PolicyCandidateCreate` default), `action_detail` unset (§12: "the
    generator's own output has `action_detail = null`"). `title`/`rationale` reuse the Finding's
    own mechanical `title`/`summary` verbatim — neither field is specified by §0-§12 (both predate
    the domain model, part of the original `PolicyCandidateModel` skeleton), and direct reuse is
    the simplest choice consistent with "no new numbers invented" rather than a second, duplicate
    mechanical-template generator."""
    return PolicyCandidateCreate(
        title=finding.title,
        rationale=finding.summary,
        effective_from=datetime.now(UTC).date(),
        expected_benefit_snapshot=EconomicImpactPersistence.model_validate(finding.impact_snapshot),
    )


def generate_policy_candidates(
    session: Session,
    *,
    finding_ids: tuple[UUID, ...] | None = None,
    force: bool = False,
) -> GenerationReport:
    """§12: batch (every `ACTIVE` Finding, when `finding_ids` is `None`) or single/explicit
    (`finding_ids` given). `force=True` is only meaningful — and only ever passed by the CLI — for
    an explicit single-Finding call (§12: "additional candidates only from explicit human review
    action, never automatic proliferation"); batch mode always calls with `force=False`.
    """
    if finding_ids is None:
        findings: list[FindingModel] = list(
            session.scalars(
                select(FindingModel).where(
                    FindingModel.lifecycle_status == FindingLifecycleStatus.ACTIVE.value
                )
            ).all()
        )
        missing: tuple[GenerationSkip, ...] = ()
    else:
        findings = []
        missing_list: list[GenerationSkip] = []
        for finding_id in finding_ids:
            finding = session.get(FindingModel, finding_id)
            if finding is None:
                missing_list.append(GenerationSkip(finding_id, "no finding with this id exists"))
            else:
                findings.append(finding)
        missing = tuple(missing_list)

    created: list[UUID] = []
    skipped: list[GenerationSkip] = list(missing)
    for finding in findings:
        payload = _build_payload(finding)
        try:
            candidate = create_draft_policy_candidate(session, finding, payload, force=force)
        except PolicyCandidateError as exc:
            skipped.append(GenerationSkip(finding.id, str(exc)))
        else:
            created.append(candidate.id)

    session.commit()
    return GenerationReport(created=tuple(created), skipped=tuple(skipped))
