"""Filesystem boundary and signed commitment for blind benchmark discovery."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from policy_analytics.outcomes.contract import (
    DATASET_IDENTITY_SHA256,
    DATASET_VERSION,
    DEFAULT_COMPARISON_RULE,
    ELIGIBLE_COHORT_RULE,
    OUTCOME_CONTRACT_VERSION,
    OUTCOME_DEFINITIONS,
    PRIMARY_OUTCOME_ID,
)

BLIND_PROTOCOL_VERSION = "1.0.0"
PERMITTED_FILES = (
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/features.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/outcomes.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/identifiers.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/metadata.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/split_manifest.json",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/split_membership.csv",
)
PUBLIC_METADATA_FILES = (
    "public/schema.json",
    "public/feature_timing.json",
    "public/outcome_metadata.json",
    "public/run_config.json",
)
FORBIDDEN_NAMES = {
    "corruption_manifest.json",
    "generation_config.json",
    "hidden_ground_truth.json",
    "synthetic_benchmark.py",
    "evaluate_synthetic_benchmark.py",
    "generate_synthetic_benchmark.py",
    "ground_truth.yaml",
    "checksums.json",
    "manifest.json",
    "missingness.json",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require_signing_key(signing_key: bytes) -> None:
    if len(signing_key) < 32:
        raise ValueError("BLIND_EVALUATION_KEY must contain at least 32 bytes")


def _signature(payload: dict[str, Any], signing_key: bytes, domain: bytes) -> str:
    _require_signing_key(signing_key)
    return hmac.new(signing_key, domain + _canonical_json(payload), hashlib.sha256).hexdigest()


def _verify_issued_manifest(manifest: dict[str, Any], signing_key: bytes) -> dict[str, Any]:
    signature = manifest.get("coordinator_signature")
    unsigned = {key: value for key, value in manifest.items() if key != "coordinator_signature"}
    expected = _signature(unsigned, signing_key, b"blind-manifest-v1\0")
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise ValueError("blind manifest coordinator signature is invalid")
    if unsigned.get("protocol_version") != BLIND_PROTOCOL_VERSION:
        raise ValueError("blind manifest protocol version is unsupported")
    raw_files: object = unsigned.get("files")
    if not isinstance(raw_files, dict):
        raise ValueError("blind manifest files must be an object")
    files = cast(dict[object, object], raw_files)
    file_names = {key for key in files if isinstance(key, str)}
    if file_names != set(PERMITTED_FILES) | set(PUBLIC_METADATA_FILES):
        raise ValueError("blind manifest does not contain the exact issued allowlist")
    copied = {str(key): str(value) for key, value in files.items()}
    if hashlib.sha256(_canonical_json(copied)).hexdigest() != unsigned.get("bundle_id"):
        raise ValueError("blind manifest bundle_id is invalid")
    return unsigned


def _write_public_metadata(repository: Path, destination: Path) -> dict[str, str]:
    analytical_manifest_path = (
        repository / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/manifest.json"
    )
    analytical_manifest = json.loads(analytical_manifest_path.read_text(encoding="utf-8"))
    if analytical_manifest.get("dataset_identity_sha256") != DATASET_IDENTITY_SHA256:
        raise ValueError("analytical dataset does not match the approved outcome contract")

    public_payloads: dict[str, dict[str, Any]] = {
        "public/schema.json": {
            "dataset_version": DATASET_VERSION,
            "dataset_identity_sha256": DATASET_IDENTITY_SHA256,
            "record_count": analytical_manifest["record_count"],
            "partitions": {
                name: {
                    "columns": partition["columns"],
                    "schema": partition["schema"],
                }
                for name, partition in analytical_manifest["partitions"].items()
            },
        },
        "public/feature_timing.json": {
            "dataset_version": DATASET_VERSION,
            "columns": analytical_manifest["feature_timing"],
            "excluded_post_decision_columns": analytical_manifest["excluded_post_decision_columns"],
        },
        "public/outcome_metadata.json": {
            "contract_version": OUTCOME_CONTRACT_VERSION,
            "dataset_version": DATASET_VERSION,
            "dataset_identity_sha256": DATASET_IDENTITY_SHA256,
            "primary_outcome_id": PRIMARY_OUTCOME_ID,
            "eligible_cohort_rule": ELIGIBLE_COHORT_RULE,
            "default_comparison_rule": DEFAULT_COMPARISON_RULE,
            "outcomes": [asdict(definition) for definition in OUTCOME_DEFINITIONS],
        },
        "public/run_config.json": {
            "blind_protocol_version": BLIND_PROTOCOL_VERSION,
            "dataset_version": DATASET_VERSION,
            "dataset_identity_sha256": DATASET_IDENTITY_SHA256,
            "analytical_partitions": {
                Path(relative).stem: relative for relative in PERMITTED_FILES
            },
            "schema": "public/schema.json",
            "feature_timing": "public/feature_timing.json",
            "outcome_metadata": "public/outcome_metadata.json",
            "temporal_splits": analytical_manifest["temporal_splits"],
            "candidate_output": "candidates.json",
        },
    }
    written: dict[str, str] = {}
    for relative, payload in public_payloads.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[relative] = sha256_file(target)
    return written


def prepare_blind_workspace(
    repository: Path, destination: Path, signing_key: bytes
) -> dict[str, Any]:
    """Create a new workspace from a strict allowlist and return its manifest."""
    repository = repository.resolve()
    destination = destination.resolve()
    if destination == repository or repository in destination.parents:
        raise ValueError("blind workspace must be outside the source repository")
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")

    missing = [relative for relative in PERMITTED_FILES if not (repository / relative).is_file()]
    if missing:
        raise FileNotFoundError(f"required blind inputs are missing: {', '.join(missing)}")

    destination.mkdir(parents=True)
    copied: dict[str, str] = {}
    for relative in PERMITTED_FILES:
        source = repository / relative
        if source.is_symlink():
            raise ValueError(f"symlinks are forbidden in blind inputs: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[relative] = sha256_file(target)
    copied.update(_write_public_metadata(repository, destination))

    bundle_id = hashlib.sha256(_canonical_json(copied)).hexdigest()
    unsigned_manifest: dict[str, Any] = {
        "protocol_version": BLIND_PROTOCOL_VERSION,
        "bundle_id": bundle_id,
        "files": copied,
    }
    manifest = {
        **unsigned_manifest,
        "coordinator_signature": _signature(unsigned_manifest, signing_key, b"blind-manifest-v1\0"),
    }
    (destination / "BLIND_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def validate_blind_workspace(workspace: Path, signing_key: bytes) -> dict[str, Any]:
    """Fail if a workspace differs from its allowlisted manifest or contains restricted names."""
    workspace = workspace.resolve()
    manifest_path = workspace / "BLIND_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    issued = _verify_issued_manifest(manifest, signing_key)
    raw_expected_files: object = issued.get("files")
    if not isinstance(raw_expected_files, dict):
        raise ValueError("blind manifest files must be an object")
    expected_files = cast(dict[str, str], raw_expected_files)

    actual_paths = {
        str(path.relative_to(workspace))
        for path in workspace.rglob("*")
        if path.is_file() and path != manifest_path
    }
    expected_paths = set(expected_files)
    unexpected = actual_paths - expected_paths
    missing = expected_paths - actual_paths
    forbidden = {
        path
        for path in actual_paths
        if Path(path).name in FORBIDDEN_NAMES or (workspace / path).is_symlink()
    }
    if unexpected or missing or forbidden:
        raise ValueError(
            f"invalid blind workspace: unexpected={sorted(unexpected)}, "
            f"missing={sorted(missing)}, forbidden={sorted(forbidden)}"
        )
    for relative, expected_hash in expected_files.items():
        if sha256_file(workspace / relative) != expected_hash:
            raise ValueError(f"blind input was modified: {relative}")
    return manifest


def commit_candidates(
    candidates_path: Path, manifest_path: Path, receipt_path: Path, signing_key: bytes
) -> dict[str, Any]:
    """Create an evaluator-signed commitment to an immutable candidate artifact."""
    _require_signing_key(signing_key)
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    if candidates.get("status") != "PERSISTED":
        raise ValueError("candidates must have status=PERSISTED before evaluator acceptance")
    bundle_id = candidates.get("blind_bundle_id")
    if not isinstance(bundle_id, str) or len(bundle_id) != 64:
        raise ValueError("candidates must include the 64-character blind_bundle_id")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    issued = _verify_issued_manifest(manifest, signing_key)
    if issued.get("bundle_id") != bundle_id:
        raise ValueError("candidate bundle does not match the issued blind manifest")
    if not isinstance(candidates.get("candidates"), list):
        raise ValueError("candidates must include a candidates list")
    if receipt_path.exists():
        raise FileExistsError(f"receipt already exists: {receipt_path}")

    payload: dict[str, Any] = {
        "protocol_version": BLIND_PROTOCOL_VERSION,
        "blind_bundle_id": bundle_id,
        "blind_manifest_sha256": sha256_file(manifest_path),
        "candidate_sha256": sha256_file(candidates_path),
        "committed_at": datetime.now(UTC).isoformat(),
    }
    signature = _signature(payload, signing_key, b"candidate-receipt-v1\0")
    receipt = {**payload, "signature": signature}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def verify_candidate_commitment(
    candidates_path: Path, receipt_path: Path, signing_key: bytes
) -> dict[str, Any]:
    """Verify evaluator signature and candidate bytes before hidden truth is opened."""
    _require_signing_key(signing_key)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    signature = receipt.pop("signature", None)
    expected = _signature(receipt, signing_key, b"candidate-receipt-v1\0")
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise ValueError("candidate commitment signature is invalid")
    if receipt.get("candidate_sha256") != sha256_file(candidates_path):
        raise ValueError("candidate artifact changed after commitment")
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    if receipt.get("blind_bundle_id") != candidates.get("blind_bundle_id"):
        raise ValueError("candidate bundle does not match the signed commitment")
    return {**receipt, "signature": signature}
