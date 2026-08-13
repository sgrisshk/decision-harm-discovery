"""Deterministic decision rules of the validation contract (TASK-018).

Every function here is pure and reproducible: the same gate results always produce the same
evidence level and the same policy readiness. No estimate, interval, or grade may be produced by
a generative model or by hand.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from policy_schemas.domain import EvidenceLevel

from policy_analytics.validation.contract import (
    DESIGN_CEILING,
    GATE_SPECS,
    LEVEL_ORDER,
    LEVEL_REQUIREMENTS,
    FailureAction,
    GateId,
    GateOutcome,
    GateResult,
    IdentificationDesign,
    PolicyReadiness,
)

ALL_GATE_IDS: frozenset[GateId] = frozenset(spec.gate_id for spec in GATE_SPECS)


def benjamini_hochberg_adjusted(
    p_values: Sequence[float], family_size: int | None = None
) -> tuple[float, ...]:
    """Return BH-adjusted p-values in input order.

    ``family_size`` is the number of hypotheses the search actually evaluated, which is normally
    larger than the number of candidates reported. It defaults to ``len(p_values)`` and may never
    be smaller: reporting only the survivors of a large search does not shrink the family.
    """
    count = len(p_values)
    if count == 0:
        return ()
    if any(not 0.0 <= value <= 1.0 for value in p_values):
        raise ValueError("p-values must lie in [0, 1]")
    size = count if family_size is None else family_size
    if size < count:
        raise ValueError("family_size cannot be smaller than the number of reported p-values")

    order = sorted(range(count), key=lambda index: p_values[index])
    adjusted = [1.0] * count
    running_minimum = 1.0
    for rank, index in reversed(list(enumerate(order, start=1))):
        scaled = min(1.0, p_values[index] * size / rank)
        running_minimum = min(running_minimum, scaled)
        adjusted[index] = running_minimum
    return tuple(adjusted)


def survives_fdr(adjusted_p_values: Iterable[float], alpha: float) -> tuple[bool, ...]:
    """Flag which BH-adjusted p-values clear the false-discovery-rate threshold."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between 0 and 1")
    return tuple(value <= alpha for value in adjusted_p_values)


def bootstrap_two_sided_p(replicates: Sequence[float]) -> float:
    """Two-sided bootstrap p-value for a null of zero effect.

    Computed by inverting the replicate distribution and floored at ``1 / (B + 1)``: a resampling
    procedure cannot report more precision than it has replicates.
    """
    total = len(replicates)
    if total == 0:
        raise ValueError("bootstrap p-value requires at least one replicate")
    at_or_below = sum(1 for value in replicates if value <= 0.0)
    at_or_above = sum(1 for value in replicates if value >= 0.0)
    raw = 2.0 * min(at_or_below, at_or_above) / total
    return min(1.0, max(raw, 1.0 / (total + 1)))


def _result_map(results: Iterable[GateResult]) -> dict[GateId, GateResult]:
    mapping: dict[GateId, GateResult] = {}
    for result in results:
        if result.gate_id in mapping:
            raise ValueError(f"duplicate gate result for {result.gate_id}")
        mapping[result.gate_id] = result
    missing = ALL_GATE_IDS - mapping.keys()
    if missing:
        names = ", ".join(sorted(gate.value for gate in missing))
        raise ValueError(f"validation is incomplete; missing gate results: {names}")
    return mapping


def evidence_ceiling(
    results: Iterable[GateResult], design: IdentificationDesign
) -> EvidenceLevel | None:
    """Highest level the candidate could reach, given failures and the identification design.

    Returns ``None`` when a rejecting gate failed, meaning no finding may be published at all.
    """
    mapping = _result_map(results)
    ceiling = DESIGN_CEILING[design]
    for spec in GATE_SPECS:
        if mapping[spec.gate_id].satisfied:
            continue
        if spec.on_failure is FailureAction.REJECT:
            return None
        cap = spec.max_level_on_failure
        if spec.on_failure is FailureAction.READINESS_ONLY or cap is None:
            continue
        if LEVEL_ORDER.index(cap) < LEVEL_ORDER.index(ceiling):
            ceiling = cap
    return ceiling


def classify_evidence_level(
    results: Iterable[GateResult], design: IdentificationDesign
) -> EvidenceLevel | None:
    """Assign exactly one evidence level, or ``None`` when the candidate is rejected.

    A level is reached only when every gate it requires — cumulatively, including all lower
    levels — is satisfied, and the level is at or below the ceiling from failures and design.
    """
    mapping = _result_map(results)
    ceiling = evidence_ceiling(results, design)
    if ceiling is None:
        return None

    assigned: EvidenceLevel | None = None
    for level in LEVEL_ORDER:
        if LEVEL_ORDER.index(level) > LEVEL_ORDER.index(ceiling):
            break
        if all(mapping[gate].satisfied for gate in LEVEL_REQUIREMENTS[level]):
            assigned = level
        else:
            break
    return assigned


def warnings_from(results: Iterable[GateResult]) -> tuple[str, ...]:
    """Caveats that must be shown with the finding: every WARN and every failure."""
    mapping = _result_map(results)
    messages: list[str] = []
    for spec in GATE_SPECS:
        result = mapping[spec.gate_id]
        if result.outcome is GateOutcome.PASS:
            continue
        detail = f": {result.detail}" if result.detail else ""
        messages.append(f"{spec.gate_id.value} {result.outcome.value}{detail}")
    return tuple(messages)


def assign_policy_readiness(
    level: EvidenceLevel | None,
    results: Iterable[GateResult],
    *,
    operationally_feasible: bool,
    backtest_net_positive: bool | None = None,
) -> PolicyReadiness:
    """Map evidence and materiality onto what the business may do with the finding.

    Materiality comes from the economic gate, not from an opinion. ``backtest_net_positive`` is
    ``None`` until a policy backtest exists (TASK-032); without one, nothing reaches
    ``HIGH_CONFIDENCE``.
    """
    mapping = _result_map(results)
    if level is None:
        return PolicyReadiness.NOT_READY
    if not mapping[GateId.ECONOMIC_MATERIALITY].satisfied:
        return PolicyReadiness.NOT_READY

    rank = LEVEL_ORDER.index(level)
    if rank <= LEVEL_ORDER.index(EvidenceLevel.PREDICTIVE):
        return PolicyReadiness.EXPERIMENT_ONLY
    if rank == LEVEL_ORDER.index(EvidenceLevel.ADJUSTED_OBSERVATIONAL):
        return (
            PolicyReadiness.SHADOW_POLICY
            if operationally_feasible
            else PolicyReadiness.EXPERIMENT_ONLY
        )
    if operationally_feasible and backtest_net_positive is True:
        return PolicyReadiness.HIGH_CONFIDENCE
    return PolicyReadiness.SHADOW_POLICY
