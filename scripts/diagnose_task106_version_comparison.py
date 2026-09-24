"""POST-HOC DIAGNOSTIC (`TASK-106`): how the frozen v0.6.2 candidate set differs from earlier
frozen travel candidate sets, under TASK-028's lenient statistic AND a specific-rule statistic
(Jaccard >= 0.5). Read-only over frozen candidate files; no engine/gate/threshold change.

Earlier runs' `artifacts/blind/*.candidates.json` are gitignored and per-checkout: pass
`--blind-root` at a checkout that holds them. Candidate conditions are re-applied to the current
analytical frame (same rows/features; v1.1.0 only adds `travel_month`).
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagnose_oracle_decomposition import _frame_mask, _rule_expr_local  # noqa: E402
from policy_analytics.discovery.engine import Condition  # noqa: E402
from policy_analytics.validation.apply import load_analytical_frame  # noqa: E402

ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
GT = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
SCOREABLE = ("P01", "P02", "P03", "P04", "P06", "P08", "P09")
RUNS = (
    "task-015-official-20260816-015",
    "task-058-remediation-20260817-001",
    "task-060-iteration-20260820-002",
    "task-060-iteration-20260820-004",
    "task-064-beam-20260822-001",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blind-root", type=Path, required=True)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    frame = load_analytical_frame(ROOT)
    index_of = {b: i for i, b in enumerate(cast("list[str]", frame["booking_id"].to_list()))}
    gt = json.loads(GT.read_text(encoding="utf-8"))
    masks: dict[str, int] = {}
    for pattern in gt["patterns"]:
        packed = 0
        for b in pattern["affected_booking_ids"]:
            packed |= 1 << index_of[b]
        masks[str(pattern["id"])] = packed
    sources: list[tuple[str, Path, Path | None]] = [
        (r, args.blind_root / f"{r}.candidates.json", None) for r in RUNS
    ]
    sources.append(
        (
            "task-103-run1 (v0.6.2)",
            REPOSITORY / "docs/benchmark/task-103-evidence/run1/candidates.json",
            REPOSITORY / "docs/benchmark/task-103-evidence/run1/evaluation.json",
        )
    )
    out: dict[str, Any] = {}
    for name, path, ev_path in sources:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cands = payload["candidates"]
        method = payload.get("discovery_method_version") or payload.get("methodology_version")
        rows: list[dict[str, Any]] = []
        for c in cands:
            rule = tuple(
                Condition(x["feature"], x["operator"], x["value"]) for x in c["conditions"]
            )
            m = _frame_mask(frame, _rule_expr_local(rule))
            n_exp = m.bit_count()
            per = {}
            for pid in SCOREABLE:
                a = masks[pid]
                inter = (m & a).bit_count()
                per[pid] = (inter / a.bit_count(), inter / (m | a).bit_count())
            rows.append({"id": c["candidate_id"], "n_exposed": n_exp, "per": per})
        ev_file = ev_path or args.evaluation_root / f"task-028-{name.split('-2026')[0]}-001.json"
        recovered: list[str] | None = None
        levels: dict[str, str] = {}
        candidates_for_eval = [
            p
            for p in args.evaluation_root.glob("task-028-*.json")
            if name.split("-2026")[0][5:] in p.name
        ]
        for p in [ev_path] if ev_path else candidates_for_eval[:1]:
            if p is not None and p.exists():
                e = json.loads(p.read_text(encoding="utf-8"))
                recovered = e["metrics"]["economic_weighted_recall"]["recovered_scoreable_patterns"]
                levels = {s["candidate_id"]: s["evidence_level"] for s in e["candidate_scores"]}
        del ev_file
        pred = ("predictive_association", "adjusted_observational_association")
        out[name] = {
            "discovery_method_version": method,
            "n_candidates": len(rows),
            "median_exposed_full_cohort": sorted(r["n_exposed"] for r in rows)[len(rows) // 2],
            "task028_recovered_scoreable_patterns": recovered,
            "candidates_matching_>=3_patterns_lenient": sum(
                1 for r in rows if sum(1 for pid in SCOREABLE if r["per"][pid][0] >= 0.5) >= 3
            ),
            "specific_j>=0.5_any_level": {
                pid: [r["id"] for r in rows if r["per"][pid][1] >= 0.5] for pid in SCOREABLE
            },
            "specific_j>=0.5_predictive": {
                pid: [
                    r["id"] for r in rows if r["per"][pid][1] >= 0.5 and levels.get(r["id"]) in pred
                ]
                for pid in SCOREABLE
            },
            "best_jaccard": {
                pid: round(max(r["per"][pid][1] for r in rows), 3) for pid in SCOREABLE
            },
        }
        print(
            name,
            method,
            out[name]["n_candidates"],
            out[name]["median_exposed_full_cohort"],
            out[name]["task028_recovered_scoreable_patterns"],
            {k: v for k, v in out[name]["specific_j>=0.5_any_level"].items() if v},
        )
    args.out.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
