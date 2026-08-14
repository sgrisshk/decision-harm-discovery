"""Deterministic decision rules of the validation contract (TASK-018).

Every function here is pure and reproducible: the same gate results always produce the same
evidence level and the same policy readiness. No estimate, interval, or grade may be produced by
a generative model or by hand.
"""

from __future__ import annotations

import math
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
    """Two-sided bootstrap p-value for a null of zero effect, by empirical tail count.

    Computed by inverting the replicate distribution and floored at ``1 / (B + 1)``: a resampling
    procedure cannot report more precision than it has replicates.

    **Not the source for gate G05 as of CONTRACT_VERSION 1.1.0.** Its floor is a hard resolution
    limit — a p-value this small or smaller cannot be distinguished from an arbitrarily smaller
    true p-value no matter how extreme the underlying effect is — and that floor is coarser than
    what Benjamini-Hochberg correction requires once ``family_size`` is in the low thousands
    (ADR-014). Use :func:`normal_approx_two_sided_p` for anything that feeds a multiple-comparison
    correction over a large family. This function remains correct and useful on its own terms —
    an exact, assumption-free tail probability at whatever resolution ``B`` provides — for
    small-family or purely diagnostic use.
    """
    total = len(replicates)
    if total == 0:
        raise ValueError("bootstrap p-value requires at least one replicate")
    at_or_below = sum(1 for value in replicates if value <= 0.0)
    at_or_above = sum(1 for value in replicates if value >= 0.0)
    raw = 2.0 * min(at_or_below, at_or_above) / total
    return min(1.0, max(raw, 1.0 / (total + 1)))


def bootstrap_standard_error(replicates: Sequence[float]) -> float:
    """Sample standard deviation of a set of bootstrap replicates.

    This is the standard cluster-bootstrap estimate of the sampling-distribution standard error of
    whatever statistic the replicates are draws of (e.g. a cluster-resampled mean difference). It
    is a moment estimate, not a tail count, so — unlike :func:`bootstrap_two_sided_p` — it does not
    saturate at a resolution floor tied to the replicate count; it converges to the true SE as
    ``B`` grows, at the ordinary Monte Carlo rate, regardless of how extreme the underlying effect
    is.
    """
    count = len(replicates)
    if count < 2:
        return math.inf
    mean = sum(replicates) / count
    variance = sum((value - mean) ** 2 for value in replicates) / (count - 1)
    return math.sqrt(variance)


def normal_approx_two_sided_p(point_estimate: float, standard_error: float) -> float:
    """Two-sided Wald p-value: point estimate vs. its bootstrap standard error, normal reference.

    This is the canonical p-value source for gate G05 as of ``CONTRACT_VERSION >= "1.1.0"``
    (ADR-014/ADR-015). It replaces :func:`bootstrap_two_sided_p` for multiplicity correction: the
    empirical method's resolution floor of ``1/(B+1)`` cannot be adjusted below itself no matter
    how large the true effect is, which makes it structurally incapable of surviving
    Benjamini-Hochberg correction once ``family_size`` is in the low thousands. This function has
    no such floor — it is a closed-form transform of the standard normal tail via ``math.erfc``,
    resolvable in double-precision arithmetic down to underflow at roughly ``z ~= 38``
    (``p ~= 1e-315``), which covers every family size this system is expected to produce many
    orders of magnitude over. ``math.erfc`` (the complementary error function), not ``1 -
    math.erf(...)``, is what supplies that range: computing the tail as ``1 - erf(x)`` suffers
    catastrophic cancellation once ``erf(x)`` rounds to ``1.0`` in double precision, which happens
    already around ``z ~= 8.3`` — three-plus orders of magnitude short of the resolution actually
    available. See ``docs/analytics/validation-contract.md`` §4a for the precision derivation and
    the worked comparison of both formulations.

    The bootstrap procedure itself — clustering, replicate count, seed — is unchanged; only how a
    replicate set becomes a p-value changed. ``standard_error`` should come from
    :func:`bootstrap_standard_error` applied to the same replicates used for the confidence
    interval, so the interval and the p-value are consistent with each other.
    """
    if standard_error <= 0.0:
        return 0.0 if point_estimate != 0.0 else 1.0
    z = abs(point_estimate) / standard_error
    return max(0.0, math.erfc(z / math.sqrt(2.0)))


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
