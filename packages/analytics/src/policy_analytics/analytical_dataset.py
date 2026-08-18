"""Build versioned, leakage-safe analytical dataset partitions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import polars as pl

from policy_analytics.cleaning.canonical_schema import (
    CANONICAL_SCHEMA_VERSION,
)
from policy_analytics.outcomes.contract import (
    DATASET_VERSION as OUTCOME_CONTRACT_DATASET_SCOPE,
)
from policy_analytics.outcomes.contract import (
    DEFAULT_COMPARISON_RULE,
    ELIGIBLE_COHORT_RULE,
    OUTCOME_CONTRACT_VERSION,
    OUTCOME_DEFINITIONS,
    PRIMARY_OUTCOME_ID,
)

DATASET_VERSION = "travel-bookings-analytical-v1.0.0"
#: TASK-010 now formally defines this schema (`policy_analytics.cleaning.canonical_schema`) —
#: re-exported here unchanged (same version string, same target shape) so existing importers of
#: `analytical_dataset.CANONICAL_SCHEMA_VERSION` are unaffected.
ALLOWED_CLASSIFICATIONS = {
    "DECISION_TIME",
    "POST_DECISION",
    "OUTCOME",
    "IDENTIFIER",
    "METADATA",
    "UNKNOWN",
}


@dataclass(frozen=True)
class AnalyticalDatasetConfig:
    dataset_version: str = DATASET_VERSION
    canonical_schema_version: str = CANONICAL_SCHEMA_VERSION
    decision_timestamp_column: str = "booking_date"
    clustering_key: str = "customer_id"
    development_end: str = "2024-12-31"
    validation_end: str = "2025-06-30"
    future_holdout_end: str = "2025-12-31"
    transformation_version: str = "1.0.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_timing(path: Path) -> dict[str, dict[str, Any]]:
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    raw_columns: object = payload.get("columns")
    if not isinstance(raw_columns, list):
        raise ValueError("feature timing manifest must contain a columns list")
    result: dict[str, dict[str, Any]] = {}
    for raw_item in cast(list[object], raw_columns):
        if not isinstance(raw_item, dict):
            raise ValueError("invalid feature timing entry")
        item = cast(dict[str, Any], raw_item)
        if not isinstance(item.get("name"), str):
            raise ValueError("invalid feature timing entry")
        classification = item.get("classification")
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(f"invalid classification for {item['name']}")
        result[item["name"]] = item
    return result


def _split_expression(config: AnalyticalDatasetConfig) -> pl.Expr:
    booking_date = pl.col(config.decision_timestamp_column).str.to_date()
    return (
        pl.when(booking_date <= pl.lit(config.development_end).str.to_date())
        .then(pl.lit("development"))
        .when(booking_date <= pl.lit(config.validation_end).str.to_date())
        .then(pl.lit("validation"))
        .when(booking_date <= pl.lit(config.future_holdout_end).str.to_date())
        .then(pl.lit("future_holdout"))
        .otherwise(pl.lit("outside_supported_window"))
        .alias("split_label")
    )


def _schema_for(frame: pl.DataFrame) -> list[dict[str, str]]:
    return [{"name": name, "dtype": str(dtype)} for name, dtype in frame.schema.items()]


def _missingness(frame: pl.DataFrame, split_labels: pl.Series) -> dict[str, Any]:
    joined = frame.with_columns(split_labels)
    by_split: dict[str, dict[str, float]] = {}
    for split in ("development", "validation", "future_holdout"):
        subset = joined.filter(  # pyright: ignore[reportUnknownMemberType]
            pl.col("split_label") == split
        ).drop("split_label")
        by_split[split] = {
            column: round(100 * subset[column].null_count() / subset.height, 6)
            for column in subset.columns
        }
    return {
        "unit": "percentage",
        "overall": {
            column: round(100 * frame[column].null_count() / frame.height, 6)
            for column in frame.columns
        },
        "by_split": by_split,
        "exposure_group_status": (
            "DEFERRED: exposure membership is candidate-specific and must be supplied by "
            "ML Discovery without changing candidate conditions after persistence."
        ),
    }


def compute_exposure_group_missingness(
    frame: pl.DataFrame, exposure: pl.Series
) -> dict[str, dict[str, float]]:
    """Compute G07 inputs after an immutable candidate exposure is supplied."""
    if exposure.len() != frame.height or exposure.dtype != pl.Boolean:
        raise ValueError("exposure must be a boolean series aligned one-to-one with the dataset")
    result: dict[str, dict[str, float]] = {}
    for label, flag in (("exposed", True), ("unexposed", False)):
        subset = frame.filter(exposure == flag)  # pyright: ignore[reportUnknownMemberType]
        if subset.is_empty():
            raise ValueError(f"exposure group {label} is empty")
        result[label] = {
            column: round(100 * subset[column].null_count() / subset.height, 6)
            for column in subset.columns
        }
    return result


def build_analytical_dataset(
    source_csv: Path,
    feature_timing_path: Path,
    output_root: Path,
    config: AnalyticalDatasetConfig | None = None,
) -> dict[str, Any]:
    """Partition a canonical benchmark into immutable analytical roles."""
    config = config or AnalyticalDatasetConfig()
    timing = _load_timing(feature_timing_path)
    frame = pl.read_csv(source_csv, try_parse_dates=False, null_values=[""])
    missing_timing = sorted(set(frame.columns) - set(timing))
    unknown_timing_columns = sorted(set(timing) - set(frame.columns))
    if missing_timing or unknown_timing_columns:
        raise ValueError(
            f"schema/timing mismatch: missing={missing_timing}, extra={unknown_timing_columns}"
        )
    if frame["booking_id"].n_unique() != frame.height:
        raise ValueError("booking_id must be unique")
    if frame[config.clustering_key].null_count() or frame[config.clustering_key].n_unique() < 5:
        raise ValueError("clustering key must be complete and contain at least five clusters")

    columns_by_classification = {
        classification: [
            name for name in frame.columns if timing[name]["classification"] == classification
        ]
        for classification in ALLOWED_CLASSIFICATIONS
    }
    if columns_by_classification["UNKNOWN"]:
        raise ValueError("UNKNOWN columns cannot enter an analytical dataset")
    feature_columns = columns_by_classification["DECISION_TIME"]
    outcome_columns = columns_by_classification["OUTCOME"]
    identifier_columns = columns_by_classification["IDENTIFIER"]
    metadata_source_columns = columns_by_classification["METADATA"]
    excluded_columns = columns_by_classification["POST_DECISION"]
    if any(not timing[name]["discovery_feature_allowed"] for name in feature_columns):
        raise ValueError("decision-time feature is not approved for discovery")

    split_labels = frame.select(_split_expression(config)).to_series()
    if "outside_supported_window" in split_labels.to_list():
        raise ValueError("records exist outside the configured temporal split window")
    row_numbers = pl.Series("source_row_number", range(1, frame.height + 1), dtype=pl.Int64)
    partitions = {
        "features": frame.select(feature_columns),
        "outcomes": frame.select(outcome_columns),
        "identifiers": frame.select(identifier_columns),
        "metadata": frame.select(metadata_source_columns)
        .with_columns(row_numbers, split_labels, pl.col("currency").alias("source_currency"))
        .drop("currency"),
    }

    version_root = output_root / config.dataset_version
    version_root.mkdir(parents=True, exist_ok=False)
    artifact_paths: dict[str, Path] = {}
    for role, partition in partitions.items():
        path = version_root / f"{role}.csv"
        partition.write_csv(path)
        artifact_paths[role] = path

    missingness_path = version_root / "missingness.json"
    _write_json(missingness_path, _missingness(frame, split_labels))
    artifact_paths["missingness"] = missingness_path
    source_sha256 = _sha256(source_csv)
    feature_timing_sha256 = _sha256(feature_timing_path)
    partition_hashes = {
        role: _sha256(path) for role, path in artifact_paths.items() if role in partitions
    }
    # dataset_identity_sha256 (below) is deliberately a hash of *content* — source data,
    # feature-timing manifest, transformation config, outcome contract version, and the written
    # partitions — not of this module's own source bytes. An earlier version hashed `Path(__file__)`
    # into this payload as `transformation_implementation_sha256`; that made any edit to this file —
    # including a value-preserving one, e.g. TASK-010's CANONICAL_SCHEMA_VERSION re-export from
    # `policy_analytics.cleaning.canonical_schema` — change dataset identity and trip
    # `scripts/build_synthetic_analytical_dataset.py`'s immutability guard, forcing a
    # dataset_version bump for a change that provably produces byte-identical output. Nothing else
    # in the codebase ever read that sub-field independently (only the aggregate
    # `dataset_identity_sha256` matters to `blind_isolation.py`/`promote_findings.py`/the outcome
    # contract's pinned hash), so it added churn without adding a checked guarantee. Which commit
    # built a given dataset version is what `git log` is for. See ADR-030.
    identity_payload = {
        "dataset_version": config.dataset_version,
        "schema_version": config.canonical_schema_version,
        "source_sha256": source_sha256,
        "feature_timing_sha256": feature_timing_sha256,
        "transformation_config": asdict(config),
        "outcome_contract_version": OUTCOME_CONTRACT_VERSION,
        "partition_sha256": partition_hashes,
    }
    version_identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    feature_manifest = {
        "dataset_version": config.dataset_version,
        "schema_version": config.canonical_schema_version,
        "role": "DECISION_TIME",
        "columns": [
            {
                "name": name,
                "dtype": str(partitions["features"].schema[name]),
                "semantic_meaning": timing[name]["semantic_meaning"],
                "discovery_feature_allowed": True,
                "leakage_risk": timing[name]["leakage_risk"],
            }
            for name in feature_columns
        ],
    }
    feature_manifest_path = version_root / "feature_manifest.json"
    _write_json(feature_manifest_path, feature_manifest)

    contract_definitions = [
        {
            "outcome_id": definition.outcome_id,
            "role": definition.role.value,
            "column": definition.column,
            "unit": definition.unit,
            "higher_is_worse": definition.higher_is_worse,
            "missing_data_policy": definition.missing_data_policy.value,
            "decomposition_of": definition.decomposition_of,
        }
        for definition in OUTCOME_DEFINITIONS
    ]
    outcome_columns_manifest = {
        "dataset_version": config.dataset_version,
        "schema_version": config.canonical_schema_version,
        "role": "OUTCOME",
        "stored_columns": outcome_columns,
        "outcome_contract": {
            "status": "ATTACHED",
            "owner": "STATISTICS",
            "task": "TASK-013",
            "version": OUTCOME_CONTRACT_VERSION,
            "dataset_scope": OUTCOME_CONTRACT_DATASET_SCOPE,
            "available_columns": outcome_columns,
            "primary_outcome_id": PRIMARY_OUTCOME_ID,
            "eligible_cohort_rule": ELIGIBLE_COHORT_RULE,
            "default_comparison_rule": DEFAULT_COMPARISON_RULE,
            "definitions": contract_definitions,
        },
    }
    outcome_manifest_path = version_root / "outcome_columns_manifest.json"
    _write_json(outcome_manifest_path, outcome_columns_manifest)

    excluded_columns_manifest = {
        "dataset_version": config.dataset_version,
        "schema_version": config.canonical_schema_version,
        "excluded_from_feature_matrix": [
            {
                "name": name,
                "classification": timing[name]["classification"],
                "reason": (
                    "Observed after the booking decision; prohibited by anti-leakage boundary."
                ),
            }
            for name in excluded_columns
        ]
        + [
            {
                "name": name,
                "classification": timing[name]["classification"],
                "reason": f"Physically separated into the {partition} partition.",
            }
            for partition, names in (
                ("outcomes", outcome_columns),
                ("identifiers", identifier_columns),
                ("metadata", metadata_source_columns),
            )
            for name in names
        ],
        "unknown_columns": columns_by_classification["UNKNOWN"],
    }
    excluded_manifest_path = version_root / "excluded_columns_manifest.json"
    _write_json(excluded_manifest_path, excluded_columns_manifest)

    reproducibility_command = "make analytical-dataset"
    version_metadata = {
        "dataset_version": config.dataset_version,
        "schema_version": config.canonical_schema_version,
        "dataset_identity_sha256": version_identity,
        "transformation_config": asdict(config),
        "source_dataset_reference": {
            "path": str(source_csv),
            "sha256": source_sha256,
            "feature_timing_path": str(feature_timing_path),
            "feature_timing_sha256": feature_timing_sha256,
        },
        "identity_payload": identity_payload,
        "reproducibility_command": reproducibility_command,
    }
    version_metadata_path = version_root / "version_metadata.json"
    _write_json(version_metadata_path, version_metadata)

    supporting_paths = {
        "feature_manifest": feature_manifest_path,
        "outcome_columns_manifest": outcome_manifest_path,
        "excluded_columns_manifest": excluded_manifest_path,
        "version_metadata": version_metadata_path,
        "missingness": missingness_path,
    }
    manifest: dict[str, Any] = {
        "dataset_version": config.dataset_version,
        "schema_version": config.canonical_schema_version,
        "dataset_identity_sha256": version_identity,
        "status": "READY",
        "record_count": frame.height,
        "row_alignment": "All CSV partitions preserve identical source row order.",
        "source": {
            "path": str(source_csv),
            "sha256": source_sha256,
            "feature_timing_path": str(feature_timing_path),
            "feature_timing_sha256": feature_timing_sha256,
        },
        "transformation": asdict(config),
        "partitions": {
            role: {
                "path": path.name,
                "sha256": partition_hashes[role],
                "columns": partitions[role].columns,
                "schema": _schema_for(partitions[role]),
            }
            for role, path in artifact_paths.items()
            if role in partitions
        },
        "excluded_post_decision_columns": excluded_columns,
        "primary_outcome": PRIMARY_OUTCOME_ID,
        "outcome_contract": outcome_columns_manifest["outcome_contract"],
        "supporting_artifacts": {
            name: {"path": path.name, "sha256": _sha256(path)}
            for name, path in supporting_paths.items()
        },
        "reproducibility_command": reproducibility_command,
        "clustering": {"column": config.clustering_key, "partition": "identifiers"},
        "temporal_splits": {
            "column": "split_label",
            "partition": "metadata",
            "strategy": "chronological; no random shuffling",
            "boundaries": {
                "development": ["2024-01-01", config.development_end],
                "validation": ["2025-01-01", config.validation_end],
                "future_holdout": ["2025-07-01", config.future_holdout_end],
            },
            "counts": dict(split_labels.value_counts().iter_rows()),
        },
        "feature_timing": {
            name: {
                "classification": timing[name]["classification"],
                "discovery_feature_allowed": timing[name]["discovery_feature_allowed"],
                "leakage_risk": timing[name]["leakage_risk"],
            }
            for name in frame.columns
        },
        "derived_metadata_columns": {
            "source_row_number": "One-based row lineage in the clean reference CSV.",
            "split_label": "Deterministic chronological split derived from booking_date.",
            "source_currency": "Renamed from the source METADATA field currency.",
        },
        "limitations": [
            "Candidate-specific exposure-group missingness is computed only after immutable "
            "candidate conditions exist.",
            "This benchmark analytical layer does not replace the blocked production TASK-010 "
            "customer-input canonicalization pipeline.",
        ],
    }
    manifest_path = version_root / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest
