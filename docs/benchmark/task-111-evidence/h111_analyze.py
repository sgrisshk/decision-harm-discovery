"""TASK-111 -- pure aggregation over `h111-decomposition-raw.json` (no engine call, no new data).

Computes, per target, per comparison (named-competitor and universal-proxy):
  * preference consistency: on how many of the 30 seeds does the broad rule's real
    `_development_score` exceed the specific rule's.
  * margin: full Delta-score (broad - specific) distribution (mean/median/min/max, sign flips).
  * log-decomposition: Delta-ln(score) = Delta-ln(harm_per_booking)
                                        + population_score_exponent * Delta-ln(n_exposed)
                                        - Delta-ln(1 + 0.15*(k-1))
    (exact additive decomposition of the real formula's own multiplicative structure:
    score = harm_per_booking * n_exposed**0.5 / (1 + 0.15*(k-1)), population_score_exponent=0.5 by
    the frozen `DiscoveryConfig` default) -- only defined on seeds where BOTH rules are eligible
    (harm_per_booking > 0 for both, required for either to ever be `_eligible`/enter `scored`).
  * counterfactual reachability: whether the specific rule's own construction prerequisites
    (>=1 single-literal eligible for 2-literal targets, >=1 of the 3 depth-2 sub-pairs eligible
    for 3-literal targets) hold on each seed.
"""
from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

OUT = Path(__file__).resolve().parent
RAW = json.loads((OUT / "h111-decomposition-raw.json").read_text())

TARGETS = ("C02", "C04", "C06", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
GUARD = "C07"
SEEDS = sorted(int(s) for s in RAW.keys())
POP_EXP = 0.5  # DiscoveryConfig.population_score_exponent frozen default


def log_decompose(specific: dict, broad: dict) -> dict | None:
    if not specific["eligible"] or not broad["eligible"]:
        return None
    hs, hb = specific["harm_per_booking"], broad["harm_per_booking"]
    ns, nb = specific["n_exposed"], broad["n_exposed"]
    ks, kb = specific["k"], broad["k"]
    ds = 1.0 + 0.15 * (ks - 1)
    db = 1.0 + 0.15 * (kb - 1)
    harm_contrib = math.log(hb) - math.log(hs)
    pop_contrib = POP_EXP * (math.log(nb) - math.log(ns))
    complexity_contrib = -(math.log(db) - math.log(ds))
    total_log = harm_contrib + pop_contrib + complexity_contrib
    # sanity check against directly-computed scores
    direct_log = math.log(broad["development_score"]) - math.log(specific["development_score"])
    return {
        "harm_contrib": harm_contrib,
        "population_contrib": pop_contrib,
        "complexity_contrib": complexity_contrib,
        "total_log_delta": total_log,
        "direct_log_delta_check": direct_log,
        "log_decomp_matches_direct": abs(total_log - direct_log) < 1e-9,
        "delta_score": broad["development_score"] - specific["development_score"],
    }


def analyze_pair(tid: str, which: str) -> dict:
    per_seed = []
    for seed in SEEDS:
        entry = RAW[str(seed)][tid]
        specific = entry["specific_direct"]
        broad = entry[which]
        decomp = log_decompose(specific, broad)
        per_seed.append(
            {
                "seed": seed,
                "specific_eligible": specific["eligible"],
                "broad_eligible": broad["eligible"],
                "specific_score": specific["development_score"],
                "broad_score": broad["development_score"],
                "delta_score": (
                    broad["development_score"] - specific["development_score"]
                    if specific["development_score"] is not None and broad["development_score"] is not None
                    else None
                ),
                "broad_wins": (
                    broad["development_score"] > specific["development_score"]
                    if specific["development_score"] is not None and broad["development_score"] is not None
                    else None
                ),
                "decomp": decomp,
            }
        )
    deltas = [p["delta_score"] for p in per_seed if p["delta_score"] is not None]
    wins = [p["broad_wins"] for p in per_seed if p["broad_wins"] is not None]
    n_broad_wins = sum(1 for w in wins if w)
    n_compared = len(wins)
    decomps = [p["decomp"] for p in per_seed if p["decomp"] is not None]
    summary = {
        "target": tid,
        "comparison": which,
        "n_seeds_both_eligible_and_comparable": n_compared,
        "n_broad_wins": n_broad_wins,
        "n_specific_wins": n_compared - n_broad_wins,
        "preference_consistency_fraction": (n_broad_wins / n_compared if n_compared else None),
        "all_30_sign_consistent": (n_broad_wins == n_compared or n_broad_wins == 0) if n_compared == 30 else None,
        "delta_score_mean": st.mean(deltas) if deltas else None,
        "delta_score_median": st.median(deltas) if deltas else None,
        "delta_score_min": min(deltas) if deltas else None,
        "delta_score_max": max(deltas) if deltas else None,
        "delta_score_stdev": st.pstdev(deltas) if len(deltas) > 1 else None,
        "n_sign_flips_vs_mode": sum(
            1 for d in deltas if (d > 0) != (st.mean(deltas) > 0)
        ) if deltas else None,
        "mean_log_decomp": (
            {
                "harm_contrib": st.mean(d["harm_contrib"] for d in decomps),
                "population_contrib": st.mean(d["population_contrib"] for d in decomps),
                "complexity_contrib": st.mean(d["complexity_contrib"] for d in decomps),
            }
            if decomps
            else None
        ),
        "log_decomp_all_checks_pass": all(d["log_decomp_matches_direct"] for d in decomps) if decomps else None,
        "per_seed": per_seed,
    }
    return summary


def reachability(tid: str) -> dict:
    per_seed = []
    for seed in SEEDS:
        entry = RAW[str(seed)][tid]
        canon_k = entry["specific_direct"]["k"]
        if canon_k == 1:
            necessary_ok = entry["specific_direct"]["eligible"]  # single literal IS the rule
        elif canon_k == 2:
            necessary_ok = entry["any_single_eligible"]
        else:
            necessary_ok = entry["any_single_eligible"] or entry["any_subpair_eligible"]
        per_seed.append(
            {
                "seed": seed,
                "canon_k": canon_k,
                "specific_rule_eligible_directly": entry["specific_direct"]["eligible"],
                "necessary_construction_condition_holds": necessary_ok,
                "specific_in_final_top15": entry["specific_in_final_top15"],
                "named_competitor_in_final_top15": entry["named_competitor_in_final_top15"],
            }
        )
    n_necessary_ok = sum(1 for p in per_seed if p["necessary_construction_condition_holds"])
    n_in_final = sum(1 for p in per_seed if p["specific_in_final_top15"])
    return {
        "target": tid,
        "n_seeds_necessary_condition_holds": n_necessary_ok,
        "n_seeds_necessary_condition_fails": 30 - n_necessary_ok,
        "n_seeds_specific_in_final_top15": n_in_final,
        "per_seed": per_seed,
    }


def main() -> None:
    report = {"targets": {}, "guard_C07": {}}
    for tid in TARGETS:
        report["targets"][tid] = {
            "vs_named_competitor": analyze_pair(tid, "named_competitor_direct"),
            "vs_universal_proxy": analyze_pair(tid, "universal_proxy_direct"),
            "reachability": reachability(tid),
        }
    report["guard_C07"] = {
        "vs_named_competitor": analyze_pair(GUARD, "named_competitor_direct"),
        "vs_universal_proxy": analyze_pair(GUARD, "universal_proxy_direct"),
        "reachability": reachability(GUARD),
    }

    # C09/C14 paired analysis
    c09_c14 = {"C14_full_vs_2of3": analyze_pair("C14", "named_competitor_direct")}
    c09_partial_per_seed = []
    for seed in SEEDS:
        entry = RAW[str(seed)]
        full = entry["C09"]["specific_direct"]
        partial = entry["C09_partial_extra"]
        decomp = log_decompose(full, partial)
        c09_partial_per_seed.append(
            {
                "seed": seed,
                "full_rule_score": full["development_score"],
                "full_rule_eligible": full["eligible"],
                "partial_rule_score": partial["development_score"],
                "partial_rule_eligible": partial["eligible"],
                "delta_score_partial_minus_full": (
                    partial["development_score"] - full["development_score"]
                    if full["development_score"] is not None and partial["development_score"] is not None
                    else None
                ),
                "partial_in_final_top15": partial.get("in_final_top15"),
                "decomp": decomp,
            }
        )
    c09_c14["C09_full_vs_tokyo_standard_partial"] = c09_partial_per_seed
    report["C09_C14_paired"] = c09_c14

    (OUT / "h111-analysis-summary.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=str))
    print("wrote", OUT / "h111-analysis-summary.json")

    # Compact stdout summary for quick review
    for tid in TARGETS + (GUARD,):
        bucket = report["targets"].get(tid) or report["guard_C07"]
        nc = bucket["vs_named_competitor"]
        up = bucket["vs_universal_proxy"]
        print(
            f"{tid}: named_competitor wins {nc['n_broad_wins']}/{nc['n_seeds_both_eligible_and_comparable']}, "
            f"mean_delta={nc['delta_score_mean']}; universal_proxy wins {up['n_broad_wins']}/{up['n_seeds_both_eligible_and_comparable']}, "
            f"mean_delta={up['delta_score_mean']}; necessary_cond_holds={bucket['reachability']['n_seeds_necessary_condition_holds']}/30"
        )


if __name__ == "__main__":
    main()
