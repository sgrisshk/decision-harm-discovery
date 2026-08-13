"""Filesystem boundary and signed commitment for blind benchmark discovery."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

BLIND_PROTOCOL_VERSION = "1.0.0"
PERMITTED_FILES = (
    "pyproject.toml",
    "uv.lock",
    "packages/analytics/src/policy_analytics/__init__.py",
    "packages/analytics/src/policy_analytics/discovery/__init__.py",
    "packages/schemas/src/policy_schemas/__init__.py",
    "packages/schemas/src/policy_schemas/domain.py",
    "synthetic_data/analytical/README.md",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/features.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/outcomes.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/identifiers.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/metadata.csv",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/manifest.json",
    "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/missingness.json",
)
FORBIDDEN_NAMES = {
    "corruption_manifest.json",
    "generation_config.json",
    "hidden_ground_truth.json",
    "synthetic_benchmark.py",
    "evaluate_synthetic_benchmark.py",
    "generate_synthetic_benchmark.py",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def prepare_blind_workspace(repository: Path, destination: Path) -> dict[str, Any]:
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

    bundle_id = hashlib.sha256(_canonical_json(copied)).hexdigest()
    manifest: dict[str, Any] = {
        "protocol_version": BLIND_PROTOCOL_VERSION,
        "bundle_id": bundle_id,
        "files": copied,
    }
    (destination / "BLIND_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def validate_blind_workspace(workspace: Path) -> dict[str, Any]:
    """Fail if a workspace differs from its allowlisted manifest or contains restricted names."""
    workspace = workspace.resolve()
    manifest_path = workspace / "BLIND_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_expected_files: object = manifest.get("files")
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
    copied = {str(key): str(value) for key, value in expected_files.items()}
    if hashlib.sha256(_canonical_json(copied)).hexdigest() != manifest.get("bundle_id"):
        raise ValueError("blind manifest bundle_id is invalid")
    return manifest


def commit_candidates(
    candidates_path: Path, manifest_path: Path, receipt_path: Path, signing_key: bytes
) -> dict[str, Any]:
    """Create an evaluator-signed commitment to an immutable candidate artifact."""
    if len(signing_key) < 32:
        raise ValueError("BLIND_EVALUATION_KEY must contain at least 32 bytes")
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    if candidates.get("status") != "PERSISTED":
        raise ValueError("candidates must have status=PERSISTED before evaluator acceptance")
    bundle_id = candidates.get("blind_bundle_id")
    if not isinstance(bundle_id, str) or len(bundle_id) != 64:
        raise ValueError("candidates must include the 64-character blind_bundle_id")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol_version") != BLIND_PROTOCOL_VERSION:
        raise ValueError("blind manifest protocol version is unsupported")
    if manifest.get("bundle_id") != bundle_id:
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
    signature = hmac.new(signing_key, _canonical_json(payload), hashlib.sha256).hexdigest()
    receipt = {**payload, "signature": signature}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def verify_candidate_commitment(
    candidates_path: Path, receipt_path: Path, signing_key: bytes
) -> dict[str, Any]:
    """Verify evaluator signature and candidate bytes before hidden truth is opened."""
    if len(signing_key) < 32:
        raise ValueError("BLIND_EVALUATION_KEY must contain at least 32 bytes")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    signature = receipt.pop("signature", None)
    expected = hmac.new(signing_key, _canonical_json(receipt), hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise ValueError("candidate commitment signature is invalid")
    if receipt.get("candidate_sha256") != sha256_file(candidates_path):
        raise ValueError("candidate artifact changed after commitment")
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    if receipt.get("blind_bundle_id") != candidates.get("blind_bundle_id"):
        raise ValueError("candidate bundle does not match the signed commitment")
    return {**receipt, "signature": signature}
