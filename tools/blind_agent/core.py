from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

from pydantic import ValidationError

from . import __version__
from .models import CandidatesDocument, MetricsDocument, RunState

FORBIDDEN = (
    "ground_truth",
    "truth.yaml",
    "truth.json",
    "generator",
    "simulation_config_private",
    "corruption_manifest",
    "evaluation",
    "evaluate_discovery",
    "hidden_patterns",
    "true_effect",
    "private_benchmark",
    ".git",
)
OUTPUT_FILES = ("output/candidates.json", "output/run_report.md", "output/discovery_metrics.json")
PUBLIC_MANIFEST = "BLIND_MANIFEST.json"
SIGNATURE_DOMAIN = b"blind-agent-manifest-v1\0"
IMMUTABLE_IMAGE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
CAUSAL_LANGUAGE = re.compile(
    r"\b(causes?|drives?|proves?|reduces?|increases?)\b|\bleads? to\b|"
    r"\bwill prevent\b|\btrue harmful pattern\b",
    re.IGNORECASE,
)
TRANSITIONS = {
    RunState.CREATED: {RunState.PREPARED, RunState.FAILED},
    RunState.PREPARED: {RunState.VERIFIED, RunState.FAILED},
    RunState.VERIFIED: {RunState.RUNNING, RunState.FAILED},
    RunState.RUNNING: {RunState.COMPLETED, RunState.FAILED},
    RunState.COMPLETED: {RunState.FROZEN, RunState.FAILED},
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def create_signing_key(key_file: Path, repository: Path, runs_root: Path) -> Path:
    """Create an evaluator-owned key outside both the checkout and issued run tree."""
    key_file = key_file.resolve()
    repository, runs_root = repository.resolve(), runs_root.resolve()
    if (
        key_file in (repository, runs_root)
        or repository in key_file.parents
        or runs_root in key_file.parents
    ):
        raise ValueError("signing key must be outside the repository and blind runs root")
    key_file.parent.mkdir(mode=stat.S_IRWXU, parents=True, exist_ok=True)
    key_file.parent.chmod(stat.S_IRWXU)
    descriptor = os.open(
        key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR
    )
    try:
        os.write(descriptor, os.urandom(32).hex().encode("ascii") + b"\n")
    finally:
        os.close(descriptor)
    return key_file


def load_signing_key(key_file: Path, repository: Path, runs_root: Path) -> bytes:
    key_file = key_file.resolve()
    repository, runs_root = repository.resolve(), runs_root.resolve()
    if (
        key_file in (repository, runs_root)
        or repository in key_file.parents
        or runs_root in key_file.parents
    ):
        raise ValueError("signing key must be outside the repository and blind runs root")
    if key_file.is_symlink() or not key_file.is_file():
        raise ValueError("signing key must be a regular non-symlink file")
    key_stat = key_file.stat()
    if key_stat.st_uid != os.getuid() or stat.S_IMODE(key_stat.st_mode) != 0o600:
        raise ValueError("signing key must be owned by the evaluator identity with mode 0600")
    try:
        key = bytes.fromhex(key_file.read_text(encoding="ascii").strip())
    except ValueError as exc:
        raise ValueError("signing key must be hex-encoded") from exc
    if len(key) < 32:
        raise ValueError("signing key must contain at least 32 bytes")
    return key


def _sign_manifest(unsigned: dict[str, Any], signing_key: bytes) -> str:
    message = SIGNATURE_DOMAIN + _canonical_json(unsigned)
    return hmac.new(signing_key, message, hashlib.sha256).hexdigest()


def _verify_manifest_signature(manifest: dict[str, Any], signing_key: bytes) -> None:
    signature = manifest.get("evaluator_signature")
    unsigned = {key: value for key, value in manifest.items() if key != "evaluator_signature"}
    expected = _sign_manifest(unsigned, signing_key)
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise ValueError("blind manifest evaluator signature is invalid")


def validate_run_id(run_id: str) -> None:
    if not run_id or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id
    ):
        raise ValueError("run_id may contain only letters, digits, '-' and '_'")


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe allowlist path: {value}")
    lowered = path.as_posix().lower()
    if any(term in lowered for term in FORBIDDEN) or any(
        part.startswith(".") for part in path.parts
    ):
        raise ValueError(f"forbidden allowlist path: {value}")
    return path


def load_allowlist(path: Path) -> list[str]:
    # JSON is a strict YAML subset, avoiding a YAML runtime dependency.
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    allowed = payload.get("allowed")
    if not isinstance(allowed, list):
        raise ValueError("allowlist must contain a string list named 'allowed'")
    values = cast(list[object], allowed)
    if not all(isinstance(item, str) for item in values):
        raise ValueError("allowlist must contain a string list named 'allowed'")
    return cast(list[str], values)


def _paths(repository: Path, patterns: list[str]) -> list[tuple[Path, Path]]:
    selected: dict[str, tuple[Path, Path]] = {}
    for pattern in patterns:
        safe_relative(pattern)
        matches = list(repository.glob(pattern))
        if not matches:
            raise FileNotFoundError(f"allowlisted source is missing: {pattern}")
        for source in matches:
            relative = source.relative_to(repository)
            safe_relative(relative.as_posix())
            if source.is_symlink() or not source.is_file():
                raise ValueError(
                    f"allowlisted artifact must be a regular non-symlink file: {relative}"
                )
            selected[relative.as_posix()] = (source, relative)
    return [selected[key] for key in sorted(selected)]


def _acceptance_contract(repository: Path) -> dict[str, Any] | None:
    analytical_manifest_path = (
        repository / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/manifest.json"
    )
    split_manifest_path = (
        repository
        / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0/split_manifest.json"
    )
    if not analytical_manifest_path.is_file() or not split_manifest_path.is_file():
        return None
    analytical = cast(
        dict[str, Any], json.loads(analytical_manifest_path.read_text(encoding="utf-8"))
    )
    split = cast(dict[str, Any], json.loads(split_manifest_path.read_text(encoding="utf-8")))
    timing = cast(dict[str, dict[str, Any]], analytical["feature_timing"])
    outcome_definitions = cast(list[dict[str, Any]], analytical["outcome_contract"]["definitions"])
    primary_outcome_id = analytical["outcome_contract"]["primary_outcome_id"]
    primary_outcome_metadata = next(
        definition
        for definition in outcome_definitions
        if definition["outcome_id"] == primary_outcome_id
    )
    engine_source = (
        repository / "packages/analytics/src/policy_analytics/discovery/engine.py"
    ).read_text(encoding="utf-8")
    method_match = re.search(r'^DISCOVERY_METHOD_VERSION = "([^"]+)"$', engine_source, re.MULTILINE)
    if method_match is None:
        raise ValueError("discovery implementation does not declare DISCOVERY_METHOD_VERSION")
    contract_version = analytical["outcome_contract"]["version"]
    return {
        "output_schema_version": "1.1.0",
        "run_contract_version": "blind-run-contract-v1.1.0",
        "dataset_version": analytical["dataset_version"],
        "dataset_identity_sha256": analytical["dataset_identity_sha256"],
        "outcome_contract_version": analytical["outcome_contract"]["version"],
        "discovery_contract_version": contract_version,
        "discovery_method_version": method_match.group(1),
        "primary_outcome": primary_outcome_id,
        "primary_outcome_metadata": primary_outcome_metadata,
        "search_fit_split": split["discovery_usage"]["search_fit_split"],
        "diagnostic_only_splits": split["discovery_usage"]["diagnostic_only_splits"],
        "feature_timing_classes": {
            name: metadata["classification"] for name, metadata in sorted(timing.items())
        },
    }


def _verify_source_snapshot(repository: Path, allowlist: Path, expected: dict[str, str]) -> None:
    current = {
        relative.as_posix(): sha256(source)
        for source, relative in _paths(repository.resolve(), load_allowlist(allowlist))
    }
    if current != expected:
        changed = sorted(
            path for path in set(current) | set(expected) if current.get(path) != expected.get(path)
        )
        raise ValueError(f"issued workspace source drift detected: {changed}")


def resolve_image(image: str) -> dict[str, str]:
    if not IMMUTABLE_IMAGE.fullmatch(image):
        raise ValueError("blind launch requires an immutable image reference name@sha256:<digest>")
    inspected = subprocess.run(
        ["docker", "image", "inspect", image], capture_output=True, check=False, text=True
    )
    if inspected.returncode:
        raise ValueError(f"blind agent image is unavailable: {image}")
    payload = cast(list[dict[str, Any]], json.loads(inspected.stdout))
    if len(payload) != 1:
        raise ValueError("docker image inspection returned an unexpected result")
    image_id = str(payload[0].get("Id", ""))
    repo_digests = cast(list[str], payload[0].get("RepoDigests") or [])
    requested_digest = image.rsplit("@", 1)[1]
    if not image_id.endswith(requested_digest) and image not in repo_digests:
        raise ValueError("resolved image does not match the requested immutable digest")
    return {
        "requested_reference": image,
        "resolved_image_id": image_id,
        "resolved_repo_digest": image if image in repo_digests else requested_digest,
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _event(run_root: Path, event: str, **details: Any) -> None:
    record = {"event": event, "timestamp": now(), **details}
    with (run_root / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _state(run_root: Path) -> RunState:
    return RunState(json.loads((run_root / "state.json").read_text())["state"])


def transition(run_root: Path, target: RunState) -> None:
    current = _state(run_root)
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid run-state transition: {current} -> {target}")
    _write(run_root / "state.json", {"state": target, "updated_at": now()})
    _event(run_root, target.value.lower())


def prepare(
    repository: Path,
    runs_root: Path,
    run_id: str,
    allowlist: Path,
    seed: int,
    signing_key: bytes,
    runtime_image: dict[str, str],
    runtime_agent: str = "deterministic",
    runtime_model: str | None = None,
) -> Path:
    validate_run_id(run_id)
    if not IMMUTABLE_IMAGE.fullmatch(runtime_image.get("requested_reference", "")):
        raise ValueError("issuance requires immutable resolved image provenance")
    if runtime_agent not in {"deterministic", "shell"}:
        raise ValueError("unsupported blind runtime agent")
    if runtime_agent == "deterministic" and runtime_model is not None:
        raise ValueError("deterministic issuance does not accept a provider model")
    repository, runs_root = repository.resolve(), runs_root.resolve()
    if runs_root == repository or repository in runs_root.parents:
        raise ValueError("blind runs root must be outside the repository checkout")
    run_root = runs_root / run_id
    if run_root.exists():
        raise FileExistsError(f"run already exists and cannot be reused: {run_root}")
    workspace = run_root / "workspace"
    workspace.mkdir(parents=True)
    _write(run_root / "state.json", {"state": RunState.CREATED, "updated_at": now()})
    _event(run_root, "created")
    copied: dict[str, str] = {}
    try:
        for source, relative in _paths(repository, load_allowlist(allowlist)):
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)
            copied[relative.as_posix()] = sha256(target)
        (workspace / "output").mkdir()
        workspace_sha256 = hashlib.sha256(json.dumps(copied, sort_keys=True).encode()).hexdigest()
        unsigned_manifest = {
            "schema_version": "1.0.0",
            "protocol_version": "1.0.0",
            "run_id": run_id,
            "created_at": now(),
            "tool_version": __version__,
            "random_seed": seed,
            "allowed_files": copied,
            "forbidden_patterns": list(FORBIDDEN),
            "workspace_sha256": workspace_sha256,
            "bundle_id": workspace_sha256,
            "allowlist_sha256": sha256(allowlist),
            "acceptance_contract": _acceptance_contract(repository),
            "runtime_image": runtime_image,
            "runtime_agent": runtime_agent,
            "runtime_model": runtime_model,
        }
        manifest = {
            **unsigned_manifest,
            "evaluator_signature": _sign_manifest(unsigned_manifest, signing_key),
        }
        _write(run_root / "manifest.json", manifest)
        _write(workspace / PUBLIC_MANIFEST, manifest)
        _write(
            run_root / "provenance.json",
            {
                "run_id": run_id,
                "creation_timestamp": manifest["created_at"],
                "tool_version": __version__,
                "source_artifact_hashes": copied,
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "random_seed": seed,
                "exact_command": " ".join(sys.argv),
                "start_timestamp": None,
                "finish_timestamp": None,
                "output_hashes": {},
            },
        )
        transition(run_root, RunState.PREPARED)
        verify(
            run_root,
            signing_key,
            repository=repository,
            allowlist=allowlist,
            check_source=True,
            advance=True,
        )
    except Exception:
        transition(run_root, RunState.FAILED)
        raise
    return run_root


def verify(
    run_root: Path,
    signing_key: bytes,
    *,
    repository: Path | None = None,
    allowlist: Path | None = None,
    check_source: bool = False,
    advance: bool = False,
) -> None:
    run_root = run_root.resolve()
    if not run_root.is_dir():
        raise FileNotFoundError(f"blind run does not exist: {run_root}")
    state_path = run_root / "state.json"
    if not state_path.is_file():
        raise ValueError(f"blind run has no state record and is invalid: {run_root}")
    if _state(run_root) == RunState.FAILED:
        raise ValueError(
            f"blind run is FAILED and cannot be verified or reused: {run_root}; use a new run ID"
        )
    manifest_path = run_root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"blind run has no issued manifest and is invalid: {run_root}")
    workspace = run_root / "workspace"
    manifest = json.loads(manifest_path.read_text())
    public_manifest_path = workspace / PUBLIC_MANIFEST
    if public_manifest_path.is_symlink() or not public_manifest_path.is_file():
        raise ValueError("signed public blind manifest is missing or is a symlink")
    public_manifest = json.loads(public_manifest_path.read_text(encoding="utf-8"))
    if public_manifest != manifest:
        raise ValueError("public blind manifest differs from evaluator run manifest")
    _verify_manifest_signature(manifest, signing_key)
    expected: dict[str, str] = manifest["allowed_files"]
    actual: set[str] = set()
    for path in workspace.rglob("*"):
        relative = path.relative_to(workspace).as_posix()
        if path.is_symlink():
            raise ValueError(f"symlink in blind workspace: {relative}")
        if any(part.startswith(".") for part in Path(relative).parts) or any(
            x in relative.lower() for x in FORBIDDEN
        ):
            raise ValueError(f"forbidden path in blind workspace: {relative}")
        if path.is_file():
            actual.add(relative)
    allowed_outputs = {name for name in OUTPUT_FILES if (workspace / name).is_file()}
    extras = actual - set(expected) - allowed_outputs - {PUBLIC_MANIFEST}
    missing = set(expected) - actual
    if extras or missing:
        raise ValueError(
            f"workspace integrity failure: unexpected={sorted(extras)}, missing={sorted(missing)}"
        )
    for relative, digest in expected.items():
        if sha256(workspace / relative) != digest:
            raise ValueError(f"blind input hash changed: {relative}")
    if check_source:
        if repository is None or allowlist is None:
            raise ValueError("source verification requires repository and allowlist")
        if sha256(allowlist) != manifest.get("allowlist_sha256"):
            raise ValueError("issued workspace allowlist source drift detected")
        _verify_source_snapshot(repository, allowlist, expected)
    if advance and _state(run_root) == RunState.PREPARED:
        transition(run_root, RunState.VERIFIED)
    else:
        _event(run_root, "verified")


def launch(
    run_root: Path,
    signing_key: bytes,
    agent: str,
    image: str,
    model: str | None = None,
    execute: bool = True,
    provider_network: bool = False,
    repository: Path | None = None,
    allowlist: Path | None = None,
) -> list[str]:
    if not IMMUTABLE_IMAGE.fullmatch(image):
        raise ValueError("blind launch requires an immutable image reference name@sha256:<digest>")
    verify(
        run_root,
        signing_key,
        repository=repository,
        allowlist=allowlist,
        check_source=True,
    )
    if _state(run_root) != RunState.VERIFIED:
        raise ValueError("only a VERIFIED run may be launched")
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    if image != manifest.get("runtime_image", {}).get("requested_reference"):
        raise ValueError("launch image reference does not match the signed issued runtime")
    if agent != manifest.get("runtime_agent"):
        raise ValueError("launch agent does not match the signed issued runtime")
    if model != manifest.get("runtime_model"):
        raise ValueError("launch model does not match the signed issued runtime")
    workspace = (run_root / "workspace").resolve()
    if provider_network:
        raise ValueError("deterministic blind launch forbids provider network")
    inner = (
        ["/bin/sh"]
        if agent == "shell"
        else ["python", "/workspace/scripts/run_discovery.py"]
    )
    network = "none"
    command = [
        "docker",
        "run",
        "--rm",
        f"--network={network}",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "-v",
        f"{workspace}:/workspace:ro",
        "-v",
        f"{workspace / 'output'}:/workspace/output:rw",
        "-w",
        "/workspace",
        "-e",
        "HOME=/tmp",
        image,
        *inner,
    ]
    if execute:
        image_provenance = resolve_image(image)
        if image_provenance != manifest.get("runtime_image"):
            raise ValueError("launch image does not match the signed issued runtime")
        provenance_path = run_root / "provenance.json"
        provenance = json.loads(provenance_path.read_text())
        provenance["start_timestamp"] = now()
        provenance["coding_agent"] = agent
        provenance["image"] = image_provenance
        _write(provenance_path, provenance)
        transition(run_root, RunState.RUNNING)
        completed = subprocess.run(command, check=False)
        transition(run_root, RunState.COMPLETED if completed.returncode == 0 else RunState.FAILED)
        if completed.returncode:
            raise RuntimeError(f"blind agent exited with status {completed.returncode}")
    return command


def _validated_freeze(run_root: Path, signing_key: bytes) -> Path:
    if _state(run_root) not in {RunState.RUNNING, RunState.COMPLETED}:
        raise ValueError("only RUNNING or COMPLETED output may be frozen")
    verify(run_root, signing_key)
    output = run_root / "workspace/output"
    missing = [name for name in OUTPUT_FILES if not (run_root / "workspace" / name).is_file()]
    if missing:
        raise FileNotFoundError(f"required outputs missing: {missing}")
    try:
        candidates = CandidatesDocument.model_validate_json(
            (output / "candidates.json").read_text()
        )
        metrics = MetricsDocument.model_validate_json(
            (output / "discovery_metrics.json").read_text()
        )
    except ValidationError as exc:
        raise ValueError(f"invalid blind output schema: {exc}") from exc
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    raw_contract: object = manifest.get("acceptance_contract")
    if not isinstance(raw_contract, dict):
        raise ValueError("issued run has no frozen output acceptance contract")
    contract = cast(dict[str, Any], raw_contract)
    if candidates.run_id != manifest["run_id"] or metrics.run_id != manifest["run_id"]:
        raise ValueError("blind output run_id does not match the issued run")
    if candidates.blind_bundle_id != manifest["bundle_id"]:
        raise ValueError("blind output bundle does not match the issued manifest")
    if metrics.random_seed != manifest["random_seed"]:
        raise ValueError("blind output random seed does not match the issued run")
    expected_candidate_fields: dict[str, Any] = {
        "schema_version": contract["output_schema_version"],
        "run_contract_version": contract["run_contract_version"],
        "dataset_version": contract["dataset_version"],
        "dataset_identity_sha256": contract["dataset_identity_sha256"],
        "outcome_contract_version": contract["outcome_contract_version"],
        "discovery_contract_version": contract["discovery_contract_version"],
        "discovery_method_version": contract["discovery_method_version"],
        "search_fit_split": contract["search_fit_split"],
        "diagnostic_only_splits": contract["diagnostic_only_splits"],
        "selection_used_only_fit_split": True,
        "input_provenance_hashes": manifest["allowed_files"],
        "feature_timing_classes": contract["feature_timing_classes"],
    }
    candidate_payload = candidates.model_dump()
    mismatched = sorted(
        key
        for key, expected_value in expected_candidate_fields.items()
        if candidate_payload.get(key) != expected_value
    )
    if mismatched:
        raise ValueError(f"blind output contract mismatch: {mismatched}")
    expected_metric_fields: dict[str, Any] = {
        "schema_version": contract["output_schema_version"],
        "run_contract_version": contract["run_contract_version"],
        "dataset_identity_sha256": contract["dataset_identity_sha256"],
        "discovery_method_version": contract["discovery_method_version"],
        "search_fit_split": contract["search_fit_split"],
        "selection_used_only_fit_split": True,
    }
    metrics_payload = metrics.model_dump()
    metric_mismatches = sorted(
        key
        for key, expected_value in expected_metric_fields.items()
        if metrics_payload.get(key) != expected_value
    )
    if metric_mismatches:
        raise ValueError(f"blind metrics contract mismatch: {metric_mismatches}")
    timing = cast(dict[str, str], contract["feature_timing_classes"])
    for candidate in candidates.candidates:
        if candidate.outcome != contract["primary_outcome"]:
            raise ValueError(f"candidate {candidate.candidate_id} uses an unapproved outcome")
        if candidate.discovery_method != contract["discovery_method_version"]:
            raise ValueError(f"candidate {candidate.candidate_id} uses an unapproved method")
        for condition in candidate.conditions:
            if timing.get(condition.feature) != "DECISION_TIME":
                raise ValueError(
                    f"candidate {candidate.candidate_id} uses non-decision-time feature "
                    f"{condition.feature}"
                )
    report = (output / "run_report.md").read_text(encoding="utf-8")
    language = json.dumps(candidate_payload, sort_keys=True) + "\n" + report
    prohibited = CAUSAL_LANGUAGE.search(language)
    if prohibited:
        raise ValueError(f"unsupported causal language in blind output: {prohibited.group(0)}")
    hashes = {path.name: sha256(path) for path in output.iterdir() if path.is_file()}
    frozen = run_root / "frozen"
    frozen.mkdir()
    for path in output.iterdir():
        if path.is_file():
            target = frozen / path.name
            shutil.copy2(path, target)
            target.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    _write(frozen / "hashes.json", hashes)
    provenance_path = run_root / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance.update({"finish_timestamp": now(), "output_hashes": hashes})
    _write(provenance_path, provenance)
    if _state(run_root) == RunState.RUNNING:
        transition(run_root, RunState.COMPLETED)
    transition(run_root, RunState.FROZEN)
    return frozen


def freeze(run_root: Path, signing_key: bytes) -> Path:
    if _state(run_root) not in {RunState.RUNNING, RunState.COMPLETED}:
        raise ValueError("only RUNNING or COMPLETED output may be frozen")
    try:
        return _validated_freeze(run_root, signing_key)
    except Exception:
        if _state(run_root) in {RunState.RUNNING, RunState.COMPLETED}:
            transition(run_root, RunState.FAILED)
        raise
