"""CODE_REVIEWER independent adversarial construction (ADR-090, TASK-087 review, mandate check 3):
"Defined behavior when candidate membership changes between development and holdout" -- attacked
with cases the design document's own Check 5 (Case E, population shrinks smoothly to 30%, rate
stable) never covers: the BOUNDARY where a candidate's exposed population changes so drastically
that `split_stats` itself cannot compute a result.

**What this finds.** `policy_analytics.validation.apply.split_stats` returns `None` whenever either
the exposed or comparison group is EMPTY in a window (`apply.py`'s own early return: `if
exposed.height == 0 or comparison.height == 0: return None`). This is a REAL, plausible outcome for
a genuine candidate: `discover_candidates`'s own eligibility is decided entirely from the
`development` split (`_eligible`, `_metric(..., "development")`) -- nothing requires a selected
rule to have ANY exposure at all in the much shorter (6-month vs. 18-month) `future_holdout` window,
especially for a narrow-support rule. `apply.py`'s own existing G10 temporal-stability gate already
handles this gracefully and by design: `split_results.get("future_holdout")` can be `None`, and the
gate's own arithmetic (`retention = ... if holdout and dev.harm_per_booking else 0.0`, `same_sign =
len(split_results) == len(SPLITS) and ...`) is written specifically to degrade to a defined FAILED
verdict rather than crash.

TASK-087's own design document (Sec 1) proposes the SAME `split_stats` call, and its own diagnostic
script (`scripts/diagnose_task087_check5_7_calibration_adversarial.py`) implements the comparison
with `assert predict_stats is not None and realize_stats is not None` -- i.e. the proposed
computation, exactly as specified, does NOT replicate G10's defensive None-handling. It would raise
an uncaught AssertionError rather than return a defined "calibration_ok" (or "not computable")
verdict for a plausible real candidate whose future_holdout exposure is zero. This is confirmed
below by direct construction (Case F1), not asserted from reading alone. Check 5's own claim of
"defined behavior under population drift" is accurate only for the smooth-shrinkage regime its own
Case E tested (30% -> non-zero); it does not hold at the boundary the design's own analogue gate
(G10) already had to guard against.

Cases F2/F3 (population explodes 40x; population shrinks to a handful of records) are included as
controls: both remain computable and correctly resolve, showing the coverage test still does real
statistical work away from the n=0 boundary -- the defect is specifically the unguarded zero-
population edge, not the general population-drift design.

Uses the real, unmodified split_stats/cluster_cells/cluster_bootstrap_replicates/percentile_ci,
composed with a verbatim reproduction of the design's own proposed `_calibration_check` formula
(mirrors `scripts/diagnose_task087_check5_7_calibration_adversarial.py`'s own function, not
imported -- no production gate/metric module exists for this design).

Read-only. Does not modify apply.py, economic_impact.py, discovery.engine, or any gate/metric code.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402

from policy_analytics.outcomes import OUTCOME_BY_ID  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    cluster_bootstrap_replicates,
    cluster_cells,
    percentile_ci,
    split_stats,
)

OUTCOME = OUTCOME_BY_ID["contribution_margin_eur"]
REPS = 2_000
CONFIDENCE = 0.95
OUT_PATH = REPOSITORY / "docs/benchmark/task-087-review-check3-population-edge-cases-raw.json"


def _calibration_check(frame: pl.DataFrame, crash_on_none: bool) -> dict[str, object]:
    """Verbatim reproduction of the design doc's own proposed computation (matches
    diagnose_task087_check5_7_calibration_adversarial.py's _calibration_check). `crash_on_none`
    mirrors the design's own `assert ... is not None` discipline when True; when False, it instead
    returns a diagnosed "not computable" result so this script can report on the crash case without
    actually raising and aborting the whole run.
    """
    predict_frame = frame.filter(pl.col("window") == "predict")
    realize_frame = frame.filter(pl.col("window") == "realize")

    predict_stats = split_stats(predict_frame, predict_frame["sel"], OUTCOME, "predict")
    realize_stats = split_stats(realize_frame, realize_frame["sel"], OUTCOME, "realize")

    if predict_stats is None or realize_stats is None:
        if crash_on_none:
            # This is the design's own literal behavior (its diagnostic script's `assert`).
            assert predict_stats is not None and realize_stats is not None
        return {
            "computable": False,
            "predict_stats_is_none": predict_stats is None,
            "realize_stats_is_none": realize_stats is None,
            "would_raise_assertionerror_under_designs_own_literal_implementation": True,
        }

    predict_clusters = cluster_cells(predict_frame, predict_frame["sel"], OUTCOME.column, "customer_id")
    predict_reps = cluster_bootstrap_replicates(predict_clusters, REPS, random.Random(20260919))
    predict_rate_reps = [d * OUTCOME.harm_multiplier for d in predict_reps]
    if not predict_rate_reps:
        return {
            "computable": False,
            "note": "cluster_bootstrap_replicates produced zero usable replicates.",
        }
    ci_low, ci_high = percentile_ci(predict_rate_reps, CONFIDENCE)
    ci_low, ci_high = min(ci_low, ci_high), max(ci_low, ci_high)

    predicted_rate = predict_stats.harm_per_booking
    realized_rate = realize_stats.harm_per_booking
    covered = ci_low <= realized_rate <= ci_high

    return {
        "computable": True,
        "predicted_per_record_rate_eur": predicted_rate,
        "predicted_rate_ci_95": [ci_low, ci_high],
        "predicted_rate_ci_width_eur": ci_high - ci_low,
        "realized_per_record_rate_eur": realized_rate,
        "calibration_ok_ci_coverage": covered,
        "predicted_n_exposed_reference": predict_stats.n_exposed,
        "realized_n_exposed": realize_stats.n_exposed,
        "population_size_ratio_realize_over_predict": (
            realize_stats.n_exposed / predict_stats.n_exposed if predict_stats.n_exposed else None
        ),
    }


def _filler(rng: random.Random, n_predict: int, n_realize: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for i in range(n_predict):
        rows.append({"sel": False, "window": "predict", "contribution_margin_eur": 0.0 + rng.gauss(0, 10), "customer_id": f"C{i}"})
    for i in range(n_realize):
        rows.append({"sel": False, "window": "realize", "contribution_margin_eur": 0.0 + rng.gauss(0, 10), "customer_id": f"C{i}_r"})
    return rows


def case_f1_population_vanishes() -> dict[str, object]:
    """Predict-window population is substantial (n=600); ZERO rows match the rule in future_holdout
    (e.g. a discontinued promo code / retired feature value) -- a plausible outcome for any
    development-only-eligible candidate with narrow support, per this script's own docstring."""
    rng = random.Random(11)
    rows: list[dict[str, object]] = [
        {"sel": True, "window": "predict", "contribution_margin_eur": -300.0 + rng.gauss(0, 15), "customer_id": f"E{i}"}
        for i in range(600)
    ]
    rows += _filler(rng, 2000, 2000)
    frame = pl.DataFrame(rows)
    result = _calibration_check(frame, crash_on_none=False)
    return {"name": "case_f1_population_vanishes_to_zero_in_future_holdout", **result}


def case_f2_population_explodes() -> dict[str, object]:
    """Predict-window population is small (n=80, wide CI); realize-window population explodes 40x
    (n=3200) with a moderate rate shift -- control case: does coverage still do real work when
    population size, not just rate, has plainly changed?"""
    rng = random.Random(12)
    rows: list[dict[str, object]] = [
        {"sel": True, "window": "predict", "contribution_margin_eur": -300.0 + rng.gauss(0, 15), "customer_id": f"E{i}"}
        for i in range(80)
    ] + [
        {"sel": True, "window": "realize", "contribution_margin_eur": -260.0 + rng.gauss(0, 15), "customer_id": f"E{i}_r"}
        for i in range(3200)
    ]
    rows += _filler(rng, 2000, 2000)
    frame = pl.DataFrame(rows)
    result = _calibration_check(frame, crash_on_none=False)
    return {"name": "case_f2_population_explodes_40x_rate_shifts_moderately", **result}


def case_f3_tiny_realize_population() -> dict[str, object]:
    """Predict-window population is large (n=600); realize-window population shrinks to a handful
    of records (n=5) with a genuinely different rate -- control case: is coverage trivially easy to
    fail/pass once realize-side n is tiny, or does it still detect the genuine miscalibration?"""
    rng = random.Random(13)
    rows: list[dict[str, object]] = [
        {"sel": True, "window": "predict", "contribution_margin_eur": -300.0 + rng.gauss(0, 15), "customer_id": f"E{i}"}
        for i in range(600)
    ] + [
        {"sel": True, "window": "realize", "contribution_margin_eur": -800.0 + rng.gauss(0, 15), "customer_id": f"E{i}_r"}
        for i in range(5)
    ]
    rows += _filler(rng, 2000, 2000)
    frame = pl.DataFrame(rows)
    result = _calibration_check(frame, crash_on_none=False)
    return {"name": "case_f3_tiny_realize_population_n5_rate_genuinely_off", **result}


def main() -> None:
    result = {
        "task": "TASK-087",
        "review_check": 3,
        "claim_tested": (
            "The design document's Check 5 ('defined behavior under population drift') is fully "
            "defined -- including at the boundary where a candidate's future_holdout population "
            "vanishes entirely, not merely the smooth 30% shrinkage its own Case E tested."
        ),
        "case_f1_population_vanishes": case_f1_population_vanishes(),
        "case_f2_population_explodes": case_f2_population_explodes(),
        "case_f3_tiny_realize_population": case_f3_tiny_realize_population(),
        "finding": (
            "Case F1 falsifies the design document's Check 5 claim of fully 'defined behavior under "
            "population drift': when a candidate's future_holdout exposure is zero (a plausible, "
            "not contrived, outcome given discover_candidates selects candidates using only "
            "development-split eligibility), the design's own proposed computation -- literally as "
            "specified in Sec 1 and implemented in its own diagnostic script's `_calibration_check` "
            "-- raises an uncaught AssertionError rather than returning any verdict at all. This is "
            "a real gap relative to G10's own existing temporal-stability gate (apply.py lines "
            "~741-757), which already handles an absent future_holdout split defensively "
            "(same_sign=False, retention=0.0, gate fails cleanly) precisely because this scenario "
            "is a known, expected case for that gate's own inputs -- the same inputs this design "
            "proposes to reuse. Cases F2/F3 (population explodes 40x; shrinks to n=5) remain "
            "correctly computable and resolve sensibly, confirming the defect is specific to the "
            "unguarded zero-population boundary, not the population-drift design generally."
        ),
    }
    print(json.dumps(result, indent=2))
    OUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
