"""TASK-084 branch 1 diagnostic: engine-version/config regression ablation.

Diagnosis only (`ADR-085`/`TASK-084`). Does not touch `discovery.engine`'s shipped code, `G06`,
`G16`, or any existing default. Every configuration below is a `DiscoveryConfig` *parameter
override*, passed to the real, unmodified `discover_candidates` — never a code edit. Where a
version's behavior cannot be reproduced by a documented override on the current engine (there is
none such here — every `TASK-058`/`TASK-060`/`TASK-064`/`TASK-068` change is a config field on the
current, unmodified `engine.py`, each with a docstring-stated "reproduces vX.Y.Z exactly" value),
this would be disclosed rather than faked.

Runs the real, unmodified `discover_candidates` -> `scripts/validate_candidates.py`'s
`run_validation` -> `scripts/evaluate_benchmark.py`'s six-metric scoring, once per named
configuration, entirely to scratch paths (never touches any frozen `artifacts/` result). This is a
diagnostic reproduction, not a new official/blind-protocol run: no isolated blind workspace, no
deterministic-agent harness, no signed receipt — so every produced validation report is honestly
marked `--no-blind-compliant --no-founder-block-lifted`. Ground truth
(`synthetic_data/evaluation/hidden_ground_truth.json`) is opened only at the final evaluation step,
exactly as `scripts/evaluate_benchmark.py` already legitimately does for every prior benchmark
report in this chain (`TASK-028`/`TASK-059`/`ADR-084`) — diagnostic use, not production-facing.

Four configurations, bisecting one axis at a time between `TASK-058`'s own `discovery-engine-v0.2.0`
(`ADR-023`) and the current `discovery-engine-v0.6.0` default:

  A_v020_v100  -- TASK-058-era engine config (population_score_exponent=0.5,
                  diversity_discount_weight=0.0 [pre-TASK-060, no diversity mechanism existed],
                  beam_rules_per_structure=0 [pre-TASK-064, the field did not exist]) on the
                  TASK-058-era analytical dataset, travel-bookings-analytical-v1.0.0.
  B_v020_v110  -- identical engine config to A, but on the CURRENT analytical dataset
                  (travel-bookings-analytical-v1.1.0, adds travel_month) -- isolates the
                  dataset-version axis alone.
  C_v041_v110  -- adds TASK-060's diversity-selection mechanism at its final v0.4.1 settings
                  (diversity_discount_weight=0.5, min_diversity_relevance_ratio=0.5,
                  relevance_floor_percentile=0.75, stability_credit_weight=0.5 -- all current
                  defaults), beam_rules_per_structure still 0 (pre-TASK-064) -- isolates the
                  TASK-060 diversity-selection axis alone, against B.
  D_v060_v110  -- literal current DiscoveryConfig() defaults (beam_rules_per_structure=2,
                  max_feature_identity_fraction=1.0 -- which the field's own docstring states
                  never binds, so this is behaviorally identical to v0.5.0) -- isolates the
                  beam_rules_per_structure axis alone, against C. This is also the actual official
                  current configuration, included as a reproduction sanity check against
                  TASK-083's frozen numbers.

Usage: uv run python scripts/diagnose_task084_branch1_engine_regression.py
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

SCRATCH_ROOT = Path(
    "<scratch>"
    "f82f6987-cd7b-429c-b576-4ad2d17b9dba/scratchpad/task084/branch1"
)
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
SEED = 1729
OUTPUT_SCHEMA_VERSION = "1.1.0"

DATASET_V100 = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
DATASET_V110 = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"

# Every override below is a documented DiscoveryConfig field on the current, real, unmodified
# engine.py -- see that module's own docstrings for the "reproduces vX.Y.Z exactly" claims cited
# in this script's own module docstring.
CONFIGS: dict[str, dict[str, Any]] = {
    "A_v020_v100": {
        "dataset_root": DATASET_V100,
        "overrides": {
            "population_score_exponent": 0.5,
            # Every TASK-060 diversity-selection field zeroed out -- diversity_discount_weight=0
            # alone is NOT sufficient: min_diversity_relevance_ratio's floor and
            # stability_credit_weight's effective-score blend both apply independently of the
            # discount weight (see _greedy_diverse_select/discover_candidates), and neither
            # existed before TASK-060. All three must be off together to reproduce pure
            # score-order top-K selection, "as v0.1.0/v0.2.0 did" (engine.py's own docstring).
            "diversity_discount_weight": 0.0,
            "min_diversity_relevance_ratio": 0.0,
            "stability_credit_weight": 0.0,
            "beam_rules_per_structure": 0,
        },
        "label": "TASK-058-era config (discovery-engine-v0.2.0 equivalent) on v1.0.0 dataset",
    },
    "B_v020_v110": {
        "dataset_root": DATASET_V110,
        "overrides": {
            "population_score_exponent": 0.5,
            "diversity_discount_weight": 0.0,
            "min_diversity_relevance_ratio": 0.0,
            "stability_credit_weight": 0.0,
            "beam_rules_per_structure": 0,
        },
        "label": "TASK-058-era config (v0.2.0 equivalent) on CURRENT v1.1.0 dataset "
        "(isolates dataset-version axis vs A)",
    },
    "C_v041_v110": {
        "dataset_root": DATASET_V110,
        "overrides": {
            "population_score_exponent": 0.5,
            "diversity_discount_weight": 0.5,
            "min_diversity_relevance_ratio": 0.5,
            "relevance_floor_percentile": 0.75,
            "stability_credit_weight": 0.5,
            "beam_rules_per_structure": 0,
        },
        "label": "v0.4.1-equivalent config (TASK-060 diversity mechanism at final settings, "
        "still pre-TASK-064 beam) on v1.1.0 dataset (isolates TASK-060 diversity axis vs B)",
    },
    "D_v060_v110": {
        "dataset_root": DATASET_V110,
        "overrides": {},  # literal current DiscoveryConfig() defaults
        "label": "current discovery-engine-v0.6.0 default config (beam_rules_per_structure=2) "
        "on v1.1.0 dataset (isolates beam_rules_per_structure axis vs C; also the actual "
        "official configuration -- reproduction sanity check against TASK-083)",
    },
}


def _load_frame_and_features(dataset_root: Path) -> tuple[pl.DataFrame, tuple[str, ...], dict[str, Any]]:
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    features = pl.read_csv(dataset_root / "features.csv", try_parse_dates=False)
    outcomes = pl.read_csv(dataset_root / "outcomes.csv", try_parse_dates=False)
    metadata = pl.read_csv(dataset_root / "metadata.csv", try_parse_dates=False)
    if not (features.height == outcomes.height == metadata.height):
        raise ValueError("analytical partitions are not row-aligned")
    frame = pl.concat([features, outcomes, metadata.select("split_label")], how="horizontal")
    timing = manifest["feature_timing"]
    feature_columns = tuple(
        column
        for column in features.columns
        if timing.get(column, {}).get("classification") == "DECISION_TIME"
    )
    feature_columns = tuple(
        name for name in feature_columns if name not in {"booking_date", "travel_date"}
    )
    return frame, feature_columns, manifest


def _condition_description(conditions: list[dict[str, object]]) -> str:
    rendered = " and ".join(
        f"{c['feature']} {c['operator']} {c['value']}" for c in conditions
    )
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

    candidates: list[dict[str, Any]] = []
    for raw in raw_candidates:
        development = cast(dict[str, Any], raw["development"])
        conditions = cast(list[dict[str, object]], raw["conditions"])
        candidates.append(
            {
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
            }
        )

    candidate_document = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_id": f"task084-branch1-{label}",
        "status": "PERSISTED" if len(candidates) >= 10 else "INSUFFICIENT_CANDIDATES",
        "dataset_version": manifest["dataset_version"],
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "outcome_contract_version": outcome_contract_version,
        "discovery_method_version": DISCOVERY_METHOD_VERSION,
        "insufficiency_reason": (
            None
            if len(candidates) >= 10
            else "Diagnostic search returned fewer than 10 candidates."
        ),
        "candidates": candidates,
    }
    metrics_document = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_id": f"task084-branch1-{label}",
        "evaluated_hypotheses": result["search"]["evaluated_hypotheses"],
        "random_seed": SEED,
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "discovery_method_version": DISCOVERY_METHOD_VERSION,
    }
    candidates_path = run_dir / "candidates.json"
    metrics_path = run_dir / "discovery_metrics.json"
    candidates_path.write_text(json.dumps(candidate_document, indent=2, sort_keys=True), encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics_document, indent=2, sort_keys=True), encoding="utf-8")

    if candidate_document["status"] != "PERSISTED":
        return {
            "label": label,
            "description": spec["label"],
            "config_overrides": overrides,
            "dataset_root": str(dataset_root.relative_to(REPOSITORY)),
            "status": "INSUFFICIENT_CANDIDATES",
            "evaluated_hypotheses": result["search"]["evaluated_hypotheses"],
            "n_candidates": len(candidates),
        }

    validation_output = run_dir / "validation-report.json"
    validate_cmd = [
        sys.executable,
        str(REPOSITORY / "scripts/validate_candidates.py"),
        "--candidates",
        str(candidates_path),
        "--metrics",
        str(metrics_path),
        "--dataset-root",
        str(dataset_root),
        "--output",
        str(validation_output),
        "--analysis-run-id",
        f"task084-branch1-{label}",
        "--no-blind-compliant",
        "--no-founder-block-lifted",
    ]
    _run_checked(validate_cmd)

    evaluation_output = run_dir / "evaluation-report.json"
    evaluate_cmd = [
        sys.executable,
        str(REPOSITORY / "scripts/evaluate_benchmark.py"),
        "--validation-report",
        str(validation_output),
        "--output",
        str(evaluation_output),
        "--dataset-root",
        str(dataset_root),
        "--ground-truth",
        str(GROUND_TRUTH_PATH),
    ]
    _run_checked(evaluate_cmd)

    evaluation = json.loads(evaluation_output.read_text(encoding="utf-8"))
    metrics = evaluation["metrics"]

    return {
        "label": label,
        "description": spec["label"],
        "config_overrides": overrides,
        "dataset_root": str(dataset_root.relative_to(REPOSITORY)),
        "status": "SCORED",
        "evaluated_hypotheses": result["search"]["evaluated_hypotheses"],
        "n_candidates": len(candidates),
        "top10_precision": metrics["top_k_precision"]["value"],
        "economic_weighted_recall": metrics["economic_weighted_recall"]["value"],
        "any_trap_promoted": metrics["confounder_trap_rejection"]["any_trap_promoted"],
        "direction_accuracy": metrics["effect_direction_accuracy"]["value"],
        "median_impact_error": metrics["economic_impact_estimation_error"]["median_relative_error"],
        "impact_error_range": [
            min(
                d["relative_error"]
                for d in metrics["economic_impact_estimation_error"]["details"]
                if d["relative_error"] is not None
            ),
            max(
                d["relative_error"]
                for d in metrics["economic_impact_estimation_error"]["details"]
                if d["relative_error"] is not None
            ),
        ],
        "median_attribution_narrowed_error": metrics[
            "economic_impact_estimation_error_attribution_narrowed_diagnostic"
        ]["median_relative_error"],
        "impact_error_details": metrics["economic_impact_estimation_error"]["details"],
        "attribution_narrowed_details": metrics[
            "economic_impact_estimation_error_attribution_narrowed_diagnostic"
        ]["details"],
    }


def main() -> None:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    results = []
    for label, spec in CONFIGS.items():
        print(f"=== running {label}: {spec['label']} ===", file=sys.stderr)
        result = _run_one(label, spec)
        print(json.dumps({k: v for k, v in result.items() if k not in ("impact_error_details", "attribution_narrowed_details")}, indent=2), file=sys.stderr)
        results.append(result)

    out_path = REPOSITORY / "docs/benchmark/task-084-branch1-engine-regression-raw.json"
    out_path.write_text(json.dumps(results, indent=2, sort_keys=False), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
