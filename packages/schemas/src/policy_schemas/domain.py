from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FeatureTiming(StrEnum):
    IDENTIFIER = "identifier"
    DECISION_TIME = "decision_time"
    POST_DECISION = "post_decision"
    OUTCOME = "outcome"
    METADATA = "metadata"
    #: A column this repository's classifiers cannot confidently place (TASK-008). Excluded from
    #: explanatory features exactly like POST_DECISION/OUTCOME
    #: (`policy_analytics.outcomes.contract.EXCLUDED_EXPLANATORY_CLASSIFICATIONS`) — never a
    #: silent stand-in for DECISION_TIME.
    UNKNOWN = "unknown"


class EvidenceLevel(StrEnum):
    DESCRIPTIVE = "descriptive_observation"
    PREDICTIVE = "predictive_association"
    ADJUSTED_OBSERVATIONAL = "adjusted_observational_association"
    QUASI_CAUSAL = "quasi_causal_evidence"
    EXPERIMENTAL = "experimental_evidence"


class ResourceStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DRAFT = "draft"


class FindingLifecycleStatus(StrEnum):
    """Distinct from `ResourceStatus` (job state, not finding lifecycle).

    Forward-only transitions: `ACTIVE -> SUPERSEDED`, `ACTIVE -> WITHDRAWN`. Nothing transitions
    back to `ACTIVE` (`docs/product/finding-product-contract.md` §12.1, resolves `HANDOFF-024`).
    """

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"


class DataQualityRating(StrEnum):
    """The `TASK-009` Data Quality Report's single overall verdict — exactly one value, never
    inferred loosely by a reader from the report's other fields."""

    READY = "ready"
    READY_WITH_LIMITATIONS = "ready_with_limitations"
    NOT_READY = "not_ready"


class DatasetColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    data_type: str = Field(min_length=1, max_length=64)
    timing: FeatureTiming
    nullable: bool = True


class FeedbackNovelty(StrEnum):
    """`docs/product/finding-feedback-contract.md` §2.1."""

    KNOWN_ALREADY = "KNOWN_ALREADY"
    NEW = "NEW"


class FeedbackActionability(StrEnum):
    """§2.2. Distinct from a Finding's own evidence/impact fields — never written back to them
    (§7)."""

    ACTIONABLE = "ACTIONABLE"
    NOT_ACTIONABLE = "NOT_ACTIONABLE"


class FeedbackTag(StrEnum):
    """§2.3 — additive qualifier tags, not alternatives to novelty/actionability."""

    WRONG = "WRONG"
    INTERESTING = "INTERESTING"


class FeedbackCertainty(StrEnum):
    """§4 `customer_certainty` — the customer's own reported sense of their reaction. Never named
    "confidence" and never combined with `EffectEstimate.confidence_level` (§4's own warning)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FeedbackCommitmentStrength(StrEnum):
    """§4 `commitment_strength` — formalizes the review protocol's stated-commitment vs.
    stated-intention distinction."""

    STATED_COMMITMENT = "STATED_COMMITMENT"
    STATED_INTENTION = "STATED_INTENTION"
    NONE = "NONE"
