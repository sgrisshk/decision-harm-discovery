"""TASK-115 Step 6 -- paired-evaluation aggregation and the two-sided go/no-go verdict (`ADR-116`
Decision 7, 7 conditions -- one more than `TASK-112`'s own 6, the added `C07`-specific guard).

Reads both engines' real end-to-end run output on the fresh reserve (written by
`step5_paired_eval.py`), computes the primary endpoint (Reliable Specific Recall: one-sided 95%
Clopper-Pearson lower bound >= 0.90 on k/30 per Core target, identical semantics to every prior
task in this arc) and the secondary endpoints (per-target Specific hit rate, Exact Recall,
Coverage Recall), reports absolute numbers for both engines side by side, and evaluates all 7
conditions explicitly, with no rebalancing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "docs/benchmark/task-107-evidence"), str(Path(__file__).resolve().parent)]
from step5_paired_eval import FINAL_CORE, compute_rates  # noqa: E402
from v2_common import clopper_pearson_lower  # noqa: E402

THIS_DIR = Path(__file__).resolve().parent
N = 30
THETA = 0.90


def reliable(k: int) -> bool:
    return clopper_pearson_lower(k, N) >= THETA


def main(eval_dir: Path, mechanism_pass: bool) -> None:
    baseline = compute_rates(eval_dir, "baseline")
    modified = compute_rates(eval_dir, "modified")

    rows = []
    for tid in FINAL_CORE:
        b = baseline["per_target_k_of_30"][tid]
        m = modified["per_target_k_of_30"][tid]
        b_cp = clopper_pearson_lower(b["specific"], N)
        m_cp = clopper_pearson_lower(m["specific"], N)
        rows.append(
            {
                "target": tid,
                "baseline_coverage_k": b["coverage"],
                "modified_coverage_k": m["coverage"],
                "baseline_specific_k": b["specific"],
                "modified_specific_k": m["specific"],
                "baseline_specific_cp_lb": b_cp,
                "modified_specific_cp_lb": m_cp,
                "baseline_reliable": b_cp >= THETA,
                "modified_reliable": m_cp >= THETA,
                "baseline_exact_k": b["exact"],
                "modified_exact_k": m["exact"],
            }
        )

    print(
        f"{'target':6} {'b_cov':>5} {'m_cov':>5} {'b_spec':>6} {'m_spec':>6} {'b_cplb':>7} "
        f"{'m_cplb':>7} {'b_rel':>6} {'m_rel':>6} {'b_exact':>7} {'m_exact':>7}"
    )
    for r in rows:
        print(
            f"{r['target']:6} {r['baseline_coverage_k']:5} {r['modified_coverage_k']:5} "
            f"{r['baseline_specific_k']:6} {r['modified_specific_k']:6} "
            f"{r['baseline_specific_cp_lb']:7.3f} {r['modified_specific_cp_lb']:7.3f} "
            f"{str(r['baseline_reliable']):>6} {str(r['modified_reliable']):>6} "
            f"{r['baseline_exact_k']:7} {r['modified_exact_k']:7}"
        )

    n_reliable_baseline = sum(1 for r in rows if r["baseline_reliable"])
    n_reliable_modified = sum(1 for r in rows if r["modified_reliable"])
    total_specific_baseline = sum(r["baseline_specific_k"] for r in rows)
    total_specific_modified = sum(r["modified_specific_k"] for r in rows)
    total_exact_baseline = sum(r["baseline_exact_k"] for r in rows)
    total_exact_modified = sum(r["modified_exact_k"] for r in rows)
    coverage_ever_baseline = sum(1 for r in rows if r["baseline_coverage_k"] >= 1)
    coverage_ever_modified = sum(1 for r in rows if r["modified_coverage_k"] >= 1)
    exact_ever_baseline = sum(1 for r in rows if r["baseline_exact_k"] >= 1)
    exact_ever_modified = sum(1 for r in rows if r["modified_exact_k"] >= 1)
    coverage_losses = [
        r["target"] for r in rows if r["modified_coverage_k"] == 0 and r["baseline_coverage_k"] > 0
    ]
    material_coverage_drop = [
        r["target"]
        for r in rows
        if r["baseline_coverage_k"] > 0 and (r["baseline_coverage_k"] - r["modified_coverage_k"]) / 30 >= 0.20
    ]
    c07_row = next(r for r in rows if r["target"] == "C07")
    c07_guard_intact = c07_row["modified_reliable"] or (not c07_row["baseline_reliable"])
    # C07 does not LOSE reliable Specific recovery: if baseline was reliable, modified must stay
    # reliable; if baseline was never reliable, there is nothing to lose (still reported in full).

    print()
    print(f"n_reliable (CP-LB>=0.90): baseline={n_reliable_baseline}/11  modified={n_reliable_modified}/11")
    print(f"total Specific-hit count across 11x30: baseline={total_specific_baseline}  modified={total_specific_modified}")
    print(f"total Exact-hit count across 11x30: baseline={total_exact_baseline}  modified={total_exact_modified}")
    print(f"Coverage Recall (ever-recovered): baseline={coverage_ever_baseline}/11  modified={coverage_ever_modified}/11")
    print(f"Exact Recall (ever-recovered): baseline={exact_ever_baseline}/11  modified={exact_ever_modified}/11")
    print(f"Core targets losing coverage at headline ever-recovered level: {coverage_losses or 'NONE'}")
    print(f"Core targets with material (>=20%) systematic coverage hit-rate drop: {material_coverage_drop or 'NONE'}")
    print(f"C07: baseline_specific_k={c07_row['baseline_specific_k']}/30 (CP-LB {c07_row['baseline_specific_cp_lb']:.4f}, reliable={c07_row['baseline_reliable']})  "
          f"modified_specific_k={c07_row['modified_specific_k']}/30 (CP-LB {c07_row['modified_specific_cp_lb']:.4f}, reliable={c07_row['modified_reliable']})")
    print(f"baseline n_seeds_any_trap_promoted: {baseline['n_seeds_any_trap_promoted']}")
    print(f"modified n_seeds_any_trap_promoted: {modified['n_seeds_any_trap_promoted']}")

    cond1 = mechanism_pass
    cond2 = n_reliable_modified > n_reliable_baseline
    cond3 = total_specific_modified > total_specific_baseline
    cond4_coverage = (not coverage_losses) and (not material_coverage_drop)
    cond4_exact = exact_ever_modified >= exact_ever_baseline
    cond5_c07 = c07_guard_intact
    cond6_safety = modified["n_seeds_any_trap_promoted"] <= baseline["n_seeds_any_trap_promoted"]
    cond7_no_frozen_change = None  # confirmed separately via git diff, not computable from this data

    verdict = all([cond1, cond2, cond3, cond4_coverage, cond4_exact, cond5_c07, cond6_safety])
    print()
    print("ADR-116 Decision 7 conditions (7 total):")
    print(f"  (0, Mechanism PASS precondition -- Step 3): {cond1}")
    print(f"  (1) Reliable Specific Recall increases vs baseline: {cond2}  ({n_reliable_modified} vs {n_reliable_baseline})")
    print(f"  (2) total Specific-hit count increases: {cond3}  ({total_specific_modified} vs {total_specific_baseline})")
    print(f"  (3) Coverage Recall does not decrease: {cond4_coverage}")
    print(f"  (4) Exact Recall does not decrease: {cond4_exact}  ({exact_ever_modified}/11 vs {exact_ever_baseline}/11)")
    print(f"  (5) C07 does not lose reliable Specific recovery: {cond5_c07}")
    print(f"  (6) precision/safety regression suite does not regress (trap promotion proxy): {cond6_safety}")
    print(f"  (7) no change anywhere to frozen benchmark/scorer/validation thresholds: CONFIRM VIA git diff SEPARATELY, not computable here")
    print()
    print(f"STEP 6 VERDICT (conditions 0-6 only; condition 7 confirmed separately): "
          f"{'SUCCESS (pending condition 7 git-diff confirmation)' if verdict else 'NOT SUCCESS -- hard stop, no second tweak'}")

    out = {
        "rows": rows,
        "n_reliable_baseline": n_reliable_baseline,
        "n_reliable_modified": n_reliable_modified,
        "total_specific_baseline": total_specific_baseline,
        "total_specific_modified": total_specific_modified,
        "total_exact_baseline": total_exact_baseline,
        "total_exact_modified": total_exact_modified,
        "coverage_ever_baseline": coverage_ever_baseline,
        "coverage_ever_modified": coverage_ever_modified,
        "exact_ever_baseline": exact_ever_baseline,
        "exact_ever_modified": exact_ever_modified,
        "coverage_losses": coverage_losses,
        "material_coverage_drop": material_coverage_drop,
        "c07_row": c07_row,
        "baseline_trap_promoted_seeds": baseline["n_seeds_any_trap_promoted"],
        "modified_trap_promoted_seeds": modified["n_seeds_any_trap_promoted"],
        "conditions": {
            "0_mechanism_pass": cond1,
            "1_reliable_specific_recall_increases": cond2,
            "2_total_specific_increases": cond3,
            "3_coverage_recall_not_decreased": cond4_coverage,
            "4_exact_recall_not_decreased": cond4_exact,
            "5_c07_guard": cond5_c07,
            "6_safety_not_worse": cond6_safety,
            "7_no_frozen_change": "confirmed separately via git diff",
        },
        "verdict_conditions_0_to_6": "SUCCESS" if verdict else "NOT SUCCESS",
    }
    (THIS_DIR / "step6-verdict.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str))
    print("wrote step6-verdict.json")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--mechanism-pass", action="store_true")
    a = ap.parse_args()
    main(a.dir, a.mechanism_pass)
