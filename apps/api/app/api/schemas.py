from datetime import date, datetime
from typing import Any
from uuid import UUID

from policy_analytics.validation.contract import IdentificationDesign, PolicyReadiness
from policy_schemas.domain import (
    DataQualityRating,
    DatasetColumn,
    EvidenceLevel,
    FeatureTiming,
    FeedbackActionability,
    FeedbackCertainty,
    FeedbackCommitmentStrength,
    FeedbackNovelty,
    FeedbackTag,
    FindingLifecycleStatus,
    PolicyCandidateMode,
    PolicyCandidateStatus,
    ResourceStatus,
)
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class HealthResponse(ApiModel):
    status: str


class DatasetColumnProfileRead(ApiModel):
    """TASK-007. `semantic_type_guess` and `examples` are disclosed heuristics, not validated
    facts — see `policy_analytics.profiling.schema_profiler`'s module docstring. Distinct from
    `DatasetColumn` (`columns` below), which is TASK-008's feature-timing classification."""

    column_name: str
    inferred_type: str
    row_count: int
    missing_count: int
    missingness: float
    distinct_count: int
    min_value: str | None
    max_value: str | None
    semantic_type_guess: str
    examples: list[str]
    examples_suppressed: bool
    suspicious_values: list[str]
    suspicious_count: int


class DateCoverageRead(ApiModel):
    column_name: str
    min_date: str
    max_date: str


class ExcludedColumnRead(ApiModel):
    """Every column not usable as a `DECISION_TIME` explanatory feature, with why (`TASK-009`)."""

    column_name: str
    timing: FeatureTiming
    reason: str


class DataQualityReportRead(ApiModel):
    """`TASK-009`. Aggregates `TASK-007`/`TASK-008` output — see
    `policy_analytics.profiling.quality_report`'s module docstring for the rating's decision
    rules. `None` on `DatasetRead` means profiling/classification did not complete for this
    version, not that quality was assessed and found perfect."""

    row_count: int
    column_count: int
    duplicate_row_count: int
    distinct_row_count: int
    date_coverage: list[DateCoverageRead]
    detected_currencies: list[str]
    total_missing_cells: int
    overall_missingness: float
    columns_with_high_missingness: list[str]
    total_suspicious_values: int
    columns_with_suspicious_values: list[str]
    excluded_columns: list[ExcludedColumnRead]
    available_outcomes: list[str]
    usable_decision_variables: list[str]
    unknown_columns: list[str]
    constant_decision_variables: list[str]
    schema_warnings: list[str]
    rating: DataQualityRating
    rating_reasons: list[str]


class DatasetRead(ApiModel):
    id: UUID
    name: str
    source_filename: str
    version: int
    status: ResourceStatus
    checksum_sha256: str
    size_bytes: int
    content_type: str
    source_type: str
    columns: list[DatasetColumn]
    column_profiles: list[DatasetColumnProfileRead]
    quality_report: DataQualityReportRead | None
    created_at: datetime
    updated_at: datetime


class AnalysisRunCreate(ApiModel):
    dataset_id: UUID
    analytical_dataset_version: str = Field(min_length=1, max_length=128)
    analytical_dataset_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_version: str = Field(min_length=1, max_length=100)
    discovery_methodology_version: str = Field(min_length=1, max_length=128)
    outcome_definition_version: str = Field(min_length=1, max_length=64)
    validation_contract_version: str = Field(min_length=1, max_length=64)
    configuration: dict[str, Any] = Field(default_factory=dict)
    random_seed: int = Field(ge=0, le=2**32 - 1)
    evaluated_hypotheses: int = Field(ge=1)


class AnalysisRunRead(ApiModel):
    id: UUID
    dataset_id: UUID
    dataset_version: int
    analytical_dataset_version: str
    analytical_dataset_identity_sha256: str
    code_version: str
    discovery_methodology_version: str
    outcome_definition_version: str
    validation_contract_version: str
    configuration: dict[str, Any]
    random_seed: int
    evaluated_hypotheses: int
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime


class EffectEstimateRead(ApiModel):
    value: float
    ci_low: float
    ci_high: float
    confidence_level: float
    method: str
    unit: str


class FindingPatternRead(ApiModel):
    """What happened / where — §1, always shown; `conditions` is the collapsed technical
    definition, not the default reading path (the plain-language `title`/`summary` are).
    `rank`/`rank_score`/`actionability` are `TASK-016` audit metadata, not part of §1's required
    list but harmless to carry alongside it."""

    candidate_key: str
    conditions: list[dict[str, Any]]
    fit_split: str
    rank: int
    rank_score: float
    actionability: str


class FindingEvidenceRead(ApiModel):
    """How strong is the evidence — §1. `raw_effect` carries no interval by construction (must be
    displayed as "descriptive, unadjusted, no interval — not a validated estimate", never styled
    as a validated figure — §3); `adjusted_effect` is required whenever `evidence_level` is at
    least `adjusted_observational_association`, enforced upstream by `ValidationReport`."""

    raw_effect: EffectEstimateRead
    adjusted_effect: EffectEstimateRead | None
    controlled_variables: list[str]
    potential_confounders: list[str]
    robustness_tests: list[str]
    temporal_stability: str
    warnings: list[str]
    failure_modes: list[str]
    recommended_validation: str
    permitted_language: str


class FindingImpactRead(ApiModel):
    """Money at stake — §1. `affected_records` (not `exposed_records`) per Statistics'
    `HANDOFF-046` recommendation: it is the full combined-window population the pattern touches,
    the customer-relevant number. `materiality_pass` is shown as pass/fail only — the underlying
    threshold value is never exposed (§3, Statistics/Customer-Discovery owned, still a
    placeholder)."""

    impact_contract_version: str
    outcome_name: str
    outcome_unit: str
    affected_records: int
    per_record_effect: EffectEstimateRead
    historical_impact: EffectEstimateRead
    annualized_impact: EffectEstimateRead | None
    annualization_justified: bool
    materiality_pass: bool


class FindingRead(ApiModel):
    id: UUID
    dataset_id: UUID
    analysis_run_id: UUID
    candidate_pattern_id: UUID
    validation_report_id: UUID
    title: str
    summary: str
    title_template_version: str
    generated_at: datetime
    pattern: FindingPatternRead = Field(validation_alias="pattern_snapshot")
    exposed_records: int
    comparison_records: int
    clustering_key: str
    evidence_level: EvidenceLevel
    identification_design: IdentificationDesign
    evidence: FindingEvidenceRead = Field(validation_alias="validation_snapshot")
    impact: FindingImpactRead = Field(validation_alias="impact_snapshot")
    policy_readiness: PolicyReadiness
    lifecycle_status: FindingLifecycleStatus
    created_at: datetime
    updated_at: datetime


class UserRead(ApiModel):
    id: UUID
    email: str
    display_name: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class FindingFeedbackRead(ApiModel):
    """`TASK-035`. `created_by_user_id` identifies the internal reviewer who captured this, not
    the customer — see `docs/product/finding-feedback-contract.md` §4/§9 on `review_session`."""

    id: UUID
    finding_id: UUID
    created_by_user_id: UUID
    review_session: str
    captured_at: datetime
    novelty: FeedbackNovelty | None
    actionability: FeedbackActionability | None
    tags: list[FeedbackTag]
    customer_comment: str | None
    customer_certainty: FeedbackCertainty | None
    intended_action: str | None
    commitment_strength: FeedbackCommitmentStrength | None
    customer_owner: str | None
    internal_follow_up_owner: str | None
    follow_up_date: date | None
    created_at: datetime


class PolicyCandidateEvidenceRead(ApiModel):
    """`TASK-030` §6 — frozen copy of the source Finding's evidence state at generation time."""

    evidence_level: EvidenceLevel
    policy_readiness: PolicyReadiness
    validation_contract_version: str
    finding_generated_at: datetime


class PolicyCandidateBacktestResultRead(ApiModel):
    """`TASK-034`. Mirrors `BacktestResult.to_dict()`'s exact shape
    (`docs/analytics/policy-backtest-contract.md`) — every field name here is copied from the
    engine, not renamed."""

    backtest_contract_version: str
    outcome_name: str
    outcome_unit: str
    window: str
    affected_decisions: int
    avoided_bad_outcomes: int
    suppressed_good_outcomes: int
    bad_outcome_definition: str
    benefit: EffectEstimateRead
    benefit_is_adjusted: bool
    operational_cost_per_review_eur: float | None
    operational_cost: EffectEstimateRead | None
    net_effect: EffectEstimateRead
    net_effect_is_cost_exclusive: bool
    no_measurable_net_effect: bool
    methodology_disclosure: str


class PolicyCandidateRead(ApiModel):
    """`TASK-030`/`TASK-034`. `trigger_conditions` is always an immutable copy of the source
    Finding's own `pattern.conditions` (§2) — never independently editable."""

    id: UUID
    finding_id: UUID
    title: str
    rationale: str
    trigger_conditions: list[dict[str, Any]]
    effective_population: str | None
    scope_narrowing_features: list[str]
    mode: PolicyCandidateMode
    effective_from: date
    expected_benefit_snapshot: FindingImpactRead
    action_detail: str | None
    evidence_snapshot: PolicyCandidateEvidenceRead
    backtest_result: PolicyCandidateBacktestResultRead | None
    status: PolicyCandidateStatus
    rejection_reason: str | None
    retirement_reason: str | None
    blocked_by_source_lifecycle: bool
    created_at: datetime
    updated_at: datetime


class PolicyBacktestRunRead(ApiModel):
    id: UUID
    policy_candidate_id: UUID
    cost_per_review_eur: float | None
    status: ResourceStatus
    backtest_result: PolicyCandidateBacktestResultRead | None
    failure_reason: str | None
    created_at: datetime
