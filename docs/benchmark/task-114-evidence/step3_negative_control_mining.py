"""TASK-114 Step 3 -- mandatory negative-control mining (`ADR-115` Decision 5).

Method A/B (`step1_build_chains.py`, `step1b_canonical_prefix_chains.py`) only ever add TRUE
canonical literals, which can never destroy a target's own Coverage (a subset of the canonical
AND-conjunction's rows is always a superset of the fully-canonical rule's own affected rows -- see
that script's own docstring). They therefore cannot, by construction, surface the negative-control
case `ADR-115` Decision 5 requires: a literal addition that increases syntactic specificity but
DESTROYS signal/evidence. This script mines for that case directly from the real, already-
committed search output instead -- no engine run, pure data mining over `score.candidates` +
`engine.candidates` already persisted by `TASK-109`/`TASK-112`.

For every seed, for every pair of real final-top-15 candidates (c_broad, c_narrow) in the SAME
seed where `c_narrow`'s conditions are EXACTLY `c_broad`'s conditions plus one more real,
engine-discovered condition (i.e. a genuine one-literal-added search-trajectory step, not
invented), and for every Core target `c_broad` covers (committed `recall >= 0.5`): if `c_narrow`
is MORE specific toward that target (higher `j_e`, the real Specific-metric exposure-Jaccard) but
its Coverage of the SAME target has collapsed (`recall < 0.5`) -- that is a real, literal negative-
control instance, reported with the same per-step detail as the positive chains (recall, j_e, cp,
cr, development harm_per_booking, support) for both `c_broad` and `c_narrow`.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
T109_RAW = HERE.parents[1] / "benchmark/task-109-evidence/engine-raw"
T112_BASELINE = HERE.parents[1] / "benchmark/task-112-evidence/step5-paired-4101-4130"
OUT = HERE / "step3-negative-control-results.json"

FINAL_CORE = ("C02", "C04", "C06", "C07", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
COVERAGE_RECALL = 0.5


def _condset(conditions: list[dict]) -> frozenset[tuple]:
    return frozenset((c["feature"], c["operator"], c["value"]) for c in conditions)


def _load(seed: int) -> dict:
    if 4001 <= seed <= 4030:
        path = T109_RAW / f"seed-{seed}.json"
    else:
        path = T112_BASELINE / f"baseline-seed-{seed}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def mine_seed(seed: int) -> list[dict]:
    doc = _load(seed)
    engine_cands = {c["candidate_id"]: c for c in doc["engine"]["candidates"]}
    score_cands = {c["candidate_id"]: c for c in doc["score"]["candidates"]}
    cids = list(engine_cands)

    findings = []
    for cb_id in cids:
        cb_conds = engine_cands[cb_id]["conditions"]
        cb_set = _condset(cb_conds)
        cb_score = score_cands[cb_id]
        for target_id in FINAL_CORE:
            pm_b = cb_score["per_target"].get(target_id)
            if pm_b is None or pm_b["recall"] < COVERAGE_RECALL:
                continue
            for cn_id in cids:
                if cn_id == cb_id:
                    continue
                cn_conds = engine_cands[cn_id]["conditions"]
                cn_set = _condset(cn_conds)
                if len(cn_set) != len(cb_set) + 1 or not cb_set.issubset(cn_set):
                    continue  # not a one-literal-added superset in the engine's own grammar
                cn_score = score_cands[cn_id]
                pm_n = cn_score["per_target"].get(target_id)
                if pm_n is None:
                    continue
                specificity_increased = pm_n["j_e"] > pm_b["j_e"] or pm_n["cr"] > pm_b["cr"]
                coverage_collapsed = pm_n["recall"] < COVERAGE_RECALL
                if specificity_increased and coverage_collapsed:
                    findings.append(
                        {
                            "seed": seed,
                            "target": target_id,
                            "broad_candidate_id": cb_id,
                            "broad_conditions": cb_conds,
                            "narrow_candidate_id": cn_id,
                            "narrow_conditions": cn_conds,
                            "added_condition": [
                                {"feature": f, "operator": o, "value": v}
                                for (f, o, v) in (cn_set - cb_set)
                            ],
                            "broad_metrics": {
                                "recall": pm_b["recall"],
                                "j_e": pm_b["j_e"],
                                "cp": pm_b["cp"],
                                "cr": pm_b["cr"],
                                "harm_per_booking_development": engine_cands[cb_id]["development"][
                                    "harm_per_booking"
                                ],
                                "n_exposed_development": engine_cands[cb_id]["development"]["n_exposed"],
                                "support_development": engine_cands[cb_id]["development"]["support"],
                            },
                            "narrow_metrics": {
                                "recall": pm_n["recall"],
                                "j_e": pm_n["j_e"],
                                "cp": pm_n["cp"],
                                "cr": pm_n["cr"],
                                "harm_per_booking_development": engine_cands[cn_id]["development"][
                                    "harm_per_booking"
                                ],
                                "n_exposed_development": engine_cands[cn_id]["development"]["n_exposed"],
                                "support_development": engine_cands[cn_id]["development"]["support"],
                            },
                        }
                    )
    return findings


def main() -> None:
    all_findings = []
    for seed in (*range(4001, 4031), *range(4101, 4131)):
        all_findings.extend(mine_seed(seed))

    by_target: dict[str, int] = {}
    for f in all_findings:
        by_target[f["target"]] = by_target.get(f["target"], 0) + 1

    out = {
        "n_negative_control_instances": len(all_findings),
        "n_instances_by_target": by_target,
        "findings": all_findings,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"total negative-control instances: {len(all_findings)}")
    print("by target:", by_target)


if __name__ == "__main__":
    main()
