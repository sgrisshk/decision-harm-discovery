"""Filesystem boundary and signed commitment for blind benchmark discovery."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import stat
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from policy_analytics.outcomes.contract import (
    DEFAULT_COMPARISON_RULE,
    ELIGIBLE_COHORT_RULE,
    OUTCOME_CONTRACT_VERSION,
    OUTCOME_DEFINITIONS,
    PRIMARY_OUTCOME_ID,
)

BLIND_PROTOCOL_VERSION = "1.0.0"
PERMITTED_FILES = (
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/features.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/outcomes.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/identifiers.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/metadata.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/split_manifest.json",
    "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/split_membership.csv",
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


def read_evaluator_key(key_file: Path) -> bytes:
    """Read evaluator key material without putting the secret in argv or child environments."""
    key_file = key_file.resolve()
    if key_file.is_symlink() or not key_file.is_file():
        raise ValueError("evaluator key must be a regular non-symlink file")
    key_stat = key_file.stat()
    if key_stat.st_uid != os.getuid() or stat.S_IMODE(key_stat.st_mode) != 0o600:
        raise ValueError("evaluator key must be owned by this identity with mode 0600")
    try:
        key = bytes.fromhex(key_file.read_text(encoding="ascii").strip())
    except ValueError as exc:
        raise ValueError("evaluator key must be hex-encoded") from exc
    _require_signing_key(key)
    return key


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
    runner_signature = manifest.get("evaluator_signature")
    if runner_signature is not None:
        unsigned_runner = {
            key: value for key, value in manifest.items() if key != "evaluator_signature"
        }
        expected_runner = _signature(unsigned_runner, signing_key, b"blind-agent-manifest-v1\0")
        if not isinstance(runner_signature, str) or not hmac.compare_digest(
            runner_signature, expected_runner
        ):
            raise ValueError("blind manifest evaluator signature is invalid")
        raw_files: object = unsigned_runner.get("allowed_files")
        if not isinstance(raw_files, dict) or not raw_files:
            raise ValueError("blind runner manifest allowed_files must be a non-empty object")
        runner_files = cast(dict[object, object], raw_files)
        copied = {str(key): str(value) for key, value in runner_files.items()}
        bundle_id = hashlib.sha256(json.dumps(copied, sort_keys=True).encode("utf-8")).hexdigest()
        if unsigned_runner.get("bundle_id") != bundle_id:
            raise ValueError("blind runner manifest bundle_id is invalid")
        if unsigned_runner.get("protocol_version") != BLIND_PROTOCOL_VERSION:
            raise ValueError("blind manifest protocol version is unsupported")
        return unsigned_runner
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
        repository / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/manifest.json"
    )
    analytical_manifest = json.loads(analytical_manifest_path.read_text(encoding="utf-8"))
    dataset_version = analytical_manifest.get("dataset_version")
    dataset_identity = analytical_manifest.get("dataset_identity_sha256")
    raw_outcome_contract: object = analytical_manifest.get("outcome_contract")
    if not isinstance(dataset_version, str) or not isinstance(dataset_identity, str):
        raise ValueError("analytical dataset identity is missing")
    if not isinstance(raw_outcome_contract, dict):
        raise ValueError("analytical dataset outcome contract is missing")
    outcome_contract = cast(dict[str, Any], raw_outcome_contract)
    if (
        outcome_contract.get("dataset_scope") != dataset_version
        or outcome_contract.get("version") != OUTCOME_CONTRACT_VERSION
    ):
        raise ValueError("analytical dataset does not match its attached outcome contract")

    public_payloads: dict[str, dict[str, Any]] = {
        "public/schema.json": {
            "dataset_version": dataset_version,
            "dataset_identity_sha256": dataset_identity,
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
            "dataset_version": dataset_version,
            "columns": analytical_manifest["feature_timing"],
            "excluded_post_decision_columns": analytical_manifest["excluded_post_decision_columns"],
        },
        "public/outcome_metadata.json": {
            "contract_version": OUTCOME_CONTRACT_VERSION,
            "dataset_version": dataset_version,
            "dataset_identity_sha256": dataset_identity,
            "primary_outcome_id": PRIMARY_OUTCOME_ID,
            "eligible_cohort_rule": ELIGIBLE_COHORT_RULE,
            "default_comparison_rule": DEFAULT_COMPARISON_RULE,
            "outcomes": [asdict(definition) for definition in OUTCOME_DEFINITIONS],
        },
        "public/run_config.json": {
            "blind_protocol_version": BLIND_PROTOCOL_VERSION,
            "dataset_version": dataset_version,
            "dataset_identity_sha256": dataset_identity,
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
