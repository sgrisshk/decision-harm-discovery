from __future__ import annotations

import json
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from policy_analytics.blind_isolation import commit_candidates

from tools.blind_agent.core import (
    create_signing_key,
    freeze,
    launch,
    load_signing_key,
    prepare,
    safe_relative,
    sha256,
    transition,
    verify,
)
from tools.blind_agent.models import RunState

SIGNING_KEY = b"test-evaluator-owned-signing-key!"
TEST_IMAGE = "test-image@sha256:" + "a" * 64
TEST_RUNTIME = {
    "requested_reference": TEST_IMAGE,
    "resolved_image_id": "sha256:" + "a" * 64,
    "resolved_repo_digest": TEST_IMAGE,
}


def fixture_repo(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "input.txt").write_text("public", encoding="utf-8")
    allowlist = repository / "allowlist.json"
    dataset = repository / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
    dataset.mkdir(parents=True)
    allowlist.write_text(
        json.dumps(
            {
                "allowed": ["input.txt"],
                "datasets": {
                    "travel": ("synthetic_data/analytical/travel-bookings-analytical-v1.1.0")
                },
            }
        ),
        encoding="utf-8",
    )
    for name in (
        "features.csv",
        "outcomes.csv",
        "identifiers.csv",
        "metadata.csv",
        "split_membership.csv",
    ):
        (dataset / name).write_text("column\n", encoding="utf-8")
    (dataset / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_version": "test-dataset-v1",
                "dataset_identity_sha256": "d" * 64,
                "outcome_contract": {
                    "dataset_scope": "test-dataset-v1",
                    "version": "1.1.0",
                    "primary_outcome_id": "margin",
                    "definitions": [
                        {
                            "outcome_id": "margin",
                            "column": "margin",
                            "unit": "EUR",
                            "higher_is_worse": False,
                        }
                    ],
                },
                "feature_timing": {
                    "feature_a": {"classification": "DECISION_TIME"},
                    "outcome_a": {"classification": "OUTCOME"},
                },
                "partitions": {
                    role: {"path": f"{role}.csv", "sha256": sha256(dataset / f"{role}.csv")}
                    for role in ("features", "outcomes", "identifiers", "metadata")
                },
            }
        )
    )
    (dataset / "split_manifest.json").write_text(
        json.dumps(
            {
                "analytical_dataset_version": "test-dataset-v1",
                "analytical_dataset_identity_sha256": "d" * 64,
                "split_config_version": "travel-bookings-temporal-split-v1.0.0",
                "membership_artifact": {
                    "path": "split_membership.csv",
                    "sha256": sha256(dataset / "split_membership.csv"),
                },
                "discovery_usage": {
                    "search_fit_split": "development",
                    "diagnostic_only_splits": ["validation", "future_holdout"],
                },
            }
        )
    )
    engine = repository / "packages/analytics/src/policy_analytics/discovery/engine.py"
    engine.parent.mkdir(parents=True)
    engine.write_text('DISCOVERY_METHOD_VERSION = "discovery-engine-v0.1.0"\n')
    return repository, allowlist


def set_allowed(allowlist: Path, allowed: list[str]) -> None:
    payload = json.loads(allowlist.read_text(encoding="utf-8"))
    payload["allowed"] = allowed
    allowlist.write_text(json.dumps(payload), encoding="utf-8")


def write_valid_outputs(run: Path) -> None:
    manifest = json.loads((run / "workspace/BLIND_MANIFEST.json").read_text())
    contract = manifest["acceptance_contract"]
    candidates = [
        {
            "candidate_id": f"C{index:03d}",
            "conditions": [{"feature": "feature_a", "operator": "eq", "value": str(index)}],
            "outcome": "margin",
            "sample_size": 4,
            "support": 0.2,
            "raw_effect": -1.0,
            "economic_exposure": -4.0,
            "discovery_method": contract["discovery_method_version"],
            "description": "associated with lower margin",
            "warnings": ["awaiting statistical validation"],
        }
        for index in range(10)
    ]
    output = run / "workspace/output"
    (output / "candidates.json").write_text(
        json.dumps(
            {
                "schema_version": contract["output_schema_version"],
                "run_id": manifest["run_id"],
                "status": "PERSISTED",
                "blind_bundle_id": manifest["bundle_id"],
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
                "candidates": candidates,
            }
        )
    )
    (output / "discovery_metrics.json").write_text(
        json.dumps(
            {
                "schema_version": contract["output_schema_version"],
                "run_id": manifest["run_id"],
                "evaluated_hypotheses": 10,
                "random_seed": manifest["random_seed"],
                "run_contract_version": contract["run_contract_version"],
                "dataset_identity_sha256": contract["dataset_identity_sha256"],
                "discovery_method_version": contract["discovery_method_version"],
                "search_fit_split": contract["search_fit_split"],
                "selection_used_only_fit_split": True,
            }
        )
    )
    (output / "run_report.md").write_text("Observed candidate associations.")


def test_prepare_copies_only_allowlist_and_is_verified(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    (repository / "secret.txt").write_text("private", encoding="utf-8")
    run = prepare(
        repository,
        tmp_path / "runs",
        "run-001",
        allowlist,
        7,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )
    assert (run / "workspace/input.txt").read_text() == "public"
    assert not (run / "workspace/secret.txt").exists()
    assert json.loads((run / "state.json").read_text())["state"] == "VERIFIED"
    verify(run, SIGNING_KEY)
    assert json.loads((run / "workspace/BLIND_MANIFEST.json").read_text())["evaluator_signature"]


def test_domain_selector_signs_and_copies_only_selected_public_dataset(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    travel = repository / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
    b2b_relative = Path("synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0")
    b2b = repository / b2b_relative
    shutil.copytree(travel, b2b)
    analytical = json.loads((b2b / "manifest.json").read_text(encoding="utf-8"))
    analytical["dataset_version"] = "b2b-sales-analytical-v1.0.0"
    analytical["dataset_identity_sha256"] = "b" * 64
    analytical["outcome_contract"]["dataset_scope"] = "b2b-sales-analytical-v1.0.0"
    analytical["outcome_contract"]["primary_outcome_id"] = "gross_margin"
    analytical["outcome_contract"]["definitions"][0]["outcome_id"] = "gross_margin"
    analytical["outcome_contract"]["definitions"][0]["column"] = "gross_margin"
    (b2b / "manifest.json").write_text(json.dumps(analytical), encoding="utf-8")
    split = json.loads((b2b / "split_manifest.json").read_text(encoding="utf-8"))
    split["analytical_dataset_version"] = "b2b-sales-analytical-v1.0.0"
    split["analytical_dataset_identity_sha256"] = "b" * 64
    (b2b / "split_manifest.json").write_text(json.dumps(split), encoding="utf-8")
    (b2b.parent / "generator.py").write_text("private", encoding="utf-8")
    (b2b.parent / "hidden_ground_truth.json").write_text("private", encoding="utf-8")
    payload = json.loads(allowlist.read_text(encoding="utf-8"))
    payload["datasets"]["b2b_sales/comparable"] = b2b_relative.as_posix()
    allowlist.write_text(json.dumps(payload), encoding="utf-8")

    run = prepare(
        repository,
        tmp_path / "runs",
        "b2b-run",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
        "b2b_sales/comparable",
    )
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    contract = manifest["acceptance_contract"]
    assert manifest["dataset_selector"] == "b2b_sales/comparable"
    assert contract["dataset_selector"] == "b2b_sales/comparable"
    assert contract["analytical_dataset_root"] == b2b_relative.as_posix()
    assert contract["dataset_identity_sha256"] == "b" * 64
    assert contract["primary_outcome_metadata"]["outcome_id"] == "gross_margin"
    assert contract["temporal_split_contract_version"] == "travel-bookings-temporal-split-v1.0.0"
    selected_prefix = f"{b2b_relative.as_posix()}/"
    assert {path for path in manifest["allowed_files"] if path.startswith(selected_prefix)} == {
        f"{selected_prefix}{name}"
        for name in (
            "features.csv",
            "outcomes.csv",
            "identifiers.csv",
            "metadata.csv",
            "split_manifest.json",
            "split_membership.csv",
        )
    }
    assert not any("travel-bookings" in path for path in manifest["allowed_files"])
    assert not any(
        "generator" in path or "ground_truth" in path for path in manifest["allowed_files"]
    )
    with pytest.raises(ValueError, match="dataset selector"):
        verify(run, SIGNING_KEY, dataset_selector="travel")


def test_prepare_rejects_unknown_dataset_or_missing_split_contract(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    with pytest.raises(ValueError, match="unknown blind dataset selector"):
        prepare(
            repository,
            tmp_path / "runs-unknown",
            "unknown",
            allowlist,
            1,
            SIGNING_KEY,
            TEST_RUNTIME,
            dataset_selector="unknown",
        )
    (
        repository
        / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/split_manifest.json"
    ).unlink()
    with pytest.raises((FileNotFoundError, ValueError), match="split_manifest"):
        prepare(
            repository,
            tmp_path / "runs-missing-split",
            "missing-split",
            allowlist,
            1,
            SIGNING_KEY,
            TEST_RUNTIME,
            dataset_selector="travel",
        )


def test_prepare_rejects_missing_analytical_manifest(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    (
        repository / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/manifest.json"
    ).unlink()
    with pytest.raises(ValueError, match="missing its analytical"):
        prepare(
            repository,
            tmp_path / "runs",
            "missing-manifest",
            allowlist,
            1,
            SIGNING_KEY,
            TEST_RUNTIME,
            dataset_selector="travel",
        )


@pytest.mark.parametrize(
    "field", ["analytical_dataset_identity_sha256", "analytical_dataset_version"]
)
def test_prepare_rejects_temporal_split_dataset_binding_mismatch(
    tmp_path: Path, field: str
) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    split_path = (
        repository
        / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/split_manifest.json"
    )
    split = json.loads(split_path.read_text(encoding="utf-8"))
    split[field] = "0" * 64 if field.endswith("sha256") else "another-dataset-version"
    split_path.write_text(json.dumps(split), encoding="utf-8")
    with pytest.raises(ValueError, match="temporal split dataset"):
        prepare(
            repository,
            tmp_path / "runs",
            f"mismatch-{field}",
            allowlist,
            1,
            SIGNING_KEY,
            TEST_RUNTIME,
            dataset_selector="travel",
        )


def test_prepare_rejects_declared_partition_hash_mismatch(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    manifest_path = (
        repository / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["partitions"]["features"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="features partition hash mismatch"):
        prepare(
            repository,
            tmp_path / "runs",
            "partition-hash-mismatch",
            allowlist,
            1,
            SIGNING_KEY,
            TEST_RUNTIME,
            dataset_selector="travel",
        )


@pytest.mark.parametrize(
    "path", ["../../ground_truth.yaml", "/tmp/public.csv", ".git/config", "generator/code.py"]
)
def test_unsafe_allowlist_paths_are_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        safe_relative(path)


def test_prepare_rejects_missing_and_symlink(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    set_allowed(allowlist, ["missing.txt"])
    with pytest.raises(FileNotFoundError):
        prepare(
            repository,
            tmp_path / "runs-a",
            "missing",
            allowlist,
            1,
            SIGNING_KEY,
            TEST_RUNTIME,
            "deterministic",
            None,
        )
    set_allowed(allowlist, ["link.txt"])
    (repository / "link.txt").symlink_to(repository / "input.txt")
    with pytest.raises(ValueError, match="symlink"):
        prepare(
            repository,
            tmp_path / "runs-b",
            "link",
            allowlist,
            1,
            SIGNING_KEY,
            TEST_RUNTIME,
            "deterministic",
            None,
        )


def test_verify_detects_extra_changed_deleted_hidden_and_git(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    for index, (name, content) in enumerate(
        (("extra.txt", "x"), ("input.txt", "changed"), (".private", "x"), (".git/config", "x"))
    ):
        run = prepare(
            repository,
            tmp_path / f"runs-{index}",
            f"run-{index}",
            allowlist,
            1,
            SIGNING_KEY,
            TEST_RUNTIME,
            "deterministic",
            None,
        )
        target = run / "workspace" / name
        target.parent.mkdir(exist_ok=True)
        target.write_text(content)
        with pytest.raises(ValueError):
            verify(run, SIGNING_KEY)
    run = prepare(
        repository,
        tmp_path / "runs-delete",
        "delete",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )
    (run / "workspace/input.txt").unlink()
    with pytest.raises(ValueError, match="missing"):
        verify(run, SIGNING_KEY)


def test_freeze_validates_and_closes_run(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(
        repository,
        tmp_path / "runs",
        "run-001",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )
    command = launch(
        run,
        SIGNING_KEY,
        "deterministic",
        TEST_IMAGE,
        model=None,
        execute=False,
        repository=repository,
        allowlist=allowlist,
        dataset_selector="travel",
    )
    assert command[0:2] == ["docker", "run"]
    assert "--full-auto" not in command
    assert "/workspace/scripts/run_discovery.py" in command
    assert "--network=none" in command
    mounts = [command[index + 1] for index, item in enumerate(command) if item == "-v"]
    assert mounts == [
        f"{(run / 'workspace').resolve()}:/workspace:ro",
        f"{(run / 'workspace/output').resolve()}:/workspace/output:rw",
    ]
    transition(run, RunState.RUNNING)
    write_valid_outputs(run)
    frozen = freeze(run, SIGNING_KEY)
    assert (frozen / "hashes.json").is_file()
    assert json.loads((run / "state.json").read_text())["state"] == "FROZEN"
    with pytest.raises(ValueError, match="FROZEN"):
        transition(run, RunState.RUNNING)


def test_freeze_makes_every_frozen_file_read_only(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(
        repository,
        tmp_path / "runs",
        "run-001",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )
    launch(
        run,
        SIGNING_KEY,
        "deterministic",
        TEST_IMAGE,
        model=None,
        execute=False,
        repository=repository,
        allowlist=allowlist,
        dataset_selector="travel",
    )
    transition(run, RunState.RUNNING)
    write_valid_outputs(run)
    frozen = freeze(run, SIGNING_KEY)
    read_only_mode = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    files = [path for path in frozen.iterdir() if path.is_file()]
    assert files, "expected at least one file under frozen/"
    assert any(path.name == "hashes.json" for path in files)
    for path in files:
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == read_only_mode, (
            f"{path.name} is mode {oct(mode)}, expected {oct(read_only_mode)}"
        )


def test_malformed_candidates_are_rejected(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(
        repository,
        tmp_path / "runs",
        "bad",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )
    transition(run, RunState.RUNNING)
    output = run / "workspace/output"
    (output / "candidates.json").write_text("{}")
    (output / "discovery_metrics.json").write_text("{}")
    (output / "run_report.md").write_text("bad")
    with pytest.raises(ValueError, match="schema"):
        freeze(run, SIGNING_KEY)
    assert json.loads((run / "state.json").read_text())["state"] == "FAILED"


def test_missing_outputs_atomically_fail_completed_run(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(
        repository,
        tmp_path / "runs",
        "missing-output",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )
    transition(run, RunState.RUNNING)
    transition(run, RunState.COMPLETED)
    with pytest.raises(FileNotFoundError, match="required outputs missing"):
        freeze(run, SIGNING_KEY)
    assert json.loads((run / "state.json").read_text())["state"] == "FAILED"


def test_verify_rejects_forged_manifest_and_wrong_key(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(
        repository,
        tmp_path / "runs",
        "signed",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )
    with pytest.raises(ValueError, match="signature"):
        verify(run, b"another-evaluator-owned-key!!!!!")
    public_manifest = run / "workspace/BLIND_MANIFEST.json"
    payload = json.loads(public_manifest.read_text())
    payload["random_seed"] = 2
    public_manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="differs"):
        verify(run, SIGNING_KEY)


def test_launch_rejects_source_drift_and_mutable_image(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(
        repository,
        tmp_path / "runs",
        "drift",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )
    with pytest.raises(ValueError, match="immutable image"):
        launch(
            run,
            SIGNING_KEY,
            "deterministic",
            "test-image:latest",
            model=None,
            execute=False,
            repository=repository,
            allowlist=allowlist,
            dataset_selector="travel",
        )
    with pytest.raises(ValueError, match="model does not match"):
        launch(
            run,
            SIGNING_KEY,
            "deterministic",
            TEST_IMAGE,
            model="different-model",
            execute=False,
            repository=repository,
            allowlist=allowlist,
            dataset_selector="travel",
        )
    (repository / "input.txt").write_text("changed after issuance")
    with pytest.raises(ValueError, match="source drift"):
        launch(
            run,
            SIGNING_KEY,
            "deterministic",
            TEST_IMAGE,
            model=None,
            execute=False,
            repository=repository,
            allowlist=allowlist,
            dataset_selector="travel",
        )


def test_verify_rejects_analytical_manifest_contract_drift(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(
        repository,
        tmp_path / "runs",
        "contract-drift",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        dataset_selector="travel",
    )
    manifest_path = (
        repository / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0/manifest.json"
    )
    analytical = json.loads(manifest_path.read_text(encoding="utf-8"))
    analytical["dataset_identity_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(analytical), encoding="utf-8")
    with pytest.raises(ValueError, match="temporal split dataset identity"):
        verify(
            run,
            SIGNING_KEY,
            repository=repository,
            allowlist=allowlist,
            check_source=True,
            dataset_selector="travel",
        )


def test_launch_records_resolved_image_before_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(
        repository,
        tmp_path / "runs",
        "image",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([{"Id": "sha256:" + "a" * 64, "RepoDigests": [TEST_IMAGE]}]),
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("tools.blind_agent.core.subprocess.run", fake_run)
    launch(
        run,
        SIGNING_KEY,
        "deterministic",
        TEST_IMAGE,
        model=None,
        repository=repository,
        allowlist=allowlist,
        dataset_selector="travel",
    )
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["image"] == {
        "requested_reference": TEST_IMAGE,
        "resolved_image_id": "sha256:" + "a" * 64,
        "resolved_repo_digest": TEST_IMAGE,
    }


def test_evaluator_key_is_external_private_and_never_mounted(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    runs_root = tmp_path / "runs"
    key_file = tmp_path / "evaluator/signing.key"
    create_signing_key(key_file, repository, runs_root)
    key = load_signing_key(key_file, repository, runs_root)
    assert len(key) == 32
    assert key_file.stat().st_mode & 0o777 == 0o600
    run = prepare(
        repository, runs_root, "isolated", allowlist, 1, key, TEST_RUNTIME, "deterministic", None
    )
    command = launch(
        run,
        key,
        "deterministic",
        TEST_IMAGE,
        model=None,
        execute=False,
        repository=repository,
        allowlist=allowlist,
        dataset_selector="travel",
    )
    assert str(key_file) not in " ".join(command)
    mounts = [command[index + 1] for index, item in enumerate(command) if item == "-v"]
    assert mounts == [
        f"{(run / 'workspace').resolve()}:/workspace:ro",
        f"{(run / 'workspace/output').resolve()}:/workspace/output:rw",
    ]
    assert not any(path.name == "signing.key" for path in (run / "workspace").rglob("*"))


def test_runner_manifest_is_accepted_by_posthoc_commitment(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)
    run = prepare(
        repository,
        tmp_path / "runs",
        "posthoc",
        allowlist,
        1,
        SIGNING_KEY,
        TEST_RUNTIME,
        "deterministic",
        None,
    )
    manifest = json.loads((run / "workspace/BLIND_MANIFEST.json").read_text())
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps(
            {
                "status": "PERSISTED",
                "blind_bundle_id": manifest["bundle_id"],
                "candidates": [],
            }
        )
    )
    receipt = tmp_path / "receipt.json"
    committed = commit_candidates(
        candidates, run / "workspace/BLIND_MANIFEST.json", receipt, SIGNING_KEY
    )
    assert committed["blind_bundle_id"] == manifest["bundle_id"]


def test_freeze_rejects_contract_drift_and_causal_language(tmp_path: Path) -> None:
    repository, allowlist = fixture_repo(tmp_path)

    def contract_drift(value: dict[str, Any]) -> None:
        value["dataset_identity_sha256"] = "0" * 64

    def causal_language(value: dict[str, Any]) -> None:
        value["candidates"][0]["description"] = "This condition causes lower margin"

    def candidate_count(value: dict[str, Any]) -> None:
        value["candidates"].pop()

    def timing_drift(value: dict[str, Any]) -> None:
        value["candidates"][0]["conditions"][0]["feature"] = "outcome_a"

    cases: tuple[tuple[str, str, Callable[[dict[str, Any]], None]], ...] = (
        (
            "contract",
            "contract mismatch",
            contract_drift,
        ),
        (
            "causal",
            "causal language",
            causal_language,
        ),
        ("count", "10-20 candidates", candidate_count),
        (
            "timing",
            "non-decision-time",
            timing_drift,
        ),
    )
    for run_id, error, mutate in cases:
        run = prepare(
            repository,
            tmp_path / "runs",
            run_id,
            allowlist,
            1,
            SIGNING_KEY,
            TEST_RUNTIME,
            "deterministic",
            None,
        )
        transition(run, RunState.RUNNING)
        write_valid_outputs(run)
        candidates_path = run / "workspace/output/candidates.json"
        candidates = json.loads(candidates_path.read_text())
        mutate(candidates)
        candidates_path.write_text(json.dumps(candidates))
        with pytest.raises(ValueError, match=error):
            freeze(run, SIGNING_KEY)
        assert json.loads((run / "state.json").read_text())["state"] == "FAILED"
