"""TASK-112 Step 3 -- pure aggregation over `step3-decomposition-raw-modified-engine.json`
(computed by `step3_decompose.py` through the real, Step-2-modified `_development_score`).

Computes, per target, the Mechanism PASS inputs: preference consistency (broad vs specific raw
score), Delta-score distribution, and a comparison of the median Delta-score against the
already-committed OLD-formula number (`docs/benchmark/task-111-evidence/h111-analysis-summary.json`)
to state explicitly whether each of the 7 H111-positive FNs moved in the predicted (decreasing)
direction, and by how much, under the real modified engine -- not a hand recomputation.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RAW = json.loads((OUT / "step3-decomposition-raw-modified-engine.json").read_text())
OLD_SUMMARY = json.loads(
    (REPO / "docs/benchmark/task-111-evidence/h111-analysis-summary.json").read_text()
)

TARGETS = ("C02", "C04", "C06", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
GUARD = "C07"
ALL_TARGETS = TARGETS + (GUARD,)
H111_POSITIVE_FNS = ("C04", "C06", "C09", "C12", "C14", "C15", "H01")
SEEDS = sorted(int(s) for s in RAW.keys())


def analyze_pair(tid: str, which: str) -> dict:
    per_seed = []
    for seed in SEEDS:
        entry = RAW[str(seed)][tid]
        specific = entry["specific_direct"]
        broad = entry[which]
        s_score, b_score = specific["development_score"], broad["development_score"]
        delta = (b_score - s_score) if (s_score is not None and b_score is not None) else None
        per_seed.append(
            {
                "seed": seed,
                "specific_eligible": specific["eligible"],
                "broad_eligible": broad["eligible"],
                "specific_score": s_score,
                "broad_score": b_score,
                "delta_score": delta,
                "broad_wins": (delta > 0) if delta is not None else None,
            }
        )
    deltas = [p["delta_score"] for p in per_seed if p["delta_score"] is not None]
    wins = [p["broad_wins"] for p in per_seed if p["broad_wins"] is not None]
    n_broad_wins = sum(1 for w in wins if w)
    n_compared = len(wins)
    return {
        "target": tid,
        "comparison": which,
        "n_seeds_both_eligible_and_comparable": n_compared,
        "n_broad_wins": n_broad_wins,
        "n_specific_wins": n_compared - n_broad_wins,
        "all_30_sign_consistent": (n_broad_wins == n_compared or n_broad_wins == 0)
        if n_compared == 30
        else None,
        "delta_score_mean": st.mean(deltas) if deltas else None,
        "delta_score_median": st.median(deltas) if deltas else None,
        "delta_score_min": min(deltas) if deltas else None,
        "delta_score_max": max(deltas) if deltas else None,
        "per_seed": per_seed,
    }


def main() -> None:
    report = {"targets": {}}
    for tid in ALL_TARGETS:
        report["targets"][tid] = {
            "vs_named_competitor": analyze_pair(tid, "named_competitor_direct"),
        }

    (OUT / "step3-analysis-summary.json").write_text(
        json.dumps(report, indent=1, sort_keys=True, default=str)
    )

    print(f"{'target':6} {'old_med_delta':>14} {'new_med_delta':>14} {'decreased':>10} {'sign':>6} {'n_broad_wins_new':>17}")
    mechanism_pass_count = 0
    no_large_reversal = True
    for tid in H111_POSITIVE_FNS:
        old = OLD_SUMMARY["targets"][tid]["vs_named_competitor"]
        new = report["targets"][tid]["vs_named_competitor"]
        decreased = new["delta_score_median"] < old["delta_score_median"]
        if decreased:
            mechanism_pass_count += 1
        # "large reversal in the opposite direction" = new median delta is MORE positive than old
        # by a wide margin (not merely noise). None of the 7 should ever increase.
        reversal = new["delta_score_median"] > old["delta_score_median"]
        if reversal:
            no_large_reversal = False
        print(
            f"{tid:6} {old['delta_score_median']:14.1f} {new['delta_score_median']:14.1f} "
            f"{str(decreased):>10} {('rev!' if reversal else 'ok'):>6} {new['n_broad_wins']:>17}"
        )

    guard_old = OLD_SUMMARY["guard_C07"]["vs_named_competitor"]
    guard_new = report["targets"][GUARD]["vs_named_competitor"]
    print()
    print(f"C07 guard: old_med_delta={guard_old['delta_score_median']:.1f} new_med_delta={guard_new['delta_score_median']:.1f}")

    c11_old = OLD_SUMMARY["targets"]["C11"]["vs_named_competitor"]
    c11_new = report["targets"]["C11"]["vs_named_competitor"]
    print(f"C11 control: old_med_delta={c11_old['delta_score_median']:.1f} new_med_delta={c11_new['delta_score_median']:.1f} (not used as pass/fail evidence)")

    print()
    verdict = mechanism_pass_count >= 5 and no_large_reversal
    print(f"MECHANISM PASS BAR: {mechanism_pass_count}/7 decreased as predicted, no_large_reversal={no_large_reversal}")
    print(f"STEP 3 VERDICT: {'PASS' if verdict else 'FAIL'}")

    report["mechanism_pass_verdict"] = {
        "n_of_7_decreased": mechanism_pass_count,
        "no_large_reversal": no_large_reversal,
        "verdict": "PASS" if verdict else "FAIL",
    }
    (OUT / "step3-analysis-summary.json").write_text(
        json.dumps(report, indent=1, sort_keys=True, default=str)
    )


if __name__ == "__main__":
    main()
