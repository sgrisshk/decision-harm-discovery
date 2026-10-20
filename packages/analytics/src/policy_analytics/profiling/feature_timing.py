"""Deterministic feature-timing classification (TASK-008).

Classifies every profiled column (`policy_analytics.profiling.schema_profiler.ColumnProfile`,
`TASK-007`) into exactly one `policy_schemas.domain.FeatureTiming`: `IDENTIFIER`, `DECISION_TIME`,
`POST_DECISION`, `OUTCOME`, `METADATA`, or `UNKNOWN`.

Safety invariant this module exists to enforce (`ARCHITECTURE.md` §4 and the shared engineering
rules): only `DECISION_TIME` columns may ever become explanatory features. Every other
classification — including `UNKNOWN` — is excluded by
`policy_analytics.outcomes.contract.EXCLUDED_EXPLANATORY_CLASSIFICATIONS`. That makes `UNKNOWN` the
safe default: a column this module cannot confidently place is never silently admitted as
`DECISION_TIME`. `DECISION_TIME` itself is reached only through explicit, disclosed positive rules
below (categorical attribute, quoted/agreed amount, plausible booking-time count, recognized flag,
or a date with no post-decision-event name signal) — never as a catch-all for "nothing else
matched."

No ML/black-box guessing (`ADR-004`): every rule here is a plain, disclosed, whole-token name match
or a `TASK-007` profiler signal — nothing invented, nothing opaque, no dataset-specific hardcoding.
Column-name tokens are matched as whole tokens (`name.lower().split("_")`), never raw substring
containment, matching `schema_profiler._guess_semantic_type`'s own fix for the same class of bug
(`trip_duration` must never match a "ratio" hint just because "duration" contains it as a
substring).

This is a best-effort classifier, not a certainty oracle: real customer column names will not
always match these rules. `docs/analytics/discovery-design.md` §13's readiness gate independently
requires "feature timing contains no unknowns" before discovery may run on a dataset — i.e. any
`UNKNOWN` this module produces is expected to require explicit human resolution downstream, not to
be silently worked around here.
"""

from __future__ import annotations

from dataclasses import dataclass

from policy_schemas.domain import FeatureTiming

from policy_analytics.profiling.schema_profiler import ColumnProfile

# --- METADATA: non-explanatory record attributes (currency, locale, ...) ---------------------
_METADATA_NAME_HINTS = frozenset({"currency", "locale", "timezone", "language"})

# --- OUTCOME: realized, post-hoc business results -----------------------------------------------
#: Multi-token phrases: every token in the set must appear in the column's name tokens. "cost" and
#: "purchase" alone are too broad to be unambiguous outcome signals (a quoted cost is
#: DECISION_TIME) — only these specific qualified combinations are.
_OUTCOME_PHRASES: tuple[frozenset[str], ...] = (
    frozenset({"support", "cost"}),
    frozenset({"additional", "cost"}),
    frozenset({"repeat", "purchase"}),
)
#: Single tokens that are themselves unambiguous outcome signals. "margin"/"profit"/"revenue" are
#: always realized accounting results in this domain, whether bare or compound ("gross_margin",
#: "net_profit", "contribution_margin", "operating_margin" all match via the bare token) — nothing
#: in a travel-booking business quotes "the margin" as a customer-facing decision-time promise.
_OUTCOME_SINGLE_HINTS = frozenset(
    {
        "profit",
        "margin",
        "revenue",
        "cancellation",
        "cancelled",
        "canceled",
        "churn",
        "retention",
        "satisfaction",
        "nps",
    }
)

# --- POST_DECISION: operational events/dates between decision and final outcome ------------------
_POST_DECISION_EVENT_HINTS = frozenset(
    {
        "modified",
        "updated",
        "processed",
        "resolved",
        "closed",
        "changes",
        "complaint",
        "dispute",
        "chargeback",
        "ticket",
    }
)
_POST_DECISION_PHRASES: tuple[frozenset[str], ...] = (frozenset({"support", "cases"}),)
#: A "*_date"-named column is POST_DECISION only if it also names a post-decision event — a bare
#: "date" token alone (booking_date, travel_date) defaults to DECISION_TIME, handled below.
_POST_DECISION_DATE_EVENT_HINTS = frozenset(
    {"refund", "cancel", "modified", "updated", "resolved", "closed", "processed"}
)

# --- DECISION_TIME: explicit positive attribute-of-record patterns -------------------------------
#: Reused/aligned with (not imported from) `schema_profiler._CURRENCY_NAME_HINTS`/`_RATE_NAME_HINTS`
#: — small deliberate duplication over a private cross-module import.
_QUOTED_AMOUNT_NAME_HINTS = frozenset(
    {"price", "cost", "amount", "discount", "fee", "rate", "pct", "percentage"}
)
#: A quoted/agreed amount whose name also carries one of these is realized, not decision-time —
#: never let this tier override an ambiguous "realized"-sounding amount into DECISION_TIME.
_REALIZED_QUALIFIER_HINTS = frozenset({"realized", "actual", "final", "true"})
_DECISION_TIME_COUNT_HINTS = frozenset(
    {
        "party",
        "size",
        "duration",
        "lead",
        "installments",
        "quantity",
        "units",
        "nights",
        "adults",
        "children",
        "rooms",
        "days",
    }
)
_DECISION_TIME_FLAG_HINTS = frozenset({"manual", "exception", "override", "approved"})


@dataclass(frozen=True, slots=True)
class FeatureTimingClassification:
    column_name: str
    timing: FeatureTiming
    reason: str


def _tokens(name: str) -> frozenset[str]:
    return frozenset(name.lower().split("_"))


def _is_identifier_name(name: str, tokens: frozenset[str]) -> bool:
    return name.lower() == "id" or (bool(tokens) and name.lower().split("_")[-1] == "id")


def classify_feature_timing(profile: ColumnProfile) -> FeatureTimingClassification:
    """Classify one profiled column. Deterministic: same profile always yields the same result."""
    name = profile.name
    tokens = _tokens(name)

    if _is_identifier_name(name, tokens) or profile.semantic_type_guess == "identifier":
        return FeatureTimingClassification(
            name, FeatureTiming.IDENTIFIER, "column name identifies a record (ends in 'id')"
        )

    if tokens & _METADATA_NAME_HINTS:
        return FeatureTimingClassification(
            name, FeatureTiming.METADATA, "column name matches a record-metadata term"
        )

    for phrase in _OUTCOME_PHRASES:
        if phrase <= tokens:
            return FeatureTimingClassification(
                name, FeatureTiming.OUTCOME, f"column name matches outcome phrase {sorted(phrase)}"
            )
    if tokens & _OUTCOME_SINGLE_HINTS:
        return FeatureTimingClassification(
            name, FeatureTiming.OUTCOME, "column name matches a realized-outcome term"
        )
    if "refund" in tokens and "date" not in tokens:
        return FeatureTimingClassification(
            name,
            FeatureTiming.OUTCOME,
            "column name names a realized refund, not a refund event date",
        )

    if tokens & _POST_DECISION_EVENT_HINTS:
        return FeatureTimingClassification(
            name, FeatureTiming.POST_DECISION, "column name matches a post-decision event term"
        )
    for phrase in _POST_DECISION_PHRASES:
        if phrase <= tokens:
            return FeatureTimingClassification(
                name,
                FeatureTiming.POST_DECISION,
                f"column name matches post-decision phrase {sorted(phrase)}",
            )
    if "date" in tokens and tokens & _POST_DECISION_DATE_EVENT_HINTS:
        return FeatureTimingClassification(
            name, FeatureTiming.POST_DECISION, "column names a date of a post-decision event"
        )

    if profile.semantic_type_guess == "categorical":
        return FeatureTimingClassification(
            name, FeatureTiming.DECISION_TIME, "low-cardinality categorical attribute of the record"
        )
    if profile.inferred_type == "date":
        return FeatureTimingClassification(
            name, FeatureTiming.DECISION_TIME, "date column with no post-decision-event name signal"
        )
    if tokens & _DECISION_TIME_COUNT_HINTS:
        return FeatureTimingClassification(
            name,
            FeatureTiming.DECISION_TIME,
            "column name matches a booking-time count/quantity term",
        )
    if tokens & _DECISION_TIME_FLAG_HINTS:
        return FeatureTimingClassification(
            name, FeatureTiming.DECISION_TIME, "column name matches a decision-time flag term"
        )
    if (
        profile.semantic_type_guess in ("currency_amount", "percentage_rate")
        or tokens & _QUOTED_AMOUNT_NAME_HINTS
    ) and not (tokens & _REALIZED_QUALIFIER_HINTS):
        return FeatureTimingClassification(
            name,
            FeatureTiming.DECISION_TIME,
            "quoted/agreed amount or rate with no realized-outcome qualifier",
        )

    return FeatureTimingClassification(
        name, FeatureTiming.UNKNOWN, "no rule matched; requires explicit human classification"
    )


def classify_columns(
    profiles: tuple[ColumnProfile, ...],
) -> tuple[FeatureTimingClassification, ...]:
    return tuple(classify_feature_timing(profile) for profile in profiles)
