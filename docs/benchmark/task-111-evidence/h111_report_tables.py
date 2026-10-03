"""TASK-111 -- renders the per-target summary table (Markdown) from `h111-analysis-summary.json`.
Pure formatting over already-committed aggregate data; no new computation, no engine call."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
r = json.loads((OUT / "h111-analysis-summary.json").read_text())

TARGETS = ("C02", "C04", "C06", "C08", "C09", "C11", "C12", "C14", "C15", "H01")


def row(tid: str) -> str:
    bucket = r["targets"][tid] if tid in r["targets"] else r["guard_C07"]
    nc = bucket["vs_named_competitor"]
    reach = bucket["reachability"]
    decomp = nc["mean_log_decomp"] or {}
    return (
        f"| {tid} | {nc['n_broad_wins']}/{nc['n_seeds_both_eligible_and_comparable']} "
        f"| {nc['delta_score_mean']:.1f} | {nc['delta_score_median']:.1f} | {nc['delta_score_min']:.1f} | {nc['delta_score_max']:.1f} "
        f"| {decomp.get('harm_contrib', float('nan')):.3f} | {decomp.get('population_contrib', float('nan')):.3f} | {decomp.get('complexity_contrib', float('nan')):.3f} "
        f"| {reach['n_seeds_necessary_condition_holds']}/30 | {reach['n_seeds_specific_in_final_top15']}/30 |"
    )


print("| Target | Broad wins (named competitor) | Mean Delta | Median Delta | Min Delta | Max Delta | log-harm contrib | log-population contrib | log-complexity contrib | Reachability (necessary cond.) | In final top-15 |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for tid in TARGETS:
    print(row(tid))
print(row("C07"))
