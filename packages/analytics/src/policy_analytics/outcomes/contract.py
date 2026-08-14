"""Outcome definition contract for the first blind benchmark (TASK-013).

This module is the vocabulary ML Discovery must use to interpret and rank candidates: which
column is the outcome, which direction is harmful, what unit it is in, what the missing-data
policy is, and which cohort is eligible. Discovery must not invent or renegotiate any of this — it
selects and ranks *conditions* over a fixed, preregistered outcome definition.

**Scope.** This contract is fixed for the delivered analytical dataset
`travel-bookings-analytical-v1.0.0` (`synthetic_data/analytical/travel-bookings-analytical-v1.0.0/`,
`dataset_identity_sha256 = 98ad4e7e08e63ee9e31f9317ca408f2895da8bece49324482915e24df0aee04c`,
resolving `HANDOFF-002`), whose outcome columns live in `outcomes.csv`, decision-time features in
`features.csv`, identifiers (including the `customer_id` clustering key) in `identifiers.csv`, and
split/timing metadata in `metadata.csv`. It answers the outcome half of `HANDOFF-003` for
`TASK-015`/`TASK-016`/`TASK-017` on that dataset. It is not the canonical real-customer outcome
contract: `OQ-002` (which outcome a real customer actually optimizes for) stays open, and this
contract's benchmark-specific eligibility rule (closed 24-month window, no right-censoring) will
not carry over unmodified — see §"Interpretation limits" and `docs/analytics/outcome-contract.md`.

No estimation, search, or ranking algorithm lives here. Computing group summaries from these
definitions is `aggregation.py`; searching for conditions is `TASK-015` (ML Discovery); adjusting,
testing, and grading effects is `packages/analytics/src/policy_analytics/validation/` (TASK-018).

**v1.1.0** adds, without changing the v1.0.0 primary-outcome decision: an empirically grounded
``valid_range`` per outcome (for data-quality sanity-checking, never for clipping or filtering),
an explicit ``winsorization_allowed_at_discovery`` flag (uniformly false — winsorization is a
validation-stage robustness perturbation, gate G12, not a discovery-time transform), an explicit
``aggregation_rule`` per outcome, and `DISCOVERY_CONTRACT`, which consolidates the statistical
rules `TASK-015`/`TASK-016` must follow at discovery time: which split to search on, the support
floor (imported from the validation contract so the two never drift apart), which feature
classifications may never appear in a candidate condition, and how to treat a missing outcome
value at discovery time (distinct from validation gate G07's later bounding of *validated*
estimates).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from policy_schemas.domain import FeatureTiming

from policy_analytics.validation.contract import DEFAULT_THRESHOLDS

OUTCOME_CONTRACT_VERSION = "1.1.0"

#: The analytical dataset this contract was written against. A new dataset version requires a new
#: outcome contract version, even if column names are unchanged.
DATASET_VERSION = "travel-bookings-analytical-v1.0.0"

#: Pinned identity of the dataset above (`manifest.json.dataset_identity_sha256`). A finding whose
#: dataset_version matches but whose identity hash does not is not graded under this contract.
DATASET_IDENTITY_SHA256 = "98ad4e7e08e63ee9e31f9317ca408f2895da8bece49324482915e24df0aee04c"


class OutcomeRole(StrEnum):
    """Whether a candidate's ranking score may be built from this outcome."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


class MissingDataPolicy(StrEnum):
    """How an outcome's missingness must be handled.

    ``COMPLETE`` asserts the outcome is expected to have no missingness; any missing value found
    at analysis time is a data-quality defect to be reported, not silently dropped.
    ``MNAR_BOUNDED`` means missingness is expected to depend on the outcome (or a close proxy of
    it) and a naive complete-case estimate is prohibited — worst-case bounds are mandatory
    alongside the observed-only figure, per validation gate G07.
    """

    COMPLETE = "complete_no_missingness_expected"
    MNAR_BOUNDED = "missing_not_at_random_report_bounds"


@dataclass(frozen=True, slots=True)
class OutcomeDefinition:
    """One versioned, unambiguous outcome. Column, direction, unit, and eligibility are fixed.

    ``valid_range`` is the empirically observed [min, max] on the pinned dataset instance
    (`DATASET_IDENTITY_SHA256`), used only to flag an out-of-range value as a data-quality defect
    at analysis time — never to clip, filter, or winsorize a value before it enters a group
    summary. ``winsorization_allowed_at_discovery`` is uniformly ``False``: discovery must rank on
    raw, untransformed values so a reported EUR effect means what it says; winsorizing the top and
    bottom 1% is a *robustness perturbation* validation runs afterward (gate G12 in the validation
    contract), not a discovery-time computation. ``aggregation_rule`` names the exact statistic a
    group summary computes.
    """

    outcome_id: str
    role: OutcomeRole
    column: str
    unit: str
    higher_is_worse: bool
    missing_data_policy: MissingDataPolicy
    description: str
    valid_range: tuple[float, float]
    aggregation_rule: str
    decomposition_of: str | None = None
    winsorization_allowed_at_discovery: bool = False

    def __post_init__(self) -> None:
        if not self.outcome_id or not self.column or not self.unit or not self.description:
            raise ValueError("outcome definitions require id, column, unit, and description")
        if not self.aggregation_rule:
            raise ValueError(f"{self.outcome_id} requires an aggregation_rule")
        low, high = self.valid_range
        if low > high:
            raise ValueError(f"{self.outcome_id} has an invalid valid_range: {self.valid_range}")

    @property
    def harm_multiplier(self) -> int:
        """Sign applied to a raw (exposed minus comparison) difference so positive means harm.

        For outcomes where higher is better (e.g. margin), a decrease is harmful, so the raw
        difference is negated. For outcomes where higher is worse (e.g. cancellation rate), the
        raw difference already points the harmful direction.
        """
        return 1 if self.higher_is_worse else -1


#: Every decision in the benchmark window is eligible, regardless of what happened after the
#: decision. No filter may reference cancellation, completion, refund, support activity, or any
#: other post-decision/outcome field — that is gate G08 (survivorship) in the validation contract,
#: restated here as the outcome layer's cohort rule so Discovery does not have to infer it.
ELIGIBLE_COHORT_RULE = (
    "booking_date within [2024-01-01, 2025-12-31]; no filter on cancellation, refund, support "
    "activity, booking_changes, or repeat_purchase_180d."
)

#: The comparison group for any candidate condition is the complement of that condition within
#: the same eligible cohort — never a hand-picked baseline, never a different time window.
DEFAULT_COMPARISON_RULE = "complement of the candidate condition within the eligible cohort"

PRIMARY_OUTCOME_ID = "contribution_margin_eur"

OUTCOME_DEFINITIONS: tuple[OutcomeDefinition, ...] = (
    OutcomeDefinition(
        outcome_id="contribution_margin_eur",
        role=OutcomeRole.PRIMARY,
        column="contribution_margin_eur",
        unit="EUR per booking (nominal; single currency; no inflation or FX adjustment)",
        higher_is_worse=False,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description=(
            "Realized contribution margin: net revenue minus base cost, refunds, additional "
            "realized cost, support cost, and payment fees. The fullest available per-booking "
            "measure of downstream economic value; harm is a decrease relative to the comparison "
            "group. Interpretation: a positive value is a profitable booking after every "
            "downstream cost in the schema; a negative value (11.1% of bookings, -5,777.45 to "
            "-0.01 EUR) is a booking that lost money outright, not merely an underperforming one."
        ),
        valid_range=(-5777.45, 2519.42),
        aggregation_rule="arithmetic_mean_of_present_values",
    ),
    OutcomeDefinition(
        outcome_id="gross_profit_eur",
        role=OutcomeRole.SECONDARY,
        column="gross_profit_eur",
        unit="EUR per booking (nominal)",
        higher_is_worse=False,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description=(
            "Net revenue minus base cost and refunds, before support cost, additional realized "
            "cost, and payment fees. Used only to decompose a contribution-margin finding: a "
            "pattern present in gross profit is priced/costed into the deal; a pattern that "
            "appears only after subtracting downstream costs is an operational-harm pattern. "
            "Never a ranking outcome on its own — it does not include the full downstream cost "
            "the primary outcome is defined to capture."
        ),
        valid_range=(-5623.99, 2709.10),
        aggregation_rule="arithmetic_mean_of_present_values",
        decomposition_of="contribution_margin_eur",
    ),
    OutcomeDefinition(
        outcome_id="contribution_margin_rate",
        role=OutcomeRole.SECONDARY,
        column="contribution_margin_eur / customer_price_eur",
        unit="ratio, dimensionless (contribution margin ÷ quoted price; not stored, computed at "
        "analysis time)",
        higher_is_worse=False,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description=(
            "Contribution margin normalized by quoted price. `customer_price_eur` is "
            "decision-time and always positive (benchmark floor 450 EUR), so the ratio is always "
            "defined. Use only to compare harm across price tiers (standard/premium/luxury) "
            "without magnitude bias; do not sum or average this ratio across bookings of "
            "materially different price as if it were a share of a common pool."
        ),
        valid_range=(-1.3660, 0.3276),
        aggregation_rule=(
            "arithmetic_mean_of_per_booking_ratio — the mean of each booking's own ratio, NOT "
            "sum(contribution_margin_eur) / sum(customer_price_eur); the two differ whenever "
            "price and margin-per-euro-of-price are correlated, which they are in this benchmark "
            "(higher-tier bookings both cost more and carry different margin rates)."
        ),
        decomposition_of="contribution_margin_eur",
    ),
    OutcomeDefinition(
        outcome_id="cancellation",
        role=OutcomeRole.SECONDARY,
        column="cancellation",
        unit="rate, proportion in [0, 1]",
        higher_is_worse=True,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description=(
            "Whether the booking was cancelled. A mechanism outcome: cancellation drives refund "
            "and is itself a component of contribution margin (through refund_amount_eur), so a "
            "cancellation finding and a margin finding on the same condition are not independent "
            "evidence — report the relationship, do not add their impacts."
        ),
        valid_range=(0.0, 1.0),
        aggregation_rule=(
            "arithmetic_mean_of_present_values (equals the observed rate for a 0/1 outcome)"
        ),
    ),
    OutcomeDefinition(
        outcome_id="refund_amount_eur",
        role=OutcomeRole.SECONDARY,
        column="refund_amount_eur",
        unit="EUR per booking (nominal)",
        higher_is_worse=True,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description=(
            "Realized refund amount, zero when not cancelled. A component of contribution "
            "margin; use to explain, not to independently size, a margin finding."
        ),
        valid_range=(0.0, 6871.55),
        aggregation_rule="arithmetic_mean_of_present_values",
        decomposition_of="contribution_margin_eur",
    ),
    OutcomeDefinition(
        outcome_id="support_cost_eur",
        role=OutcomeRole.SECONDARY,
        column="support_cost_eur",
        unit="EUR per booking (nominal)",
        higher_is_worse=True,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description=(
            "Realized support cost. A component of contribution margin; use to explain, not to "
            "independently size, a margin finding."
        ),
        valid_range=(0.0, 393.27),
        aggregation_rule="arithmetic_mean_of_present_values",
        decomposition_of="contribution_margin_eur",
    ),
    OutcomeDefinition(
        outcome_id="additional_cost_eur",
        role=OutcomeRole.SECONDARY,
        column="additional_cost_eur",
        unit="EUR per booking (nominal)",
        higher_is_worse=True,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description=(
            "Realized unplanned cost. A component of contribution margin; use to explain, not to "
            "independently size, a margin finding."
        ),
        valid_range=(0.0, 1523.05),
        aggregation_rule="arithmetic_mean_of_present_values",
        decomposition_of="contribution_margin_eur",
    ),
    OutcomeDefinition(
        outcome_id="repeat_purchase_180d",
        role=OutcomeRole.SECONDARY,
        column="repeat_purchase_180d",
        unit="rate, proportion in [0, 1]; not economically commensurable with the EUR outcomes",
        higher_is_worse=False,
        missing_data_policy=MissingDataPolicy.MNAR_BOUNDED,
        description=(
            "Whether the customer purchased again within 180 days. Exploratory only: overall "
            "missingness is 9.7%, but 45.7% among cancelled bookings versus 7.2% otherwise "
            "(measured on the benchmark), which is missingness driven by an outcome-adjacent "
            "variable. Never eligible as a primary outcome and never reportable as a complete-case "
            "point estimate — report the observed-only estimate together with the worst-case "
            "bounds required by validation gate G07. No customer-lifetime-value model exists in "
            "this repository, so a repeat-purchase effect must never be converted to EUR and "
            "combined with margin-based impact."
        ),
        valid_range=(0.0, 1.0),
        aggregation_rule=(
            "arithmetic_mean_of_present_values only — never impute a missing value before "
            "averaging; use mnar_bounds() for the observed-plus-worst-case range instead"
        ),
    ),
)

OUTCOME_BY_ID: dict[str, OutcomeDefinition] = {
    definition.outcome_id: definition for definition in OUTCOME_DEFINITIONS
}


def primary_outcome() -> OutcomeDefinition:
    return OUTCOME_BY_ID[PRIMARY_OUTCOME_ID]


def secondary_outcomes() -> tuple[OutcomeDefinition, ...]:
    return tuple(d for d in OUTCOME_DEFINITIONS if d.role is OutcomeRole.SECONDARY)


#: Classifications a candidate condition may never use as an explanatory variable. Built from
#: `FeatureTiming` rather than hardcoded so a future classification (e.g. `UNKNOWN`, per TASK-008's
#: still-pending goal) is excluded automatically instead of silently falling through.
EXCLUDED_EXPLANATORY_CLASSIFICATIONS: frozenset[str] = frozenset(
    timing.value for timing in FeatureTiming if timing is not FeatureTiming.DECISION_TIME
)


@dataclass(frozen=True, slots=True)
class DiscoveryStatisticalContract:
    """Rules `TASK-015`/`TASK-016` must follow at discovery time, before any validation runs.

    This is deliberately separate from `packages.analytics.validation.contract`: that module
    grades a candidate *after* discovery proposes it. This one constrains what discovery is
    allowed to propose and rank in the first place. Numeric floors are imported, not restated, so
    the two contracts cannot silently drift apart.
    """

    contract_version: str
    search_fit_split: str
    diagnostic_only_splits: tuple[str, ...]
    min_support_records: int
    excluded_explanatory_classifications: frozenset[str]
    primary_outcome_missing_handling: str
    mnar_outcome_missing_handling: str
    causal_language_note: str

    def __post_init__(self) -> None:
        if self.search_fit_split in self.diagnostic_only_splits:
            raise ValueError("the fit split cannot also be a diagnostic-only split")
        if self.min_support_records < 1:
            raise ValueError("min_support_records must be positive")


DISCOVERY_CONTRACT = DiscoveryStatisticalContract(
    contract_version=OUTCOME_CONTRACT_VERSION,
    search_fit_split="development",
    diagnostic_only_splits=("validation", "future_holdout"),
    # Same floor as validation gate G03 (`min_exposed_records`): a candidate discovery proposes
    # below this can never be analysable, let alone pass validation, so generating or ranking it
    # only spends multiple-comparison budget (gate G05) on something dead on arrival.
    min_support_records=DEFAULT_THRESHOLDS.min_exposed_records,
    excluded_explanatory_classifications=EXCLUDED_EXPLANATORY_CLASSIFICATIONS,
    primary_outcome_missing_handling=(
        "contribution_margin_eur has MissingDataPolicy.COMPLETE: 0% missingness is a verified "
        "property of the pinned dataset, not an assumption. If a missing value is nonetheless "
        "encountered for a candidate's exposed or comparison group, exclude that record from the "
        "group's support and effect calculation (never impute, never zero-fill) and attach a "
        "data-quality warning to the candidate — its presence means the dataset no longer matches "
        "this contract's DATASET_IDENTITY_SHA256 and the run should be treated as suspect."
    ),
    mnar_outcome_missing_handling=(
        "repeat_purchase_180d (and any other MNAR_BOUNDED outcome) must never be used to rank or "
        "select candidates for the primary leaderboard. If discovery explores it at all, report it "
        "as a separate, clearly labeled exploratory list using mnar_bounds() — observed-only mean "
        "plus pessimistic/optimistic bounds — never a bare complete-case mean, and never merge its "
        "candidates into the primary-outcome ranking."
    ),
    causal_language_note=(
        "Candidate descriptions and names, even at the pre-validation discovery stage, may not use "
        "causal verbs (causes, drives, leads to, reduces, increases) or imply a mechanism. Nothing "
        "discovery produces has an evidence level yet — evidence levels are assigned only after "
        "TASK-018/TASK-019 gates run — so candidate language must stay at or below "
        "descriptive_observation phrasing (e.g. 'bookings where X are observed with lower margin', "
        "not 'X reduces margin'). See LANGUAGE_RULES in the validation contract for the full rule "
        "and its enforcement at every subsequent evidence level."
    ),
)
