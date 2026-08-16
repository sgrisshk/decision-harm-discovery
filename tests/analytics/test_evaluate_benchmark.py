"""Tests for the TASK-028 benchmark evaluator's pure scoring logic.

Does not open `hidden_ground_truth.json` for anything beyond what the real evaluator run already
did (these are unit tests of the matching/parsing helpers on synthetic fixtures, not a re-run of
the scoring itself).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from evaluate_benchmark import (  # noqa: E402
    MATCH_RECALL_THRESHOLD,
    TRAP_APPARENT_CONDITIONS,
    _condition_from_dict,
    _matches_trap,
)

pytestmark = pytest.mark.analytics


def test_condition_from_dict_round_trips_fields() -> None:
    condition = _condition_from_dict({"feature": "discount_rate", "operator": "ge", "value": 0.12})
    assert condition.feature == "discount_rate"
    assert condition.operator == "ge"
    assert condition.value == 0.12


def test_matches_trap_detects_an_exact_apparent_condition() -> None:
    conditions = [
        {"feature": "manager", "operator": "eq", "value": "Manager 2"},
        {"feature": "discount_rate", "operator": "ge", "value": 0.1},
    ]
    assert _matches_trap(conditions) == ["T01"]


def test_matches_trap_does_not_fire_on_the_opposite_polarity() -> None:
    # T05 is manual_exception == True; a candidate requiring manual_exception == False is a
    # different, non-trap condition and must not be flagged.
    conditions = [{"feature": "manual_exception", "operator": "eq", "value": False}]
    assert _matches_trap(conditions) == []


def test_matches_trap_returns_empty_for_unrelated_conditions() -> None:
    conditions = [
        {"feature": "discount_rate", "operator": "ge", "value": 0.12},
        {"feature": "booking_lead_days", "operator": "lt", "value": 21},
    ]
    assert _matches_trap(conditions) == []


def test_matches_trap_can_detect_multiple_traps_at_once() -> None:
    conditions = [
        {"feature": "manager", "operator": "eq", "value": "Manager 2"},
        {"feature": "supplier", "operator": "eq", "value": "Atlas"},
    ]
    assert sorted(_matches_trap(conditions)) == ["T01", "T02"]


def test_all_five_traps_are_registered_with_their_stated_apparent_feature() -> None:
    # Cross-check against docs/benchmark/decision-gate.md's fixed denominator: 5 confounding traps.
    assert set(TRAP_APPARENT_CONDITIONS) == {"T01", "T02", "T03", "T04", "T05"}


def test_match_recall_threshold_is_a_majority_bar_fixed_before_scoring() -> None:
    # Documents the preregistered choice (module docstring): 0.5, chosen once, not tuned to results.
    assert MATCH_RECALL_THRESHOLD == 0.5
