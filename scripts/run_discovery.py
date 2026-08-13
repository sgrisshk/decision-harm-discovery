"""Run TASK-015 discovery against a versioned analytical dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/analytics/src"))

from policy_analytics.discovery.engine import DiscoveryConfig, discover_candidates
from policy_analytics.outcomes import DATASET_IDENTITY_SHA256, primary_outcome


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = cast(dict[str, Any], json.loads((args.dataset / "manifest.json").read_text()))
    if manifest["dataset_identity_sha256"] != DATASET_IDENTITY_SHA256:
        raise ValueError("dataset identity does not match outcome contract")
    features = pl.read_csv(args.dataset / "features.csv", try_parse_dates=False)
    outcomes = pl.read_csv(args.dataset / "outcomes.csv", try_parse_dates=False)
    metadata = pl.read_csv(args.dataset / "metadata.csv", try_parse_dates=False)
    if not (features.height == outcomes.height == metadata.height == manifest["record_count"]):
        raise ValueError("analytical partitions are not row-aligned")
    frame = pl.concat([features, outcomes, metadata.select("split_label")], how="horizontal")
    feature_columns = tuple(manifest["partitions"]["features"]["columns"])
    # Calendar dates are permitted decision-time fields but raw date thresholds are not reusable
    # policy rules, so v0 excludes them from candidate conditions.
    feature_columns = tuple(
        name for name in feature_columns if name not in {"booking_date", "travel_date"}
    )
    result = discover_candidates(frame, feature_columns, primary_outcome(), DiscoveryConfig())
    result.update(
        {
            "status": "PERSISTED",
            "dataset_version": manifest["dataset_version"],
            "dataset_identity_sha256": manifest["dataset_identity_sha256"],
            "outcome_contract_version": "1.0.0",
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
