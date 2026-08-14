"""Outcome definition contract for the first blind benchmark.

Vocabulary and versioned definitions live in `contract`; pure group-summary arithmetic lives in
`aggregation`. Prose methodology: `docs/analytics/outcome-contract.md`.
"""

from policy_analytics.outcomes.aggregation import (
    GroupSummary,
    MnarBounds,
    harm_score,
    historical_exposure,
    missingness_gap,
    mnar_bounds,
    raw_difference,
    summarize_group,
)
from policy_analytics.outcomes.contract import (
    DATASET_IDENTITY_SHA256,
    DATASET_VERSION,
    DISCOVERY_CONTRACT,
    ELIGIBLE_COHORT_RULE,
    EXCLUDED_EXPLANATORY_CLASSIFICATIONS,
    OUTCOME_BY_ID,
    OUTCOME_CONTRACT_VERSION,
    OUTCOME_DEFINITIONS,
    PRIMARY_OUTCOME_ID,
    DiscoveryStatisticalContract,
    MissingDataPolicy,
    OutcomeDefinition,
    OutcomeRole,
    primary_outcome,
    secondary_outcomes,
)

__all__ = [
    "DATASET_IDENTITY_SHA256",
    "DATASET_VERSION",
    "DISCOVERY_CONTRACT",
    "ELIGIBLE_COHORT_RULE",
    "EXCLUDED_EXPLANATORY_CLASSIFICATIONS",
    "OUTCOME_BY_ID",
    "OUTCOME_CONTRACT_VERSION",
    "OUTCOME_DEFINITIONS",
    "PRIMARY_OUTCOME_ID",
    "DiscoveryStatisticalContract",
    "GroupSummary",
    "MissingDataPolicy",
    "MnarBounds",
    "OutcomeDefinition",
    "OutcomeRole",
    "harm_score",
    "historical_exposure",
    "missingness_gap",
    "mnar_bounds",
    "primary_outcome",
    "raw_difference",
    "secondary_outcomes",
    "summarize_group",
]
