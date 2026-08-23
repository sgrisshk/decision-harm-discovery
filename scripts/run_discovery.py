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
IDENTITY_FRACTION_FIELD = "max_feature_identity_fraction"
DISABLED_IDENTITY_FRACTION = 1.0


def _signed_identity_fraction(contract: dict[str, Any]) -> float:
    """Read `max_feature_identity_fraction` out of the signed acceptance contract, fail-closed.

    Absent -> `1.0`, the engine's own disabled default, so an omitted field can only ever mean
    "cap disabled" and never some other value applied silently. Present but not a real number in
    `[0.0, 1.0]` -> `ValueError`: a `bool` (an `int` in Python), a numeric string, `NaN`, `inf`,
    or an out-of-range value all refuse to run rather than being coerced into something usable.

    This parameter is the *only* difference between `TASK-068`'s two preregistered runs
    (`ADR-061`), so a wrong value here yields a candidate set that looks like a legitimate result
    but answers a different question — the `ADR-039` failure mode, except mistaken for the answer
    instead of caught by diff. Refusing to run is always the correct outcome.

    Deliberately duplicated from `tools.blind_agent.core.signed_identity_fraction`, exactly as
    `OUTPUT_SCHEMA_VERSION` above is duplicated from `tools/blind_agent/models.py`: this script
    executes inside the isolated blind workspace, which contains only `blind/allowlist.yaml`'s
    allowlisted files and therefore cannot import that module.
    `tests/blind_agent/test_run_discovery_signed_config.py` pins the two to identical behavior.
    """
    if IDENTITY_FRACTION_FIELD not in contract:
        return DISABLED_IDENTITY_FRACTION
    value: object = contract[IDENTITY_FRACTION_FIELD]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"signed {IDENTITY_FRACTION_FIELD} must be a number")
    fraction = float(value)
    # Also rejects NaN, which compares false against every bound.
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"signed {IDENTITY_FRACTION_FIELD} must be in [0.0, 1.0]")
    return fraction


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
    signed_dataset_root = Path(str(contract["analytical_dataset_root"]))
    if signed_dataset_root.is_absolute() or ".." in signed_dataset_root.parts:
        raise ValueError("signed analytical dataset root is unsafe")
    if args.dataset is not None and args.dataset != signed_dataset_root:
        raise ValueError("dataset argument does not match signed analytical dataset root")
    dataset = signed_dataset_root
    outcome_metadata = cast(dict[str, Any], contract["primary_outcome_metadata"])
    outcome = SignedOutcome(
        outcome_id=str(outcome_metadata["outcome_id"]),
        column=str(outcome_metadata["column"]),
        unit=str(outcome_metadata["unit"]),
        higher_is_worse=bool(outcome_metadata["higher_is_worse"]),
    )
    features = pl.read_csv(dataset / "features.csv", try_parse_dates=False)
    outcomes = pl.read_csv(dataset / "outcomes.csv", try_parse_dates=False)
    metadata = pl.read_csv(dataset / "metadata.csv", try_parse_dates=False)
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
    max_feature_identity_fraction = _signed_identity_fraction(contract)
    config = DiscoveryConfig(
        seed=int(manifest["random_seed"]),
        max_feature_identity_fraction=max_feature_identity_fraction,
    )
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
        # Declared from the value actually handed to `DiscoveryConfig` above, never re-read from
        # the contract, so this records what the run did rather than what it was asked to do.
        # `blind_agent.core._validated_freeze` refuses to freeze output where the two disagree.
        IDENTITY_FRACTION_FIELD: max_feature_identity_fraction,
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
