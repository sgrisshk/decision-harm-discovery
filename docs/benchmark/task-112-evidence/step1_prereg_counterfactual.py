"""TASK-112 Step 1 -- pre-registered counterfactual, BEFORE any engine code change.

Read-only. Does not run the engine, does not touch engine.py, and does not use seeds other than
the already-committed TASK-111 decomposition raw data (itself computed from TASK-109's 4001-4030
engine-raw files). This script recomputes, by hand, what each already-recorded (harm_per_booking,
n_exposed, k) triple would score under the ONE proposed parameter-free modification, and compares
the resulting Delta-score direction against the already-committed OLD-formula Delta-score (H111's
own `h111-analysis-summary.json`). No new engine run occurs here -- see ADR-113 Decision 2.

The proposed modification (see docs/benchmark/task-112-evidence/step1_formula_derivation.md for the
full "is there a parameter-free form" reasoning): drop `_development_score`'s
`n_exposed ** population_score_exponent` term entirely (equivalent to the term's natural
exponent -> 0 special case, i.e. population_component == 1 unconditionally), leaving the formula
purely rate-based:

    OLD: score = harm_per_booking * n_exposed**0.5            / (1 + 0.15*(k-1))
    NEW: score = harm_per_booking                              / (1 + 0.15*(k-1))

No new free coefficient is introduced -- the complexity penalty (0.15) is untouched, and the
population term is removed, not reparameterized to some other value someone picked.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RAW = json.loads(
    (REPO / "docs/benchmark/task-111-evidence/h111-decomposition-raw.json").read_text()
)
OLD_SUMMARY = json.loads(
    (REPO / "docs/benchmark/task-111-evidence/h111-analysis-summary.json").read_text()
)

SEEDS = list(range(4001, 4031))
H111_POSITIVE_FNS = ["C04", "C06", "C09", "C12", "C14", "C15", "H01"]
CONTROL = "C11"
GUARD = "C07"
ALL_TARGETS = H111_POSITIVE_FNS + [CONTROL, GUARD]


def new_score(harm_per_booking: float, k: int) -> float:
    """The one proposed modification: no population/volume term at all."""
    return harm_per_booking / (1.0 + 0.15 * (k - 1))


def old_score(harm_per_booking: float, n_exposed: int, k: int) -> float:
    """Recompute the real, current formula from the same raw numbers, as a cross-check that this
    script's inputs reproduce the already-committed `development_score` field exactly."""
    return harm_per_booking * (n_exposed ** 0.5) / (1.0 + 0.15 * (k - 1))


def main() -> None:
    report: dict = {"per_target": {}, "cross_check": {"max_abs_relative_error": 0.0}}
    max_rel_err = 0.0

    for tid in ALL_TARGETS:
        rows = []
        for seed in SEEDS:
            entry = RAW[str(seed)][tid]
            spec = entry["specific_direct"]
            comp = entry["named_competitor_direct"]
            if spec["harm_per_booking"] is None or comp["harm_per_booking"] is None:
                continue
            # cross-check: recomputed OLD score from raw fields must match the committed
            # development_score field already in h111-decomposition-raw.json (sanity: confirms
            # this script reads the real recorded harm_per_booking/n_exposed/k correctly).
            for side in (spec, comp):
                recomputed = old_score(side["harm_per_booking"], side["n_exposed"], side["k"])
                committed = side["development_score"]
                rel_err = abs(recomputed - committed) / max(abs(committed), 1e-9)
                max_rel_err = max(max_rel_err, rel_err)

            delta_old = comp["development_score"] - spec["development_score"]
            delta_new = new_score(comp["harm_per_booking"], comp["k"]) - new_score(
                spec["harm_per_booking"], spec["k"]
            )
            rows.append(
                {
                    "seed": seed,
                    "n_exposed_specific": spec["n_exposed"],
                    "n_exposed_competitor": comp["n_exposed"],
                    "delta_score_old": delta_old,
                    "delta_score_new": delta_new,
                }
            )

        deltas_old = [r["delta_score_old"] for r in rows]
        deltas_new = [r["delta_score_new"] for r in rows]
        n_ratio = statistics.median(
            [r["n_exposed_competitor"] / r["n_exposed_specific"] for r in rows]
        )
        report["per_target"][tid] = {
            "n_seeds": len(rows),
            "median_delta_old": statistics.median(deltas_old),
            "median_delta_new": statistics.median(deltas_new),
            "mean_delta_old": statistics.mean(deltas_old),
            "mean_delta_new": statistics.mean(deltas_new),
            "n_broad_wins_new": sum(1 for d in deltas_new if d > 0),
            "n_specific_wins_new": sum(1 for d in deltas_new if d < 0),
            "all_30_sign_consistent_new": len({d > 0 for d in deltas_new}) == 1,
            "median_n_exposed_ratio_competitor_over_specific": n_ratio,
            "predicted_direction": "decrease" if tid != GUARD else "n/a (guard, not a target)",
            "median_decreased_old_to_new": statistics.median(deltas_new)
            < statistics.median(deltas_old),
            "rows": rows,
        }

    report["cross_check"]["max_abs_relative_error"] = max_rel_err
    report["cross_check"]["note"] = (
        "Recomputing the OLD formula from this script's own raw-field reads must match the "
        "committed development_score field from TASK-111's raw data to near machine precision -- "
        "confirms this script is reading the real recorded harm_per_booking/n_exposed/k, not "
        "transcribed numbers."
    )

    out = Path(__file__).resolve().parent / "step1-prereg-counterfactual-results.json"
    out.write_text(json.dumps(report, indent=1, sort_keys=True))
    print("wrote", out)
    print()
    print(f"{'target':6} {'med_old':>12} {'med_new':>12} {'n_ratio':>9} {'decreased':>10} {'sign_consist':>13}")
    for tid in ALL_TARGETS:
        e = report["per_target"][tid]
        print(
            f"{tid:6} {e['median_delta_old']:12.1f} {e['median_delta_new']:12.1f} "
            f"{e['median_n_exposed_ratio_competitor_over_specific']:9.2f} "
            f"{str(e['median_decreased_old_to_new']):>10} {str(e['all_30_sign_consistent_new']):>13}"
        )
    print()
    print("max_abs_relative_error (cross-check):", max_rel_err)


if __name__ == "__main__":
    main()
