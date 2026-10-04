"""TASK-114 Step 3b -- supplementary negative-control enrichment: real-atom sweep.

`step3_negative_control_mining.py` mines only pairs that BOTH happen to already sit in the same
seed's real final top-15 -- a narrow slice (15 of the many thousands of candidates the real search
actually scores). This script enriches that evidence using the exact same real, unmodified engine
functions (`_atoms`, `_metric`, `_eligible`) plus `benchmark_v2_scoring.effective_rule`/
`pair_metrics`, bounded and cheap (one real atom set per seed, ~90-100 atoms, no beam/search
reconstruction): for every (seed, target) where Step 1 (`step1_build_chains.py`) already
identified a qualifying clean broad candidate, this sweeps every real depth-1 atom NOT already on
one of the broad candidate's own features (exactly the real engine's own expansion rule in
`discover_candidates`: "for atom in atoms: if atom.feature in used: continue") and adds it as a
real, single additional condition -- not necessarily a canonical literal, which is the whole point:
most real atoms are NOT the target's own canonical literal, so this is exactly where a destructive
("looks more specific, kills the signal") addition is expected to show up, the reason support/
volume protection exists in the first place (`ADR-115` Decision 5).

Still fully real: every one of these `broad + atom` rules is scored by the real `_metric`/
`_eligible`/`_development_score` and the real `pair_metrics`/`effective_rule`, nothing invented or
re-derived.
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

OUT_DIR = Path(__file__).resolve().parent / "step3b-atom-sweep-raw"
IN_DIR = Path(__file__).resolve().parent / "step1-chains-raw"


def sweep_for_seed(seed: int) -> dict[str, Any]:
    step1_doc = json.loads((IN_DIR / f"seed-{seed}.json").read_text(encoding="utf-8"))
    results: dict[str, Any] = {"seed": seed, "targets": {}}

    targets_needing_sweep = [
        tid
        for tid, entry in step1_doc["targets"].items()
        if entry.get("chainable") and entry.get("has_qualifying_broad_candidate")
    ]
    if not targets_needing_sweep:
        return results

    with tempfile.TemporaryDirectory(prefix=f"task114-3b-{seed}-") as tmp:
        draw = s1.vc.build_draw(seed, Path(tmp), s1.tg.DESIGNS)
        outcome = s1.primary_outcome()
        config = s1.engine.DiscoveryConfig(seed=seed)
        development = draw.frame.filter(pl.col("split_label") == "development")
        atoms = s1.engine._atoms(development, draw.features, config)

        for target_id in targets_needing_sweep:
            entry = step1_doc["targets"][target_id]
            canon = s1.canonical_conditions(target_id)
            target = s1.scoring.Target(
                target_id=target_id,
                stratum="core",
                conditions=canon,
                affected=draw.masks[target_id],
                canonical_in_language=canon,
                assessed=True,
            )
            broad = entry["chosen_broad_candidate"]
            broad_conditions = broad["conditions"]
            used_features = {c["feature"] for c in broad_conditions}
            broad_step = s1._measure_step(draw, outcome, config, development, broad_conditions, target)
            findings = []
            for atom in atoms:
                if atom.feature in used_features:
                    continue
                child_conditions = broad_conditions + [
                    {"feature": atom.feature, "operator": atom.operator, "value": atom.value}
                ]
                child_step = s1._measure_step(draw, outcome, config, development, child_conditions, target)
                bv = broad_step["benchmark_v2_scoring"]
                cv = child_step["benchmark_v2_scoring"]
                specificity_increased = cv["j_e"] > bv["j_e"] or cv["cr"] > bv["cr"]
                coverage_collapsed = cv["recall"] < s1.COVERAGE_RECALL
                evidence_collapsed = (not child_step["eligible"]) or (
                    child_step["engine_metric_development"] is None
                    or child_step["engine_metric_development"]["harm_per_booking"] <= 0
                )
                is_negative_control = specificity_increased and (coverage_collapsed or evidence_collapsed)
                if is_negative_control:
                    findings.append(
                        {
                            "added_atom": {
                                "feature": atom.feature,
                                "operator": atom.operator,
                                "value": atom.value,
                            },
                            "is_canonical_literal": any(
                                _m(atom, lit) for lit in canon
                            ),
                            "broad_step": broad_step,
                            "child_step": child_step,
                            "coverage_collapsed": coverage_collapsed,
                            "evidence_collapsed": evidence_collapsed,
                        }
                    )
            results["targets"][target_id] = {
                "broad_candidate_id": broad["candidate_id"],
                "n_atoms_swept": len(atoms) - len(used_features),
                "n_negative_control_atoms_found": len(findings),
                "negative_control_findings": findings,
            }
    return results


def _m(atom, lit) -> bool:
    if atom.feature != lit.feature:
        return False
    if lit.operator == "eq":
        return atom.operator == "eq" and atom.value == lit.value
    return atom.operator == lit.operator


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
        print(f"seed {seed}: sweeping atoms...", flush=True)
        result = sweep_for_seed(seed)
        out_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        total_nc = sum(t["n_negative_control_atoms_found"] for t in result["targets"].values())
        print(f"  wrote {out_path} ({total_nc} negative-control atom additions found across {len(result['targets'])} targets)")
    final_digest = s1._verify_engine()
    print(f"engine.py sha256 after run: {final_digest} (unchanged)")


if __name__ == "__main__":
    main()
