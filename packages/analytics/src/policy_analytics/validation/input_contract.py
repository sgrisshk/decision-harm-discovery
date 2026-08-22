"""Typed, fail-closed validation inputs derived from an analytical dataset manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast


class FeatureRole(StrEnum):
    DECISION_TIME = "DECISION_TIME"
    POST_DECISION = "POST_DECISION"
    OUTCOME = "OUTCOME"
    IDENTIFIER = "IDENTIFIER"
    METADATA = "METADATA"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ValidationInput:
    dataset_version: str
    dataset_identity_sha256: str
    feature_roles: dict[str, FeatureRole]
    decision_time_features: frozenset[str]
    adjustment_features: frozenset[str]
    heterogeneity_column: str | None
    seasonality_column: str | None
    clustering_column: str
    robustness_group_column: str | None
    alternative_outcome_id: str | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validation_input_from_manifest(dataset_root: Path) -> ValidationInput:
    """Load and verify the manifest-owned input contract used by every validation gate."""
    manifest_path = dataset_root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"analytical dataset manifest is missing: {manifest_path}")
    manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    dataset_version = manifest.get("dataset_version")
    identity = manifest.get("dataset_identity_sha256")
    if not isinstance(dataset_version, str) or not isinstance(identity, str):
        raise ValueError("analytical dataset manifest lacks dataset_version or dataset identity")

    raw_partitions = manifest.get("partitions")
    if not isinstance(raw_partitions, dict):
        raise ValueError("analytical dataset manifest lacks partitions")
    partitions = cast(dict[str, object], raw_partitions)
    physical_columns: dict[str, str] = {}
    for partition_name, raw_partition in partitions.items():
        if not isinstance(raw_partition, dict):
            raise ValueError(f"invalid manifest partition {partition_name!r}")
        partition = cast(dict[str, Any], raw_partition)
        path_value, expected_hash, columns = (
            partition.get("path"),
            partition.get("sha256"),
            partition.get("columns"),
        )
        if not isinstance(path_value, str) or not isinstance(expected_hash, str):
            raise ValueError(f"manifest partition {partition_name!r} lacks path or sha256")
        partition_path = dataset_root / path_value
        if not partition_path.is_file() or _sha256(partition_path) != expected_hash:
            raise ValueError(f"manifest drift for partition {partition_name!r}: hash mismatch")
        if not isinstance(columns, list):
            raise ValueError(f"manifest partition {partition_name!r} has invalid columns")
        typed_columns: list[str] = []
        for raw_column in cast(list[object], columns):
            if not isinstance(raw_column, str):
                raise ValueError(f"manifest partition {partition_name!r} has invalid columns")
            typed_columns.append(raw_column)
        for column in typed_columns:
            if column in physical_columns:
                raise ValueError(f"column {column!r} appears in multiple dataset partitions")
            physical_columns[column] = str(partition_name)

    raw_roles_value = manifest.get("feature_timing")
    if not isinstance(raw_roles_value, dict):
        raise ValueError("analytical dataset manifest lacks feature_timing roles")
    raw_roles = cast(dict[str, object], raw_roles_value)
    roles: dict[str, FeatureRole] = {}
    for column, partition_name in physical_columns.items():
        raw_entry = raw_roles.get(column)
        if raw_entry is None and partition_name == "metadata":
            roles[column] = FeatureRole.METADATA
            continue
        if not isinstance(raw_entry, dict):
            raise ValueError(f"missing feature role for column {column!r}")
        entry = cast(dict[str, object], raw_entry)
        classification = entry.get("classification")
        if not isinstance(classification, str):
            raise ValueError(f"missing feature role for column {column!r}")
        try:
            roles[column] = FeatureRole(classification)
        except ValueError as exc:
            raise ValueError(
                f"unknown feature role {classification!r} for column {column!r}"
            ) from exc

    raw_validation_value = manifest.get("validation_roles")
    if not isinstance(raw_validation_value, dict):
        raise ValueError("manifest lacks supported validation_roles version 1.0.0")
    raw_validation = cast(dict[str, object], raw_validation_value)
    if raw_validation.get("version") != "1.0.0":
        raise ValueError("manifest lacks supported validation_roles version 1.0.0")
    adjustment = raw_validation.get("adjustment_eligible")
    if not isinstance(adjustment, list):
        raise ValueError("validation_roles.adjustment_eligible must be a string list")
    adjustment_values: list[str] = []
    for raw_value in cast(list[object], adjustment):
        if not isinstance(raw_value, str):
            raise ValueError("validation_roles.adjustment_eligible must be a string list")
        adjustment_values.append(raw_value)

    def optional_column(key: str) -> str | None:
        value = raw_validation.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"validation_roles.{key} must be a column name or null")
        return value

    decision_time = frozenset(
        column for column, role in roles.items() if role is FeatureRole.DECISION_TIME
    )
    adjustment_features = frozenset(adjustment_values)
    semantic_columns = {
        "heterogeneity_column": optional_column("heterogeneity_column"),
        "seasonality_column": optional_column("seasonality_column"),
        "robustness_group_column": optional_column("robustness_group_column"),
    }
    for role_name, column in semantic_columns.items():
        if column is not None and roles.get(column) is not FeatureRole.DECISION_TIME:
            raise ValueError(f"{role_name} {column!r} is not a DECISION_TIME feature")
    invalid_adjustment = sorted(adjustment_features - decision_time)
    if invalid_adjustment:
        raise ValueError(
            f"adjustment eligibility includes non-DECISION_TIME columns: {invalid_adjustment}"
        )
    clustering_value = manifest.get("clustering")
    if not isinstance(clustering_value, dict):
        raise ValueError("manifest lacks clustering.column")
    clustering = cast(dict[str, object], clustering_value)
    if not isinstance(clustering.get("column"), str):
        raise ValueError("manifest lacks clustering.column")
    clustering_column = cast(str, clustering["column"])
    if roles.get(clustering_column) is not FeatureRole.IDENTIFIER:
        raise ValueError(f"clustering column {clustering_column!r} is not an IDENTIFIER")
    alternative_outcome = raw_validation.get("alternative_outcome_id")
    if alternative_outcome is not None and (
        not isinstance(alternative_outcome, str)
        or roles.get(alternative_outcome) is not FeatureRole.OUTCOME
    ):
        raise ValueError(
            "validation_roles.alternative_outcome_id must name an OUTCOME column or null"
        )
    return ValidationInput(
        dataset_version=dataset_version,
        dataset_identity_sha256=identity,
        feature_roles=roles,
        decision_time_features=decision_time,
        adjustment_features=adjustment_features,
        heterogeneity_column=semantic_columns["heterogeneity_column"],
        seasonality_column=semantic_columns["seasonality_column"],
        clustering_column=clustering_column,
        robustness_group_column=semantic_columns["robustness_group_column"],
        alternative_outcome_id=alternative_outcome,
    )


def validate_candidate_fields(candidates: list[dict[str, Any]], inputs: ValidationInput) -> None:
    """Reject candidate fields absent from, or unsafe according to, the signed manifest."""
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id", "<unknown>")
        conditions = candidate.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise ValueError(f"candidate {candidate_id!r} has no valid conditions")
        for raw_condition in cast(list[object], conditions):
            condition = (
                cast(dict[str, object], raw_condition) if isinstance(raw_condition, dict) else {}
            )
            feature = condition.get("feature")
            if not isinstance(feature, str) or feature not in inputs.feature_roles:
                raise ValueError(
                    f"candidate {candidate_id!r} references unknown feature {feature!r}"
                )
