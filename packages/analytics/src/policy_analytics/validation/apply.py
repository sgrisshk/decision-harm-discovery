"""Apply the validation contract to frozen discovery candidates (TASK-019).

This module answers exactly one question per candidate: does the raw association discovery found
survive uncertainty, confounding, temporal/segment stability, robustness, and multiple-comparison
scrutiny — and if so, at what evidence level? It never opens hidden ground truth, never chooses a
candidate, and never runs discovery; it grades what `TASK-015` already froze.

**Confounding-adjustment discipline (CONTRACT_VERSION >= 1.2.0, `ADR-036`/`ADR-042`, `TASK-063`).**
G06's adjustment set is no longer a fixed pair chosen once by hand — it is computed per candidate as
every eligible `DECISION_TIME` covariate outside the candidate's own condition set, greedily
included in ascending-cardinality order up to whatever the sample can jointly support
(`_select_adjustment_columns`). The *rule* is fixed generically (cardinality-ordered, coverage-
gated, applies identically to every candidate and every dataset); the resulting *set* varies by
candidate, which is the point — a fixed two-variable set structurally cannot see a confounder
outside it, exactly the gap `ADR-036` diagnosed in the travel benchmark's trap `T03`. No gate logic
here references `T03`, `acquisition_channel`, or any other specific feature/trap by name — the
generalization is a property of the selection *rule*, not a patch for one candidate. See
`docs/analytics/validation-contract.md` §4b for the full design and its synthetic-only regression
tests. Heterogeneity and seasonality roles are declared by the selected analytical manifest.
This module does not import, read, or reference `synthetic_benchmark.py` or
`hidden_ground_truth.json`, and must not be edited to do so.

**Robustness semantics (CONTRACT_VERSION >= 1.3.0, `ADR-064`, `TASK-070`).** G12's threshold
perturbation is now a one-bin step measured from *each candidate's own threshold position*
(`PERTURBATION_PERCENTILE_STEP`), the semantics the contract's preregistered wording always
specified, with named `RobustnessRefitState`s for coarse/discrete columns instead of a silent
no-estimate failure; and an alternative outcome binds G12's magnitude-parity check only when
`alternative_outcome_admissibility` admits it as a commensurable measurement of the same construct
rather than an accounting component of the primary. Both defects were established on neutrally-
constructed synthetic data in `docs/benchmark/task-069-g12-form-investigation.md`; neither fix
references any dataset, pattern, or feature identity. `RobustnessSemantics.FIXED_QUANTILE_V1` keeps
the pre-v1.3.0 behaviour executable so frozen runs remain reproducible under their own recorded
`validation_contract_version`. See `docs/analytics/validation-contract.md` §4c.

Flow: `validate_family` computes gates G00-G04 and G06-G15 per candidate (everything that does not
require knowing the other candidates), collects one G05 p-value per candidate (the normal
approximation on the cluster-bootstrap standard error — see `grading.normal_approx_two_sided_p`
and ADR-014/ADR-015; the empirical count-based bootstrap p-value is retained only as a diagnostic),
then applies Benjamini-Hochberg across the *entire evaluated search* (family_size from the
discovery run manifest, not the 15 reported candidates) to fill in G05, and finally assembles each
`ValidationReport`.
"""

from __future__ import annotations

import bisect
import json
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast

import polars as pl
from policy_schemas.domain import EvidenceLevel

from policy_analytics.outcomes import (
    OUTCOME_BY_ID,
    MissingDataPolicy,
    OutcomeDefinition,
    harm_score,
    raw_difference,
    summarize_group,
)
from policy_analytics.validation.composition_safety import classify_composition_safety
from policy_analytics.validation.contract import (
    DEFAULT_THRESHOLDS,
    ROBUSTNESS_SEMANTICS_VERSION,
    AlternativeOutcomeAdmissibility,
    GateId,
    GateOutcome,
    GateResult,
    IdentificationDesign,
    PolicyReadiness,
    RobustnessRefitState,
    RobustnessSemantics,
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
from policy_analytics.validation.input_contract import (
    FeatureRole,
    ValidationInput,
    validate_candidate_fields,
    validation_input_from_manifest,
)
from policy_analytics.validation.report import EffectEstimate, ValidationReport

Z_95 = 1.959964  # two-sided 95% normal quantile
Z_POWER_80 = 0.841621  # one-sided 80% normal quantile (matches DEFAULT_THRESHOLDS.power_target)

SPLITS: tuple[str, ...] = ("development", "validation", "future_holdout")
DEV_BOOTSTRAP_REPS = 2000
DIAGNOSTIC_BOOTSTRAP_REPS = 1000
BOOTSTRAP_SEED = 20260813
#: Legacy G12 threshold-perturbation grid (CONTRACT_VERSION <= 1.2.0, `RobustnessSemantics.
#: FIXED_QUANTILE_V1`). Frozen: it is the definition of an older contract version's behaviour and
#: must never change again. It replaced *every* numeric threshold with these two fixed quantiles of
#: its own column, regardless of where the candidate's threshold actually sat — a genuine one-bin
#: step only for a threshold at this pair's own ~q0.20 anchor, and a closed-form function of
#: threshold position everywhere else (`docs/benchmark/task-069-g12-form-investigation.md` §2).
PERTURBATION_QUANTILES: tuple[float, float] = (0.15, 0.25)
#: One bin (CONTRACT_VERSION >= 1.3.0): the *same step the legacy pair already encoded* — its own
#: half-width about its own anchor, `(0.25 - 0.15) / 2` — now measured from each candidate's own
#: threshold position instead of from a fixed anchor. The magnitude of the preregistered step is
#: deliberately unchanged by TASK-070; only its reference point was ever wrong.
PERTURBATION_PERCENTILE_STEP: float = (
    max(PERTURBATION_QUANTILES) - min(PERTURBATION_QUANTILES)
) / 2.0
MIN_STRATUM_CELL = 5

#: G06's adjustment pool is every `DECISION_TIME` feature except these two: both are calendar-date
#: strings, not usable as a stratification group without a separate binning design of their own,
#: and temporal effects already have a dedicated gate (G09, temporal stability) — excluding them
#: here is a disclosed scope limit, not an oversight (`docs/analytics/validation-contract.md` §4b).
#: A numeric column with this many or fewer distinct values in the development split is already
#: effectively categorical (e.g. `installments`, `party_size`) and is used as-is; only numeric
#: columns with more distinct values than this get quantile-binned.
ADJUSTMENT_NUMERIC_RAW_LEVELS_MAX = 6
#: Quartiles: enough resolution to separate a numeric confounder's groups without consuming more
#: degrees of freedom per covariate than a typical low-cardinality categorical feature does.
ADJUSTMENT_QUANTILE_BINS = 4


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


def load_analytical_frame(dataset_root: Path) -> pl.DataFrame:
    """Join the four manifest-verified, row-aligned analytical partitions."""
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
    return pl.concat([features, outcomes, identifiers, metadata], how="horizontal")


@dataclass(frozen=True, slots=True)
class ClusterCell:
    exposed_sum: float = 0.0
    exposed_n: int = 0
    comparison_sum: float = 0.0
    comparison_n: int = 0


def cluster_cells(
    frame: pl.DataFrame, mask: pl.Series, outcome_column: str, cluster_column: str
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
    """Bootstrap the exposed-minus-comparison mean while resampling clusters.

    `population` is built in sorted-key order, never raw dict/insertion order. `cells` is
    typically built by `cluster_cells()` from a Polars `group_by(...).agg(...)`, whose row order
    is not guaranteed run-to-run without `maintain_order=True` (which it does not set, for
    performance). Resampling by *index* (`rng.choices(population, k=len(population))`) with a
    fixed-seed `rng` is only reproducible if `population`'s element order is itself fixed — an
    unsorted dict-derived list silently broke that across otherwise-identical runs (`HANDOFF-047`:
    point estimates stayed byte-identical, since they sum over the whole population regardless of
    order, but bootstrap CIs and BH-adjusted p-values drifted run-to-run). Sorting here, at the one
    place resampling actually happens, fixes it regardless of how any caller's dict was built.
    """
    population = [cells[key] for key in sorted(cells)]
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


def _stratified_adjustment(
    frame: pl.DataFrame, mask: pl.Series, outcome: OutcomeDefinition, columns: tuple[str, ...]
) -> tuple[float, float]:
    """Exposure-weighted stratified effect, jointly cross-tabulated over `columns` (any count —
    despite the historical name, this was never actually limited to two). Returns
    `(adjusted_diff, coverage)`. Genuinely N-way joint stratification is combinatorially fragile as
    `columns` grows (`coverage` collapses toward 0 once strata get too small to clear
    `MIN_STRATUM_CELL` on both sides) — `_select_adjustment_columns` exists specifically to grow
    `columns` only as far as this function's own `coverage` output tolerates, not to work around a
    limitation in this function itself.
    """
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


def _adjustment_pool(
    eligible_features: frozenset[str], condition_features: frozenset[str]
) -> tuple[str, ...]:
    """Every `DECISION_TIME` feature eligible for G06 adjustment on one candidate: not one of the
    candidate's own conditions (adjusting for the treatment itself is circular). Sorted for a
    deterministic, auditable order independent of set iteration order — the actual selection
    order used by `_select_adjustment_columns` is by
    cardinality, computed separately; this is just the eligible pool.
    """
    return tuple(sorted(eligible_features - condition_features))


def _quantile_breakpoints(values: Sequence[float], bins: int) -> list[float]:
    """`bins - 1` cut points splitting `values` into `bins` roughly-equal-sized groups. Same
    index-based approach as `percentile_ci`/`baseline_statistics.numeric_summary` elsewhere in
    this codebase, not a new quantile convention.
    """
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return []
    return [ordered[min(n - 1, max(0, int(n * i / bins)))] for i in range(1, bins)]


def _binned_group_label(frame: pl.DataFrame, column: str) -> pl.Series | None:
    """A small-cardinality string label for `column`, or `None` if `column` should be used as-is
    (already categorical/boolean, or numeric with few enough distinct values that binning it would
    only throw away information — `installments`, `party_size`). Binning is quartile-based
    (`ADJUSTMENT_QUANTILE_BINS`) on `column`'s own present values, computed fresh from whatever
    frame is passed in (always the development split, at the call site) — never from a value
    learned about any specific candidate or feature identity.
    """
    if not frame.schema[column].is_numeric():
        return None
    values = [value for value in frame[column].to_list() if value is not None]
    if len({round(float(value), 9) for value in values}) <= ADJUSTMENT_NUMERIC_RAW_LEVELS_MAX:
        return None
    breakpoints = _quantile_breakpoints(values, ADJUSTMENT_QUANTILE_BINS)
    labels = [
        None if value is None else f"q{bisect.bisect_right(breakpoints, float(value))}"
        for value in frame[column].to_list()
    ]
    return pl.Series(column, labels)


def _binned_adjustment_frame(frame: pl.DataFrame, columns: tuple[str, ...]) -> pl.DataFrame:
    """`frame` with every high-cardinality numeric column in `columns` replaced by a quartile-bin
    label, so any eligible covariate — numeric or categorical — can be used as a stratification
    group by `_stratified_adjustment`. Columns not in `columns`, and columns that don't need
    binning, pass through unchanged.
    """
    result = frame
    for column in columns:
        label = _binned_group_label(frame, column)
        if label is not None:
            result = result.with_columns(label)
    return result


def _select_adjustment_columns(
    binned_frame: pl.DataFrame,
    mask: pl.Series,
    outcome: OutcomeDefinition,
    pool: tuple[str, ...],
    min_coverage: float,
) -> tuple[str, ...]:
    """Greedily grow the joint G06 stratification set from `pool` — the generalization of the old
    fixed two-column `CONFOUNDER_COLUMNS` to "every eligible covariate the sample can actually
    support" (`ADR-036`/`ADR-042`, `TASK-063`).

    Covariates are tried in ascending order of their own distinct-value count in `binned_frame`
    (ties broken alphabetically for determinism) — a dataset-level property fixed before any
    candidate is evaluated, not a per-candidate or per-feature-identity choice. Each covariate is
    added to the running joint stratification only if doing so keeps `_stratified_adjustment`'s
    `coverage` at or above `min_coverage`; a covariate that would push coverage below the floor is
    left out and the next one (in cardinality order) is tried instead — low-cardinality covariates
    are tried first because each additional covariate multiplies the number of joint strata by
    roughly its own cardinality, so trying cheap ones first lets more covariates fit before the
    sample runs out. No covariate is ever included or excluded because of what it *is* — only
    because of how much of the exposed group survives stratifying on it jointly with whatever is
    already selected.
    """
    ordering = sorted(pool, key=lambda column: (binned_frame[column].n_unique(), column))
    selected: list[str] = []
    for column in ordering:
        trial = (*selected, column)
        _, coverage = _stratified_adjustment(binned_frame, mask, outcome, trial)
        if coverage >= min_coverage:
            selected.append(column)
    return tuple(selected)


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
    frame: pl.DataFrame,
    candidate: dict[str, Any],
    outcome: OutcomeDefinition,
    inputs: ValidationInput,
    rng: random.Random,
    robustness_semantics: RobustnessSemantics = ROBUSTNESS_SEMANTICS_VERSION,
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

    non_decision_time = {
        feature
        for feature in condition_features
        if inputs.feature_roles.get(feature) is not FeatureRole.DECISION_TIME
    }
    gates[GateId.TARGET_LEAKAGE] = _gate(
        GateId.TARGET_LEAKAGE,
        not non_decision_time,
        "All condition features are DECISION_TIME."
        if not non_decision_time
        else f"Non-decision-time features: {sorted(non_decision_time)}",
    )

    adjustment_pool = _adjustment_pool(inputs.adjustment_features, condition_features)
    binned_dev_frame = _binned_adjustment_frame(dev_frame, adjustment_pool)
    adjustment_set = _select_adjustment_columns(
        binned_dev_frame,
        dev_mask,
        outcome,
        adjustment_pool,
        DEFAULT_THRESHOLDS.min_confounder_stratum_coverage,
    )
    diagnostics["adjustment_columns_considered"] = list(adjustment_pool)
    diagnostics["adjustment_columns_used"] = list(adjustment_set)
    gates[GateId.POST_TREATMENT] = _gate(
        GateId.POST_TREATMENT,
        True,
        f"Adjustment set {adjustment_set} is decision-time and excludes condition features.",
    )

    dev_clusters = cluster_cells(dev_frame, dev_mask, outcome.column, inputs.clustering_column)
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
        f"cluster_bootstrap_{inputs.clustering_column}",
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

    adjusted_diff, coverage = _stratified_adjustment(
        binned_dev_frame, dev_mask, outcome, adjustment_set
    )
    adjusted_harm = adjusted_diff * outcome.harm_multiplier
    attenuation = 1.0 - (adjusted_harm / dev.harm_per_booking if dev.harm_per_booking else 1.0)
    ev = e_value(adjusted_harm, dev.pooled_sd)
    diagnostics["adjusted_harm_per_booking"] = adjusted_harm
    diagnostics["confounder_stratum_coverage"] = coverage
    diagnostics["e_value"] = ev
    confounding_ok = (
        coverage >= DEFAULT_THRESHOLDS.min_confounder_stratum_coverage
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
    # G16_CANDIDATE_COMPOSITION_SAFETY (TASK-081, implementing TASK-080's design per ADR-078's
    # two-state, confound_like/composition_risk_indeterminate specification, §8.1/§15.3). Every
    # condition atom (full 1..k enumeration, no order-dependent exclusion) gets its own
    # leave-one-out check via the real, unmodified _stratified_adjustment above -- this is not a
    # new estimator, only a new caller of the existing one. Vacuous (satisfied) for k == 1.
    atom_masks: tuple[tuple[str, pl.Series], ...] = tuple(
        (condition.feature, dev_frame.select(condition_expr(condition).alias("m"))["m"])
        for condition in conditions
    )
    composition_result = classify_composition_safety(
        dev_frame, atom_masks, outcome, _stratified_adjustment, DEFAULT_THRESHOLDS
    )
    gates[GateId.COMPOSITION_SAFETY] = GateResult(
        gate_id=GateId.COMPOSITION_SAFETY,
        outcome=GateOutcome.PASS if composition_result.satisfied else GateOutcome.FAIL,
        detail=composition_result.detail,
    )
    diagnostics["composition_safety_reason"] = composition_result.reason.value
    diagnostics["composition_safety_atoms"] = [
        {
            "atom_index": atom.atom_index,
            "feature": atom.feature,
            "classification": atom.classification.value,
            "coverage": atom.coverage,
            "raw_base_effect": atom.raw_base_effect,
            "adjusted_effect": atom.adjusted_effect,
            "attenuation": atom.attenuation,
        }
        for atom in composition_result.atom_results
    ]

    shift = adjusted_harm - dev.harm_per_booking
    adjusted_effect = EffectEstimate(
        adjusted_harm,
        dev_effect.ci_low + shift,
        dev_effect.ci_high + shift,
        DEFAULT_THRESHOLDS.confidence_level,
        "stratified_generalized_adjustment",
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

    heterogeneity_column = inputs.heterogeneity_column
    if heterogeneity_column is None:
        diagnostics["segment_reversal_exposure_share"] = None
        gates[GateId.SIMPSON] = GateResult(
            gate_id=GateId.SIMPSON,
            outcome=GateOutcome.NOT_EVALUATED,
            detail="Manifest declares no reviewed heterogeneity role; G09 cannot be evaluated.",
        )
    else:
        seg_frame_grouped = dev_frame.select([heterogeneity_column, outcome.column]).with_columns(
            dev_mask.alias("_exposed")
        )
        seg_grouped = seg_frame_grouped.group_by([heterogeneity_column, "_exposed"]).agg(
            pl.col(outcome.column).sum().alias("_sum"), pl.col(outcome.column).count().alias("_n")
        )
        seg_cells: dict[str, dict[str, float]] = {}
        for row in seg_grouped.iter_rows(named=True):
            cell = seg_cells.setdefault(
                str(row[heterogeneity_column]), {"es": 0.0, "en": 0, "cs": 0.0, "cn": 0}
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
            f"Sign reverses in {heterogeneity_column} strata covering {reversal_share:.1%} of "
            f"exposure (threshold {DEFAULT_THRESHOLDS.simpson_reversal_exposure_share:.0%}).",
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

    seasonality_column = inputs.seasonality_column
    if seasonality_column is None:
        diagnostics["seasonal_concentration_index"] = None
        gates[GateId.SEASONALITY] = GateResult(
            gate_id=GateId.SEASONALITY,
            outcome=GateOutcome.NOT_EVALUATED,
            detail="Manifest declares no reviewed seasonality role; G11 cannot be evaluated.",
        )
    else:
        seasonal_frame = dev_frame.with_columns(
            pl.col(seasonality_column)
            .cast(pl.String)
            .str.slice(5, 2)
            .cast(pl.Int64)
            .alias("_month")
        )
        month_cohort = seasonal_frame.group_by("_month").agg(pl.len().alias("n"))
        month_exposed = seasonal_frame.filter(dev_mask).group_by("_month").agg(pl.len().alias("n"))  # pyright: ignore[reportUnknownMemberType]
        cohort_by_month = dict(
            zip(month_cohort["_month"].to_list(), month_cohort["n"].to_list(), strict=True)
        )
        exposed_by_month = dict(
            zip(month_exposed["_month"].to_list(), month_exposed["n"].to_list(), strict=True)
        )
        total_cohort_n = sum(cohort_by_month.values())
        total_exposed_n = sum(exposed_by_month.values())
        concentration = (
            max(
                (exposed_by_month.get(month, 0) / total_exposed_n)
                / (cohort_by_month[month] / total_cohort_n)
                for month in cohort_by_month
            )
            if total_exposed_n and total_cohort_n
            else 1.0
        )
        diagnostics["seasonal_concentration_index"] = concentration
        gates[GateId.SEASONALITY] = _gate(
            GateId.SEASONALITY,
            concentration <= DEFAULT_THRESHOLDS.seasonal_concentration_index,
            f"Max monthly exposure/cohort concentration ratio {concentration:.2f} "
            f"(threshold {DEFAULT_THRESHOLDS.seasonal_concentration_index}).",
        )

    battery = _robustness_battery(
        dev_frame, conditions, dev_mask, outcome, dev, inputs, robustness_semantics
    )
    sign_agree = battery.sign_agreement
    magnitude_dev_max = battery.max_magnitude_deviation
    checks_run = battery.checks_run
    diagnostics["robustness_sign_agreement"] = sign_agree
    diagnostics["robustness_max_magnitude_deviation"] = magnitude_dev_max
    diagnostics["robustness_checks_run"] = checks_run
    diagnostics["robustness_not_evaluated_reason"] = battery.not_evaluated_reason
    diagnostics.update(battery.diagnostics)
    if not battery.evaluated:
        # Never a silent pass and never a silent fail: an unanswerable robustness question is
        # disclosed as unanswered, with the reason in the gate's own detail. NOT_EVALUATED is
        # treated exactly like FAIL for grading (validation-contract §3) — it caps evidence — but
        # a reader can tell "this effect moved when we perturbed the cutoff" apart from "this
        # column has no cutoff to perturb".
        gates[GateId.ROBUSTNESS] = GateResult(
            gate_id=GateId.ROBUSTNESS,
            outcome=GateOutcome.NOT_EVALUATED,
            detail=cast(str, battery.not_evaluated_reason),
        )
    else:
        robustness_ok = (
            sign_agree >= DEFAULT_THRESHOLDS.min_robustness_sign_agreement
            and magnitude_dev_max <= DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation
        )
        alternative_note = (
            ""
            if battery.diagnostics["robustness_alternative_outcome_diagnostic"] is None
            else (
                " Declared alternative outcome "
                f"{inputs.alternative_outcome_id!r} is "
                f"{battery.diagnostics['robustness_alternative_outcome_admissibility']} and is "
                "reported as a decomposition diagnostic, not counted here."
            )
        )
        # The refit-state breakdown is a v1.3.0 concept; under the superseded semantics it is
        # uniformly zero and would only mislead, so it is omitted there rather than printed empty.
        refit_note = (
            ""
            if robustness_semantics is RobustnessSemantics.FIXED_QUANTILE_V1
            else (
                "; threshold refit states "
                f"{battery.diagnostics['robustness_threshold_refit_states']}"
            )
        )
        gates[GateId.ROBUSTNESS] = _gate(
            GateId.ROBUSTNESS,
            robustness_ok,
            f"Sign agreement {sign_agree:.0%} over {checks_run} perturbations "
            f"(floor {DEFAULT_THRESHOLDS.min_robustness_sign_agreement:.0%}); max magnitude "
            f"deviation {magnitude_dev_max:.0%} "
            f"(ceiling {DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation:.0%}); "
            f"semantics {battery.diagnostics['robustness_semantics_version']}"
            f"{refit_note}.{alternative_note}",
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
    combined_clusters = cluster_cells(
        frame, combined_mask, outcome.column, inputs.clustering_column
    )
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


def alternative_outcome_admissibility(
    primary: OutcomeDefinition, alternative: OutcomeDefinition | None
) -> AlternativeOutcomeAdmissibility:
    """May `alternative` bind G12's magnitude-parity refit against `primary`? (v1.3.0, TASK-070.)

    G12 asks whether an effect survives a *different definition of the same outcome*. That question
    only has an answer when the two outcomes are commensurable measurements of one construct. Three
    mechanical disqualifications, checked in this fixed order so a candidate always gets one
    deterministic reason:

    1. **Decomposition.** Either outcome declared ``decomposition_of`` the other, or both
       decompositions of a common parent. A total and one of its own accounting components cannot
       agree in magnitude unless the remaining components are exactly zero, so the deviation such a
       refit reports is the component's share of the effect — an identity about outcome algebra,
       with no stability content whatsoever. `TASK-069` item 2 quantified this on the travel
       benchmark (measured deviation reproduced the ground truth's own component ratio to within
       1.6 points for every pattern with a non-zero component effect) *and* reproduced it truth-free
       on invented two-channel synthetic data (99.9% deviation against a 50% ceiling for an effect
       that is maximally stable by construction).
    2. **Unit.** Magnitude parity across units is meaningless: requiring a rate effect to sit within
       +/-50% of a EUR effect measures the two outcomes' scales, not the pattern. The test is exact
       equality of the reviewed ``unit`` strings — deliberately mechanical and deliberately
       conservative. A cosmetically different unit string on a genuinely commensurable outcome
       yields the *disclosed* inadmissible state and a recorded diagnostic, never a wrong verdict.
    3. **Missingness.** An ``MNAR_BOUNDED`` outcome has no reportable complete-case estimate at all
       (gate G07 requires bounds for it), so a complete-case refit against one is not a robustness
       measurement.

    This function reads only the reviewed ``OutcomeDefinition`` registry. It never looks at a
    candidate, an effect, a dataset value, or a pattern identity, and its answer is therefore a
    property of the outcome contract alone — fixed before any candidate is evaluated.
    """
    if alternative is None:
        return AlternativeOutcomeAdmissibility.NOT_DECLARED
    shared_parent = (
        primary.decomposition_of is not None
        and primary.decomposition_of == alternative.decomposition_of
    )
    if (
        alternative.decomposition_of == primary.outcome_id
        or primary.decomposition_of == alternative.outcome_id
        or shared_parent
    ):
        return AlternativeOutcomeAdmissibility.INADMISSIBLE_DECOMPOSITION
    if alternative.unit != primary.unit:
        return AlternativeOutcomeAdmissibility.INADMISSIBLE_UNIT_MISMATCH
    if alternative.missing_data_policy is not primary.missing_data_policy or (
        alternative.missing_data_policy is not MissingDataPolicy.COMPLETE
    ):
        return AlternativeOutcomeAdmissibility.INADMISSIBLE_MISSINGNESS_POLICY
    return AlternativeOutcomeAdmissibility.ADMISSIBLE


def _threshold_percentile(column: pl.Series, value: float) -> float:
    """Where a threshold sits in its own column: the share of present rows strictly below it."""
    below_share = cast(Any, (column < value).mean())
    return 0.0 if below_share is None else float(cast(float, below_share))


def _adjacent_level(levels: Sequence[float], value: float, direction: int) -> float | None:
    """The next distinct value of a column below (`direction < 0`) or above (`direction > 0`).

    `levels` is the column's own sorted distinct present values, so this is that column's true
    one-bin move: the smallest threshold change its resolution can actually express. Returns
    ``None`` at the ends of the column, where no such move exists.
    """
    if direction < 0:
        below = [level for level in levels if level < value]
        return below[-1] if below else None
    above = [level for level in levels if level > value]
    return above[0] if above else None


class _ThresholdRefit(NamedTuple):
    state: RobustnessRefitState
    perturbed_value: float | None
    snapped_to_adjacent_level: bool
    stats: SplitStats | None


def _one_bin_threshold_refit(
    dev_frame: pl.DataFrame,
    conditions: tuple[Condition, ...],
    condition: Condition,
    outcome: OutcomeDefinition,
    own_percentile: float,
    levels: Sequence[float],
    direction: int,
) -> _ThresholdRefit:
    """One one-bin perturbation of one numeric threshold, in one direction (v1.3.0, TASK-070).

    The target is the candidate's own threshold percentile shifted by
    ``PERTURBATION_PERCENTILE_STEP``; the perturbed threshold is the column's own nearest realised
    value at that target. When the column's resolution is too coarse for the step to move the
    threshold at all — a count-like integer column, where the old fixed grid silently produced no
    estimate — the perturbation snaps to the adjacent distinct level, which *is* one bin for that
    column. Every way this can fail to produce a usable refit has its own named state; none of them
    is silently folded into the gate's aggregates.
    """
    value = float(cast(float, condition.value))
    column = dev_frame[condition.feature]
    target = own_percentile + direction * PERTURBATION_PERCENTILE_STEP
    perturbed_value: float | None = None
    if 0.0 < target < 1.0:
        at_target = column.quantile(target, interpolation="nearest")
        if at_target is not None:
            perturbed_value = round(float(at_target), 8)
    snapped = False
    if perturbed_value is None or perturbed_value == round(value, 8):
        adjacent = _adjacent_level(levels, value, direction)
        if adjacent is None:
            return _ThresholdRefit(RobustnessRefitState.UNREPRESENTABLE_STEP, None, False, None)
        perturbed_value = round(float(adjacent), 8)
        snapped = True
    if perturbed_value == round(value, 8):
        return _ThresholdRefit(
            RobustnessRefitState.VACUOUS_IDENTICAL_RULE, perturbed_value, snapped, None
        )
    perturbed = tuple(
        Condition(c.feature, c.operator, perturbed_value) if c is condition else c
        for c in conditions
    )
    pmask = dev_frame.select(rule_expr(perturbed).alias("m"))["m"]
    stats = split_stats(dev_frame, pmask, outcome, "development")
    if stats is None:
        return _ThresholdRefit(
            RobustnessRefitState.DEGENERATE_NO_CONTRAST, perturbed_value, snapped, None
        )
    return _ThresholdRefit(RobustnessRefitState.ESTIMATED, perturbed_value, snapped, stats)


class RobustnessBattery(NamedTuple):
    """G12's aggregates plus the disclosed state behind them.

    A ``NamedTuple`` on purpose: the first three fields are positionally identical to the
    ``(sign_agreement, max_magnitude_deviation, checks_run)`` tuple this function returned through
    v1.2.0, so existing diagnostic callers keep working unchanged.
    """

    sign_agreement: float
    max_magnitude_deviation: float
    checks_run: int
    evaluated: bool
    not_evaluated_reason: str | None
    diagnostics: dict[str, Any]


def _robustness_battery(
    dev_frame: pl.DataFrame,
    conditions: tuple[Condition, ...],
    dev_mask: pl.Series,
    outcome: OutcomeDefinition,
    dev: SplitStats,
    inputs: ValidationInput,
    semantics: RobustnessSemantics = ROBUSTNESS_SEMANTICS_VERSION,
) -> RobustnessBattery:
    """G12's four refit families.

    ``semantics`` selects which contract version's behaviour to run: ``FIXED_QUANTILE_V1`` is
    exactly what shipped through v1.2.0 (kept executable so frozen runs stay reproducible under
    their own recorded version), ``ONE_BIN_RELATIVE_V2`` is v1.3.0's corrected behaviour and is
    what every new run uses. Only the threshold-perturbation and alternative-outcome families
    differ between them — leave-one-cluster-out and winsorisation are byte-identical under both,
    including their treatment of a refit that produces no estimate, which for those two families is
    a genuine fragility signal rather than an artifact of the perturbation grid.
    """
    legacy = semantics is RobustnessSemantics.FIXED_QUANTILE_V1
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

    if inputs.robustness_group_column is not None:
        group_column = inputs.robustness_group_column
        for group_value in dev_frame[group_column].unique().to_list():
            subset = dev_frame.filter(pl.col(group_column) != group_value)  # pyright: ignore[reportUnknownMemberType]
            submask = subset.select(rule_expr(conditions).alias("m"))["m"]
            _record(split_stats(subset, submask, outcome, "development"))

    low, high = dev_frame[outcome.column].quantile(0.01), dev_frame[outcome.column].quantile(0.99)
    winsor_frame = dev_frame.with_columns(
        pl.col(outcome.column).clip(cast(float, low), cast(float, high))
    )
    _record(split_stats(winsor_frame, dev_mask, outcome, "development"))

    alt_outcome: OutcomeDefinition | None = None
    if inputs.alternative_outcome_id is not None:
        alt_outcome = OUTCOME_BY_ID.get(inputs.alternative_outcome_id)
        if alt_outcome is None:
            raise ValueError(
                f"no reviewed OutcomeDefinition for alternative outcome "
                f"{inputs.alternative_outcome_id!r}"
            )
    admissibility = (
        AlternativeOutcomeAdmissibility.ADMISSIBLE
        if legacy and alt_outcome is not None
        else alternative_outcome_admissibility(outcome, alt_outcome)
    )
    alt_diagnostic: dict[str, Any] | None = None
    if alt_outcome is not None:
        alt_stats = split_stats(dev_frame, dev_mask, alt_outcome, "development")
        if admissibility is AlternativeOutcomeAdmissibility.ADMISSIBLE:
            _record(alt_stats)
        else:
            # Never silently dropped: the refit is still estimated and reported, it simply does not
            # bind the gate. Whoever reads the finding sees the number *and* why it is not evidence.
            ratio = (
                abs(alt_stats.harm_per_booking / dev.harm_per_booking)
                if alt_stats is not None and dev.harm_per_booking
                else None
            )
            alt_diagnostic = {
                "outcome_id": alt_outcome.outcome_id,
                "admissibility": admissibility.value,
                "harm_per_booking": (
                    None if alt_stats is None else round(alt_stats.harm_per_booking, 6)
                ),
                "magnitude_deviation": None if ratio is None else round(abs(ratio - 1.0), 6),
                "sign_agrees": (
                    None
                    if alt_stats is None or not dev.harm_per_booking
                    else (alt_stats.harm_per_booking > 0) == (dev.harm_per_booking > 0)
                ),
                "note": (
                    "Recorded as a disclosed decomposition diagnostic, not as a G12 refit: this "
                    "outcome is not a commensurable measurement of the primary construct, so a "
                    "magnitude-parity requirement against it reports outcome algebra rather than "
                    "the effect's stability (CONTRACT_VERSION >= 1.3.0, TASK-070)."
                ),
            }

    refit_states: dict[str, int] = {state.value: 0 for state in RobustnessRefitState}
    threshold_refits: list[dict[str, Any]] = []
    unevaluable_conditions: list[str] = []
    for condition in conditions:
        if not isinstance(condition.value, int | float) or isinstance(condition.value, bool):
            continue
        column = dev_frame[condition.feature]
        if legacy:
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
            continue
        own_percentile = _threshold_percentile(column, float(cast(float, condition.value)))
        levels = sorted(
            {
                round(float(cast(float, level)), 8)
                for level in column.unique().to_list()
                if level is not None
            }
        )
        estimated_here = 0
        for direction in (-1, 1):
            refit = _one_bin_threshold_refit(
                dev_frame, conditions, condition, outcome, own_percentile, levels, direction
            )
            refit_states[refit.state.value] += 1
            threshold_refits.append(
                {
                    "condition": f"{condition.feature} {condition.operator} {condition.value}",
                    "threshold_percentile": round(own_percentile, 6),
                    "direction": "one_bin_below" if direction < 0 else "one_bin_above",
                    "perturbed_value": refit.perturbed_value,
                    "snapped_to_adjacent_level": refit.snapped_to_adjacent_level,
                    "state": refit.state.value,
                    "harm_per_booking": (
                        None if refit.stats is None else round(refit.stats.harm_per_booking, 6)
                    ),
                    "n_exposed": None if refit.stats is None else refit.stats.n_exposed,
                }
            )
            if refit.state is RobustnessRefitState.ESTIMATED:
                estimated_here += 1
                _record(refit.stats)
        if estimated_here == 0:
            unevaluable_conditions.append(
                f"{condition.feature} {condition.operator} {condition.value}"
            )

    sign_agreement = sign_agree / checks_run if checks_run else 0.0
    max_magnitude_deviation = max((abs(r - 1.0) for r in magnitude_ratios), default=1.0)
    diagnostics: dict[str, Any] = {
        "robustness_semantics_version": semantics.value,
        "robustness_alternative_outcome_admissibility": admissibility.value,
        "robustness_alternative_outcome_diagnostic": alt_diagnostic,
        "robustness_threshold_refit_states": refit_states,
        "robustness_threshold_refits": threshold_refits,
    }
    reason: str | None = None
    if checks_run == 0:
        reason = "No robustness refit of any family could be estimated for this candidate."
    elif unevaluable_conditions:
        reason = (
            "No one-bin threshold perturbation could be estimated for numeric condition(s) "
            f"{unevaluable_conditions}: the column's own resolution cannot express a step away "
            "from this threshold that leaves a comparison group. G12 cannot answer whether the "
            "effect depends on that cutoff, so it is not evaluated rather than passed or failed."
        )
    return RobustnessBattery(
        sign_agreement=sign_agreement,
        max_magnitude_deviation=max_magnitude_deviation,
        checks_run=checks_run,
        evaluated=reason is None,
        not_evaluated_reason=reason,
        diagnostics=diagnostics,
    )


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


def _robustness_test_names(inputs: ValidationInput, diagnostics: dict[str, Any]) -> tuple[str, ...]:
    """The G12 refits this candidate actually ran, named so the frozen report discloses the states.

    A declared-but-inadmissible alternative outcome appears with its admissibility spelled out, so
    a reader of the report alone can tell a refit that bound the gate from one that was recorded as
    a decomposition diagnostic — the state is evidence-level-visible, not buried in a diagnostics
    blob (CONTRACT_VERSION >= 1.3.0, TASK-070).
    """
    semantics = cast(str, diagnostics.get("robustness_semantics_version", ""))
    alternative: tuple[str, ...] = ()
    if inputs.alternative_outcome_id is not None:
        admissibility = cast(
            str, diagnostics.get("robustness_alternative_outcome_admissibility", "")
        )
        alternative = (
            (f"alternative_outcome_{inputs.alternative_outcome_id}",)
            if admissibility == AlternativeOutcomeAdmissibility.ADMISSIBLE.value
            else (
                f"alternative_outcome_{inputs.alternative_outcome_id}_"
                f"not_gate_binding_{admissibility}",
            )
        )
    return (
        *(
            (f"leave_one_{inputs.robustness_group_column}_out",)
            if inputs.robustness_group_column
            else ()
        ),
        "winsorize_top_bottom_1pct",
        *alternative,
        f"numeric_threshold_perturbation_{semantics}",
    )


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
    robustness_semantics: RobustnessSemantics = ROBUSTNESS_SEMANTICS_VERSION,
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
    inputs = validation_input_from_manifest(dataset_root)
    if inputs.dataset_version != dataset_version:
        raise ValueError(
            f"manifest dataset_version {inputs.dataset_version!r} conflicts with validation input "
            f"{dataset_version!r}"
        )
    family_size = _evaluated_hypotheses(payload, metrics_path)
    raw_candidates = payload["candidates"]
    if not isinstance(raw_candidates, list):
        raise ValueError("candidates payload must contain a candidates list")
    candidates: list[dict[str, Any]] = []
    for raw_candidate in cast(list[object], raw_candidates):
        if not isinstance(raw_candidate, dict):
            raise ValueError("candidates payload must contain candidate objects")
        candidates.append(cast(dict[str, Any], raw_candidate))
    validate_candidate_fields(candidates, inputs)

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
        _validate_one(frame, candidate, outcome, inputs, rng, robustness_semantics)
        for candidate in candidates
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
                clustering_key=inputs.clustering_column,
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
            clustering_key=inputs.clustering_column,
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
            potential_confounders=tuple(sorted(inputs.adjustment_features)),
            robustness_tests=_robustness_test_names(inputs, interim.diagnostics),
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
        # CONTRACT_VERSION >= 1.2.0: the adjustment set is per-candidate, not a fixed run-level
        # pair (ADR-036/ADR-042) — this is the full eligible pool before any candidate's own
        # conditions are excluded from it; each candidate's actually-used subset is in its own
        # diagnostics ("adjustment_columns_considered"/"adjustment_columns_used").
        "adjustment_pool_all_decision_time_features": sorted(inputs.adjustment_features),
        "heterogeneity_column": inputs.heterogeneity_column,
        "seasonality_column": inputs.seasonality_column,
        "clustering_column": inputs.clustering_column,
        # CONTRACT_VERSION >= 1.3.0 (ADR-064, TASK-070): which G12 robustness semantics graded this
        # run. Recorded at run level because it is the one thing that makes an older frozen run
        # reproducible — re-running with this value reproduces that run's verdicts exactly.
        "robustness_semantics_version": robustness_semantics.value,
        "alternative_outcome_id": inputs.alternative_outcome_id,
    }
    return results, manifest
