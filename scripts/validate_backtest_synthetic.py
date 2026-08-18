"""CLI: validate the TASK-032 backtest engine against synthetic ground truth (TASK-033).

Run only after `docs/analytics/policy-backtest-contract.md` and the engine's own code
(`packages/analytics/src/policy_analytics/backtest/`) were written and frozen — the same
sequencing discipline as `TASK-018`→`TASK-028`: methodology fixed *before* ground truth is opened,
here for grading the engine's correctness, never for tuning it afterward.

**What this validates, and how.** For each of the 9 hidden patterns, this script builds the exact
membership mask `hidden_ground_truth.json` already provides (`affected_booking_ids`), restricted
to `future_holdout`, and runs `backtest_from_mask()` directly on it — isolating the *engine's*
correctness (does `benefit`'s point estimate and bootstrap CI recover something close to the
pattern's own true effect, on the *true* affected population) from any candidate-matching/dilution
error, which is `TASK-028`'s already-diagnosed, separate problem
(`task-029-benchmark-report-v1.md` §3.6). It also runs the same engine, unadjusted, against each
of the 5 confounding traps' `apparent_feature` condition
(`evaluate_benchmark.TRAP_APPARENT_CONDITIONS`, reused rather than re-parsed) — traps have a
*known-zero* `direct_effect`, so a nonzero raw `benefit` there is an expected, disclosed
consequence of this being a mechanical, unadjusted replay, not a failure of the engine; it is
reported to keep that disclosure honest, not graded pass/fail.

**The comparison is an approximation, not exact ground truth**, disclosed in
`docs/analytics/policy-backtest-contract.md` §8: `hidden_ground_truth.json`'s
`realized_counterfactual_effects` is a whole-population paired-counterfactual mean, with no
`future_holdout`-only breakdown. "True" future_holdout benefit is approximated as
`mean_effect x |affected_booking_ids intersect future_holdout|`, assuming the per-booking effect
is homogeneous across time — the same category of assumption already used throughout this
benchmark, stated as an approximation here, not presented as exact.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

import polars as pl  # noqa: E402
from evaluate_benchmark import TRAP_APPARENT_CONDITIONS  # noqa: E402
from policy_analytics.backtest import BACKTEST_CONTRACT_VERSION, backtest_from_mask  # noqa: E402
from policy_analytics.outcomes import OutcomeDefinition, primary_outcome  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    BOOTSTRAP_SEED,
    Condition,
    load_analytical_frame,
    rule_expr,
)

DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
OUTPUT_PATH = REPOSITORY / "artifacts/backtest/task-033-backtest-validation.json"


def _pattern_result(
    pattern: dict[str, Any],
    holdout_ids: set[str],
    frame: pl.DataFrame,
    outcome: OutcomeDefinition,
    rng: random.Random,
) -> dict[str, Any]:
    affected = set(pattern["affected_booking_ids"])
    true_future_holdout_ids = affected & holdout_ids
    true_n = len(true_future_holdout_ids)
    mean_effect = pattern["realized_counterfactual_effects"]["outcomes"][outcome.outcome_id][
        "mean_effect"
    ]
    true_harm_per_booking = mean_effect * outcome.harm_multiplier
    true_benefit_approx = true_harm_per_booking * true_n

    holdout_frame = frame.filter(pl.col("split_label") == "future_holdout")  # pyright: ignore[reportUnknownMemberType]
    mask = holdout_frame["booking_id"].is_in(list(true_future_holdout_ids))

    entry: dict[str, Any] = {
        "pattern_id": pattern["id"],
        "name": pattern["name"],
        "true_future_holdout_n": true_n,
        "true_harm_per_booking_eur": true_harm_per_booking,
        "true_benefit_future_holdout_approx_eur": true_benefit_approx,
    }
    if true_n == 0:
        entry["skipped_reason"] = "pattern has no affected bookings in future_holdout"
        return entry
    try:
        result = backtest_from_mask(
            frame=frame, rule_mask_within_holdout=mask, outcome=outcome, rng=rng
        )
    except ValueError as exc:
        entry["skipped_reason"] = str(exc)
        return entry

    relative_error = (
        abs(result.benefit.value - true_benefit_approx) / abs(true_benefit_approx)
        if true_benefit_approx
        else None
    )
    direction_correct = (result.benefit.value > 0) == (true_benefit_approx > 0)
    entry["engine_result"] = result.to_dict()
    entry["relative_error"] = relative_error
    entry["direction_correct"] = direction_correct
    return entry


def _trap_result(
    trap_id: str,
    condition: tuple[str, str, object],
    frame: pl.DataFrame,
    outcome: OutcomeDefinition,
    rng: random.Random,
) -> dict[str, Any]:
    feature, operator, value = condition
    holdout_frame = frame.filter(pl.col("split_label") == "future_holdout")  # pyright: ignore[reportUnknownMemberType]
    mask = holdout_frame.select(
        rule_expr([Condition(feature, operator, value)]).alias("m")  # type: ignore[arg-type]
    )["m"]
    entry: dict[str, Any] = {
        "trap_id": trap_id,
        "apparent_condition": f"{feature} {operator} {value}",
        "true_direct_effect": 0,
    }
    try:
        result = backtest_from_mask(
            frame=frame, rule_mask_within_holdout=mask, outcome=outcome, rng=rng
        )
    except ValueError as exc:
        entry["skipped_reason"] = str(exc)
        return entry
    entry["engine_result"] = result.to_dict()
    entry["note"] = (
        "A nonzero raw benefit here, despite a known-zero true direct effect, is an expected "
        "consequence of this being an unadjusted mechanical replay (docs/analytics/"
        "policy-backtest-contract.md §4) — not a pass/fail check, a disclosure check."
    )
    return entry


def main() -> None:
    if OUTPUT_PATH.exists():
        print(
            f"{OUTPUT_PATH} already exists and is a frozen result. Refusing to overwrite.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    frame = load_analytical_frame(DATASET_ROOT)
    holdout_ids = set(
        frame.filter(pl.col("split_label") == "future_holdout")["booking_id"].to_list()  # pyright: ignore[reportUnknownMemberType]
    )
    outcome = primary_outcome()
    rng = random.Random(BOOTSTRAP_SEED)

    patterns = [
        _pattern_result(pattern, holdout_ids, frame, outcome, rng)
        for pattern in ground_truth["patterns"]
    ]
    traps = [
        _trap_result(trap_id, condition, frame, outcome, rng)
        for trap_id, condition in TRAP_APPARENT_CONDITIONS.items()
    ]

    scored_patterns = [
        p for p in patterns if "relative_error" in p and p["relative_error"] is not None
    ]
    relative_errors = sorted(p["relative_error"] for p in scored_patterns)
    median_relative_error = None
    if relative_errors:
        mid = len(relative_errors) // 2
        median_relative_error = (
            relative_errors[mid]
            if len(relative_errors) % 2 == 1
            else (relative_errors[mid - 1] + relative_errors[mid]) / 2
        )
    direction_correct_count = sum(1 for p in scored_patterns if p["direction_correct"])

    payload = {
        "status": "FROZEN",
        "frozen_at": datetime.now(UTC).isoformat(),
        "task": "TASK-033",
        "backtest_contract_version": BACKTEST_CONTRACT_VERSION,
        "hidden_ground_truth_opened": True,
        "hidden_ground_truth_opened_note": (
            "Legitimate: methodology (docs/analytics/policy-backtest-contract.md) and the "
            "engine's own code were written and frozen before this script ever ran."
        ),
        "approximation_note": (
            "true_benefit_future_holdout_approx_eur assumes a homogeneous per-booking effect "
            "across time (mean_effect x overlap count) — see policy-backtest-contract.md §8."
        ),
        "patterns": patterns,
        "traps": traps,
        "summary": {
            "scored_pattern_count": len(scored_patterns),
            "skipped_pattern_count": len(patterns) - len(scored_patterns),
            "median_relative_error": median_relative_error,
            "direction_correct": direction_correct_count,
            "direction_total": len(scored_patterns),
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Scored patterns: {len(scored_patterns)}/9")
    print(f"Median relative error: {median_relative_error}")
    print(f"Direction correct: {direction_correct_count}/{len(scored_patterns)}")
    for p in patterns:
        if "skipped_reason" in p:
            print(f"  SKIPPED {p['pattern_id']}: {p['skipped_reason']}")
        else:
            print(
                f"  {p['pattern_id']}: relative_error={p['relative_error']:.1%} "
                f"direction_correct={p['direction_correct']}"
            )
    for t in traps:
        if "skipped_reason" in t:
            print(f"  SKIPPED trap {t['trap_id']}: {t['skipped_reason']}")
        else:
            benefit_value = t["engine_result"]["benefit"]["value"]
            print(f"  trap {t['trap_id']}: raw benefit={benefit_value:.0f}")


if __name__ == "__main__":
    main()
