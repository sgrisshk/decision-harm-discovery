"""CODE_REVIEWER independent verification, Check 1 (ADR-086).

Independent re-implementation of TASK-084 branch 4's positive/negative control DESIGN, built
from scratch (different parameters, different seeds, finer dilution grid, multiple repetitions
per dilution point to test genuine monotonicity rather than a single noisy draw) but calling the
SAME real, unmodified estimator functions the production code uses
(policy_analytics.outcomes.summarize_group/raw_difference/harm_score,
policy_analytics.validation.apply.cluster_cells/cluster_bootstrap_replicates/percentile_ci,
policy_analytics.validation.economic_impact.build_economic_impact_result).

Does not import or reuse any code from scripts/diagnose_task084_branch4_controls.py -- the DGP,
outcome definition, and parameter values below are chosen independently to avoid quietly
re-deriving the same numbers by construction.
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
    cluster_bootstrap_replicates,
    cluster_cells,
    percentile_ci,
)
from policy_analytics.validation.economic_impact import build_economic_impact_result  # noqa: E402

# Independent parameter choices -- deliberately different from the production diagnostic script's
# N_BACKGROUND=6000, N_TRUE_AFFECTED=200, TRUE_HARM=80, BACKGROUND_MEAN=1000, NOISE_SD=120,
# CONFOUND_C=45.
N_BACKGROUND = 4000
N_TRUE = 150
TRUE_HARM = 55.0
BG_MEAN = 300.0
NOISE_SD = 60.0
CONFOUND_C = 22.0
CONF_LEVEL = 0.95
DIAG_REPS = 300

# Finer, non-integer-multiple grid than the production script's {0,1,2,5,10,20}, and each point
# repeated across 5 independent seeds to check whether the monotonic trend survives resampling
# noise, not just a single lucky draw.
DILUTION_RATIOS = [0, 1, 2, 3, 4, 6, 8, 12, 16, 24]
SEEDS = [11, 22, 33, 44, 55]


class _Outcome:
    outcome_id = "indep_check_outcome"
    column = "value"
    unit = "EUR"
    higher_is_worse = False
    harm_multiplier = -1


OUTCOME = _Outcome()


def make_frame(rng: random.Random, n_dilute: int, confound: float) -> tuple[pl.DataFrame, list[str], list[str]]:
    rows: list[dict[str, Any]] = []
    true_ids: list[str] = []
    exposed_ids: list[str] = []
    idx = 0
    for _ in range(N_BACKGROUND):
        rid = f"bg{idx}"
        idx += 1
        rows.append({"rid": rid, "cust": rid, "value": rng.gauss(BG_MEAN, NOISE_SD)})
    for _ in range(N_TRUE):
        rid = f"true{idx}"
        idx += 1
        rows.append({"rid": rid, "cust": rid, "value": rng.gauss(BG_MEAN - TRUE_HARM, NOISE_SD)})
        true_ids.append(rid)
        exposed_ids.append(rid)
    for _ in range(n_dilute):
        rid = f"dil{idx}"
        idx += 1
        rows.append({"rid": rid, "cust": rid, "value": rng.gauss(BG_MEAN - confound, NOISE_SD)})
        exposed_ids.append(rid)
    return pl.DataFrame(rows), true_ids, exposed_ids


def estimate(frame: pl.DataFrame, exposed_ids: list[str]) -> float:
    exposed_set = frozenset(exposed_ids)
    mask = pl.Series("m", [rid in exposed_set for rid in frame["rid"].to_list()])
    exposed = frame.filter(mask)[OUTCOME.column].to_list()
    comparison = frame.filter(~mask)[OUTCOME.column].to_list()
    es = summarize_group(exposed, OUTCOME)
    cs = summarize_group(comparison, OUTCOME)
    diff = raw_difference(es, cs)
    per_record = harm_score(diff, OUTCOME)
    n = es.n_present
    clusters = cluster_cells(frame, mask, OUTCOME.column, "cust")
    rng = random.Random(7)
    reps = cluster_bootstrap_replicates(clusters, DIAG_REPS, rng)
    exp_reps = [d * OUTCOME.harm_multiplier * n for d in reps]
    lo, hi = percentile_ci(exp_reps, CONF_LEVEL)
    historical_value = per_record * n
    result = build_economic_impact_result(
        outcome=OUTCOME,
        affected_records=n,
        per_record_value=per_record,
        per_record_ci_low=lo / n if n else 0.0,
        per_record_ci_high=hi / n if n else 0.0,
        confidence_level=CONF_LEVEL,
        historical_value=historical_value,
        historical_ci_low=lo,
        historical_ci_high=hi,
        materiality_pass=True,
    )
    return (result.historical_impact.ci_low + result.historical_impact.ci_high) / 2


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy) ** 0.5


def run(confound: float, label: str) -> dict[str, Any]:
    truth = TRUE_HARM * N_TRUE
    per_ratio_mean_error: list[tuple[int, float]] = []
    all_rows = []
    for ratio in DILUTION_RATIOS:
        errs = []
        for seed in SEEDS:
            rng = random.Random(seed * 1000 + ratio)
            n_dil = ratio * N_TRUE
            frame, true_ids, exposed_ids = make_frame(rng, n_dil, confound)
            reported = estimate(frame, exposed_ids)
            err = (reported - truth) / truth
            errs.append(err)
        mean_err = sum(errs) / len(errs)
        per_ratio_mean_error.append((ratio, mean_err))
        all_rows.append({"ratio": ratio, "dilution_factor": (N_TRUE + ratio * N_TRUE) / N_TRUE,
                          "seed_errors": errs, "mean_signed_error": mean_err})
        print(f"[{label}] k={ratio:>3} dilution={(N_TRUE+ratio*N_TRUE)/N_TRUE:5.1f}x "
              f"mean_error={mean_err:+.1%}  spread={min(errs):+.1%}..{max(errs):+.1%}")

    # Monotonicity check: count sign of successive differences in mean_signed_error
    diffs = [per_ratio_mean_error[i+1][1] - per_ratio_mean_error[i][1] for i in range(len(per_ratio_mean_error)-1)]
    n_increasing = sum(1 for d in diffs if d > 0)
    n_total = len(diffs)
    dilution_factors = [(N_TRUE + r * N_TRUE) / N_TRUE for r in DILUTION_RATIOS]
    mean_errors = [e for _, e in per_ratio_mean_error]
    r = pearson(dilution_factors, mean_errors)
    return {
        "label": label,
        "monotone_increasing_steps": f"{n_increasing}/{n_total}",
        "pearson_dilution_vs_mean_signed_error": r,
        "rows": all_rows,
    }


def main() -> None:
    print("=== INDEPENDENT NEGATIVE CONTROL (own params/seeds/grid) ===")
    neg = run(confound=0.0, label="negative")
    print()
    print("=== INDEPENDENT POSITIVE CONTROL (own params/seeds/grid) ===")
    pos = run(confound=CONFOUND_C, label="positive")
    print()
    print(json.dumps({"negative": {k: v for k, v in neg.items() if k != "rows"},
                       "positive": {k: v for k, v in pos.items() if k != "rows"}}, indent=2))
    out = {"negative_control": neg, "positive_control": pos}
    out_path = REPOSITORY / "docs/benchmark/task-084-review-check1-independent-controls-raw.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
