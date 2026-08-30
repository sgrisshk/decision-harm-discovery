"""CODE_REVIEWER Check 4 (ADR-086): independent branch-1 verification via an ALTERNATE ablation
ORDER, to test whether beam_rules_per_structure=2's "amplifier, +33.8pp" characterization is an
artifact of the specific A->B->C->D bisection path TASK-084's own script used, or a robust,
order-insensitive effect.

TASK-084's own path added beam_rules_per_structure LAST (C -> D, after TASK-060 diversity was
already on). This script instead adds beam_rules_per_structure=2 FIRST, directly to the TASK-058-
era config A (diversity mechanism still OFF) -- config E below -- and separately adds it to the
v1.1.0-dataset/no-diversity config B -- to see whether the isolated beam_rules_per_structure effect
size is comparable when measured on a different baseline, not the same one path TASK-084 used.

Uses the real, unmodified discover_candidates/validate_candidates.py/evaluate_benchmark.py exactly
as scripts/diagnose_task084_branch1_engine_regression.py does -- no reimplementation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    DISCOVERY_METHOD_VERSION,
    DiscoveryConfig,
    discover_candidates,
)
from policy_analytics.outcomes import outcome_definition_from_manifest  # noqa: E402

SCRATCH_ROOT = Path("<scratch>"
                     "f82f6987-cd7b-429c-b576-4ad2d17b9dba/scratchpad/task084_check4")
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
SEED = 1729
OUTPUT_SCHEMA_VERSION = "1.1.0"
DATASET_V100 = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
DATASET_V110 = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"

CONFIGS: dict[str, dict[str, Any]] = {
    "E_v100_beam_only": {
        "dataset_root": DATASET_V100,
        "overrides": {
            "population_score_exponent": 0.5,
            "diversity_discount_weight": 0.0,
            "min_diversity_relevance_ratio": 0.0,
            "stability_credit_weight": 0.0,
            "beam_rules_per_structure": 2,  # added directly to A, diversity still OFF
        },
        "label": "config A + beam_rules_per_structure=2 ONLY (diversity still off, v1.0.0 data) "
                  "-- isolates beam axis on a DIFFERENT baseline than TASK-084's own path",
    },
    "F_v110_beam_only": {
        "dataset_root": DATASET_V110,
        "overrides": {
            "population_score_exponent": 0.5,
            "diversity_discount_weight": 0.0,
            "min_diversity_relevance_ratio": 0.0,
            "stability_credit_weight": 0.0,
            "beam_rules_per_structure": 2,
        },
        "label": "config B + beam_rules_per_structure=2 ONLY (diversity still off, v1.1.0 data)",
    },
}


def _load_frame_and_features(
    dataset_root: Path,
) -> tuple[pl.DataFrame, tuple[str, ...], dict[str, Any]]:
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    features = pl.read_csv(dataset_root / "features.csv", try_parse_dates=False)
    outcomes = pl.read_csv(dataset_root / "outcomes.csv", try_parse_dates=False)
    metadata = pl.read_csv(dataset_root / "metadata.csv", try_parse_dates=False)
    frame = pl.concat([features, outcomes, metadata.select("split_label")], how="horizontal")
    timing = manifest["feature_timing"]
    feature_columns = tuple(
        c for c in features.columns if timing.get(c, {}).get("classification") == "DECISION_TIME"
    )
    feature_columns = tuple(n for n in feature_columns if n not in {"booking_date", "travel_date"})
    return frame, feature_columns, manifest


def _condition_description(conditions: list[dict[str, object]]) -> str:
    rendered = " and ".join(f"{c['feature']} {c['operator']} {c['value']}" for c in conditions)
    return f"Observed development-split association for {rendered}."


def _run_checked(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=REPOSITORY, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {' '.join(cmd)}")


def _run_one(label: str, spec: dict[str, Any]) -> dict[str, Any]:
    dataset_root: Path = spec["dataset_root"]
    overrides: dict[str, Any] = spec["overrides"]
    run_dir = SCRATCH_ROOT / label
    run_dir.mkdir(parents=True, exist_ok=True)

    frame, feature_columns, manifest = _load_frame_and_features(dataset_root)
    outcome, outcome_contract_version = outcome_definition_from_manifest(manifest, dataset_root)
    config = DiscoveryConfig(seed=SEED, **overrides)
    result = discover_candidates(frame, feature_columns, outcome, config)
    raw_candidates = cast(list[dict[str, Any]], result["candidates"])

    candidates = []
    for raw in raw_candidates:
        development = cast(dict[str, Any], raw["development"])
        conditions = cast(list[dict[str, object]], raw["conditions"])
        candidates.append({
            "candidate_id": raw["candidate_id"],
            "conditions": conditions,
            "outcome": outcome.outcome_id,
            "sample_size": development["n_exposed"],
            "support": development["support"],
            "raw_effect": development["raw_difference"],
            "economic_exposure": development["historical_exposure"],
            "discovery_method": DISCOVERY_METHOD_VERSION,
            "description": _condition_description(conditions),
            "warnings": raw["warnings"],
        })

    candidate_document = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_id": f"task084-check4-{label}",
        "status": "PERSISTED" if len(candidates) >= 10 else "INSUFFICIENT_CANDIDATES",
        "dataset_version": manifest["dataset_version"],
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "outcome_contract_version": outcome_contract_version,
        "discovery_method_version": DISCOVERY_METHOD_VERSION,
        "insufficiency_reason": None if len(candidates) >= 10 else "insufficient",
        "candidates": candidates,
    }
    metrics_document = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_id": f"task084-check4-{label}",
        "evaluated_hypotheses": result["search"]["evaluated_hypotheses"],
        "random_seed": SEED,
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "discovery_method_version": DISCOVERY_METHOD_VERSION,
    }
    candidates_path = run_dir / "candidates.json"
    metrics_path = run_dir / "discovery_metrics.json"
    candidates_path.write_text(
        json.dumps(candidate_document, indent=2, sort_keys=True), encoding="utf-8"
    )
    metrics_path.write_text(
        json.dumps(metrics_document, indent=2, sort_keys=True), encoding="utf-8"
    )

    validation_output = run_dir / "validation-report.json"
    _run_checked([
        sys.executable, str(REPOSITORY / "scripts/validate_candidates.py"),
        "--candidates", str(candidates_path), "--metrics", str(metrics_path),
        "--dataset-root", str(dataset_root), "--output", str(validation_output),
        "--analysis-run-id", f"task084-check4-{label}",
        "--no-blind-compliant", "--no-founder-block-lifted",
    ])
    evaluation_output = run_dir / "evaluation-report.json"
    _run_checked([
        sys.executable, str(REPOSITORY / "scripts/evaluate_benchmark.py"),
        "--validation-report", str(validation_output), "--output", str(evaluation_output),
        "--dataset-root", str(dataset_root), "--ground-truth", str(GROUND_TRUTH_PATH),
    ])
    evaluation = json.loads(evaluation_output.read_text(encoding="utf-8"))
    metrics = evaluation["metrics"]
    return {
        "label": label,
        "description": spec["label"],
        "median_impact_error": metrics["economic_impact_estimation_error"]["median_relative_error"],
        "median_attribution_narrowed_error": metrics[
            "economic_impact_estimation_error_attribution_narrowed_diagnostic"]["median_relative_error"],
        "top10_precision": metrics["top_k_precision"]["value"],
    }


def main() -> None:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    results = []
    for label, spec in CONFIGS.items():
        print(f"=== running {label} ===", file=sys.stderr)
        r = _run_one(label, spec)
        print(json.dumps(r, indent=2))
        results.append(r)
    out_path = REPOSITORY / "docs/benchmark/task-084-review-check4-alt-order-raw.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
