"""Tests for the TASK-014 baseline statistics script's pure helper functions.

Synthetic fixtures only — this is a data-understanding/sanity-check pass, not a validated finding
or a discovery run, and nothing here opens `hidden_ground_truth.json`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "scripts"))
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from baseline_statistics import (  # noqa: E402
    _rename_mean,
    _split_frame,
    categorical_summary,
    numeric_summary,
    outcome_breakdown_by,
)
from policy_analytics.outcomes import OUTCOME_BY_ID  # noqa: E402

pytestmark = pytest.mark.analytics


def test_numeric_summary_matches_hand_computation() -> None:
    summary = numeric_summary([10.0, 20.0, 30.0, 40.0])
    assert summary["n"] == 4
    assert summary["mean"] == pytest.approx(25.0)
    assert summary["min"] == 10.0
    assert summary["max"] == 40.0
    assert summary["median"] == pytest.approx(30.0)  # int(4 * 0.5) = index 2 -> 30.0


def test_numeric_summary_handles_an_empty_sequence_without_error() -> None:
    summary = numeric_summary([])
    assert summary["n"] == 0
    assert summary["mean"] == 0.0


def test_categorical_summary_orders_by_descending_frequency_then_alphabetically() -> None:
    summary = categorical_summary(["b", "a", "a", "c", "b", "a"])
    assert summary["distinct"] == 3
    assert list(summary["value_counts"]) == ["a", "b", "c"]  # a:3, b:2, c:1
    assert summary["value_counts"] == {"a": 3, "b": 2, "c": 1}
    assert summary["share"]["a"] == pytest.approx(0.5)


def test_categorical_summary_breaks_frequency_ties_alphabetically() -> None:
    summary = categorical_summary(["z", "y", "x"])  # all count 1
    assert list(summary["value_counts"]) == ["x", "y", "z"]


def test_split_frame_filters_to_the_requested_split_only() -> None:
    frame = pl.DataFrame(
        {"split_label": ["development", "validation", "development"], "value": [1, 2, 3]}
    )
    dev = _split_frame(frame, "development")
    assert dev.height == 2
    assert dev["value"].to_list() == [1, 3]


def test_outcome_breakdown_by_reports_per_value_n_and_mean() -> None:
    outcome = OUTCOME_BY_ID["contribution_margin_eur"]
    frame = pl.DataFrame(
        {
            "manager": ["Manager 1", "Manager 1", "Manager 2"],
            "contribution_margin_eur": [100.0, 200.0, 300.0],
        }
    )
    rows = outcome_breakdown_by(frame, "manager", outcome)
    by_value = {row["value"]: row for row in rows}
    assert by_value["Manager 1"]["n_total"] == 2
    assert by_value["Manager 1"]["mean"] == pytest.approx(150.0)
    assert by_value["Manager 2"]["n_total"] == 1
    assert by_value["Manager 2"]["mean"] == pytest.approx(300.0)


def test_outcome_breakdown_by_reports_missing_rate_for_a_group_with_nulls() -> None:
    outcome = OUTCOME_BY_ID["repeat_purchase_180d"]
    frame = pl.DataFrame(
        {
            "manager": ["Manager 1", "Manager 1", "Manager 1"],
            "repeat_purchase_180d": [True, None, False],
        }
    )
    rows = outcome_breakdown_by(frame, "manager", outcome)
    assert rows[0]["n_total"] == 3
    assert rows[0]["n_present"] == 2
    assert rows[0]["missing_rate"] == pytest.approx(1 / 3)


def test_rename_mean_leaves_exactly_one_key_behind() -> None:
    # Regression: an earlier version used {**row, "primary_outcome_mean": row.pop("mean")}, which
    # unpacks **row (including "mean") before the pop takes effect, silently leaving both keys.
    rows = [{"value": "x", "mean": 42.0, "n_total": 5}]
    result = _rename_mean(rows)
    assert result[0]["primary_outcome_mean"] == 42.0
    assert "mean" not in result[0]
