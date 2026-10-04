"""TASK-114 Step 6 -- summarize Step 4's validation evidence levels against the chain steps
backing (a) the 6 independently-qualifying targets' positive transitions and (b) the negative-
control cases, for the results document. Read-only aggregation; no engine run."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAL_DIR = HERE / "step4-validation-raw"
STEP1B_DIR = HERE / "step1b-canonical-prefix-raw"


def _rule_key(conditions: list[dict]) -> str:
    return " & ".join(
        f"{c['feature']} {c['operator']} {c['value']!r}"
        for c in sorted(conditions, key=lambda c: (c["feature"], c["operator"], str(c["value"])))
    )


INDEPENDENT_TARGETS = ("C04", "C06", "C09", "C14", "C15", "H01")
# the specific unique starting literal driving each target's independent qualification (from
# step5-independence-results.json)
DRIVING_START = {
    "C04": {"feature": "trip_duration_days", "operator": "ge", "value": 8},
    "C06": {"feature": "discount_rate", "operator": "ge", "value": 0.05},
    "C09": {"feature": "destination", "operator": "eq", "value": "Tokyo"},
    "C14": {"feature": "discount_rate", "operator": "ge", "value": 0.08},
    "C15": {"feature": "trip_duration_days", "operator": "ge", "value": 6},
    "H01": {"feature": "customer_type", "operator": "eq", "value": "new"},
}


def main() -> None:
    val_files = sorted(VAL_DIR.glob("seed-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    all_rules: dict[int, dict] = {}
    for f in val_files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        all_rules[doc["seed"]] = doc.get("rules", {})

    evidence_counter_by_target: dict[str, Counter] = {t: Counter() for t in INDEPENDENT_TARGETS}
    verdict_counter_by_target: dict[str, Counter] = {t: Counter() for t in INDEPENDENT_TARGETS}
    evidence_by_target_and_step: dict[str, dict[int, Counter]] = {
        t: {0: Counter(), 1: Counter(), 2: Counter()} for t in INDEPENDENT_TARGETS
    }
    missing = 0
    n_seeds_checked = 0

    for seed_file in sorted(STEP1B_DIR.glob("seed-*.json"), key=lambda p: int(p.stem.split("-")[1])):
        doc = json.loads(seed_file.read_text(encoding="utf-8"))
        seed = doc["seed"]
        rules = all_rules.get(seed)
        if rules is None:
            continue
        n_seeds_checked += 1
        for target_id in INDEPENDENT_TARGETS:
            entry = doc["targets"].get(target_id)
            if not entry or not entry.get("chainable"):
                continue
            want = DRIVING_START[target_id]
            for start in entry["starts"]:
                sl = start["starting_literal"]
                if (sl["feature"], sl["operator"], sl["value"]) != (want["feature"], want["operator"], want["value"]):
                    continue
                for step_idx, step in enumerate(start["chain_steps"]):
                    key = _rule_key(step["conditions"])
                    info = rules.get(key)
                    if info is None:
                        missing += 1
                        continue
                    evidence_counter_by_target[target_id][info["evidence_level"]] += 1
                    verdict_counter_by_target[target_id][info["verdict"]] += 1
                    evidence_by_target_and_step[target_id][step_idx][info["evidence_level"]] += 1

    out = {
        "n_seeds_with_validation_data_checked": n_seeds_checked,
        "n_rule_lookups_missing": missing,
        "evidence_level_counts_by_target_on_driving_chain": {
            t: dict(c) for t, c in evidence_counter_by_target.items()
        },
        "verdict_counts_by_target_on_driving_chain": {
            t: dict(c) for t, c in verdict_counter_by_target.items()
        },
        "evidence_level_by_target_and_step_index": {
            t: {str(i): dict(c) for i, c in steps.items()} for t, steps in evidence_by_target_and_step.items()
        },
    }
    out_path = HERE / "step6-validation-summary.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
