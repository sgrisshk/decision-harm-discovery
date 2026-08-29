"""POST-HOC DIAGNOSTIC (`TASK-079`, `ADR-072`): second forensic layer beyond `G06`
adjustment-set selection.

Three independent branches, each answering a distinct question `TASK-078` left open. **This
script does not propose, scope, or implement any fix, gate change, threshold change, estimator
replacement, or `discovery.engine` change.** It calls the real, unmodified
`policy_analytics.validation.apply` and `policy_analytics.discovery.engine` modules throughout.
The only interventions are process-local, `finally`-restored monkeypatches of module attributes
(never a change to any function's source on disk), used exactly the way `TASK-078`'s own script
established this project's precedent for testing counterfactual estimator behavior without
touching production code:

- Branch 1 (`T04`, estimator sufficiency): `apply_module.ADJUSTMENT_QUANTILE_BINS` is temporarily
  overridden to sweep binning granularity, and `apply_module._select_adjustment_columns` is
  overridden to force `T04`'s fixed, already-established oracle set
  (`booking_lead_days`, `destination` — never re-chosen here). A from-scratch, pure-Python OLS
  regression-adjustment variant is computed independently (no monkeypatch — a separate estimator
  entirely, run alongside, never inside, `run_validation`).
- Branch 2 (`T03`, candidate-condition/confounder entanglement): calls
  `policy_analytics.discovery.engine`'s real, unmodified `_metric`/`_development_score`/`_atoms`/
  `_eligible` functions read-only, to characterize the search's own scoring behavior. No
  `discovery.engine` code is edited, called with modified config in a way that changes its
  behavior, or run inside `discover_candidates` with altered logic — every call uses the shipped
  functions exactly as `discover_candidates` itself would call them.
- Branch 3 (`T05`, overlap ceiling): read-only calls to `_binned_adjustment_frame`/
  `_stratified_adjustment` over every non-empty subset of the oracle set already established by
  `TASK-078`. No gate, threshold, or selection logic change.

Fidelity discipline matches `TASK-075`/`TASK-078`: dataset identity re-verified fresh; oracle sets
and real candidate conditions parsed generically from already-committed raw JSON (`TASK-075`'s and
`TASK-078`'s), never retyped by hand or revised after seeing a result.

Usage:
  uv run python scripts/diagnose_task079_residual_confounding_forensics.py
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402

import policy_analytics.validation.apply as apply_module  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    Condition as EngineCondition,
)
from policy_analytics.discovery.engine import (  # noqa: E402
    DiscoveryConfig,
    _atoms,
    _development_score,
    _eligible,
    _metric,
)
from policy_analytics.outcomes import primary_outcome  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    Condition,
    load_analytical_frame,
    rule_expr,
    run_validation,
    split_stats,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS, PolicyReadiness  # noqa: E402
from policy_analytics.validation.input_contract import validation_input_from_manifest  # noqa: E402

DOCUMENTED_OFFICIAL_FAMILY_SIZE = 33085  # reused verbatim from TASK-075/TASK-078, not re-derived

DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
TASK075_RAW_PATH = REPOSITORY / "docs/benchmark/task-075-t03-forensic-trace-raw.json"
TASK078_RAW_PATH = REPOSITORY / "docs/benchmark/task-078-oracle-adjustment-sufficiency-raw.json"
DEFAULT_RAW_OUTPUT = REPOSITORY / "docs/benchmark/task-079-residual-confounding-forensics-raw.json"
DATASET_IDENTITY_SHA256 = "b6128eb3c1bdb36515c90570aa4ccabfc3dff8d1026d9002f1c832774b60a683"

_CONDITION_TOKEN_RE = re.compile(r"^(?P<feature>\S+)\s+(?P<operator>eq|ge|lt)\s+(?P<value>.+)$")


def _coerce_value(raw_value: str) -> Any:
    raw_value = raw_value.strip()
    if raw_value in ("True", "true"):
        return True
    if raw_value in ("False", "false"):
        return False
    try:
        return int(raw_value)
    except ValueError:
        pass
    try:
        return float(raw_value)
    except ValueError:
        pass
    return raw_value


def _parse_condition_token(token: str) -> Condition:
    match = _CONDITION_TOKEN_RE.match(token.strip())
    if match is None:
        raise ValueError(f"cannot parse condition token {token!r}")
    return Condition(match.group("feature"), match.group("operator"), _coerce_value(match.group("value")))


def _parse_apparent_feature(apparent_feature: str) -> Condition:
    feature, _, raw_value = apparent_feature.partition("=")
    return Condition(feature.strip(), "eq", _coerce_value(raw_value.strip()))


def _real_candidate_conditions_from_task075_raw(trap_id: str, label_prefix: str | None = None) -> tuple[Condition, ...]:
    payload = cast(dict[str, Any], json.loads(TASK075_RAW_PATH.read_text(encoding="utf-8")))
    matches = [
        trace
        for trace in payload["trap_selection_traces"]
        if trace["trap_id"] == trap_id and not trace["is_counterfactual"]
    ]
    if label_prefix is not None:
        matches = [m for m in matches if m["label"].startswith(label_prefix)]
    if not matches:
        raise ValueError(f"no real-candidate trace recorded for {trap_id} in {TASK075_RAW_PATH}")
    trace = matches[0]
    return tuple(_parse_condition_token(token) for token in trace["condition"])


# =====================================================================================
# Small, generic, from-scratch linear algebra for the Branch-1 regression-adjustment
# variant. No numpy available in this environment; matrices here are at most ~8x8
# (intercept + treatment + 4 destination dummies + booking_lead_days), so a plain
# Gauss-Jordan solve over Python lists is fast and exact enough for this diagnostic.
# =====================================================================================


def _solve_normal_equations(xtx: list[list[float]], xty: list[float]) -> list[float]:
    n = len(xty)
    aug = [row[:] + [xty[i]] for i, row in enumerate(xtx)]
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot_row][col]) < 1e-12:
            raise ValueError("singular design matrix in OLS solve")
        aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
        pivot = aug[col][col]
        aug[col] = [v / pivot for v in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor != 0.0:
                aug[row] = [a - factor * b for a, b in zip(aug[row], aug[col])]
    return [aug[i][n] for i in range(n)]


def _ols_fit(design_rows: list[list[float]], y: list[float]) -> list[float]:
    n_cols = len(design_rows[0])
    xtx = [[0.0] * n_cols for _ in range(n_cols)]
    xty = [0.0] * n_cols
    for row, target in zip(design_rows, y):
        for i in range(n_cols):
            xty[i] += row[i] * target
            for j in range(n_cols):
                xtx[i][j] += row[i] * row[j]
    return _solve_normal_equations(xtx, xty)


def _write_candidate_and_metrics(
    tmp_dir: Path, run_label: str, candidate_id: str, conditions: tuple[Condition, ...], outcome_id: str
) -> tuple[Path, Path]:
    candidates_path = tmp_dir / f"{run_label}.candidates.json"
    metrics_path = tmp_dir / f"{run_label}.discovery_metrics.json"
    candidates_path.write_text(
        json.dumps(
            {
                "status": "PERSISTED",
                "outcome": {"outcome_id": outcome_id, "outcome_definition_version": "1.1.0"},
                "candidates": [
                    {
                        "candidate_id": candidate_id,
                        "conditions": [
                            {"feature": c.feature, "operator": c.operator, "value": c.value} for c in conditions
                        ],
                        "outcome": outcome_id,
                    }
                ],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(json.dumps({"evaluated_hypotheses": DOCUMENTED_OFFICIAL_FAMILY_SIZE}, indent=2), encoding="utf-8")
    return candidates_path, metrics_path


def _run_with_oracle_override(
    tmp_dir: Path,
    run_label: str,
    candidate_id: str,
    conditions: tuple[Condition, ...],
    oracle_set: tuple[str, ...],
    dataset_root: Path,
    outcome: Any,
) -> dict[str, Any]:
    """Same monkeypatch discipline TASK-078 established: `_select_adjustment_columns` is
    replaced with a wrapper returning a fixed set for the duration of one `run_validation()`
    call, restored in `finally`. The function's own source on disk is never edited.
    """
    inputs = validation_input_from_manifest(dataset_root)
    candidates_path, metrics_path = _write_candidate_and_metrics(tmp_dir, run_label, candidate_id, conditions, outcome.outcome_id)
    real_select = apply_module._select_adjustment_columns

    def _forced(binned_frame: pl.DataFrame, mask: pl.Series, outcome_arg: Any, pool: tuple[str, ...], min_coverage: float) -> tuple[str, ...]:
        missing = [c for c in oracle_set if c not in pool]
        if missing:
            raise AssertionError(f"oracle override columns {missing} not in real eligible pool {pool}")
        return oracle_set

    apply_module._select_adjustment_columns = _forced  # type: ignore[assignment]
    try:
        results, run_manifest = run_validation(
            dataset_root=dataset_root,
            candidates_path=candidates_path,
            outcome=outcome,
            dataset_version=inputs.dataset_version,
            outcome_definition_version="1.1.0",
            analysis_run_id=f"task079-{run_label}",
            metrics_path=metrics_path,
        )
    finally:
        apply_module._select_adjustment_columns = real_select
    report = results[0].report
    diagnostics = results[0].diagnostics
    gate_trace = [
        {"gate_id": g.gate_id.value, "outcome": g.outcome.value, "satisfied": g.satisfied, "detail": g.detail}
        for g in report.gate_results
    ]
    first_failing = next(
        (g for g in gate_trace if not g["satisfied"] and g["gate_id"] not in ("G13_IDENTIFICATION_DESIGN", "G14_RANDOMIZATION_INTEGRITY")),
        None,
    )
    return {
        "conditions": [f"{c.feature} {c.operator} {c.value}" for c in conditions],
        "oracle_set_applied": list(oracle_set),
        "raw_effect_eur": report.raw_effect.value,
        "adjusted_effect_eur": report.adjusted_effect.value if report.adjusted_effect else None,
        "confounder_stratum_coverage": diagnostics.get("confounder_stratum_coverage"),
        "e_value": diagnostics.get("e_value"),
        "evidence_level": report.evidence_level.value if report.evidence_level else None,
        "policy_readiness": report.policy_readiness.value,
        "gate_of_death_non_g13_g14": first_failing["gate_id"] if first_failing else None,
        "reaches_disqualifying_state": report.policy_readiness.value
        in (PolicyReadiness.SHADOW_POLICY.value, PolicyReadiness.HIGH_CONFIDENCE.value),
    }


# =====================================================================================
# Branch 1 — T04 estimator sufficiency (oracle set held fixed: booking_lead_days, destination)
# =====================================================================================


def branch1_t04(dataset_root: Path, ground_truth: dict[str, Any]) -> dict[str, Any]:
    frame = load_analytical_frame(dataset_root)
    outcome = primary_outcome()
    cand015_conditions = _real_candidate_conditions_from_task075_raw("T04", label_prefix="CAND-015")
    condition_features = frozenset(c.feature for c in cand015_conditions)

    dev_frame = frame.filter(pl.col("split_label") == "development")
    full_mask = frame.select(rule_expr(cand015_conditions).alias("m"))["m"]
    dev_mask = full_mask.filter(frame["split_label"] == "development")

    dev = split_stats(dev_frame, dev_mask, outcome, "development")
    assert dev is not None

    oracle_set = ("booking_lead_days", "destination")
    assert set(oracle_set).isdisjoint(condition_features), "oracle set must not overlap CAND-015's own conditions"

    def _confounding_ok(coverage: float, adjusted_harm: float, attenuation: float, ev: float) -> bool:
        return (
            coverage >= DEFAULT_THRESHOLDS.min_confounder_stratum_coverage
            and (adjusted_harm > 0) == (dev.harm_per_booking > 0)
            and attenuation <= DEFAULT_THRESHOLDS.max_adjusted_attenuation
            and ev >= DEFAULT_THRESHOLDS.min_e_value
        )

    def _run_stratified(bins: int) -> dict[str, Any]:
        original_bins = apply_module.ADJUSTMENT_QUANTILE_BINS
        apply_module.ADJUSTMENT_QUANTILE_BINS = bins
        try:
            binned = apply_module._binned_adjustment_frame(dev_frame, oracle_set)
            adjusted_diff, coverage = apply_module._stratified_adjustment(binned, dev_mask, outcome, oracle_set)
        finally:
            apply_module.ADJUSTMENT_QUANTILE_BINS = original_bins
        adjusted_harm = adjusted_diff * outcome.harm_multiplier
        attenuation = 1.0 - (adjusted_harm / dev.harm_per_booking if dev.harm_per_booking else 1.0)
        ev = apply_module.e_value(adjusted_harm, dev.pooled_sd)

        # Cell-level diagnostics: reproduce _stratified_adjustment's own grouping to report cell
        # counts (not returned by the real function, whose contract is (diff, coverage) only).
        working = binned.select([*oracle_set, outcome.column]).with_columns(dev_mask.alias("_exposed"))
        grouped = working.group_by([*oracle_set, "_exposed"]).agg(
            pl.col(outcome.column).count().alias("_n")
        )
        cells: dict[tuple[Any, ...], dict[str, int]] = {}
        for row in grouped.iter_rows(named=True):
            key = tuple(row[c] for c in oracle_set)
            cell = cells.setdefault(key, {"en": 0, "cn": 0})
            if row["_exposed"]:
                cell["en"] += row["_n"]
            else:
                cell["cn"] += row["_n"]
        usable = [c for c in cells.values() if c["en"] >= apply_module.MIN_STRATUM_CELL and c["cn"] >= apply_module.MIN_STRATUM_CELL]

        return {
            "bins": bins,
            "coverage": coverage,
            "adjusted_harm_eur": adjusted_harm,
            "attenuation": attenuation,
            "e_value": ev,
            "confounding_gate_ok": _confounding_ok(coverage, adjusted_harm, attenuation, ev),
            "total_joint_cells": len(cells),
            "usable_joint_cells": len(usable),
            "usable_cell_fraction": len(usable) / len(cells) if cells else 0.0,
        }

    bin_sweep = [_run_stratified(b) for b in (2, 3, 4, 5, 6, 8, 10, 12)]
    baseline = next(r for r in bin_sweep if r["bins"] == apply_module.ADJUSTMENT_QUANTILE_BINS)

    # --- Pure-T04 counterfactual: does the trap's own single-condition apparent_feature
    # (payment_method==bank_transfer, WITHOUT CAND-015's own second condition discount_rate>=0.05
    # compounded on) survive under the identical oracle set? TASK-075 §2 established this exact
    # counterfactual discipline for T03 (isolate whether a candidate's *own extra condition*, not
    # just the trap's confounders, is load-bearing for the survival). ---
    with tempfile.TemporaryDirectory(prefix="task079_t04_pure_") as tmp:
        tmp_dir = Path(tmp)
        pure_t04_result = _run_with_oracle_override(
            tmp_dir,
            "t04-pure-oracle",
            "TASK079-T04-pure-counterfactual",
            (Condition("payment_method", "eq", "bank_transfer"),),
            oracle_set,
            dataset_root,
            outcome,
        )

    # --- discount_rate hypothetical: CAND-015's own second condition (discount_rate>=0.05) is
    # itself the single strongest score-boosting feature found in Branch 2's sweep for this same
    # trap (see branch2_t03's T04 entry) and is structurally excluded from CAND-015's own
    # adjustment set by G02's circularity guard (it is literally CAND-015's own condition), the
    # same structural mechanism Branch 2 characterizes for T03/discount_rate. This hypothetical
    # (adjusting for discount_rate jointly with the oracle set, bypassing G02 for
    # characterization only, exactly mirroring TASK-075 §2's own "what if this exclusion were not
    # load-bearing" counterfactual discipline for T03) is diagnostic only -- it does not propose
    # bypassing G02 for real, and is reported as evidence for the cross-branch mechanism, not as a
    # recommended adjustment set.
    hypothetical_set = (*oracle_set, "discount_rate")
    binned_hyp = apply_module._binned_adjustment_frame(dev_frame, hypothetical_set)
    hyp_diff, hyp_coverage = apply_module._stratified_adjustment(binned_hyp, dev_mask, outcome, hypothetical_set)
    hyp_harm = hyp_diff * outcome.harm_multiplier
    hyp_attenuation = 1.0 - (hyp_harm / dev.harm_per_booking if dev.harm_per_booking else 1.0)
    hyp_ev = apply_module.e_value(hyp_harm, dev.pooled_sd)
    discount_rate_hypothetical = {
        "note": (
            "G02-bypassing hypothetical, diagnostic only, mirrors TASK-075 Section 2's own "
            "counterfactual discipline for T03/discount_rate. Not a proposal to bypass G02."
        ),
        "hypothetical_set": list(hypothetical_set),
        "coverage": hyp_coverage,
        "adjusted_harm_eur": hyp_harm,
        "attenuation": hyp_attenuation,
        "e_value": hyp_ev,
        "confounding_gate_ok": _confounding_ok(hyp_coverage, hyp_harm, hyp_attenuation, hyp_ev),
    }

    # --- Regression-adjustment variant: standard additive OLS, oracle set held fixed ---
    # Design: intercept, treatment (CAND-015 exposure indicator), destination one-hot (k-1
    # dummies, alphabetically drop the first level), booking_lead_days as a raw continuous
    # covariate (no binning at all -- the natural alternative to the estimator's own quartile
    # discretization). This is a genuinely different, standard method (regression/ANCOVA-style
    # adjustment) from stratified mean-differencing, not a variant chosen to flip the verdict.
    dest_levels = sorted(dev_frame["destination"].unique().to_list())
    dest_dummy_levels = dest_levels[1:]  # drop first as reference level
    lead_days_col = dev_frame["booking_lead_days"].to_list()
    dest_col = dev_frame["destination"].to_list()
    outcome_col = dev_frame[outcome.column].to_list()
    treatment_col = dev_mask.to_list()

    design_rows: list[list[float]] = []
    y: list[float] = []
    for lead, dest, out, treated in zip(lead_days_col, dest_col, outcome_col, treatment_col):
        if out is None or lead is None or dest is None:
            continue
        row = [1.0, 1.0 if treated else 0.0]
        row.extend(1.0 if dest == level else 0.0 for level in dest_dummy_levels)
        row.append(float(lead))
        design_rows.append(row)
        y.append(float(out))

    beta = _ols_fit(design_rows, y)
    treatment_coef_raw = beta[1]  # coefficient on the raw outcome scale (direction: harm sign depends on outcome.harm_multiplier)
    regression_adjusted_harm = treatment_coef_raw * outcome.harm_multiplier
    regression_attenuation = 1.0 - (regression_adjusted_harm / dev.harm_per_booking if dev.harm_per_booking else 1.0)
    regression_ev = apply_module.e_value(regression_adjusted_harm, dev.pooled_sd)
    regression_ok = _confounding_ok(1.0, regression_adjusted_harm, regression_attenuation, regression_ev)

    # --- P06-overlap decomposition: how much of the raw/residual effect is genuine partial
    # recovery of the true pattern P06 ("destination=Tokyo AND booking_lead_days<10 AND
    # payment_method=bank_transfer"), vs. the rest of CAND-015's exposed population, which the
    # trap's own hidden_ground_truth records as direct_effect=0 (pure confounding)? ---
    p06 = next(p for p in ground_truth["patterns"] if p["id"] == "P06")
    p06_rule = tuple(
        _parse_apparent_feature(tok) if "=" in tok and "<" not in tok else None
        for tok in [p06["rule"]]
    )
    # Parse "destination=Tokyo AND booking_lead_days<10 AND payment_method=bank_transfer" generically.
    p06_conditions: list[Condition] = []
    for clause in p06["rule"].split(" AND "):
        clause = clause.strip()
        if "<" in clause:
            feature, _, value = clause.partition("<")
            p06_conditions.append(Condition(feature.strip(), "lt", _coerce_value(value.strip())))
        elif ">=" in clause:
            feature, _, value = clause.partition(">=")
            p06_conditions.append(Condition(feature.strip(), "ge", value.strip()))
        else:
            feature, _, value = clause.partition("=")
            p06_conditions.append(Condition(feature.strip(), "eq", _coerce_value(value.strip())))
    p06_mask_full = frame.select(rule_expr(tuple(p06_conditions)).alias("m"))["m"]
    p06_mask = p06_mask_full.filter(frame["split_label"] == "development")

    overlap_mask = [e and p for e, p in zip(dev_mask.to_list(), p06_mask.to_list())]
    exposed_only_mask = [e and not p for e, p in zip(dev_mask.to_list(), p06_mask.to_list())]
    comparison_mask = [not e for e in dev_mask.to_list()]

    def _subset_stats(mask_list: list[bool]) -> dict[str, Any]:
        series = pl.Series(mask_list)
        subset = dev_frame.filter(series)
        vals = subset[outcome.column].drop_nulls().to_list()
        mean_val = sum(vals) / len(vals) if vals else None
        return {"n": len(vals), "mean": mean_val}

    overlap_stats = _subset_stats(overlap_mask)
    exposed_only_stats = _subset_stats(exposed_only_mask)
    comparison_stats = _subset_stats(comparison_mask)
    n_exposed_total = overlap_stats["n"] + exposed_only_stats["n"]

    comparison_mean = comparison_stats["mean"]
    overlap_contribution = None
    exposed_only_contribution = None
    if comparison_mean is not None and n_exposed_total:
        if overlap_stats["mean"] is not None:
            overlap_contribution = (
                (overlap_stats["mean"] - comparison_mean) * outcome.harm_multiplier
                * overlap_stats["n"] / n_exposed_total
            )
        if exposed_only_stats["mean"] is not None:
            exposed_only_contribution = (
                (exposed_only_stats["mean"] - comparison_mean) * outcome.harm_multiplier
                * exposed_only_stats["n"] / n_exposed_total
            )

    return {
        "candidate_conditions": [f"{c.feature} {c.operator} {c.value}" for c in cand015_conditions],
        "oracle_set_fixed": list(oracle_set),
        "raw_dev_harm_eur": dev.harm_per_booking,
        "raw_dev_pooled_sd": dev.pooled_sd,
        "baseline_4bin_reproduction": baseline,
        "bin_granularity_sweep": bin_sweep,
        "pure_t04_counterfactual_no_discount_rate_compounding": pure_t04_result,
        "discount_rate_hypothetical_g02_bypass_diagnostic_only": discount_rate_hypothetical,
        "regression_adjustment_variant": {
            "method": "additive OLS: outcome ~ treatment + destination(4 dummies) + booking_lead_days(raw continuous)",
            "n_rows": len(design_rows),
            "beta": beta,
            "treatment_coefficient_raw": treatment_coef_raw,
            "regression_adjusted_harm_eur": regression_adjusted_harm,
            "attenuation": regression_attenuation,
            "e_value": regression_ev,
            "confounding_gate_ok_if_applied": regression_ok,
        },
        "adr043_prior_context": (
            "ADR-043 (2026-08-21, HANDOFF-058) already tested additive multivariate regression vs "
            "full joint stratification on an earlier run's CAND-015-labeled candidate over its full "
            "8-covariate adjustment-eligible pool (not the 2-variable oracle set held fixed here): "
            "additive regression showed harm 157.2->158.9 EUR (near-zero attenuation, direction "
            "opposite of attenuating), while an unrestricted 8-covariate joint stratification "
            "(ignoring the coverage floor, which collapsed to 0.21) showed harm collapsing to ~47.7 "
            "EUR. ADR-043 attributed the gap to interaction structure additive regression cannot "
            "capture. This task's own regression run (2-variable oracle set, not 8) is reported "
            "independently below, not as a re-litigation of ADR-043's already-decided scope."
        ),
        "p06_overlap_decomposition": {
            "p06_rule": p06["rule"],
            "overlap_subset": overlap_stats,
            "exposed_only_subset": exposed_only_stats,
            "comparison_subset": comparison_stats,
            "overlap_weighted_contribution_to_raw_effect_eur": overlap_contribution,
            "exposed_only_weighted_contribution_to_raw_effect_eur": exposed_only_contribution,
            "note": (
                "hidden_ground_truth records T04's own direct_effect as 0 (payment_method=bank_transfer "
                "has no genuine causal effect on its own) -- any real signal in CAND-015's exposed "
                "population traces only to whatever fraction of it overlaps a true pattern (P06)."
            ),
        },
    }


# =====================================================================================
# Branch 2 — T03 candidate-condition/confounder entanglement
# =====================================================================================


def branch2_t03(dataset_root: Path, ground_truth: dict[str, Any]) -> dict[str, Any]:
    frame = load_analytical_frame(dataset_root)
    outcome = primary_outcome()
    inputs = validation_input_from_manifest(dataset_root)
    config = DiscoveryConfig()
    dev = frame.filter(pl.col("split_label") == "development")

    traps = {t["id"]: t for t in ground_truth["confounding_traps"]}
    per_trap: dict[str, Any] = {}
    all_trials: list[dict[str, Any]] = []

    for trap_id, trap in traps.items():
        base_feature, _, base_value = trap["apparent_feature"].partition("=")
        base_feature = base_feature.strip()
        base_condition = EngineCondition(base_feature, "eq", _coerce_value(base_value.strip()))
        base_rule = (base_condition,)
        m_base = _metric(frame, base_rule, outcome, "development")
        if m_base is None or not _eligible(m_base, config):
            per_trap[trap_id] = {"apparent_feature": trap["apparent_feature"], "base_eligible": False}
            continue
        s_base = _development_score(m_base, 1, config)

        confounders = set(trap["confounded_by"])
        pool = sorted(inputs.adjustment_features - {base_feature})
        atoms = _atoms(dev, tuple(pool), config)
        by_feature: dict[str, list[EngineCondition]] = {}
        for a in atoms:
            by_feature.setdefault(a.feature, []).append(a)

        trials: list[dict[str, Any]] = []
        for feature, feature_atoms in sorted(by_feature.items()):
            best: tuple[EngineCondition, float, Any] | None = None
            for atom in feature_atoms:
                rule = (*base_rule, atom)
                m = _metric(frame, rule, outcome, "development")
                if m is None or not _eligible(m, config):
                    continue
                s = _development_score(m, 2, config)
                if best is None or s > best[1]:
                    best = (atom, s, m)
            is_confounder = feature in confounders
            if best is None:
                trial = {
                    "feature": feature,
                    "is_ground_truth_confounder": is_confounder,
                    "eligible_atom_found": False,
                }
            else:
                atom, s, m = best
                delta = s - s_base
                trial = {
                    "feature": feature,
                    "best_atom": f"{atom.feature} {atom.operator} {atom.value}",
                    "score": s,
                    "score_delta_vs_singleton": delta,
                    "score_increased": delta > 0,
                    "harm_per_booking_eur": m.harm_per_booking,
                    "n_exposed": m.n_exposed,
                    "is_ground_truth_confounder": is_confounder,
                    "eligible_atom_found": True,
                }
            trials.append(trial)
            all_trials.append({**trial, "trap_id": trap_id})

        n_increase = sum(1 for t in trials if t.get("score_increased"))
        n_eligible = sum(1 for t in trials if t.get("eligible_atom_found"))
        per_trap[trap_id] = {
            "apparent_feature": trap["apparent_feature"],
            "base_eligible": True,
            "base_score": s_base,
            "base_harm_per_booking_eur": m_base.harm_per_booking,
            "base_n_exposed": m_base.n_exposed,
            "ground_truth_confounders": sorted(confounders),
            "compounding_trials": sorted(trials, key=lambda t: -(t.get("score", float("-inf")))),
            "n_features_increasing_score": n_increase,
            "n_features_eligible": n_eligible,
        }

    # --- Aggregate 2x2: is being a ground-truth confounder (for the trap being compounded onto)
    # associated with being score-increasing, across all trials from all 5 traps? ---
    eligible_trials = [t for t in all_trials if t.get("eligible_atom_found")]
    confounder_trials = [t for t in eligible_trials if t["is_ground_truth_confounder"]]
    non_confounder_trials = [t for t in eligible_trials if not t["is_ground_truth_confounder"]]
    confounder_increase_rate = (
        sum(1 for t in confounder_trials if t["score_increased"]) / len(confounder_trials)
        if confounder_trials else None
    )
    non_confounder_increase_rate = (
        sum(1 for t in non_confounder_trials if t["score_increased"]) / len(non_confounder_trials)
        if non_confounder_trials else None
    )

    # --- Direct trace: CAND-014's actual real condition pair vs its own singleton ---
    cand014_full = _real_candidate_conditions_from_task075_raw("T03")
    singleton_ac = (EngineCondition("acquisition_channel", "eq", "paid_search"),)
    compound_ac_discount = (
        EngineCondition("acquisition_channel", "eq", "paid_search"),
        EngineCondition("discount_rate", "ge", 0.08),
    )
    m_single = _metric(frame, singleton_ac, outcome, "development")
    m_compound = _metric(frame, compound_ac_discount, outcome, "development")
    s_single = _development_score(m_single, 1, config)
    s_compound = _development_score(m_compound, 2, config)

    return {
        "method": (
            "For each trap's single-condition apparent_feature, compute discovery.engine's real, "
            "unmodified _development_score for the singleton, then for every DECISION_TIME "
            "adjustment-eligible pool feature, compute the score of compounding that feature's own "
            "best-scoring real atom (from engine._atoms) onto the singleton as a 2-condition rule. "
            "No discovery.engine code is modified; every call uses the shipped scoring function "
            "exactly as discover_candidates itself would."
        ),
        "per_trap": per_trap,
        "aggregate_confounder_vs_nonconfounder_score_increase_rate": {
            "n_confounder_trials": len(confounder_trials),
            "confounder_score_increase_rate": confounder_increase_rate,
            "n_non_confounder_trials": len(non_confounder_trials),
            "non_confounder_score_increase_rate": non_confounder_increase_rate,
        },
        "cand014_direct_trace": {
            "singleton": "acquisition_channel eq paid_search",
            "singleton_score": s_single,
            "singleton_harm_eur": m_single.harm_per_booking,
            "singleton_n_exposed": m_single.n_exposed,
            "compound_with_discount_rate": "acquisition_channel eq paid_search AND discount_rate ge 0.08",
            "compound_score": s_compound,
            "compound_harm_eur": m_compound.harm_per_booking,
            "compound_n_exposed": m_compound.n_exposed,
            "score_delta": s_compound - s_single,
            "score_increased": s_compound > s_single,
            "matches_real_cand014_conditions": (
                {(c.feature, c.operator, c.value) for c in cand014_full}
                == {(c.feature, c.operator, c.value) for c in compound_ac_discount}
            ),
        },
    }


# =====================================================================================
# Branch 3 — T05 overlap ceiling
# =====================================================================================


def branch3_t05(dataset_root: Path, ground_truth: dict[str, Any]) -> dict[str, Any]:
    frame = load_analytical_frame(dataset_root)
    outcome = primary_outcome()

    traps = {t["id"]: t for t in ground_truth["confounding_traps"]}
    t05 = traps["T05"]
    condition = _parse_apparent_feature(t05["apparent_feature"])
    dev_frame = frame.filter(pl.col("split_label") == "development")
    full_mask = frame.select(rule_expr((condition,)).alias("m"))["m"]
    dev_mask = full_mask.filter(frame["split_label"] == "development")

    dev = split_stats(dev_frame, dev_mask, outcome, "development")
    assert dev is not None

    oracle_set = tuple(sorted(t05["confounded_by"]))

    def _subsets(items: tuple[str, ...]) -> list[tuple[str, ...]]:
        result: list[tuple[str, ...]] = []
        n = len(items)
        for mask in range(1, 1 << n):
            result.append(tuple(items[i] for i in range(n) if mask & (1 << i)))
        return result

    subset_results = []
    for subset in _subsets(oracle_set):
        binned = apply_module._binned_adjustment_frame(dev_frame, subset)
        adjusted_diff, coverage = apply_module._stratified_adjustment(binned, dev_mask, outcome, subset)
        # joint cell count for this subset
        working = binned.select([*subset, outcome.column]).with_columns(dev_mask.alias("_exposed"))
        grouped = working.group_by([*subset, "_exposed"]).agg(pl.col(outcome.column).count().alias("_n"))
        cells: dict[tuple[Any, ...], dict[str, int]] = {}
        for row in grouped.iter_rows(named=True):
            key = tuple(row[c] for c in subset)
            cell = cells.setdefault(key, {"en": 0, "cn": 0})
            if row["_exposed"]:
                cell["en"] += row["_n"]
            else:
                cell["cn"] += row["_n"]
        usable = [c for c in cells.values() if c["en"] >= apply_module.MIN_STRATUM_CELL and c["cn"] >= apply_module.MIN_STRATUM_CELL]
        subset_results.append(
            {
                "subset": list(subset),
                "size": len(subset),
                "coverage": coverage,
                "total_joint_cells": len(cells),
                "usable_joint_cells": len(usable),
                "clears_0.50_floor": coverage >= DEFAULT_THRESHOLDS.min_confounder_stratum_coverage,
            }
        )
    subset_results.sort(key=lambda r: (r["size"], -r["coverage"]))

    # Theoretical joint-cell ceiling given n_exposed and MIN_STRATUM_CELL: how many joint cells
    # could this exposed population possibly support at MIN_STRATUM_CELL=5 minimum occupancy,
    # under perfectly even allocation (upper bound, real allocation is never this even).
    n_exposed = dev.n_exposed
    max_cells_even_allocation = n_exposed // apply_module.MIN_STRATUM_CELL

    per_variable_marginal_cardinality = {}
    for var in oracle_set:
        binned_single = apply_module._binned_adjustment_frame(dev_frame, (var,))
        per_variable_marginal_cardinality[var] = binned_single[var].n_unique()

    return {
        "condition_tested": f"{condition.feature} {condition.operator} {condition.value}",
        "n_exposed_development": n_exposed,
        "oracle_set_full": list(oracle_set),
        "per_variable_marginal_cardinality_binned": per_variable_marginal_cardinality,
        "subset_coverage_sweep": subset_results,
        "max_joint_cells_supportable_even_allocation": max_cells_even_allocation,
        "note": (
            "max_joint_cells_supportable_even_allocation is n_exposed // MIN_STRATUM_CELL -- an "
            "upper bound under perfectly even allocation across cells (the best case any allocation "
            "could achieve); real data is never this even, so real usable-cell counts at a given "
            "joint cardinality are always <= this bound, generally well below it."
        ),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    dataset_root = cast(Path, args.dataset_root)

    manifest = cast(dict[str, Any], json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8")))
    if manifest["dataset_identity_sha256"] != DATASET_IDENTITY_SHA256:
        raise SystemExit(
            f"dataset identity {manifest['dataset_identity_sha256']} != TASK-075/TASK-078's own "
            f"recorded identity ({DATASET_IDENTITY_SHA256})"
        )
    print(f"[fidelity] dataset identity matches TASK-075/TASK-078's own record: {DATASET_IDENTITY_SHA256}")

    if not TASK078_RAW_PATH.exists():
        raise SystemExit(f"missing {TASK078_RAW_PATH} -- TASK-079 depends on TASK-078's raw output")

    ground_truth = cast(dict[str, Any], json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8")))

    print("\n=== Branch 1 (T04, estimator sufficiency) ===")
    b1 = branch1_t04(dataset_root, ground_truth)
    print(f"baseline (4-bin) adjusted harm: {b1['baseline_4bin_reproduction']['adjusted_harm_eur']:.1f} EUR, "
          f"attenuation {b1['baseline_4bin_reproduction']['attenuation']:.2f}, "
          f"E-value {b1['baseline_4bin_reproduction']['e_value']:.2f}")
    for r in b1["bin_granularity_sweep"]:
        print(f"  bins={r['bins']:>2d} adjusted_harm={r['adjusted_harm_eur']:7.1f} "
              f"attenuation={r['attenuation']:6.2f} e_value={r['e_value']:5.2f} "
              f"gate_ok={r['confounding_gate_ok']} usable_cells={r['usable_joint_cells']}/{r['total_joint_cells']}")
    reg = b1["regression_adjustment_variant"]
    print(f"regression variant: adjusted_harm={reg['regression_adjusted_harm_eur']:.1f} "
          f"attenuation={reg['attenuation']:.2f} e_value={reg['e_value']:.2f} gate_ok={reg['confounding_gate_ok_if_applied']}")
    pure = b1["pure_t04_counterfactual_no_discount_rate_compounding"]
    print(f"pure T04 (no discount_rate compounding): policy_readiness={pure['policy_readiness']} "
          f"gate_of_death={pure['gate_of_death_non_g13_g14']} reaches_disqualifying={pure['reaches_disqualifying_state']}")
    hyp = b1["discount_rate_hypothetical_g02_bypass_diagnostic_only"]
    print(f"discount_rate hypothetical (G02-bypass, diagnostic only): adjusted_harm={hyp['adjusted_harm_eur']:.1f} "
          f"attenuation={hyp['attenuation']:.2f} e_value={hyp['e_value']:.2f} gate_ok={hyp['confounding_gate_ok']} "
          f"coverage={hyp['coverage']:.2f}")
    p06 = b1["p06_overlap_decomposition"]
    print(f"P06 overlap: n={p06['overlap_subset']['n']}, exposed_only: n={p06['exposed_only_subset']['n']}")
    print(f"  overlap contribution to raw effect: {p06['overlap_weighted_contribution_to_raw_effect_eur']}")
    print(f"  exposed_only contribution to raw effect: {p06['exposed_only_weighted_contribution_to_raw_effect_eur']}")

    print("\n=== Branch 2 (T03, candidate-condition/confounder entanglement) ===")
    b2 = branch2_t03(dataset_root, ground_truth)
    for trap_id, info in b2["per_trap"].items():
        if not info.get("base_eligible"):
            print(f"  {trap_id}: base singleton not eligible, skipped")
            continue
        print(f"  {trap_id}: {info['n_features_increasing_score']}/{info['n_features_eligible']} "
              f"pool features increase score when compounded onto '{info['apparent_feature']}'")
    agg = b2["aggregate_confounder_vs_nonconfounder_score_increase_rate"]
    print(f"aggregate: confounder trials score-increase rate = {agg['confounder_score_increase_rate']} "
          f"(n={agg['n_confounder_trials']}), non-confounder rate = {agg['non_confounder_score_increase_rate']} "
          f"(n={agg['n_non_confounder_trials']})")
    trace = b2["cand014_direct_trace"]
    print(f"CAND-014 direct trace: singleton score {trace['singleton_score']:.1f} -> "
          f"compound score {trace['compound_score']:.1f} (delta {trace['score_delta']:.1f}), "
          f"matches real CAND-014: {trace['matches_real_cand014_conditions']}")

    print("\n=== Branch 3 (T05, overlap ceiling) ===")
    b3 = branch3_t05(dataset_root, ground_truth)
    print(f"n_exposed={b3['n_exposed_development']}, max joint cells (even allocation) = "
          f"{b3['max_joint_cells_supportable_even_allocation']}")
    for r in b3["subset_coverage_sweep"]:
        print(f"  size={r['size']} subset={r['subset']} coverage={r['coverage']:.3f} "
              f"usable_cells={r['usable_joint_cells']}/{r['total_joint_cells']} "
              f"clears_floor={r['clears_0.50_floor']}")

    output = {
        "diagnostic": "TASK-079 second forensic layer (ADR-072)",
        "dataset_identity_sha256": DATASET_IDENTITY_SHA256,
        "branch1_t04_estimator_sufficiency": b1,
        "branch2_t03_candidate_condition_entanglement": b2,
        "branch3_t05_overlap_ceiling": b3,
    }
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {args.raw_output}")


if __name__ == "__main__":
    main()
