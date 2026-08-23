"""`TASK-068` / `ADR-061` §8 R4: prove a signed `max_feature_identity_fraction` actually reaches
the blind executor and actually changes what it produces.

The failure this file exists to make impossible: before R4, `scripts/run_discovery.py` built its
configuration as `DiscoveryConfig(seed=int(manifest["random_seed"]))` and left every other knob at
its default, so the preregistered "cap-enabled" run would have executed with the cap *disabled*
and emitted a candidate set byte-identical to the baseline — a configuration bug wearing the
costume of a legitimate null result (`ADR-039`'s `task-060-iteration-20260820-003` failure mode,
except mistaken for the answer instead of caught by diff).

Green tests alone cannot show that; a test that only asserts "the executor ran" would have passed
just as happily before the fix. So the central test below runs the real script twice over
identical inputs, differing only in the signed fraction, and asserts the outputs **differ** in the
specific way the cap predicts — the same falsification discipline `ADR-057`'s fixture used to
prove the cap does something rather than merely that tests pass.

Fixture discipline, matching `tests/analytics/test_discovery_engine.py`'s reviewed one: invented
feature names only, `DECISION_TIME`-only inputs, no reference to any domain, pattern, or trap.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from policy_analytics.discovery.engine import DISCOVERY_METHOD_VERSION

from tools.blind_agent.core import signed_identity_fraction

REPOSITORY = Path(__file__).resolve().parents[2]
RUN_DISCOVERY = REPOSITORY / "scripts/run_discovery.py"
DATASET_ROOT = "data/analytical/fixture-analytical-v1.0.0"
OUTCOME_COLUMN = "outcome_value"

# `top_k` is DiscoveryConfig's committed default (15) because run_discovery.py deliberately leaves
# it at the default; 0.34 is the fraction `ADR-061` §4 preregistered, and floor(0.34 * 15) == 5.
TOP_K = 15
TEST_FRACTION = 0.34
EXPECTED_MAX_PER_FEATURE = 5

_N_FILLER_FEATURES = 6
_N_ROWS_PER_SPLIT = 700

FEATURE_COLUMNS = (
    "feature_alpha",
    *[f"filler_{slot}" for slot in range(_N_FILLER_FEATURES)],
    *[f"feature_distinct{position}" for position in range(1, 7)],
)


def _crowding_frame() -> pl.DataFrame:
    """One dominant feature that can pair with several effect-free fillers to produce many
    differently-thresholded but same-identity rules, plus six independently strong, genuinely
    distinct alternatives. Structurally identical in intent to the fixture `ADR-057`/`ADR-059`
    approved, resized so the crowding reproduces at `DiscoveryConfig`'s *default* `top_k`/`min_n`
    (the executor never overrides them)."""
    rows: list[dict[str, object]] = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(_N_ROWS_PER_SPLIT):
            alpha_high = index >= int(_N_ROWS_PER_SPLIT * 0.7)
            distinct = [index % modulus == 0 for modulus in (5, 7, 9, 11, 13, 17)]
            value = 100.0
            if alpha_high:
                value -= 50.0  # the dominant, strong, real effect
            for position, present in enumerate(distinct):
                if present:
                    value -= 20.0 - 1.0 * position
            row: dict[str, object] = {"feature_alpha": float(index)}
            for slot in range(_N_FILLER_FEATURES):
                row[f"filler_{slot}"] = index % _N_FILLER_FEATURES == slot
            for position, present in enumerate(distinct, start=1):
                row[f"feature_distinct{position}"] = present
            row[OUTCOME_COLUMN] = value
            row["split_label"] = split
            rows.append(row)
    return pl.DataFrame(rows)


def _write_dataset(workspace: Path) -> None:
    frame = _crowding_frame()
    dataset = workspace / DATASET_ROOT
    dataset.mkdir(parents=True)
    frame.select(FEATURE_COLUMNS).write_csv(dataset / "features.csv")
    frame.select(OUTCOME_COLUMN).write_csv(dataset / "outcomes.csv")
    frame.select("split_label").write_csv(dataset / "metadata.csv")


def _manifest(fraction: float | str | bool | None, *, omit: bool = False) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "output_schema_version": "1.1.0",
        "run_contract_version": "blind-run-contract-v1.1.0",
        "dataset_version": "fixture-analytical-v1.0.0",
        "dataset_selector": "fixture/comparable",
        "analytical_dataset_root": DATASET_ROOT,
        "dataset_identity_sha256": "d" * 64,
        "outcome_contract_version": "1.0.0",
        "discovery_contract_version": "1.0.0",
        "discovery_method_version": DISCOVERY_METHOD_VERSION,
        "temporal_split_contract_version": "fixture-temporal-split-v1.0.0",
        "primary_outcome": "fixture_outcome",
        "primary_outcome_metadata": {
            "outcome_id": "fixture_outcome",
            "column": OUTCOME_COLUMN,
            "unit": "EUR",
            "higher_is_worse": False,
        },
        "search_fit_split": "development",
        "diagnostic_only_splits": ["validation", "future_holdout"],
        "feature_timing_classes": {name: "DECISION_TIME" for name in FEATURE_COLUMNS},
    }
    if not omit:
        contract["max_feature_identity_fraction"] = fraction
    return {
        "schema_version": "1.0.0",
        "run_id": "fixture-run-001",
        "bundle_id": "b" * 64,
        "random_seed": 1729,
        "allowed_files": {"scripts/run_discovery.py": "a" * 64},
        "acceptance_contract": contract,
    }


def _execute(
    tmp_path: Path, fraction: float | str | bool | None, *, omit: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run the real `scripts/run_discovery.py` the way the container runs it: cwd is the
    workspace root, manifest and output directory at their default relative locations."""
    workspace = tmp_path / f"workspace-{'omitted' if omit else fraction}"
    workspace.mkdir()
    _write_dataset(workspace)
    (workspace / "output").mkdir()
    (workspace / "BLIND_MANIFEST.json").write_text(
        json.dumps(_manifest(fraction, omit=omit)), encoding="utf-8"
    )
    return subprocess.run(
        [sys.executable, str(RUN_DISCOVERY)],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )


def _outputs(
    tmp_path: Path, fraction: float | str | bool | None, *, omit: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    completed = _execute(tmp_path, fraction, omit=omit)
    assert completed.returncode == 0, completed.stderr
    workspace = tmp_path / f"workspace-{'omitted' if omit else fraction}"
    candidates = json.loads((workspace / "output/candidates.json").read_text(encoding="utf-8"))
    metrics = json.loads((workspace / "output/discovery_metrics.json").read_text(encoding="utf-8"))
    return candidates, metrics


def _feature_usage(candidates: dict[str, Any]) -> dict[str, int]:
    usage: dict[str, int] = {}
    for candidate in candidates["candidates"]:
        for feature in {condition["feature"] for condition in candidate["conditions"]}:
            usage[feature] = usage.get(feature, 0) + 1
    return usage


def _slots_free_of(candidates: dict[str, Any], feature: str) -> int:
    return sum(
        1
        for candidate in candidates["candidates"]
        if all(condition["feature"] != feature for condition in candidate["conditions"])
    )


def _signal_identities(candidates: dict[str, Any]) -> set[str]:
    """Excludes `filler_*` padding, which is structural plumbing (a rule cannot place two
    conditions on the same feature) with no effect of its own, not part of the diversity axis --
    the same exclusion the reviewed `test_discovery_engine.py` fixture makes."""
    return {feature for feature in _feature_usage(candidates) if not feature.startswith("filler_")}


def test_signed_cap_changes_the_executor_output_and_is_not_a_relabelled_baseline(
    tmp_path: Path,
) -> None:
    """THE regression test for `ADR-061` §8 R4.

    Same dataset, same seed, same method version, same every-other-knob; the *only* difference is
    the signed `max_feature_identity_fraction`. If the parameter had no path from the manifest
    into `DiscoveryConfig` — the exact pre-fix state — both runs would produce the identical
    candidate list and the first assertion below would fail.
    """
    baseline, baseline_metrics = _outputs(tmp_path, 1.0)
    capped, capped_metrics = _outputs(tmp_path, TEST_FRACTION)

    # 1. Not byte-identical. This single assertion is what distinguishes a real cap-enabled run
    #    from the silent disabled-default run that would otherwise have been reported as a null.
    assert baseline["candidates"] != capped["candidates"]

    # 2. The difference is specifically the cap, not incidental churn: the dominant feature holds
    #    far more than its quota in the baseline and exactly its quota under the cap.
    baseline_usage = _feature_usage(baseline)
    capped_usage = _feature_usage(capped)
    assert baseline_usage["feature_alpha"] > EXPECTED_MAX_PER_FEATURE
    assert capped_usage["feature_alpha"] == EXPECTED_MAX_PER_FEATURE
    assert max(capped_usage.values()) <= EXPECTED_MAX_PER_FEATURE

    # 3. Concentration genuinely fell rather than the set merely being reshuffled. The baseline
    #    is the crowding failure mode in its purest form — every one of the 15 committed slots
    #    touches the dominant feature — and under the cap two thirds of the set is free of it.
    assert max(baseline_usage.values()) == TOP_K
    assert _slots_free_of(baseline, "feature_alpha") == 0
    assert _slots_free_of(capped, "feature_alpha") == TOP_K - EXPECTED_MAX_PER_FEATURE

    # 4. `TASK-068`'s preregistered structural check, at the executor level rather than the engine
    #    level: strictly more distinct signal identities in the committed Top-K. Both runs still
    #    return a full `top_k` — a shrink to fewer candidates would be a materially weaker outcome
    #    (and under 10 would emit `INSUFFICIENT_CANDIDATES`), so it is asserted against.
    assert len(_signal_identities(capped)) > len(_signal_identities(baseline))
    assert len(baseline["candidates"]) == len(capped["candidates"]) == TOP_K
    assert baseline["status"] == capped["status"] == "PERSISTED"

    # 5. Which configuration produced which candidates is recorded in the artifact itself, not
    #    only in whoever remembers what was issued.
    assert baseline_metrics["max_feature_identity_fraction"] == 1.0
    assert capped_metrics["max_feature_identity_fraction"] == TEST_FRACTION


def test_omitted_cap_field_reproduces_the_disabled_run_exactly(tmp_path: Path) -> None:
    """Default safety (`ADR-061` §8 R4 requirement 3): a contract with no such field must run
    fully disabled — byte-identical to an explicit `1.0`, never silently something else."""
    explicit, explicit_metrics = _outputs(tmp_path, 1.0)
    omitted, omitted_metrics = _outputs(tmp_path, None, omit=True)
    assert omitted["candidates"] == explicit["candidates"]
    assert omitted_metrics["max_feature_identity_fraction"] == 1.0
    assert omitted_metrics == explicit_metrics


@pytest.mark.parametrize("bad_value", [1.5, -0.1, "0.34", True, None, float("nan")])
def test_malformed_cap_refuses_to_run(tmp_path: Path, bad_value: object) -> None:
    """Fail closed, never coerce. A run that cannot express its signed configuration must not
    produce output at all — a run ID is consumed permanently on issuance, and a wrong-but-plausible
    candidate set is worse than no candidate set."""
    completed = _execute(tmp_path, bad_value)  # pyright: ignore[reportArgumentType]
    assert completed.returncode != 0
    assert "max_feature_identity_fraction" in completed.stderr
    workspace = tmp_path / f"workspace-{bad_value}"
    assert not (workspace / "output/candidates.json").exists()


def test_executor_and_evaluator_identity_fraction_parsers_agree() -> None:
    """`scripts/run_discovery.py` deliberately duplicates `core.signed_identity_fraction` because
    the isolated workspace cannot import `tools.blind_agent.core`. Duplication is only safe while
    the two agree, so pin them to each other over the cases that matter."""
    module = _load_run_discovery_module()
    executor_parser = module._signed_identity_fraction  # pyright: ignore[reportPrivateUsage]
    accepted_contracts: list[dict[str, Any]] = [
        {},
        {"max_feature_identity_fraction": 1.0},
        {"max_feature_identity_fraction": 0.34},
        {"max_feature_identity_fraction": 0.0},
        {"max_feature_identity_fraction": 1},
        {"max_feature_identity_fraction": 0},
    ]
    for contract in accepted_contracts:
        assert executor_parser(contract) == signed_identity_fraction(contract)
    rejected_contracts: list[dict[str, Any]] = [
        {"max_feature_identity_fraction": 1.5},
        {"max_feature_identity_fraction": -0.1},
        {"max_feature_identity_fraction": "0.34"},
        {"max_feature_identity_fraction": True},
        {"max_feature_identity_fraction": False},
        {"max_feature_identity_fraction": None},
        {"max_feature_identity_fraction": float("nan")},
        {"max_feature_identity_fraction": float("inf")},
    ]
    for contract in rejected_contracts:
        with pytest.raises(ValueError):
            executor_parser(contract)
        with pytest.raises(ValueError):
            signed_identity_fraction(contract)


def _load_run_discovery_module() -> Any:
    """`scripts/` is not an importable package, so load the executor from its real path. It must
    be registered in `sys.modules` before execution: it defines a `@dataclass`, and
    `dataclasses` resolves string annotations through `sys.modules[cls.__module__]`."""
    import importlib.util

    name = "_run_discovery_under_test"
    spec = importlib.util.spec_from_file_location(name, RUN_DISCOVERY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        raise
    return module
