"""TASK-115 Step 3 -- Mechanism PASS analysis. Compares the modified (refinement-augmented)
engine's real output on `4001-4030`/`4101-4130` (`step3-dev-seeds/modified-seed-*.json`, written
by `step3_run_modified_dev_seeds.py`) against the already-committed baseline (pre-TASK-115) raw
output for the identical seeds (`docs/benchmark/task-109-evidence/engine-raw/seed-*.json` for
4001-4030, `docs/benchmark/task-112-evidence/step5-paired-4101-4130/baseline-seed-*.json` for
4101-4130 -- never re-run here).

For each of the 5 strong `H114` targets (`C04, C06, C09, C14, C15`) plus the secondary `H01` and
the mandatory `C07` negative control: did a refinement candidate (identified by the
"TASK-115 refinement candidate" warning marker `engine.py` writes) appear, and does the modified
engine's per-seed Specific/Coverage status for that target improve relative to baseline on that
same seed. Reports per-target, per-seed detail plus the aggregate verdict.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
T109_RAW = REPO / "docs/benchmark/task-109-evidence/engine-raw"
T112_BASELINE = REPO / "docs/benchmark/task-112-evidence/step5-paired-4101-4130"
MODIFIED_DIR = Path(__file__).resolve().parent / "step3-dev-seeds"
THETA_KEY = "0.50"

FINAL_CORE: tuple[str, ...] = ("C02", "C04", "C06", "C07", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
STRONG_TARGETS: tuple[str, ...] = ("C04", "C06", "C09", "C14", "C15")
SECONDARY_TARGET = "H01"
NEGATIVE_CONTROL = "C07"
ALL_DEV_SEEDS = list(range(4001, 4031)) + list(range(4101, 4131))


def load_baseline(seed: int) -> dict[str, Any]:
    if 4001 <= seed <= 4030:
        return json.loads((T109_RAW / f"seed-{seed}.json").read_text())
    return json.loads((T112_BASELINE / f"baseline-seed-{seed}.json").read_text())


def load_modified(seed: int) -> dict[str, Any]:
    return json.loads((MODIFIED_DIR / f"modified-seed-{seed}.json").read_text())


def specific_set(score_doc: dict[str, Any]) -> set[str]:
    core = score_doc["score"]["strata"].get("core", {})
    return set(core.get("specific_targets", {}).get(THETA_KEY, []))


def coverage_set(score_doc: dict[str, Any]) -> set[str]:
    core = score_doc["score"]["strata"].get("core", {})
    return set(core.get("coverage_targets", []))


def refinement_candidate_ids(modified_doc: dict[str, Any]) -> set[str]:
    out = set()
    for c in modified_doc["engine"]["candidates"]:
        if any("TASK-115 refinement candidate" in w for w in c.get("warnings", [])):
            out.add(c["candidate_id"])
    return out


def main() -> None:
    missing = [s for s in ALL_DEV_SEEDS if not (MODIFIED_DIR / f"modified-seed-{s}.json").exists()]
    if missing:
        print(f"WARNING: {len(missing)} seeds not yet run: {missing[:10]}{'...' if len(missing) > 10 else ''}")
    available_seeds = [s for s in ALL_DEV_SEEDS if s not in missing]
    print(f"Analyzing {len(available_seeds)}/{len(ALL_DEV_SEEDS)} seeds available so far.\n")

    per_target_rows: dict[str, list[dict[str, Any]]] = {t: [] for t in FINAL_CORE}
    refinement_seed_counts: list[int] = []

    for seed in available_seeds:
        baseline_doc = load_baseline(seed)
        modified_doc = load_modified(seed)
        b_spec = specific_set(baseline_doc)
        m_spec = specific_set(modified_doc)
        b_cov = coverage_set(baseline_doc)
        m_cov = coverage_set(modified_doc)
        refine_ids = refinement_candidate_ids(modified_doc)
        refinement_seed_counts.append(len(refine_ids))
        for tid in FINAL_CORE:
            per_target_rows[tid].append(
                {
                    "seed": seed,
                    "baseline_specific": tid in b_spec,
                    "modified_specific": tid in m_spec,
                    "baseline_coverage": tid in b_cov,
                    "modified_coverage": tid in m_cov,
                    "gained_specific": (tid not in b_spec) and (tid in m_spec),
                    "lost_specific": (tid in b_spec) and (tid not in m_spec),
                    "lost_coverage": (tid in b_cov) and (tid not in m_cov),
                    "n_refinement_candidates_this_seed": len(refine_ids),
                }
            )

    print(f"Seeds with >=1 refinement candidate added: "
          f"{sum(1 for n in refinement_seed_counts if n > 0)}/{len(available_seeds)}")
    print(f"Total refinement candidates added across all seeds: {sum(refinement_seed_counts)}\n")

    summary: dict[str, Any] = {}
    print(f"{'target':6} {'base_spec/n':>12} {'mod_spec/n':>12} {'gained':>7} {'lost_spec':>10} {'lost_cov':>9}")
    for tid in FINAL_CORE:
        rows = per_target_rows[tid]
        n = len(rows)
        b = sum(r["baseline_specific"] for r in rows)
        m = sum(r["modified_specific"] for r in rows)
        gained = sum(r["gained_specific"] for r in rows)
        lost_spec = sum(r["lost_specific"] for r in rows)
        lost_cov = sum(r["lost_coverage"] for r in rows)
        print(f"{tid:6} {b:4}/{n:<7} {m:4}/{n:<7} {gained:7} {lost_spec:10} {lost_cov:9}")
        summary[tid] = {
            "n_seeds": n,
            "baseline_specific_k": b,
            "modified_specific_k": m,
            "gained_specific_seeds": [r["seed"] for r in rows if r["gained_specific"]],
            "lost_specific_seeds": [r["seed"] for r in rows if r["lost_specific"]],
            "lost_coverage_seeds": [r["seed"] for r in rows if r["lost_coverage"]],
        }

    print("\n=== Strong-target (C04,C06,C09,C14,C15) mechanism-pass check ===")
    n_targets_showing_pattern = 0
    for tid in STRONG_TARGETS:
        s = summary[tid]
        shows_pattern = len(s["gained_specific_seeds"]) > 0
        if shows_pattern:
            n_targets_showing_pattern += 1
        print(f"  {tid}: gained Specific on {len(s['gained_specific_seeds'])}/{s['n_seeds']} seeds "
              f"-> {'PATTERN SHOWN' if shows_pattern else 'not shown'}")
    print(f"\n{n_targets_showing_pattern}/5 strong targets show the predicted pattern "
          f"(bar: >=4 of 5) -> {'BAR MET' if n_targets_showing_pattern >= 4 else 'BAR NOT MET'}")

    print(f"\n=== H01 (secondary) ===")
    s = summary[SECONDARY_TARGET]
    print(f"  gained Specific on {len(s['gained_specific_seeds'])}/{s['n_seeds']} seeds")

    print(f"\n=== C07 (mandatory negative control) ===")
    s = summary[NEGATIVE_CONTROL]
    print(f"  baseline_specific_k={s['baseline_specific_k']}/{s['n_seeds']}, "
          f"modified_specific_k={s['modified_specific_k']}/{s['n_seeds']}")
    print(f"  lost_specific_seeds (baseline had it, modified doesn't): {s['lost_specific_seeds']}")
    print(f"  lost_coverage_seeds: {s['lost_coverage_seeds']}")
    guard_intact = s["modified_specific_k"] >= s["baseline_specific_k"] and not s["lost_coverage_seeds"]
    print(f"  C07 guard intact (no baseline Specific/Coverage lost): {guard_intact}")

    out = {
        "n_seeds_available": len(available_seeds),
        "n_seeds_total": len(ALL_DEV_SEEDS),
        "missing_seeds": missing,
        "per_target_summary": summary,
        "n_strong_targets_showing_pattern": n_targets_showing_pattern,
        "mechanism_pass_bar_met": n_targets_showing_pattern >= 4,
        "c07_guard_intact": guard_intact,
    }
    out_path = Path(__file__).resolve().parent / "step3-analysis-results.json"
    out_path.write_text(json.dumps(out, indent=1, sort_keys=True, default=str))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
