"""TASK-114 Step 2 -- classify every chain step transition built by Step 1 into one of:

  * POSITIVE (H114 pattern): coverage retained, specificity increased (j_e up), evidence/signal
    remains sufficient (still eligible, harm_per_booking > 0 at the more-specific step), and the
    real unmodified `_development_score` nonetheless DROPS from the broader step to the
    more-specific step -- i.e. the existing objective still prefers the broader parent.
  * SCORE_ALREADY_PREFERS_SPECIFIC: same retained-coverage/increased-specificity/sufficient-evidence
    conditions, but `_development_score` INCREASES at the more-specific step -- no refinement
    opportunity here; the existing score already handles this case correctly.
  * NEGATIVE CONTROL (signal destroyed by added specificity): j_e (or cr) increases but coverage is
    lost (recall < 0.5), OR the more-specific step becomes ineligible (`_eligible` fails), OR its
    development-split effect collapses (`harm_per_booking <= 0`) -- regardless of what the score
    says, this is the destructive case support/volume protection exists for.
  * OTHER: anything not cleanly one of the above (disclosed, not forced).

Reads only Step 1's own committed output (`step1-chains-raw/seed-*.json`). No engine run, no
recomputation -- pure aggregation over already-measured quantities.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN_DIR = HERE / "step1-chains-raw"
OUT = HERE / "step2-classification-results.json"

COVERAGE_RECALL = 0.5


def classify_transition(step_a: dict, step_b: dict) -> dict:
    bv = step_a["benchmark_v2_scoring"]
    cv = step_b["benchmark_v2_scoring"]
    coverage_retained = bv["recall"] >= COVERAGE_RECALL and cv["recall"] >= COVERAGE_RECALL
    specificity_increased = cv["j_e"] > bv["j_e"] or cv["cr"] > bv["cr"]
    parent_eligible = step_a["eligible"]
    child_eligible = step_b["eligible"]
    child_harm = (
        step_b["engine_metric_development"]["harm_per_booking"]
        if step_b["engine_metric_development"] is not None
        else None
    )
    evidence_sufficient = child_eligible and (child_harm is not None and child_harm > 0)

    score_a = step_a["development_score"]
    score_b = step_b["development_score"]
    score_available = score_a is not None and score_b is not None
    score_prefers_broad = score_available and score_b < score_a
    score_prefers_specific = score_available and score_b > score_a

    if specificity_increased and not coverage_retained:
        kind = "NEGATIVE_CONTROL_COVERAGE_LOST"
    elif specificity_increased and not evidence_sufficient:
        kind = "NEGATIVE_CONTROL_EVIDENCE_COLLAPSED"
    elif not parent_eligible:
        # The broader "parent" step was never itself a real contender (the real engine's own
        # `_eligible` gate runs BEFORE scoring -- an ineligible rule never enters `scored` at all,
        # so it could never actually have been preferred by anything). Comparing its score to an
        # eligible child's would misrepresent "the real ranking prefers broad" when the broad
        # rule was never really in contention. Verified separately (results doc) that this never
        # actually changed any target's qualification -- zero `H114_POSITIVE` transitions in the
        # full dataset had an ineligible parent even before this guard was added.
        kind = "OTHER_PARENT_INELIGIBLE_NOT_A_REAL_CONTENDER"
    elif coverage_retained and specificity_increased and evidence_sufficient and score_prefers_broad:
        kind = "H114_POSITIVE_SCORE_PREFERS_BROAD"
    elif coverage_retained and specificity_increased and evidence_sufficient and score_prefers_specific:
        kind = "SCORE_ALREADY_PREFERS_SPECIFIC"
    elif not specificity_increased:
        kind = "OTHER_NO_SPECIFICITY_INCREASE"
    else:
        kind = "OTHER_UNCLASSIFIED"

    return {
        "kind": kind,
        "coverage_retained": coverage_retained,
        "specificity_increased": specificity_increased,
        "evidence_sufficient_at_child": evidence_sufficient,
        "parent_eligible": parent_eligible,
        "child_eligible": child_eligible,
        "child_harm_per_booking": child_harm,
        "j_e_parent": bv["j_e"],
        "j_e_child": cv["j_e"],
        "cr_parent": bv["cr"],
        "cr_child": cv["cr"],
        "recall_parent": bv["recall"],
        "recall_child": cv["recall"],
        "development_score_parent": score_a,
        "development_score_child": score_b,
        "score_delta_child_minus_parent": (score_b - score_a) if score_available else None,
    }


def main() -> None:
    seed_files = sorted(IN_DIR.glob("seed-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    per_target: dict[str, dict] = {}

    for f in seed_files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        seed = doc["seed"]
        for target_id, entry in doc["targets"].items():
            per_target.setdefault(
                target_id,
                {
                    "chainable": entry.get("chainable", False),
                    "seeds_with_qualifying_broad_candidate": [],
                    "seed_results": {},
                },
            )
            pt = per_target[target_id]
            if not entry.get("chainable"):
                pt["reason_not_chainable"] = entry.get("reason")
                continue
            if not entry.get("has_qualifying_broad_candidate"):
                continue
            pt["seeds_with_qualifying_broad_candidate"].append(seed)
            steps = entry["chain_steps"]
            transitions = [classify_transition(steps[i], steps[i + 1]) for i in range(len(steps) - 1)]
            any_positive = any(t["kind"] == "H114_POSITIVE_SCORE_PREFERS_BROAD" for t in transitions)
            any_negative = any(t["kind"].startswith("NEGATIVE_CONTROL") for t in transitions)
            pt["seed_results"][str(seed)] = {
                "broad_candidate_id": entry["chosen_broad_candidate"]["candidate_id"],
                "broad_candidate_conditions": entry["chosen_broad_candidate"]["conditions"],
                "n_steps": len(steps),
                "transitions": transitions,
                "any_positive_transition": any_positive,
                "any_negative_control_transition": any_negative,
            }

    summary = {}
    for target_id, pt in per_target.items():
        if not pt["chainable"]:
            summary[target_id] = {"chainable": False, "reason": pt.get("reason_not_chainable")}
            continue
        n_applicable = len(pt["seeds_with_qualifying_broad_candidate"])
        n_positive_seeds = sum(
            1 for r in pt["seed_results"].values() if r["any_positive_transition"]
        )
        n_negative_seeds = sum(
            1 for r in pt["seed_results"].values() if r["any_negative_control_transition"]
        )
        summary[target_id] = {
            "chainable": True,
            "n_applicable_seeds": n_applicable,
            "applicable_seeds": pt["seeds_with_qualifying_broad_candidate"],
            "n_seeds_with_h114_positive_pattern": n_positive_seeds,
            "n_seeds_with_negative_control_pattern": n_negative_seeds,
            "fraction_positive_of_applicable": (n_positive_seeds / n_applicable) if n_applicable else None,
            "qualifies_on_most_applicable_seeds": (
                n_applicable > 0 and n_positive_seeds / n_applicable > 0.5
            ),
        }

    out = {"per_target_detail": per_target, "per_target_summary": summary}
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    for target_id, s in sorted(summary.items()):
        if s.get("chainable"):
            print(
                f"{target_id}: applicable={s['n_applicable_seeds']} "
                f"positive={s['n_seeds_with_h114_positive_pattern']} "
                f"negative_control={s['n_seeds_with_negative_control_pattern']} "
                f"qualifies={s['qualifies_on_most_applicable_seeds']}"
            )
        else:
            print(f"{target_id}: NOT CHAINABLE ({s.get('reason')})")


if __name__ == "__main__":
    main()
