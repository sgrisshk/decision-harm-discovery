from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import polars as pl
import pytest
from policy_analytics.outcomes import primary_outcome
from policy_analytics.validation.apply import run_validation
from policy_analytics.validation.contract import GateId, GateOutcome
from policy_analytics.validation.input_contract import (
    FeatureRole,
    validation_input_from_manifest,
)

pytestmark = pytest.mark.analytics


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _neutral_dataset(root: Path) -> tuple[Path, Path]:
    root.mkdir()
    features = pl.DataFrame(
        {
            "signal_alpha": ["yes", "no"] * 45,
            "adjust_beta": ["low", "high", "low"] * 30,
            "segment_gamma": ["one"] * 45 + ["two"] * 45,
            "event_clock": [
                f"{year}-{month:02d}-15"
                for year in (2024, 2025)
                for month in range(1, 13)
                for _ in range(4)
            ][:90],
        }
    )
    outcomes = pl.DataFrame(
        {"result_value": [80.0 if value == "yes" else 100.0 for value in features["signal_alpha"]]}
    )
    identifiers = pl.DataFrame({"record_key": [f"r{i}" for i in range(90)]})
    metadata = pl.DataFrame(
        {"split_label": ["development"] * 30 + ["validation"] * 30 + ["future_holdout"] * 30}
    )
    frames = {
        "features": features,
        "outcomes": outcomes,
        "identifiers": identifiers,
        "metadata": metadata,
    }
    partitions: dict[str, object] = {}
    roles: dict[str, object] = {}
    partition_role = {
        "features": "DECISION_TIME",
        "outcomes": "OUTCOME",
        "identifiers": "IDENTIFIER",
        "metadata": "METADATA",
    }
    for name, frame in frames.items():
        path = root / f"{name}.csv"
        frame.write_csv(path)
        partitions[name] = {
            "path": path.name,
            "sha256": _sha256(path),
            "columns": frame.columns,
            "schema": [{"name": key, "dtype": str(value)} for key, value in frame.schema.items()],
        }
        for column in frame.columns:
            roles[column] = {"classification": partition_role[name]}
    manifest = {
        "dataset_version": "neutral-analytical-v1",
        "dataset_identity_sha256": "a" * 64,
        "partitions": partitions,
        "feature_timing": roles,
        "clustering": {"column": "record_key", "partition": "identifiers"},
        "validation_roles": {
            "version": "1.0.0",
            "adjustment_eligible": ["adjust_beta", "segment_gamma"],
            "heterogeneity_column": "segment_gamma",
            "seasonality_column": "event_clock",
            "robustness_group_column": None,
            "alternative_outcome_id": None,
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    candidates = {
        "status": "PERSISTED",
        "search": {"evaluated_hypotheses": 1},
        "candidates": [
            {
                "candidate_id": "NEUTRAL-001",
                "conditions": [{"feature": "signal_alpha", "operator": "eq", "value": "yes"}],
                "outcome": "result_value",
            }
        ],
    }
    candidates_path = root / "candidates.json"
    candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
    return root, candidates_path


def test_neutral_domain_drives_g01_g06_g09_g11_from_manifest(tmp_path: Path) -> None:
    root, candidates = _neutral_dataset(tmp_path / "neutral")
    outcome = replace(
        primary_outcome(),
        outcome_id="result_value",
        column="result_value",
        unit="neutral units",
    )
    results, run_manifest = run_validation(
        root, candidates, outcome, "neutral-analytical-v1", "test", "neutral-run"
    )
    result = results[0]
    gates = {gate.gate_id: gate for gate in result.report.gate_results}
    assert gates[GateId.TARGET_LEAKAGE].outcome is GateOutcome.PASS
    assert gates[GateId.SIMPSON].outcome is not GateOutcome.NOT_EVALUATED
    assert gates[GateId.SEASONALITY].outcome is not GateOutcome.NOT_EVALUATED
    assert result.diagnostics["adjustment_columns_considered"] == [
        "adjust_beta",
        "segment_gamma",
    ]
    assert run_manifest["heterogeneity_column"] == "segment_gamma"
    assert run_manifest["seasonality_column"] == "event_clock"


def test_roles_are_typed_and_unknown_post_outcome_identifier_metadata_fail_closed(
    tmp_path: Path,
) -> None:
    root, _ = _neutral_dataset(tmp_path / "neutral")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert (
        validation_input_from_manifest(root).feature_roles["signal_alpha"]
        is FeatureRole.DECISION_TIME
    )

    for role in ("UNKNOWN", "POST_DECISION", "OUTCOME", "IDENTIFIER", "METADATA"):
        changed = json.loads(json.dumps(manifest))
        changed["feature_timing"]["adjust_beta"]["classification"] = role
        manifest_path.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match="non-DECISION_TIME"):
            validation_input_from_manifest(root)
    manifest_path.write_text(json.dumps(manifest))


def test_missing_unknown_roles_and_partition_drift_have_clear_errors(tmp_path: Path) -> None:
    root, _ = _neutral_dataset(tmp_path / "neutral")
    manifest_path = root / "manifest.json"
    original = json.loads(manifest_path.read_text())

    missing = json.loads(json.dumps(original))
    del missing["feature_timing"]["signal_alpha"]
    manifest_path.write_text(json.dumps(missing))
    with pytest.raises(ValueError, match="missing feature role.*signal_alpha"):
        validation_input_from_manifest(root)

    unknown = json.loads(json.dumps(original))
    unknown["feature_timing"]["signal_alpha"]["classification"] = "MYSTERY"
    manifest_path.write_text(json.dumps(unknown))
    with pytest.raises(ValueError, match="unknown feature role"):
        validation_input_from_manifest(root)

    manifest_path.write_text(json.dumps(original))
    (root / "features.csv").write_text("signal_alpha\nchanged\n")
    with pytest.raises(ValueError, match="manifest drift.*hash mismatch"):
        validation_input_from_manifest(root)


def test_candidate_field_must_exist_in_manifest(tmp_path: Path) -> None:
    root, candidates_path = _neutral_dataset(tmp_path / "neutral")
    payload = json.loads(candidates_path.read_text())
    payload["candidates"][0]["conditions"][0]["feature"] = "invented_field"
    candidates_path.write_text(json.dumps(payload))
    outcome = replace(primary_outcome(), outcome_id="result_value", column="result_value")
    with pytest.raises(ValueError, match="unknown feature.*invented_field"):
        run_validation(root, candidates_path, outcome, "neutral-analytical-v1", "test", "run")


def test_g01_rejects_outcome_leakage_from_manifest_role(tmp_path: Path) -> None:
    root, candidates_path = _neutral_dataset(tmp_path / "neutral")
    payload = json.loads(candidates_path.read_text())
    payload["candidates"][0]["conditions"][0] = {
        "feature": "result_value",
        "operator": "ge",
        "value": 90.0,
    }
    candidates_path.write_text(json.dumps(payload))
    outcome = replace(primary_outcome(), outcome_id="result_value", column="result_value")
    results, _ = run_validation(
        root, candidates_path, outcome, "neutral-analytical-v1", "test", "run"
    )
    g01 = next(
        gate for gate in results[0].report.gate_results if gate.gate_id is GateId.TARGET_LEAKAGE
    )
    assert g01.outcome is GateOutcome.FAIL
    assert "result_value" in g01.detail
