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
    _attribution_narrowed_impact,
    _attribution_overlap_ids,
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


# --- TASK-059: attribution-narrowed diagnostic helpers (synthetic fixtures only) -----------------


def test_attribution_overlap_ids_is_the_intersection_with_matched_patterns_only() -> None:
    exposed_ids = frozenset({"b1", "b2", "b3", "b4"})
    patterns_by_id = {
        "P01": {"affected_booking_ids": ["b2", "b3", "b9"]},
        "P02": {"affected_booking_ids": ["b4", "b10"]},
        "P03": {"affected_booking_ids": ["b1"]},  # not in matched_patterns -> must not contribute
    }
    overlap = _attribution_overlap_ids(exposed_ids, ["P01", "P02"], patterns_by_id)
    assert overlap == frozenset({"b2", "b3", "b4"})


def test_attribution_overlap_ids_is_empty_when_no_patterns_matched() -> None:
    exposed_ids = frozenset({"b1", "b2"})
    patterns_by_id = {"P01": {"affected_booking_ids": ["b1", "b2"]}}
    assert _attribution_overlap_ids(exposed_ids, [], patterns_by_id) == frozenset()


def test_attribution_narrowed_impact_scales_per_record_effect_by_overlap_n() -> None:
    per_record_effect = {"value": 100.0, "ci_low": 80.0, "ci_high": 130.0}
    point, ci = _attribution_narrowed_impact(per_record_effect, overlap_n=50)
    assert point == pytest.approx(5000.0)
    assert ci == (pytest.approx(4000.0), pytest.approx(6500.0))


def test_attribution_narrowed_impact_is_zero_for_an_empty_overlap() -> None:
    # A candidate can recover a pattern by recall (majority of the pattern's bookings) while still
    # sharing zero bookings with a *different* matched pattern's affected set — must not divide by
    # zero or otherwise error, just report zero narrowed impact for that population.
    per_record_effect = {"value": -42.0, "ci_low": -60.0, "ci_high": -20.0}
    point, ci = _attribution_narrowed_impact(per_record_effect, overlap_n=0)
    assert point == 0.0
    assert ci == (0.0, 0.0)
