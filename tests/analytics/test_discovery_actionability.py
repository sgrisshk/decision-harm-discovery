import pytest
from policy_analytics.discovery.actionability import (
    DIRECTLY_CONTROLLABLE_FEATURES,
    HIGH_SCORE,
    REVIEW_REQUIRED_SCORE,
    actionability_label,
    actionability_score,
)
from policy_analytics.discovery.engine import Condition

pytestmark = pytest.mark.analytics


def test_high_when_any_condition_is_directly_controllable() -> None:
    conditions = (Condition("discount_rate", "ge", 0.1), Condition("party_size", "eq", 2))
    assert actionability_label(conditions) == "HIGH"
    assert actionability_score(conditions) == HIGH_SCORE


def test_review_required_when_no_condition_is_directly_controllable() -> None:
    conditions = (Condition("party_size", "eq", 2), Condition("trip_duration_days", "lt", 5.0))
    assert actionability_label(conditions) == "REVIEW_REQUIRED"
    assert actionability_score(conditions) == REVIEW_REQUIRED_SCORE


def test_review_required_score_is_conservative_not_zero() -> None:
    # A REVIEW_REQUIRED candidate can still be actionable after business review, so it must not
    # be scored as if it were nearly worthless.
    assert 0.0 < REVIEW_REQUIRED_SCORE < HIGH_SCORE


def test_controllable_feature_set_matches_engine_reference() -> None:
    # party_size/trip_duration_days/booking_lead_days describe the trip, not a policy lever.
    assert "party_size" not in DIRECTLY_CONTROLLABLE_FEATURES
    assert "discount_rate" in DIRECTLY_CONTROLLABLE_FEATURES
    assert "supplier" in DIRECTLY_CONTROLLABLE_FEATURES
