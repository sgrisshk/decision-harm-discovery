from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.blind_agent.core import freeze, launch, prepare, safe_relative, transition, verify
from tools.blind_agent.models import RunState


def fixture_repo(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "input.txt").write_text("public", encoding="utf-8")
    allowlist = repository / "allowlist.json"
    allowlist.write_text(json.dumps({"allowed": ["input.txt"]}), encoding="utf-8")
    return repository, allowlist


def test_prepare_copies_only_allowlist_and_is_verified(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    (repository / "secret.txt").write_text("private", encoding="utf-8")
    run = prepare(repository, tmp_path / "runs", "run-001", allowlist, 7)
    assert (run / "workspace/input.txt").read_text() == "public"
    assert not (run / "workspace/secret.txt").exists()
    assert json.loads((run / "state.json").read_text())["state"] == "VERIFIED"
    verify(run)


@pytest.mark.parametrize(
    "path", ["../../ground_truth.yaml", "/tmp/public.csv", ".git/config", "generator/code.py"]
)
def test_unsafe_allowlist_paths_are_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        safe_relative(path)


def test_prepare_rejects_missing_and_symlink(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    allowlist.write_text(json.dumps({"allowed": ["missing.txt"]}))
    with pytest.raises(FileNotFoundError):
        prepare(repository, tmp_path / "runs-a", "missing", allowlist, 1)
    allowlist.write_text(json.dumps({"allowed": ["link.txt"]}))
    (repository / "link.txt").symlink_to(repository / "input.txt")
    with pytest.raises(ValueError, match="symlink"):
        prepare(repository, tmp_path / "runs-b", "link", allowlist, 1)


def test_verify_detects_extra_changed_deleted_hidden_and_git(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    for index, (name, content) in enumerate(
        (("extra.txt", "x"), ("input.txt", "changed"), (".private", "x"), (".git/config", "x"))
    ):
        run = prepare(repository, tmp_path / f"runs-{index}", f"run-{index}", allowlist, 1)
        target = run / "workspace" / name
        target.parent.mkdir(exist_ok=True)
        target.write_text(content)
        with pytest.raises(ValueError):
            verify(run)
    run = prepare(repository, tmp_path / "runs-delete", "delete", allowlist, 1)
    (run / "workspace/input.txt").unlink()
    with pytest.raises(ValueError, match="missing"):
        verify(run)


def test_freeze_validates_and_closes_run(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(repository, tmp_path / "runs", "run-001", allowlist, 1)
    command = launch(run, "external-cli", "test-image", execute=False)
    assert command[0:2] == ["docker", "run"]
    transition(run, RunState.RUNNING)
    output = run / "workspace/output"
    (output / "candidates.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "run_id": "run-001",
                "candidates": [
                    {
                        "candidate_id": "C001",
                        "conditions": [],
                        "outcome": "margin",
                        "sample_size": 4,
                        "support": 0.2,
                        "raw_effect": -1.0,
                        "economic_exposure": -4.0,
                        "discovery_method": "test",
                        "warnings": [],
                    }
                ],
            }
        )
    )
    (output / "discovery_metrics.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "run_id": "run-001",
                "evaluated_hypotheses": 1,
                "random_seed": 1,
            }
        )
    )
    (output / "run_report.md").write_text("done")
    frozen = freeze(run)
    assert (frozen / "hashes.json").is_file()
    assert json.loads((run / "state.json").read_text())["state"] == "FROZEN"
    with pytest.raises(ValueError, match="FROZEN"):
        transition(run, RunState.RUNNING)


def test_malformed_candidates_are_rejected(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(repository, tmp_path / "runs", "bad", allowlist, 1)
    transition(run, RunState.RUNNING)
    output = run / "workspace/output"
    (output / "candidates.json").write_text("{}")
    (output / "discovery_metrics.json").write_text("{}")
    (output / "run_report.md").write_text("bad")
    with pytest.raises(ValueError, match="schema"):
        freeze(run)
