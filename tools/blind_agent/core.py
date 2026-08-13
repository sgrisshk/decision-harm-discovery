from __future__ import annotations

import hashlib
import json
import os
import platform
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


def prepare(repository: Path, runs_root: Path, run_id: str, allowlist: Path, seed: int) -> Path:
    validate_run_id(run_id)
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
        manifest = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "created_at": now(),
            "tool_version": __version__,
            "random_seed": seed,
            "allowed_files": copied,
            "forbidden_patterns": list(FORBIDDEN),
            "workspace_sha256": hashlib.sha256(
                json.dumps(copied, sort_keys=True).encode()
            ).hexdigest(),
        }
        _write(run_root / "manifest.json", manifest)
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
        verify(run_root, advance=True)
    except Exception:
        transition(run_root, RunState.FAILED)
        raise
    return run_root


def verify(run_root: Path, *, advance: bool = False) -> None:
    run_root = run_root.resolve()
    workspace = run_root / "workspace"
    manifest = json.loads((run_root / "manifest.json").read_text())
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
    extras = actual - set(expected) - allowed_outputs
    missing = set(expected) - actual
    if extras or missing:
        raise ValueError(
            f"workspace integrity failure: unexpected={sorted(extras)}, missing={sorted(missing)}"
        )
    for relative, digest in expected.items():
        if sha256(workspace / relative) != digest:
            raise ValueError(f"blind input hash changed: {relative}")
    if advance and _state(run_root) == RunState.PREPARED:
        transition(run_root, RunState.VERIFIED)
    else:
        _event(run_root, "verified")


def launch(
    run_root: Path,
    agent: str,
    image: str,
    execute: bool = True,
    provider_network: bool = False,
) -> list[str]:
    verify(run_root)
    if _state(run_root) != RunState.VERIFIED:
        raise ValueError("only a VERIFIED run may be launched")
    workspace = (run_root / "workspace").resolve()
    prompt = (
        "Read agents/ML_DISCOVERY_BLIND.md, execute the frozen discovery method, "
        "and write only approved output files."
    )
    inner = ["/bin/sh"] if agent == "shell" else [agent, "exec", "--full-auto", prompt]
    network = "bridge" if provider_network else "none"
    command = [
        "docker",
        "run",
        "--rm",
        "-it",
        f"--network={network}",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "-v",
        f"{workspace}:/workspace:rw",
        "-w",
        "/workspace",
        "-e",
        "HOME=/tmp",
        image,
        *inner,
    ]
    if provider_network and agent != "shell":
        credential = "PROVIDER_A_API_KEY" if agent == "external-cli" else "PROVIDER_B_API_KEY"
        if not os.environ.get(credential):
            raise ValueError(f"{credential} is required for provider-network launch")
        image_index = command.index(image)
        command[image_index:image_index] = ["-e", credential]
    if execute:
        transition(run_root, RunState.RUNNING)
        provenance_path = run_root / "provenance.json"
        provenance = json.loads(provenance_path.read_text())
        provenance["start_timestamp"] = now()
        provenance["coding_agent"] = agent
        _write(provenance_path, provenance)
        completed = subprocess.run(command, check=False)
        transition(run_root, RunState.COMPLETED if completed.returncode == 0 else RunState.FAILED)
        if completed.returncode:
            raise RuntimeError(f"blind agent exited with status {completed.returncode}")
    return command


def freeze(run_root: Path) -> Path:
    if _state(run_root) not in {RunState.RUNNING, RunState.COMPLETED}:
        raise ValueError("only RUNNING or COMPLETED output may be frozen")
    verify(run_root)
    output = run_root / "workspace/output"
    missing = [name for name in OUTPUT_FILES if not (run_root / "workspace" / name).is_file()]
    if missing:
        raise FileNotFoundError(f"required outputs missing: {missing}")
    try:
        CandidatesDocument.model_validate_json((output / "candidates.json").read_text())
        MetricsDocument.model_validate_json((output / "discovery_metrics.json").read_text())
    except ValidationError as exc:
        raise ValueError(f"invalid blind output schema: {exc}") from exc
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
