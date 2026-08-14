"""Statistical validation, evidence grading, and stability checks.

The preregistered rules live in `contract`, the deterministic decision functions in `grading`, and
the mandatory output format in `report`. Prose methodology: `docs/analytics/validation-contract.md`.
"""

from policy_analytics.validation.contract import (
    CONTRACT_VERSION,
    DEFAULT_THRESHOLDS,
    GATE_SPEC_BY_ID,
    GATE_SPECS,
    LANGUAGE_RULES,
    LEVEL_ORDER,
    LEVEL_REQUIREMENTS,
    BiasClass,
    FailureAction,
    GateId,
    GateOutcome,
    GateResult,
    GateSpec,
    IdentificationDesign,
    LanguageRule,
    PolicyReadiness,
    ValidationThresholds,
)
from policy_analytics.validation.grading import (
    assign_policy_readiness,
    benjamini_hochberg_adjusted,
    bootstrap_two_sided_p,
    classify_evidence_level,
    evidence_ceiling,
    survives_fdr,
    warnings_from,
)
from policy_analytics.validation.report import EffectEstimate, ValidationReport

__all__ = [
    "CONTRACT_VERSION",
    "DEFAULT_THRESHOLDS",
    "GATE_SPECS",
    "GATE_SPEC_BY_ID",
    "LANGUAGE_RULES",
    "LEVEL_ORDER",
    "LEVEL_REQUIREMENTS",
    "BiasClass",
    "EffectEstimate",
    "FailureAction",
    "GateId",
    "GateOutcome",
    "GateResult",
    "GateSpec",
    "IdentificationDesign",
    "LanguageRule",
    "PolicyReadiness",
    "ValidationReport",
    "ValidationThresholds",
    "assign_policy_readiness",
    "benjamini_hochberg_adjusted",
    "bootstrap_two_sided_p",
    "classify_evidence_level",
    "evidence_ceiling",
    "survives_fdr",
    "warnings_from",
]
