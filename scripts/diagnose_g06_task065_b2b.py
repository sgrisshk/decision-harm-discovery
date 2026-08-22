"""POST-HOC DIAGNOSTIC (`TASK-067`): per-candidate mechanistic trace of why gate G06 downgraded
every one of `task-065-b2b-comparable-20260822-001`'s 15 frozen candidates.

Not part of the official discovery/blind/validation pipeline. Never runs as part of an official
blind run and never influences one. It re-derives, from already-frozen inputs, exactly the same
G06 computation `apply.py::_validate_one` already performed and already froze into
`artifacts/validation/task-019-task-065-b2b-comparable-20260822-001.json` — plus several
*intermediate* numbers that computation discards internally (which pool covariate was tried at
each step of the greedy selection and why it was kept or skipped, cell-level strata counts behind
the reported `confounder_stratum_coverage`, an unrestricted/interaction-preserving joint
stratification ignoring the coverage floor, and a Frisch-Waugh-Lovell-style additive/main-effects
comparison — the same diagnostic shape `ADR-043` used for travel's own residual G06 case). Every
number this script prints is a **POST-HOC DIAGNOSTIC**: it is not a new official `TASK-019` run,
does not change any frozen artifact, threshold, or gate, and must never be substituted for the
frozen `task-019`/`task-028` metrics in `docs/benchmark/decision-gate.md` or anywhere else.

**Why this is legitimate now:** `b2b_sales/comparable` hidden ground truth was already legitimately
opened once, after candidate commitment, by the independent `TASK-028` evaluator
(`memory/HANDOFFS.md` HANDOFF-067's `CUSTODY_VERIFIED`/evaluator-completion record) — the same
"already frozen, now graded" discipline `docs/benchmark/blind-benchmark-protocol.md` and
`ADR-025`/`HANDOFF-054`/`ADR-038` already established for post-hoc diagnostics on other committed
runs (`scripts/diagnose_candidate_pool_recall.py` is the direct precedent this script follows in
shape and discipline). `ADR-054` (Founder Strategy) explicitly states that "diagnostic reading of
the frozen b2b artifacts to understand the failure mechanism is permitted and required" for
`TASK-067`, while forbidding any method change scoped or justified by `b2b_sales`'s *specific*
pattern/trap identity.

**Deliberate scope boundary, disclosed rather than silently worked around:** this script does
**not** open `synthetic_data_domains/b2b_sales/comparable/evaluation/hidden_ground_truth.json`.
When this diagnostic was being built, an attempt to read that file's contents was declined by this
environment's own tool-use permission system (a classifier-level denial on that specific path, not
a project-policy decision) — and, separately, using a different tool to read the identical content
would defeat the evident intent of that denial, so no such attempt was made. This turned out not to
cost anything: every finding below is derived entirely from already-public artifacts (the frozen
candidate file, the frozen `TASK-019` validation report, and the public b2b analytical dataset) and
from `apply.py`'s real, unmodified, read-only-called functions. Nothing here depends on which real
pattern or trap any candidate corresponds to.

**Discipline maintained:** this script imports and calls `policy_analytics.validation.apply`'s
private functions verbatim (`_adjustment_pool`, `_binned_adjustment_frame`,
`_select_adjustment_columns`, `_stratified_adjustment`) rather than reimplementing them, so every
number it reports is guaranteed to use the exact same logic the frozen `TASK-019` report used — the
only new code here is *tracing* (recording intermediate state the production call site doesn't
keep) and two exploratory-only comparison methods (unrestricted joint stratification, additive FWL)
that mirror `ADR-043`'s own already-precedented diagnostic technique. No line of this script
references any `b2b_sales` pattern or trap identity.

Usage:
  uv run python scripts/diagnose_g06_task065_b2b.py
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402

from policy_analytics.outcomes.contract import OutcomeDefinition  # noqa: E402
from policy_analytics.outcomes.manifest_binding import outcome_definition_from_manifest  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    Condition,
    MIN_STRATUM_CELL,
    _adjustment_pool,
    _binned_adjustment_frame,
    _select_adjustment_columns,
    _stratified_adjustment,
    load_analytical_frame,
    rule_expr,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS  # noqa: E402
from policy_analytics.validation.input_contract import validation_input_from_manifest  # noqa: E402

DATASET_ROOT = REPOSITORY / "synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0"
CANDIDATES_PATH = REPOSITORY / "artifacts/blind/task-065-b2b-comparable-20260822-001.candidates.json"
FROZEN_VALIDATION_PATH = (
    REPOSITORY / "artifacts/validation/task-019-task-065-b2b-comparable-20260822-001.json"
)
EXPECTED_CANDIDATE_SHA256 = "ec3b1c17c9826724dfaa6adec1a1db431768bad772b228d33cf906be6ab49bcc"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cell_stats(
    frame: pl.DataFrame, mask: pl.Series, outcome_column: str, columns: tuple[str, ...]
) -> dict[str, Any]:
    """Re-derive the exact cell partition `_stratified_adjustment` builds internally, plus the
    counts it discards after computing `coverage`. Read-only duplication of that function's own
    group-by, not a change to it — kept local so the diagnostic can see cell-level detail the
    production return value (`(adjusted_diff, coverage)`) does not expose."""
    if not columns:
        return {
            "n_groups": 1,
            "n_usable": 1,
            "n_exposed_only": 0,
            "n_comparison_only": 0,
            "n_both_below_floor": 0,
            "total_exposed_all": int(mask.sum()),
            "total_exposed_usable": int(mask.sum()),
        }
    working = frame.select([*columns, outcome_column]).with_columns(mask.alias("_exposed"))
    grouped = working.group_by([*columns, "_exposed"]).agg(
        pl.col(outcome_column).count().alias("_n")
    )
    cells: dict[tuple[Any, ...], dict[str, int]] = {}
    for row in grouped.iter_rows(named=True):
        key = tuple(row[c] for c in columns)
        cell = cells.setdefault(key, {"en": 0, "cn": 0})
        if row["_exposed"]:
            cell["en"] += row["_n"]
        else:
            cell["cn"] += row["_n"]
    n_usable = sum(
        1 for c in cells.values() if c["en"] >= MIN_STRATUM_CELL and c["cn"] >= MIN_STRATUM_CELL
    )
    n_exposed_only = sum(1 for c in cells.values() if c["en"] > 0 and c["cn"] == 0)
    n_comparison_only = sum(1 for c in cells.values() if c["cn"] > 0 and c["en"] == 0)
    n_both_below_floor = sum(
        1
        for c in cells.values()
        if c["en"] > 0
        and c["cn"] > 0
        and (c["en"] < MIN_STRATUM_CELL or c["cn"] < MIN_STRATUM_CELL)
    )
    total_exposed_all = sum(c["en"] for c in cells.values())
    total_exposed_usable = sum(
        c["en"] for c in cells.values() if c["en"] >= MIN_STRATUM_CELL and c["cn"] >= MIN_STRATUM_CELL
    )
    return {
        "n_groups": len(cells),
        "n_usable": n_usable,
        "n_exposed_only": n_exposed_only,
        "n_comparison_only": n_comparison_only,
        "n_both_below_floor": n_both_below_floor,
        "total_exposed_all": total_exposed_all,
        "total_exposed_usable": total_exposed_usable,
    }


def _greedy_trace(
    binned_frame: pl.DataFrame,
    mask: pl.Series,
    outcome: OutcomeDefinition,
    pool: tuple[str, ...],
    min_coverage: float,
) -> list[dict[str, Any]]:
    """Re-derive `_select_adjustment_columns`'s exact ascending-cardinality ordering and, for every
    pool covariate in that order, record whether it was kept and the trial coverage that decided
    it -- the production function only returns the final selected tuple, discarding this trace."""
    ordering = sorted(pool, key=lambda column: (binned_frame[column].n_unique(), column))
    selected: list[str] = []
    trace: list[dict[str, Any]] = []
    for column in ordering:
        trial = (*selected, column)
        _, coverage = _stratified_adjustment(binned_frame, mask, outcome, trial)
        kept = coverage >= min_coverage
        trace.append(
            {
                "covariate": column,
                "n_unique_in_dev": binned_frame[column].n_unique(),
                "trial_coverage_if_added": coverage,
                "kept": kept,
            }
        )
        if kept:
            selected.append(column)
    assert tuple(selected) == tuple(
        c["covariate"] for c in trace if c["kept"]
    )  # internal consistency only
    return trace


def _fwl_additive_coefficient(
    frame: pl.DataFrame, mask: pl.Series, outcome_column: str, columns: tuple[str, ...],
    max_iter: int = 200, tol: float = 1e-10,
) -> tuple[float, int]:
    """Frisch-Waugh-Lovell partialling-out: the additive (main-effects-only) multivariate
    regression coefficient of `mask` (treatment indicator) on `outcome_column`, controlling for
    every column in `columns` as a fixed effect, via iterative alternating group-demeaning of both
    variables until convergence. Same technique `ADR-043` used for travel's own residual G06 case
    (there: harm 157.2 -> 158.9 EUR additive vs. 47.7 EUR fully joint-stratified). Returns
    `(coefficient, iterations)`. Diagnostic-only; not a new production estimator."""
    y = frame[outcome_column].to_numpy().astype(float).copy()
    t = mask.to_numpy().astype(float).copy()
    if not columns:
        # No covariates: the additive "coefficient" is just the raw mean difference.
        exposed = y[t == 1]
        comparison = y[t == 0]
        return float(exposed.mean() - comparison.mean()), 0
    group_arrays = [frame[c].to_numpy() for c in columns]
    for iteration in range(1, max_iter + 1):
        max_shift = 0.0
        for group in group_arrays:
            for series in (y, t):
                # demean series within each level of this group column
                keys = group
                sums: dict[Any, float] = {}
                counts: dict[Any, int] = {}
                for k, v in zip(keys, series, strict=True):
                    sums[k] = sums.get(k, 0.0) + v
                    counts[k] = counts.get(k, 0) + 1
                means = {k: sums[k] / counts[k] for k in sums}
                before = series.copy()
                for i, k in enumerate(keys):
                    series[i] -= means[k]
                shift = float(abs(series - before).max()) if len(series) else 0.0
                max_shift = max(max_shift, shift)
        if max_shift < tol:
            break
    var_t = float((t * t).sum())
    if var_t == 0:
        return 0.0, iteration
    coefficient = float((t * y).sum() / var_t)
    return coefficient, iteration


def _eta_squared(frame: pl.DataFrame, numeric_column: str, group_column: str) -> float:
    """Correlation ratio (eta^2): the share of `numeric_column`'s variance explained by
    `group_column` membership, computed on the development split alone. 0 = no relationship,
    1 = `group_column` fully determines `numeric_column`. A dataset-level, public-data-only
    collinearity check -- not per-candidate, not dependent on any candidate's condition."""
    values = frame[numeric_column].to_numpy().astype(float)
    groups = frame[group_column].to_numpy()
    grand_mean = float(values.mean())
    ss_total = float(((values - grand_mean) ** 2).sum())
    if ss_total == 0:
        return 0.0
    ss_between = 0.0
    for level in set(groups.tolist()):
        subset = values[groups == level]
        if len(subset) == 0:
            continue
        ss_between += len(subset) * (float(subset.mean()) - grand_mean) ** 2
    return ss_between / ss_total


def main() -> None:
    actual_sha = _sha256(CANDIDATES_PATH)
    print(f"Candidate file: {CANDIDATES_PATH}")
    print(f"  SHA-256 (recomputed): {actual_sha}")
    print(f"  Matches HANDOFF-067 CUSTODY_VERIFIED record: {actual_sha == EXPECTED_CANDIDATE_SHA256}")
    if actual_sha != EXPECTED_CANDIDATE_SHA256:
        raise SystemExit("candidate file does not match the frozen custody record -- aborting")

    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    raw_candidates = cast(list[dict[str, Any]], payload["candidates"])

    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    outcome, outcome_contract_version = outcome_definition_from_manifest(manifest, DATASET_ROOT)
    inputs = validation_input_from_manifest(DATASET_ROOT)
    frame = load_analytical_frame(DATASET_ROOT)
    dev_frame = frame.filter(frame["split_label"] == "development")

    print(f"\nDataset: {DATASET_ROOT}")
    print(f"  dataset_identity_sha256: {inputs.dataset_identity_sha256}")
    print(f"  outcome: {outcome.outcome_id} ({outcome_contract_version}); "
          f"harm_multiplier={outcome.harm_multiplier}")
    print(f"  development rows: {dev_frame.height}")
    print(f"  adjustment-eligible pool (manifest-wide): {sorted(inputs.adjustment_features)}")

    # Dataset-level, public-data-only collinearity check (not per-candidate).
    eta_sq_company_on_deal = _eta_squared(dev_frame, "deal_size_usd", "company_size_band")
    print(f"\nDataset-level collinearity check (development split, public data only):")
    print(f"  eta^2(deal_size_usd | company_size_band) = {eta_sq_company_on_deal:.4f}")
    band_stats = (
        dev_frame.group_by("company_size_band")
        .agg(
            pl.col("deal_size_usd").min().alias("min"),
            pl.col("deal_size_usd").max().alias("max"),
            pl.col("deal_size_usd").mean().alias("mean"),
            pl.len().alias("n"),
        )
        .sort("mean")
    )
    print(band_stats)

    results: list[dict[str, Any]] = []
    for raw in raw_candidates:
        candidate_id = raw["candidate_id"]
        conditions = tuple(
            Condition(c["feature"], c["operator"], c["value"]) for c in raw["conditions"]
        )
        condition_features = frozenset(c.feature for c in conditions)
        full_mask = frame.select(rule_expr(conditions).alias("m"))["m"]
        dev_mask = full_mask.filter(frame["split_label"] == "development")

        pool = _adjustment_pool(inputs.adjustment_features, condition_features)
        binned = _binned_adjustment_frame(dev_frame, pool)
        trace = _greedy_trace(
            binned, dev_mask, outcome, pool, DEFAULT_THRESHOLDS.min_confounder_stratum_coverage
        )
        selected = tuple(t["covariate"] for t in trace if t["kept"])
        skipped = [t for t in trace if not t["kept"]]

        raw_diff, _ = _stratified_adjustment(binned, dev_mask, outcome, ())
        raw_harm = raw_diff * outcome.harm_multiplier
        adj_diff, coverage = _stratified_adjustment(binned, dev_mask, outcome, selected)
        adjusted_harm = adj_diff * outcome.harm_multiplier
        attenuation = 1.0 - (adjusted_harm / raw_harm if raw_harm else 1.0)
        same_sign = (adjusted_harm > 0) == (raw_harm > 0)
        cells = _cell_stats(binned, dev_mask, outcome.column, selected)

        # Unrestricted joint stratification: full pool, ignore the coverage floor entirely.
        unrestricted_diff, unrestricted_coverage = _stratified_adjustment(
            binned, dev_mask, outcome, pool
        )
        unrestricted_harm = unrestricted_diff * outcome.harm_multiplier
        unrestricted_attenuation = (
            1.0 - (unrestricted_harm / raw_harm if raw_harm else 1.0)
        )

        # Additive (main-effects-only) comparison over the same full pool.
        additive_diff, fwl_iterations = _fwl_additive_coefficient(
            binned, dev_mask, outcome.column, pool
        )
        additive_harm = additive_diff * outcome.harm_multiplier
        additive_attenuation = 1.0 - (additive_harm / raw_harm if raw_harm else 1.0)

        # Marginal contribution of the size-proxy covariate (whichever of deal_size_usd /
        # company_size_band is in the selected set -- never both, since one is always excluded as
        # the candidate's own condition feature).
        size_proxy = next(
            (c for c in selected if c in ("deal_size_usd", "company_size_band")), None
        )
        without_proxy_attenuation = None
        without_proxy_coverage = None
        if size_proxy is not None:
            reduced = tuple(c for c in selected if c != size_proxy)
            reduced_diff, reduced_coverage = _stratified_adjustment(binned, dev_mask, outcome, reduced)
            reduced_harm = reduced_diff * outcome.harm_multiplier
            without_proxy_attenuation = 1.0 - (reduced_harm / raw_harm if raw_harm else 1.0)
            without_proxy_coverage = reduced_coverage

        e_value_pass = None  # e-value itself already frozen; not recomputed here (needs pooled_sd).

        record = {
            "candidate_id": candidate_id,
            "conditions": [f"{c.feature} {c.operator} {c.value}" for c in conditions],
            "raw_harm": raw_harm,
            "adjusted_harm": adjusted_harm,
            "attenuation": attenuation,
            "same_sign": same_sign,
            "coverage": coverage,
            "adjustment_pool_size": len(pool),
            "adjustment_selected": list(selected),
            "adjustment_skipped": [
                {"covariate": t["covariate"], "trial_coverage_if_added": t["trial_coverage_if_added"]}
                for t in skipped
            ],
            "cells": cells,
            "unrestricted_pool_coverage": unrestricted_coverage,
            "unrestricted_pool_attenuation": unrestricted_attenuation,
            "additive_fwl_attenuation": additive_attenuation,
            "additive_fwl_iterations": fwl_iterations,
            "size_proxy_in_selected_set": size_proxy,
            "attenuation_without_size_proxy": without_proxy_attenuation,
            "coverage_without_size_proxy": without_proxy_coverage,
        }
        results.append(record)

        print(f"\n=== {candidate_id}: {' AND '.join(record['conditions'])} ===")
        print(f"  raw_harm={raw_harm:.1f}  adjusted_harm={adjusted_harm:.1f}  "
              f"attenuation={attenuation:.4f}  same_sign={same_sign}  coverage={coverage:.4f}")
        print(f"  selected ({len(selected)}/{len(pool)} pool): {selected}")
        for t in skipped:
            print(f"    skipped: {t['covariate']:22s} n_unique={t['n_unique_in_dev']:3d} "
                  f"trial_coverage_if_added={t['trial_coverage_if_added']:.4f}")
        print(f"  cells: {cells}")
        print(f"  unrestricted (full pool, no floor): coverage={unrestricted_coverage:.4f} "
              f"attenuation={unrestricted_attenuation:.4f}")
        print(f"  additive FWL (full pool, main-effects only): attenuation={additive_attenuation:.4f} "
              f"({fwl_iterations} iterations)")
        if size_proxy is not None:
            print(f"  size-proxy covariate in selected set: {size_proxy}")
            print(f"    attenuation WITHOUT it: {without_proxy_attenuation:.4f} "
                  f"(coverage {without_proxy_coverage:.4f})")
        else:
            print("  size-proxy covariate in selected set: NONE")

    out_path = REPOSITORY / "docs/benchmark/task-067-g06-diagnostic-raw.json"
    out_path.write_text(json.dumps({"candidates": results}, indent=2, default=str), encoding="utf-8")
    print(f"\nFull raw diagnostic trace written to {out_path} (POST-HOC DIAGNOSTIC, not an official "
          f"artifact -- documentation reference only, not consumed by any pipeline).")


if __name__ == "__main__":
    main()
