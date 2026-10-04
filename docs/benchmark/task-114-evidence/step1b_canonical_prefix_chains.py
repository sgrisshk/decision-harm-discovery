"""TASK-114 Step 1b -- supplementary probe, Method B ("canonical single-literal starts").

`step1_build_chains.py` (Method A) anchors every chain's starting "broad candidate" on an actual
member of the seed's real, committed final top-15 whose own conditions are a CLEAN subset of the
target's canonical literals. That is the most literal reading of "a broad candidate covers a Core
target" (the engine's own already-persisted output), but it under-counts: a target's own single
canonical literal, taken alone, is itself a legitimate "broad candidate" in H114's sense (the most
general possible true-to-target rule) whether or not it happened to survive the search's own beam/
final-selection cut to appear in that seed's top-15. Excluding it would silently make this
autopsy's coverage depend on an unrelated question (did this literal also win a top-15 slot on its
own merits?), not on H114's actual question (does the ranking prefer broad over specific once both
are constructed and scored by the real functions?).

Method B therefore constructs, directly from `synthetic_benchmark_v2_targets.DESIGNS`'s own
canonical literals (never from anything invented or tuned on this data), one chain per possible
single-literal starting point: `{canon[i]} -> +canon[j] -> +canon[k] -> ... -> full canonical`,
covering every literal in turn as the starting point, remaining literals added in the canonical
rule's own declared order. Every step is measured with the exact same real, unmodified functions
as Method A (`_metric`, `_eligible`, `_development_score`, `_exposed_rows`,
`benchmark_v2_scoring.effective_rule`/`pair_metrics`/`metric_specific`). A seed/target/starting-
literal combination is "applicable" only if its first (single-literal) step already covers the
target (Coverage, recall >= 0.5) -- exactly Method A's own applicability bar, just not gated on
also having survived to a real top-15.

This is a supplementary, equally-reproducible probe over the SAME already-collected 4001-4030 /
4101-4130 data -- no new seed, no new score, no new candidate invented outside the target's own
pre-declared canonical literals (`ADR-107`/`TASK-107`, committed long before this task).
"""
# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import step1_build_chains as s1

import polars as pl


OUT_DIR = Path(__file__).resolve().parent / "step1b-canonical-prefix-raw"


def build_for_seed(seed: int) -> dict[str, Any]:
    results: dict[str, Any] = {"seed": seed, "targets": {}}
    with tempfile.TemporaryDirectory(prefix=f"task114b-{seed}-") as tmp:
        draw = s1.vc.build_draw(seed, Path(tmp), s1.tg.DESIGNS)
        outcome = s1.primary_outcome()
        config = s1.engine.DiscoveryConfig(seed=seed)
        development = draw.frame.filter(pl.col("split_label") == "development")

        for target_id in s1.NON_CHAINABLE_TARGETS:
            results["targets"][target_id] = {"chainable": False}

        for target_id in s1.CHAINABLE_TARGETS:
            canon = s1.canonical_conditions(target_id)
            design = s1.DESIGN_INDEX[target_id]
            target = s1.scoring.Target(
                target_id=target_id,
                stratum="core",
                conditions=canon,
                affected=draw.masks[target_id],
                canonical_in_language=canon,
                assessed=True,
            )
            starts: list[dict[str, Any]] = []
            for start_idx in range(len(canon)):
                order = [canon[start_idx]] + [c for i, c in enumerate(canon) if i != start_idx]
                step_conditions_list: list[list[dict[str, Any]]] = []
                current: list[dict[str, Any]] = []
                for lit in order:
                    current = current + [{"feature": lit.feature, "operator": lit.operator, "value": lit.value}]
                    step_conditions_list.append(list(current))
                steps = [
                    s1._measure_step(draw, outcome, config, development, sc, target)
                    for sc in step_conditions_list
                ]
                applicable = steps[0]["benchmark_v2_scoring"]["recall"] >= s1.COVERAGE_RECALL
                starts.append(
                    {
                        "starting_literal_index_in_canonical_order": start_idx,
                        "starting_literal": {
                            "feature": canon[start_idx].feature,
                            "operator": canon[start_idx].operator,
                            "value": canon[start_idx].value,
                        },
                        "applicable_single_literal_covers_target": applicable,
                        "chain_steps": steps,
                    }
                )
            results["targets"][target_id] = {
                "chainable": True,
                "canonical_rule": design.rule,
                "starts": starts,
            }
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for seed in args.seeds:
        out_path = OUT_DIR / f"seed-{seed}.json"
        if out_path.exists():
            print(f"seed {seed}: already built, skipping")
            continue
        print(f"seed {seed}: building Method B chains...", flush=True)
        result = build_for_seed(seed)
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        n_app = sum(
            1
            for t in result["targets"].values()
            if t.get("chainable")
            for st in t["starts"]
            if st["applicable_single_literal_covers_target"]
        )
        print(f"  wrote {out_path} ({n_app} applicable starting-literal chains)")
    final_digest = s1._verify_engine()
    print(f"engine.py sha256 after run: {final_digest} (unchanged)")


if __name__ == "__main__":
    main()
