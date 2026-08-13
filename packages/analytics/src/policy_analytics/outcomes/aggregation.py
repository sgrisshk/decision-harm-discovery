"""Pure group-summary arithmetic over an outcome definition (TASK-013).

These functions compute descriptive statistics for a candidate condition against its comparison
group — the "deterministic economic exposure" the `TASK-015` candidate contract requires. They do
not search for conditions, decide which conditions are interesting, or rank candidates: producing
the *set* of candidates is `TASK-015`; ordering them is `TASK-016`. This module only turns a
group of values plus an `OutcomeDefinition` into numbers, deterministically and the same way every
time (ADR-004).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from policy_analytics.outcomes.contract import MissingDataPolicy, OutcomeDefinition


@dataclass(frozen=True, slots=True)
class GroupSummary:
    """Descriptive statistics for one group on one outcome. No inference, no interval."""

    outcome_id: str
    n_total: int
    n_present: int
    missing_count: int
    missing_rate: float
    mean: float | None
    variance: float | None

    def __post_init__(self) -> None:
        if self.n_total < 0 or self.missing_count < 0:
            raise ValueError("counts cannot be negative")
        if self.missing_count > self.n_total:
            raise ValueError("missing_count cannot exceed n_total")
        if self.n_present != self.n_total - self.missing_count:
            raise ValueError("n_present must equal n_total minus missing_count")
        if self.n_present == 0 and self.mean is not None:
            raise ValueError("an empty group cannot have a mean")


def summarize_group(
    values: Sequence[float | bool | None], outcome: OutcomeDefinition
) -> GroupSummary:
    """Summarize one group's values for one outcome.

    ``None`` marks a missing observation. A ``COMPLETE`` outcome with any missing value still
    produces a summary — callers must surface the missingness as a data-quality warning rather
    than silently accepting it, since G03/G07 in the validation contract depend on it being
    visible.
    """
    n_total = len(values)
    present = [float(value) for value in values if value is not None]
    missing_count = n_total - len(present)
    missing_rate = missing_count / n_total if n_total else 0.0
    mean = sum(present) / len(present) if present else None
    variance = (
        sum((value - mean) ** 2 for value in present) / len(present)
        if present and mean is not None
        else None
    )
    return GroupSummary(
        outcome_id=outcome.outcome_id,
        n_total=n_total,
        n_present=len(present),
        missing_count=missing_count,
        missing_rate=missing_rate,
        mean=mean,
        variance=variance,
    )


@dataclass(frozen=True, slots=True)
class MnarBounds:
    """Worst-case bounds for an MNAR outcome, required by validation gate G07.

    ``optimistic`` assumes every missing observation would have been the best possible value
    (1.0 for a rate outcome); ``pessimistic`` assumes the worst (0.0). The observed-only mean is
    never reported alone for an MNAR outcome.
    """

    observed_only_mean: float | None
    pessimistic_mean: float
    optimistic_mean: float


def mnar_bounds(values: Sequence[float | bool | None], outcome: OutcomeDefinition) -> MnarBounds:
    """Bound a rate-valued MNAR outcome assuming missing values in [0, 1].

    Only defined for ``MissingDataPolicy.MNAR_BOUNDED`` outcomes whose present values already lie
    in [0, 1]; this module does not know how to bound an unbounded quantity.
    """
    if outcome.missing_data_policy is not MissingDataPolicy.MNAR_BOUNDED:
        raise ValueError(f"{outcome.outcome_id} is not an MNAR-bounded outcome")
    present = [float(value) for value in values if value is not None]
    if any(not 0.0 <= value <= 1.0 for value in present):
        raise ValueError("mnar_bounds only supports outcomes valued in [0, 1]")
    n_total = len(values)
    n_present = len(present)
    n_missing = n_total - n_present
    if n_total == 0:
        return MnarBounds(observed_only_mean=None, pessimistic_mean=0.0, optimistic_mean=0.0)
    observed_only = sum(present) / n_present if n_present else None
    pessimistic = sum(present) / n_total if n_present else 0.0
    optimistic = (sum(present) + n_missing) / n_total
    return MnarBounds(
        observed_only_mean=observed_only, pessimistic_mean=pessimistic, optimistic_mean=optimistic
    )


def raw_difference(exposed: GroupSummary, comparison: GroupSummary) -> float:
    """Signed exposed-minus-comparison difference in the outcome's own direction."""
    if exposed.mean is None or comparison.mean is None:
        raise ValueError("cannot compute a difference when either group has no present values")
    if exposed.outcome_id != comparison.outcome_id:
        raise ValueError("groups must summarize the same outcome")
    return exposed.mean - comparison.mean


def harm_score(difference: float, outcome: OutcomeDefinition) -> float:
    """Normalize a raw difference so a positive value always means harm."""
    return difference * outcome.harm_multiplier


def historical_exposure(
    exposed: GroupSummary, comparison: GroupSummary, outcome: OutcomeDefinition
) -> float:
    """Undiscounted, unadjusted historical exposure: harm per record times exposed records.

    This is raw descriptive exposure over the observed window only — not annualized, not
    interval-bounded, not adjusted for confounding. It answers "how much value sits in these
    records under the naive raw comparison", which is what the `TASK-015` candidate contract asks
    discovery to report. Annualization, uncertainty, and adjustment belong to `TASK-021`/`TASK-023`
    (Statistics), applied only to candidates that survive the validation gates.
    """
    return harm_score(raw_difference(exposed, comparison), outcome) * exposed.n_present


def missingness_gap(exposed: GroupSummary, comparison: GroupSummary) -> float:
    """Absolute difference in missingness rate between groups; feeds validation gate G07."""
    if exposed.outcome_id != comparison.outcome_id:
        raise ValueError("groups must summarize the same outcome")
    return abs(exposed.missing_rate - comparison.missing_rate)
