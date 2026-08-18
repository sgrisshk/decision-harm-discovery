"""Tests for the TASK-032 policy backtest engine.

Synthetic fixtures only — a small hand-built frame with a known future_holdout population, so
every count and sign is checkable by hand. Never opens `hidden_ground_truth.json` (that is
TASK-033's job, in a separate script, after this methodology is frozen).
"""

from __future__ import annotations

import random

import polars as pl
import pytest
from policy_analytics.backtest import BACKTEST_CONTRACT_VERSION, BacktestResult, run_backtest
from policy_analytics.backtest.contract import BAD_OUTCOME_THRESHOLD
from policy_analytics.outcomes import OUTCOME_BY_ID
from policy_analytics.validation.apply import Condition
from policy_analytics.validation.report import EffectEstimate

pytestmark = pytest.mark.analytics


def _outcome():
    return OUTCOME_BY_ID["contribution_margin_eur"]


def _frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def _row(
    booking_id: str,
    customer_id: str,
    split: str,
    flag: bool,
    margin: float,
) -> dict[str, object]:
    return {
        "booking_id": booking_id,
        "customer_id": customer_id,
        "split_label": split,
        "flag_feature": flag,
        "contribution_margin_eur": margin,
    }


def _base_rows() -> list[dict[str, object]]:
    # future_holdout: 4 flagged (2 bad, 2 good), 4 comparison, all margin >= 0 (no harm signal in
    # the comparison group). development rows exist only to prove they are never touched.
    rows = [
        _row("H1", "C1", "future_holdout", True, -50.0),
        _row("H2", "C2", "future_holdout", True, -30.0),
        _row("H3", "C3", "future_holdout", True, 40.0),
        _row("H4", "C4", "future_holdout", True, 60.0),
        _row("H5", "C5", "future_holdout", False, 100.0),
        _row("H6", "C6", "future_holdout", False, 110.0),
        _row("H7", "C7", "future_holdout", False, 90.0),
        _row("H8", "C8", "future_holdout", False, 95.0),
        _row("D1", "C9", "development", True, -99999.0),  # would blow up the result if included
        _row("D2", "C10", "development", False, 99999.0),
    ]
    return rows


def _conditions() -> list[Condition]:
    return [Condition("flag_feature", "eq", True)]


def test_run_backtest_matches_hand_computation_on_a_known_frame() -> None:
    frame = _frame(_base_rows())
    result = run_backtest(
        frame=frame, conditions=_conditions(), outcome=_outcome(), rng=random.Random(1)
    )
    assert result.backtest_contract_version == BACKTEST_CONTRACT_VERSION
    assert result.window == "future_holdout"
    assert result.affected_decisions == 4
    assert result.avoided_bad_outcomes == 2  # -50, -30
    assert result.suppressed_good_outcomes == 2  # 40, 60
    # exposed mean = (-50-30+40+60)/4 = 5; comparison mean = (100+110+90+95)/4 = 98.75
    # raw diff = 5 - 98.75 = -93.75; harm_multiplier for margin (higher_is_worse=False) = -1
    # harm_per_booking = -93.75 * -1 = 93.75; benefit = 93.75 * 4 = 375.0
    assert result.benefit.value == pytest.approx(375.0)
    assert result.benefit_is_adjusted is False


def test_run_backtest_never_touches_development_rows() -> None:
    # D1/D2 have extreme values designed to blow up the result if the future_holdout filter leaked.
    frame = _frame(_base_rows())
    result = run_backtest(
        frame=frame, conditions=_conditions(), outcome=_outcome(), rng=random.Random(1)
    )
    assert abs(result.benefit.value) < 1000  # would be ~1e5 if development rows leaked in


def test_avoided_plus_suppressed_always_equals_affected_decisions() -> None:
    frame = _frame(_base_rows())
    result = run_backtest(
        frame=frame, conditions=_conditions(), outcome=_outcome(), rng=random.Random(1)
    )
    assert result.avoided_bad_outcomes + result.suppressed_good_outcomes == (
        result.affected_decisions
    )


def test_run_backtest_rejects_a_non_primary_outcome() -> None:
    frame = _frame(_base_rows())
    with pytest.raises(ValueError, match="only supports"):
        run_backtest(
            frame=frame,
            conditions=_conditions(),
            outcome=OUTCOME_BY_ID["gross_profit_eur"],
            rng=random.Random(1),
        )


def test_run_backtest_raises_when_future_holdout_has_no_comparison_group() -> None:
    rows = [_row(f"H{i}", f"C{i}", "future_holdout", True, 10.0) for i in range(5)]
    frame = _frame(rows)
    with pytest.raises(ValueError, match="nothing to backtest"):
        run_backtest(
            frame=frame, conditions=_conditions(), outcome=_outcome(), rng=random.Random(1)
        )


def test_run_backtest_raises_on_a_missing_outcome_value_among_affected_records() -> None:
    rows = _base_rows()
    rows[0]["contribution_margin_eur"] = None
    frame = pl.DataFrame(rows)
    with pytest.raises(ValueError, match="MissingDataPolicy.COMPLETE"):
        run_backtest(
            frame=frame, conditions=_conditions(), outcome=_outcome(), rng=random.Random(1)
        )


def test_operational_cost_is_none_when_not_supplied() -> None:
    frame = _frame(_base_rows())
    result = run_backtest(
        frame=frame, conditions=_conditions(), outcome=_outcome(), rng=random.Random(1)
    )
    assert result.operational_cost is None
    assert result.operational_cost_per_review_eur is None
    assert result.net_effect_is_cost_exclusive is True
    assert result.net_effect.value == pytest.approx(result.benefit.value)


def test_operational_cost_is_netted_when_supplied() -> None:
    frame = _frame(_base_rows())
    result = run_backtest(
        frame=frame,
        conditions=_conditions(),
        outcome=_outcome(),
        cost_per_review_eur=50.0,
        rng=random.Random(1),
    )
    assert result.operational_cost is not None
    assert result.operational_cost.value == pytest.approx(50.0 * result.affected_decisions)
    expected_net = result.benefit.value - result.operational_cost.value
    assert result.net_effect.value == pytest.approx(expected_net)
    assert result.net_effect_is_cost_exclusive is False


def test_reproducible_across_two_runs_with_the_same_seed() -> None:
    frame = _frame(_base_rows())
    first = run_backtest(
        frame=frame, conditions=_conditions(), outcome=_outcome(), rng=random.Random(20260818)
    )
    second = run_backtest(
        frame=frame, conditions=_conditions(), outcome=_outcome(), rng=random.Random(20260818)
    )
    assert first.benefit.ci_low == second.benefit.ci_low
    assert first.benefit.ci_high == second.benefit.ci_high


def test_no_measurable_net_effect_true_when_interval_crosses_zero() -> None:
    # Construct a frame with a tiny, noisy exposed group so the bootstrap CI is wide and crosses 0.
    rows = [
        _row("H1", "C1", "future_holdout", True, -10.0),
        _row("H2", "C2", "future_holdout", True, 10.0),
        _row("H3", "C3", "future_holdout", False, -5.0),
        _row("H4", "C4", "future_holdout", False, 5.0),
    ]
    frame = _frame(rows)
    result = run_backtest(
        frame=frame, conditions=_conditions(), outcome=_outcome(), rng=random.Random(1)
    )
    assert result.no_measurable_net_effect == (
        not (result.net_effect.ci_low > 0 or result.net_effect.ci_high < 0)
    )


def test_backtest_result_rejects_a_window_other_than_future_holdout() -> None:
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="future_holdout"):
        BacktestResult(
            backtest_contract_version=BACKTEST_CONTRACT_VERSION,
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            window="development",
            affected_decisions=0,
            avoided_bad_outcomes=0,
            suppressed_good_outcomes=0,
            bad_outcome_definition="x",
            benefit=estimate,
            benefit_is_adjusted=False,
            operational_cost_per_review_eur=None,
            operational_cost=None,
            net_effect=estimate,
            net_effect_is_cost_exclusive=True,
            no_measurable_net_effect=True,
            methodology_disclosure="x",
        )


def test_backtest_result_rejects_mismatched_avoided_suppressed_counts() -> None:
    estimate = EffectEstimate(0.0, 0.0, 0.0, 0.95, "test", "EUR")
    with pytest.raises(ValueError, match="avoided_bad_outcomes"):
        BacktestResult(
            backtest_contract_version=BACKTEST_CONTRACT_VERSION,
            outcome_name="contribution_margin_eur",
            outcome_unit="EUR",
            window="future_holdout",
            affected_decisions=10,
            avoided_bad_outcomes=3,
            suppressed_good_outcomes=3,  # should sum to 10
            bad_outcome_definition="x",
            benefit=estimate,
            benefit_is_adjusted=False,
            operational_cost_per_review_eur=None,
            operational_cost=None,
            net_effect=estimate,
            net_effect_is_cost_exclusive=True,
            no_measurable_net_effect=True,
            methodology_disclosure="x",
        )


def test_bad_outcome_threshold_is_zero_margin() -> None:
    assert BAD_OUTCOME_THRESHOLD == 0.0
