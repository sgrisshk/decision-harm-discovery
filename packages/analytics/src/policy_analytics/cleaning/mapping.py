"""Column mapping from a raw ingested dataset onto the canonical schema (TASK-010).

A mapping says which source column (if any) supplies each canonical field, plus how to coerce its
values. It is never invented automatically for real data: `suggest_mapping` proposes candidates
from exact/alias name matches only and is explicitly advisory (see its own docstring) — an actual
`ColumnMapping` used to canonicalize real customer data must be confirmed by a human, matching this
repository's rule that semantic meaning is never guessed silently (`ADR-004`,
`engineering rules`: "never allow unknown ... fields into explanatory features silently"). The synthetic
benchmark is the one dataset whose canonical identity mapping is safe to construct automatically,
because its column names already *are* the canonical names by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from policy_schemas.domain import FeatureTiming

from policy_analytics.cleaning.canonical_schema import (
    CANONICAL_FIELDS_BY_NAME,
    CANONICAL_SCHEMA,
    CANONICAL_SCHEMA_VERSION,
)
from policy_analytics.profiling.feature_timing import FeatureTimingClassification
from policy_analytics.profiling.schema_profiler import ColumnProfile

#: Known alternate source names per canonical field, used only to *suggest* a mapping — never
#: applied without confirmation. Sourced from the one other real schema variant this repository
#: has ever seen (`tests/fixtures/synthetic_travel_bookings.csv`, an earlier bootstrap fixture with
#: different column names for the same booking concepts), not invented.
KNOWN_ALIASES: dict[str, tuple[str, ...]] = {
    "customer_price_eur": ("customer_price",),
    "quoted_cost_eur": ("cost",),
    "discount_rate": ("discount",),
    "gross_profit_eur": ("gross_margin",),
    "trip_duration_days": ("trip_duration",),
    "booking_lead_days": ("booking_lead_time",),
    "refund_amount_eur": ("refund_amount",),
    "additional_cost_eur": ("additional_cost",),
    "repeat_purchase_180d": ("repeat_purchase",),
}


@dataclass(frozen=True, slots=True)
class FieldMapping:
    canonical_name: str
    source_column: str


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    """`fields` covers only canonical names that have a source column — an absent canonical field
    means "not present in this raw dataset," checked against `required_fields()` by
    `normalize.canonicalize`, never assumed here."""

    schema_version: str
    fields: tuple[FieldMapping, ...]

    def source_for(self, canonical_name: str) -> str | None:
        for mapping in self.fields:
            if mapping.canonical_name == canonical_name:
                return mapping.source_column
        return None


def suggest_mapping(profiles: tuple[ColumnProfile, ...]) -> ColumnMapping:
    """Propose a mapping from exact (case-insensitive) or known-alias name matches only.

    Advisory. This function makes no claim about correctness for a dataset it has never seen — a
    matching name is a hint a human should confirm, not evidence the columns mean the same thing.
    """
    by_lower = {profile.name.lower(): profile.name for profile in profiles}
    fields: list[FieldMapping] = []
    for field in CANONICAL_SCHEMA:
        candidates = (field.name, *KNOWN_ALIASES.get(field.name, ()))
        for candidate in candidates:
            source = by_lower.get(candidate.lower())
            if source is not None:
                fields.append(FieldMapping(canonical_name=field.name, source_column=source))
                break
    return ColumnMapping(schema_version=CANONICAL_SCHEMA_VERSION, fields=tuple(fields))


def validate_mapping(
    mapping: ColumnMapping, classifications: tuple[FeatureTimingClassification, ...]
) -> tuple[str, ...]:
    """Return every problem with `mapping`, empty if none. Does not raise — callers decide whether
    any given problem is fatal (`normalize.canonicalize` treats all of these as fatal)."""
    errors: list[str] = []
    timing_by_source = {c.column_name: c.timing for c in classifications}
    seen_sources: dict[str, str] = {}

    for field_mapping in mapping.fields:
        canonical = CANONICAL_FIELDS_BY_NAME.get(field_mapping.canonical_name)
        if canonical is None:
            errors.append(f"'{field_mapping.canonical_name}' is not a canonical field")
            continue

        source = field_mapping.source_column
        if source in seen_sources:
            errors.append(
                f"source column '{source}' is mapped to both "
                f"'{seen_sources[source]}' and '{field_mapping.canonical_name}'"
            )
        else:
            seen_sources[source] = field_mapping.canonical_name

        source_timing = timing_by_source.get(source)
        if source_timing is None:
            errors.append(f"source column '{source}' has no feature-timing classification")
        elif (
            canonical.role is FeatureTiming.DECISION_TIME
            and source_timing is not FeatureTiming.DECISION_TIME
        ):
            # The one safety-critical check: refuse to launder a column TASK-008 classified as
            # non-decision-time into a canonical decision-time field, however the mapping got
            # constructed. This does not forbid other role combinations — a source column TASK-008
            # called DECISION_TIME can still be mapped onto a canonical OUTCOME/METADATA/etc. field
            # (e.g. a customer's own "currency" export might get profiled as categorical
            # DECISION_TIME by TASK-008's generic rules; the canonical schema is the more informed,
            # human-confirmed source of truth for that one field once mapped).
            errors.append(
                f"'{field_mapping.canonical_name}' is DECISION_TIME in the canonical schema but "
                f"source column '{source}' was classified {source_timing.value.upper()}, not "
                "DECISION_TIME — refusing to launder it into a decision-time feature"
            )

    missing_required = [
        field.name
        for field in CANONICAL_SCHEMA
        if field.required and mapping.source_for(field.name) is None
    ]
    if missing_required:
        errors.append(f"missing required canonical field(s): {', '.join(missing_required)}")

    return tuple(errors)
