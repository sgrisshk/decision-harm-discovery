"""Versioned chronological splits with explicit outcome-maturity handling."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import polars as pl

from policy_analytics.outcomes.contract import (
    DISCOVERY_CONTRACT,
    OUTCOME_CONTRACT_VERSION,
    OUTCOME_DEFINITIONS,
)

SPLIT_CONFIG_VERSION = "travel-bookings-temporal-split-v1.0.0"


@dataclass(frozen=True)
class TemporalSplitConfig:
    version: str = SPLIT_CONFIG_VERSION
    timestamp_column: str = "booking_date"
    development_start: str = "2024-01-01"
    development_end: str = "2024-12-31"
    validation_start: str = "2025-01-01"
    validation_end: str = "2025-06-30"
    future_holdout_start: str = "2025-07-01"
    future_holdout_end: str = "2025-12-31"
    assignment_rule: str = "closed intervals on booking_date; no random shuffle"
    outcome_availability_mode: str = "CLOSED_SYNTHETIC_BENCHMARK"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_config(config: TemporalSplitConfig) -> None:
    if config.outcome_availability_mode != "CLOSED_SYNTHETIC_BENCHMARK":
        raise ValueError(
            "live/open datasets require an approved observation cutoff and outcome maturation "
            "windows; they cannot use the synthetic all-final policy"
        )
    boundaries = [
        date.fromisoformat(config.development_start),
        date.fromisoformat(config.development_end),
        date.fromisoformat(config.validation_start),
        date.fromisoformat(config.validation_end),
        date.fromisoformat(config.future_holdout_start),
        date.fromisoformat(config.future_holdout_end),
    ]
    if boundaries != sorted(boundaries):
        raise ValueError("temporal boundaries must be chronologically ordered")
    if boundaries[1].toordinal() + 1 != boundaries[2].toordinal():
        raise ValueError("development and validation boundaries must be contiguous")
    if boundaries[3].toordinal() + 1 != boundaries[4].toordinal():
        raise ValueError("validation and future holdout boundaries must be contiguous")


def assign_temporal_splits(
    booking_dates: pl.Series, config: TemporalSplitConfig | None = None
) -> pl.Series:
    """Assign exactly one chronological split to every supported booking date."""
    config = config or TemporalSplitConfig()
    _validate_config(config)
    parsed = booking_dates.str.to_date() if booking_dates.dtype == pl.String else booking_dates
    labels = (
        pl.DataFrame({config.timestamp_column: parsed})
        .select(
            pl.when(
                pl.col(config.timestamp_column).is_between(
                    date.fromisoformat(config.development_start),
                    date.fromisoformat(config.development_end),
                    closed="both",
                )
            )
            .then(pl.lit("development"))
            .when(
                pl.col(config.timestamp_column).is_between(
                    date.fromisoformat(config.validation_start),
                    date.fromisoformat(config.validation_end),
                    closed="both",
                )
            )
            .then(pl.lit("validation"))
            .when(
                pl.col(config.timestamp_column).is_between(
                    date.fromisoformat(config.future_holdout_start),
                    date.fromisoformat(config.future_holdout_end),
                    closed="both",
                )
            )
            .then(pl.lit("future_holdout"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("split_label")
        )
        .to_series()
    )
    if labels.null_count():
        raise ValueError("records exist outside the configured temporal split windows")
    return labels


def build_temporal_split_manifest(
    dataset_root: Path, config: TemporalSplitConfig | None = None
) -> dict[str, Any]:
    """Verify alignment and persist split membership plus its machine-readable contract."""
    config = config or TemporalSplitConfig()
    _validate_config(config)
    aggregate = cast(
        dict[str, Any], json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    )
    features = pl.read_csv(dataset_root / "features.csv", columns=[config.timestamp_column])
    identifiers = pl.read_csv(dataset_root / "identifiers.csv", columns=["booking_id"])
    outcomes = pl.read_csv(dataset_root / "outcomes.csv")
    existing_metadata = pl.read_csv(dataset_root / "metadata.csv", columns=["split_label"])
    if not (
        features.height
        == identifiers.height
        == outcomes.height
        == existing_metadata.height
        == aggregate["record_count"]
    ):
        raise ValueError("analytical partitions are not row-aligned")
    labels = assign_temporal_splits(features[config.timestamp_column], config)
    if not labels.equals(existing_metadata["split_label"]):
        raise ValueError("TASK-011 metadata split labels disagree with TASK-012 assignment")
    membership = pl.DataFrame(
        {
            "booking_id": identifiers["booking_id"],
            "booking_date": features[config.timestamp_column],
            "split_label": labels,
            "outcomes_final": pl.Series([True] * features.height),
        }
    )
    membership_path = dataset_root / "split_membership.csv"
    membership.write_csv(membership_path)

    split_details: dict[str, Any] = {}
    for split in ("development", "validation", "future_holdout"):
        subset = membership.filter(  # pyright: ignore[reportUnknownMemberType]
            pl.col("split_label") == split
        )
        split_details[split] = {
            "start_inclusive": getattr(config, f"{split}_start"),
            "end_inclusive": getattr(config, f"{split}_end"),
            "row_count": subset.height,
            "first_booking_date": subset["booking_date"].min(),
            "last_booking_date": subset["booking_date"].max(),
            "all_outcomes_final": bool(subset["outcomes_final"].all()),
        }
    manifest: dict[str, Any] = {
        "split_config_version": config.version,
        "analytical_dataset_version": aggregate["dataset_version"],
        "analytical_dataset_identity_sha256": aggregate["dataset_identity_sha256"],
        "schema_version": aggregate["schema_version"],
        "config": asdict(config),
        "assignment_invariants": {
            "random_shuffle": False,
            "exactly_one_split_per_record": True,
            "overlap_count": 0,
            "unassigned_count": 0,
            "row_order_changed": False,
        },
        "splits": split_details,
        "discovery_usage": {
            "search_fit_split": DISCOVERY_CONTRACT.search_fit_split,
            "diagnostic_only_splits": list(DISCOVERY_CONTRACT.diagnostic_only_splits),
            "permitted_development_rows": split_details["development"]["row_count"],
        },
        "outcome_availability": {
            "mode": config.outcome_availability_mode,
            "contract_version": OUTCOME_CONTRACT_VERSION,
            "all_rows_final": True,
            "basis": (
                "TASK-013 defines this generated 24-month benchmark as closed: downstream costs "
                "and outcomes were fully realized before export, so it has no right-censoring."
            ),
            "outcomes": [
                {
                    "outcome_id": definition.outcome_id,
                    "column": definition.column,
                    "final_for_all_rows": True,
                    "missing_data_policy": definition.missing_data_policy.value,
                }
                for definition in OUTCOME_DEFINITIONS
            ],
            "production_guard": (
                "Do not reuse CLOSED_SYNTHETIC_BENCHMARK for live data. A future customer outcome "
                "contract must provide an observation cutoff and per-outcome maturation window; "
                "immature records must be marked outcomes_final=false and excluded from final-"
                "outcome estimation, never coerced to zero or treated as final."
            ),
        },
        "membership_artifact": {
            "path": membership_path.name,
            "sha256": _sha256(membership_path),
            "columns": membership.columns,
        },
        "reproducibility_command": "make temporal-splits",
    }
    _write_json(dataset_root / "split_manifest.json", manifest)
    return manifest
