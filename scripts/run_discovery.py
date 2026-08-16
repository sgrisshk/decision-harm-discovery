"""Run TASK-015 discovery against a versioned analytical dataset."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/analytics/src"))

from policy_analytics.discovery.engine import (
    DISCOVERY_METHOD_VERSION,
    DiscoveryConfig,
    discover_candidates,
)

OUTPUT_SCHEMA_VERSION = "1.1.0"


@dataclass(frozen=True, slots=True)
class SignedOutcome:
    outcome_id: str
    column: str
    unit: str
    higher_is_worse: bool

    @property
    def harm_multiplier(self) -> int:
        return 1 if self.higher_is_worse else -1


def _condition_description(conditions: list[dict[str, object]]) -> str:
    rendered = " and ".join(
        f"{condition['feature']} {condition['operator']} {condition['value']}"
        for condition in conditions
    )
    return f"Observed development-split association for {rendered}."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("synthetic_data/analytical/travel-bookings-analytical-v1.0.0"),
    )
    parser.add_argument("--manifest", type=Path, default=Path("BLIND_MANIFEST.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    manifest = cast(dict[str, Any], json.loads(args.manifest.read_text(encoding="utf-8")))
    contract = cast(dict[str, Any], manifest.get("acceptance_contract"))
    if not contract:
        raise ValueError("signed blind manifest has no acceptance contract")
    if contract["output_schema_version"] != OUTPUT_SCHEMA_VERSION:
        raise ValueError("unsupported signed output schema version")
    if contract["discovery_method_version"] != DISCOVERY_METHOD_VERSION:
        raise ValueError("signed discovery method does not match implementation")
    outcome_metadata = cast(dict[str, Any], contract["primary_outcome_metadata"])
    outcome = SignedOutcome(
        outcome_id=str(outcome_metadata["outcome_id"]),
        column=str(outcome_metadata["column"]),
        unit=str(outcome_metadata["unit"]),
        higher_is_worse=bool(outcome_metadata["higher_is_worse"]),
    )
    features = pl.read_csv(args.dataset / "features.csv", try_parse_dates=False)
    outcomes = pl.read_csv(args.dataset / "outcomes.csv", try_parse_dates=False)
    metadata = pl.read_csv(args.dataset / "metadata.csv", try_parse_dates=False)
    if not (features.height == outcomes.height == metadata.height):
        raise ValueError("analytical partitions are not row-aligned")
    frame = pl.concat([features, outcomes, metadata.select("split_label")], how="horizontal")
    timing = cast(dict[str, str], contract["feature_timing_classes"])
    feature_columns = tuple(
        column for column in features.columns if timing.get(column) == "DECISION_TIME"
    )
    # Calendar dates are permitted decision-time fields but raw date thresholds are not reusable
    # policy rules, so v0 excludes them from candidate conditions.
    feature_columns = tuple(
        name for name in feature_columns if name not in {"booking_date", "travel_date"}
    )
    config = DiscoveryConfig(seed=int(manifest["random_seed"]))
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
    persisted = len(candidates) >= 10
    candidate_document: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "status": "PERSISTED" if persisted else "INSUFFICIENT_CANDIDATES",
        "blind_bundle_id": manifest["bundle_id"],
        "run_contract_version": contract["run_contract_version"],
        "dataset_version": contract["dataset_version"],
        "dataset_identity_sha256": contract["dataset_identity_sha256"],
        "outcome_contract_version": contract["outcome_contract_version"],
        "discovery_contract_version": contract["discovery_contract_version"],
        "discovery_method_version": contract["discovery_method_version"],
        "search_fit_split": contract["search_fit_split"],
        "diagnostic_only_splits": contract["diagnostic_only_splits"],
        "selection_used_only_fit_split": True,
        "input_provenance_hashes": manifest["allowed_files"],
        "feature_timing_classes": contract["feature_timing_classes"],
        "insufficiency_reason": (
            None if persisted else "Deterministic search returned fewer than 10 candidates."
        ),
        "candidates": candidates,
    }
    metrics_document = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "evaluated_hypotheses": result["search"]["evaluated_hypotheses"],
        "random_seed": manifest["random_seed"],
        "run_contract_version": contract["run_contract_version"],
        "dataset_identity_sha256": contract["dataset_identity_sha256"],
        "discovery_method_version": contract["discovery_method_version"],
        "search_fit_split": contract["search_fit_split"],
        "selection_used_only_fit_split": True,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "candidates.json").write_text(
        json.dumps(candidate_document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "discovery_metrics.json").write_text(
        json.dumps(metrics_document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "run_report.md").write_text(
        "# Deterministic blind discovery run\n\n"
        f"Generated {len(candidates)} candidate associations from "
        f"{result['search']['evaluated_hypotheses']} evaluated hypotheses.\n\n"
        "Candidate discovery only; Statistics validation is required.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
