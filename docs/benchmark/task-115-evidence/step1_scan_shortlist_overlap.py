import json
from pathlib import Path

REPO = Path("<repo>/worktrees/agent-ab783e08609be4ffa")
T109 = REPO / "docs/benchmark/task-109-evidence/engine-raw"
T112 = REPO / "docs/benchmark/task-112-evidence/step5-paired-4101-4130"

CANON = {
    "C04": [("supplier", "eq", "Cedar"), ("customer_segment", "eq", "leisure"), ("trip_duration_days", "ge", 8)],
    "C06": [("destination", "eq", "Reykjavik"), ("customer_type", "eq", "returning"), ("discount_rate", "ge", 0.05)],
    "C09": [("destination", "eq", "Tokyo"), ("customer_segment", "eq", "leisure"), ("product_category", "eq", "standard")],
    "C14": [("customer_segment", "eq", "leisure"), ("supplier", "eq", "BlueWing"), ("discount_rate", "ge", 0.08)],
    "C15": [("customer_type", "eq", "returning"), ("acquisition_channel", "eq", "direct"), ("trip_duration_days", "ge", 6)],
}


def lit_match(cond, lit):
    feat, op, val = lit
    if cond["feature"] != feat:
        return False
    if op == "eq":
        return cond["operator"] == "eq" and cond["value"] == val
    return cond["operator"] == op


def load(seed):
    if 4001 <= seed <= 4030:
        p = T109 / f"seed-{seed}.json"
    else:
        p = T112 / f"baseline-seed-{seed}.json"
    return json.loads(p.read_text())


seeds = list(range(4001, 4031)) + list(range(4101, 4131))
summary = {tid: {"any_top15_literal_match_room": 0, "clean_subset_room": 0, "n_seeds_checked": 0, "example": None} for tid in CANON}

for seed in seeds:
    doc = load(seed)
    cands = doc["engine"]["candidates"]
    for tid, canon in CANON.items():
        summary[tid]["n_seeds_checked"] += 1
        found_any = False
        found_clean = False
        for c in cands:
            econd = c["conditions"]
            if len(econd) >= 3:
                continue
            matched = [lit for lit in canon if any(lit_match(cc, lit) for cc in econd)]
            if not matched:
                continue
            found_any = True
            unmatched_conditions = [cc for cc in econd if not any(lit_match(cc, lit) for lit in canon)]
            if not unmatched_conditions:
                found_clean = True
                if summary[tid]["example"] is None:
                    summary[tid]["example"] = {"seed": seed, "conditions": econd}
        if found_any:
            summary[tid]["any_top15_literal_match_room"] += 1
        if found_clean:
            summary[tid]["clean_subset_room"] += 1

print(json.dumps(summary, indent=2))
