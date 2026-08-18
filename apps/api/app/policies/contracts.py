"""Persistence input contracts for Policy Candidates (`TASK-030`).

Field set and rules mirror `docs/product/policy-candidate-domain-model.md` §2-§7 exactly. Not
exposed as public routes — matches `app.findings.persistence`'s own boundary (`TASK-024`); the only
intended future caller is `TASK-031`'s generator, which does not exist yet.
"""

from __future__ import annotations

from datetime import date, datetime

from policy_analytics.validation.contract import PolicyReadiness
from policy_schemas.domain import EvidenceLevel, PolicyCandidateMode
from pydantic import Field, field_validator, model_validator

from app.findings.contracts import (
    ContractModel,
    EconomicImpactPersistence,
    EffectEstimatePersistence,
)

#: §1: "no code path today can produce an enforcement proposal, by construction, not by an
#: omitted feature." Enforced here as a real invariant, not left as a doc claim.
_REACHABLE_MODES = frozenset({PolicyCandidateMode.SHADOW})


class PolicyCandidateBacktestSnapshot(ContractModel):
    """§7 — mirrors `policy_analytics.backtest.contract.BacktestResult.to_dict()`'s exact shape.

    Reserved: nothing in this task populates it. A future caller attaching a real backtest result
    validates it through this model rather than writing an arbitrary dict to the JSONB column.
    """

    backtest_contract_version: str = Field(min_length=1, max_length=64)
    outcome_name: str = Field(min_length=1, max_length=128)
    outcome_unit: str = Field(min_length=1, max_length=256)
    window: str = Field(min_length=1)
    affected_decisions: int = Field(ge=0)
    avoided_bad_outcomes: int = Field(ge=0)
    suppressed_good_outcomes: int = Field(ge=0)
    bad_outcome_definition: str = Field(min_length=1)
    benefit: EffectEstimatePersistence
    benefit_is_adjusted: bool
    operational_cost_per_review_eur: float | None = None
    operational_cost: EffectEstimatePersistence | None = None
    net_effect: EffectEstimatePersistence
    net_effect_is_cost_exclusive: bool
    no_measurable_net_effect: bool
    methodology_disclosure: str = Field(min_length=1)

    @model_validator(mode="after")
    def both_sides_sum(self) -> PolicyCandidateBacktestSnapshot:
        if self.avoided_bad_outcomes + self.suppressed_good_outcomes != self.affected_decisions:
            raise ValueError(
                "avoided_bad_outcomes + suppressed_good_outcomes must equal affected_decisions"
            )
        return self


class PolicyCandidateEvidenceSnapshot(ContractModel):
    """§6 — frozen copy of the source Finding's evidence state at generation time."""

    evidence_level: EvidenceLevel
    policy_readiness: PolicyReadiness
    validation_contract_version: str = Field(min_length=1, max_length=64)
    finding_generated_at: datetime


class PolicyCandidateCreate(ContractModel):
    """§2-§7's persistence input. `trigger_conditions`/`evidence_snapshot` are deliberately not
    accepted here — `app.policies.service.create_draft_policy_candidate` derives both from the
    source Finding directly, never from caller input (§2: "the generator may not edit ... this
    condition set")."""

    title: str = Field(min_length=1, max_length=240)
    rationale: str = Field(min_length=1)
    effective_population: str | None = Field(default=None, min_length=1)
    scope_narrowing_features: tuple[str, ...] = ()
    mode: PolicyCandidateMode = PolicyCandidateMode.SHADOW
    effective_from: date
    expected_benefit_snapshot: EconomicImpactPersistence
    action_detail: str | None = Field(default=None, min_length=1)

    @field_validator("mode")
    @classmethod
    def mode_is_reachable(cls, value: PolicyCandidateMode) -> PolicyCandidateMode:
        if value not in _REACHABLE_MODES:
            raise ValueError(
                f"{value} is not reachable today (§1) — no code path may produce an "
                "enforcement proposal"
            )
        return value
