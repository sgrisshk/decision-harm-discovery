"""Actionability classification shared by discovery search (TASK-015) and ranking (TASK-016).

A candidate's actionability is a coarse discovery-time label, not a Statistics or Product
judgment: conditions that touch a field the business can directly change (a commercial policy
lever) are `HIGH`; everything else needs business review before anyone could act on it at all. The
set below was fixed once, from ordinary booking-domain reasoning — the same discipline Statistics
uses for its confounder set (`validation/apply.py`'s `CONFOUNDER_COLUMNS`) — and is shared by
`discovery.engine` (the search-time label) and `discovery.ranking` (a ranking component) so the
two can never silently diverge into two different notions of "actionable".
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol


class ConditionLike(Protocol):
    @property
    def feature(self) -> str: ...


#: Fields a manager or policy owner can change directly (a discount rule, a supplier contract, a
#: payment-method restriction, ...), as opposed to fields that only describe the customer or the
#: trip and cannot themselves be turned into a policy lever.
DIRECTLY_CONTROLLABLE_FEATURES: frozenset[str] = frozenset(
    {
        "supplier",
        "discount_rate",
        "manager",
        "manual_exception",
        "payment_method",
        "installments",
        "acquisition_channel",
        "quoted_cost_eur",
        "customer_price_eur",
    }
)

ActionabilityLabel = Literal["HIGH", "REVIEW_REQUIRED"]

#: A REVIEW_REQUIRED candidate can still turn out to be genuinely actionable after business
#: review, so it is scored conservatively rather than near-zero — it simply cannot outrank an
#: otherwise-similar HIGH candidate on this component alone.
REVIEW_REQUIRED_SCORE = 0.35
HIGH_SCORE = 1.0


def actionability_label(conditions: Sequence[ConditionLike]) -> ActionabilityLabel:
    """`HIGH` if any condition touches a directly controllable field, else `REVIEW_REQUIRED`."""
    if any(condition.feature in DIRECTLY_CONTROLLABLE_FEATURES for condition in conditions):
        return "HIGH"
    return "REVIEW_REQUIRED"


def actionability_score(conditions: Sequence[ConditionLike]) -> float:
    """Numeric form of `actionability_label`, for use as a ranking component."""
    return HIGH_SCORE if actionability_label(conditions) == "HIGH" else REVIEW_REQUIRED_SCORE
