"""Typed persistence boundary for candidates, validation reports, and findings.

These schemas prepare TASK-024. They are not wired to routes until TASK-020 and TASK-023 deliver
validated reports and economic-impact results.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from policy_analytics.validation.contract import (
    GateId,
    GateOutcome,
    IdentificationDesign,
    PolicyReadiness,
)
from policy_schemas.domain import EvidenceLevel
from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Scalar = str | int | float | bool


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LineageReference(ContractModel):
    kind: Literal[
        "analytical_dataset",
        "discovery_manifest",
        "candidate_artifact",
        "validation_report",
        "impact_report",
        "code",
        "configuration",
    ]
    uri: str = Field(min_length=1, max_length=1024)
    sha256: Sha256
    version: str | None = Field(default=None, max_length=128)


class AnalysisRunPersistence(ContractModel):
    id: UUID
    dataset_id: UUID
    dataset_version: int = Field(ge=1)
    analytical_dataset_version: str = Field(min_length=1, max_length=128)
    analytical_dataset_identity_sha256: Sha256
    code_version: str = Field(min_length=1, max_length=100)
    discovery_methodology_version: str = Field(min_length=1, max_length=128)
    outcome_definition_version: str = Field(min_length=1, max_length=64)
    validation_contract_version: str = Field(min_length=1, max_length=64)
    configuration: dict[str, object]
    random_seed: int = Field(ge=0, le=2**32 - 1)
    evaluated_hypotheses: int = Field(ge=1)
    lineage: tuple[LineageReference, ...] = Field(min_length=1)


class PatternCondition(ContractModel):
    feature: str = Field(min_length=1, max_length=128)
    operator: Literal["eq", "lt", "le", "gt", "ge"]
    value: Scalar


class CandidateMetric(ContractModel):
    split: Literal["development", "validation", "future_holdout"]
    n_population: int = Field(ge=1)
    n_exposed: int = Field(ge=1)
    support: float = Field(gt=0, le=1)
    exposed_mean: float
    comparison_mean: float
    raw_difference: float
    harm_per_booking: float
    historical_exposure: float


class CandidatePatternPersistence(ContractModel):
    id: UUID
    analysis_run_id: UUID
    candidate_key: str = Field(min_length=1, max_length=128)
    conditions: tuple[PatternCondition, ...] = Field(min_length=1)
    fit_split: Literal["development"]
    rank: int = Field(ge=1)
    rank_score: float
    actionability: str = Field(min_length=1, max_length=64)
    metrics: tuple[CandidateMetric, ...] = Field(min_length=1)
    warnings: tuple[str, ...] = ()
    artifact_sha256: Sha256
    persisted_at: datetime
    lineage: tuple[LineageReference, ...] = Field(min_length=1)


class EffectEstimatePersistence(ContractModel):
    value: float
    ci_low: float
    ci_high: float
    confidence_level: float = Field(gt=0, lt=1)
    method: str = Field(min_length=1, max_length=256)
    unit: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def point_inside_interval(self) -> "EffectEstimatePersistence":
        if not self.ci_low <= self.value <= self.ci_high:
            raise ValueError("point estimate must lie inside its interval")
        return self


class GateResultPersistence(ContractModel):
    gate_id: GateId
    outcome: GateOutcome
    detail: str = Field(min_length=1)


class ValidationMetadataPersistence(ContractModel):
    contract_version: str = Field(min_length=1, max_length=64)
    outcome_definition_version: str = Field(min_length=1, max_length=64)
    outcome_definition: str = Field(min_length=1)
    exposed_records: int = Field(ge=0)
    comparison_records: int = Field(ge=0)
    clustering_key: str = Field(min_length=1, max_length=128)
    raw_effect: EffectEstimatePersistence
    adjusted_effect: EffectEstimatePersistence | None = None
    adjusted_p_value: float | None = Field(default=None, ge=0, le=1)
    family_size: int | None = Field(default=None, ge=1)
    controlled_variables: tuple[str, ...] = ()
    potential_confounders: tuple[str, ...] = ()
    robustness_tests: tuple[str, ...] = ()
    temporal_stability: str = ""
    identification_design: IdentificationDesign
    gate_results: tuple[GateResultPersistence, ...] = Field(min_length=1)
    evidence_level: EvidenceLevel | None
    policy_readiness: PolicyReadiness
    failure_modes: tuple[str, ...] = ()
    recommended_validation: str = Field(min_length=1)
    warnings: tuple[str, ...] = ()
    permitted_language: str = Field(min_length=1)


class EconomicImpactPersistence(ContractModel):
    """Storage envelope only; computation and semantics remain owned by TASK-023/Statistics."""

    impact_contract_version: str = Field(min_length=1, max_length=64)
    outcome_name: str = Field(min_length=1, max_length=128)
    outcome_unit: str = Field(min_length=1, max_length=256)
    affected_records: int = Field(ge=0)
    per_record_effect: EffectEstimatePersistence
    historical_impact: EffectEstimatePersistence
    annualized_impact: EffectEstimatePersistence | None = None
    annualization_justified: bool
    materiality_pass: bool

    @model_validator(mode="after")
    def annualization_is_gated(self) -> "EconomicImpactPersistence":
        if (self.annualized_impact is not None) != self.annualization_justified:
            raise ValueError("annualized impact must exist exactly when annualization is justified")
        return self


class FindingPromotion(ContractModel):
    """Internal command; a rejected or unvalidated candidate cannot become a Finding."""

    candidate_id: UUID
    analysis_run_id: UUID
    dataset_id: UUID
    validation: ValidationMetadataPersistence
    impact: EconomicImpactPersistence
    lineage: tuple[LineageReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validation_must_publish(self) -> "FindingPromotion":
        if self.validation.evidence_level is None:
            raise ValueError("a rejected candidate cannot be promoted to Finding")
        return self
