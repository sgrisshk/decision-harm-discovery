"""TASK-114 Step 2b -- classify Method B (`step1b_canonical_prefix_chains.py`) chain-step
transitions, same classification logic as Step 2 (`step2_classify_patterns.py`), reused directly
(imported, not re-implemented) against the different `starts`-shaped Method B records. Read-only
aggregation over already-committed Step 1b output; no engine run."""
from __future__ import annotations

import json
from pathlib import Path

import step2_classify_patterns as s2

HERE = Path(__file__).resolve().parent
IN_DIR = HERE / "step1b-canonical-prefix-raw"
OUT = HERE / "step2b-classification-results.json"


def main() -> None:
    seed_files = sorted(IN_DIR.glob("seed-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    per_target: dict[str, dict] = {}

    for f in seed_files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        seed = doc["seed"]
        for target_id, entry in doc["targets"].items():
            per_target.setdefault(
                target_id,
                {"chainable": entry.get("chainable", False), "seed_start_results": {}},
            )
            pt = per_target[target_id]
            if not entry.get("chainable"):
                continue
            for start in entry["starts"]:
                if not start["applicable_single_literal_covers_target"]:
                    continue  # mathematically should always be true (see step1b docstring), guard anyway
                steps = start["chain_steps"]
                transitions = [
                    s2.classify_transition(steps[i], steps[i + 1]) for i in range(len(steps) - 1)
                ]
                any_positive = any(t["kind"] == "H114_POSITIVE_SCORE_PREFERS_BROAD" for t in transitions)
                any_negative = any(t["kind"].startswith("NEGATIVE_CONTROL") for t in transitions)
                key = f"{seed}:start={start['starting_literal_index_in_canonical_order']}"
                pt["seed_start_results"][key] = {
                    "seed": seed,
                    "starting_literal": start["starting_literal"],
                    "n_steps": len(steps),
                    "transitions": transitions,
                    "any_positive_transition": any_positive,
                    "any_negative_control_transition": any_negative,
                }

    summary = {}
    for target_id, pt in per_target.items():
        if not pt["chainable"]:
            summary[target_id] = {"chainable": False}
            continue
        results = list(pt["seed_start_results"].values())
        n_applicable = len(results)
        n_positive = sum(1 for r in results if r["any_positive_transition"])
        n_negative = sum(1 for r in results if r["any_negative_control_transition"])
        # per-seed (collapsing the up-to-3 starting literals into "pattern seen this seed at all")
        per_seed_positive: dict[int, bool] = {}
        per_seed_applicable: set[int] = set()
        for r in results:
            per_seed_applicable.add(r["seed"])
            if r["any_positive_transition"]:
                per_seed_positive[r["seed"]] = True
        n_seeds_applicable = len(per_seed_applicable)
        n_seeds_positive = sum(1 for s in per_seed_applicable if per_seed_positive.get(s))
        summary[target_id] = {
            "chainable": True,
            "n_applicable_start_chains": n_applicable,
            "n_positive_start_chains": n_positive,
            "n_negative_control_start_chains": n_negative,
            "n_seeds_applicable": n_seeds_applicable,
            "n_seeds_with_at_least_one_positive_start": n_seeds_positive,
            "fraction_seeds_positive": (n_seeds_positive / n_seeds_applicable) if n_seeds_applicable else None,
            "qualifies_on_most_applicable_seeds": (
                n_seeds_applicable > 0 and n_seeds_positive / n_seeds_applicable > 0.5
            ),
        }

    out = {"per_target_detail": per_target, "per_target_summary": summary}
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    for target_id, s in sorted(summary.items()):
        if s.get("chainable"):
            print(
                f"{target_id}: seeds_applicable={s['n_seeds_applicable']} "
                f"seeds_positive={s['n_seeds_with_at_least_one_positive_start']} "
                f"start_chains(applicable/positive/negctrl)="
                f"{s['n_applicable_start_chains']}/{s['n_positive_start_chains']}/{s['n_negative_control_start_chains']} "
                f"qualifies={s['qualifies_on_most_applicable_seeds']}"
            )
        else:
            print(f"{target_id}: NOT CHAINABLE")


if __name__ == "__main__":
    main()
