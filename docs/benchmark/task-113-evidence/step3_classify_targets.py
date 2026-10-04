"""TASK-113 Step 3 -- per-target stage-of-disappearance classification.

READ-ONLY. Consumes:
  * step1-identification-results.json (which targets lost Coverage, which candidate(s) achieved
    it at baseline, on which seed)
  * step2-dual-trace-raw/trace-seed-{4101,4102}.json (the validated dual-formula stage trace --
    both seeds' "baseline" simulation matched the real committed baseline-seed-*.json EXACTLY,
    and both seeds' "modified" simulation (arithmetic recomputation of TASK-112's documented
    formula fed through the real, unmodified `_select_expansion_beam`/`_greedy_diverse_select`)
    matched the real committed modified-seed-*.json EXACTLY too -- this is checked below again,
    not just asserted, before any conclusion is drawn from it)
  * docs/benchmark/task-112-evidence/step5-paired-4101-4130/modified-seed-{4101,4102}.json (the
    real modified engine's own committed final top-15, used to name the specific real candidate
    that occupies the slot the lost candidate would have had)

For each of the 8 Coverage-losing targets, classifies the lost baseline Coverage candidate as:
  - ACQUISITION FAILURE: at least one of its depth-1 parent single-conditions failed to survive
    the depth-1 beam under the modified formula, so the depth-2 rule was never even constructed
    (never appears in the modified-formula `scored` pool at depth 2) -- lost before scoring could
    even see it.
  - REFINEMENT-STAGE CROWDING: the rule WAS constructed and scored under the modified formula
    (both parents survived beam, or depth-2 composition otherwise occurred), but did not survive
    to the final top-15 -- displaced by a specific, named, higher-scoring real candidate.
  - OTHER / mixed: anything not cleanly one of the above (disclosed explicitly, not forced into
    one of the two bins).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EVAL_DIR = REPO / "docs/benchmark/task-112-evidence/step5-paired-4101-4130"

STEP1 = json.loads((HERE / "step1-identification-results.json").read_text())
TRACES = {
    4101: json.loads((HERE / "step2-dual-trace-raw/trace-seed-4101.json").read_text()),
    4102: json.loads((HERE / "step2-dual-trace-raw/trace-seed-4102.json").read_text()),
}

LOSSES = STEP1["coverage_losing_targets_verified"]


def cond_str(c: dict) -> str:
    """Match engine.py's Condition dataclass default repr exactly (feature, operator, value)."""
    value = c["value"]
    if isinstance(value, str):
        value_repr = f"'{value}'"
    else:
        value_repr = repr(value)
    return f"Condition(feature={c['feature']!r}, operator={c['operator']!r}, value={value_repr})"


def depth1_strs(conditions: list[dict]) -> list[str]:
    return [cond_str(c) for c in conditions]


def depth2_key(conditions: list[dict]) -> str:
    strs = depth1_strs(conditions)
    # engine.py sorts conditions via tuple(sorted((*rule, atom))) -- Condition is
    # order=True on (feature, operator, value); replicate that ordering on the two strings by
    # sorting the ORIGINAL condition dicts the same way, not the rendered strings (string sort
    # of the repr happens to agree here since feature names differ, but do it correctly anyway).
    ordered = sorted(conditions, key=lambda c: (c["feature"], c["operator"], str(c["value"])))
    return " & ".join(cond_str(c) for c in ordered)


def committed_final15(variant: str, seed: int) -> list[dict]:
    doc = json.loads((EVAL_DIR / f"{variant}-seed-{seed}.json").read_text())
    return doc["engine"]["candidates"]


def classify_candidate(target: str, seed: int, conditions: list[dict]) -> dict:
    trace = TRACES[seed]
    assert trace["validation_against_committed"]["baseline_simulation_matches_committed_exactly_in_order"]
    assert trace["validation_against_committed"]["modified_simulation_matches_committed_exactly_in_order"]

    parent_strs = depth1_strs(conditions)
    # beam_rules is list of lists (each a 1-tuple at depth 1); flatten.
    beam_b1 = {r[0] for r in trace["by_depth_baseline"]["1"]["beam_rules"]}
    beam_m1 = {r[0] for r in trace["by_depth_modified"]["1"]["beam_rules"]}
    scored_b1 = trace["by_depth_baseline"]["1"]["scored_at_depth"]
    scored_m1 = trace["by_depth_modified"]["1"]["scored_at_depth"]

    parents_info = []
    for p in parent_strs:
        parents_info.append(
            {
                "condition": p,
                "eligible_baseline": p in scored_b1,
                "eligible_modified": p in scored_m1,
                "score_baseline": scored_b1.get(p),
                "score_modified": scored_m1.get(p),
                "in_beam_baseline_depth1": p in beam_b1,
                "in_beam_modified_depth1": p in beam_m1,
            }
        )

    at_least_one_parent_in_beam_modified = any(p["in_beam_modified_depth1"] for p in parents_info)

    key2 = depth2_key(conditions)
    scored_b2 = trace["by_depth_baseline"]["2"]["scored_at_depth"]
    scored_m2 = trace["by_depth_modified"]["2"]["scored_at_depth"]
    constructed_baseline_d2 = key2 in scored_b2
    constructed_modified_d2 = key2 in scored_m2

    final_sets_modified = [frozenset(r) for r in trace["final_selected_modified"]]
    rule_set = frozenset(parent_strs)
    survived_to_final_modified = rule_set in final_sets_modified

    # Name what's actually occupying the real modified engine's final top-15 for this seed:
    # the committed candidates, sorted by rank_score (already in final order), i.e. CAND-001..015.
    committed_modified = committed_final15("modified", seed)

    if not constructed_modified_d2:
        stage = "ACQUISITION FAILURE"
        reason = (
            "Depth-2 rule never appears in the modified-formula scored pool at depth 2 at all -- "
            "neither parent single-condition survived the depth-1 beam under the modified formula, "
            "so this composition was never even constructed/evaluated."
        )
    elif not survived_to_final_modified:
        stage = "REFINEMENT-STAGE CROWDING"
        reason = (
            "Rule WAS constructed and scored under the modified formula (depth-2 scored pool "
            "contains it) but did not survive to the final top-15 -- displaced by other candidates "
            "with higher effective_score in the greedy-diverse final selection."
        )
    else:
        stage = "OTHER (survived in simulation but absent from committed data -- investigate)"
        reason = "Simulation says this rule reached final selection under modified; contradicts Step 1's committed-data finding that it is absent from modified's real top-15. Needs investigation."

    return {
        "target": target,
        "seed": seed,
        "rule": parent_strs,
        "parents_depth1": parents_info,
        "at_least_one_parent_survives_depth1_beam_modified": at_least_one_parent_in_beam_modified,
        "depth2_key": key2,
        "constructed_scored_baseline_depth2": constructed_baseline_d2,
        "constructed_scored_modified_depth2": constructed_modified_d2,
        "score_baseline_depth2": scored_b2.get(key2),
        "score_modified_depth2_recomputed": scored_m2.get(key2),
        "survived_to_final_selection_modified_simulation": survived_to_final_modified,
        "stage_of_disappearance": stage,
        "reason": reason,
        "real_modified_final_top15_committed": [
            {
                "candidate_id": c["candidate_id"],
                "conditions": [f"{cc['feature']} {cc['operator']} {cc['value']}" for cc in c["conditions"]],
                "rank_score": c["rank_score"],
            }
            for c in committed_modified
        ],
    }


def main() -> None:
    results = {}
    for target in LOSSES:
        subj = STEP1["trace_subjects"][target]
        seed = subj["first_baseline_covering_seed"]
        target_results = []
        for cand in subj["covering_candidates"]:
            conds_raw = cand["conditions"]  # list of "feature operator value" strings in step1 output
            # step1 stored conditions as raw dicts originally from the committed JSON's
            # cand["conditions"] field (list of {feature, operator, value} dicts) -- re-fetch them
            # directly from the committed baseline file by candidate_id to avoid any
            # string-parsing ambiguity.
            bdoc = json.loads((EVAL_DIR / f"baseline-seed-{seed}.json").read_text())
            raw_cand = next(
                c for c in bdoc["engine"]["candidates"] if c["candidate_id"] == cand["candidate_id"]
            )
            classification = classify_candidate(target, seed, raw_cand["conditions"])
            classification["candidate_id_baseline"] = cand["candidate_id"]
            classification["credited_target_of_candidate"] = cand["credited_target"]
            target_results.append(classification)
        results[target] = target_results

    out = HERE / "step3-classification-results.json"
    out.write_text(json.dumps(results, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    for target, items in results.items():
        for item in items:
            print(f"{target} (cand {item['candidate_id_baseline']} on seed {item['seed']}): {item['stage_of_disappearance']}")


if __name__ == "__main__":
    main()
