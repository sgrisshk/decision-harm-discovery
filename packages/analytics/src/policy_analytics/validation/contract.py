"""Preregistered validation and evidence contract (TASK-018).

This module is the executable half of ``docs/validation_contract.md``: the vocabulary, the
preregistered thresholds, and the ordered gate specification that every candidate pattern must
survive before a finding may be published.

It deliberately contains no estimation code. Computing effects, intervals, and gate outcomes for
persisted candidates is TASK-019; this module only fixes the rules *before* any candidate is seen.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from policy_schemas.domain import EvidenceLevel

CONTRACT_VERSION = "1.0.0"


class BiasClass(StrEnum):
    """Family of inferential failure a gate is responsible for detecting."""

    LINEAGE = "lineage"
    LEAKAGE = "leakage"
    POST_TREATMENT = "post_treatment"
    SAMPLE = "sample"
    UNCERTAINTY = "uncertainty"
    MULTIPLICITY = "multiplicity"
    CONFOUNDING = "confounding"
    SELECTION = "selection"
    SURVIVORSHIP = "survivorship"
    HETEROGENEITY = "heterogeneity"
    TEMPORAL = "temporal"
    SEASONALITY = "seasonality"
    ROBUSTNESS = "robustness"
    IDENTIFICATION = "identification"
    ECONOMIC = "economic"


class GateOutcome(StrEnum):
    """Result of a single gate.

    ``WARN`` means the gate is satisfied but produced a caveat that must be surfaced in the
    finding. It never raises or lowers the evidence ceiling. ``NOT_EVALUATED`` is treated exactly
    like ``FAIL``: an unrun check is not a passed check.
    """

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NOT_EVALUATED = "not_evaluated"


class FailureAction(StrEnum):
    """What a failed gate does to the candidate."""

    REJECT = "reject"
    CAP_EVIDENCE = "cap_evidence"
    READINESS_ONLY = "readiness_only"


class IdentificationDesign(StrEnum):
    """How the exposure was assigned; hard ceiling on any causal claim."""

    OBSERVATIONAL = "observational"
    QUASI_EXPERIMENTAL = "quasi_experimental"
    RANDOMIZED_PROSPECTIVE = "randomized_prospective"


class PolicyReadiness(StrEnum):
    """What a business is allowed to do with the finding."""

    NOT_READY = "not_ready"
    EXPERIMENT_ONLY = "experiment_only"
    SHADOW_POLICY = "shadow_policy"
    HIGH_CONFIDENCE = "high_confidence"


class GateId(StrEnum):
    """Stable identifiers; persisted in validation reports and never renumbered."""

    LINEAGE = "G00_LINEAGE_PREREGISTRATION"
    TARGET_LEAKAGE = "G01_TARGET_LEAKAGE"
    POST_TREATMENT = "G02_POST_TREATMENT_CONTROLS"
    SAMPLE = "G03_SAMPLE_ADEQUACY"
    UNCERTAINTY = "G04_UNCERTAINTY"
    MULTIPLICITY = "G05_MULTIPLE_COMPARISONS"
    CONFOUNDING = "G06_CONFOUNDING"
    SELECTION_COLLIDER = "G07_SELECTION_AND_COLLIDER"
    SURVIVORSHIP = "G08_SURVIVORSHIP_COHORT"
    SIMPSON = "G09_SIMPSON_AND_HETEROGENEITY"
    TEMPORAL_STABILITY = "G10_TEMPORAL_STABILITY"
    SEASONALITY = "G11_SEASONALITY"
    ROBUSTNESS = "G12_ROBUSTNESS"
    IDENTIFICATION = "G13_IDENTIFICATION_DESIGN"
    RANDOMIZATION = "G14_RANDOMIZATION_INTEGRITY"
    ECONOMIC_MATERIALITY = "G15_ECONOMIC_MATERIALITY"


@dataclass(frozen=True, slots=True)
class ValidationThresholds:
    """Numeric rules fixed before any candidate is inspected.

    Changing any value requires a new ``CONTRACT_VERSION`` and re-validation of every finding
    graded under the old version. Values are pilot defaults tuned to the synthetic benchmark scale
    (10k bookings, 24 months); the materiality thresholds must be re-set per customer.
    """

    version: str = CONTRACT_VERSION
    # Sample adequacy. The substantive rule is power, not headcount: a flat record floor
    # discards small-but-detectable patterns and admits large-but-noisy ones. The floor exists
    # only so the cluster bootstrap and stratified checks remain meaningful.
    min_exposed_records: int = 50
    min_outcome_events_binary: int = 25
    min_clusters: int = 5
    power_target: float = 0.80
    # Uncertainty
    bootstrap_resamples: int = 2000
    confidence_level: float = 0.95
    # Multiplicity
    fdr_alpha: float = 0.10
    # Confounding
    max_adjusted_attenuation: float = 0.50
    min_e_value: float = 1.50
    # Selection
    max_outcome_missingness_rate: float = 0.20
    max_outcome_missingness_gap: float = 0.05
    # Heterogeneity
    simpson_reversal_exposure_share: float = 0.20
    # Temporal
    required_same_sign_splits: int = 3
    min_holdout_effect_retention: float = 0.50
    # Seasonality
    seasonal_concentration_index: float = 1.50
    # Robustness
    min_robustness_sign_agreement: float = 0.90
    max_robustness_magnitude_deviation: float = 0.50
    # Economic materiality
    min_annualization_months: int = 12
    min_material_annual_impact: float = 25_000.0
    min_material_outcome_share: float = 0.005

    def __post_init__(self) -> None:
        if self.min_exposed_records < 30:
            raise ValueError("min_exposed_records below 30 makes the cluster bootstrap unreliable")
        if not 0.5 < self.power_target < 1.0:
            raise ValueError("power_target must be between 0.5 and 1")
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be strictly between 0 and 1")
        if not 0.0 < self.fdr_alpha < 1.0:
            raise ValueError("fdr_alpha must be strictly between 0 and 1")
        if self.bootstrap_resamples < 1000:
            raise ValueError("bootstrap_resamples must be at least 1000 for stable tail estimates")
        if not 0.0 < self.max_adjusted_attenuation <= 1.0:
            raise ValueError("max_adjusted_attenuation must be in (0, 1]")
        if self.min_e_value < 1.0:
            raise ValueError("min_e_value must be at least 1.0")
        if self.required_same_sign_splits < 1:
            raise ValueError("required_same_sign_splits must be at least 1")
        if any(
            value < 0.0
            for value in (
                self.min_material_annual_impact,
                self.min_material_outcome_share,
                self.max_outcome_missingness_rate,
                self.max_outcome_missingness_gap,
            )
        ):
            raise ValueError("rate and materiality thresholds must be non-negative")


DEFAULT_THRESHOLDS = ValidationThresholds()


@dataclass(frozen=True, slots=True)
class GateSpec:
    """One mandatory check, its rule, and the consequence of failing it."""

    gate_id: GateId
    name: str
    bias_class: BiasClass
    question: str
    rule: str
    on_failure: FailureAction
    max_level_on_failure: EvidenceLevel | None = None

    def __post_init__(self) -> None:
        capped = self.on_failure is FailureAction.CAP_EVIDENCE
        if capped and self.max_level_on_failure is None:
            raise ValueError(f"{self.gate_id} caps evidence but declares no ceiling")
        if not capped and self.max_level_on_failure is not None:
            raise ValueError(f"{self.gate_id} declares a ceiling but does not cap evidence")


GATE_SPECS: tuple[GateSpec, ...] = (
    GateSpec(
        gate_id=GateId.LINEAGE,
        name="Lineage and preregistration integrity",
        bias_class=BiasClass.LINEAGE,
        question="Was this candidate fixed, with its dataset and code, before validation ran?",
        rule=(
            "Candidate file is PERSISTED with a timestamp preceding the validation run; dataset "
            "version, code version, seed, split manifest, outcome-definition version, and "
            "contract version are all recorded and resolvable."
        ),
        on_failure=FailureAction.REJECT,
    ),
    GateSpec(
        gate_id=GateId.TARGET_LEAKAGE,
        name="Target leakage",
        bias_class=BiasClass.LEAKAGE,
        question="Does the pattern use information unavailable at the decision timestamp?",
        rule=(
            "Every variable in the pattern condition is classified DECISION_TIME and observed at "
            "or before the decision timestamp. Any POST_DECISION, OUTCOME, or UNKNOWN variable, "
            "or any variable that is an algebraic component of the outcome, fails the gate. "
            "Definitional dependencies that survive review are recorded as WARN with the "
            "mechanical relationship stated."
        ),
        on_failure=FailureAction.REJECT,
    ),
    GateSpec(
        gate_id=GateId.POST_TREATMENT,
        name="Post-treatment controls",
        bias_class=BiasClass.POST_TREATMENT,
        question="Does the adjustment set contain anything caused by the exposure?",
        rule=(
            "The adjustment set contains only DECISION_TIME variables that are not descendants of "
            "the exposure in the declared DAG. Mediators and post-decision events are excluded; "
            "if a mediator is analysed deliberately, it is reported as a separate decomposition, "
            "never as the adjusted total effect."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.PREDICTIVE,
    ),
    GateSpec(
        gate_id=GateId.SAMPLE,
        name="Sample adequacy",
        bias_class=BiasClass.SAMPLE,
        question="Could this analysis have detected an effect worth acting on?",
        rule=(
            "The minimum detectable effect at power_target, computed from the observed outcome "
            "variance and the exposed/comparison sizes, is no larger than the materiality "
            "threshold: an analysis that cannot see an actionable effect has not tested for one. "
            "Below the floors — min_exposed_records exposed records, min_outcome_events_binary "
            "events in the exposed group for binary outcomes, min_clusters distinct clusters on "
            "the clustering key — the candidate is not analysable at all. The minimum detectable "
            "effect is reported whether or not the gate passes."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.DESCRIPTIVE,
    ),
    GateSpec(
        gate_id=GateId.UNCERTAINTY,
        name="Uncertainty interval",
        bias_class=BiasClass.UNCERTAINTY,
        question="Is the effect distinguishable from noise under dependence?",
        rule=(
            "Cluster bootstrap over the clustering key with bootstrap_resamples replicates and "
            "the run seed; percentile interval at confidence_level excludes zero. Point estimates "
            "without an interval never satisfy this gate."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.DESCRIPTIVE,
    ),
    GateSpec(
        gate_id=GateId.MULTIPLICITY,
        name="Multiple comparisons",
        bias_class=BiasClass.MULTIPLICITY,
        question="Does the effect survive the size of the search that produced it?",
        rule=(
            "Benjamini-Hochberg control at fdr_alpha over a family whose size is the number of "
            "hypotheses discovery actually evaluated, not the number it reported. The evaluated "
            "count comes from the discovery run manifest; when it is missing, the candidate "
            "cannot pass this gate."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.DESCRIPTIVE,
    ),
    GateSpec(
        gate_id=GateId.CONFOUNDING,
        name="Observed confounding",
        bias_class=BiasClass.CONFOUNDING,
        question="Does the effect survive adjustment for prespecified common causes?",
        rule=(
            "A DAG and its minimal adjustment set are declared before estimation. The adjusted "
            "interval excludes zero, keeps the sign of the raw effect, and retains at least "
            "(1 - max_adjusted_attenuation) of the raw magnitude. The E-value for the adjusted "
            "estimate is at least min_e_value and exceeds the strongest measured "
            "confounder-outcome association."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.PREDICTIVE,
    ),
    GateSpec(
        gate_id=GateId.SELECTION_COLLIDER,
        name="Selection and collider bias",
        bias_class=BiasClass.SELECTION,
        question="Is inclusion in the analysed sample independent of the outcome?",
        rule=(
            "Outcome missingness is at most max_outcome_missingness_rate overall and differs "
            "between exposed and comparison groups by at most max_outcome_missingness_gap. "
            "Missingness that depends on the outcome requires worst-case bounds; the reported "
            "effect is the bound, not the complete-case estimate. No variable is conditioned on "
            "that both the exposure and the outcome influence."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.PREDICTIVE,
    ),
    GateSpec(
        gate_id=GateId.SURVIVORSHIP,
        name="Survivorship and cohort completeness",
        bias_class=BiasClass.SURVIVORSHIP,
        question="Was the cohort defined at decision time and kept complete?",
        rule=(
            "The cohort is every decision in the window, entered on its decision timestamp. No "
            "filter references cancellation, completion, refund, tenure, or any other survival "
            "condition. Record counts reconcile with the source dataset version."
        ),
        on_failure=FailureAction.REJECT,
    ),
    GateSpec(
        gate_id=GateId.SIMPSON,
        name="Simpson reversal and heterogeneity",
        bias_class=BiasClass.HETEROGENEITY,
        question="Does the pooled effect misrepresent its own subgroups?",
        rule=(
            "The effect is recomputed within each level of every declared strong covariate. If "
            "the sign reverses in strata covering at least simpson_reversal_exposure_share of "
            "exposure, or the pooled estimate falls outside the range of stratum estimates, the "
            "pooled number is not reportable and the candidate must be re-specified at the "
            "stratum level and re-validated as a new candidate."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.DESCRIPTIVE,
    ),
    GateSpec(
        gate_id=GateId.TEMPORAL_STABILITY,
        name="Temporal stability",
        bias_class=BiasClass.TEMPORAL,
        question="Does the effect persist out of period, not only where it was found?",
        rule=(
            "The effect is re-estimated on development, validation, and future holdout splits. "
            "The sign agrees across required_same_sign_splits splits and the holdout magnitude "
            "retains at least min_holdout_effect_retention of the development magnitude with "
            "overlapping intervals. Genuinely period-limited patterns are re-scoped to an "
            "explicit validity window and re-validated as a new candidate."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.DESCRIPTIVE,
    ),
    GateSpec(
        gate_id=GateId.SEASONALITY,
        name="Seasonality",
        bias_class=BiasClass.SEASONALITY,
        question="Is the pattern a calendar effect wearing a business label?",
        rule=(
            "When the condition references calendar fields, or exposure concentration in any "
            "month or quarter exceeds seasonal_concentration_index, the calendar period enters "
            "the adjustment set and the effect is reported within period as well as pooled."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.PREDICTIVE,
    ),
    GateSpec(
        gate_id=GateId.ROBUSTNESS,
        name="Robustness battery",
        bias_class=BiasClass.ROBUSTNESS,
        question="Does the effect depend on one cluster, one outlier, or one arbitrary cutoff?",
        rule=(
            "Leave-one-cluster-out refits, winsorising the top and bottom 1% of the outcome, the "
            "alternative outcome definition, and one-bin perturbation of every numeric threshold. "
            "The sign holds in at least min_robustness_sign_agreement of refits and the magnitude "
            "stays within max_robustness_magnitude_deviation of the primary estimate."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.DESCRIPTIVE,
    ),
    GateSpec(
        gate_id=GateId.IDENTIFICATION,
        name="Identification design",
        bias_class=BiasClass.IDENTIFICATION,
        question="Is there a design, not just an adjustment, behind the causal claim?",
        rule=(
            "A named quasi-experimental design with its testable implication: difference-in-"
            "differences with pre-period parallel trends, instrumental variable with first stage "
            "and an argued exclusion restriction, regression discontinuity with density and "
            "covariate continuity, or a documented natural experiment. At least one negative-"
            "control or placebo test passes. Adjustment alone never satisfies this gate."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.ADJUSTED_OBSERVATIONAL,
    ),
    GateSpec(
        gate_id=GateId.RANDOMIZATION,
        name="Randomisation integrity",
        bias_class=BiasClass.IDENTIFICATION,
        question="Was assignment randomised prospectively under a preregistered plan?",
        rule=(
            "Prospective randomised assignment with a preregistered analysis plan, balance check, "
            "documented attrition, and an intention-to-treat primary estimate. This gate can "
            "never be satisfied retrospectively on historical data."
        ),
        on_failure=FailureAction.CAP_EVIDENCE,
        max_level_on_failure=EvidenceLevel.QUASI_CAUSAL,
    ),
    GateSpec(
        gate_id=GateId.ECONOMIC_MATERIALITY,
        name="Economic materiality",
        bias_class=BiasClass.ECONOMIC,
        question="Is the effect large enough to be worth a business decision?",
        rule=(
            "Historical impact is computed deterministically over the observed window with the "
            "bootstrap interval; its lower bound is above zero and clears either "
            "min_material_annual_impact or min_material_outcome_share. Annualisation requires at "
            "least min_annualization_months of coverage and a stable exposure rate; otherwise "
            "only the observed-window figure is reported. Failing this gate never changes the "
            "evidence level, only policy readiness."
        ),
        on_failure=FailureAction.READINESS_ONLY,
    ),
)

GATE_SPEC_BY_ID: dict[GateId, GateSpec] = {spec.gate_id: spec for spec in GATE_SPECS}

_LEVEL_GATES: tuple[tuple[EvidenceLevel, tuple[GateId, ...]], ...] = (
    (
        EvidenceLevel.DESCRIPTIVE,
        (GateId.LINEAGE, GateId.TARGET_LEAKAGE, GateId.SURVIVORSHIP),
    ),
    (
        EvidenceLevel.PREDICTIVE,
        (
            GateId.SAMPLE,
            GateId.UNCERTAINTY,
            GateId.MULTIPLICITY,
            GateId.TEMPORAL_STABILITY,
            GateId.ROBUSTNESS,
        ),
    ),
    (
        EvidenceLevel.ADJUSTED_OBSERVATIONAL,
        (
            GateId.POST_TREATMENT,
            GateId.CONFOUNDING,
            GateId.SELECTION_COLLIDER,
            GateId.SIMPSON,
            GateId.SEASONALITY,
        ),
    ),
    (EvidenceLevel.QUASI_CAUSAL, (GateId.IDENTIFICATION,)),
    (EvidenceLevel.EXPERIMENTAL, (GateId.RANDOMIZATION,)),
)

LEVEL_ORDER: tuple[EvidenceLevel, ...] = tuple(level for level, _ in _LEVEL_GATES)


def _cumulative_requirements() -> dict[EvidenceLevel, frozenset[GateId]]:
    requirements: dict[EvidenceLevel, frozenset[GateId]] = {}
    accumulated: set[GateId] = set()
    for level, gates in _LEVEL_GATES:
        accumulated.update(gates)
        requirements[level] = frozenset(accumulated)
    return requirements


LEVEL_REQUIREMENTS: dict[EvidenceLevel, frozenset[GateId]] = _cumulative_requirements()

DESIGN_CEILING: dict[IdentificationDesign, EvidenceLevel] = {
    IdentificationDesign.OBSERVATIONAL: EvidenceLevel.ADJUSTED_OBSERVATIONAL,
    IdentificationDesign.QUASI_EXPERIMENTAL: EvidenceLevel.QUASI_CAUSAL,
    IdentificationDesign.RANDOMIZED_PROSPECTIVE: EvidenceLevel.EXPERIMENTAL,
}


@dataclass(frozen=True, slots=True)
class LanguageRule:
    """Wording permitted at an evidence level. UI and API text may not exceed it."""

    level: EvidenceLevel
    permitted_claim: str
    permitted_verbs: tuple[str, ...]
    forbidden_verbs: tuple[str, ...]


_CAUSAL_VERBS = ("causes", "leads to", "drives", "results in", "reduces", "increases")

LANGUAGE_RULES: dict[EvidenceLevel, LanguageRule] = {
    EvidenceLevel.DESCRIPTIVE: LanguageRule(
        level=EvidenceLevel.DESCRIPTIVE,
        permitted_claim="In this dataset and window, these records differ on this outcome.",
        permitted_verbs=("is observed with", "differs from", "coincides with"),
        forbidden_verbs=(*_CAUSAL_VERBS, "predicts", "is associated with"),
    ),
    EvidenceLevel.PREDICTIVE: LanguageRule(
        level=EvidenceLevel.PREDICTIVE,
        permitted_claim=(
            "This combination is associated with a worse outcome and holds out of period."
        ),
        permitted_verbs=("is associated with", "predicts", "identifies"),
        forbidden_verbs=(*_CAUSAL_VERBS, "after accounting for"),
    ),
    EvidenceLevel.ADJUSTED_OBSERVATIONAL: LanguageRule(
        level=EvidenceLevel.ADJUSTED_OBSERVATIONAL,
        permitted_claim=(
            "The association survives adjustment for the listed variables; unmeasured confounding "
            "remains possible."
        ),
        permitted_verbs=("remains associated with", "persists after adjusting for"),
        forbidden_verbs=_CAUSAL_VERBS,
    ),
    EvidenceLevel.QUASI_CAUSAL: LanguageRule(
        level=EvidenceLevel.QUASI_CAUSAL,
        permitted_claim="Under the stated design assumptions, the estimated effect is causal.",
        permitted_verbs=("is estimated to cause", "under <design> assumptions, reduces"),
        forbidden_verbs=("proves", "guarantees", "will save"),
    ),
    EvidenceLevel.EXPERIMENTAL: LanguageRule(
        level=EvidenceLevel.EXPERIMENTAL,
        permitted_claim="Randomised assignment measured this effect.",
        permitted_verbs=("causes", "reduces", "increases"),
        forbidden_verbs=("proves", "guarantees"),
    ),
}


@dataclass(frozen=True, slots=True)
class GateResult:
    """Outcome of one gate for one candidate."""

    gate_id: GateId
    outcome: GateOutcome
    detail: str = ""

    @property
    def satisfied(self) -> bool:
        return self.outcome in (GateOutcome.PASS, GateOutcome.WARN)
