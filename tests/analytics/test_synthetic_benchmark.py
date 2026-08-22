import csv
import json
from pathlib import Path

import pytest
from policy_analytics.blind_isolation import (
    FORBIDDEN_NAMES,
    PERMITTED_FILES,
    PUBLIC_METADATA_FILES,
    commit_candidates,
    prepare_blind_workspace,
    validate_blind_workspace,
)
from policy_analytics.outcomes.contract import OUTCOME_CONTRACT_VERSION
from policy_analytics.synthetic_benchmark import (
    BenchmarkConfig,
    evaluate_persisted_candidates,
    generate_benchmark,
)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


@pytest.mark.analytics
def test_generation_is_reproducible_and_separates_ground_truth(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    config = BenchmarkConfig(row_count=600)

    first_checksums = generate_benchmark(first, config)
    second_checksums = generate_benchmark(second, config)
    repeated_checksums = generate_benchmark(first, config)

    assert first_checksums == second_checksums
    assert first_checksums == repeated_checksums
    public_text = "".join(
        path.read_text(encoding="utf-8")
        for directory in ("raw", "reference", "metadata")
        for path in (first / directory).glob("*")
    )
    assert "affected_booking_ids" not in public_text
    assert "confounding_traps" not in public_text
    assert all("evaluation/" not in path for path in first_checksums)
    assert (first / "evaluation" / "hidden_ground_truth.json").exists()


@pytest.mark.analytics
def test_expected_rows_patterns_dirty_layer_and_temporal_coverage(tmp_path: Path) -> None:
    output = tmp_path / "benchmark"
    config = BenchmarkConfig(row_count=2_000, dirty_duplicate_rows=17)
    generate_benchmark(output, config)

    clean = _read_rows(output / "reference" / "travel_bookings_clean.csv")
    dirty = _read_rows(output / "raw" / "travel_bookings_dirty.csv")
    truth = json.loads((output / "evaluation" / "hidden_ground_truth.json").read_text())
    timing = json.loads((output / "metadata" / "feature_timing.json").read_text())

    assert len(clean) == 2_000
    assert len(dirty) == 2_017
    assert min(row["booking_date"] for row in clean) >= "2024-01-01"
    assert max(row["booking_date"] for row in clean) <= "2025-12-31"
    assert len(truth["patterns"]) >= 8
    assert len(truth["confounding_traps"]) >= 5
    assert all(pattern["affected_booking_ids"] for pattern in truth["patterns"])
    assert all(
        pattern["realized_counterfactual_effects"]["outcomes"]["contribution_margin_eur"][
            "mean_effect"
        ]
        is not None
        for pattern in truth["patterns"]
    )
    for pattern in truth["patterns"]:
        effect = pattern["true_effect"]
        assert effect["pattern_id"] == pattern["id"]
        assert effect["configured_effect"]
        assert effect["realized_effect"] < 0
        assert effect["direction"] == "decrease_is_harm"
        assert effect["affected_n"] == len(pattern["affected_booking_ids"])
        assert effect["affected_support"] == pytest.approx(effect["affected_n"] / 2_000)
        assert effect["realized_economic_impact"] == pytest.approx(
            -effect["realized_effect"] * effect["affected_n"], abs=0.01
        )
        assert effect["valid_time_interval"]["start_inclusive"] >= "2024-01-01"
        assert effect["valid_time_interval"]["end_inclusive"] == "2025-12-31"
        assert effect["relevant_outcome"] == "contribution_margin_eur"
        assert effect["units"]["realized_effect"].startswith("EUR per booking")
    classes = {column["name"]: column for column in timing["columns"]}
    assert classes["booking_date"]["classification"] == "DECISION_TIME"
    assert classes["support_cases"]["discovery_feature_allowed"] is False
    assert classes["contribution_margin_eur"]["classification"] == "OUTCOME"


@pytest.mark.analytics
def test_blind_workspace_is_allowlisted_and_rejects_restricted_files(tmp_path: Path) -> None:
    key = b"evaluator-owned-test-key-with-32-bytes-minimum"
    repository = tmp_path / "repository"
    for relative in PERMITTED_FILES:
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"public input: {relative}\n", encoding="utf-8")
    analytical_manifest = (
        repository / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/manifest.json"
    )
    analytical_manifest.write_text(
        json.dumps(
            {
                "dataset_version": "travel-bookings-analytical-v1.1.0",
                "dataset_identity_sha256": "a" * 64,
                "outcome_contract": {
                    "dataset_scope": "travel-bookings-analytical-v1.1.0",
                    "version": OUTCOME_CONTRACT_VERSION,
                },
                "record_count": 10,
                "partitions": {
                    name: {"columns": [name], "schema": [{"name": name, "dtype": "String"}]}
                    for name in ("features", "outcomes", "identifiers", "metadata")
                },
                "feature_timing": {},
                "excluded_post_decision_columns": [],
                "temporal_splits": {},
            }
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "blind-workspace"

    manifest = prepare_blind_workspace(repository, workspace, key)

    assert set(manifest["files"]) == set(PERMITTED_FILES) | set(PUBLIC_METADATA_FILES)
    assert not any(path.name in FORBIDDEN_NAMES for path in workspace.rglob("*"))
    assert not any(path.suffix == ".py" for path in workspace.rglob("*"))
    public_text = "".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in workspace.rglob("*")
        if path.is_file()
    )
    for private_marker in (
        "affected_booking_ids",
        "confounding_traps",
        "corruption_manifest",
        "generation_config",
        "hidden_ground_truth",
        "ground_truth.yaml",
        "true_effect",
        "configured_effect",
        "realized_effect",
        "realized_economic_impact",
    ):
        assert private_marker not in public_text
    assert validate_blind_workspace(workspace, key) == manifest

    (workspace / "hidden_ground_truth.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden"):
        validate_blind_workspace(workspace, key)


@pytest.mark.analytics
def test_evaluator_requires_signed_immutable_commitment(tmp_path: Path) -> None:
    output = tmp_path / "benchmark"
    generate_benchmark(output, BenchmarkConfig(row_count=200))
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps({"status": "PERSISTED", "blind_bundle_id": "a" * 64, "candidates": []}),
        encoding="utf-8",
    )
    receipt = tmp_path / "receipt.json"
    key = b"evaluator-owned-test-key-with-32-bytes-minimum"
    repository = tmp_path / "repository"
    for relative in PERMITTED_FILES:
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"public input: {relative}\n", encoding="utf-8")
    analytical_manifest = (
        repository / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/manifest.json"
    )
    analytical_manifest.write_text(
        json.dumps(
            {
                "dataset_version": "travel-bookings-analytical-v1.1.0",
                "dataset_identity_sha256": "a" * 64,
                "outcome_contract": {
                    "dataset_scope": "travel-bookings-analytical-v1.1.0",
                    "version": OUTCOME_CONTRACT_VERSION,
                },
                "record_count": 10,
                "partitions": {
                    name: {"columns": [name], "schema": [{"name": name, "dtype": "String"}]}
                    for name in ("features", "outcomes", "identifiers", "metadata")
                },
                "feature_timing": {},
                "excluded_post_decision_columns": [],
                "temporal_splits": {},
            }
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    issued = prepare_blind_workspace(repository, workspace, key)
    manifest = workspace / "BLIND_MANIFEST.json"
    candidate_payload = json.loads(candidates.read_text(encoding="utf-8"))
    candidate_payload["blind_bundle_id"] = issued["bundle_id"]
    candidates.write_text(json.dumps(candidate_payload), encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        evaluate_persisted_candidates(
            candidates,
            output / "evaluation" / "hidden_ground_truth.json",
            receipt,
            key,
        )

    committed = commit_candidates(candidates, manifest, receipt, key)
    result = evaluate_persisted_candidates(
        candidates, output / "evaluation" / "hidden_ground_truth.json", receipt, key
    )
    assert result["candidate_file_sha256"] == committed["candidate_sha256"]
    assert result["blind_bundle_id"] == issued["bundle_id"]

    forged_manifest = tmp_path / "forged-manifest.json"
    forged_manifest.write_text(
        json.dumps({"protocol_version": "1.0.0", "bundle_id": "b" * 64, "files": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="coordinator signature"):
        commit_candidates(candidates, forged_manifest, tmp_path / "forged-receipt.json", key)

    with pytest.raises(ValueError, match="signature is invalid"):
        evaluate_persisted_candidates(
            candidates,
            output / "evaluation" / "hidden_ground_truth.json",
            receipt,
            b"different-evaluator-key-with-at-least-32-bytes",
        )

    candidates.write_text(
        json.dumps(
            {
                "status": "PERSISTED",
                "blind_bundle_id": issued["bundle_id"],
                "candidates": [{"condition": "changed"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="changed after commitment"):
        evaluate_persisted_candidates(
            candidates, output / "evaluation" / "hidden_ground_truth.json", receipt, key
        )
