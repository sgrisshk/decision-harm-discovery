"""TASK-110 step A (read-only mining, no engine run): for each of the 10 non-reliable Core
targets, extract from TASK-109's already-committed, untouched raw evidence
(`docs/benchmark/task-109-evidence/engine-raw/seed-*.json`) the per-seed best-Coverage candidate,
best-Specific-metric candidate (by j_e even when below theta_J), and the credited/validated
outcome. Pure read + aggregate; does not import or call the engine, scorer, or generator -- it only
reads JSON that TASK-109 already wrote and never modifies it. Output is new evidence for THIS task
(`task-110-evidence/`), never written back into `task-109-evidence/`.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RAW = REPO / "docs/benchmark/task-109-evidence/engine-raw"
OUT = Path(__file__).resolve().parent

TARGETS = ("C02", "C04", "C06", "C08", "C09", "C11", "C12", "C14", "C15", "H01")

CANONICAL = {
    "C02": "destination=Rome AND customer_segment=corporate",
    "C04": "supplier=Cedar AND customer_segment=leisure AND trip_duration_days>=8",
    "C06": "destination=Reykjavik AND customer_type=returning AND discount_rate>=0.05",
    "C08": "payment_method=wallet",
    "C09": "destination=Tokyo AND customer_segment=leisure AND product_category=standard",
    "C11": "destination=Tokyo AND customer_segment=family",
    "C12": "acquisition_channel=direct AND product_category=premium AND customer_segment=leisure",
    "C14": "customer_segment=leisure AND supplier=BlueWing AND discount_rate>=0.08",
    "C15": "customer_type=returning AND acquisition_channel=direct AND trip_duration_days>=6",
    "H01": "supplier=BlueWing AND destination=Zanzibar AND customer_type=new",
}


def load(seed: int) -> dict:
    return json.loads((RAW / f"seed-{seed}.json").read_text())


def main() -> None:
    seeds = list(range(4001, 4031))
    per_target: dict[str, dict] = {tid: {"canonical": CANONICAL[tid], "seeds": {}} for tid in TARGETS}

    for seed in seeds:
        d = load(seed)
        score_cands = d["score"]["candidates"]
        core = d["score"]["strata"]["core"]
        specific_0_50 = set(core["specific_targets"]["0.50"])
        exact_set = set(core["exact_targets"])
        coverage_set = set(core["coverage_targets"])
        for tid in TARGETS:
            # best Coverage (max recall), best Specific-metric attempt (max j_e), regardless of
            # whether it was the credited target for that candidate.
            best_cov = max(score_cands, key=lambda c: c["per_target"][tid]["recall"])
            best_j = max(score_cands, key=lambda c: c["per_target"][tid]["j_e"])
            per_target[tid]["seeds"][seed] = {
                "coverage_reached": tid in coverage_set,
                "specific_reached": tid in specific_0_50,
                "exact_reached": tid in exact_set,
                "best_coverage_candidate": {
                    "candidate_id": best_cov["candidate_id"],
                    "conditions": best_cov["conditions"],
                    "recall": best_cov["per_target"][tid]["recall"],
                    "j_e": best_cov["per_target"][tid]["j_e"],
                    "cp": best_cov["per_target"][tid]["cp"],
                    "cr": best_cov["per_target"][tid]["cr"],
                    "evidence_level": best_cov["evidence_level"],
                    "credited_target": best_cov["credited_target"],
                },
                "best_j_candidate": {
                    "candidate_id": best_j["candidate_id"],
                    "conditions": best_j["conditions"],
                    "recall": best_j["per_target"][tid]["recall"],
                    "j_e": best_j["per_target"][tid]["j_e"],
                    "cp": best_j["per_target"][tid]["cp"],
                    "cr": best_j["per_target"][tid]["cr"],
                    "evidence_level": best_j["evidence_level"],
                    "credited_target": best_j["credited_target"],
                },
            }

    (OUT / "mined-seed-evidence.json").write_text(json.dumps(per_target, indent=1, sort_keys=True))
    print("wrote", OUT / "mined-seed-evidence.json")

    # Quick stability summary of the best-coverage candidate's condition *set* across all 30 seeds,
    # per target -- does the engine keep finding the "same" broad rule, or a different one each time?
    summary = {}
    for tid in TARGETS:
        cond_sets = [
            tuple(sorted(info["best_coverage_candidate"]["conditions"]))
            for info in per_target[tid]["seeds"].values()
        ]
        from collections import Counter

        counts = Counter(cond_sets)
        summary[tid] = {
            "n_distinct_best_coverage_rules_across_30_seeds": len(counts),
            "most_common": [
                {"conditions": list(cs), "n_seeds": n} for cs, n in counts.most_common(3)
            ],
        }
    (OUT / "stable-coverage-candidate-summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True)
    )
    print("wrote", OUT / "stable-coverage-candidate-summary.json")


if __name__ == "__main__":
    main()
