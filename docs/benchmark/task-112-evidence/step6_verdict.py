"""TASK-112 Step 5/6 -- paired-evaluation aggregation and the two-sided go/no-go verdict.

Reads both engines' real end-to-end run output on 4101-4130 (written by step5_paired_eval.py),
computes the primary endpoint (Reliable Specific Recall: one-sided 95% Clopper-Pearson lower
bound >= 0.90 on k/30 per Core target, identical semantics to TASK-109/TASK-111) and the secondary
endpoints (per-target Specific hit rate, Exact Recall, Coverage Recall), reports absolute numbers
for both engines side by side, and evaluates ADR-113 Decision 7's six conditions explicitly, with
no rebalancing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "docs/benchmark/task-107-evidence"), str(Path(__file__).resolve().parent)]
from step5_paired_eval import FINAL_CORE, compute_rates  # noqa: E402
from v2_common import clopper_pearson_lower  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent / "step5-paired-4101-4130"
N = 30
THETA = 0.90


def reliable(k: int) -> bool:
    return clopper_pearson_lower(k, N) >= THETA


def main() -> None:
    baseline = compute_rates(EVAL_DIR, "baseline")
    modified = compute_rates(EVAL_DIR, "modified")

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

    print(f"{'target':6} {'b_cov':>5} {'m_cov':>5} {'b_spec':>6} {'m_spec':>6} {'b_cplb':>7} {'m_cplb':>7} {'b_rel':>6} {'m_rel':>6} {'b_exact':>7} {'m_exact':>7}")
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
    # "ever recovered" / "any_of_30" style counts -- same convention as run_blind_engine.py's
    # coverage_recall_any_of_30 / specific_recall_any_of_30 / exact_recall_any_of_30 (how many of
    # the 11 Core targets are recovered at least once in 30 seeds), used for Decision 7's
    # Coverage (condition 4) and Exact Recall (condition 5) checks -- distinct from condition 3's
    # explicit raw-sum "total Specific-hit count across 11x30".
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

    print()
    print(f"n_reliable (CP-LB>=0.90): baseline={n_reliable_baseline}/11  modified={n_reliable_modified}/11")
    print(f"total Specific-hit count across 11x30: baseline={total_specific_baseline}  modified={total_specific_modified}")
    print(f"total Exact-hit count across 11x30: baseline={total_exact_baseline}  modified={total_exact_modified}")
    print(f"Coverage Recall (ever-recovered, any_of_30 style): baseline={coverage_ever_baseline}/11  modified={coverage_ever_modified}/11")
    print(f"Exact Recall (ever-recovered, any_of_30 style): baseline={exact_ever_baseline}/11  modified={exact_ever_modified}/11")
    print(f"Core targets losing coverage at headline ever-recovered level: {coverage_losses or 'NONE'}")
    print(f"Core targets with material (>=20%) systematic coverage hit-rate drop: {material_coverage_drop or 'NONE'}")
    print(f"baseline n_seeds_any_trap_promoted: {baseline['n_seeds_any_trap_promoted']}")
    print(f"modified n_seeds_any_trap_promoted: {modified['n_seeds_any_trap_promoted']}")

    cond1 = True  # Step 3 Mechanism PASS already confirmed (step3-analysis-summary.json)
    cond2 = n_reliable_modified > n_reliable_baseline
    cond3 = total_specific_modified > total_specific_baseline
    cond4 = (not coverage_losses) and (not material_coverage_drop)
    cond5 = exact_ever_modified >= exact_ever_baseline
    cond6 = modified["n_seeds_any_trap_promoted"] <= baseline["n_seeds_any_trap_promoted"]

    verdict = all([cond1, cond2, cond3, cond4, cond5, cond6])
    print()
    print("ADR-113 Decision 7 conditions:")
    print(f"  (1) Step 3 Mechanism PASS held: {cond1}")
    print(f"  (2) modified has MORE reliable Core targets than baseline: {cond2}  ({n_reliable_modified} vs {n_reliable_baseline})")
    print(f"  (3) total Specific-hit count increases: {cond3}  ({total_specific_modified} vs {total_specific_baseline})")
    print(f"  (4) no Core target loses coverage / no material systematic hit-rate drop: {cond4}")
    print(f"  (5) Exact Recall (ever-recovered) does not worsen: {cond5}  ({exact_ever_modified}/11 vs {exact_ever_baseline}/11; raw totals {total_exact_modified} vs {total_exact_baseline})")
    print(f"  (6) precision/safety regression suite does not worsen (trap promotion proxy): {cond6}")
    print()
    print(f"STEP 6 VERDICT: {'SUCCESS' if verdict else 'NOT SUCCESS -- hard stop, no second tweak'}")

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
        "baseline_trap_promoted_seeds": baseline["n_seeds_any_trap_promoted"],
        "modified_trap_promoted_seeds": modified["n_seeds_any_trap_promoted"],
        "conditions": {
            "1_mechanism_pass": cond1,
            "2_more_reliable_targets": cond2,
            "3_total_specific_increases": cond3,
            "4_no_coverage_loss": cond4,
            "5_exact_recall_not_worse": cond5,
            "6_safety_not_worse": cond6,
        },
        "verdict": "SUCCESS" if verdict else "NOT SUCCESS",
    }
    (Path(__file__).resolve().parent / "step6-verdict.json").write_text(
        json.dumps(out, indent=1, sort_keys=True, default=str)
    )
    print("wrote step6-verdict.json")


if __name__ == "__main__":
    main()
