"""Multi-factor candidate ranking (TASK-016).

Discovery's search-time order is deliberately a single number — development historical exposure
with a mild complexity penalty (`engine._development_score`) — used only to decide which
candidates survive the beam search and deduplication. `docs/analytics/discovery-engine-v0.md`
says so explicitly: *"Preliminary order is development historical exposure with a mild complexity
penalty. Full multi-factor ranking is TASK-016."* This module is that ranking.

`rank_candidates` is a pure function over `CandidateSignals` — it does no I/O, opens no dataset,
and never touches hidden ground truth. It combines five components into one transparent score,
with every component exposed on the result, specifically so ranking can never quietly collapse
back into "whatever the search's own importance number said":

- **economic_impact** — magnitude of the committed development-split economic exposure.
- **support** — how much of the eligible population the condition covers.
- **stability** — share of available later chronological splits whose harm direction agrees with
  the committed one. Missing (`None`, no later split had exposure) is scored as `0.0`, never as
  passing — a candidate this module cannot vouch for as stable must not rank as if it were stable.
- **actionability** — `policy_analytics.discovery.actionability`; whether a condition touches a
  field the business can directly change.
- **novelty** — `1 - ` the largest pairwise Jaccard overlap of a candidate's development-split
  exposed population against every other candidate in the same ranked set. A candidate that is
  mostly a re-slice of another candidate's population adds little beyond it and is scored low here
  even if its own economic exposure looks large.

**Weight provenance.** `DEFAULT_WEIGHTS` are ML_DISCOVERY-authored v0 defaults, fixed from
ordinary business reasoning (impact and durability matter most; support, actionability, and
novelty matter but less) before this module was ever run against a specific candidate set — not
fit, tuned, or reweighted after looking at any ranking output, benchmark grade, or hidden ground
truth. `docs/analytics/discovery-design.md` §7 calls for these weights to eventually come from a
Product/Statistics-approved contract rather than ML Discovery invention alone; that review is
requested separately (see `HANDOFF-045` in `memory/HANDOFFS.md`) and `RANKING_METHOD_VERSION`
exists precisely so a future contract change is visible and comparable, not silently retroactive.

Ranking never edits, drops, reorders the persisted candidate list itself, or changes any of a
candidate's own committed metrics — it only orders and annotates an already-frozen candidate set.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

RANKING_METHOD_VERSION = "candidate-ranking-v0.1.0"


@dataclass(frozen=True, slots=True)
class RankingWeights:
    """Weights for the five ranking components. Must sum to 1.0."""

    economic_impact: float = 0.35
    support: float = 0.15
    stability: float = 0.20
    actionability: float = 0.15
    novelty: float = 0.15

    def __post_init__(self) -> None:
        total = (
            self.economic_impact
            + self.support
            + self.stability
            + self.actionability
            + self.novelty
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"ranking weights must sum to 1.0, got {total}")


DEFAULT_WEIGHTS = RankingWeights()

#: Every candidate carries the standard non-causal boilerplate warning; only warnings beyond that
#: one penalize the score, at 0.05 per extra warning, capped so no single component can dominate.
WARNING_PENALTY_PER_EXTRA = 0.05
MAX_WARNING_PENALTY = 0.20


@dataclass(frozen=True, slots=True)
class CandidateSignals:
    """Raw, not-yet-normalized ranking inputs for one candidate.

    `economic_impact` and `support` are taken as-is from the already-frozen candidate document
    (unbounded magnitudes; normalized against the rest of the batch inside `rank_candidates`).
    `stability` and `actionability` are already meaningful in absolute [0, 1] terms and are not
    renormalized. `exposed_row_ids` is the development-split row-index set the condition selects,
    used only to compute novelty against the other candidates in the same call.
    """

    candidate_id: str
    economic_impact: float
    support: float
    stability: float | None
    actionability: float
    exposed_row_ids: frozenset[int]
    warning_count: int = 0

    def __post_init__(self) -> None:
        if self.economic_impact < 0:
            raise ValueError("economic_impact must be non-negative (pass the magnitude)")
        if not 0.0 <= self.support <= 1.0:
            raise ValueError("support must be a fraction in [0, 1]")
        if self.stability is not None and not 0.0 <= self.stability <= 1.0:
            raise ValueError("stability must be None or a fraction in [0, 1]")
        if not 0.0 <= self.actionability <= 1.0:
            raise ValueError("actionability must be a fraction in [0, 1]")


@dataclass(frozen=True, slots=True)
class RankingComponents:
    """Every normalized component that fed the composite score, for audit."""

    economic_impact: float
    support: float
    stability: float
    actionability: float
    novelty: float
    warning_penalty: float

    def to_dict(self) -> dict[str, float]:
        return {
            "economic_impact": self.economic_impact,
            "support": self.support,
            "stability": self.stability,
            "actionability": self.actionability,
            "novelty": self.novelty,
            "warning_penalty": self.warning_penalty,
        }


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate_id: str
    rank: int
    rank_score: float
    components: RankingComponents
    stability_missing: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "rank": self.rank,
            "rank_score": self.rank_score,
            "components": self.components.to_dict(),
            "stability_missing": self.stability_missing,
        }


@dataclass(frozen=True, slots=True)
class _Scored:
    candidate_id: str
    rank_score: float
    components: RankingComponents
    stability_missing: bool


def _normalize(value: float, low: float, high: float) -> float:
    if high - low <= 1e-12:
        # Degenerate batch (every candidate has the same value): the component cannot break any
        # tie either way, so it is neutral rather than arbitrarily penalizing everyone.
        return 1.0
    return (value - low) / (high - low)


def _jaccard(left: frozenset[int], right: frozenset[int]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def rank_candidates(
    signals: Sequence[CandidateSignals], weights: RankingWeights = DEFAULT_WEIGHTS
) -> tuple[RankedCandidate, ...]:
    """Rank candidates by a transparent, weighted combination of five components.

    Deterministic: ties in `rank_score` break on `candidate_id`, never on input order.
    """
    if not signals:
        return ()

    economic_values = [signal.economic_impact for signal in signals]
    support_values = [signal.support for signal in signals]
    econ_low, econ_high = min(economic_values), max(economic_values)
    support_low, support_high = min(support_values), max(support_values)

    scored: list[_Scored] = []
    for signal in signals:
        economic_norm = _normalize(signal.economic_impact, econ_low, econ_high)
        support_norm = _normalize(signal.support, support_low, support_high)
        stability_missing = signal.stability is None
        stability_value = 0.0 if signal.stability is None else signal.stability

        max_overlap = max(
            (
                _jaccard(signal.exposed_row_ids, other.exposed_row_ids)
                for other in signals
                if other.candidate_id != signal.candidate_id
            ),
            default=0.0,
        )
        novelty_value = 1.0 - max_overlap

        warning_penalty = min(
            WARNING_PENALTY_PER_EXTRA * max(0, signal.warning_count - 1), MAX_WARNING_PENALTY
        )

        weighted = (
            weights.economic_impact * economic_norm
            + weights.support * support_norm
            + weights.stability * stability_value
            + weights.actionability * signal.actionability
            + weights.novelty * novelty_value
        )
        rank_score = max(0.0, weighted - warning_penalty)

        scored.append(
            _Scored(
                candidate_id=signal.candidate_id,
                rank_score=rank_score,
                components=RankingComponents(
                    economic_impact=economic_norm,
                    support=support_norm,
                    stability=stability_value,
                    actionability=signal.actionability,
                    novelty=novelty_value,
                    warning_penalty=warning_penalty,
                ),
                stability_missing=stability_missing,
            )
        )

    scored.sort(key=lambda item: (-item.rank_score, item.candidate_id))
    return tuple(
        RankedCandidate(
            candidate_id=item.candidate_id,
            rank=index,
            rank_score=item.rank_score,
            components=item.components,
            stability_missing=item.stability_missing,
        )
        for index, item in enumerate(scored, start=1)
    )
