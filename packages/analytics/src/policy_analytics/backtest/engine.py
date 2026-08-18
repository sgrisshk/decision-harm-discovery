"""Policy backtest engine (TASK-032): mechanical replay of a trigger condition against
`future_holdout`, per `docs/analytics/validation-contract.md` §9.

Reuses, rather than re-implements, the same primitives `TASK-018`/`TASK-023` already use and
already have test coverage: `Condition`/`rule_expr` (rule evaluation), `split_stats` (the real,
unresampled point estimate), `cluster_cells`/`cluster_bootstrap_replicates`/`percentile_ci`
(customer-clustered uncertainty). This module adds no new estimation primitive — only the
backtest-specific framing (`future_holdout`-only, both-sides counts, operational cost, mechanical
upper-bound disclosure).
"""

from __future__ import annotations

import random
from collections.abc import Sequence

import polars as pl

from policy_analytics.backtest.contract import (
    BACKTEST_CONTRACT_VERSION,
    BACKTEST_WINDOW_SPLIT,
    BAD_OUTCOME_SUPPORTED_OUTCOME_ID,
    BAD_OUTCOME_THRESHOLD,
    BacktestResult,
)
from policy_analytics.outcomes import OutcomeDefinition
from policy_analytics.validation.apply import (
    Condition,
    cluster_bootstrap_replicates,
    cluster_cells,
    percentile_ci,
    rule_expr,
    split_stats,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS
from policy_analytics.validation.report import EffectEstimate

BACKTEST_BOOTSTRAP_REPS = 1000
BACKTEST_BOOTSTRAP_SEED = 20260818

METHODOLOGY_DISCLOSURE = (
    "Mechanical replay of the trigger condition against future_holdout only (decision-time-only, "
    "out-of-period first, docs/analytics/validation-contract.md §9). Assumes no behavioural "
    "change from customers, managers, or suppliers in response to the policy — an upper bound on "
    "mechanical effect, not a forecast. benefit is unadjusted (raw, not confounder-adjusted)."
)


def _widen_to_contain(value: float, ci_low: float, ci_high: float) -> tuple[float, float]:
    return min(ci_low, ci_high, value), max(ci_low, ci_high, value)


def run_backtest(
    *,
    frame: pl.DataFrame,
    conditions: Sequence[Condition],
    outcome: OutcomeDefinition,
    cost_per_review_eur: float | None = None,
    bootstrap_reps: int = BACKTEST_BOOTSTRAP_REPS,
    rng: random.Random | None = None,
) -> BacktestResult:
    """Backtest one trigger condition, expressed as `Condition`s, against `future_holdout`.

    Thin wrapper around `backtest_from_mask()` that builds the exposure mask from `conditions` via
    `rule_expr` — the normal path for a real Finding's `pattern.conditions`. `TASK-033` calls
    `backtest_from_mask()` directly with a ground-truth-derived membership mask instead, since a
    synthetic pattern's `affected_booking_ids` cannot always be expressed as this repository's
    restricted `Condition` grammar (no `IN (...)` support).
    """
    holdout_frame = frame.filter(pl.col("split_label") == BACKTEST_WINDOW_SPLIT)  # pyright: ignore[reportUnknownMemberType]
    rule_mask = holdout_frame.select(rule_expr(conditions).alias("m"))["m"]
    return backtest_from_mask(
        frame=frame,
        rule_mask_within_holdout=rule_mask,
        outcome=outcome,
        cost_per_review_eur=cost_per_review_eur,
        bootstrap_reps=bootstrap_reps,
        rng=rng,
    )


def backtest_from_mask(
    *,
    frame: pl.DataFrame,
    rule_mask_within_holdout: pl.Series,
    outcome: OutcomeDefinition,
    cost_per_review_eur: float | None = None,
    bootstrap_reps: int = BACKTEST_BOOTSTRAP_REPS,
    rng: random.Random | None = None,
) -> BacktestResult:
    """Backtest an already-computed exposure mask against `future_holdout`.

    `rule_mask_within_holdout` must be a boolean `Series` the same length as, and aligned row-for-
    row with, `frame.filter(pl.col("split_label") == "future_holdout")` — not the full `frame`.

    Raises `ValueError` if `outcome` is not `contribution_margin_eur` (v1.0.0 scope limit, §
    `BAD_OUTCOME_SUPPORTED_OUTCOME_ID`), if `future_holdout` has no exposed or no comparison
    records under this mask (nothing to backtest), or if a missing outcome value is found among
    affected records (a `MissingDataPolicy.COMPLETE` contract violation — never silently excluded,
    matching `DISCOVERY_CONTRACT.primary_outcome_missing_handling`).
    """
    if outcome.outcome_id != BAD_OUTCOME_SUPPORTED_OUTCOME_ID:
        raise ValueError(
            f"v{BACKTEST_CONTRACT_VERSION} only supports "
            f"{BAD_OUTCOME_SUPPORTED_OUTCOME_ID!r} as the backtest outcome; got "
            f"{outcome.outcome_id!r}"
        )
    if rng is None:
        rng = random.Random(BACKTEST_BOOTSTRAP_SEED)

    holdout_frame = frame.filter(pl.col("split_label") == BACKTEST_WINDOW_SPLIT)  # pyright: ignore[reportUnknownMemberType]
    rule_mask = rule_mask_within_holdout
    if rule_mask.len() != holdout_frame.height:
        raise ValueError(
            "rule_mask_within_holdout must be aligned with the future_holdout-filtered frame "
            f"({rule_mask.len()} != {holdout_frame.height})"
        )

    stats = split_stats(holdout_frame, rule_mask, outcome, BACKTEST_WINDOW_SPLIT)
    if stats is None:
        raise ValueError(
            "future_holdout has no exposed or no comparison records for this condition — nothing "
            "to backtest"
        )

    affected_values = holdout_frame.filter(rule_mask)[outcome.column].to_list()  # pyright: ignore[reportUnknownMemberType]
    if any(value is None for value in affected_values):
        raise ValueError(
            f"{outcome.outcome_id} has MissingDataPolicy.COMPLETE; a missing value among "
            "future_holdout's affected records means the dataset no longer matches its pinned "
            "identity and this backtest run should be treated as suspect"
        )
    avoided_bad = sum(1 for value in affected_values if value < BAD_OUTCOME_THRESHOLD)
    suppressed_good = sum(1 for value in affected_values if value >= BAD_OUTCOME_THRESHOLD)

    clusters = cluster_cells(holdout_frame, rule_mask, outcome.column)
    raw_reps = cluster_bootstrap_replicates(clusters, bootstrap_reps, rng)
    confidence_level = DEFAULT_THRESHOLDS.confidence_level

    benefit_value = stats.harm_per_booking * stats.n_exposed
    benefit_reps = [d * outcome.harm_multiplier * stats.n_exposed for d in raw_reps]
    benefit_low, benefit_high = percentile_ci(benefit_reps, confidence_level)
    benefit_low, benefit_high = _widen_to_contain(benefit_value, benefit_low, benefit_high)
    benefit = EffectEstimate(
        benefit_value,
        benefit_low,
        benefit_high,
        confidence_level,
        "cluster_bootstrap_customer_id_future_holdout_raw",
        outcome.unit,
    )

    operational_cost: EffectEstimate | None = None
    if cost_per_review_eur is not None:
        cost_value = cost_per_review_eur * stats.n_exposed
        operational_cost = EffectEstimate(
            cost_value,
            cost_value,
            cost_value,
            confidence_level,
            "assumed_input_no_interval",
            outcome.unit,
        )
        net_value = benefit_value - cost_value
        net_low, net_high = benefit_low - cost_value, benefit_high - cost_value
        net_low, net_high = _widen_to_contain(net_value, net_low, net_high)
        net_method = "cluster_bootstrap_customer_id_future_holdout_raw_minus_assumed_cost"
    else:
        net_value, net_low, net_high = benefit_value, benefit_low, benefit_high
        net_method = benefit.method

    net_effect = EffectEstimate(
        net_value, net_low, net_high, confidence_level, net_method, outcome.unit
    )
    excludes_zero = net_effect.ci_low > 0 or net_effect.ci_high < 0

    return BacktestResult(
        backtest_contract_version=BACKTEST_CONTRACT_VERSION,
        outcome_name=outcome.outcome_id,
        outcome_unit=outcome.unit,
        window=BACKTEST_WINDOW_SPLIT,
        affected_decisions=stats.n_exposed,
        avoided_bad_outcomes=avoided_bad,
        suppressed_good_outcomes=suppressed_good,
        bad_outcome_definition=(
            f"{BAD_OUTCOME_SUPPORTED_OUTCOME_ID} < {BAD_OUTCOME_THRESHOLD} "
            "(loses money outright, per the outcome contract's own documented threshold)"
        ),
        benefit=benefit,
        benefit_is_adjusted=False,
        operational_cost_per_review_eur=cost_per_review_eur,
        operational_cost=operational_cost,
        net_effect=net_effect,
        net_effect_is_cost_exclusive=operational_cost is None,
        no_measurable_net_effect=not excludes_zero,
        methodology_disclosure=METHODOLOGY_DISCLOSURE,
    )
