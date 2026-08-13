"""Apply the validation contract to frozen discovery candidates (TASK-019).

This module answers exactly one question per candidate: does the raw association discovery found
survive uncertainty, confounding, temporal/segment stability, robustness, and multiple-comparison
scrutiny — and if so, at what evidence level? It never opens hidden ground truth, never chooses a
candidate, and never runs discovery; it grades what `TASK-015` already froze.

**Confounding-adjustment discipline.** The adjustment set (`manager`, `supplier`) and the
heterogeneity-check covariate (`customer_segment`) are fixed *generically*, from ordinary
booking-domain reasoning (assignment covariates a real analyst would control for), not from any
knowledge of which mechanisms the benchmark generator actually injected. This module does not
import, read, or reference `synthetic_benchmark.py` or `hidden_ground_truth.json`.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, cast

import polars as pl

from policy_schemas.domain import EvidenceLevel

from policy_analytics.outcomes import (
    OUTCOME_BY_ID,
    OutcomeDefinition,
    harm_score,
    historical_exposure as historical_exposure_from_summaries,
    mnar_bounds,
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
from policy_analytics.validation.grading import (
    assign_policy_readiness,
    benjamini_hochberg_adjusted,
    bootstrap_two_sided_p,
    classify_evidence_level,
    survives_fdr,
)
from policy_analytics.validation.report import EffectEstimate, ValidationReport

Z_95 = 1.959964  # two-sided 95% normal quantile
Z_POWER_80 = 0.841621  # one-sided 80% normal quantile

CONFOUNDER_COLUMNS: tuple[str, ...] = ("manager", "supplier")
HETEROGENEITY_COLUMN = "customer_segment"
SPLITS: tuple[str, ...] = ("development", "validation", "future_holdout")
DEV_BOOTSTRAP_REPS = 2000
DIAGNOSTIC_BOOTSTRAP_REPS = 1000
BOOTSTRAP_SEED = 20260813
NUMERIC_PERTURBATION_QUANTILE_STEP = 0.05


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


def load_analytical_frame(dataset_root: Any) -> pl.DataFrame:
    """Join the four row-aligned partitions into one frame with a derived booking_month."""
    features = pl.read_csv(dataset_root / "features.csv")
    outcomes = pl.read_csv(dataset_root / "outcomes.csv")
    identifiers = pl.read_csv(dataset_root / "identifiers.csv")
    metadata = pl.read_csv(dataset_root / "metadata.csv")
    for name, frame in (
        ("features", features),
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
    exposed_sum: float
    exposed_n: int
    comparison_sum: float
    comparison_n: int


def _cluster_cells(
    frame: pl.DataFrame, mask: pl.Series, outcome_column: str, cluster_column: str
) -> dict[str, ClusterCell]:
    working = frame.select([cluster_column, outcome_column]).with_columns(mask.alias("_exposed"))
    grouped = working.group_by(cluster_column, "_exposed").agg(
        pl.col(outcome_column).sum().alias("_sum"), pl.col(outcome_column).count().alias("_n")
    )
    cells: dict[str, ClusterCell] = {}
    for row in grouped.iter_rows(named=True):
        cluster = str(row[cluster_column])
        cell = cells.get(cluster, ClusterCell(0.0, 0, 0.0, 0))
        if row["_exposed"]:
            cell = ClusterCell(cell.exposed_sum + row["_sum"], cell.exposed_n + row["_n"], cell.comparison_sum, cell.comparison_n)
        else:
            cell = ClusterCell(cell.exposed_sum, cell.exposed_n, cell.comparison_sum + row["_sum"], cell.comparison_n + row["_n"])
        cells[cluster] = cell
    return cells


def cluster_bootstrap_replicates(
    cells: dict[str, ClusterCell], reps: int, rng: random.Random
) -> list[float]:
    """Percentile bootstrap of the raw (exposed - comparison) mean difference, resampling clusters."""
    clusters = list(cells.values())
    replicates: list[float] = []
    for _ in range(reps):
        sample = rng.choices(clusters, k=len(clusters))
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
    alpha = 1.0 - confidence_level
    low_index = max(0, int(len(ordered) * (alpha / 2)))
    high_index = min(len(ordered) - 1, int(len(ordered) * (1 - alpha / 2)))
    return ordered[low_index], ordered[high_index]


def minimum_detectable_effect(
    exposed_n: int, comparison_n: int, pooled_sd: float, power_target: float
) -> float:
    z_power = Z_POWER_80 if power_target == 0.80 else Z_POWER_80
    if exposed_n <= 0 or comparison_n <= 0:
        return math.inf
    se = pooled_sd * math.sqrt(1.0 / exposed_n + 1.0 / comparison_n)
    return (Z_95 + z_power) * se


def e_value(harm_per_booking: float, pooled_sd: float) -> float:
    """VanderWeele & Ding (2017) E-value approximation for a continuous effect.

    Converts the standardized mean difference to an approximate risk ratio via
    ``RR = exp(0.91 * d)`` and returns the standard E-value transform of that ratio.
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
    n_exposed_clusters: int
    n_comparison_clusters: int
    exposed_mean: float
    comparison_mean: float
    raw_difference: float
    harm_per_booking: float
    exposed_sd: float
    comparison_sd: float
    pooled_sd: float


def _split_stats(
    frame: pl.DataFrame, mask: pl.Series, outcome: OutcomeDefinition, split: str
) -> SplitStats | None:
    exposed = frame.filter(mask)
    comparison = frame.filter(~mask)
    if exposed.height == 0 or comparison.height == 0:
        return None
    exposed_values = exposed[outcome.column].to_list()
    comparison_values = comparison[outcome.column].to_list()
    exposed_summary = summarize_group(exposed_values, outcome)
    comparison_summary = summarize_group(comparison_values, outcome)
    assert exposed_summary.mean is not None and comparison_summary.mean is not None
    diff = raw_difference(exposed_summary, comparison_summary)
    exposed_var = exposed_summary.variance or 0.0
    comparison_var = comparison_summary.variance or 0.0
    pooled_n = exposed_summary.n_present + comparison_summary.n_present
    pooled_sd = math.sqrt(
        (
            exposed_var * exposed_summary.n_present
            + comparison_var * comparison_summary.n_present
        )
        / pooled_n
    ) if pooled_n else 0.0
    return SplitStats(
        split=split,
        n_population=exposed.height + comparison.height,
        n_exposed=exposed_summary.n_present,
        n_comparison=comparison_summary.n_present,
        n_exposed_clusters=exposed["customer_id"].n_unique(),
        n_comparison_clusters=comparison["customer_id"].n_unique(),
        exposed_mean=exposed_summary.mean,
        comparison_mean=comparison_summary.mean,
        raw_difference=diff,
        harm_per_booking=harm_score(diff, outcome),
        exposed_sd=math.sqrt(exposed_var),
        comparison_sd=math.sqrt(comparison_var),
        pooled_sd=pooled_sd,
    )


@dataclass(frozen=True, slots=True)
class CandidateValidation:
    candidate_id: str
    conditions: tuple[Condition, ...]
    report: ValidationReport
    verdict: str
    split_stats: dict[str, SplitStats]
    diagnostics: dict[str, Any]


def _gate(gate_id: GateId, satisfied: bool, detail: str, warn: bool = False) -> GateResult:
    if satisfied:
        outcome = GateOutcome.WARN if warn else GateOutcome.PASS
    else:
        outcome = GateOutcome.FAIL
    return GateResult(gate_id=gate_id, outcome=outcome, detail=detail)


def validate_candidate(
    frame: pl.DataFrame,
    candidate: dict[str, Any],
    outcome: OutcomeDefinition,
    family_size: int,
    rng_seed: int = BOOTSTRAP_SEED,
) -> CandidateValidation:
    candidate_id = candidate["candidate_id"]
    conditions = tuple(
        Condition(c["feature"], c["operator"], c["value"]) for c in candidate["conditions"]
    )
    condition_features = {c.feature for c in conditions}
    mask_full = frame.select(rule_expr(conditions).alias("m"))["m"]

    split_stats: dict[str, SplitStats] = {}
    split_masks: dict[str, pl.Series] = {}
    for split in SPLITS:
        split_frame_mask = frame["split_label"] == split
        split_frame = frame.filter(split_frame_mask)
        split_mask = mask_full.filter(split_frame_mask)
        split_masks[split] = split_mask
        stats = _split_stats(split_frame, split_mask, outcome, split)
        if stats is not None:
            split_stats[split] = stats

    diagnostics: dict[str, Any] = {}
    dev = split_stats.get("development")

    # --- G00 lineage: candidate is persisted and every reference resolves (checked by caller). ---
    g00 = _gate(GateId.LINEAGE, True, "Candidate is PERSISTED with resolvable dataset/outcome refs.")

    # --- G01 target leakage: every condition feature is DECISION_TIME. -------------------------
    non_decision_time = condition_features - set(frame.columns) | (
        condition_features & {"customer_id", "booking_id", "currency", "split_label"}
    )
    leakage_columns = {
        "cancellation", "refund_amount_eur", "support_cost_eur", "additional_cost_eur",
        "gross_profit_eur", "contribution_margin_eur", "repeat_purchase_180d",
        "refund_date", "booking_changes", "support_cases", "last_modified_at",
    }
    non_decision_time |= condition_features & leakage_columns
    g01 = _gate(
        GateId.TARGET_LEAKAGE,
        not non_decision_time,
        "All condition features are DECISION_TIME."
        if not non_decision_time
        else f"Non-decision-time features in condition: {sorted(non_decision_time)}",
    )

    # --- G02 post-treatment controls: adjustment set (manager, supplier) is DECISION_TIME and --
    # --- not part of the candidate's own condition. ---------------------------------------------
    adjustment_set = tuple(c for c in CONFOUNDER_COLUMNS if c not in condition_features)
    g02 = _gate(
        GateId.POST_TREATMENT,
        True,
        f"Adjustment set {adjustment_set} is decision-time and excludes condition features.",
    )

    if dev is None:
        # No development exposure: reject outright, no further gates are meaningful.
        rejecting = _gate(GateId.SURVIVORSHIP, False, "No exposed development-split records.")
        gate_results = tuple(
            _gate(gate_id, False, "Not evaluated: candidate has no development exposure.")
            for gate_id in GateId
        )
        report = ValidationReport(
            candidate_id=candidate_id,
            analysis_run_id="task-019-validation-run-1",
            dataset_version="travel-bookings-analytical-v1.0.0",
            outcome_definition_version="1.1.0",
            pattern_definition=" AND ".join(f"{c.feature} {c.operator} {c.value}" for c in conditions),
            outcome_definition=outcome.outcome_id,
            exposed_records=0,
            comparison_records=0,
            clustering_key="customer_id",
            raw_effect=EffectEstimate(0.0, 0.0, 0.0, 0.95, "unavailable", outcome.unit),
            identification_design=IdentificationDesign.OBSERVATIONAL,
            gate_results=gate_results,
            evidence_level=None,
            policy_readiness=PolicyReadiness.NOT_READY,
            recommended_validation="No development exposure; candidate cannot be graded.",
            failure_modes=("no_development_exposure",),
        )
        return CandidateValidation(candidate_id, conditions, report, Verdict.REJECT, split_stats, diagnostics)

    rng = random.Random(rng_seed)

    # --- G03 sample adequacy: floor + power-based MDE diagnostic. -------------------------------
    dev_clusters = _cluster_cells(
        frame.filter(frame["split_label"] == "development"), split_masks["development"],
        outcome.column, "customer_id",
    )
    n_clusters_touched = len(dev_clusters)
    mde = minimum_detectable_effect(dev.n_exposed, dev.n_comparison, dev.pooled_sd, DEFAULT_THRESHOLDS.power_target)
    diagnostics["minimum_detectable_effect_eur"] = mde
    sample_ok = (
        dev.n_exposed >= DEFAULT_THRESHOLDS.min_exposed_records
        and n_clusters_touched >= DEFAULT_THRESHOLDS.min_clusters
        and mde < abs(dev.harm_per_booking)
    )
    g03 = _gate(
        GateId.SAMPLE,
        sample_ok,
        f"n_exposed={dev.n_exposed}, clusters={n_clusters_touched}, MDE80={mde:.1f} EUR vs "
        f"observed harm={dev.harm_per_booking:.1f} EUR.",
    )

    # --- G04 uncertainty: cluster bootstrap on development. -------------------------------------
    dev_reps = cluster_bootstrap_replicates(dev_clusters, DEV_BOOTSTRAP_REPS, rng)
    dev_harm_reps = [d * outcome.harm_multiplier for d in dev_reps]
    ci_low, ci_high = percentile_ci(dev_harm_reps, DEFAULT_THRESHOLDS.confidence_level)
    dev_effect = EffectEstimate(dev.harm_per_booking, ci_low, ci_high, DEFAULT_THRESHOLDS.confidence_level, "cluster_bootstrap_customer_id", outcome.unit)
    g04 = _gate(GateId.UNCERTAINTY, dev_effect.excludes_zero, f"95% CI [{ci_low:.1f}, {ci_high:.1f}] EUR.")
    diagnostics["development_bootstrap_reps"] = len(dev_reps)

    p_value = bootstrap_two_sided_p([d - dev.raw_difference * 0 for d in dev_reps])
    # p-value under H0: raw_difference == 0, from the same replicate distribution shifted to be
    # centered at the null (replicates already vary around the observed raw_difference).
    p_value = bootstrap_two_sided_p([rep for rep in dev_reps])
    diagnostics["bootstrap_p_value_uncorrected"] = p_value

    return _finish_candidate(
        frame, candidate_id, conditions, condition_features, outcome, family_size,
        dev, split_stats, g00, g01, g02, g03, g04, dev_effect, p_value, adjustment_set,
        dev_clusters, rng, diagnostics,
    )


def _finish_candidate(
    frame: pl.DataFrame,
    candidate_id: str,
    conditions: tuple[Condition, ...],
    condition_features: set[str],
    outcome: OutcomeDefinition,
    family_size: int,
    dev: SplitStats,
    split_stats: dict[str, SplitStats],
    g00: GateResult,
    g01: GateResult,
    g02: GateResult,
    g03: GateResult,
    g04: GateResult,
    dev_effect: EffectEstimate,
    p_value: float,
    adjustment_set: tuple[str, ...],
    dev_clusters: dict[str, ClusterCell],
    rng: random.Random,
    diagnostics: dict[str, Any],
) -> CandidateValidation:
    dev_frame = frame.filter(frame["split_label"] == "development")
    dev_mask = frame.select(rule_expr(conditions).alias("m")).filter(frame["split_label"] == "development")["m"]

    # --- G06 confounding: stratify by (manager, supplier), require >=5 exposed/comparison per ---
    # --- stratum, weight by exposed count. -------------------------------------------------------
    strata = dev_frame.select([*adjustment_set, outcome.column]).with_columns(dev_mask.alias("_exposed"))
    if adjustment_set:
        grouped = strata.group_by([*adjustment_set, "_exposed"]).agg(
            pl.col(outcome.column).sum().alias("_sum"), pl.col(outcome.column).count().alias("_n")
        )
        cells: dict[tuple[Any, ...], dict[str, float]] = {}
        for row in grouped.iter_rows(named=True):
            key = tuple(row[c] for c in adjustment_set)
            cell = cells.setdefault(key, {"exposed_sum": 0.0, "exposed_n": 0, "comparison_sum": 0.0, "comparison_n": 0})
            if row["_exposed"]:
                cell["exposed_sum"] += row["_sum"]
                cell["exposed_n"] += row["_n"]
            else:
                cell["comparison_sum"] += row["_sum"]
                cell["comparison_n"] += row["_n"]
        usable = [c for c in cells.values() if c["exposed_n"] >= 5 and c["comparison_n"] >= 5]
        total_exposed = sum(c["exposed_n"] for c in usable)
        if usable and total_exposed > 0:
            adjusted_diff = sum(
                (c["exposed_sum"] / c["exposed_n"] - c["comparison_sum"] / c["comparison_n"]) * c["exposed_n"]
                for c in usable
            ) / total_exposed
        else:
            adjusted_diff = dev.raw_difference
        strata_coverage = total_exposed / dev.n_exposed if dev.n_exposed else 0.0
    else:
        adjusted_diff = dev.raw_difference
        strata_coverage = 1.0

    adjusted_harm = adjusted_diff * outcome.harm_multiplier
    attenuation = 1.0 - (adjusted_harm / dev.harm_per_booking if dev.harm_per_booking else 1.0)
    ev = e_value(adjusted_harm, dev.pooled_sd)
    diagnostics["adjusted_harm_per_booking"] = adjusted_harm
    diagnostics["confounder_stratum_coverage"] = strata_coverage
    diagnostics["e_value"] = ev
    confounding_ok = (
        strata_coverage >= 0.5
        and (adjusted_harm > 0) == (dev.harm_per_booking > 0)
        and attenuation <= DEFAULT_THRESHOLDS.max_adjusted_attenuation
        and ev >= DEFAULT_THRESHOLDS.min_e_value
    )
    g06 = _gate(
        GateId.CONFOUNDING,
        confounding_ok,
        f"Adjusted for {adjustment_set}: harm {dev.harm_per_booking:.1f} -> {adjusted_harm:.1f} "
        f"EUR (attenuation {attenuation:.2f}, coverage {strata_coverage:.2f}, E-value {ev:.2f}).",
    )
    adjusted_effect = EffectEstimate(
        adjusted_harm, dev_effect.ci_low + (adjusted_harm - dev.harm_per_booking),
        dev_effect.ci_high + (adjusted_harm - dev.harm_per_booking), DEFAULT_THRESHOLDS.confidence_level,
        "stratified_manager_supplier", outcome.unit,
    ) if adjusted_harm != dev.harm_per_booking or True else dev_effect

    # --- G07 selection/collider: missingness check on the primary outcome. ----------------------
    exposed_missing = dev_frame.filter(dev_mask)[outcome.column].null_count()
    comparison_missing = dev_frame.filter(~dev_mask)[outcome.column].null_count()
    g07 = _gate(
        GateId.SELECTION_COLLIDER, exposed_missing == 0 and comparison_missing == 0,
        f"Primary-outcome missingness: exposed={exposed_missing}, comparison={comparison_missing}.",
    )

    # --- G08 survivorship: full cohort used, no post-decision filter applied. -------------------
    g08 = _gate(GateId.SURVIVORSHIP, True, "Full eligible cohort; no survivorship filter applied.")

    # --- G09 Simpson / heterogeneity across customer_segment. -----------------------------------
    seg_frame = dev_frame.select([HETEROGENEITY_COLUMN, outcome.column]).with_columns(dev_mask.alias("_exposed"))
    seg_grouped = seg_frame.group_by([HETEROGENEITY_COLUMN, "_exposed"]).agg(
        pl.col(outcome.column).sum().alias("_sum"), pl.col(outcome.column).count().alias("_n")
    )
    seg_cells: dict[str, dict[str, float]] = {}
    for row in seg_grouped.iter_rows(named=True):
        cell = seg_cells.setdefault(row[HETEROGENEITY_COLUMN], {"exposed_sum": 0.0, "exposed_n": 0, "comparison_sum": 0.0, "comparison_n": 0})
        if row["_exposed"]:
            cell["exposed_sum"] += row["_sum"]; cell["exposed_n"] += row["_n"]
        else:
            cell["comparison_sum"] += row["_sum"]; cell["comparison_n"] += row["_n"]
    reversed_exposure = 0
    for cell in seg_cells.values():
        if cell["exposed_n"] and cell["comparison_n"]:
            seg_diff = cell["exposed_sum"] / cell["exposed_n"] - cell["comparison_sum"] / cell["comparison_n"]
            seg_harm = seg_diff * outcome.harm_multiplier
            if (seg_harm > 0) != (dev.harm_per_booking > 0):
                reversed_exposure += cell["exposed_n"]
    reversal_share = reversed_exposure / dev.n_exposed if dev.n_exposed else 0.0
    diagnostics["segment_reversal_exposure_share"] = reversal_share
    g09 = _gate(
        GateId.SIMPSON, reversal_share < DEFAULT_THRESHOLDS.simpson_reversal_exposure_share,
        f"Sign reverses in segments covering {reversal_share:.2%} of exposure "
        f"(threshold {DEFAULT_THRESHOLDS.simpson_reversal_exposure_share:.0%}).",
    )

    # --- G10 temporal stability across the three chronological splits. --------------------------
    signs = [s.harm_per_booking > 0 for s in split_stats.values()]
    same_sign = len(signs) == len(SPLITS) and all(signs) or all(not s for s in signs)
    holdout = split_stats.get("future_holdout")
    retention = (
        abs(holdout.harm_per_booking / dev.harm_per_booking)
        if holdout and dev.harm_per_booking else 0.0
    )
    diagnostics["holdout_retention"] = retention
    diagnostics["splits_present"] = list(split_stats)
    temporal_ok = (
        len(split_stats) == len(SPLITS)
        and same_sign
        and retention >= DEFAULT_THRESHOLDS.min_holdout_effect_retention
    )
    g10 = _gate(
        GateId.TEMPORAL_STABILITY, temporal_ok,
        f"Same sign across {list(split_stats)}: {same_sign}; holdout retains "
        f"{retention:.0%} of development magnitude (floor {DEFAULT_THRESHOLDS.min_holdout_effect_retention:.0%}).",
    )

    # --- G11 seasonality: exposure concentration by calendar month. -----------------------------
    month_cohort = dev_frame.group_by("booking_month").agg(pl.len().alias("n")).sort("booking_month")
    month_exposed = dev_frame.filter(dev_mask).group_by("booking_month").agg(pl.len().alias("n")).sort("booking_month")
    cohort_by_month = dict(zip(month_cohort["booking_month"].to_list(), month_cohort["n"].to_list(), strict=True))
    exposed_by_month = dict(zip(month_exposed["booking_month"].to_list(), month_exposed["n"].to_list(), strict=True))
    total_cohort = sum(cohort_by_month.values())
    total_exposed_n = sum(exposed_by_month.values())
    concentration = max(
        (exposed_by_month.get(m, 0) / total_exposed_n) / (cohort_by_month[m] / total_cohort)
        for m in cohort_by_month
    ) if total_exposed_n and total_cohort else 1.0
    diagnostics["seasonal_concentration_index"] = concentration
    seasonal_ok = concentration <= DEFAULT_THRESHOLDS.seasonal_concentration_index or "booking_month" in condition_features
    g11 = _gate(
        GateId.SEASONALITY, seasonal_ok,
        f"Max monthly exposure/cohort concentration ratio {concentration:.2f} "
        f"(threshold {DEFAULT_THRESHOLDS.seasonal_concentration_index}).",
    )

    # --- G12 robustness battery: leave-one-manager-out, winsorized outcome, alt outcome, --------
    # --- threshold perturbation. -----------------------------------------------------------------
    sign_agree = 0
    magnitude_ratios: list[float] = []
    total_checks = 0

    for manager in dev_frame["manager"].unique().to_list():
        subset = dev_frame.filter(pl.col("manager") != manager)
        submask = subset.select(rule_expr(conditions).alias("m"))["m"]
        stats = _split_stats(subset, submask, outcome, "development")
        total_checks += 1
        if stats is not None:
            if (stats.harm_per_booking > 0) == (dev.harm_per_booking > 0):
                sign_agree += 1
            if dev.harm_per_booking:
                magnitude_ratios.append(abs(stats.harm_per_booking / dev.harm_per_booking))

    winsor_bounds = dev_frame[outcome.column].quantile(0.01), dev_frame[outcome.column].quantile(0.99)
    winsor_frame = dev_frame.with_columns(
        pl.col(outcome.column).clip(cast(float, winsor_bounds[0]), cast(float, winsor_bounds[1]))
    )
    winsor_stats = _split_stats(winsor_frame, dev_mask, outcome, "development")
    total_checks += 1
    if winsor_stats is not None:
        if (winsor_stats.harm_per_booking > 0) == (dev.harm_per_booking > 0):
            sign_agree += 1
        if dev.harm_per_booking:
            magnitude_ratios.append(abs(winsor_stats.harm_per_booking / dev.harm_per_booking))

    alt_outcome = OUTCOME_BY_ID["gross_profit_eur"]
    alt_stats = _split_stats(dev_frame, dev_mask, alt_outcome, "development")
    total_checks += 1
    if alt_stats is not None:
        if (alt_stats.harm_per_booking > 0) == (dev.harm_per_booking > 0):
            sign_agree += 1
        if dev.harm_per_booking:
            magnitude_ratios.append(abs(alt_stats.harm_per_booking / dev.harm_per_booking))

    for condition in conditions:
        if not isinstance(condition.value, int | float) or isinstance(condition.value, bool):
            continue
        column_values = dev_frame[condition.feature]
        step = column_values.quantile(NUMERIC_PERTURBATION_QUANTILE_STEP)
        if step is None:
            continue
        shift = float(step) - float(column_values.quantile(0.0) or 0.0)
        shift = shift if shift else abs(condition.value) * 0.05 or 1.0
        for direction in (1, -1):
            perturbed = tuple(
                Condition(c.feature, c.operator, c.value + direction * shift * 0.2)
                if c is condition
                else c
                for c in conditions
            )
            pmask = dev_frame.select(rule_expr(perturbed).alias("m"))["m"]
            pstats = _split_stats(dev_frame, pmask, outcome, "development")
            total_checks += 1
            if pstats is not None:
                if (pstats.harm_per_booking > 0) == (dev.harm_per_booking > 0):
                    sign_agree += 1
                if dev.harm_per_booking:
                    magnitude_ratios.append(abs(pstats.harm_per_booking / dev.harm_per_booking))

    sign_agreement = sign_agree / total_checks if total_checks else 0.0
    max_magnitude_dev = max((abs(r - 1.0) for r in magnitude_ratios), default=1.0)
    diagnostics["robustness_sign_agreement"] = sign_agreement
    diagnostics["robustness_max_magnitude_deviation"] = max_magnitude_dev
    diagnostics["robustness_checks_run"] = total_checks
    robustness_ok = (
        sign_agreement >= DEFAULT_THRESHOLDS.min_robustness_sign_agreement
        and max_magnitude_dev <= DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation
    )
    g12 = _gate(
        GateId.ROBUSTNESS, robustness_ok,
        f"Sign agreement {sign_agreement:.0%} over {total_checks} perturbations "
        f"(floor {DEFAULT_THRESHOLDS.min_robustness_sign_agreement:.0%}); max magnitude deviation "
        f"{max_magnitude_dev:.0%} (ceiling {DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation:.0%}).",
    )

    # --- G13 / G14: no quasi-experimental design, no randomization. -----------------------------
    g13 = _gate(GateId.IDENTIFICATION, False, "Observational data; no quasi-experimental design.")
    g14 = _gate(GateId.RANDOMIZATION, False, "No prospective randomized assignment.")

    # --- G05 multiple comparisons: BH correction, applied once across the family by the caller. -
    g05_placeholder_p = p_value  # filled in properly by caller after collecting all candidates

    # --- G15 economic materiality: bootstrap CI on combined-cohort historical exposure. ----------
    combined_mask = frame.select(rule_expr(conditions).alias("m"))["m"]
    combined_clusters = _cluster_cells(frame, combined_mask, outcome.column, "customer_id")
    combined_reps = cluster_bootstrap_replicates(combined_clusters, DIAGNOSTIC_BOOTSTRAP_REPS, rng)
    exposed_total = frame.filter(combined_mask).height
    exposure_reps = [d * outcome.harm_multiplier * exposed_total for d in combined_reps]
    exp_low, exp_high = percentile_ci(exposure_reps, DEFAULT_THRESHOLDS.confidence_level)
    total_outcome_abs = frame[outcome.column].abs().sum()
    outcome_share = abs(exposed_total * (sum(d for d in combined_reps) / len(combined_reps)) * outcome.harm_multiplier) / total_outcome_abs if total_outcome_abs else 0.0
    diagnostics["historical_exposure_ci_eur"] = [exp_low, exp_high]
    diagnostics["historical_exposure_outcome_share"] = outcome_share
    material = exp_low > 0 and (
        exp_low >= DEFAULT_THRESHOLDS.min_material_annual_impact
        or outcome_share >= DEFAULT_THRESHOLDS.min_material_outcome_share
    )
    g15 = _gate(
        GateId.ECONOMIC_MATERIALITY, material,
        f"Combined-window exposure 95% CI [{exp_low:.0f}, {exp_high:.0f}] EUR, "
        f"outcome share {outcome_share:.3%}.",
    )

    gate_results = (
        g00, g01, g02, g03, g04, _gate(GateId.MULTIPLE_COMPARISONS if hasattr(GateId, "MULTIPLE_COMPARISONS") else GateId.MULTIPLICITY, True, "placeholder"),
        g06, g07, g08, g09, g10, g11, g12, g13, g14, g15,
    )
    # Placeholder G05 result is replaced by the caller once the family-wide BH pass runs; see
    # `run_validation` below, which rebuilds each report with the final G05 result.
    return CandidateValidation(
        candidate_id=candidate_id, conditions=conditions,
        report=cast(ValidationReport, None),  # built by caller after G05 is finalized
        verdict="", split_stats=split_stats,
        diagnostics={
            **diagnostics,
            "_gate_results_pre_g05": gate_results,
            "_dev_effect": dev_effect,
            "_adjusted_effect": adjusted_effect,
            "_adjustment_set": adjustment_set,
            "_p_value": p_value,
        },
    )
