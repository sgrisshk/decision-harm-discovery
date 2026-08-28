"""POST-HOC DIAGNOSTIC (`TASK-069` reformulation item 2): is `G12`'s form fit for threshold rules?

Companion to `scripts/diagnose_validation_power.py` (reprioritization item 1), which established
that `P01` and `P03` are held at `descriptive_observation` by `G12` alone, with every other level-2
gate passing by orders of magnitude, and that `G12`'s two binding sub-checks are the numeric-
threshold perturbation and the `gross_profit_eur` alternative outcome. That autopsy explicitly
declined to answer whether `G12` is *correctly calibrated* (the effects really are fragile) or
*form-mismatched* (the perturbation grid mechanically penalises a localised threshold rule for
being localised). This script produces the evidence that decides it.

**The decisive experiment is truth-free.** Section A builds neutrally-constructed synthetic data
with invented column names, invented distributions, and invented data-generating processes whose
stability is known *by construction*, and measures the production perturbation grid against them.
Nothing in Section A reads travel, any benchmark dataset, any ground truth, or any pattern
identity; its thresholds are swept across the whole percentile range rather than chosen. The
`TASK-069` hard rule permits testing the *general* question ("does a fixed-quantile-step grid
systematically misclassify localised threshold rules, independent of which rule") and forbids using
`P01`/`P03`'s own numbers to pick or justify a replacement design. Section A is the general test;
Sections B and C are measurement of the existing gate on rules the autopsy already opened, in the
same disclosed-diagnostic posture its precedents set.

**No design work, and none authorised.** This script proposes no gate, threshold, estimator, or
perturbation rule; it writes nothing into `policy_analytics`; `validation/apply.py` is untouched and
is imported unmodified. The alternative perturbation *variants* it computes are diagnostic
counterfactuals whose only purpose is to establish whether the production grid's verdicts are
forced by the data or by the grid's construction — they are not proposals, are not tuned, and every
constant in them is derived from the production constant `PERTURBATION_QUANTILES` itself
(`(0.15, 0.25)` = a +/- 0.05 percentile step about a q0.20 anchor, and a +/- 25% exposure step at
that same anchor for a `lt` atom), never from any observed result.

Not part of the official discovery/blind/validation pipeline. Writes no artifact under `artifacts/`,
produces no official metric, changes no frozen artifact, and touches no production module.

Usage:
  uv run python scripts/diagnose_g12_perturbation_form.py
  uv run python scripts/diagnose_g12_perturbation_form.py --blind-root /path/to/artifacts/blind
  uv run python scripts/diagnose_g12_perturbation_form.py --synthetic-only
"""

# pyright: reportPrivateUsage=false
# Reuses `validation.apply`'s and the two prior diagnostics' own private functions verbatim rather
# than reimplementing their arithmetic — the precedent `diagnose_oracle_decomposition.py`,
# `diagnose_candidate_pool_recall.py`, `diagnose_g06_task065_b2b.py` and
# `diagnose_validation_power.py` already set.
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import polars as pl  # noqa: E402
from diagnose_oracle_decomposition import (  # noqa: E402
    BLIND_ROOT,
    DATASET_ROOT,
    DEFAULT_RUN_ID,
    GROUND_TRUTH_PATH,
    NON_SCOREABLE_PATTERNS,
    _render_rule,
    build_projection,
)
from diagnose_validation_power import _robustness_decomposition  # noqa: E402
from policy_analytics.discovery.engine import DiscoveryConfig, _atoms  # noqa: E402
from policy_analytics.outcomes import (  # noqa: E402
    OutcomeDefinition,
    outcome_definition_from_manifest,
)
from policy_analytics.outcomes.contract import MissingDataPolicy, OutcomeRole  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    PERTURBATION_QUANTILES,
    Condition,
    _robustness_battery,
    load_analytical_frame,
    rule_expr,
    split_stats,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS  # noqa: E402
from policy_analytics.validation.input_contract import (  # noqa: E402
    validation_input_from_manifest,
)

DEFAULT_AUTOPSY_RAW = REPOSITORY / "docs/benchmark/task-069-validation-power-autopsy-raw.json"
DEFAULT_ORACLE_RAW = REPOSITORY / "docs/benchmark/task-069-oracle-decomposition-raw.json"
DEFAULT_RAW_OUTPUT = REPOSITORY / "docs/benchmark/task-069-g12-form-investigation-raw.json"

#: Everything the diagnostic perturbation variants below are parameterised by is read off the
#: production constant rather than chosen here. `PERTURBATION_QUANTILES = (0.15, 0.25)` is a pair
#: symmetric about q0.20 with a half-width of 0.05 percentile points; for a `lt` atom sitting at
#: that anchor it moves the exposed population by +/- 25%. Those two numbers — and only those two —
#: define the "same step, applied relative to the atom's own position" counterfactuals.
IMPLIED_ANCHOR_QUANTILE = sum(PERTURBATION_QUANTILES) / len(PERTURBATION_QUANTILES)
IMPLIED_PERCENTILE_STEP = (max(PERTURBATION_QUANTILES) - min(PERTURBATION_QUANTILES)) / 2.0
IMPLIED_EXPOSURE_STEP = IMPLIED_PERCENTILE_STEP / IMPLIED_ANCHOR_QUANTILE

CEILING = DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation

SYNTHETIC_ROWS = 40_000
SYNTHETIC_SEED = 20260828
SYNTHETIC_NOISE_SD = 40.0
SYNTHETIC_EFFECT = 500.0
SYNTHETIC_BASELINE = 1_000.0
#: Swept, not chosen: the whole interior of the percentile range at a uniform spacing.
SWEEP_PERCENTILES: tuple[float, ...] = tuple(round(0.10 + 0.05 * i, 2) for i in range(17))

NEUTRAL_OUTCOME = OutcomeDefinition(
    outcome_id="synthetic_neutral_metric",
    role=OutcomeRole.PRIMARY,
    column="value_metric",
    unit="unit",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description=(
        "Neutral synthetic outcome for a truth-free G12 form experiment. Invented; unrelated to "
        "any dataset, domain, or benchmark in this repository."
    ),
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Value Metric increases",
)
NEUTRAL_VISIBLE_OUTCOME = OutcomeDefinition(
    outcome_id="synthetic_neutral_partial_metric",
    role=OutcomeRole.SECONDARY,
    column="partial_metric",
    unit="unit",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description=(
        "Neutral synthetic decomposition component of `synthetic_neutral_metric`: it excludes one "
        "of the two additive channels the total is built from. Invented; unrelated to any dataset."
    ),
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Partial Metric increases",
    decomposition_of="synthetic_neutral_metric",
)


# --------------------------------------------------------------------------------------------
# Shared perturbation arithmetic (mirrors `_robustness_battery`'s threshold-perturbation family)
# --------------------------------------------------------------------------------------------


def _threshold_percentile(column: pl.Series, value: float) -> float:
    """Where a threshold sits in its own column, by the same rule the item-1 autopsy recorded."""
    below_share = cast(Any, (column < value).mean())
    return 0.0 if below_share is None else float(cast(float, below_share))


def _fixed_grid(_own_percentile: float) -> tuple[float, ...]:
    """The production grid: the column's fixed 0.15 and 0.25 quantiles, wherever the atom sits."""
    return PERTURBATION_QUANTILES


def _relative_percentile_grid(own_percentile: float) -> tuple[float, ...]:
    """The production grid's own step size, applied about the atom's own percentile instead."""
    return tuple(
        q
        for q in (
            round(own_percentile - IMPLIED_PERCENTILE_STEP, 10),
            round(own_percentile + IMPLIED_PERCENTILE_STEP, 10),
        )
        if 0.0 < q < 1.0
    )


def _relative_exposure_grid(own_percentile: float) -> tuple[float, ...]:
    """The production grid's own exposure step, applied about the atom's own percentile.

    A threshold move that changes the *exposed population* by the same fraction in both directions,
    rather than by the same number of percentile points — the second of the two forms the task
    description names. Which side of the atom's percentile the exposed group lies on depends on the
    operator, so both sides are generated and the caller keeps whichever the operator realises.
    """
    below, above = own_percentile, 1.0 - own_percentile
    candidates = (
        below * (1.0 - IMPLIED_EXPOSURE_STEP),
        below * (1.0 + IMPLIED_EXPOSURE_STEP),
        1.0 - above * (1.0 - IMPLIED_EXPOSURE_STEP),
        1.0 - above * (1.0 + IMPLIED_EXPOSURE_STEP),
    )
    return tuple(sorted({round(q, 10) for q in candidates if 0.0 < q < 1.0}))


GRIDS: dict[str, Callable[[float], tuple[float, ...]]] = {
    "production_fixed_quantiles": _fixed_grid,
    "diagnostic_relative_percentile_step": _relative_percentile_grid,
    "diagnostic_relative_exposure_step": _relative_exposure_grid,
}


def _perturbation_checks(
    frame: pl.DataFrame,
    conditions: tuple[Condition, ...],
    outcome: OutcomeDefinition,
    base_harm: float,
    base_exposed: int,
    grid: Callable[[float], tuple[float, ...]],
) -> list[dict[str, Any]]:
    """Run the numeric-threshold perturbation family under one grid, recording every refit.

    Line-for-line the same control flow as `_robustness_battery`'s threshold loop — same condition
    filter, same `round(..., 8)`, same `rule_expr`/`split_stats` call — with the quantile source
    swapped for the caller's grid. No other check family runs here.
    """
    checks: list[dict[str, Any]] = []
    for condition in conditions:
        if not isinstance(condition.value, int | float) or isinstance(condition.value, bool):
            continue
        column = frame[condition.feature]
        own_percentile = _threshold_percentile(column, float(condition.value))
        for quantile in grid(own_percentile):
            perturbed_value = column.quantile(quantile)
            if perturbed_value is None:
                continue
            perturbed = tuple(
                Condition(c.feature, c.operator, round(float(perturbed_value), 8))
                if c is condition
                else c
                for c in conditions
            )
            pmask = frame.select(rule_expr(perturbed).alias("m"))["m"]
            stats = split_stats(frame, pmask, outcome, "development")
            entry: dict[str, Any] = {
                "condition": f"{condition.feature} {condition.operator} {condition.value}",
                "threshold_percentile": round(own_percentile, 4),
                "perturbation_quantile": round(quantile, 6),
                "perturbed_value": round(float(perturbed_value), 8),
                "threshold_percentile_shift": round(own_percentile - quantile, 4),
                # A refit whose perturbed threshold lands back on the candidate's own value tests
                # nothing: it re-estimates the identical rule. Recorded rather than hidden, because
                # a coarse integer column can make a small percentile step vacuous.
                "vacuous_identical_rule": bool(
                    round(float(perturbed_value), 8) == round(float(condition.value), 8)
                ),
            }
            if stats is None or not base_harm:
                entry.update(
                    {
                        "n_exposed": stats.n_exposed if stats else 0,
                        "exposure_growth": None,
                        "harm_per_booking": None,
                        "sign_agrees": False,
                        "magnitude_deviation": None,
                        "note": "no estimate produced; counted as a check that does not agree",
                    }
                )
            else:
                ratio = abs(stats.harm_per_booking / base_harm)
                entry.update(
                    {
                        "n_exposed": stats.n_exposed,
                        "exposure_growth": (
                            round(stats.n_exposed / base_exposed, 4) if base_exposed else None
                        ),
                        "harm_per_booking": round(stats.harm_per_booking, 4),
                        "sign_agrees": (stats.harm_per_booking > 0) == (base_harm > 0),
                        "magnitude_deviation": round(abs(ratio - 1.0), 6),
                    }
                )
            checks.append(entry)
    return checks


def _family_summary(checks: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate a set of robustness refits by `G12`'s own two rules.

    `passes` applies the real gate's conjunction — sign agreement at or above the floor *and* max
    magnitude deviation at or under the ceiling — to whatever subset of checks it is handed. When a
    subset is a single check family this is the gate's rule applied in isolation, which is what
    makes "which family is doing the work" answerable; the isolation is disclosed everywhere it is
    used and is never presented as the production verdict.
    """
    deviations = [
        cast(float, c["magnitude_deviation"])
        for c in checks
        if c.get("magnitude_deviation") is not None
    ]
    signs = [bool(c["sign_agrees"]) for c in checks]
    max_deviation = max(deviations, default=None)
    sign_agreement = sum(signs) / len(signs) if signs else 0.0
    return {
        "checks_run": len(checks),
        "estimates_produced": len(deviations),
        "degenerate_refits": sum(1 for c in checks if c.get("magnitude_deviation") is None),
        "vacuous_refits": sum(1 for c in checks if c.get("vacuous_identical_rule")),
        "max_magnitude_deviation": None if max_deviation is None else round(max_deviation, 6),
        "sign_agreement": round(sign_agreement, 4),
        "passes": bool(
            len(checks) > 0
            and sign_agreement >= DEFAULT_THRESHOLDS.min_robustness_sign_agreement
            and (max_deviation is None or max_deviation <= CEILING)
        ),
    }


# --------------------------------------------------------------------------------------------
# Section A — neutral synthetic sweep (truth-free; reads nothing from this repository's data)
# --------------------------------------------------------------------------------------------


def _feature_values(distribution: str, rng: random.Random, rows: int) -> list[float]:
    if distribution == "uniform":
        return [round(rng.uniform(0.0, 100.0), 4) for _ in range(rows)]
    if distribution == "lognormal":
        return [round(rng.lognormvariate(3.0, 0.9), 4) for _ in range(rows)]
    if distribution == "discrete_small":
        # A coarse integer feature: the shape a count-like column has, where a single percentile
        # step can be unrepresentable. Included so the sweep is not a property of smooth columns.
        return [float(min(9, int(rng.expovariate(1 / 2.5)))) for _ in range(rows)]
    raise ValueError(f"unknown synthetic distribution {distribution!r}")


SPIKE_WIDTH = 0.02


def _effect_multiplier(
    dgp: str, position: float, threshold_position: float, operator: str
) -> float:
    """Effect weight for a row at percentile `position`, for a rule anchored at
    `threshold_position` with the given operator.

    Every process is defined purely in percentile space *relative to the rule's own exposed side*,
    so the same process means the same thing at every swept threshold and under either operator —
    that is what makes the sweep a controlled comparison rather than a collection of different
    phenomena.
    """
    inside = position >= threshold_position if operator == "ge" else position < threshold_position
    if not inside:
        return 0.0
    distance = position - threshold_position if operator == "ge" else threshold_position - position
    span = (
        max(1.0 - threshold_position, 1e-9) if operator == "ge" else max(threshold_position, 1e-9)
    )
    if dgp == "step_stable":
        # A genuinely localised, genuinely stable threshold effect: uniform across the whole
        # exposed side. Moving the cutoff cannot make it appear or disappear.
        return 1.0
    if dgp == "spike_cutoff_dependent":
        # Genuinely cutoff-dependent: the effect exists only in a 2-percentile-point sliver just
        # inside the boundary. A robustness gate *should* flag this one.
        return 1.0 if distance < SPIKE_WIDTH else 0.0
    if dgp == "ramp":
        # Neither knife-edge nor uniform: strengthens with distance past the cutoff.
        return distance / span
    raise ValueError(f"unknown synthetic dgp {dgp!r}")


def _step_dgp_predicted_deviation(
    threshold_position: float, perturbed_position: float, operator: str
) -> float:
    """Closed-form magnitude deviation for the `step_stable` process, from percentile geometry.

    With the affected region equal to the true rule's own exposed region, a difference in means is
    pure set arithmetic: the perturbed estimate is (affected share of the perturbed exposed group)
    minus (affected share of the perturbed comparison group), against a base estimate of exactly 1.
    Nothing about the effect's stability enters — only where the two thresholds sit.
    """
    tau, q = threshold_position, perturbed_position
    if operator == "ge":
        exposed, comparison = 1.0 - q, q
        in_exposed, in_comparison = 1.0 - max(q, tau), max(0.0, q - tau)
    else:
        exposed, comparison = q, 1.0 - q
        in_exposed, in_comparison = min(q, tau), max(0.0, tau - q)
    if exposed <= 0 or comparison <= 0:
        return float("nan")
    ratio = in_exposed / exposed - in_comparison / comparison
    return abs(abs(ratio) - 1.0)


def _synthetic_frame(
    distribution: str, dgp: str, threshold_position: float, operator: str, rng: random.Random
) -> tuple[pl.DataFrame, float]:
    """Build one neutral synthetic dataset and return it with the threshold value in feature units.

    The feature is drawn first, then each row's *own* percentile in the realised sample decides
    whether the effect applies, so the affected share is exactly `1 - threshold_position` (up to
    ties) regardless of the feature's distribution.
    """
    values = _feature_values(distribution, rng, SYNTHETIC_ROWS)
    order = sorted(range(len(values)), key=lambda index: values[index])
    position = [0.0] * len(values)
    for rank, index in enumerate(order):
        position[index] = rank / len(values)
    series = pl.Series("signal_metric", values)
    threshold = float(cast(float, series.quantile(threshold_position, interpolation="nearest")))
    outcome_values: list[float] = []
    partial_values: list[float] = []
    for index, own_position in enumerate(position):
        weight = _effect_multiplier(dgp, own_position, threshold_position, operator)
        noise = rng.gauss(0.0, SYNTHETIC_NOISE_SD)
        # `partial_metric` is a decomposition component of `value_metric`: it carries the baseline
        # and the noise but not the effect channel — the neutral analogue of an outcome that is
        # structurally unable to see the mechanism a pattern acts through.
        partial_values.append(round(SYNTHETIC_BASELINE + noise, 6))
        outcome_values.append(round(SYNTHETIC_BASELINE + noise + weight * SYNTHETIC_EFFECT, 6))
        del index
    frame = pl.DataFrame(
        {
            "signal_metric": values,
            "value_metric": outcome_values,
            "partial_metric": partial_values,
        }
    )
    return frame, threshold


def _synthetic_sweep() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for distribution in ("uniform", "lognormal", "discrete_small"):
        for operator in ("ge", "lt"):
            for dgp in ("step_stable", "spike_cutoff_dependent", "ramp"):
                for threshold_position in SWEEP_PERCENTILES:
                    rng = random.Random(SYNTHETIC_SEED)
                    frame, threshold = _synthetic_frame(
                        distribution, dgp, threshold_position, operator, rng
                    )
                    condition = (
                        Condition("signal_metric", cast(Any, operator), round(threshold, 8)),
                    )
                    mask = frame.select(rule_expr(condition).alias("m"))["m"]
                    base = split_stats(frame, mask, NEUTRAL_OUTCOME, "development")
                    if base is None or not base.harm_per_booking:
                        continue
                    own_percentile = _threshold_percentile(frame["signal_metric"], threshold)
                    variants: dict[str, Any] = {}
                    for grid_name, grid in GRIDS.items():
                        checks = _perturbation_checks(
                            frame,
                            condition,
                            NEUTRAL_OUTCOME,
                            base.harm_per_booking,
                            base.n_exposed,
                            grid,
                        )
                        for check in checks:
                            check["step_dgp_predicted_deviation"] = round(
                                _step_dgp_predicted_deviation(
                                    own_percentile,
                                    cast(float, check["perturbation_quantile"]),
                                    operator,
                                ),
                                6,
                            )
                        summary = _family_summary(checks)
                        summary["checks"] = checks
                        variants[grid_name] = summary
                    rows.append(
                        {
                            "distribution": distribution,
                            "operator": operator,
                            "dgp": dgp,
                            "requested_threshold_percentile": threshold_position,
                            "realised_threshold_percentile": round(own_percentile, 4),
                            "base_n_exposed": base.n_exposed,
                            "base_harm_per_booking": round(base.harm_per_booking, 4),
                            "variants": variants,
                        }
                    )

    # The confusion table: how often does each grid flag a process whose stability is known by
    # construction? `step_stable` is the same phenomenon at every swept threshold and is stable by
    # definition — every flag on it is a false alarm. `spike_cutoff_dependent` is genuinely an
    # artefact of exactly where the cut falls — every miss on it is a missed detection.
    confusion: dict[str, Any] = {}
    for column_family, column_rows in (
        ("continuous_columns", [r for r in rows if r["distribution"] != "discrete_small"]),
        ("coarse_integer_column", [r for r in rows if r["distribution"] == "discrete_small"]),
    ):
        per_grid: dict[str, Any] = {}
        for grid_name in GRIDS:
            per_dgp: dict[str, Any] = {}
            for dgp in ("step_stable", "spike_cutoff_dependent", "ramp"):
                subset = [row for row in column_rows if row["dgp"] == dgp]
                flagged = [
                    row
                    for row in subset
                    if not cast(dict[str, Any], row["variants"][grid_name])["passes"]
                ]
                per_dgp[dgp] = {
                    "cells": len(subset),
                    "flagged": len(flagged),
                    "flagged_share": round(len(flagged) / len(subset), 4) if subset else None,
                    "flagged_threshold_percentiles": sorted(
                        {cast(float, row["realised_threshold_percentile"]) for row in flagged}
                    ),
                }
            per_grid[grid_name] = per_dgp
        confusion[column_family] = per_grid

    # The pass window, read off the sweep rather than asserted: over which realised threshold
    # percentiles does each grid clear the gate for a process that is stable by construction?
    pass_windows: dict[str, Any] = {}
    for grid_name in GRIDS:
        passing = [
            cast(float, row["realised_threshold_percentile"])
            for row in rows
            if row["dgp"] == "step_stable"
            and row["distribution"] != "discrete_small"
            and cast(dict[str, Any], row["variants"][grid_name])["passes"]
        ]
        pass_windows[grid_name] = {
            "step_stable_continuous_pass_percentile_min": min(passing) if passing else None,
            "step_stable_continuous_pass_percentile_max": max(passing) if passing else None,
            "step_stable_continuous_cells_passing": len(passing),
        }

    # Where the closed form crosses the ceiling, at a resolution the sweep itself cannot resolve.
    # Solved by scanning the same closed form the sweep is checked against, under the production
    # grid, for both operators — no simulation, no data.
    closed_form_pass: dict[str, Any] = {}
    for operator in ("ge", "lt"):
        passing_positions = [
            index / 1000.0
            for index in range(1, 1000)
            if max(
                _step_dgp_predicted_deviation(index / 1000.0, quantile, operator)
                for quantile in PERTURBATION_QUANTILES
            )
            <= CEILING
        ]
        closed_form_pass[operator] = {
            "min_threshold_percentile": min(passing_positions) if passing_positions else None,
            "max_threshold_percentile": max(passing_positions) if passing_positions else None,
        }

    # Does the deviation carry any information about the effect's stability at all? For a process
    # that is uniform across its own exposed side, the answer is closed-form: the measured
    # deviation is fixed by where the two thresholds sit, and by nothing else. Recorded as a
    # residual of the realised numbers against that prediction.
    residuals: list[dict[str, Any]] = []
    for row in rows:
        if row["dgp"] != "step_stable" or row["distribution"] == "discrete_small":
            continue
        for grid_name in GRIDS:
            for check in cast(
                list[dict[str, Any]], cast(dict[str, Any], row["variants"][grid_name])["checks"]
            ):
                deviation = check.get("magnitude_deviation")
                predicted = cast(float, check["step_dgp_predicted_deviation"])
                if deviation is None or predicted != predicted:
                    continue
                residuals.append(
                    {
                        "distribution": row["distribution"],
                        "operator": row["operator"],
                        "grid": grid_name,
                        "threshold_percentile": row["realised_threshold_percentile"],
                        "observed_deviation": deviation,
                        "predicted_deviation_from_threshold_geometry_alone": predicted,
                        "residual": round(cast(float, deviation) - predicted, 6),
                    }
                )
    residual_values = [abs(cast(float, r["residual"])) for r in residuals]

    return {
        "design": {
            "rows_per_cell": SYNTHETIC_ROWS,
            "seed": SYNTHETIC_SEED,
            "effect_size": SYNTHETIC_EFFECT,
            "noise_sd": SYNTHETIC_NOISE_SD,
            "baseline": SYNTHETIC_BASELINE,
            "threshold_percentiles_swept": list(SWEEP_PERCENTILES),
            "operators_swept": ["ge", "lt"],
            "distributions": ["uniform", "lognormal", "discrete_small"],
            "data_generating_processes": {
                "step_stable": "effect applies uniformly to every row above the cutoff",
                "spike_cutoff_dependent": (
                    "effect applies only within 2 percentile points above the cutoff"
                ),
                "ramp": "effect grows linearly with distance above the cutoff",
            },
            "ceiling": CEILING,
            "grid_constants_derived_from_production": {
                "production_quantiles": list(PERTURBATION_QUANTILES),
                "implied_anchor_quantile": IMPLIED_ANCHOR_QUANTILE,
                "implied_percentile_step": IMPLIED_PERCENTILE_STEP,
                "implied_exposure_step": round(IMPLIED_EXPOSURE_STEP, 6),
            },
        },
        "sweep": rows,
        "confusion": confusion,
        "step_stable_pass_windows": pass_windows,
        "step_stable_closed_form_pass_window_production_grid": {
            "note": (
                "Threshold percentiles at which the production grid clears the ceiling for an "
                "effect that is uniform across its own exposed side, solved from the closed form "
                "at 0.001 resolution. Simulation-free."
            ),
            "by_operator": closed_form_pass,
        },
        "threshold_geometry_identity": {
            "note": (
                "For an effect that is uniform across its own exposed side, the measured magnitude "
                "deviation is predicted by the two thresholds' percentile positions alone, with no "
                "reference to the effect's stability."
            ),
            "comparisons": len(residuals),
            "max_abs_residual": round(max(residual_values), 6) if residual_values else None,
            "mean_abs_residual": (
                round(sum(residual_values) / len(residual_values), 6) if residual_values else None
            ),
        },
    }


def _decomposition_outcome_case() -> dict[str, Any]:
    """Neutral analogue of an alternative-outcome robustness refit against a decomposition.

    `partial_metric` is `value_metric` minus one additive channel; the synthetic pattern acts only
    through that channel. This is a truth-free construction — it says nothing about any real
    outcome — and it isolates one question: what does a +/-50% magnitude-parity requirement report
    when the alternative outcome structurally excludes the channel the effect runs through?
    """
    rng = random.Random(SYNTHETIC_SEED)
    frame, threshold = _synthetic_frame("uniform", "step_stable", 0.50, "ge", rng)
    condition = (Condition("signal_metric", "ge", round(threshold, 8)),)
    mask = frame.select(rule_expr(condition).alias("m"))["m"]
    primary = split_stats(frame, mask, NEUTRAL_OUTCOME, "development")
    alternative = split_stats(frame, mask, NEUTRAL_VISIBLE_OUTCOME, "development")
    if primary is None or alternative is None or not primary.harm_per_booking:
        raise SystemExit("neutral decomposition case produced no estimate")
    ratio = abs(alternative.harm_per_booking / primary.harm_per_booking)
    return {
        "primary_harm_per_booking": round(primary.harm_per_booking, 4),
        "alternative_harm_per_booking": round(alternative.harm_per_booking, 4),
        "magnitude_deviation": round(abs(ratio - 1.0), 4),
        "ceiling": CEILING,
        "within_ceiling": bool(abs(ratio - 1.0) <= CEILING),
        "effect_stability": (
            "maximally stable by construction: the effect is uniform above the cutoff and every "
            "row's contribution is identical"
        ),
    }


# --------------------------------------------------------------------------------------------
# Sections B and C — measurement of the existing gate on the rules item 1 already opened
# --------------------------------------------------------------------------------------------


def _oracle_rules(
    blind_root: Path, run_id: str, dataset_root: Path, oracle_raw_path: Path
) -> tuple[dict[str, tuple[Condition, ...]], dict[str, Any], pl.DataFrame, dict[str, Any]]:
    """Re-derive item 7's oracle projections and assert they reproduce its committed output.

    Same custody discipline as `diagnose_validation_power.py`: the frozen candidate file's SHA-256
    is checked against its own `hashes.json`, the dataset identity is checked against the committed
    run's metrics, and every re-derived projection must equal item 7's committed rule
    condition-for-condition before any number is reported.
    """
    candidates_path = blind_root / f"{run_id}.candidates.json"
    metrics_path = blind_root / f"{run_id}.discovery_metrics.json"
    hashes_path = blind_root / f"{run_id}.hashes.json"
    for path in (candidates_path, metrics_path, hashes_path):
        if not path.exists():
            raise SystemExit(
                f"missing frozen artifact {path}; `artifacts/` is gitignored and per-checkout — "
                "point --blind-root at a checkout that holds this run's frozen outputs, or pass "
                "--synthetic-only to run Section A alone"
            )
    hashes = cast(dict[str, str], json.loads(hashes_path.read_text(encoding="utf-8")))
    digest = hashlib.sha256(candidates_path.read_bytes()).hexdigest()
    if digest != hashes.get("candidates.json"):
        raise SystemExit(
            f"candidate file SHA-256 {digest} does not match the frozen hashes.json entry "
            f"{hashes.get('candidates.json')} — refusing to explain a mutated run"
        )
    run_metrics = cast(dict[str, Any], json.loads(metrics_path.read_text(encoding="utf-8")))
    manifest = cast(
        dict[str, Any], json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    )
    if run_metrics["dataset_identity_sha256"] != manifest["dataset_identity_sha256"]:
        raise SystemExit("dataset identity drifted since the committed run; results untrustworthy")

    oracle_raw = cast(dict[str, Any], json.loads(oracle_raw_path.read_text(encoding="utf-8")))
    oracle_by_pattern = {
        str(entry["pattern_id"]): entry
        for entry in cast(list[dict[str, Any]], oracle_raw["patterns"])
    }
    config = DiscoveryConfig(
        seed=int(run_metrics["random_seed"]),
        max_feature_identity_fraction=float(run_metrics.get("max_feature_identity_fraction", 1.0)),
    )
    timing_meta = cast(dict[str, dict[str, Any]], manifest["feature_timing"])
    timing = {name: str(meta["classification"]) for name, meta in timing_meta.items()}
    excluded_dates = {"booking_date", "travel_date"}
    frame = load_analytical_frame(dataset_root)
    feature_columns = tuple(
        name
        for name in frame.columns
        if timing.get(name) == "DECISION_TIME" and name not in excluded_dates
    )
    development = frame.filter(pl.col("split_label") == "development")  # pyright: ignore[reportUnknownMemberType]
    atoms = _atoms(development, feature_columns, config)
    frame_columns = frozenset(frame.columns)
    ground_truth = cast(dict[str, Any], json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8")))
    patterns = cast(list[dict[str, Any]], ground_truth["patterns"])

    canonical: dict[str, tuple[Condition, ...]] = {}
    for pattern in patterns:
        pattern_id = str(pattern["id"])
        projection = build_projection(
            pattern_id,
            str(pattern["rule"]),
            atoms,
            feature_columns,
            frame_columns,
            timing,
            development,
            config,
        )
        if projection.over_depth or not projection.atoms:
            continue
        rendered = _render_rule(projection.atoms)
        if rendered != oracle_by_pattern[pattern_id]["canonical_representable_rule"]:
            raise SystemExit(
                f"{pattern_id}: re-derived oracle projection {rendered!r} differs from item 7's "
                "committed rule — refusing to report numbers for a different rule"
            )
        canonical[pattern_id] = tuple(
            Condition(c.feature, cast(Any, c.operator), c.value) for c in projection.atoms
        )
    ground_truth_by_pattern = {str(pattern["id"]): pattern for pattern in patterns}
    return canonical, ground_truth_by_pattern, frame, manifest


def _real_atom_sections(
    canonical: dict[str, tuple[Condition, ...]],
    ground_truth_by_pattern: dict[str, Any],
    frame: pl.DataFrame,
    manifest: dict[str, Any],
    dataset_root: Path,
    autopsy_raw_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    outcome, _version = outcome_definition_from_manifest(manifest, dataset_root)
    inputs = validation_input_from_manifest(dataset_root)
    dev_frame = frame.filter(frame["split_label"] == "development")  # pyright: ignore[reportUnknownMemberType]
    autopsy_raw = cast(dict[str, Any], json.loads(autopsy_raw_path.read_text(encoding="utf-8")))
    autopsy_by_pattern = {
        str(entry["pattern_id"]): entry
        for entry in cast(list[dict[str, Any]], autopsy_raw["patterns"])
    }

    section_b: list[dict[str, Any]] = []
    section_c: list[dict[str, Any]] = []
    for pattern_id, rule in sorted(canonical.items()):
        full_mask = frame.select(rule_expr(rule).alias("m"))["m"]
        dev_mask = full_mask.filter(frame["split_label"] == "development")
        dev = split_stats(dev_frame, dev_mask, outcome, "development")
        if dev is None or not dev.harm_per_booking:
            continue

        # ---- Fidelity: the full battery must reproduce item 1's committed decomposition ----
        checks, sign_agreement, max_deviation, checks_run = _robustness_decomposition(
            dev_frame, rule, dev_mask, outcome, dev, inputs
        )
        battery = _robustness_battery(dev_frame, rule, dev_mask, outcome, dev, inputs)
        if (
            abs(battery[0] - sign_agreement) > 1e-12
            or abs(battery[1] - max_deviation) > 1e-12
            or battery[2] != checks_run
        ):
            raise SystemExit(f"{pattern_id}: decomposition does not reproduce _robustness_battery")
        committed = cast(dict[str, Any], autopsy_by_pattern[pattern_id]["g12_robustness"])
        if (
            abs(float(cast(float, committed["max_magnitude_deviation"])) - max_deviation) > 5e-5
            or abs(float(cast(float, committed["sign_agreement"])) - sign_agreement) > 5e-5
            or int(cast(int, committed["checks_run"])) != checks_run
        ):
            raise SystemExit(
                f"{pattern_id}: G12 aggregates do not reproduce item 1's committed raw output"
            )

        # ---- Section B: the same threshold family under each grid ----
        variants: dict[str, Any] = {}
        for grid_name, grid in GRIDS.items():
            family = _perturbation_checks(
                dev_frame, rule, outcome, dev.harm_per_booking, dev.n_exposed, grid
            )
            summary = _family_summary(family)
            summary["checks"] = family
            variants[grid_name] = summary
        section_b.append(
            {
                "pattern_id": pattern_id,
                "scoreable": pattern_id not in NON_SCOREABLE_PATTERNS,
                "oracle_rule": _render_rule(cast(Any, rule)),
                "development_n_exposed": dev.n_exposed,
                "development_harm_per_booking": round(dev.harm_per_booking, 4),
                "committed_g12_max_magnitude_deviation": committed["max_magnitude_deviation"],
                "threshold_perturbation_by_grid": variants,
                "disclosure": (
                    "Measurement only. No per-pattern counterfactual G12 verdict is computed or "
                    "claimed from these numbers; the pass/fail question is settled on the neutral "
                    "synthetic sweep in Section A, per TASK-069's hard rule."
                ),
            }
        )

        # ---- Section C: which check family is doing the work ----
        by_family: dict[str, list[dict[str, Any]]] = {}
        for check in checks:
            by_family.setdefault(str(check["check"]), []).append(check)
        families = sorted(by_family)
        contribution: dict[str, Any] = {}
        for family_name in families:
            contribution[family_name] = {
                "alone": _family_summary(by_family[family_name]),
                "excluded": _family_summary(
                    [c for name, group in by_family.items() if name != family_name for c in group]
                ),
            }
        # What the alternative-outcome refit can attain at best. `hidden_ground_truth.json` records
        # each pattern's realised counterfactual effect on the primary outcome *and* on the
        # alternative one; their ratio is the deviation the check must report if it estimates both
        # perfectly. Read generically (outcome ids come from the manifest and the outcome contract,
        # not from a list written here) and used only to explain an observed failure.
        pattern_meta = cast(dict[str, Any], ground_truth_by_pattern[pattern_id])
        realised = cast(
            dict[str, Any],
            cast(dict[str, Any], pattern_meta["realized_counterfactual_effects"])["outcomes"],
        )
        alternative_id = inputs.alternative_outcome_id
        attainable: dict[str, Any] | None = None
        if alternative_id is not None and {outcome.outcome_id, alternative_id} <= set(realised):
            primary_effect = float(
                cast(float, cast(dict[str, Any], realised[outcome.outcome_id])["mean_effect"])
            )
            alternative_effect = float(
                cast(float, cast(dict[str, Any], realised[alternative_id])["mean_effect"])
            )
            if primary_effect:
                attainable_ratio = alternative_effect / primary_effect
                attainable = {
                    "primary_outcome_id": outcome.outcome_id,
                    "alternative_outcome_id": alternative_id,
                    "ground_truth_primary_mean_effect": round(primary_effect, 4),
                    "ground_truth_alternative_mean_effect": round(alternative_effect, 4),
                    "attainable_magnitude_ratio": round(attainable_ratio, 6),
                    "attainable_magnitude_deviation": round(abs(abs(attainable_ratio) - 1.0), 6),
                    "attainable_deviation_within_ceiling": bool(
                        abs(abs(attainable_ratio) - 1.0) <= CEILING
                    ),
                    "note": (
                        "The deviation a perfect estimator would report for this check, from the "
                        "benchmark's own recorded counterfactual effects on the two outcomes. It "
                        "is a property of how the pattern's harm is routed through the outcome "
                        "decomposition, not of the candidate, the sample, or the effect's "
                        "stability."
                    ),
                }
        effect = cast(dict[str, Any], pattern_meta["true_effect"]).get("configured_effect", {})
        section_c.append(
            {
                "pattern_id": pattern_id,
                "scoreable": pattern_id not in NON_SCOREABLE_PATTERNS,
                "g12_all_checks": {
                    "max_magnitude_deviation": round(max_deviation, 6),
                    "sign_agreement": round(sign_agreement, 4),
                    "checks_run": checks_run,
                    "passes": bool(
                        checks_run > 0
                        and sign_agreement >= DEFAULT_THRESHOLDS.min_robustness_sign_agreement
                        and max_deviation <= CEILING
                    ),
                },
                "by_check_family": contribution,
                "alternative_outcome_attainable_deviation": attainable,
                "configured_effect_channels": {
                    str(key): value for key, value in sorted(cast(dict[str, Any], effect).items())
                },
            }
        )
    return {"patterns": section_b}, {"patterns": section_c}


# --------------------------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-id", type=str, default=DEFAULT_RUN_ID)
    parser.add_argument("--blind-root", type=Path, default=BLIND_ROOT)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--oracle-raw", type=Path, default=DEFAULT_ORACLE_RAW)
    parser.add_argument("--autopsy-raw", type=Path, default=DEFAULT_AUTOPSY_RAW)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    parser.add_argument(
        "--synthetic-only",
        action="store_true",
        help="run Section A alone (requires no frozen artifacts and reads no benchmark data)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    print("TASK-069 item 2 — G12 perturbation-form diagnostic (POST-HOC; changes nothing)")
    print(
        f"  production grid {PERTURBATION_QUANTILES} = anchor q{IMPLIED_ANCHOR_QUANTILE:.2f} "
        f"+/- {IMPLIED_PERCENTILE_STEP:.2f} percentile points "
        f"(= +/- {IMPLIED_EXPOSURE_STEP:.0%} exposure at that anchor for a `lt` atom)"
    )
    print("  Section A: neutral synthetic sweep (no repository data) ...")
    section_a = _synthetic_sweep()
    decomposition_case = _decomposition_outcome_case()

    payload: dict[str, Any] = {
        "diagnostic": "POST_HOC_DIAGNOSTIC",
        "task": "TASK-069 reformulation item 2 (is G12 measuring the right thing?)",
        "disclosure": (
            "Not an official TASK-015/TASK-019/TASK-028 run. Produces no official metric, changes "
            "no frozen artifact, proposes no gate/threshold/estimator/perturbation rule, and "
            "touches no production module. The non-production perturbation grids are diagnostic "
            "counterfactuals parameterised entirely from the production constant itself."
        ),
        "validation_contract_version": DEFAULT_THRESHOLDS.version,
        "robustness_thresholds": {
            "max_robustness_magnitude_deviation": CEILING,
            "min_robustness_sign_agreement": DEFAULT_THRESHOLDS.min_robustness_sign_agreement,
        },
        "section_a_neutral_synthetic": section_a,
        "section_a4_neutral_decomposition_outcome": decomposition_case,
    }

    if not cast(bool, args.synthetic_only):
        print("  Sections B/C: real oracle atoms (fidelity-checked against item 1) ...")
        canonical, ground_truth_by_pattern, frame, manifest = _oracle_rules(
            cast(Path, args.blind_root),
            cast(str, args.run_id),
            cast(Path, args.dataset_root),
            cast(Path, args.oracle_raw),
        )
        section_b, section_c = _real_atom_sections(
            canonical,
            ground_truth_by_pattern,
            frame,
            manifest,
            cast(Path, args.dataset_root),
            cast(Path, args.autopsy_raw),
        )
        payload["section_b_real_atom_measurement"] = section_b
        payload["section_c_check_family_contribution"] = section_c
        print("  FIDELITY OK: G12 aggregates reproduce item 1's committed raw output")

    output = cast(Path, args.raw_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nRaw output written to {output}")

    print("\n=== Section A: flag rate by data-generating process (stability known a priori) ===")
    for column_family, per_grid in cast(dict[str, Any], section_a["confusion"]).items():
        print(f"  {column_family}:")
        for grid_name, per_dgp in cast(dict[str, Any], per_grid).items():
            print(f"    {grid_name}:")
            for dgp, stats in cast(dict[str, Any], per_dgp).items():
                print(
                    f"      {dgp:<26} flagged {stats['flagged']:>2}/{stats['cells']:<2} "
                    f"({stats['flagged_share']:.0%})"
                )
    print("\n  step_stable pass window over realised threshold percentile (continuous columns):")
    for grid_name, window in cast(dict[str, Any], section_a["step_stable_pass_windows"]).items():
        print(
            f"    {grid_name}: "
            f"[{window['step_stable_continuous_pass_percentile_min']}, "
            f"{window['step_stable_continuous_pass_percentile_max']}] "
            f"({window['step_stable_continuous_cells_passing']} cells pass)"
        )
    closed_form = cast(
        dict[str, Any],
        cast(dict[str, Any], section_a["step_stable_closed_form_pass_window_production_grid"])[
            "by_operator"
        ],
    )
    print("\n  closed-form pass window for the production grid on a maximally stable effect:")
    for operator, window in closed_form.items():
        print(
            f"    {operator}: [{window['min_threshold_percentile']}, "
            f"{window['max_threshold_percentile']}]"
        )
    identity = cast(dict[str, Any], section_a["threshold_geometry_identity"])
    print(
        f"\n  threshold-geometry identity on step_stable: max |residual| "
        f"{identity['max_abs_residual']}, mean |residual| {identity['mean_abs_residual']} "
        f"over {identity['comparisons']} refits"
    )
    print(
        f"\n  neutral decomposition-outcome case: deviation "
        f"{decomposition_case['magnitude_deviation']:.0%} vs ceiling {CEILING:.0%} on a "
        f"maximally stable effect"
    )

    if "section_b_real_atom_measurement" in payload:
        print("\n=== Section B: threshold-perturbation family, per grid (measurement only) ===")
        for entry in cast(
            list[dict[str, Any]],
            cast(dict[str, Any], payload["section_b_real_atom_measurement"])["patterns"],
        ):
            variants = cast(dict[str, Any], entry["threshold_perturbation_by_grid"])
            parts: list[str] = []
            for name, variant in variants.items():
                summary = cast(dict[str, Any], variant)
                deviation = cast(float | None, summary["max_magnitude_deviation"])
                label = f"{name.split('_')[-2]}_{name.split('_')[-1]}"
                shown = "n/a" if deviation is None else f"{deviation:.0%}"
                degenerate = cast(int, summary["degenerate_refits"])
                suffix = f" (+{degenerate} degenerate)" if degenerate else ""
                parts.append(f"{label}={shown}{suffix}")
            rendered = " ".join(parts)
            print(f"  {entry['pattern_id']}: {rendered}")

        print("\n=== Section C: alternative-outcome check vs. what it could attain at best ===")
        for entry in cast(
            list[dict[str, Any]],
            cast(dict[str, Any], payload["section_c_check_family_contribution"])["patterns"],
        ):
            attainable = cast(
                dict[str, Any] | None, entry["alternative_outcome_attainable_deviation"]
            )
            observed = cast(dict[str, Any], entry["by_check_family"]).get("alternative_outcome")
            if attainable is None or observed is None:
                continue
            measured = cast(dict[str, Any], cast(dict[str, Any], observed)["alone"])[
                "max_magnitude_deviation"
            ]
            print(
                f"  {entry['pattern_id']}: measured {cast(float, measured):.1%} vs. attainable "
                f"{cast(float, attainable['attainable_magnitude_deviation']):.1%} "
                f"(ceiling {CEILING:.0%})"
            )


if __name__ == "__main__":
    main()
