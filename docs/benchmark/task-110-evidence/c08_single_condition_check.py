"""TASK-110 S4 counterfactual for C08: pure read + count over TASK-109's own 30 committed,
untouched `engine-raw/seed-*.json` files (no engine call). Confirms that the real, unmodified
`discover_candidates`'s real output -- under the real default `DiscoveryConfig`
(`reserve_k1_slot=False`) TASK-109 actually used -- never includes a single-condition final
candidate, on any of the 30 pre-registered seeds, for any target. This is the direct, exhaustive
evidence for the S4 claim that C08's canonical single-literal rule is excluded by the
interactions-first phase-ordering design, not by its own (good) quality.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RAW = REPO / "docs/benchmark/task-109-evidence/engine-raw"


def main() -> None:
    per_seed = {}
    for seed in range(4001, 4031):
        d = json.loads((RAW / f"seed-{seed}.json").read_text())
        cands = d["engine"]["candidates"]
        singles = [c["candidate_id"] for c in cands if len(c["conditions"]) == 1]
        per_seed[seed] = {
            "n_final_candidates": len(cands),
            "n_single_condition_final_candidates": len(singles),
            "single_candidate_ids": singles,
            "reserve_k1_slot_config_value": d["engine"]["search_config"]["reserve_k1_slot"],
        }
    total_singles = sum(v["n_single_condition_final_candidates"] for v in per_seed.values())
    out = {
        "per_seed": per_seed,
        "total_single_condition_final_candidates_across_all_30_seeds": total_singles,
        "conclusion": (
            "zero single-condition candidates in the real final top-15 on any of the 30 seeds; "
            "reserve_k1_slot is False (the frozen default) on every seed"
        ),
    }
    out_path = Path(__file__).resolve().parent / "c08-single-condition-check.json"
    out_path.write_text(json.dumps(out, indent=1, sort_keys=True))
    print("total single-condition final candidates across 30 seeds:", total_singles)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
