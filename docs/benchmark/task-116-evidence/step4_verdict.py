"""TASK-116 Step 4 -- the pre-registered `H116` SUPPORTED/NOT SUPPORTED verdict (`ADR-117`
Decision 4), evaluated honestly against Step 3's already-computed per-seed measurements. No
threshold or criterion here is chosen after seeing the numbers -- all four are copied verbatim
from `ADR-117` Decision 3/4/5 (see `TASKS.md` TASK-116 and `DECISIONS.md` ADR-117).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
IN = HERE / "step3-measurements-results.json"
OUT = HERE / "step4-verdict-results.json"

STRONG: tuple[str, ...] = ("C04", "C06", "C09", "C14", "C15")


def main() -> None:
    results: list[dict[str, Any]] = json.loads(IN.read_text())

    per_target: dict[str, Any] = {}
    for tid in (*STRONG, "C07"):
        applicable_seeds = []
        all_three_hold_seeds = []
        for seed_doc in results:
            entry = seed_doc["targets"].get(tid, {})
            if not entry.get("has_productive_descendant"):
                continue
            applicable_seeds.append(seed_doc["seed"])
            crit = entry.get("criterion", {})
            if (
                crit.get("c1_productive_descendant_exists")
                and crit.get("c2_capacity_cutoff_is_first_cause")
                and crit.get("c3_passes_real_validation_unlimited")
            ):
                all_three_hold_seeds.append(seed_doc["seed"])

        n_applicable = len(applicable_seeds)
        n_holds = len(all_three_hold_seeds)
        fraction = (n_holds / n_applicable) if n_applicable else 0.0
        holds_on_most = n_applicable > 0 and fraction > 0.5
        per_target[tid] = {
            "n_seeds_with_productive_descendant": n_applicable,
            "applicable_seeds": applicable_seeds,
            "n_seeds_all_three_criteria_hold": n_holds,
            "seeds_all_three_criteria_hold": all_three_hold_seeds,
            "fraction_of_applicable_seeds": fraction,
            "criterion_4_holds_on_most_applicable_seeds": holds_on_most,
            "target_qualifies_for_h116_support": n_applicable > 0 and holds_on_most,
        }

    n_strong_qualifying = sum(1 for tid in STRONG if per_target[tid]["target_qualifies_for_h116_support"])
    h116_supported = n_strong_qualifying >= 4

    # C07 guard (ADR-117 Decision 5): does unlimited capacity make the pathological-narrowing
    # descendant indistinguishable from genuine refinement anywhere?
    c07_guard_violations = []
    for seed_doc in results:
        for hit in seed_doc.get("c07_guard", {}).get("hits", []):
            if hit.get("is_specific") and hit.get("real_validation_verdict") not in (None, "REJECT"):
                c07_guard_violations.append({"seed": seed_doc["seed"], "hit": hit})

    verdict = {
        "per_target": per_target,
        "n_strong_targets_qualifying": n_strong_qualifying,
        "bar": "at least 4 of 5",
        "h116_supported": h116_supported,
        "c07_guard_violations_found": len(c07_guard_violations) > 0,
        "c07_guard_violations": c07_guard_violations,
        "evidence_bar_discipline": (
            "Reliable Specific Recall remains 1/11 and Exact remains 0/11 from TASK-109's last "
            "valid blind measurement. This task, even with a fully SUPPORTED H116, does not move "
            "that number -- it is a mechanistic-understanding result only, same as TASK-112/115."
        ),
    }
    OUT.write_text(json.dumps(verdict, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(verdict, indent=1, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
