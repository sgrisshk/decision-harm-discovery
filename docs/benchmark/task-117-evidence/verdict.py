"""TASK-117: aggregate per-seed raw output and apply the pre-registered H117 verdict rule
(`preregistration.md`). Pure read + count; no engine call.
  python verdict.py > verdict.json
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
STRONG = ("C04", "C06", "C09", "C14", "C15")


def main() -> None:
    files = sorted((HERE / "raw").glob("seed-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    data = [json.loads(f.read_text()) for f in files]
    excluded = [d["seed"] for d in data if not d["fidelity_matches_task109"]]
    frozen_ok = all(
        d["frozen_before"]["hashes"] == d["frozen_after"]["hashes"] for d in data
    )
    data = [d for d in data if d["fidelity_matches_task109"]]
    per_target: dict[str, object] = {}
    counting: dict[str, str] = {}
    for t in (*STRONG, "C07"):
        applicable = [d for d in data if not d["targets"][t]["baseline_specific_task109"]]
        principles = collections.Counter(d["targets"][t]["divergence"]["principle"] for d in applicable)
        causes = collections.Counter(str(d["targets"][t]["divergence"].get("cause")) for d in applicable)
        atoms = sum(d["targets"][t]["all_literals_atoms"] for d in applicable)
        restored_one = sum(
            1 for d in applicable
            if d["targets"][t]["counterfactual"].get("restored_specific")
            and d["targets"][t]["counterfactual"].get("interventions_needed") == 1
        )
        ratios = sorted(
            d["targets"][t]["best_productive_scored"]["ratio_to_15th_selected"]
            for d in applicable if "best_productive_scored" in d["targets"][t]
        )
        ranks = sorted(
            d["targets"][t]["best_productive_scored"]["effective_rank_among_interactions"]
            for d in applicable if "best_productive_scored" in d["targets"][t]
        )
        n = len(applicable)
        top_principle, top_count = principles.most_common(1)[0] if principles else (None, 0)
        majority = n > 0 and top_count * 2 > n and atoms * 2 > n and restored_one * 2 > n
        if t in STRONG and majority:
            counting[t] = str(top_principle)
        per_target[t] = {
            "n_applicable_seeds": n,
            "principles": dict(principles),
            "causes": dict(causes),
            "all_literals_atoms_on": atoms,
            "restored_by_one_step_on": restored_one,
            "ratio_to_15th_selected_min_median_max": (
                [ratios[0], ratios[len(ratios) // 2], ratios[-1]] if ratios else None
            ),
            "effective_rank_min_median_max": (
                [ranks[0], ranks[len(ranks) // 2], ranks[-1]] if ranks else None
            ),
            "counts_toward_h117": t in counting,
        }
    shared = collections.Counter(counting.values())
    best_principle, best_n = shared.most_common(1)[0] if shared else (None, 0)
    verdict = "SUPPORTED" if best_n >= 4 else "NOT SUPPORTED"
    out = {
        "n_seeds": len(data),
        "fidelity_excluded_seeds": excluded,
        "engine_hash_unchanged_every_seed": frozen_ok,
        "per_target": per_target,
        "counting_targets": counting,
        "shared_principle": best_principle,
        "n_strong_targets_with_shared_principle": best_n,
        "verdict": verdict,
    }
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
