"""Apply the validation contract to frozen discovery candidates (TASK-019).

This module answers exactly one question per candidate: does the raw association discovery found
survive uncertainty, confounding, temporal/segment stability, robustness, and multiple-comparison
scrutiny — and if so, at what evidence level? It never opens hidden ground truth, never chooses a
candidate, and never runs discovery; it grades what `TASK-015` already froze.

**Confounding-adjustment discipline.** The adjustment set (`manager`, `supplier`) and the
heterogeneity-check covariate (`customer_segment`) are fixed *generically*, from ordinary
booking-domain reasoning (assignment covariates a real analyst would control for before ever
seeing a result), not from any knowledge of which mechanisms the benchmark generator injected.
This module does not import, read, or reference `synthetic_benchmark.py` or
`hidden_ground_truth.json`, and must not be edited to do so.

Flow: `validate_family` computes gates G00-G04 and G06-G15 per candidate (everything that does not
require knowing the other candidates), collects one G05 p-value per candidate (the normal
approximation on the cluster-bootstrap standard error — see `grading.normal_approx_two_sided_p`
and ADR-014/ADR-015; the empirical count-based bootstrap p-value is retained only as a diagnostic),
then applies Benjamini-Hochberg across the *entire evaluated search* (family_size from the
discovery run manifest, not the 15 reported candidates) to fill in G05, and finally assembles each
`ValidationReport`.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import polars as pl
from policy_schemas.domain import EvidenceLevel

from policy_analytics.outcomes import (
    OUTCOME_BY_ID,
    OutcomeDefinition,
    harm_score,
    raw_difference,
    summarize_group,
)
from policy_analytics.validation.contract import (
    DEFAULT_THRESHOLDS,
    GateId,
    GateOutcome,
    GateResult,
    IdentificationDesign,
    PolicyReadiness,
)
from policy_analytics.validation.economic_impact import (
    EconomicImpactResult,
    build_economic_impact_result,
)
from policy_analytics.validation.grading import (
    assign_policy_readiness,
    benjamini_hochberg_adjusted,
    bootstrap_standard_error,
    bootstrap_two_sided_p,
    classify_evidence_level,
    normal_approx_two_sided_p,
)
from policy_analytics.validation.report import EffectEstimate, ValidationReport

Z_95 = 1.959964  # two-sided 95% normal quantile
Z_POWER_80 = 0.841621  # one-sided 80% normal quantile (matches DEFAULT_THRESHOLDS.power_target)

CONFOUNDER_COLUMNS: tuple[str, ...] = ("manager", "supplier")
HETEROGENEITY_COLUMN = "customer_segment"
SPLITS: tuple[str, ...] = ("development", "validation", "future_holdout")
DEV_BOOTSTRAP_REPS = 2000
DIAGNOSTIC_BOOTSTRAP_REPS = 1000
BOOTSTRAP_SEED = 20260813
PERTURBATION_QUANTILES: tuple[float, float] = (0.15, 0.25)  # one bin below / above each threshold
MIN_STRATUM_CELL = 5


class Verdict:
    PASS = "PASS"
    DOWNGRADE = "DOWNGRADE"
    REJECT = "REJECT"


Operator = Literal["eq", "ge", "lt"]


@dataclass(frozen=True, slots=True)
class Condition:
    feature: str
    operator: Operator
    value: Any


def condition_expr(condition: Condition) -> pl.Expr:
    column = pl.col(condition.feature)
    if condition.operator == "eq":
        return column == condition.value
    if condition.operator == "ge":
        return column >= condition.value
    return column < condition.value


def rule_expr(conditions: Sequence[Condition]) -> pl.Expr:
    expression = condition_expr(conditions[0])
    for condition in conditions[1:]:
        expression &= condition_expr(condition)
    return expression


DECISION_TIME_FEATURES: frozenset[str] = frozenset(
    {
        "booking_date",
        "travel_date",
        "destination",
        "supplier",
        "product_category",
        "customer_price_eur",
        "quoted_cost_eur",
        "discount_rate",
        "manager",
        "acquisition_channel",
        "customer_segment",
        "customer_type",
        "party_size",
        "trip_duration_days",
        "booking_lead_days",
        "payment_method",
        "installments",
        "manual_exception",
    }
)


def load_analytical_frame(dataset_root: Path) -> pl.DataFrame:
    """Join the four row-aligned partitions into one frame with a derived booking_month."""
    features = pl.read_csv(dataset_root / "features.csv")
    outcomes = pl.read_csv(dataset_root / "outcomes.csv")
    identifiers = pl.read_csv(dataset_root / "identifiers.csv")
    metadata = pl.read_csv(dataset_root / "metadata.csv")
    for name, frame in (
        ("outcomes", outcomes),
        ("identifiers", identifiers),
        ("metadata", metadata),
    ):
        if frame.height != features.height:
            raise ValueError(f"partition {name} is not row-aligned with features.csv")
    frame = pl.concat([features, outcomes, identifiers, metadata], how="horizontal")
    return frame.with_columns(
        pl.col("booking_date").str.slice(5, 2).cast(pl.Int64).alias("booking_month")
    )


@dataclass(frozen=True, slots=True)
class ClusterCell:
    exposed_sum: float = 0.0
    exposed_n: int = 0
    comparison_sum: float = 0.0
    comparison_n: int = 0


def cluster_cells(
    frame: pl.DataFrame, mask: pl.Series, outcome_column: str, cluster_column: str = "customer_id"
) -> dict[str, ClusterCell]:
    working = frame.select([cluster_column, outcome_column]).with_columns(mask.alias("_exposed"))
    grouped = working.group_by([cluster_column, "_exposed"]).agg(
        pl.col(outcome_column).sum().alias("_sum"), pl.col(outcome_column).count().alias("_n")
    )
    cells: dict[str, ClusterCell] = {}
    for row in grouped.iter_rows(named=True):
        cluster = str(row[cluster_column])
        cell = cells.get(cluster, ClusterCell())
        if row["_exposed"]:
            cell = ClusterCell(
                cell.exposed_sum + row["_sum"],
                cell.exposed_n + row["_n"],
                cell.comparison_sum,
                cell.comparison_n,
            )
        else:
            cell = ClusterCell(
                cell.exposed_sum,
                cell.exposed_n,
                cell.comparison_sum + row["_sum"],
                cell.comparison_n + row["_n"],
            )
        cells[cluster] = cell
    return cells


def cluster_bootstrap_replicates(
    cells: dict[str, ClusterCell], reps: int, rng: random.Random
) -> list[float]:
    """Bootstrap the exposed-minus-comparison mean while resampling clusters."""
    population = list(cells.values())
    replicates: list[float] = []
    for _ in range(reps):
        sample = rng.choices(population, k=len(population))
        exposed_sum = sum(cell.exposed_sum for cell in sample)
        exposed_n = sum(cell.exposed_n for cell in sample)
        comparison_sum = sum(cell.comparison_sum for cell in sample)
        comparison_n = sum(cell.comparison_n for cell in sample)
        if exposed_n == 0 or comparison_n == 0:
            continue
        replicates.append(exposed_sum / exposed_n - comparison_sum / comparison_n)
    return replicates


def percentile_ci(values: Sequence[float], confidence_level: float) -> tuple[float, float]:
    ordered = sorted(values)
    if not ordered:
        return (0.0, 0.0)
    alpha = 1.0 - confidence_level
    low_index = max(0, int(len(ordered) * (alpha / 2)))
    high_index = min(len(ordered) - 1, int(len(ordered) * (1 - alpha / 2)))
    return ordered[low_index], ordered[high_index]


def minimum_detectable_effect(exposed_n: int, comparison_n: int, pooled_sd: float) -> float:
    if exposed_n <= 0 or comparison_n <= 0:
        return math.inf
    se = pooled_sd * math.sqrt(1.0 / exposed_n + 1.0 / comparison_n)
    return (Z_95 + Z_POWER_80) * se


def e_value(harm_per_booking: float, pooled_sd: float) -> float:
    """VanderWeele & Ding (2017) E-value approximation for a continuous outcome.

    Standardizes the effect (Cohen's d), converts it to an approximate risk ratio via
    ``RR = exp(0.91 * d)``, and returns the usual E-value transform of that ratio.
    """
    if pooled_sd <= 0:
        return math.inf
    d = abs(harm_per_booking) / pooled_sd
    risk_ratio = math.exp(0.91 * d)
    if risk_ratio < 1.0:
        risk_ratio = 1.0 / risk_ratio
    return risk_ratio + math.sqrt(risk_ratio * (risk_ratio - 1.0))


@dataclass(frozen=True, slots=True)
class SplitStats:
    split: str
    n_population: int
    n_exposed: int
    n_comparison: int
    exposed_mean: float
    comparison_mean: float
    raw_difference: float
    harm_per_booking: float
    pooled_sd: float


def split_stats(
    frame: pl.DataFrame, mask: pl.Series, outcome: OutcomeDefinition, split: str
) -> SplitStats | None:
    exposed = frame.filter(mask)  # pyright: ignore[reportUnknownMemberType]
    comparison = frame.filter(~mask)  # pyright: ignore[reportUnknownMemberType]
    if exposed.height == 0 or comparison.height == 0:
        return None
    exposed_summary = summarize_group(exposed[outcome.column].to_list(), outcome)
    comparison_summary = summarize_group(comparison[outcome.column].to_list(), outcome)
    if exposed_summary.mean is None or comparison_summary.mean is None:
        return None
    diff = raw_difference(exposed_summary, comparison_summary)
    exposed_var = exposed_summary.variance or 0.0
    comparison_var = comparison_summary.variance or 0.0
    pooled_n = exposed_summary.n_present + comparison_summary.n_present
    pooled_sd = (
        math.sqrt(
            (
                exposed_var * exposed_summary.n_present
                + comparison_var * comparison_summary.n_present
            )
            / pooled_n
        )
        if pooled_n
        else 0.0
    )
    return SplitStats(
        split=split,
        n_population=exposed.height + comparison.height,
        n_exposed=exposed_summary.n_present,
        n_comparison=comparison_summary.n_present,
        exposed_mean=exposed_summary.mean,
        comparison_mean=comparison_summary.mean,
        raw_difference=diff,
        harm_per_booking=harm_score(diff, outcome),
        pooled_sd=pooled_sd,
    )


def _stratified_two_way_adjustment(
    frame: pl.DataFrame, mask: pl.Series, outcome: OutcomeDefinition, columns: tuple[str, ...]
) -> tuple[float, float]:
    """Exposure-weighted stratified effect over `columns`. Returns (adjusted_diff, coverage)."""
    if not columns:
        summary_e = summarize_group(frame.filter(mask)[outcome.column].to_list(), outcome)  # pyright: ignore[reportUnknownMemberType]
        summary_c = summarize_group(frame.filter(~mask)[outcome.column].to_list(), outcome)  # pyright: ignore[reportUnknownMemberType]
        if summary_e.mean is None or summary_c.mean is None:
            return 0.0, 0.0
        return raw_difference(summary_e, summary_c), 1.0

    working = frame.select([*columns, outcome.column]).with_columns(mask.alias("_exposed"))
    grouped = working.group_by([*columns, "_exposed"]).agg(
        pl.col(outcome.column).sum().alias("_sum"), pl.col(outcome.column).count().alias("_n")
    )
    cells: dict[tuple[Any, ...], dict[str, float]] = {}
    for row in grouped.iter_rows(named=True):
        key = tuple(row[c] for c in columns)
        cell = cells.setdefault(key, {"es": 0.0, "en": 0, "cs": 0.0, "cn": 0})
        if row["_exposed"]:
            cell["es"] += row["_sum"]
            cell["en"] += row["_n"]
        else:
            cell["cs"] += row["_sum"]
            cell["cn"] += row["_n"]
    usable = [
        c for c in cells.values() if c["en"] >= MIN_STRATUM_CELL and c["cn"] >= MIN_STRATUM_CELL
    ]
    total_exposed_all = sum(c["en"] for c in cells.values())
    total_exposed_usable = sum(c["en"] for c in usable)
    if not usable or total_exposed_usable == 0:
        return 0.0, 0.0
    adjusted_diff = (
        sum((c["es"] / c["en"] - c["cs"] / c["cn"]) * c["en"] for c in usable)
        / total_exposed_usable
    )
    coverage = total_exposed_usable / total_exposed_all if total_exposed_all else 0.0
    return adjusted_diff, coverage


def _gate(gate_id: GateId, satisfied: bool, detail: str, warn: bool = False) -> GateResult:
    outcome = GateOutcome.FAIL
    if satisfied:
        outcome = GateOutcome.WARN if warn else GateOutcome.PASS
    return GateResult(gate_id=gate_id, outcome=outcome, detail=detail)


@dataclass(frozen=True, slots=True)
class CandidateInterim:
    """Everything computed for one candidate before the family-wide BH pass fills in G05."""

    candidate_id: str
    conditions: tuple[Condition, ...]
    condition_features: frozenset[str]
    adjustment_set: tuple[str, ...]
    split_results: dict[str, SplitStats]
    dev_effect: EffectEstimate
    adjusted_effect: EffectEstimate
    p_value: float
    gates_except_multiplicity: dict[GateId, GateResult]
    diagnostics: dict[str, Any]
    economic_impact: EconomicImpactResult


def _validate_one(
    frame: pl.DataFrame, candidate: dict[str, Any], outcome: OutcomeDefinition, rng: random.Random
) -> CandidateInterim | None:
    candidate_id = candidate["candidate_id"]
    conditions = tuple(
        Condition(c["feature"], c["operator"], c["value"]) for c in candidate["conditions"]
    )
    condition_features = frozenset(c.feature for c in conditions)
    full_mask = frame.select(rule_expr(conditions).alias("m"))["m"]

    split_results: dict[str, SplitStats] = {}
    for split in SPLITS:
        split_frame_mask = frame["split_label"] == split
        s_frame = frame.filter(split_frame_mask)  # pyright: ignore[reportUnknownMemberType]
        s_mask = full_mask.filter(split_frame_mask)
        stats = split_stats(s_frame, s_mask, outcome, split)
        if stats is not None:
            split_results[split] = stats

    dev = split_results.get("development")
    if dev is None:
        return None
    dev_frame = frame.filter(frame["split_label"] == "development")  # pyright: ignore[reportUnknownMemberType]
    dev_mask = full_mask.filter(frame["split_label"] == "development")
    diagnostics: dict[str, Any] = {}
    gates: dict[GateId, GateResult] = {}

    gates[GateId.LINEAGE] = _gate(
        GateId.LINEAGE, True, "Candidate is PERSISTED with a resolvable dataset/outcome reference."
    )

    non_decision_time = condition_features - DECISION_TIME_FEATURES
    gates[GateId.TARGET_LEAKAGE] = _gate(
        GateId.TARGET_LEAKAGE,
        not non_decision_time,
        "All condition features are DECISION_TIME."
        if not non_decision_time
        else f"Non-decision-time features: {sorted(non_decision_time)}",
    )

    adjustment_set = tuple(c for c in CONFOUNDER_COLUMNS if c not in condition_features)
    gates[GateId.POST_TREATMENT] = _gate(
        GateId.POST_TREATMENT,
        True,
        f"Adjustment set {adjustment_set} is decision-time and excludes condition features.",
    )

    dev_clusters = cluster_cells(dev_frame, dev_mask, outcome.column)
    n_clusters_touched = len(dev_clusters)
    mde = minimum_detectable_effect(dev.n_exposed, dev.n_comparison, dev.pooled_sd)
    diagnostics["minimum_detectable_effect_eur"] = mde
    sample_ok = (
        dev.n_exposed >= DEFAULT_THRESHOLDS.min_exposed_records
        and n_clusters_touched >= DEFAULT_THRESHOLDS.min_clusters
        and mde < abs(dev.harm_per_booking)
    )
    gates[GateId.SAMPLE] = _gate(
        GateId.SAMPLE,
        sample_ok,
        f"n_exposed={dev.n_exposed}, clusters={n_clusters_touched}, MDE80={mde:.1f} EUR vs "
        f"observed harm={dev.harm_per_booking:.1f} EUR.",
    )

    dev_reps_raw = cluster_bootstrap_replicates(dev_clusters, DEV_BOOTSTRAP_REPS, rng)
    dev_harm_reps = [d * outcome.harm_multiplier for d in dev_reps_raw]
    ci_low, ci_high = percentile_ci(dev_harm_reps, DEFAULT_THRESHOLDS.confidence_level)
    ci_low, ci_high = min(ci_low, ci_high), max(ci_low, ci_high)
    # The percentile interval is a property of the bootstrap distribution and is not guaranteed by
    # construction to bracket the point estimate computed on the unresampled data; widen it to
    # contain the point estimate rather than fail an internal consistency check over a rounding-
    # scale gap. This never *narrows* the reported interval.
    ci_low, ci_high = min(ci_low, dev.harm_per_booking), max(ci_high, dev.harm_per_booking)
    dev_effect = EffectEstimate(
        dev.harm_per_booking,
        ci_low,
        ci_high,
        DEFAULT_THRESHOLDS.confidence_level,
        "cluster_bootstrap_customer_id",
        outcome.unit,
    )
    gates[GateId.UNCERTAINTY] = _gate(
        GateId.UNCERTAINTY, dev_effect.excludes_zero, f"95% CI [{ci_low:.1f}, {ci_high:.1f}] EUR."
    )
    # G05's binding p-value (CONTRACT_VERSION >= 1.1.0, ADR-014/ADR-015): a Wald-type p-value from
    # the normal approximation to the cluster-bootstrap sampling distribution, not an empirical
    # tail count. The empirical count-based p-value is still computed and kept as a diagnostic —
    # it is an exact, assumption-free figure at whatever resolution the bootstrap provides, useful
    # for sanity-checking, but its resolution floor of 1/(B+1) makes it structurally unusable as
    # the source for BH correction once family_size is in the low thousands (see grading.py).
    bootstrap_se = bootstrap_standard_error(dev_reps_raw)
    p_value = normal_approx_two_sided_p(dev.raw_difference, bootstrap_se)
    diagnostics["development_bootstrap_reps"] = len(dev_reps_raw)
    diagnostics["bootstrap_standard_error_eur"] = bootstrap_se
    diagnostics["p_value_normal_approx_bootstrap_se"] = p_value
    diagnostics["p_value_empirical_bootstrap_floor_limited"] = bootstrap_two_sided_p(dev_reps_raw)

    adjusted_diff, coverage = _stratified_two_way_adjustment(
        dev_frame, dev_mask, outcome, adjustment_set
    )
    adjusted_harm = adjusted_diff * outcome.harm_multiplier
    attenuation = 1.0 - (adjusted_harm / dev.harm_per_booking if dev.harm_per_booking else 1.0)
    ev = e_value(adjusted_harm, dev.pooled_sd)
    diagnostics["adjusted_harm_per_booking"] = adjusted_harm
    diagnostics["confounder_stratum_coverage"] = coverage
    diagnostics["e_value"] = ev
    confounding_ok = (
        coverage >= 0.5
        and (adjusted_harm > 0) == (dev.harm_per_booking > 0)
        and attenuation <= DEFAULT_THRESHOLDS.max_adjusted_attenuation
        and ev >= DEFAULT_THRESHOLDS.min_e_value
    )
    gates[GateId.CONFOUNDING] = _gate(
        GateId.CONFOUNDING,
        confounding_ok,
        f"Adjusted for {adjustment_set}: harm {dev.harm_per_booking:.1f} -> "
        f"{adjusted_harm:.1f} EUR "
        f"(attenuation {attenuation:.2f}, coverage {coverage:.2f}, E-value {ev:.2f}, "
        f"floor {DEFAULT_THRESHOLDS.min_e_value}).",
    )
    shift = adjusted_harm - dev.harm_per_booking
    adjusted_effect = EffectEstimate(
        adjusted_harm,
        dev_effect.ci_low + shift,
        dev_effect.ci_high + shift,
        DEFAULT_THRESHOLDS.confidence_level,
        "stratified_manager_supplier",
        outcome.unit,
    )

    exposed_missing = dev_frame.filter(dev_mask)[outcome.column].null_count()  # pyright: ignore[reportUnknownMemberType]
    comparison_missing = dev_frame.filter(~dev_mask)[outcome.column].null_count()  # pyright: ignore[reportUnknownMemberType]
    gates[GateId.SELECTION_COLLIDER] = _gate(
        GateId.SELECTION_COLLIDER,
        exposed_missing == 0 and comparison_missing == 0,
        f"Primary-outcome missingness: exposed={exposed_missing}, comparison={comparison_missing}.",
    )
    gates[GateId.SURVIVORSHIP] = _gate(
        GateId.SURVIVORSHIP, True, "Full eligible cohort; no post-decision filter applied."
    )

    seg_frame_grouped = dev_frame.select([HETEROGENEITY_COLUMN, outcome.column]).with_columns(
        dev_mask.alias("_exposed")
    )
    seg_grouped = seg_frame_grouped.group_by([HETEROGENEITY_COLUMN, "_exposed"]).agg(
        pl.col(outcome.column).sum().alias("_sum"), pl.col(outcome.column).count().alias("_n")
    )
    seg_cells: dict[str, dict[str, float]] = {}
    for row in seg_grouped.iter_rows(named=True):
        cell = seg_cells.setdefault(
            row[HETEROGENEITY_COLUMN], {"es": 0.0, "en": 0, "cs": 0.0, "cn": 0}
        )
        if row["_exposed"]:
            cell["es"] += row["_sum"]
            cell["en"] += row["_n"]
        else:
            cell["cs"] += row["_sum"]
            cell["cn"] += row["_n"]
    reversed_exposure = sum(
        cell["en"]
        for cell in seg_cells.values()
        if cell["en"]
        and cell["cn"]
        and ((cell["es"] / cell["en"] - cell["cs"] / cell["cn"]) * outcome.harm_multiplier > 0)
        != (dev.harm_per_booking > 0)
    )
    reversal_share = reversed_exposure / dev.n_exposed if dev.n_exposed else 0.0
    diagnostics["segment_reversal_exposure_share"] = reversal_share
    gates[GateId.SIMPSON] = _gate(
        GateId.SIMPSON,
        reversal_share < DEFAULT_THRESHOLDS.simpson_reversal_exposure_share,
        f"Sign reverses in {HETEROGENEITY_COLUMN} strata covering {reversal_share:.1%} of exposure "
        f"(threshold {DEFAULT_THRESHOLDS.simpson_reversal_exposure_share:.0%}).",
    )

    signs = [s.harm_per_booking > 0 for s in split_results.values()]
    same_sign = len(split_results) == len(SPLITS) and (all(signs) or not any(signs))
    holdout = split_results.get("future_holdout")
    retention = (
        abs(holdout.harm_per_booking / dev.harm_per_booking)
        if holdout and dev.harm_per_booking
        else 0.0
    )
    diagnostics["holdout_retention"] = retention
    diagnostics["splits_present"] = list(split_results)
    temporal_ok = same_sign and retention >= DEFAULT_THRESHOLDS.min_holdout_effect_retention
    gates[GateId.TEMPORAL_STABILITY] = _gate(
        GateId.TEMPORAL_STABILITY,
        temporal_ok,
        f"Same sign across {list(split_results)}: {same_sign}; holdout retains {retention:.0%} of "
        f"development magnitude (floor {DEFAULT_THRESHOLDS.min_holdout_effect_retention:.0%}).",
    )

    month_cohort = dev_frame.group_by("booking_month").agg(pl.len().alias("n"))
    month_exposed = dev_frame.filter(dev_mask).group_by("booking_month").agg(pl.len().alias("n"))  # pyright: ignore[reportUnknownMemberType]
    cohort_by_month = dict(
        zip(month_cohort["booking_month"].to_list(), month_cohort["n"].to_list(), strict=True)
    )
    exposed_by_month = dict(
        zip(month_exposed["booking_month"].to_list(), month_exposed["n"].to_list(), strict=True)
    )
    total_cohort_n, total_exposed_n = sum(cohort_by_month.values()), sum(exposed_by_month.values())
    concentration = (
        max(
            (exposed_by_month.get(m, 0) / total_exposed_n) / (cohort_by_month[m] / total_cohort_n)
            for m in cohort_by_month
        )
        if total_exposed_n and total_cohort_n
        else 1.0
    )
    diagnostics["seasonal_concentration_index"] = concentration
    seasonal_ok = concentration <= DEFAULT_THRESHOLDS.seasonal_concentration_index
    gates[GateId.SEASONALITY] = _gate(
        GateId.SEASONALITY,
        seasonal_ok,
        f"Max monthly exposure/cohort concentration ratio {concentration:.2f} "
        f"(threshold {DEFAULT_THRESHOLDS.seasonal_concentration_index}).",
    )

    sign_agree, magnitude_dev_max, checks_run = _robustness_battery(
        dev_frame, conditions, dev_mask, outcome, dev
    )
    diagnostics["robustness_sign_agreement"] = sign_agree
    diagnostics["robustness_max_magnitude_deviation"] = magnitude_dev_max
    diagnostics["robustness_checks_run"] = checks_run
    robustness_ok = (
        checks_run > 0
        and sign_agree >= DEFAULT_THRESHOLDS.min_robustness_sign_agreement
        and magnitude_dev_max <= DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation
    )
    gates[GateId.ROBUSTNESS] = _gate(
        GateId.ROBUSTNESS,
        robustness_ok,
        f"Sign agreement {sign_agree:.0%} over {checks_run} perturbations "
        f"(floor {DEFAULT_THRESHOLDS.min_robustness_sign_agreement:.0%}); max magnitude deviation "
        f"{magnitude_dev_max:.0%} "
        f"(ceiling {DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation:.0%}).",
    )

    gates[GateId.IDENTIFICATION] = _gate(
        GateId.IDENTIFICATION, False, "Observational data; no quasi-experimental design exists."
    )
    gates[GateId.RANDOMIZATION] = _gate(
        GateId.RANDOMIZATION,
        False,
        "No prospective randomized assignment; retrospective data only.",
    )

    combined_mask = full_mask
    # TASK-023 / economic_impact.py: the combined (development + validation + future_holdout)
    # cohort, not the development-only split evidence grading uses above. `combined_stats` is the
    # real, unresampled point estimate; the bootstrap below supplies its interval only.
    combined_stats = split_stats(frame, combined_mask, outcome, "combined")
    combined_clusters = cluster_cells(frame, combined_mask, outcome.column)
    combined_reps = cluster_bootstrap_replicates(combined_clusters, DIAGNOSTIC_BOOTSTRAP_REPS, rng)
    exposed_total = combined_stats.n_exposed if combined_stats else 0
    per_record_value = combined_stats.harm_per_booking if combined_stats else 0.0
    per_record_reps = [d * outcome.harm_multiplier for d in combined_reps]
    per_low, per_high = percentile_ci(per_record_reps, DEFAULT_THRESHOLDS.confidence_level)
    exposure_reps = [d * outcome.harm_multiplier * exposed_total for d in combined_reps]
    exp_low, exp_high = percentile_ci(exposure_reps, DEFAULT_THRESHOLDS.confidence_level)
    historical_value = per_record_value * exposed_total
    total_outcome_abs = frame[outcome.column].abs().sum()
    outcome_share = abs(historical_value) / total_outcome_abs if total_outcome_abs else 0.0
    diagnostics["historical_exposure_ci_eur"] = [min(exp_low, exp_high), max(exp_low, exp_high)]
    diagnostics["historical_exposure_outcome_share"] = outcome_share
    material = min(exp_low, exp_high) > 0 and (
        min(exp_low, exp_high) >= DEFAULT_THRESHOLDS.min_material_annual_impact
        or outcome_share >= DEFAULT_THRESHOLDS.min_material_outcome_share
    )
    gates[GateId.ECONOMIC_MATERIALITY] = _gate(
        GateId.ECONOMIC_MATERIALITY,
        material,
        f"Combined-window exposure 95% CI [{min(exp_low, exp_high):.0f}, "
        f"{max(exp_low, exp_high):.0f}] "
        f"EUR, outcome share {outcome_share:.3%}.",
    )
    economic_impact = build_economic_impact_result(
        outcome=outcome,
        affected_records=exposed_total,
        per_record_value=per_record_value,
        per_record_ci_low=per_low,
        per_record_ci_high=per_high,
        confidence_level=DEFAULT_THRESHOLDS.confidence_level,
        historical_value=historical_value,
        historical_ci_low=exp_low,
        historical_ci_high=exp_high,
        materiality_pass=material,
    )

    return CandidateInterim(
        candidate_id=candidate_id,
        conditions=conditions,
        condition_features=condition_features,
        adjustment_set=adjustment_set,
        split_results=split_results,
        dev_effect=dev_effect,
        adjusted_effect=adjusted_effect,
        p_value=p_value,
        economic_impact=economic_impact,
        gates_except_multiplicity=gates,
        diagnostics=diagnostics,
    )


def _robustness_battery(
    dev_frame: pl.DataFrame,
    conditions: tuple[Condition, ...],
    dev_mask: pl.Series,
    outcome: OutcomeDefinition,
    dev: SplitStats,
) -> tuple[float, float, int]:
    sign_agree = 0
    checks_run = 0
    magnitude_ratios: list[float] = []

    def _record(stats: SplitStats | None) -> None:
        nonlocal sign_agree, checks_run
        checks_run += 1
        if stats is None or not dev.harm_per_booking:
            return
        if (stats.harm_per_booking > 0) == (dev.harm_per_booking > 0):
            sign_agree += 1
        magnitude_ratios.append(abs(stats.harm_per_booking / dev.harm_per_booking))

    for manager in dev_frame["manager"].unique().to_list():
        subset = dev_frame.filter(pl.col("manager") != manager)  # pyright: ignore[reportUnknownMemberType]
        submask = subset.select(rule_expr(conditions).alias("m"))["m"]
        _record(split_stats(subset, submask, outcome, "development"))

    low, high = dev_frame[outcome.column].quantile(0.01), dev_frame[outcome.column].quantile(0.99)
    winsor_frame = dev_frame.with_columns(
        pl.col(outcome.column).clip(cast(float, low), cast(float, high))
    )
    _record(split_stats(winsor_frame, dev_mask, outcome, "development"))

    alt_outcome = OUTCOME_BY_ID["gross_profit_eur"]
    _record(split_stats(dev_frame, dev_mask, alt_outcome, "development"))

    for condition in conditions:
        if not isinstance(condition.value, int | float) or isinstance(condition.value, bool):
            continue
        column = dev_frame[condition.feature]
        for quantile in PERTURBATION_QUANTILES:
            perturbed_value = column.quantile(quantile)
            if perturbed_value is None:
                continue
            perturbed = tuple(
                Condition(c.feature, c.operator, round(float(perturbed_value), 8))
                if c is condition
                else c
                for c in conditions
            )
            pmask = dev_frame.select(rule_expr(perturbed).alias("m"))["m"]
            _record(split_stats(dev_frame, pmask, outcome, "development"))

    sign_agreement = sign_agree / checks_run if checks_run else 0.0
    max_magnitude_deviation = max((abs(r - 1.0) for r in magnitude_ratios), default=1.0)
    return sign_agreement, max_magnitude_deviation, checks_run


@dataclass(frozen=True, slots=True)
class CandidateValidation:
    candidate_id: str
    conditions: tuple[Condition, ...]
    report: ValidationReport
    verdict: str
    split_results: dict[str, SplitStats]
    diagnostics: dict[str, Any]
    economic_impact: EconomicImpactResult | None = None


def verdict_for(report: ValidationReport) -> str:
    if report.evidence_level is None:
        return Verdict.REJECT
    at_least_adjusted = report.evidence_level in (
        EvidenceLevel.ADJUSTED_OBSERVATIONAL,
        EvidenceLevel.QUASI_CAUSAL,
        EvidenceLevel.EXPERIMENTAL,
    )
    if at_least_adjusted and report.policy_readiness is not PolicyReadiness.NOT_READY:
        return Verdict.PASS
    return Verdict.DOWNGRADE


def _evaluated_hypotheses(payload: dict[str, Any], metrics_path: Path | None) -> int:
    """Locate the search's evaluated-hypothesis count across the two candidate schemas in use.

    The original discovery engine (`policy_analytics.discovery.engine`) nests it at
    ``payload["search"]["evaluated_hypotheses"]``. The blind-agent output schema
    (`tools.blind_agent.models.CandidatesDocument`, schema_version 1.1.0) does not carry it at
    all — it lives in a sibling ``discovery_metrics.json`` (`MetricsDocument.evaluated_hypotheses`)
    written by the same frozen run, because a blind actor's own count is not something the
    candidates document format allows it to assert about itself.
    """
    search = payload.get("search")
    if isinstance(search, dict) and "evaluated_hypotheses" in search:
        return int(cast(str, search["evaluated_hypotheses"]))
    if metrics_path is not None:
        metrics = cast(dict[str, Any], json.loads(metrics_path.read_text(encoding="utf-8")))
        return int(cast(str, metrics["evaluated_hypotheses"]))
    raise ValueError(
        "candidates payload has no search.evaluated_hypotheses and no metrics_path was given; "
        "gate G05 cannot run without the evaluated-hypothesis count (see the blind-agent schema's "
        "discovery_metrics.json)"
    )


def run_validation(
    dataset_root: Path,
    candidates_path: Path,
    outcome: OutcomeDefinition,
    dataset_version: str,
    outcome_definition_version: str,
    analysis_run_id: str,
    bootstrap_seed: int = BOOTSTRAP_SEED,
    metrics_path: Path | None = None,
) -> tuple[list[CandidateValidation], dict[str, Any]]:
    """Grade a persisted candidate document under the validation contract.

    Accepts either candidate-artifact shape in current use: the original discovery engine's
    output (`search.evaluated_hypotheses` nested inline) or the blind-agent output schema
    (`tools.blind_agent.models.CandidatesDocument`, `evaluated_hypotheses` in a sibling
    ``discovery_metrics.json`` passed as ``metrics_path``). Both put `candidate_id` and
    `conditions` in the same shape, which is all this function reads from each candidate — every
    other quantity (support, effect, per-split stability) is independently recomputed from the
    analytical dataset, never trusted from either document.
    """
    payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    status = payload.get("status")
    if status == "INSUFFICIENT_CANDIDATES":
        reason = payload.get("insufficiency_reason", "no reason recorded")
        raise ValueError(f"candidates run reported INSUFFICIENT_CANDIDATES: {reason}")
    if status != "PERSISTED":
        raise ValueError(f"candidates must have status=PERSISTED to be validated, got {status!r}")
    family_size = _evaluated_hypotheses(payload, metrics_path)
    candidates = payload["candidates"]

    payload_outcome_id = (
        payload.get("outcome", {}).get("outcome_id")
        if isinstance(payload.get("outcome"), dict)
        else None
    )
    mismatched_outcomes = sorted(
        {
            candidate["outcome"]
            for candidate in candidates
            if isinstance(candidate.get("outcome"), str)
            and candidate["outcome"] != outcome.outcome_id
        }
    )
    if mismatched_outcomes:
        raise ValueError(
            f"candidate(s) target outcome(s) {mismatched_outcomes}, expected only "
            f"{outcome.outcome_id!r} — refusing to grade a mixed-outcome candidate set"
        )
    if payload_outcome_id is not None and payload_outcome_id != outcome.outcome_id:
        raise ValueError(
            f"candidates payload declares outcome {payload_outcome_id!r}, "
            f"expected {outcome.outcome_id!r}"
        )

    frame = load_analytical_frame(dataset_root)
    rng = random.Random(bootstrap_seed)
    interims: list[CandidateInterim | None] = [
        _validate_one(frame, candidate, outcome, rng) for candidate in candidates
    ]

    reported_p_values = [interim.p_value if interim else 1.0 for interim in interims]
    adjusted_p_values = benjamini_hochberg_adjusted(reported_p_values, family_size=family_size)

    results: list[CandidateValidation] = []
    for candidate, interim, adjusted_p in zip(candidates, interims, adjusted_p_values, strict=True):
        candidate_id = candidate["candidate_id"]
        pattern_definition = " AND ".join(
            f"{c['feature']} {c['operator']} {c['value']}" for c in candidate["conditions"]
        )
        if interim is None:
            gate_results = tuple(
                GateResult(
                    gate_id=gate_id,
                    outcome=GateOutcome.NOT_EVALUATED,
                    detail="No development exposure.",
                )
                for gate_id in GateId
            )
            report = ValidationReport(
                candidate_id=candidate_id,
                analysis_run_id=analysis_run_id,
                dataset_version=dataset_version,
                outcome_definition_version=outcome_definition_version,
                pattern_definition=pattern_definition,
                outcome_definition=outcome.outcome_id,
                exposed_records=0,
                comparison_records=0,
                clustering_key="customer_id",
                raw_effect=EffectEstimate(0.0, 0.0, 0.0, 0.95, "unavailable", outcome.unit),
                identification_design=IdentificationDesign.OBSERVATIONAL,
                gate_results=gate_results,
                evidence_level=None,
                policy_readiness=PolicyReadiness.NOT_READY,
                recommended_validation="No development-split exposure; candidate cannot be graded.",
                failure_modes=("no_development_exposure",),
            )
            results.append(CandidateValidation(candidate_id, (), report, Verdict.REJECT, {}, {}))
            continue

        g05 = _gate(
            GateId.MULTIPLICITY,
            adjusted_p <= DEFAULT_THRESHOLDS.fdr_alpha,
            f"Normal-approx p (bootstrap SE)={interim.p_value:.3g}, BH-adjusted p="
            f"{adjusted_p:.3g} over family_size={family_size} "
            f"(alpha={DEFAULT_THRESHOLDS.fdr_alpha}).",
        )
        merged_gates = {**interim.gates_except_multiplicity, GateId.MULTIPLICITY: g05}
        gate_results = tuple(merged_gates[gate_id] for gate_id in GateId)
        design = IdentificationDesign.OBSERVATIONAL
        evidence_level = classify_evidence_level(gate_results, design)
        readiness = assign_policy_readiness(
            evidence_level, gate_results, operationally_feasible=True, backtest_net_positive=None
        )
        dev = interim.split_results["development"]
        failure_modes = tuple(
            gate_id.value for gate_id in GateId if not merged_gates[gate_id].satisfied
        )
        report = ValidationReport(
            candidate_id=candidate_id,
            analysis_run_id=analysis_run_id,
            dataset_version=dataset_version,
            outcome_definition_version=outcome_definition_version,
            pattern_definition=pattern_definition,
            outcome_definition=outcome.outcome_id,
            exposed_records=dev.n_exposed,
            comparison_records=dev.n_comparison,
            clustering_key="customer_id",
            raw_effect=interim.dev_effect,
            identification_design=design,
            gate_results=gate_results,
            evidence_level=evidence_level,
            policy_readiness=readiness,
            recommended_validation=(
                "Design a controlled experiment or natural-experiment test before any enforcement."
                if evidence_level is None
                or evidence_level in (EvidenceLevel.DESCRIPTIVE, EvidenceLevel.PREDICTIVE)
                else (
                    "Run as a shadow policy for at least one full seasonal cycle before "
                    "enforcement."
                )
            ),
            adjusted_effect=interim.adjusted_effect,
            adjusted_p_value=adjusted_p,
            family_size=family_size,
            controlled_variables=interim.adjustment_set,
            potential_confounders=("manager", "supplier", "customer_segment", "booking_month"),
            robustness_tests=(
                "leave_one_manager_out",
                "winsorize_top_bottom_1pct",
                "alternative_outcome_gross_profit",
                "numeric_threshold_perturbation",
            ),
            temporal_stability=(
                f"same_sign={interim.diagnostics.get('splits_present')}, "
                f"holdout_retention={interim.diagnostics.get('holdout_retention', 0.0):.2f}"
            ),
            failure_modes=failure_modes,
        )
        verdict = verdict_for(report)
        results.append(
            CandidateValidation(
                candidate_id,
                interim.conditions,
                report,
                verdict,
                interim.split_results,
                interim.diagnostics,
                economic_impact=interim.economic_impact,
            )
        )

    manifest = {
        "family_size": family_size,
        "family_size_source": "candidates.search" if "search" in payload else "metrics_path",
        "candidates_schema_version": payload.get("schema_version"),
        "candidates_payload_dataset_identity_sha256": payload.get("dataset_identity_sha256"),
        "fdr_alpha": DEFAULT_THRESHOLDS.fdr_alpha,
        "bootstrap_seed": bootstrap_seed,
        "development_bootstrap_reps": DEV_BOOTSTRAP_REPS,
        "diagnostic_bootstrap_reps": DIAGNOSTIC_BOOTSTRAP_REPS,
        "adjustment_columns_considered": list(CONFOUNDER_COLUMNS),
        "heterogeneity_column": HETEROGENEITY_COLUMN,
    }
    return results, manifest
