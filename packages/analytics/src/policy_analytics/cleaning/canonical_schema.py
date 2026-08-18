"""The travel-booking canonical schema contract (TASK-010).

Fixes the typed target shape every raw ingested dataset must be mapped onto before it can enter
`policy_analytics.analytical_dataset.build_analytical_dataset` (or a future real-customer
equivalent of it). This is a **contract, not a guess**: every field here is either read off the
synthetic benchmark's own public, disclosed schema
(`synthetic_data/metadata/feature_timing.json`/`schema_profile.json`) — the only concrete
travel-booking schema this repository has ever seen — or cross-referenced against a structural
dependency already hard-coded elsewhere:

- `booking_id` uniqueness and `customer_id` (`clustering_key`, >=5 clusters) are enforced by
  `analytical_dataset.build_analytical_dataset`.
- `booking_date` is `decision_timestamp_column`, read by name to compute temporal splits.
- `currency` is read by literal name (`.alias("source_currency")`) in the same module.
- Every `contribution_margin_eur`/`gross_profit_eur`/`cancellation`/`refund_amount_eur`/
  `support_cost_eur`/`additional_cost_eur` column carries `MissingDataPolicy.COMPLETE` in the
  `TASK-013` outcome contract (0% missingness expected) — `policy_analytics.outcomes.contract`.
  `customer_price_eur` is never itself an `OutcomeDefinition.column` (it only appears embedded in
  `contribution_margin_rate`'s formula), but that definition's own description documents it as
  "decision-time and always positive... so the ratio is always defined" — expected-complete by the
  same contract, just not through a standalone entry. `repeat_purchase_180d` is deliberately
  **not** required: its `MissingDataPolicy.MNAR_BOUNDED` means missingness is expected and
  structurally meaningful.

`required=True` therefore means "something downstream already structurally depends on this field
existing and being complete," not an editorial guess about what a travel agency probably tracks.
Everything else is a real, useful, but optional attribute.

Version `travel-booking-canonical-v1.0.0` is unchanged from what
`policy_analytics.analytical_dataset.CANONICAL_SCHEMA_VERSION` already labeled — this module makes
that label's contents explicit and machine-checkable for the first time; it does not change the
target shape, so the version number does not bump (`analytical_dataset` now imports it from here).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from policy_schemas.domain import FeatureTiming

CANONICAL_SCHEMA_VERSION = "travel-booking-canonical-v1.0.0"

CanonicalDType = Literal["string", "integer", "float", "boolean", "date"]


@dataclass(frozen=True, slots=True)
class CanonicalField:
    name: str
    role: FeatureTiming
    dtype: CanonicalDType
    required: bool
    unit: str | None
    description: str


#: Ordered to match the benchmark's own public column order — not semantically significant, but
#: keeps diffs against `synthetic_data/metadata/feature_timing.json` easy to eyeball.
CANONICAL_SCHEMA: tuple[CanonicalField, ...] = (
    CanonicalField(
        "booking_id", FeatureTiming.IDENTIFIER, "string", True, None, "Unique booking identifier"
    ),
    CanonicalField(
        "customer_id", FeatureTiming.IDENTIFIER, "string", True, None, "Stable customer identifier"
    ),
    CanonicalField(
        "booking_date", FeatureTiming.DECISION_TIME, "date", True, None, "Decision timestamp"
    ),
    CanonicalField(
        "travel_date",
        FeatureTiming.DECISION_TIME,
        "date",
        False,
        None,
        "Known scheduled travel date",
    ),
    CanonicalField(
        "destination", FeatureTiming.DECISION_TIME, "string", False, None, "Quoted destination"
    ),
    CanonicalField(
        "supplier",
        FeatureTiming.DECISION_TIME,
        "string",
        False,
        None,
        "Supplier selected at booking",
    ),
    CanonicalField(
        "product_category",
        FeatureTiming.DECISION_TIME,
        "string",
        False,
        None,
        "Booked product tier",
    ),
    CanonicalField(
        "customer_price_eur",
        FeatureTiming.DECISION_TIME,
        "float",
        True,
        "EUR",
        "Quoted gross price",
    ),
    CanonicalField(
        "quoted_cost_eur",
        FeatureTiming.DECISION_TIME,
        "float",
        False,
        "EUR",
        "Cost estimate available at booking",
    ),
    CanonicalField(
        "discount_rate",
        FeatureTiming.DECISION_TIME,
        "float",
        False,
        "ratio_0_1",
        "Discount approved at booking",
    ),
    CanonicalField("manager", FeatureTiming.DECISION_TIME, "string", False, None, "Booking owner"),
    CanonicalField(
        "acquisition_channel",
        FeatureTiming.DECISION_TIME,
        "string",
        False,
        None,
        "Acquisition source",
    ),
    CanonicalField(
        "customer_segment",
        FeatureTiming.DECISION_TIME,
        "string",
        False,
        None,
        "Pre-existing customer segment",
    ),
    CanonicalField(
        "customer_type",
        FeatureTiming.DECISION_TIME,
        "string",
        False,
        None,
        "New or returning at booking",
    ),
    CanonicalField(
        "party_size", FeatureTiming.DECISION_TIME, "integer", False, "count", "Booked travellers"
    ),
    CanonicalField(
        "trip_duration_days",
        FeatureTiming.DECISION_TIME,
        "integer",
        False,
        "days",
        "Scheduled duration",
    ),
    CanonicalField(
        "booking_lead_days",
        FeatureTiming.DECISION_TIME,
        "integer",
        False,
        "days",
        "Days between booking and travel",
    ),
    CanonicalField(
        "payment_method",
        FeatureTiming.DECISION_TIME,
        "string",
        False,
        None,
        "Chosen payment method",
    ),
    CanonicalField(
        "installments",
        FeatureTiming.DECISION_TIME,
        "integer",
        False,
        "count",
        "Agreed installment count",
    ),
    CanonicalField(
        "manual_exception",
        FeatureTiming.DECISION_TIME,
        "boolean",
        False,
        None,
        "Exception recorded during approval",
    ),
    CanonicalField("currency", FeatureTiming.METADATA, "string", True, None, "Source currency"),
    CanonicalField(
        "cancellation",
        FeatureTiming.OUTCOME,
        "boolean",
        True,
        None,
        "Cancellation observed after booking",
    ),
    CanonicalField(
        "refund_amount_eur", FeatureTiming.OUTCOME, "float", True, "EUR", "Realized refund amount"
    ),
    CanonicalField(
        "refund_date", FeatureTiming.POST_DECISION, "date", False, None, "Date a refund occurred"
    ),
    CanonicalField(
        "booking_changes",
        FeatureTiming.POST_DECISION,
        "integer",
        False,
        "count",
        "Changes after initial booking",
    ),
    CanonicalField(
        "support_cases",
        FeatureTiming.POST_DECISION,
        "integer",
        False,
        "count",
        "Support interactions after booking",
    ),
    CanonicalField(
        "support_cost_eur", FeatureTiming.OUTCOME, "float", True, "EUR", "Realized support cost"
    ),
    CanonicalField(
        "additional_cost_eur",
        FeatureTiming.OUTCOME,
        "float",
        True,
        "EUR",
        "Unplanned realized cost",
    ),
    CanonicalField(
        "gross_profit_eur", FeatureTiming.OUTCOME, "float", True, "EUR", "Realized gross profit"
    ),
    CanonicalField(
        "contribution_margin_eur",
        FeatureTiming.OUTCOME,
        "float",
        True,
        "EUR",
        "Realized contribution after downstream costs",
    ),
    CanonicalField(
        "repeat_purchase_180d",
        FeatureTiming.OUTCOME,
        "boolean",
        False,
        None,
        "Repeat purchase within outcome window (MNAR-bounded, missingness expected)",
    ),
    CanonicalField(
        "last_modified_at",
        FeatureTiming.POST_DECISION,
        "date",
        False,
        None,
        "Operational update timestamp; leakage field",
    ),
)

CANONICAL_FIELDS_BY_NAME: dict[str, CanonicalField] = {
    field.name: field for field in CANONICAL_SCHEMA
}


def required_fields() -> tuple[str, ...]:
    return tuple(field.name for field in CANONICAL_SCHEMA if field.required)
