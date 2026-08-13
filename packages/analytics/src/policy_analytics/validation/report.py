"""Validation report contract (TASK-018).

The report is the only sanctioned output of validation. Constructing one re-derives the evidence
level from the gate results, so a report cannot claim more than its checks support. Mapping this
structure onto persisted findings is TASK-024 (Architect).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from policy_schemas.domain import EvidenceLevel

from policy_analytics.validation.contract import (
    CONTRACT_VERSION,
    LANGUAGE_RULES,
    LEVEL_ORDER,
    GateResult,
    IdentificationDesign,
    PolicyReadiness,
)
from policy_analytics.validation.grading import classify_evidence_level, warnings_from


@dataclass(frozen=True, slots=True)
class EffectEstimate:
    """A number is only reportable together with its interval and the method that produced it."""

    value: float
    ci_low: float
    ci_high: float
    confidence_level: float
    method: str
    unit: str

    def __post_init__(self) -> None:
        if not self.ci_low <= self.value <= self.ci_high:
            raise ValueError("point estimate must lie inside its interval")
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be strictly between 0 and 1")
        if not self.method or not self.unit:
            raise ValueError("effect estimates require a method and a unit")

    @property
    def excludes_zero(self) -> bool:
        return self.ci_low > 0.0 or self.ci_high < 0.0


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Required validation output for one candidate pattern."""

    candidate_id: str
    analysis_run_id: str
    dataset_version: str
    outcome_definition_version: str
    pattern_definition: str
    outcome_definition: str
    exposed_records: int
    comparison_records: int
    clustering_key: str
    raw_effect: EffectEstimate
    identification_design: IdentificationDesign
    gate_results: tuple[GateResult, ...]
    evidence_level: EvidenceLevel | None
    policy_readiness: PolicyReadiness
    recommended_validation: str
    adjusted_effect: EffectEstimate | None = None
    adjusted_p_value: float | None = None
    family_size: int | None = None
    controlled_variables: tuple[str, ...] = ()
    potential_confounders: tuple[str, ...] = ()
    robustness_tests: tuple[str, ...] = ()
    temporal_stability: str = ""
    failure_modes: tuple[str, ...] = ()
    contract_version: str = CONTRACT_VERSION
    warnings: tuple[str, ...] = field(init=False, default=())

    def __post_init__(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise ValueError(
                f"report was graded under contract {self.contract_version}; "
                f"this code implements {CONTRACT_VERSION}"
            )
        if self.exposed_records < 0 or self.comparison_records < 0:
            raise ValueError("record counts cannot be negative")
        if not self.recommended_validation:
            raise ValueError("every report must state the next validation step")

        derived = classify_evidence_level(self.gate_results, self.identification_design)
        if derived is not self.evidence_level:
            claimed = self.evidence_level.value if self.evidence_level else "rejected"
            supported = derived.value if derived else "rejected"
            raise ValueError(
                f"evidence level {claimed} is not supported by the gate results ({supported})"
            )
        if derived is None and self.policy_readiness is not PolicyReadiness.NOT_READY:
            raise ValueError("a rejected candidate cannot carry a policy readiness above NOT_READY")

        adjusted_required = derived is not None and LEVEL_ORDER.index(derived) >= LEVEL_ORDER.index(
            EvidenceLevel.ADJUSTED_OBSERVATIONAL
        )
        if adjusted_required:
            if self.adjusted_effect is None:
                raise ValueError("adjusted levels require an adjusted effect estimate")
            if not self.controlled_variables:
                raise ValueError("adjusted levels require the list of controlled variables")
        object.__setattr__(self, "warnings", warnings_from(self.gate_results))

    @property
    def permitted_language(self) -> str:
        """Strongest wording the API or UI may use for this report."""
        if self.evidence_level is None:
            return "Rejected candidate; no claim may be published."
        return LANGUAGE_RULES[self.evidence_level].permitted_claim

    def to_dict(self) -> dict[str, Any]:
        """Serialisable form for run artifacts and later persistence."""
        return {
            "contract_version": self.contract_version,
            "candidate_id": self.candidate_id,
            "analysis_run_id": self.analysis_run_id,
            "dataset_version": self.dataset_version,
            "outcome_definition_version": self.outcome_definition_version,
            "pattern_definition": self.pattern_definition,
            "outcome_definition": self.outcome_definition,
            "exposed_records": self.exposed_records,
            "comparison_records": self.comparison_records,
            "clustering_key": self.clustering_key,
            "raw_effect": _estimate_to_dict(self.raw_effect),
            "adjusted_effect": _estimate_to_dict(self.adjusted_effect),
            "adjusted_p_value": self.adjusted_p_value,
            "family_size": self.family_size,
            "controlled_variables": list(self.controlled_variables),
            "potential_confounders": list(self.potential_confounders),
            "robustness_tests": list(self.robustness_tests),
            "temporal_stability": self.temporal_stability,
            "identification_design": self.identification_design.value,
            "gate_results": [
                {
                    "gate_id": result.gate_id.value,
                    "outcome": result.outcome.value,
                    "detail": result.detail,
                }
                for result in self.gate_results
            ],
            "evidence_level": self.evidence_level.value if self.evidence_level else None,
            "policy_readiness": self.policy_readiness.value,
            "failure_modes": list(self.failure_modes),
            "recommended_validation": self.recommended_validation,
            "warnings": list(self.warnings),
            "permitted_language": self.permitted_language,
        }


def _estimate_to_dict(estimate: EffectEstimate | None) -> dict[str, Any] | None:
    if estimate is None:
        return None
    return {
        "value": estimate.value,
        "ci_low": estimate.ci_low,
        "ci_high": estimate.ci_high,
        "confidence_level": estimate.confidence_level,
        "method": estimate.method,
        "unit": estimate.unit,
    }
