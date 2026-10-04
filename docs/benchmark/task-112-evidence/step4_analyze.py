"""TASK-112 Step 4 -- regression/kill tests on development evidence (4001-4030).

Compares the modified engine's real end-to-end Coverage/Specific/Exact recall (computed by
step5_paired_eval.py's `compute_rates`, reused here) against the already-committed OLD-engine
numbers on the SAME seed range (docs/benchmark/task-109-evidence/engine-aggregate-rates.json).
This is development evidence ONLY -- not used to claim any improvement (that claim is reserved for
the untouched 4101-4130 paired evaluation, Step 5/6, per ADR-113 Decision 5).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from step5_paired_eval import FINAL_CORE, compute_rates  # noqa: E402

OLD = json.loads(
    (REPO / "docs/benchmark/task-109-evidence/engine-aggregate-rates.json").read_text()
)
DEV_DIR = Path(__file__).resolve().parent / "step4-dev-regression"


def main() -> None:
    new = compute_rates(DEV_DIR, "modified")
    old_per_target = OLD["core"]["per_target_k_of_30"]

    print(f"{'target':6} {'old_cov':>8} {'new_cov':>8} {'old_spec':>9} {'new_spec':>9} {'old_exact':>10} {'new_exact':>10}")
    coverage_degraded = []
    specific_changes = {}
    for tid in FINAL_CORE:
        o = old_per_target[tid]
        n = new["per_target_k_of_30"][tid]
        print(
            f"{tid:6} {o['coverage_k_of_n']:8} {n['coverage']:8} "
            f"{o['specific_k_of_n']:9} {n['specific']:9} "
            f"{o['exact_k_of_n']:10} {n['exact']:10}"
        )
        if n["coverage"] < o["coverage_k_of_n"]:
            coverage_degraded.append((tid, o["coverage_k_of_n"], n["coverage"]))
        specific_changes[tid] = (o["specific_k_of_n"], n["specific"])

    print()
    print("C07 (reliable Specific recovery guard):", specific_changes["C07"])
    print("Coverage degraded (any Core target, old > new):", coverage_degraded or "NONE")
    print("n_seeds_any_trap_promoted (modified engine, 4001-4030):", new["n_seeds_any_trap_promoted"])

    out = {
        "new_rates": new,
        "old_per_target_k_of_30": old_per_target,
        "coverage_degraded": coverage_degraded,
        "specific_changes": specific_changes,
    }
    (Path(__file__).resolve().parent / "step4-analysis-summary.json").write_text(
        json.dumps(out, indent=1, sort_keys=True, default=str)
    )
    print("wrote step4-analysis-summary.json")


if __name__ == "__main__":
    main()
