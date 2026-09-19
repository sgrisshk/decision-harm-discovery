"""Typed persistence boundary for candidates, validation reports, and findings.

These schemas prepare TASK-024. They are not wired to routes until TASK-020 and TASK-023 deliver
validated reports and economic-impact results.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from policy_analytics.validation.contract import (
    GateId,
    GateOutcome,
    IdentificationDesign,
    PolicyReadiness,
)
from policy_analytics.validation.economic_impact import (
    TIER_1_POPULATION_SCOPE,
    TIER_1_QUANTITY_NAME,
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


class CandidateExposureTierPersistence(ContractModel):
    """Storage envelope for one tier (1 or 2) of `economic_impact.CandidateExposureResult`
    (`O1` — observed candidate exposure, `TASK-085` §5.2, `TASK-086`/`ADR-089`). Field-for-field
    match to `CandidateExposureResult.to_dict()`; computation and semantics remain owned by
    `TASK-023`/`TASK-085`/Statistics — this is a storage envelope only, exactly like the `v1`
    shape it replaces."""

    exposure_contract_version: str = Field(min_length=1, max_length=64)
    tier: Literal[1, 2]
    population_scope: str = Field(min_length=1, max_length=64)
    quantity_name: str = Field(min_length=1, max_length=128)
    outcome_name: str = Field(min_length=1, max_length=128)
    outcome_unit: str = Field(min_length=1, max_length=256)
    affected_records: int = Field(ge=0)
    per_record_effect: EffectEstimatePersistence
    candidate_exposure: EffectEstimatePersistence
    annualized_candidate_exposure: EffectEstimatePersistence | None = None
    annualization_justified: bool
    materiality_pass: bool

    @model_validator(mode="after")
    def annualization_is_gated(self) -> "CandidateExposureTierPersistence":
        if (self.annualized_candidate_exposure is not None) != self.annualization_justified:
            raise ValueError(
                "annualized candidate exposure must exist exactly when annualization is justified"
            )
        return self


class AttributableImpactPersistence(ContractModel):
    """Storage envelope for `economic_impact.AttributableImpactResult` (`O2` — attributable
    harmful impact, `TASK-085` §5.2 tier 3). Field-for-field match to
    `AttributableImpactResult.to_dict()`. Always `None` on `EconomicImpactPersistence` in this
    project's own history today — tier 3 is the disclosed "always-empty slot"
    (`build_attributable_impact_result` returns `None` for every real candidate, since `apply.py`
    hardcodes `G13`/`G14` to `FAIL`) — but the shape is real and this model is exercised directly
    by unit tests even though no live payload populates it yet."""

    exposure_contract_version: str = Field(min_length=1, max_length=64)
    tier: Literal[3] = 3
    population_scope: Literal["A"] = "A"
    quantity_name: Literal["attributable_harmful_impact"] = "attributable_harmful_impact"
    outcome_name: str = Field(min_length=1, max_length=128)
    outcome_unit: str = Field(min_length=1, max_length=256)
    affected_records: int = Field(ge=0)
    per_record_effect: EffectEstimatePersistence
    attributable_impact: EffectEstimatePersistence
    identification_gate: GateId
    materiality_pass: bool


def normalize_economic_impact_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Version-dispatch a persisted economic-impact payload to the `v2.0.0` tiered shape, mirroring
    `economic_impact.load_candidate_exposure_result`'s own dispatch (`TASK-086`'s migration
    discipline, `ADR-015`/`ADR-064` precedent: a payload is parsed under **its own recorded
    contract version**, never silently re-graded, never re-versioned).

    A `v2.0.0`+ payload (`exposure_contract_version` key present, `tier1`/`tier2`/
    `reportable_tiers`/`attributable_impact` shape) passes through unchanged. A legacy `v1.x`
    payload (`impact_contract_version` key, flat `historical_impact`) is wrapped as **tier 1** —
    `TASK-085` §7's own stated equivalence that `v1`'s sole computation always *was* tier 1's
    unchanged quantity over `E`, before `TASK-086`'s rename gave it an honest name. The legacy
    payload's own `impact_contract_version` string is preserved verbatim as the returned
    `exposure_contract_version`, so a reader can always tell which contract version actually
    graded this artifact.
    """
    if "exposure_contract_version" in data:
        return data
    if "impact_contract_version" in data:
        tier1 = {
            "exposure_contract_version": data["impact_contract_version"],
            "tier": 1,
            "population_scope": TIER_1_POPULATION_SCOPE,
            "quantity_name": TIER_1_QUANTITY_NAME,
            "outcome_name": data["outcome_name"],
            "outcome_unit": data["outcome_unit"],
            "affected_records": data["affected_records"],
            "per_record_effect": data["per_record_effect"],
            "candidate_exposure": data["historical_impact"],
            "annualized_candidate_exposure": data.get("annualized_impact"),
            "annualization_justified": data["annualization_justified"],
            "materiality_pass": data["materiality_pass"],
        }
        return {
            "exposure_contract_version": data["impact_contract_version"],
            "tier1": tier1,
            "tier2": None,
            # A v1.x record was only ever written for a promoted (evidence_level is not None)
            # Finding, i.e. at least `descriptive_observation` -- tier 1's own threshold -- so
            # tier 1 was always reportable. Never inferred as tier 2: v1 never computed E_dev.
            "reportable_tiers": [1],
            "attributable_impact": None,
        }
    raise ValueError(
        "economic-impact payload has neither 'exposure_contract_version' nor "
        "'impact_contract_version'; cannot determine which contract version graded it"
    )


class EconomicImpactPersistence(ContractModel):
    """Storage envelope for `economic_impact`'s tiered `v2.0.0` shape (`TASK-085` §5.2/§7,
    `TASK-086`/`ADR-089`, `TASK-088`). Computation and semantics remain owned by
    `TASK-023`/`TASK-086`/Statistics — this model only gives their already-computed
    `CandidateExposureResult`/`AttributableImpactResult` output a persisted, versioned shape.

    Not a re-flattening back to `v1`'s single `historical_impact` figure: `tier1`/`tier2` are
    carried as distinct, both-correct numbers over different populations (`TASK-085` §5.2), and
    `reportable_tiers` records which of them this candidate's own evidence level actually cleared
    for display (`CandidateValidation.reportable_exposure_tiers`) — never re-derived here from a
    proxy. `tier1`/`tier2` are `None` only defensively; in this project's real pipeline
    (`apply.py`) both are always computed for every candidate. `attributable_impact` (tier 3, `O2`)
    is always `None` in this project's own history — the disclosed "always-empty slot" — never
    bridged by a fallback.

    A legacy `v1.x` payload validates here too, via `normalize_economic_impact_payload`'s
    before-validator: it is wrapped as tier 1 under its own recorded version, never silently
    reinterpreted as a newly invented tier (`TASK-088`'s migration requirement, matching
    `ADR-015`/`ADR-064` precedent) -- see `load_candidate_exposure_result`'s identical dispatch in
    `economic_impact.py` for the analytics-side half of this same discipline.
    """

    exposure_contract_version: str | None = None
    tier1: CandidateExposureTierPersistence | None = None
    tier2: CandidateExposureTierPersistence | None = None
    reportable_tiers: tuple[int, ...] = ()
    attributable_impact: AttributableImpactPersistence | None = None

    @model_validator(mode="before")
    @classmethod
    def _dispatch_contract_version(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return normalize_economic_impact_payload(data)
        return data


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
