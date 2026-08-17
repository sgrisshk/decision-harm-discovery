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
