"""TASK-107 Phase 2a: benchmark v2 scorer core (pure, no I/O, no engine).

Implements the recovery contract fixed by `ADR-107` (D2, D3, D5, D6, D7 and the author pins) on top
of `docs/benchmark/task-107-benchmark-v2-specification.md` (sections 2 ii, 3.3, 5, 10). The v1
scorer (`scripts/evaluate_benchmark.py`) is untouched; this module lives beside it.

Three separate recovery levels, never blended and never printed as a bare ratio:

* **Coverage** (soft, unchanged from v1): `recall(C, P) = |E(C) & A_P| / |A_P| >= 0.5`.
* **Specific**: exposure-Jaccard `J_e(C, P) >= theta_J` (0.50) AND effective-condition precision
  `Cp(C, P) >= theta_p` (1.00) with a non-empty effective rule `K(C)` AND the candidate reaches
  `predictive_association` or above under the real validation (headline; ADR-107 D7 wording: "N/M
  benchmark targets reached predictive_association under the v2 recovery contract").
* **Exact** (strict diagnostic): a bijection between the candidate's RAW conditions and the target's
  canonical in-language conditions (numeric tolerance `eta`), plus exposure equivalence `eps_x`.
  The bijection is required BEFORE any vacuity relaxation; a candidate that would only match after
  vacuous conditions are dropped is reported as `exact_after_vacuity` and never counted as Exact.
  The truth's own conditions are never relaxed, so removing a weak true condition can never turn a
  near-exact candidate into an exact one.

**Vacuity** (spec 3.3, Rev 1): sequential and deterministic. Compute `g(c) - 1` for every
condition of the current rule (`g(c) = |E(rule without c)| / |E(rule)|`); if none is below `nu`
stop, otherwise drop the single condition with the smallest `g(c) - 1` (ties: feature, operator,
value) and repeat.

**Trap classification** (ADR-107 author pin: strict). `trap_hit(C, T)` iff `T`'s literal is a
condition of `C` or `J(E(C), E(L)) >= theta_T`; it is exempt only if some target `P` whose rule
contains that literal has `J_e >= theta_J`, `Cp >= theta_p`, non-empty `K(C)` (the metric match) AND
`C` reaches `predictive_association` or above (the validation clause). Geometric similarity to a
positive never cancels trap semantics on its own.

**Pinned readings (Rev 2, flagged for the reviewer)**
1. Credit: each candidate is credited to at most one scoreable target, the one with the highest
   `J_e` (ties: target id); the Specific test is then applied to that target only. Other targets
   for which the metric part of SPEC also holds are reported
   (`specific_metric_also_holds_for`), not credited.
2. Pool: Coverage, Specific and Exact all use the same candidate pool: every emitted candidate
   that is not a genuine trap hit (`trap_hit` and not exempt). Coverage does not require
   validation.
3. `mu(c, t)` (condition match) requires the same feature, compatible direction (`ge`/`ge`,
   `lt`/`lt`, or `eq`/`in` with `eq`/`in`) and nested, non-empty marginal row sets. Thresholds are
   not compared.
4. `S subset of C` (Specific targets inside Coverage targets) is guaranteed and enforced only for
   `theta_J >= 0.5`; at lower sensitivities the check is reported, not enforced.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

BENCHMARK_ID = "travel-v2"
RECOVERY_CONTRACT_LABEL = "v2 recovery contract"

PREDICTIVE_OR_ABOVE: tuple[str, ...] = (
    "predictive_association",
    "adjusted_observational_association",
    "quasi_causal_evidence",
    "experimental_evidence",
)
PROMOTED_READINESS: tuple[str, ...] = ("shadow_policy", "high_confidence")

STRATA: tuple[str, ...] = ("core", "challenge", "declared_overlap", "out_of_language")
#: Strata named by ADR-107 D3/D6; `out_of_language` is the spec's invariant (iii) `L` suite and is
#: reported on its own only if present.
SENSITIVITY_THETAS: tuple[float, ...] = (0.3, 0.5, 0.7)


@dataclass(frozen=True, slots=True)
class Constants:
    """ADR-107 specification constants. Changing any requires a new dated ADR."""

    coverage_recall: float = 0.5
    theta_j: float = 0.50
    theta_p: float = 1.00
    nu: float = 0.05
    eta: float = 0.15
    eps_x: float = 0.10
    theta_t: float = 0.90
    broad_min_targets: int = 3
    min_exposed_records: int = 50  # == ValidationThresholds.min_exposed_records
    min_dev_n: int = 40  # == DiscoveryConfig.min_n


CONSTANTS = Constants()


@dataclass(frozen=True, slots=True)
class CondSpec:
    """A condition on a dataset column. `operator` in eq / ge / lt / in (`in`: tuple value)."""

    feature: str
    operator: str
    value: Any

    def sort_key(self) -> tuple[str, str, str]:
        return (self.feature, self.operator, repr(self.value))

    def render(self) -> str:
        return f"{self.feature} {self.operator} {self.value!r}"


class RowSpace:
    """The cohort as bitmasks. `columns` maps column name -> per-row values (row-aligned)."""

    def __init__(self, columns: Mapping[str, Sequence[Any]], dev_mask: int | None = None) -> None:
        lengths = {len(v) for v in columns.values()}
        if len(lengths) != 1:
            raise ValueError("columns must be non-empty and row-aligned")
        self.n = lengths.pop()
        self.full = (1 << self.n) - 1
        self.columns = columns
        self.dev_mask = self.full if dev_mask is None else dev_mask
        self._cache: dict[CondSpec, int] = {}

    def cond_mask(self, cond: CondSpec) -> int:
        cached = self._cache.get(cond)
        if cached is not None:
            return cached
        values = self.columns[cond.feature]
        mask = 0
        for i, x in enumerate(values):
            if _row_matches(x, cond):
                mask |= 1 << i
        self._cache[cond] = mask
        return mask

    def rule_mask(self, conds: Sequence[CondSpec]) -> int:
        mask = self.full
        for cond in conds:
            mask &= self.cond_mask(cond)
        return mask

    def ids_to_mask(self, index_of: Mapping[str, int], ids: Sequence[str]) -> int:
        mask = 0
        for record_id in ids:
            mask |= 1 << index_of[record_id]
        return mask


def _row_matches(x: Any, cond: CondSpec) -> bool:
    if x is None:
        return False
    v = cond.value
    if cond.operator == "eq":
        if isinstance(v, bool) or isinstance(x, bool):
            return x is v
        return bool(x == v)
    if cond.operator == "in":
        return any(_row_matches(x, CondSpec(cond.feature, "eq", item)) for item in v)
    if isinstance(x, bool) or not isinstance(x, int | float):
        return False
    if cond.operator == "ge":
        return bool(x >= v)
    if cond.operator == "lt":
        return bool(x < v)
    raise ValueError(f"unsupported operator {cond.operator!r}")


def popcount(mask: int) -> int:
    return mask.bit_count()


def jaccard(a: int, b: int) -> float:
    union = popcount(a | b)
    return popcount(a & b) / union if union else 0.0


def nested(a: int, b: int) -> bool:
    if a == 0 or b == 0:
        return False
    inter = a & b
    return inter in (a, b)


# ---------------------------------------------------------------- rule grammar (ground truth) --
_CLAUSE = re.compile(r"^\s*(?P<f>\w+)\s*(?P<op>>=|<|=|\bIN\b)\s*(?P<v>.*?)\s*$")


def _coerce(raw: str) -> Any:
    if raw == "true":
        return True
    if raw == "false":
        return False
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            continue
    return raw


def parse_rule(rule: str) -> tuple[CondSpec, ...]:
    """Ground-truth grammar: clauses joined by ` AND `: `a=x`, `b>=3`, `c<23`, `m IN [1,2,12]`."""
    out: list[CondSpec] = []
    for clause in rule.split(" AND "):
        parsed = _CLAUSE.match(clause)
        if parsed is None:
            raise ValueError(f"unparsable clause {clause!r}")
        op, raw = parsed["op"], parsed["v"]
        if op == "IN":
            items = tuple(_coerce(x.strip()) for x in raw.strip("[]").split(","))
            out.append(CondSpec(parsed["f"], "in", items))
        else:
            out.append(CondSpec(parsed["f"], {"=": "eq", ">=": "ge", "<": "lt"}[op], _coerce(raw)))
    return tuple(out)


# ------------------------------------------------------------------------------ data model ------
@dataclass(frozen=True, slots=True)
class Target:
    """A ground-truth positive. `conditions` = the canonical true conditions `T_P` (may include
    `in` conditions). `canonical_in_language` = the declared engine-language form `T_P^` used by
    Exact, or None when the target has no in-language form (Exact undefined)."""

    target_id: str
    stratum: str
    conditions: tuple[CondSpec, ...]
    affected: int
    canonical_in_language: tuple[CondSpec, ...] | None = None

    def literals(self) -> frozenset[CondSpec]:
        return frozenset(c for c in self.conditions if c.operator == "eq")


@dataclass(frozen=True, slots=True)
class Trap:
    trap_id: str
    literal: CondSpec


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    conditions: tuple[CondSpec, ...]
    evidence_level: str | None
    policy_readiness: str = "unknown"

    @property
    def validated(self) -> bool:
        return self.evidence_level in PREDICTIVE_OR_ABOVE


# ------------------------------------------------------------------------------- vacuity --------
@dataclass(frozen=True, slots=True)
class EffectiveRule:
    conditions: tuple[CondSpec, ...]
    dropped: tuple[CondSpec, ...]


def effective_rule(
    space: RowSpace, conds: Sequence[CondSpec], nu: float = CONSTANTS.nu
) -> EffectiveRule:
    """Sequential vacuity (spec 3.3 Rev 1). A rule whose exposure is empty has no vacuous condition
    (removal grows an empty set without bound)."""
    current = list(conds)
    dropped: list[CondSpec] = []
    while current:
        exposed = popcount(space.rule_mask(current))
        if exposed == 0:
            break
        growth: list[tuple[float, tuple[str, str, str], CondSpec]] = []
        for i, cond in enumerate(current):
            rest = current[:i] + current[i + 1 :]
            grown = popcount(space.rule_mask(rest)) / exposed - 1.0
            growth.append((grown, cond.sort_key(), cond))
        least = min(growth, key=lambda g: (g[0], g[1]))
        if least[0] >= nu:
            break
        current.remove(least[2])
        dropped.append(least[2])
    return EffectiveRule(tuple(current), tuple(dropped))


# ---------------------------------------------------------------------------- pair metrics ------
def _compatible(a: CondSpec, b: CondSpec) -> bool:
    if a.feature != b.feature:
        return False
    if a.operator in ("eq", "in") and b.operator in ("eq", "in"):
        return True
    return a.operator == b.operator and a.operator in ("ge", "lt")


def conditions_match(space: RowSpace, c: CondSpec, t: CondSpec) -> bool:
    """`mu(c, t)`: same feature, compatible direction, nested non-empty marginal row sets."""
    return _compatible(c, t) and nested(space.cond_mask(c), space.cond_mask(t))


@dataclass(frozen=True, slots=True)
class PairMetrics:
    recall: float
    precision: float
    j_e: float
    cp: float
    cr: float
    n_effective: int
    n_exposed: int


def pair_metrics(
    space: RowSpace, effective: Sequence[CondSpec], exposed: int, target: Target
) -> PairMetrics:
    inter = popcount(exposed & target.affected)
    n_a = popcount(target.affected)
    n_e = popcount(exposed)
    k = len(effective)
    hit_c = sum(any(conditions_match(space, c, t) for t in target.conditions) for c in effective)
    hit_t = sum(any(conditions_match(space, c, t) for c in effective) for t in target.conditions)
    return PairMetrics(
        recall=inter / n_a if n_a else 0.0,
        precision=inter / n_e if n_e else 0.0,
        j_e=jaccard(exposed, target.affected),
        cp=hit_c / k if k else 0.0,
        cr=hit_t / len(target.conditions) if target.conditions else 0.0,
        n_effective=k,
        n_exposed=n_e,
    )


def metric_specific(pm: PairMetrics, theta_j: float, theta_p: float) -> bool:
    """Metric part of SPEC: J_e >= theta_J and Cp >= theta_p and K non-empty."""
    return pm.n_effective > 0 and pm.j_e >= theta_j and pm.cp >= theta_p


# ---------------------------------------------------------------------------------- exact ------
def _pair_ok(space: RowSpace, c: CondSpec, t: CondSpec, eta: float) -> bool:
    if c.feature != t.feature:
        return False
    if c.operator != t.operator:
        return False
    mc, mt = space.cond_mask(c), space.cond_mask(t)
    if mt == 0:
        return False
    if c.operator in ("eq", "in"):
        return mc == mt
    return popcount(mc ^ mt) <= eta * popcount(mt)


def bijection_exists(
    space: RowSpace, conds: Sequence[CondSpec], truth: Sequence[CondSpec], eta: float
) -> bool:
    """A perfect matching between `conds` and `truth` (same feature/operator; categorical rows
    equal; numeric row-set symmetric difference <= eta * |rows(truth cond)|)."""
    if len(conds) != len(truth) or not truth:
        return False
    return any(
        all(_pair_ok(space, c, t, eta) for c, t in zip(perm, truth, strict=True))
        for perm in itertools.permutations(conds)
    )


@dataclass(frozen=True, slots=True)
class ExactVerdict:
    exact: bool
    exact_after_vacuity: bool


def exact_verdict(
    space: RowSpace,
    candidate_conditions: Sequence[CondSpec],
    effective: Sequence[CondSpec],
    exposed: int,
    target: Target,
    const: Constants = CONSTANTS,
) -> ExactVerdict | None:
    """None when the target has no in-language canonical form (Exact undefined)."""
    truth = target.canonical_in_language
    if truth is None:
        return None
    tolerance = const.eps_x * popcount(target.affected)
    equivalent = popcount(exposed ^ space.rule_mask(truth)) <= tolerance
    strict = equivalent and bijection_exists(space, candidate_conditions, truth, const.eta)
    if strict:
        return ExactVerdict(True, False)
    relaxed = (
        list(effective) != list(candidate_conditions)
        and equivalent
        and bijection_exists(space, effective, truth, const.eta)
    )
    return ExactVerdict(False, relaxed)


# ---------------------------------------------------------------------------------- scoring -----
class InvariantViolation(AssertionError):
    """A scorer invariant failed: a scorer bug, not a finding (spec sections 3.3 and 5)."""


@dataclass(slots=True)
class CandidateRecord:
    candidate_id: str
    conditions: list[str]
    evidence_level: str | None
    policy_readiness: str
    validated: bool
    n_exposed: int
    effective_conditions: list[str]
    vacuous_dropped: list[str]
    trap_literal_hits: list[str]
    trap_equivalence_hits: list[str]
    trap_hits: list[str]
    exempted_traps: list[dict[str, str]]
    in_pool: bool
    covers_targets: list[str]
    broad: bool
    credited_target: str | None
    best_j: float
    per_target: dict[str, dict[str, float]]
    specific_targets_by_theta: dict[str, str | None]
    specific_metric_also_holds_for: list[str]
    exact_targets: list[str]
    exact_after_vacuity_targets: list[str]


@dataclass(slots=True)
class StratumResult:
    stratum: str
    scoreable: list[str]
    unscoreable: list[str]
    coverage_targets: list[str]
    specific_targets: dict[str, list[str]]  # keyed by theta_J string
    exact_targets: list[str]
    exact_after_vacuity_targets: list[str]
    exact_defined_targets: list[str]
    specific_not_in_coverage: dict[str, list[str]] = field(default_factory=lambda: {})


def _is_scoreable(space: RowSpace, target: Target, const: Constants) -> bool:
    return (
        popcount(target.affected) >= const.min_exposed_records
        and popcount(target.affected & space.dev_mask) >= const.min_dev_n
    )


def _tkey(theta: float) -> str:
    return f"{theta:.2f}"


def score(
    space: RowSpace,
    targets: Sequence[Target],
    traps: Sequence[Trap],
    candidates: Sequence[Candidate],
    const: Constants = CONSTANTS,
    thetas: Sequence[float] = SENSITIVITY_THETAS,
) -> dict[str, Any]:
    """Score one seed. Returns a JSON-serialisable dict; raises `InvariantViolation` on a bug."""
    scoreable = {t.target_id: t for t in targets if _is_scoreable(space, t, const)}
    unscoreable = sorted(t.target_id for t in targets if t.target_id not in scoreable)
    trap_masks = {tr.trap_id: space.cond_mask(tr.literal) for tr in traps}
    records: list[CandidateRecord] = []
    for cand in candidates:
        exposed = space.rule_mask(cand.conditions)
        eff = effective_rule(space, cand.conditions, const.nu)
        per_target: dict[str, dict[str, float]] = {}
        metrics: dict[str, PairMetrics] = {}  # every target (exemption); credit uses scoreable only
        for target in targets:
            tid = target.target_id
            pm = pair_metrics(space, eff.conditions, exposed, target)
            metrics[tid] = pm
            per_target[tid] = {
                "recall": pm.recall,
                "precision": pm.precision,
                "j_e": pm.j_e,
                "cp": pm.cp,
                "cr": pm.cr,
            }
        # --- strict trap classification (ADR-107) ------------------------------------------------
        cand_set = set(cand.conditions)
        literal_hits = sorted(tr.trap_id for tr in traps if tr.literal in cand_set)
        equiv_hits = sorted(
            tr.trap_id
            for tr in traps
            if tr.trap_id not in literal_hits
            and jaccard(exposed, trap_masks[tr.trap_id]) >= const.theta_t
        )
        exempted: list[dict[str, str]] = []
        genuine: list[str] = []
        for trap in traps:
            if trap.trap_id not in literal_hits and trap.trap_id not in equiv_hits:
                continue
            exempt_by: str | None = None
            if cand.validated:
                for target in sorted(targets, key=lambda t: t.target_id):
                    if trap.literal in target.literals() and metric_specific(
                        metrics[target.target_id], const.theta_j, const.theta_p
                    ):
                        exempt_by = target.target_id
                        break
            if exempt_by is None:
                genuine.append(trap.trap_id)
            else:
                exempted.append({"trap": trap.trap_id, "pattern": exempt_by})
        in_pool = not genuine
        covers = sorted(
            tid
            for tid, pm in metrics.items()
            if tid in scoreable and pm.recall >= const.coverage_recall
        )
        # --- credit: highest J_e, ties by target id -------------------------------------------
        credited: str | None = None
        best_j = 0.0
        for tid in sorted(scoreable):
            if metrics[tid].j_e > best_j:
                best_j, credited = metrics[tid].j_e, tid
        spec_by_theta: dict[str, str | None] = {}
        for theta in thetas:
            ok = (
                in_pool
                and cand.validated
                and credited is not None
                and metric_specific(metrics[credited], theta, const.theta_p)
            )
            spec_by_theta[_tkey(theta)] = credited if ok else None
        also = sorted(
            tid
            for tid, pm in metrics.items()
            if tid in scoreable
            and tid != credited
            and metric_specific(pm, const.theta_j, const.theta_p)
        )
        exact_ok: list[str] = []
        exact_relaxed: list[str] = []
        if in_pool:
            for tid, target in scoreable.items():
                verdict = exact_verdict(
                    space, cand.conditions, eff.conditions, exposed, target, const
                )
                if verdict is None:
                    continue
                if verdict.exact:
                    exact_ok.append(tid)
                elif verdict.exact_after_vacuity:
                    exact_relaxed.append(tid)
        records.append(
            CandidateRecord(
                candidate_id=cand.candidate_id,
                conditions=[c.render() for c in cand.conditions],
                evidence_level=cand.evidence_level,
                policy_readiness=cand.policy_readiness,
                validated=cand.validated,
                n_exposed=popcount(exposed),
                effective_conditions=[c.render() for c in eff.conditions],
                vacuous_dropped=[c.render() for c in eff.dropped],
                trap_literal_hits=literal_hits,
                trap_equivalence_hits=equiv_hits,
                trap_hits=genuine,
                exempted_traps=exempted,
                in_pool=in_pool,
                covers_targets=covers if in_pool else [],
                broad=len(covers) >= const.broad_min_targets,
                credited_target=credited,
                best_j=best_j,
                per_target=per_target,
                specific_targets_by_theta=spec_by_theta,
                specific_metric_also_holds_for=also,
                exact_targets=sorted(exact_ok),
                exact_after_vacuity_targets=sorted(exact_relaxed),
            )
        )
    strata = _aggregate(targets, scoreable, records, thetas)
    _check_invariants(strata, records, thetas)
    safety = _safety(traps, candidates, records)
    return {
        "benchmark_id": BENCHMARK_ID,
        "comparable_to_other_benchmark_ids": False,
        "constants": {
            "coverage_recall": const.coverage_recall,
            "theta_j": const.theta_j,
            "theta_p": const.theta_p,
            "nu": const.nu,
            "eta": const.eta,
            "eps_x": const.eps_x,
            "theta_t": const.theta_t,
            "sensitivity_theta_j": list(thetas),
        },
        "unscoreable_targets": unscoreable,
        "strata": {
            name: {
                "stratum": s.stratum,
                "scoreable": s.scoreable,
                "unscoreable": s.unscoreable,
                "coverage_targets": s.coverage_targets,
                "specific_targets": s.specific_targets,
                "exact_targets": s.exact_targets,
                "exact_after_vacuity_targets": s.exact_after_vacuity_targets,
                "exact_defined_targets": s.exact_defined_targets,
                "specific_not_in_coverage": s.specific_not_in_coverage,
            }
            for name, s in strata.items()
        },
        "safety": safety,
        "candidates": [_asdict(r) for r in records],
    }


def _asdict(r: CandidateRecord) -> dict[str, Any]:
    return {name: getattr(r, name) for name in CandidateRecord.__slots__}


def _aggregate(
    targets: Sequence[Target],
    scoreable: Mapping[str, Target],
    records: Sequence[CandidateRecord],
    thetas: Sequence[float],
) -> dict[str, StratumResult]:
    out: dict[str, StratumResult] = {}
    for stratum in STRATA:
        members = [t for t in targets if t.stratum == stratum]
        if not members:
            continue
        ids = sorted(t.target_id for t in members if t.target_id in scoreable)
        cover = sorted({tid for r in records for tid in r.covers_targets if tid in ids})
        spec = {
            _tkey(theta): sorted(
                {
                    tid
                    for r in records
                    if (tid := r.specific_targets_by_theta[_tkey(theta)]) is not None and tid in ids
                }
            )
            for theta in thetas
        }
        exact = sorted({tid for r in records for tid in r.exact_targets if tid in ids})
        relaxed = sorted(
            {tid for r in records for tid in r.exact_after_vacuity_targets if tid in ids}
            - set(exact)
        )
        defined = sorted(
            t.target_id for t in members if t.target_id in ids and t.canonical_in_language
        )
        out[stratum] = StratumResult(
            stratum=stratum,
            scoreable=ids,
            unscoreable=sorted(t.target_id for t in members if t.target_id not in scoreable),
            coverage_targets=cover,
            specific_targets=spec,
            exact_targets=exact,
            exact_after_vacuity_targets=relaxed,
            exact_defined_targets=defined,
            specific_not_in_coverage={k: sorted(set(v) - set(cover)) for k, v in spec.items()},
        )
    return out


def _check_invariants(
    strata: Mapping[str, StratumResult], records: Sequence[CandidateRecord], thetas: Sequence[float]
) -> None:
    for name, s in strata.items():
        for key, spec in s.specific_targets.items():
            if float(key) >= 0.5 - 1e-12 and set(spec) - set(s.coverage_targets):
                raise InvariantViolation(
                    f"stratum {name}: Specific targets outside Coverage at theta_J={key}: "
                    f"{sorted(set(spec) - set(s.coverage_targets))}"
                )
    for r in records:
        for tid in r.specific_targets_by_theta.values():
            if tid is not None and tid != r.credited_target:
                raise InvariantViolation(f"{r.candidate_id}: credited to more than one target")
        for pm in r.per_target.values():
            if not all(0.0 <= v <= 1.0 for v in pm.values()):
                raise InvariantViolation(f"{r.candidate_id}: metric outside [0, 1]")
        if not r.in_pool and (r.covers_targets or any(r.specific_targets_by_theta.values())):
            raise InvariantViolation(f"{r.candidate_id}: trap-excluded candidate credited")
    expected = {_tkey(t) for t in thetas}
    if any(set(s.specific_targets) != expected for s in strata.values()):
        raise InvariantViolation("unexpected sensitivity keys")


def _safety(
    traps: Sequence[Trap], candidates: Sequence[Candidate], records: Sequence[CandidateRecord]
) -> dict[str, Any]:
    promoted = {
        tr.trap_id: any(
            tr.trap_id in r.trap_hits and c.policy_readiness in PROMOTED_READINESS
            for r, c in zip(records, candidates, strict=True)
        )
        for tr in traps
    }
    appeared = {tr.trap_id: any(tr.trap_id in r.trap_hits for r in records) for tr in traps}
    return {
        "trap_appeared": appeared,
        "trap_promoted": promoted,
        "any_trap_promoted": any(promoted.values()),
        "exempted_candidates_to_verify_manually": [
            {"candidate_id": r.candidate_id, "exempted": r.exempted_traps}
            for r in records
            if r.exempted_traps
        ],
    }


# ---------------------------------------------------------------------------- rendering ---------
_RATIO = re.compile(r"\d+/\d+")
_LABELLED_RATIO = re.compile(r"\d+/\d+ benchmark targets")


def assert_no_bare_ratio(text: str) -> None:
    """Every `N/M` in rendered output must be the head of a labelled `N/M benchmark targets ...`
    phrase. A bare `N/N` (the ADR-106 failure mode) can therefore never be printed."""
    if len(_RATIO.findall(text)) != len(_LABELLED_RATIO.findall(text)):
        raise InvariantViolation("rendered output contains a ratio without its label")


def _ratio(hit: Sequence[str], scoreable: Sequence[str]) -> str:
    return f"{len(hit)}/{len(scoreable)} benchmark targets"


def render_report(result: Mapping[str, Any], seed_label: str = "") -> str:
    """Human-readable report. One block per stratum; strata are never blended."""
    lines: list[str] = []
    tag = f"{BENCHMARK_ID}{' / ' + seed_label if seed_label else ''}"
    broad = [c["candidate_id"] for c in result["candidates"] if c["broad"]]
    for name, s in result["strata"].items():
        scoreable = s["scoreable"]
        if not scoreable:
            lines.append(f"{tag} / {name}: no scoreable benchmark targets in this stratum")
            continue
        consts = result["constants"]
        primary = s["specific_targets"][_tkey(consts["theta_j"])]
        lines.append(
            f"{tag} / {name} / Specific: {_ratio(primary, scoreable)} reached "
            f"predictive_association under the {RECOVERY_CONTRACT_LABEL} "
            f"(theta_J={consts['theta_j']:.2f}, theta_p={consts['theta_p']:.2f}; "
            f"not promotion; targets: {', '.join(primary) or 'none'})"
        )
        cov = _ratio(s["coverage_targets"], scoreable)
        lines.append(
            f"{tag} / {name} / Coverage (soft, not recovery): {cov} "
            f"overlap at least one candidate with recall>=0.5"
            + (f"; broad candidates present: {', '.join(broad)}" if broad else "")
        )
        if s["exact_defined_targets"]:
            exact = _ratio(s["exact_targets"], s["exact_defined_targets"])
            relaxed = ", ".join(s["exact_after_vacuity_targets"]) or "none"
            lines.append(
                f"{tag} / {name} / Exact (strict diagnostic): {exact} matched exactly; "
                f"exact_after_vacuity (not counted): {relaxed}"
            )
        sens = ", ".join(
            f"theta_J={k}: {_ratio(v, scoreable)}" for k, v in sorted(s["specific_targets"].items())
        )
        lines.append(f"{tag} / {name} / Specific sensitivity: {sens}")
    lines.append(f"{tag} / safety: any_trap_promoted={result['safety']['any_trap_promoted']}")
    text = "\n".join(lines)
    assert_no_bare_ratio(text)
    return text
