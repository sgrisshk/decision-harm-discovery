from __future__ import annotations

import dataclasses
import hashlib
import json
import random
from pathlib import Path

import pytest
from policy_analytics.synthetic_benchmark import (
    DIFFICULTY_PRESETS,
    BenchmarkConfig,
    Difficulty,
    difficulty_config,
    generate_benchmark,
    scale_effect_leaves,
    scaled_uniform,
)

pytestmark = pytest.mark.analytics

#: The already-frozen hidden ground truth's own SHA-256, referenced throughout TASKS.md/
#: memory/HANDOFFS.md as the basis for every already-completed discovery/validation/blind run
#: built on this benchmark. This is the single most important regression gate in this file: TASK-
#: 004 must never change this value.
FROZEN_HIDDEN_GROUND_TRUTH_SHA256 = (
    "5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506"
)


# --- the critical non-destructiveness gate -----------------------------------------------------


def test_default_config_still_reproduces_the_frozen_hidden_ground_truth(tmp_path: Path) -> None:
    """If this ever fails, TASK-004's changes have altered the benchmark every already-completed
    discovery/validation/blind run (task-015-official-20260816-015 and everything scored from it)
    was built against — treat as a hard stop, not a value to update."""
    generate_benchmark(tmp_path, BenchmarkConfig())
    digest = hashlib.sha256(
        (tmp_path / "evaluation" / "hidden_ground_truth.json").read_bytes()
    ).hexdigest()
    assert digest == FROZEN_HIDDEN_GROUND_TRUTH_SHA256


def test_medium_preset_config_equals_plain_default_config() -> None:
    assert difficulty_config(Difficulty.MEDIUM) == BenchmarkConfig()


def test_medium_preset_generates_byte_identical_artifacts_to_plain_default(tmp_path: Path) -> None:
    plain_root = tmp_path / "plain"
    preset_root = tmp_path / "preset"
    plain_checksums = generate_benchmark(plain_root, BenchmarkConfig(row_count=300))
    preset_checksums = generate_benchmark(
        preset_root, difficulty_config(Difficulty.MEDIUM, row_count=300)
    )
    # generation_config.json legitimately differs (it now records the six new fields) — every
    # other artifact, including the hidden ground truth, must not.
    plain_checksums.pop("metadata/generation_config.json")
    preset_checksums.pop("metadata/generation_config.json")
    assert plain_checksums == preset_checksums


# --- pure helper functions ----------------------------------------------------------------------


def test_scaled_uniform_reduces_to_plain_uniform_at_scale_one() -> None:
    seed = 12345
    scaled = scaled_uniform(random.Random(seed), 10.0, 20.0, 1.0)
    plain = random.Random(seed).uniform(10.0, 20.0)
    assert scaled == plain


def test_scaled_uniform_widens_the_range_around_the_same_mean() -> None:
    rng = random.Random(1)
    draws = [scaled_uniform(rng, 10.0, 20.0, 2.0) for _ in range(500)]
    assert min(draws) < 10.0  # widened beyond the original [10, 20] bounds
    assert max(draws) > 20.0
    assert 14.0 < (sum(draws) / len(draws)) < 16.0  # mean stays ~15


def test_scale_effect_leaves_identity_at_scale_one_preserves_int_type() -> None:
    original: dict[str, object] = {"a": 410, "b": {"c": 1.05, "d": "formula string"}}
    result = scale_effect_leaves(original, 1.0)
    assert result is original  # not even a copy — the documented byte-identity guarantee
    assert isinstance(result, dict)
    assert isinstance(result["a"], int)


def test_scale_effect_leaves_scales_numeric_leaves_recursively() -> None:
    original: dict[str, object] = {"a": 410, "b": {"c": 1.05, "d": "formula string"}, "e": True}
    result = scale_effect_leaves(original, 2.0)
    assert result == {"a": 820.0, "b": {"c": 2.1, "d": "formula string"}, "e": True}


def test_scale_effect_leaves_never_scales_booleans() -> None:
    assert scale_effect_leaves(True, 5.0) is True
    assert scale_effect_leaves(False, 5.0) is False


# --- validation --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "effect_scale",
        "noise_scale",
        "confounding_scale",
        "missingness_scale",
        "rarity_scale",
        "drift_scale",
    ],
)
def test_generate_benchmark_rejects_non_positive_scale_factors(tmp_path: Path, field: str) -> None:
    config = dataclasses.replace(BenchmarkConfig(row_count=200), **{field: 0.0})
    with pytest.raises(ValueError, match="difficulty scale factor"):
        generate_benchmark(tmp_path, config)


# --- the presets actually move difficulty in the expected direction ----------------------------


def _total_exposure_and_impact(root: Path) -> tuple[int, float]:
    truth = json.loads((root / "evaluation" / "hidden_ground_truth.json").read_text())
    total_n = sum(p["true_effect"]["affected_n"] for p in truth["patterns"])
    total_impact = sum(
        abs(p["true_effect"]["realized_economic_impact"] or 0.0) for p in truth["patterns"]
    )
    return total_n, total_impact


def test_presets_move_support_and_economic_impact_monotonically(tmp_path: Path) -> None:
    """EASY must be easier (more exposed rows, larger total impact) than MEDIUM, which must be
    easier than HARD, which must be easier than BRUTAL — the actual point of TASK-004."""
    totals: dict[Difficulty, tuple[int, float]] = {}
    for difficulty in Difficulty:
        root = tmp_path / difficulty.value
        generate_benchmark(root, difficulty_config(difficulty, row_count=1500))
        totals[difficulty] = _total_exposure_and_impact(root)

    exposure = {d: totals[d][0] for d in Difficulty}
    impact = {d: totals[d][1] for d in Difficulty}
    assert (
        exposure[Difficulty.EASY]
        > exposure[Difficulty.MEDIUM]
        > exposure[Difficulty.HARD]
        > exposure[Difficulty.BRUTAL]
    )
    assert (
        impact[Difficulty.EASY]
        > impact[Difficulty.MEDIUM]
        > impact[Difficulty.HARD]
        > impact[Difficulty.BRUTAL]
    )


def test_every_preset_generates_and_stays_internally_consistent(tmp_path: Path) -> None:
    """The same paired factual-minus-counterfactual arithmetic Statistics independently verified
    for the frozen MEDIUM artifact (HANDOFF-030) must still hold at every difficulty: realized
    economic impact is exactly |realized_effect| x affected_n."""
    for difficulty in Difficulty:
        root = tmp_path / difficulty.value
        generate_benchmark(root, difficulty_config(difficulty, row_count=800))
        truth = json.loads((root / "evaluation" / "hidden_ground_truth.json").read_text())
        for pattern in truth["patterns"]:
            effect = pattern["true_effect"]
            if effect["realized_effect"] is None:
                continue
            expected_impact = round(-effect["realized_effect"] * effect["affected_n"], 2)
            assert expected_impact == effect["realized_economic_impact"], (
                difficulty.value,
                pattern["id"],
            )


def test_difficulty_presets_cover_all_four_named_difficulties() -> None:
    assert set(DIFFICULTY_PRESETS) == set(Difficulty)
