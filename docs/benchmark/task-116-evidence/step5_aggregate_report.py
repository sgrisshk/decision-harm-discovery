"""TASK-116 Step 5 -- aggregate Step 3's per-seed measurements into the summary numbers the
results doc cites (displacement relationship counts, capacity-sensitivity curve counts, role
composition, C07 guard hits). Pure aggregation, read-only."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
results = json.loads((HERE / "step3-measurements-results.json").read_text())

STRONG = ("C04", "C06", "C09", "C14", "C15")
TARGETS = (*STRONG, "C07")

disp_counts = {t: Counter() for t in TARGETS}
curve_counts = {t: {k: Counter() for k in ("15", "30", "60", "unlimited")} for t in TARGETS}
n_admissible_total_by_target = {t: [] for t in TARGETS}
rank_by_target = {t: [] for t in TARGETS}

for seed_doc in results:
    for t in TARGETS:
        e = seed_doc["targets"].get(t, {})
        if not e.get("has_productive_descendant"):
            continue
        n_admissible_total_by_target[t].append(e["n_admissible_total"])
        rank_by_target[t].append(e["productive_descendant_rank"])
        disp = e.get("displacement", {})
        rel = disp.get("relationship_to_productive_descendant")
        if rel:
            disp_counts[t][rel] += 1
        else:
            disp_counts[t][disp.get("note", "?")] += 1
        curve = e.get("capacity_sensitivity_curve", {})
        for k in ("15", "30", "60", "unlimited"):
            c = curve.get(k, {})
            key = (
                ("survives" if c.get("survives_cutoff") else "excluded")
                + "/"
                + ("pass" if c.get("passes_validation") else "no-pass-or-NA")
            )
            curve_counts[t][k][key] += 1

print("=== Displacement relationship counts (at real K=15), per target ===")
for t in TARGETS:
    if disp_counts[t]:
        print(t, dict(disp_counts[t]))

print()
print("=== Capacity-sensitivity curve counts, per target, per K ===")
for t in TARGETS:
    if n_admissible_total_by_target[t]:
        print(t, "n_applicable_seeds=", len(n_admissible_total_by_target[t]))
        for k in ("15", "30", "60", "unlimited"):
            print("  K=", k, dict(curve_counts[t][k]))

print()
print("=== productive descendant rank stats (within applicable seeds) ===")
for t in TARGETS:
    if rank_by_target[t]:
        rs = rank_by_target[t]
        print(t, "ranks:", sorted(rs))
        print(t, "pool sizes:", n_admissible_total_by_target[t])

print()
print("=== role_composition_real_k15 aggregate across all seeds ===")
kept_sizes = [sd["role_composition_real_k15"]["n_kept"] for sd in results]
touching = [sd["role_composition_real_k15"]["n_touching_any_strong_target_canonical_feature"] for sd in results]
shortlist_sizes = [sd["role_composition_real_k15"]["acquisition_shortlist_size"] for sd in results]
print("n seeds:", len(results))
print(
    "n_kept (real K=15 refinement slots filled) min/max/mean:",
    min(kept_sizes), max(kept_sizes), sum(kept_sizes) / len(kept_sizes),
)
print(
    "touching-any-strong-target-canonical-feature min/max/mean:",
    min(touching), max(touching), sum(touching) / len(touching),
)
print("acquisition shortlist size (all seeds):", set(shortlist_sizes))

print()
print("=== C07 guard hits aggregate ===")
n_hits = [sd["c07_guard"]["n_hits_in_pool"] for sd in results]
print("n_hits_in_pool per seed min/max/mean:", min(n_hits), max(n_hits), sum(n_hits) / len(n_hits))
specific_hits = sum(1 for sd in results for h in sd["c07_guard"]["hits"] if h["is_specific"])
total_hits = sum(n_hits)
print("total hits across all seeds:", total_hits, "is_specific hits:", specific_hits)
reject_hits = sum(
    1
    for sd in results
    for h in sd["c07_guard"]["hits"]
    if h.get("real_validation_verdict") == "REJECT"
)
print("REJECT-verdict hits:", reject_hits)
