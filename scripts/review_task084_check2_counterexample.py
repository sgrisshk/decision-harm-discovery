"""CODE_REVIEWER Check 2 (ADR-086): synthetic counterexample hunting for a per-booking estimator
defect that would silently shrink under the doubly-narrowed diagnostic's own transformation,
INDEPENDENT of whether real surrogate-rule dilution confounding is present.

Design: a true pattern of `PATTERN_TOTAL` records, true per-record harm `TRUE_HARM`. The
candidate's rule captures only `RECALL` fraction of the true pattern (overlap_n) AND admits
`k * overlap_n` diluting records that are i.i.d. with the pure background (confound_c = 0 --
deliberately NO surrogate-rule confounding at all, to isolate whether ANYTHING else can still
produce dilution-correlated, narrowing-sensitive error).

On top of this "clean" (no surrogate confound) DGP, inject an INDEPENDENT per-record measurement
bias BUG_DELTA applied uniformly to every record the candidate's rule admits as "exposed"
(both the true-overlap records and the diluting records) -- representing a hypothetical estimator/
pipeline defect (e.g. a unit-conversion or feature-timing bug tied to whatever the surrogate
condition selects on) that has NOTHING to do with the true pattern's own effect and nothing to do
with population dilution as a *concept* -- it is a fixed EUR/record measurement artifact, not a
"the diluted population has its own real association with the outcome" story.

Uses the real, unmodified estimator functions throughout (summarize_group/raw_difference/
harm_score/cluster_bootstrap_replicates/build_economic_impact_result), and replicates the
production doubly-narrowed diagnostic's own comparison-group convention exactly (comparison =
"everyone outside the overlap", i.e. diluting records fall into the comparison group under
doubly-narrowing, not the whole-rule exposed group) -- this is the precise mechanism this check is
required to probe.
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

N_BACKGROUND = 8000
PATTERN_TOTAL = 300
TRUE_HARM = 70.0
BG_MEAN = 500.0
NOISE_SD = 90.0
RECALL = 0.65
CONF_LEVEL = 0.95
DIAG_REPS = 400
BUG_DELTA = 25.0  # EUR/record, independent measurement artifact -- present on ALL rule-admitted
# records (overlap AND diluting), NOT scaled by dilution intentionally -- a per-record constant.

DILUTION_RATIOS = [0, 2, 5, 10, 20]


class _Outcome:
    outcome_id = "check2_outcome"
    column = "value"
    unit = "EUR"
    higher_is_worse = False
    harm_multiplier = -1


OUTCOME = _Outcome()


def make_frame(rng: random.Random, n_dilute: int, bug_delta: float) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    idx = 0

    for _ in range(N_BACKGROUND):
        rid = f"bg{idx}"; idx += 1
        rows.append({"rid": rid, "cust": rid, "value": rng.gauss(BG_MEAN, NOISE_SD)})

    overlap_n = round(PATTERN_TOTAL * RECALL)
    uncaptured_n = PATTERN_TOTAL - overlap_n
    overlap_ids: list[str] = []
    for _ in range(overlap_n):
        rid = f"ovl{idx}"; idx += 1
        # true harm + independent bug delta (present because this record IS captured by the rule)
        rows.append({"rid": rid, "cust": rid, "value": rng.gauss(BG_MEAN - TRUE_HARM - bug_delta, NOISE_SD)})
        overlap_ids.append(rid)
    for _ in range(uncaptured_n):
        rid = f"unc{idx}"; idx += 1
        # true harm present (real pattern member) but NOT captured by the rule -> no bug_delta,
        # sits in "comparison" for every variant, exactly like the real recall<1 case.
        rows.append({"rid": rid, "cust": rid, "value": rng.gauss(BG_MEAN - TRUE_HARM, NOISE_SD)})

    diluting_ids: list[str] = []
    for _ in range(n_dilute):
        rid = f"dil{idx}"; idx += 1
        # i.i.d. with background (confound_c = 0, NO real surrogate-confounding) + the SAME
        # independent bug_delta (present because this record is also rule-admitted / "exposed").
        rows.append({"rid": rid, "cust": rid, "value": rng.gauss(BG_MEAN - bug_delta, NOISE_SD)})
        diluting_ids.append(rid)

    exposed_ids = overlap_ids + diluting_ids
    frame = pl.DataFrame(rows)
    return {
        "frame": frame,
        "overlap_ids": frozenset(overlap_ids),
        "exposed_ids": frozenset(exposed_ids),
        "pattern_affected_total": PATTERN_TOTAL,
    }


def _summarize(frame: pl.DataFrame, mask: pl.Series) -> float:
    """Return the point per-record harm estimate for `mask`=exposed vs ~mask=comparison."""
    exposed = frame.filter(mask)[OUTCOME.column].to_list()
    comparison = frame.filter(~mask)[OUTCOME.column].to_list()
    es = summarize_group(exposed, OUTCOME)
    cs = summarize_group(comparison, OUTCOME)
    return harm_score(raw_difference(es, cs), OUTCOME)


def _reported_ci_midpoint(frame: pl.DataFrame, mask: pl.Series, n: int, per_record: float) -> float:
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


def run_one(seed: int, ratio: int) -> dict[str, Any]:
    rng = random.Random(seed)
    overlap_n_target = round(PATTERN_TOTAL * RECALL)
    n_dilute = ratio * overlap_n_target
    data = make_frame(rng, n_dilute, BUG_DELTA)
    frame = data["frame"]
    exposed_ids = data["exposed_ids"]
    overlap_ids = data["overlap_ids"]
    pattern_total = data["pattern_affected_total"]

    rids = frame["rid"].to_list()
    exposed_mask = pl.Series("m", [r in exposed_ids for r in rids])
    overlap_mask = pl.Series("m", [r in overlap_ids for r in rids])

    exposed_n = int(exposed_mask.sum())
    overlap_n = int(overlap_mask.sum())

    truth = TRUE_HARM * pattern_total  # the true pattern's FULL economic impact (bug-free)

    # whole-rule
    whole_per_record = _summarize(frame, exposed_mask)
    whole_reported = _reported_ci_midpoint(frame, exposed_mask, exposed_n, whole_per_record)
    whole_err = (whole_reported - truth) / truth

    # attribution-narrowed (TASK-059 style): reuse whole-rule per-record effect, scale by overlap_n
    attrib_reported = whole_per_record * overlap_n
    attrib_err = (attrib_reported - truth) / truth

    # doubly-narrowed: recompute per-record effect fresh over the overlap population, comparison =
    # everyone OUTSIDE the overlap (the real production diagnostic's own convention -- this pulls
    # diluting records, which also carry BUG_DELTA, into the comparison side)
    if overlap_n == 0:
        doubly_err = None
        doubly_per_record = None
    else:
        doubly_per_record = _summarize(frame, overlap_mask)
        doubly_reported = _reported_ci_midpoint(frame, overlap_mask, overlap_n, doubly_per_record)
        doubly_err = (doubly_reported - truth) / truth

    return {
        "seed": seed,
        "dilution_ratio_k": ratio,
        "dilution_factor": exposed_n / overlap_n if overlap_n else None,
        "exposed_n": exposed_n,
        "overlap_n": overlap_n,
        "whole_per_record_effect": whole_per_record,
        "whole_rule_signed_error": whole_err,
        "attribution_narrowed_signed_error": attrib_err,
        "doubly_narrowed_per_record_effect": doubly_per_record,
        "doubly_narrowed_signed_error": doubly_err,
    }


def main() -> None:
    print(f"=== Check 2 synthetic counterexample: independent BUG_DELTA={BUG_DELTA} EUR/record, "
          f"ZERO surrogate confound (confound_c=0), RECALL={RECALL} ===")
    rows = []
    for ratio in DILUTION_RATIOS:
        seed_rows = [run_one(1000 + ratio * 7 + s, ratio) for s in range(4)]
        n = len(seed_rows)
        avg = {
            "dilution_ratio_k": ratio,
            "dilution_factor": sum(r["dilution_factor"] for r in seed_rows) / n,
            "mean_whole_rule_signed_error": (
                sum(r["whole_rule_signed_error"] for r in seed_rows) / n
            ),
            "mean_attribution_narrowed_signed_error": (
                sum(r["attribution_narrowed_signed_error"] for r in seed_rows) / n
            ),
            "mean_doubly_narrowed_signed_error": (
                sum(r["doubly_narrowed_signed_error"] for r in seed_rows) / n
            ),
        }
        rows.append(avg)
        print(json.dumps(avg, indent=2))

    out_path = REPOSITORY / "docs/benchmark/task-084-review-check2-counterexample-raw.json"
    out_path.write_text(json.dumps(rows, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
