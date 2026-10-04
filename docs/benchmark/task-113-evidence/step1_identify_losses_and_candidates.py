"""TASK-113 Step 1 -- verify, from TASK-112's own committed raw data (NOT assumed), exactly which
8 Core targets went from "ever-recovered" (Coverage, k>=1/30) under the frozen baseline engine to
"never-recovered" (Coverage, k==0/30) under the modified engine, across all 30 seeds of
4101-4130. Also identifies, for each such target, the first baseline seed (lowest seed number,
deterministic -- not cherry-picked) at which baseline achieved Coverage for that target, and the
exact baseline candidate (conditions) credited with it, for use as the trace subject in Step 2+.

Reads ONLY already-committed TASK-112 raw files
(docs/benchmark/task-112-evidence/step5-paired-4101-4130/{baseline,modified}-seed-*.json).
No engine run. No modification of any file.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO / "docs/benchmark/task-112-evidence/step5-paired-4101-4130"
OUT = Path(__file__).resolve().parent / "step1-identification-results.json"

FINAL_CORE = ("C02", "C04", "C06", "C07", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
SEEDS = list(range(4101, 4131))
COVERAGE_RECALL = 0.5  # benchmark_v2_scoring.Constants.coverage_recall -- confirmed by reading
                        # packages/analytics/src/policy_analytics/benchmark_v2_scoring.py directly


def load(variant: str, seed: int) -> dict:
    return json.loads((EVAL_DIR / f"{variant}-seed-{seed}.json").read_text(encoding="utf-8"))


def coverage_candidates(seed_doc: dict, target: str) -> list[dict]:
    """Every candidate in this seed's final top-15 whose recall against `target` clears
    coverage_recall -- directly from the committed per-candidate `per_target[target]["recall"]`
    field (same quantity benchmark_v2_scoring.score() used to build `covers_targets`/
    `coverage_targets` -- cross-checked against the candidate's own `covers_targets` list, not
    just recomputed independently)."""
    out = []
    for cand in seed_doc["score"]["candidates"]:
        pm = cand["per_target"].get(target)
        if pm is None:
            continue
        recall = pm["recall"]
        in_covers_list = target in cand["covers_targets"]
        if recall >= COVERAGE_RECALL:
            assert in_covers_list, (
                f"recall {recall} >= {COVERAGE_RECALL} but {target} missing from covers_targets "
                f"for {cand['candidate_id']} -- scoring logic mismatch, investigate before trusting"
            )
            out.append(cand)
        else:
            assert not in_covers_list, (
                f"{target} present in covers_targets but recall {recall} < {COVERAGE_RECALL} "
                f"for {cand['candidate_id']} -- scoring logic mismatch, investigate before trusting"
            )
    return out


def main() -> None:
    baseline_docs = {s: load("baseline", s) for s in SEEDS}
    modified_docs = {s: load("modified", s) for s in SEEDS}

    per_target_summary = {}
    for target in FINAL_CORE:
        baseline_ever = []
        modified_ever = []
        for s in SEEDS:
            if any(target in c["covers_targets"] for c in baseline_docs[s]["score"]["candidates"]):
                baseline_ever.append(s)
            if any(target in c["covers_targets"] for c in modified_docs[s]["score"]["candidates"]):
                modified_ever.append(s)
        per_target_summary[target] = {
            "baseline_coverage_k_of_30": len(baseline_ever),
            "modified_coverage_k_of_30": len(modified_ever),
            "baseline_covering_seeds": baseline_ever,
            "modified_covering_seeds": modified_ever,
            "lost_coverage_entirely": len(baseline_ever) >= 1 and len(modified_ever) == 0,
        }

    losses = sorted(t for t, v in per_target_summary.items() if v["lost_coverage_entirely"])
    assert len(losses) == 8, f"expected exactly 8 Coverage-losing targets, got {len(losses)}: {losses}"
    expected = {"C02", "C04", "C06", "C08", "C09", "C14", "C15", "H01"}
    assert set(losses) == expected, f"mismatch vs ADR-114/TASK-112 narrative: {sorted(set(losses) ^ expected)}"

    # For each lost target: identify the first (lowest-numbered) baseline seed where Coverage was
    # achieved, and the exact credited candidate(s) (by conditions, since candidate_id numbering is
    # per-seed and not comparable across seeds/variants).
    trace_subjects = {}
    for target in losses:
        first_seed = per_target_summary[target]["baseline_covering_seeds"][0]
        bdoc = baseline_docs[first_seed]
        covering = coverage_candidates(bdoc, target)
        mdoc = modified_docs[first_seed]
        mod_conditions_sets = [tuple(sorted(c["conditions"])) for c in mdoc["score"]["candidates"]]
        subjects = []
        for cand in covering:
            conds = tuple(sorted(cand["conditions"]))
            present_in_modified_final15 = conds in mod_conditions_sets
            subjects.append(
                {
                    "candidate_id": cand["candidate_id"],
                    "conditions": cand["conditions"],
                    "rank_score_baseline": next(
                        c["rank_score"]
                        for c in bdoc["engine"]["candidates"]
                        if c["candidate_id"] == cand["candidate_id"]
                    ),
                    "recall_vs_target": cand["per_target"][target]["recall"],
                    "best_j": cand["best_j"],
                    "credited_target": cand["credited_target"],
                    "present_in_modified_final_top15_same_seed": present_in_modified_final15,
                }
            )
        trace_subjects[target] = {
            "first_baseline_covering_seed": first_seed,
            "n_covering_candidates_this_seed": len(covering),
            "covering_candidates": subjects,
        }

    result = {
        "coverage_recall_threshold": COVERAGE_RECALL,
        "per_target_summary": per_target_summary,
        "coverage_losing_targets_verified": losses,
        "trace_subjects": trace_subjects,
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print("Coverage-losing targets (verified from raw data):", losses)
    for t in losses:
        ts = trace_subjects[t]
        print(f"  {t}: first covering seed={ts['first_baseline_covering_seed']}, "
              f"{ts['n_covering_candidates_this_seed']} covering candidate(s)")


if __name__ == "__main__":
    main()
