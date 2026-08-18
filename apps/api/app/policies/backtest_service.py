"""Trigger and persist a real Policy Candidate backtest run (`TASK-034`).

Computed synchronously inside the request — no async/worker infrastructure exists anywhere in
this codebase (`AnalysisRunModel`/`scripts/promote_findings.py` resolve `status` directly after
synchronous work); a real `pending`/`running` state would be theater with nothing actually running
concurrently. `run_backtest` (`policy_analytics.backtest.engine`, `TASK-032`) does the real
computation — this module only wires a Policy Candidate's stored trigger to it and persists the
result, exactly like `scripts/run_backtest.py` does for the standalone CLI path.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import HTTPException, status
from policy_analytics.backtest.engine import run_backtest
from policy_analytics.outcomes.contract import primary_outcome
from policy_analytics.validation.apply import Condition, Operator, load_analytical_frame
from sqlalchemy.orm import Session

from app.db.models import PolicyBacktestRunModel, PolicyCandidateModel
from app.policies.contracts import PolicyCandidateBacktestSnapshot

_ANALYTICAL_DATASET_DIR = (
    Path(__file__).resolve().parents[4]
    / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
)

#: `docs/product/policy-backtest-screen.md` §1: only a candidate already at `APPROVED_SHADOW` or
#: later may be backtested — replaying a still-`DRAFT`/`UNDER_REVIEW` rule nobody has reviewed or
#: committed to trying would be premature.
_ELIGIBLE_STATUSES = frozenset({"APPROVED_SHADOW", "APPROVED_FOR_CUSTOMER_DECISION"})

_SUPPORTED_OUTCOME = "contribution_margin_eur"

_OPERATORS = frozenset({"eq", "lt", "le", "gt", "ge"})


def _to_condition(raw: dict[str, object]) -> Condition:
    operator = cast(str, raw["operator"])
    if operator not in _OPERATORS:
        raise ValueError(f"unsupported operator for backtest replay: {operator!r}")
    return Condition(cast(str, raw["feature"]), cast(Operator, operator), raw["value"])


def trigger_backtest(
    session: Session, candidate: PolicyCandidateModel, *, cost_per_review_eur: float | None = None
) -> PolicyBacktestRunModel:
    """§1's eligibility gate, then a real `run_backtest()` call against the real analytical
    dataset. Always inserts a new row — re-running never overwrites a prior run (§2). A `failed`
    run still commits (audit trail), with the engine's own disclosed reason, never a raw 500."""
    if candidate.status not in _ELIGIBLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"candidate {candidate.id} is {candidate.status}, not APPROVED_SHADOW or later — "
                "not eligible for a backtest (§1)"
            ),
        )
    outcome_name = candidate.expected_benefit_snapshot.get("outcome_name")
    if outcome_name != _SUPPORTED_OUTCOME:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"backtesting isn't available for outcome {outcome_name!r} yet — only "
                f"{_SUPPORTED_OUTCOME!r} is supported in this contract version (§1.2)"
            ),
        )

    conditions = [_to_condition(cast(dict[str, object], c)) for c in candidate.trigger_conditions]
    frame = load_analytical_frame(_ANALYTICAL_DATASET_DIR)
    outcome = primary_outcome()

    try:
        result = run_backtest(
            frame=frame,
            conditions=conditions,
            outcome=outcome,
            cost_per_review_eur=cost_per_review_eur,
        )
    except ValueError as exc:
        run = PolicyBacktestRunModel(
            id=uuid4(),
            policy_candidate_id=candidate.id,
            cost_per_review_eur=cost_per_review_eur,
            status="failed",
            backtest_result=None,
            failure_reason=str(exc),
        )
    else:
        snapshot = PolicyCandidateBacktestSnapshot.model_validate(result.to_dict())
        run = PolicyBacktestRunModel(
            id=uuid4(),
            policy_candidate_id=candidate.id,
            cost_per_review_eur=cost_per_review_eur,
            status="completed",
            backtest_result=snapshot.model_dump(mode="json"),
            failure_reason=None,
        )

    session.add(run)
    session.flush()
    return run
