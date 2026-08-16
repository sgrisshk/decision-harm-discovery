import polars as pl
import pytest
from policy_analytics.discovery.ranking_signals import build_candidate_signals
from policy_analytics.outcomes import primary_outcome

pytestmark = pytest.mark.analytics


def _frame() -> pl.DataFrame:
    # contribution_margin_eur: higher is better, so harm = a decrease under the condition.
    # discount_rate >= 0.1 is harmful and holds in every split.
    rows: list[tuple[float, float, str]] = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(40):
            discount = 0.2 if index % 2 == 0 else 0.0
            margin = 100.0 - (50.0 if discount >= 0.1 else 0.0)
            rows.append((discount, margin, split))
    return pl.DataFrame(
        rows, schema=["discount_rate", "contribution_margin_eur", "split_label"], orient="row"
    )


def _payload(candidate: dict[str, object]) -> dict[str, object]:
    return {"candidates": [candidate]}


def test_stable_harmful_condition_gets_full_stability_and_correct_membership() -> None:
    frame = _frame()
    candidate = {
        "candidate_id": "CAND-001",
        "conditions": [{"feature": "discount_rate", "operator": "ge", "value": 0.1}],
        "outcome": "contribution_margin_eur",
        "economic_exposure": -1000.0,
        "support": 0.5,
        "raw_effect": -50.0,  # exposed mean - comparison mean, matches the harmful direction
        "warnings": ["Raw descriptive association; not adjusted and not causal."],
    }
    (signals,) = build_candidate_signals(_payload(candidate), frame, primary_outcome())
    assert signals.candidate_id == "CAND-001"
    assert signals.economic_impact == 1000.0
    assert signals.support == 0.5
    assert signals.stability == 1.0
    assert signals.stability is not None
    assert len(signals.exposed_row_ids) == 20  # half of the 40 development rows
    assert signals.actionability == 1.0  # discount_rate is directly controllable


def test_condition_with_no_development_exposure_has_no_stability() -> None:
    frame = _frame()
    candidate = {
        "candidate_id": "CAND-002",
        "conditions": [{"feature": "discount_rate", "operator": "ge", "value": 5.0}],
        "outcome": "contribution_margin_eur",
        "economic_exposure": 0.0,
        "support": 0.0,
        "raw_effect": 0.0,
        "warnings": [],
    }
    (signals,) = build_candidate_signals(_payload(candidate), frame, primary_outcome())
    assert signals.stability is None
    assert signals.exposed_row_ids == frozenset()


def test_non_controllable_condition_scores_review_required() -> None:
    frame = _frame().rename({"discount_rate": "party_size"})
    candidate = {
        "candidate_id": "CAND-003",
        "conditions": [{"feature": "party_size", "operator": "ge", "value": 0.1}],
        "outcome": "contribution_margin_eur",
        "economic_exposure": -500.0,
        "support": 0.5,
        "raw_effect": -50.0,
        "warnings": [],
    }
    (signals,) = build_candidate_signals(_payload(candidate), frame, primary_outcome())
    assert signals.actionability == pytest.approx(0.35)


def test_economic_impact_is_the_absolute_value_of_frozen_exposure() -> None:
    frame = _frame()
    candidate = {
        "candidate_id": "CAND-004",
        "conditions": [{"feature": "discount_rate", "operator": "ge", "value": 0.1}],
        "outcome": "contribution_margin_eur",
        "economic_exposure": -12345.67,
        "support": 0.5,
        "raw_effect": -50.0,
        "warnings": [],
    }
    (signals,) = build_candidate_signals(_payload(candidate), frame, primary_outcome())
    assert signals.economic_impact == pytest.approx(12345.67)
