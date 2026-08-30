"""TASK-084 branch 4 diagnostic: synthetic positive/negative controls for the population-dilution
hypothesis.

Diagnosis only (`ADR-085`/`TASK-084`). Known-by-construction synthetic DGPs, calling the real,
unmodified estimator functions (`policy_analytics.outcomes.summarize_group`/`raw_difference`/
`harm_score`, `policy_analytics.validation.apply.cluster_cells`/`cluster_bootstrap_replicates`/
`percentile_ci`/`build_economic_impact_result`) -- no reimplemented estimator logic, matching this
chain's established synthetic-first discipline (`TASK-075`/`078`/`079`).

**Design note, derived analytically before coding (kept here so the result is checked against a
real prior, not just read off):** for a rule whose "diluting" (non-true-pattern) exposed records are
literally drawn from the SAME distribution as the comparison group (zero incremental association
with the outcome), `historical_impact = harm_per_booking * exposed_total` is *algebraically exact*
in expectation regardless of how much dilution is added -- the attenuation in the per-record mean
and the inflation in the count cancel exactly:
  mean(exposed) = [n_true*(mu_bg - h) + k*n_true*mu_bg] / (n_true*(1+k)) = mu_bg - h/(1+k)
  reported = [h/(1+k)] * [n_true*(1+k)] = h * n_true = truth, for any k.
So pure population growth by itself is NOT sufficient to bias this estimator -- this is the
NEGATIVE control's precise, quantitative prediction, not just a qualitative expectation.

Whole-rule error should instead grow with dilution specifically when the diluting population
carries its OWN, non-true-pattern association with the outcome (a "surrogate confound" -- e.g. the
surrogate condition, such as a discount-rate threshold, is itself correlated with the outcome for
reasons unrelated to the injected true pattern). In that case:
  reported = n_true*h + k*n_true*c   (c = the confound's own per-record association)
which grows linearly in k whenever c != 0 -- this is the POSITIVE control.

Two synthetic DGPs, both calling the real functions:

  NEGATIVE CONTROL -- diluting records i.i.d. with the comparison group (c = 0 by construction).
  Sweeps dilution ratio k in {0, 1, 2, 5, 10, 20}. Prediction: whole-rule reported impact and its
  relative error stay flat (within bootstrap noise) as k grows; an overlap-conditioned (oracle)
  estimand is unnecessary here since there is nothing to correct.

  POSITIVE CONTROL -- diluting records carry a fixed, nonzero, same-signed confound c (a real,
  distinct, non-true-pattern association with the outcome -- NOT the injected true effect).
  Sweeps the same dilution ratios. Prediction: whole-rule reported impact and relative error grow
  with k; an overlap-conditioned estimand (computed only over the known true-affected records, using
  the real functions) stays close to truth throughout, unmoved by how much dilution surrounds it.

Every group is clustered one-record-per-cluster (a distinct synthetic customer_id per row) so
`cluster_bootstrap_replicates` runs unmodified over a trivial clustering; this does not simplify the
point estimate, only the resampling unit.

Usage: uv run python scripts/diagnose_task084_branch4_controls.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402

from policy_analytics.outcomes import harm_score, raw_difference, summarize_group  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    BOOTSTRAP_SEED,
    DEFAULT_THRESHOLDS,
    DIAGNOSTIC_BOOTSTRAP_REPS,
    cluster_bootstrap_replicates,
    cluster_cells,
    percentile_ci,
)
from policy_analytics.validation.economic_impact import build_economic_impact_result  # noqa: E402

N_BACKGROUND = 6000
N_TRUE_AFFECTED = 200
TRUE_HARM = 80.0  # fixed, known-by-construction per-record harm (EUR), true pattern only
BACKGROUND_MEAN = 1000.0
NOISE_SD = 120.0
CONFOUND_C = 45.0  # positive control only: diluting records' own, non-true-pattern harm (EUR)
DILUTION_RATIOS = [0, 1, 2, 5, 10, 20]
SEED = 20260830


class _Outcome:
    outcome_id = "synthetic_contribution_margin"
    column = "value"
    unit = "EUR per record"
    higher_is_worse = False
    harm_multiplier = -1  # a decrease in margin is harm, matching the real travel outcome


OUTCOME = _Outcome()


def _make_frame(rng: random.Random, n_diluting: int, confound_c: float) -> tuple[pl.DataFrame, list[str], list[str]]:
    """Build one synthetic frame: background + true-affected + diluting records.

    Returns (frame, true_affected_ids, exposed_ids). `exposed_ids` = true_affected + diluting
    (the candidate rule's full reported population); the comparison group is everyone else.
    """
    rows: list[dict[str, Any]] = []
    true_ids: list[str] = []
    exposed_ids: list[str] = []

    idx = 0
    # background / comparison pool (never part of the candidate's exposed set)
    n_pure_background = N_BACKGROUND
    for _ in range(n_pure_background):
        rid = f"bg-{idx}"
        idx += 1
        rows.append({"record_id": rid, "customer_id": rid, "value": rng.gauss(BACKGROUND_MEAN, NOISE_SD)})

    # true-affected records (always in the candidate's exposed set, fixed known effect)
    for _ in range(N_TRUE_AFFECTED):
        rid = f"true-{idx}"
        idx += 1
        rows.append(
            {"record_id": rid, "customer_id": rid, "value": rng.gauss(BACKGROUND_MEAN - TRUE_HARM, NOISE_SD)}
        )
        true_ids.append(rid)
        exposed_ids.append(rid)

    # diluting records: satisfy the candidate's surrogate rule but are NOT part of the true
    # pattern. `confound_c` = 0 -> negative control (i.i.d. with background); `confound_c` != 0
    # -> positive control (a real, distinct, non-true-pattern association with the outcome).
    for _ in range(n_diluting):
        rid = f"dilute-{idx}"
        idx += 1
        rows.append(
            {"record_id": rid, "customer_id": rid, "value": rng.gauss(BACKGROUND_MEAN - confound_c, NOISE_SD)}
        )
        exposed_ids.append(rid)

    frame = pl.DataFrame(rows)
    return frame, true_ids, exposed_ids


def _estimate(
    frame: pl.DataFrame, exposed_ids: list[str], comparison_ids_mask: pl.Series | None = None
) -> dict[str, Any]:
    """Run the real estimator (summarize_group/raw_difference/harm_score + cluster bootstrap +
    build_economic_impact_result) over `exposed_ids` vs everyone else -- the same computation
    `apply.py`'s combined_stats/economic_impact section performs, called directly.
    """
    exposed_set = frozenset(exposed_ids)
    mask = pl.Series("m", [rid in exposed_set for rid in frame["record_id"].to_list()])
    exposed_group = frame.filter(mask)[OUTCOME.column].to_list()
    comparison_group = frame.filter(~mask)[OUTCOME.column].to_list()
    exposed_summary = summarize_group(exposed_group, OUTCOME)
    comparison_summary = summarize_group(comparison_group, OUTCOME)
    diff = raw_difference(exposed_summary, comparison_summary)
    per_record_value = harm_score(diff, OUTCOME)
    exposed_total = exposed_summary.n_present

    clusters = cluster_cells(frame, mask, OUTCOME.column, "customer_id")
    rng = random.Random(BOOTSTRAP_SEED)
    reps = cluster_bootstrap_replicates(clusters, DIAGNOSTIC_BOOTSTRAP_REPS, rng)
    per_record_reps = [d * OUTCOME.harm_multiplier for d in reps]
    per_low, per_high = percentile_ci(per_record_reps, DEFAULT_THRESHOLDS.confidence_level)
    exposure_reps = [d * OUTCOME.harm_multiplier * exposed_total for d in reps]
    exp_low, exp_high = percentile_ci(exposure_reps, DEFAULT_THRESHOLDS.confidence_level)
    historical_value = per_record_value * exposed_total

    result = build_economic_impact_result(
        outcome=OUTCOME,
        affected_records=exposed_total,
        per_record_value=per_record_value,
        per_record_ci_low=per_low,
        per_record_ci_high=per_high,
        confidence_level=DEFAULT_THRESHOLDS.confidence_level,
        historical_value=historical_value,
        historical_ci_low=exp_low,
        historical_ci_high=exp_high,
        materiality_pass=True,
    )
    reported_point = (result.historical_impact.ci_low + result.historical_impact.ci_high) / 2
    return {
        "exposed_n": exposed_total,
        "per_record_value": per_record_value,
        "reported_point_eur": reported_point,
    }


def _run_sweep(label: str, confound_c: float) -> list[dict[str, Any]]:
    truth_total = TRUE_HARM * N_TRUE_AFFECTED
    rows: list[dict[str, Any]] = []
    for ratio in DILUTION_RATIOS:
        rng = random.Random(SEED + ratio)  # fresh draw per point, deterministic
        n_diluting = ratio * N_TRUE_AFFECTED
        frame, true_ids, exposed_ids = _make_frame(rng, n_diluting, confound_c)

        whole_rule = _estimate(frame, exposed_ids)
        whole_rule_signed_error = (whole_rule["reported_point_eur"] - truth_total) / truth_total

        oracle = _estimate(frame, true_ids)  # overlap-conditioned: only the known true-affected
        oracle_signed_error = (oracle["reported_point_eur"] - truth_total) / truth_total

        dilution_factor = len(exposed_ids) / len(true_ids)
        rows.append(
            {
                "dilution_ratio_k": ratio,
                "dilution_factor_exposed_over_true": dilution_factor,
                "exposed_n": len(exposed_ids),
                "truth_total_eur": truth_total,
                "whole_rule_reported_eur": whole_rule["reported_point_eur"],
                "whole_rule_signed_relative_error": whole_rule_signed_error,
                "oracle_overlap_conditioned_reported_eur": oracle["reported_point_eur"],
                "oracle_overlap_conditioned_signed_relative_error": oracle_signed_error,
            }
        )
        print(
            f"[{label}] k={ratio:>2} dilution={dilution_factor:5.1f}x  "
            f"whole_rule_error={whole_rule_signed_error:+.1%}  "
            f"oracle_error={oracle_signed_error:+.1%}"
        )
    return rows


def main() -> None:
    print("=== NEGATIVE CONTROL: diluting population i.i.d. with comparison (c=0) ===")
    negative = _run_sweep("negative", confound_c=0.0)

    print()
    print(f"=== POSITIVE CONTROL: diluting population carries a fixed confound c={CONFOUND_C} EUR ===")
    positive = _run_sweep("positive", confound_c=CONFOUND_C)

    def _pearson(xs: list[float], ys: list[float]) -> float | None:
        n = len(xs)
        if n < 2:
            return None
        mean_x, mean_y = sum(xs) / n, sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x == 0 or var_y == 0:
            return None
        return cov / (var_x * var_y) ** 0.5

    summary = {
        "negative_control": {
            "whole_rule_abs_error_range": [
                min(abs(r["whole_rule_signed_relative_error"]) for r in negative),
                max(abs(r["whole_rule_signed_relative_error"]) for r in negative),
            ],
            "pearson_dilution_vs_whole_rule_signed_error": _pearson(
                [r["dilution_factor_exposed_over_true"] for r in negative],
                [r["whole_rule_signed_relative_error"] for r in negative],
            ),
        },
        "positive_control": {
            "whole_rule_abs_error_range": [
                min(abs(r["whole_rule_signed_relative_error"]) for r in positive),
                max(abs(r["whole_rule_signed_relative_error"]) for r in positive),
            ],
            "oracle_abs_error_range": [
                min(abs(r["oracle_overlap_conditioned_signed_relative_error"]) for r in positive),
                max(abs(r["oracle_overlap_conditioned_signed_relative_error"]) for r in positive),
            ],
            "pearson_dilution_vs_whole_rule_signed_error": _pearson(
                [r["dilution_factor_exposed_over_true"] for r in positive],
                [r["whole_rule_signed_relative_error"] for r in positive],
            ),
            "pearson_dilution_vs_oracle_signed_error": _pearson(
                [r["dilution_factor_exposed_over_true"] for r in positive],
                [r["oracle_overlap_conditioned_signed_relative_error"] for r in positive],
            ),
        },
    }
    print()
    print("=== summary ===")
    print(json.dumps(summary, indent=2))

    out = {
        "design": {
            "N_BACKGROUND": N_BACKGROUND,
            "N_TRUE_AFFECTED": N_TRUE_AFFECTED,
            "TRUE_HARM": TRUE_HARM,
            "BACKGROUND_MEAN": BACKGROUND_MEAN,
            "NOISE_SD": NOISE_SD,
            "CONFOUND_C": CONFOUND_C,
            "DILUTION_RATIOS": DILUTION_RATIOS,
        },
        "summary": summary,
        "negative_control_sweep": negative,
        "positive_control_sweep": positive,
    }
    out_path = REPOSITORY / "docs/benchmark/task-084-branch4-controls-raw.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
