"""TASK-108: rescore archived TASK-028 evaluation outputs under the corrected trap classification.

Read-only over every archived input: nothing under `artifacts/` or the TASK-103 evidence directory
is opened for writing. For each archived `evaluation.json`, the archived per-candidate lenient
recall match (`matched_patterns`, unchanged by `TASK-108`), evidence level, readiness and reported
exposure are kept as recorded; only the trap-vs-pattern classification is recomputed with
`evaluate_benchmark._genuine_trap_matches` from the candidate's conditions and the ground truth's
pattern rules. The derived metrics that read that classification (Top-K precision, economic-weighted
recall, trap appeared/promoted) are then recomputed with the evaluator's own constants, and the
original and rescored values are written side by side. Nothing original is replaced.

Usage:
    uv run python scripts/rescore_task108_trap_classification.py \
        --artifacts-root <checkout containing artifacts/> \
        --out docs/benchmark/task-108-rescore-comparison.json
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from evaluate_benchmark import (  # noqa: E402
    DEFAULT_GROUND_TRUTH_PATH,
    PROMOTED_READINESS,
    TOP_K,
    VALIDATED_LEVELS,
    _genuine_trap_matches,
    _trap_apparent_conditions,
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _metrics(
    scores: list[dict[str, Any]],
    traps: dict[str, tuple[str, str, object]],
    patterns_by_id: dict[str, dict[str, Any]],
    scoreable: list[str],
) -> dict[str, Any]:
    ranked = sorted(scores, key=lambda s: (-s["economic_exposure_reported"], s["candidate_id"]))
    top_k = ranked[:TOP_K]
    tp = sum(1 for s in top_k if s["is_true_pattern"])
    recovered = {
        pid
        for s in scores
        if s["evidence_level"] in VALIDATED_LEVELS and not s["is_trap"]
        for pid in s["matched_patterns"]
        if pid in scoreable
    }
    total = sum(patterns_by_id[p]["true_effect"]["realized_economic_impact"] for p in scoreable)
    rec = sum(patterns_by_id[p]["true_effect"]["realized_economic_impact"] for p in recovered)
    appeared = {t: any(t in s["matched_traps"] for s in scores) for t in traps}
    promoted = {
        t: any(
            t in s["matched_traps"] and s["policy_readiness"] in PROMOTED_READINESS for s in scores
        )
        for t in traps
    }
    return {
        "top_k_true_pattern_count": tp,
        "top_k_precision": tp / len(top_k) if top_k else 0.0,
        "recovered_scoreable_patterns": sorted(recovered),
        "economic_weighted_recall": rec / total if total else 0.0,
        "trap_appeared_as_candidate": appeared,
        "trap_promoted": promoted,
        "any_trap_promoted": any(promoted.values()),
        "n_true_pattern": sum(1 for s in scores if s["is_true_pattern"]),
        "n_trap": sum(1 for s in scores if s["is_trap"]),
        "n_noise": sum(1 for s in scores if s["is_noise"]),
    }


def rescore(evaluation_path: Path, candidates_path: Path, root: Path) -> dict[str, Any]:
    evaluation = _load(evaluation_path)
    gt_rel = evaluation["inputs"].get("ground_truth")
    gt_path = root / gt_rel if gt_rel else DEFAULT_GROUND_TRUTH_PATH
    ground_truth = _load(gt_path)
    gt_sha = hashlib.sha256(gt_path.read_bytes()).hexdigest()
    recorded_sha = evaluation["inputs"].get("ground_truth_sha256")
    patterns_by_id = {p["id"]: p for p in ground_truth["patterns"]}
    traps = _trap_apparent_conditions(ground_truth)
    scoreable = list(evaluation["methodology"]["scoreable_pattern_ids"])
    conditions_by_id = {
        c["candidate_id"]: c["conditions"] for c in _load(candidates_path)["candidates"]
    }

    original = evaluation["candidate_scores"]
    rescored: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for old in original:
        new_traps = _genuine_trap_matches(
            conditions_by_id[old["candidate_id"]], old["matched_patterns"], traps, patterns_by_id
        )
        new = dict(old)
        new["matched_traps"] = new_traps
        new["is_true_pattern"] = bool(old["matched_patterns"]) and not new_traps
        new["is_trap"] = bool(new_traps)
        new["is_noise"] = not old["matched_patterns"] and not new_traps
        rescored.append(new)
        if new["matched_traps"] != old["matched_traps"]:
            changes.append(
                {
                    "candidate_id": old["candidate_id"],
                    "pattern_definition": old["pattern_definition"],
                    "evidence_level": old["evidence_level"],
                    "policy_readiness": old["policy_readiness"],
                    "matched_patterns": old["matched_patterns"],
                    "original": {
                        "matched_traps": old["matched_traps"],
                        "is_true_pattern": old["is_true_pattern"],
                        "is_trap": old["is_trap"],
                        "is_noise": old["is_noise"],
                    },
                    "rescored": {
                        "matched_traps": new["matched_traps"],
                        "is_true_pattern": new["is_true_pattern"],
                        "is_trap": new["is_trap"],
                        "is_noise": new["is_noise"],
                    },
                }
            )
    original_metrics = _metrics(original, traps, patterns_by_id, scoreable)
    rescored_metrics = _metrics(rescored, traps, patterns_by_id, scoreable)
    recorded = evaluation["metrics"]
    consistent = (
        recorded["top_k_precision"]["value"] == original_metrics["top_k_precision"]
        and recorded["economic_weighted_recall"]["value"]
        == original_metrics["economic_weighted_recall"]
        and recorded["confounder_trap_rejection"]["trap_promoted"]
        == original_metrics["trap_promoted"]
        and recorded["confounder_trap_rejection"]["trap_appeared_as_candidate"]
        == original_metrics["trap_appeared_as_candidate"]
    )
    return {
        "evaluation": str(evaluation_path.relative_to(root)),
        "candidates_file": str(candidates_path),
        "ground_truth": gt_rel or "synthetic_data/evaluation/hidden_ground_truth.json (default)",
        "ground_truth_sha256_matches_recorded": (recorded_sha == gt_sha) if recorded_sha else None,
        "recomputed_original_metrics_equal_archived_metrics": consistent,
        "original_metrics": original_metrics,
        "rescored_metrics": rescored_metrics,
        "reading_changed": bool(changes),
        "any_trap_promoted_changed": original_metrics["any_trap_promoted"]
        != rescored_metrics["any_trap_promoted"],
        "trap_promoted_map_changed": original_metrics["trap_promoted"]
        != rescored_metrics["trap_promoted"],
        "changed_candidates": changes,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    root: Path = args.artifacts_root.resolve()
    jobs: list[tuple[Path, Path]] = []
    for path in sorted((root / "artifacts/evaluation").glob("*.json")):
        source = _load(path)["inputs"]["candidates_source"]
        jobs.append((path, root / source))
    for run in ("run1", "run2"):
        base = REPOSITORY / "docs/benchmark/task-103-evidence" / run
        jobs.append((base / "evaluation.json", base / "candidates.json"))
    results: list[dict[str, Any]] = []
    for evaluation_path, candidates_path in jobs:
        display_root = REPOSITORY if evaluation_path.is_relative_to(REPOSITORY) else root
        results.append(rescore(evaluation_path, candidates_path, display_root))
    payload = {
        "task": "TASK-108",
        "note": (
            "Original values are the archived evaluation outputs, unchanged; rescored values apply "
            "only the corrected trap-vs-pattern classification (see "
            "docs/benchmark/task-108-scorer-trap-classification-spec.md). The lenient 0.5 recall "
            "match is the archived matched_patterns, not recomputed."
        ),
        "runs": results,
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for r in results:
        print(
            r["evaluation"],
            "changed" if r["reading_changed"] else "same",
            "consistent"
            if r["recomputed_original_metrics_equal_archived_metrics"]
            else "INCONSISTENT",
        )


if __name__ == "__main__":
    main()
