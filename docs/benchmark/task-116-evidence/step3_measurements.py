"""TASK-116 Step 3 -- combine Step 1's pool reconstruction and Step 2's real validation verdicts
into the four required measurements (`ADR-117` Decision 3), per seed, per `H114`-strong target
(`C04, C06, C09, C14, C15`) plus `C07` (negative control).

Pure aggregation over already-computed, already-committed JSON -- no engine run, no new
validation call. Read-only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
POOL_DIR = HERE / "step1-pool-raw"
VAL_DIR = HERE / "step2-validation-raw"
OUT = HERE / "step3-measurements-results.json"

STRONG: tuple[str, ...] = ("C04", "C06", "C09", "C14", "C15")
TARGETS: tuple[str, ...] = (*STRONG, "C07")
CAPACITY_LEVELS: tuple[int, ...] = (15, 30, 60)  # "unlimited" handled separately
REAL_TOP_K = 15


def _rule_key(conditions: list[dict[str, Any]]) -> str:
    return " & ".join(
        f"{c['feature']} {c['operator']} {c['value']!r}"
        for c in sorted(conditions, key=lambda c: (c["feature"], c["operator"], str(c["value"])))
    )


def _is_subset(small: list[dict[str, Any]], big: list[dict[str, Any]]) -> bool:
    small_set = {(c["feature"], c["operator"], c["value"]) for c in small}
    big_set = {(c["feature"], c["operator"], c["value"]) for c in big}
    return small_set.issubset(big_set) and small_set != big_set


def _structure(conditions: list[dict[str, Any]]) -> frozenset[tuple[str, str]]:
    return frozenset((c["feature"], c["operator"]) for c in conditions)


def classify_displacement(
    boundary_item: dict[str, Any], productive: dict[str, Any]
) -> str:
    """broad ancestor / sibling / unrelated / duplicate-equivalent-structure, per ADR-117
    Decision 3 item 2. Computed purely from conditions/parent_conditions already recorded by
    Step 1 -- no new engine call."""
    if _structure(boundary_item["conditions"]) == _structure(productive["conditions"]):
        return "duplicate_equivalent_structure"
    if _is_subset(boundary_item["conditions"], productive["conditions"]) or _is_subset(
        productive["conditions"], boundary_item["conditions"]
    ):
        return "broad_ancestor"
    if _rule_key(boundary_item["parent_conditions"]) == _rule_key(productive["parent_conditions"]):
        return "sibling"
    return "unrelated"


def simulate_capacity_cutoff(
    ranked_pool: list[dict[str, Any]], verdicts: dict[str, str], cap: int
) -> dict[str, Any]:
    """Replays the real, reverted `_refinement_candidates` batching exactly (`ADR-117` Decision 3
    item 3): process the score-descending pool in batches of `cap`, validate each batch (using
    REAL verdicts already computed by Step 2 where available), stop once `cap` have PASSed
    (verdict != REJECT). Returns the kept set (in encounter order) and whether the probe depth
    (ranks with a known real verdict) was sufficient to resolve the simulation, or whether it ran
    out of known verdicts before a determination could be made (disclosed, never guessed)."""
    kept: list[dict[str, Any]] = []
    start = 0
    exhausted_known_depth = False
    while start < len(ranked_pool) and len(kept) < cap:
        batch = ranked_pool[start : start + cap]
        start += cap
        for item in batch:
            key = _rule_key(item["conditions"])
            if key not in verdicts:
                exhausted_known_depth = True
                continue
            if verdicts[key] != "REJECT":
                kept.append(item)
        if exhausted_known_depth:
            break
    return {
        "kept": kept[:cap],
        "n_kept": min(len(kept), cap),
        "exhausted_known_verdict_depth": exhausted_known_depth,
    }


def measure_seed(seed: int) -> dict[str, Any]:
    pool_doc = json.loads((POOL_DIR / f"pool-seed-{seed}.json").read_text())
    val_path = VAL_DIR / f"val-seed-{seed}.json"
    val_doc = json.loads(val_path.read_text()) if val_path.exists() else {"rules": {}}
    verdicts = {k: v["verdict"] for k, v in val_doc["rules"].items()}

    top60 = pool_doc["top60_pool"]  # already rank-ordered 1..60 (or fewer if pool smaller)

    out: dict[str, Any] = {"seed": seed, "targets": {}}
    for tid in TARGETS:
        summary = pool_doc["per_target_summary"][tid]
        productive = summary.get("productive_descendant")
        entry: dict[str, Any] = {
            "has_productive_descendant": productive is not None,
            "n_admissible_total": summary["n_admissible_total"],
        }
        if productive is None:
            out["targets"][tid] = entry
            continue

        prod_key = _rule_key(productive["conditions"])
        prod_rank = productive["rank"]
        prod_verdict = verdicts.get(prod_key)
        entry.update(
            {
                "productive_descendant_conditions": productive["conditions"],
                "productive_descendant_rank": prod_rank,
                "productive_descendant_j_e": productive["j_e"],
                "productive_descendant_dev_score": productive["development_score"],
                "generated_and_eligible": True,  # by construction: it is in the admissible pool
                "real_validation_verdict_unlimited_cap": prod_verdict,
                "passes_real_validation_unlimited_cap": (
                    None if prod_verdict is None else prod_verdict != "REJECT"
                ),
            }
        )

        # Measurement 3: capacity-sensitivity curve at K=15/30/60 using the real batching replay.
        curve: dict[str, Any] = {}
        for cap in CAPACITY_LEVELS:
            sim = simulate_capacity_cutoff(top60, verdicts, cap)
            kept_keys = {_rule_key(i["conditions"]) for i in sim["kept"]}
            survives = prod_key in kept_keys
            curve[str(cap)] = {
                "n_kept": sim["n_kept"],
                "survives_cutoff": survives,
                "passes_validation": (survives and prod_verdict is not None and prod_verdict != "REJECT"),
                "reached_within_known_probe_depth": prod_rank <= 60,
                "simulation_exhausted_known_verdict_depth": sim["exhausted_known_verdict_depth"],
            }
        curve["unlimited"] = {
            "n_kept": None,
            "survives_cutoff": True,  # unlimited cap excludes nothing by definition
            "passes_validation": entry["passes_real_validation_unlimited_cap"],
            "reached_within_known_probe_depth": True,
            "simulation_exhausted_known_verdict_depth": False,
        }
        entry["capacity_sensitivity_curve"] = curve

        # Measurement 2: displacement accounting at the REAL cap K=15.
        sim15 = simulate_capacity_cutoff(top60, verdicts, REAL_TOP_K)
        kept15_keys = {_rule_key(i["conditions"]) for i in sim15["kept"]}
        if prod_key not in kept15_keys and sim15["kept"]:
            boundary = sim15["kept"][-1]  # lowest-scoring member of the real K=15 kept set
            entry["displacement"] = {
                "boundary_slot_conditions": boundary["conditions"],
                "boundary_slot_parent_conditions": boundary["parent_conditions"],
                "boundary_slot_dev_score": boundary["development_score"],
                "relationship_to_productive_descendant": classify_displacement(boundary, productive),
            }
        elif prod_key in kept15_keys:
            entry["displacement"] = {"note": "productive descendant WAS kept at real K=15 (not displaced)"}
        else:
            entry["displacement"] = {"note": "no items kept at K=15 in simulation (unexpected)"}

        # Measurement 1 criterion components, assembled explicitly.
        entry["criterion"] = {
            "c1_productive_descendant_exists": True,
            "c2_capacity_cutoff_is_first_cause": (
                not curve[str(REAL_TOP_K)]["survives_cutoff"]
                and prod_verdict is not None
                and prod_verdict != "REJECT"
            ),
            "c3_passes_real_validation_unlimited": entry["passes_real_validation_unlimited_cap"],
        }
        out["targets"][tid] = entry

    # Measurement 4: role composition of the REAL K=15 kept set (whichever target we last
    # simulated for -- the kept set is target-independent, computed once more here cleanly).
    sim15_generic = simulate_capacity_cutoff(top60, verdicts, REAL_TOP_K)
    canonical_features_by_target = {
        tid: {
            c["feature"]
            for c in (pool_doc["per_target_summary"][tid].get("productive_descendant") or {}).get(
                "conditions", []
            )
        }
        for tid in TARGETS
    }
    all_canon_features: set[str] = set()
    for feats in canonical_features_by_target.values():
        all_canon_features |= feats
    on_target_count = sum(
        1 for item in sim15_generic["kept"]
        if any(c["feature"] in all_canon_features for c in item["conditions"])
    )
    out["role_composition_real_k15"] = {
        "n_kept": sim15_generic["n_kept"],
        "n_touching_any_strong_target_canonical_feature": on_target_count,
        "acquisition_shortlist_size": pool_doc["n_shortlist"],
        "note": (
            "Acquisition shortlist and refinement descendants occupy structurally SEPARATE "
            "output segments in the real (reverted) v0.6.4 mechanism -- refinement candidates "
            "are appended after the untouched shortlist, each phase capped separately at "
            "config.top_k. They do not compete for literally the same output list slots; what "
            "is shared is config.top_k itself (reused as both the refinement batch size and "
            "stop threshold) and _development_score (the same ranking function both stages use)."
        ),
    }

    # C07 guard (ADR-117 Decision 5): does the known pathological-narrowing literal
    # (party_size>=4.0 on an acquisition_channel=direct & supplier=BlueWing parent) appear in the
    # pool, and if so, does unlimited capacity make it indistinguishable from genuine refinement?
    guard_hits = pool_doc.get("c07_guard_literal_hits", [])
    guard_entries = []
    for hit in guard_hits:
        key = _rule_key(hit["conditions"])
        guard_entries.append(
            {
                "conditions": hit["conditions"],
                "rank": hit["rank"],
                "j_e": hit["j_e"],
                "recall": hit["recall"],
                "is_specific": hit["is_specific"],
                "real_validation_verdict": verdicts.get(key),
            }
        )
    out["c07_guard"] = {"n_hits_in_pool": len(guard_hits), "hits": guard_entries}
    return out


def main() -> None:
    seeds = sorted(
        int(p.stem.replace("pool-seed-", "")) for p in POOL_DIR.glob("pool-seed-*.json")
    )
    results = [measure_seed(seed) for seed in seeds]
    OUT.write_text(json.dumps(results, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(results)} seeds)")


if __name__ == "__main__":
    main()
