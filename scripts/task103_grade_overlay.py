"""TASK-103: mechanical Dimension 1/2/3/5 overlay for two official runs (read-only grading).

Reads the two runs' frozen `candidates.json`/`discovery_metrics.json` and `TASK-028` evaluation
reports, verifies whether the two runs' discovery output actually differs, computes the per-run
measurements, and applies `docs/strategy/task-102-outreach-evidence-bar-proposal.md`'s frozen
pass/fail rules literally. Changes no engine, gate, or threshold. Usage:
  uv run python scripts/task103_grade_overlay.py docs/benchmark/task-103-evidence
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

PRECISION_THRESHOLD = 0.8  # Dimension 1, frozen (ADR-097)
FROZEN_RECALL_SET = ("P01", "P06")  # Dimension 3, frozen (ADR-097)
LEVELS = ("descriptive_observation", "predictive_association", "adjusted_observational_association")
PRIOR_ACTIVE_TRAPS = {"T03", "T04"}  # cumulative Part B before this task (TASK-083 / ADR-082)


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _level(name: str) -> int:
    return LEVELS.index(name) if name in LEVELS else -1


def measure(run_dir: Path) -> dict[str, Any]:
    evaluation = _load(run_dir / "evaluation.json")
    scores = cast(list[dict[str, Any]], evaluation["candidate_scores"])
    metrics = cast(dict[str, Any], evaluation["metrics"])
    top_ids = cast(list[str], metrics["top_k_precision"]["top_k_candidate_ids"])
    by_id = {c["candidate_id"]: c for c in scores}
    top = [by_id[i] for i in top_ids]
    good = sum(1 for c in top if c["is_true_pattern"] and not c["is_trap"])
    traps = cast(dict[str, Any], metrics["confounder_trap_rejection"])
    appeared = sorted(k for k, v in traps["trap_appeared_as_candidate"].items() if v)
    promoted = sorted(k for k, v in traps["trap_promoted"].items() if v)
    shadow = [
        c["candidate_id"]
        for c in scores
        if c["is_trap"] and c["policy_readiness"] in {"shadow_policy", "high_confidence"}
    ]
    recall: dict[str, Any] = {}
    for pattern in FROZEN_RECALL_SET:
        best = max(
            (
                _level(c["evidence_level"])
                for c in scores
                if pattern in c["matched_patterns"] and not c["is_trap"]
            ),
            default=-1,
        )
        recall[pattern] = {
            "best_non_trap_level": LEVELS[best] if best >= 0 else None,
            "reaches_predictive_association": best >= _level("predictive_association"),
        }
    return {
        "top10_precision": good / len(top),
        "top10_true_non_trap": good,
        "top10_n": len(top),
        "trap_promoted": promoted,
        "trap_at_shadow_or_high": shadow,
        "traps_appeared_as_candidate": appeared,
        "recall_frozen_set": recall,
        "recall_frozen_set_all_reached": all(
            v["reaches_predictive_association"] for v in recall.values()
        ),
    }


def main() -> None:
    root = Path(sys.argv[1])
    runs = {name: root / name for name in ("run1", "run2")}
    cands = {n: _load(p / "candidates.json") for n, p in runs.items()}
    mets = {n: _load(p / "discovery_metrics.json") for n, p in runs.items()}

    def body(doc: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in doc.items() if k != "run_id"}

    identical = body(cands["run1"]) == body(cands["run2"])
    per_run = {n: measure(p) for n, p in runs.items()}
    draws = 1 if identical else 2
    independence: dict[str, Any] = {
        "seeds": {n: m["random_seed"] for n, m in mets.items()},
        "seed_labels_differ": mets["run1"]["random_seed"] != mets["run2"]["random_seed"],
        "candidates_json_identical_except_run_id": identical,
        "evaluated_hypotheses": {n: m["evaluated_hypotheses"] for n, m in mets.items()},
        "effective_independent_draws": draws,
    }
    d1_meas = all(m["top10_precision"] >= PRECISION_THRESHOLD for m in per_run.values())
    d3_meas = all(m["recall_frozen_set_all_reached"] for m in per_run.values())
    partA = not any(m["trap_promoted"] or m["trap_at_shadow_or_high"] for m in per_run.values())
    appeared = set(PRIOR_ACTIVE_TRAPS)  # this task's runs add none unless traps appeared
    for m in per_run.values():
        appeared |= set(m["traps_appeared_as_candidate"])
    partB = len(appeared)
    enough = draws >= 2
    overlay = {
        "D1_precision": {
            "measurement_meets_threshold_both_runs": d1_meas,
            "verdict": "PASS" if d1_meas and enough else "FAIL",
        },
        "D2_safety": {
            "partA_no_promotion": partA,
            "partB_cumulative_count": f"{partB}/5",
            "verdict": "PASS" if partA and partB == 5 else "FAIL",
        },
        "D3_recall": {
            "measurement_2_of_2_both_runs": d3_meas,
            "verdict": "PASS" if d3_meas and enough else "FAIL",
        },
        "D4_economic": {"verdict": "UNKNOWN"},
        "D5_independent_runs": {
            "verdict": "FAIL",
            "reason": "requires >=2 qualifying runs each clearing D1-D4; "
            "D2 and D4 are not clearing, and effective draws="
            f"{draws}",
        },
    }
    print(
        json.dumps(
            {"per_run": per_run, "independence": independence, "overlay": overlay},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
