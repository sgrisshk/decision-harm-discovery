"""TASK-115 Step 3 diagnostic (not a protocol step -- explains the NOT-MET mechanism-pass result).

For each strong target, checks across all 60 seeds whether ANY refinement candidate's conditions
touch ANY of that target's canonical literal features at all, and if so, what its Specific-metric
j_e/cr/recall came out to (via benchmark_v2_scoring, same real functions every other evidence
script in this arc uses) -- distinguishing "the mechanism never even tried something relevant to
this target" from "it tried, but validation or specificity still fell short".
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPO / "packages/analytics/src"),
    str(REPO / "packages/schemas/src"),
    str(REPO / "scripts"),
    str(REPO / "docs/benchmark/task-107-evidence"),
]
import v2_common as vc  # noqa: E402
import policy_analytics.synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics import benchmark_v2_scoring as scoring  # noqa: E402

MODIFIED_DIR = Path(__file__).resolve().parent / "step3-dev-seeds"
STRONG_TARGETS = ("C04", "C06", "C09", "C14", "C15")
DESIGN_INDEX = tg.design_index()


def canon_features(tid: str) -> set[str]:
    return {c.feature for c in DESIGN_INDEX[tid].conditions}


def main() -> None:
    seeds = list(range(4001, 4031)) + list(range(4101, 4131))
    touches: dict[str, int] = {t: 0 for t in STRONG_TARGETS}
    best_je: dict[str, float] = {t: 0.0 for t in STRONG_TARGETS}
    examples: dict[str, Any] = {t: None for t in STRONG_TARGETS}

    for seed in seeds[:10]:  # sample 10 seeds for the expensive real-scoring probe
        doc = json.loads((MODIFIED_DIR / f"modified-seed-{seed}.json").read_text())
        refine_candidates = [
            c for c in doc["engine"]["candidates"]
            if any("TASK-115 refinement candidate" in w for w in c.get("warnings", []))
        ]
        with tempfile.TemporaryDirectory(prefix=f"diag3-{seed}-") as tmp:
            draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
            for tid in STRONG_TARGETS:
                feats = canon_features(tid)
                target = scoring.Target(
                    target_id=tid, stratum="core",
                    conditions=tuple(
                        scoring.CondSpec(c.feature, c.operator, c.value)
                        for c in DESIGN_INDEX[tid].conditions
                    ),
                    affected=draw.masks[tid],
                    canonical_in_language=tuple(
                        scoring.CondSpec(c.feature, c.operator, c.value)
                        for c in DESIGN_INDEX[tid].conditions
                    ),
                    assessed=True,
                )
                for cand in refine_candidates:
                    cfeats = {c["feature"] for c in cand["conditions"]}
                    if not (cfeats & feats):
                        continue
                    touches[tid] += 1
                    cs = tuple(
                        scoring.CondSpec(c["feature"], c["operator"], c["value"])
                        for c in cand["conditions"]
                    )
                    exposed_mask = draw.space.rule_mask(cs)
                    eff = scoring.effective_rule(draw.space, cs, scoring.CONSTANTS.nu)
                    pm = scoring.pair_metrics(draw.space, eff.conditions, exposed_mask, target)
                    if pm.j_e > best_je[tid]:
                        best_je[tid] = pm.j_e
                        examples[tid] = {
                            "seed": seed,
                            "candidate_id": cand["candidate_id"],
                            "conditions": cand["conditions"],
                            "j_e": pm.j_e,
                            "cp": pm.cp,
                            "cr": pm.cr,
                            "recall": pm.recall,
                        }

    print("Sampled 10/60 seeds (4001-4010).")
    for tid in STRONG_TARGETS:
        print(f"\n{tid}: canonical features = {canon_features(tid)}")
        print(f"  refinement candidates touching >=1 canonical feature: {touches[tid]}")
        print(f"  best j_e observed: {best_je[tid]:.3f} (theta_j=0.50 required for Specific)")
        if examples[tid]:
            print(f"  example: {examples[tid]}")


if __name__ == "__main__":
    main()
