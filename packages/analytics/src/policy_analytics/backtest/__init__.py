"""Policy backtest engine (TASK-032) — validated only against synthetic ground truth (TASK-033)."""

from __future__ import annotations

from policy_analytics.backtest.contract import (
    BACKTEST_CONTRACT_VERSION,
    BACKTEST_WINDOW_SPLIT,
    BAD_OUTCOME_SUPPORTED_OUTCOME_ID,
    BacktestResult,
)
from policy_analytics.backtest.engine import backtest_from_mask, run_backtest

__all__ = [
    "BACKTEST_CONTRACT_VERSION",
    "BACKTEST_WINDOW_SPLIT",
    "BAD_OUTCOME_SUPPORTED_OUTCOME_ID",
    "BacktestResult",
    "backtest_from_mask",
    "run_backtest",
]
