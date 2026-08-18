"""Builds `discovery.ranking` inputs from a persisted candidate document (TASK-016).

`ranking.rank_candidates` is a pure function over `CandidateSignals`; this module is the one piece
of I/O-adjacent glue that turns a frozen candidates artifact (the blind-agent output schema,
`tools/blind_agent/models.py` `OUTPUT_SCHEMA_VERSION = "1.1.0"`, or the original discovery engine's
inline shape) plus the analytical dataset into those inputs.

A candidate's own committed `economic_exposure`, `support`, and `raw_effect` are trusted exactly
as frozen — this module never recomputes them differently from what was persisted. Only what the
frozen document does not carry — later-split direction stability and development-split exposure
membership for novelty — is recomputed from the analytical dataset, the same discipline
`validation.apply` already uses when it grades a candidate (it never trusts precomputed split
stats either; see its module docstring).
"""

from __future__ import annotations

from typing import Any, cast

import polars as pl

from policy_analytics.discovery.actionability import actionability_score
from policy_analytics.discovery.ranking import CandidateSignals
from policy_analytics.outcomes import OutcomeDefinition
from policy_analytics.validation.apply import SPLITS, Condition, rule_expr, split_stats


def _conditions_from(raw_conditions: list[dict[str, Any]]) -> tuple[Condition, ...]:
    return tuple(Condition(raw["feature"], raw["operator"], raw["value"]) for raw in raw_conditions)


def _development_exposed_ids(
    frame: pl.DataFrame, conditions: tuple[Condition, ...]
) -> frozenset[int]:
    development = frame.filter(pl.col("split_label") == "development")  # pyright: ignore[reportUnknownMemberType]
    mask = development.select(rule_expr(conditions).alias("m"))["m"].to_list()
    return frozenset(index for index, exposed in enumerate(mask) if exposed)


def _later_split_stability(
    frame: pl.DataFrame,
    conditions: tuple[Condition, ...],
    outcome: OutcomeDefinition,
    reference_sign_positive: bool,
) -> float | None:
    """Share of available later splits whose recomputed harm direction matches the committed one.

    `None` (not `0.0`) when no later split had any exposure to check — `ranking.rank_candidates`
    treats that as an explicitly missing, conservatively-scored signal, never as passing.
    """
    agreements: list[bool] = []
    for split in SPLITS:
        if split == "development":
            continue
        split_frame = frame.filter(pl.col("split_label") == split)  # pyright: ignore[reportUnknownMemberType]
        mask = split_frame.select(rule_expr(conditions).alias("m"))["m"]
        stats = split_stats(split_frame, mask, outcome, split)
        if stats is not None:
            agreements.append((stats.harm_per_booking > 0) == reference_sign_positive)
    if not agreements:
        return None
    return sum(agreements) / len(agreements)


def build_candidate_signals(
    candidates_payload: dict[str, Any], frame: pl.DataFrame, outcome: OutcomeDefinition
) -> tuple[CandidateSignals, ...]:
    """One `CandidateSignals` per candidate in `candidates_payload["candidates"]`, in order."""
    signals: list[CandidateSignals] = []
    for candidate in cast(list[dict[str, Any]], candidates_payload["candidates"]):
        conditions = _conditions_from(cast(list[dict[str, Any]], candidate["conditions"]))
        reference_sign_positive = float(candidate["raw_effect"]) * outcome.harm_multiplier > 0
        signals.append(
            CandidateSignals(
                candidate_id=str(candidate["candidate_id"]),
                economic_impact=abs(float(candidate["economic_exposure"])),
                support=float(candidate["support"]),
                stability=_later_split_stability(
                    frame, conditions, outcome, reference_sign_positive
                ),
                actionability=actionability_score(conditions),
                exposed_row_ids=_development_exposed_ids(frame, conditions),
                warning_count=len(cast(list[str], candidate.get("warnings", []))),
            )
        )
    return tuple(signals)
