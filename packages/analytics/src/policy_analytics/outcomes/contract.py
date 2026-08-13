"""Outcome definition contract for the first blind benchmark (TASK-013).

This module is the vocabulary ML Discovery must use to interpret and rank candidates: which
column is the outcome, which direction is harmful, what unit it is in, what the missing-data
policy is, and which cohort is eligible. Discovery must not invent or renegotiate any of this — it
selects and ranks *conditions* over a fixed, preregistered outcome definition.

**Scope.** This contract is fixed for the delivered analytical dataset
`travel-bookings-analytical-v1.0.0` (`synthetic_data/analytical/travel-bookings-analytical-v1.0.0/`,
`dataset_identity_sha256 = 490c65655aff645ec8da845cff257f23edfccea4abe609553b576b5b800f91e8`,
resolving `HANDOFF-002`), whose outcome columns live in `outcomes.csv`, decision-time features in
`features.csv`, identifiers (including the `customer_id` clustering key) in `identifiers.csv`, and
split/timing metadata in `metadata.csv`. It answers the outcome half of `HANDOFF-003` for
`TASK-015`/`TASK-016`/`TASK-017` on that dataset. It is not the canonical real-customer outcome
contract: `OQ-002` (which outcome a real customer actually optimizes for) stays open, and this
contract's benchmark-specific eligibility rule (closed 24-month window, no right-censoring) will
not carry over unmodified — see §"Interpretation limits" and `docs/outcome_contract.md`.

No estimation, search, or ranking algorithm lives here. Computing group summaries from these
definitions is `aggregation.py`; searching for conditions is `TASK-015` (ML Discovery); adjusting,
testing, and grading effects is `packages/analytics/src/policy_analytics/validation/` (TASK-018).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

OUTCOME_CONTRACT_VERSION = "1.0.0"

#: The analytical dataset this contract was written against. A new dataset version requires a new
#: outcome contract version, even if column names are unchanged.
DATASET_VERSION = "travel-bookings-analytical-v1.0.0"

#: Pinned identity of the dataset above (`manifest.json.dataset_identity_sha256`). A finding whose
#: dataset_version matches but whose identity hash does not is not graded under this contract.
DATASET_IDENTITY_SHA256 = "490c65655aff645ec8da845cff257f23edfccea4abe609553b576b5b800f91e8"


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
    """One versioned, unambiguous outcome. Column, direction, unit, and eligibility are fixed."""

    outcome_id: str
    role: OutcomeRole
    column: str
    unit: str
    higher_is_worse: bool
    missing_data_policy: MissingDataPolicy
    description: str
    decomposition_of: str | None = None

    def __post_init__(self) -> None:
        if not self.outcome_id or not self.column or not self.unit or not self.description:
            raise ValueError("outcome definitions require id, column, unit, and description")

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
            "group."
        ),
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
    ),
)

OUTCOME_BY_ID: dict[str, OutcomeDefinition] = {
    definition.outcome_id: definition for definition in OUTCOME_DEFINITIONS
}


def primary_outcome() -> OutcomeDefinition:
    return OUTCOME_BY_ID[PRIMARY_OUTCOME_ID]


def secondary_outcomes() -> tuple[OutcomeDefinition, ...]:
    return tuple(d for d in OUTCOME_DEFINITIONS if d.role is OutcomeRole.SECONDARY)
