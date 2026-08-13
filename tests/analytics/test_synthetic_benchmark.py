import csv
import json
from pathlib import Path

import pytest
from policy_analytics.blind_isolation import (
    FORBIDDEN_NAMES,
    PERMITTED_FILES,
    commit_candidates,
    prepare_blind_workspace,
    validate_blind_workspace,
)
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
    classes = {column["name"]: column for column in timing["columns"]}
    assert classes["booking_date"]["classification"] == "DECISION_TIME"
    assert classes["support_cases"]["discovery_feature_allowed"] is False
    assert classes["contribution_margin_eur"]["classification"] == "OUTCOME"


@pytest.mark.analytics
def test_blind_workspace_is_allowlisted_and_rejects_restricted_files(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    for relative in PERMITTED_FILES:
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"public input: {relative}\n", encoding="utf-8")
    workspace = tmp_path / "blind-workspace"

    manifest = prepare_blind_workspace(repository, workspace)

    assert set(manifest["files"]) == set(PERMITTED_FILES)
    assert not any(path.name in FORBIDDEN_NAMES for path in workspace.rglob("*"))
    assert validate_blind_workspace(workspace) == manifest

    (workspace / "hidden_ground_truth.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden"):
        validate_blind_workspace(workspace)


@pytest.mark.analytics
def test_evaluator_requires_signed_immutable_commitment(tmp_path: Path) -> None:
    output = tmp_path / "benchmark"
    generate_benchmark(output, BenchmarkConfig(row_count=100))
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps({"status": "PERSISTED", "blind_bundle_id": "a" * 64, "candidates": []}),
        encoding="utf-8",
    )
    receipt = tmp_path / "receipt.json"
    key = b"evaluator-owned-test-key-with-32-bytes-minimum"
    manifest = tmp_path / "BLIND_MANIFEST.json"
    manifest.write_text(
        json.dumps({"protocol_version": "1.0.0", "bundle_id": "a" * 64, "files": {}}),
        encoding="utf-8",
    )

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
    assert result["blind_bundle_id"] == "a" * 64

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
                "blind_bundle_id": "a" * 64,
                "candidates": [{"condition": "changed"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="changed after commitment"):
        evaluate_persisted_candidates(
            candidates, output / "evaluation" / "hidden_ground_truth.json", receipt, key
        )
