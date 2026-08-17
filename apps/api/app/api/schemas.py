from datetime import datetime
from typing import Any
from uuid import UUID

from policy_analytics.validation.contract import IdentificationDesign, PolicyReadiness
from policy_schemas.domain import (
    DatasetColumn,
    EvidenceLevel,
    FindingLifecycleStatus,
    ResourceStatus,
)
from pydantic import BaseModel, ConfigDict, Field


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
