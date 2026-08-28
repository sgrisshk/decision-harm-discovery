"""POST-HOC DIAGNOSTIC (`TASK-069` research-plan item 7): stage-by-stage decomposition of where
each of travel's scoreable ground-truth patterns dies inside `discovery.engine`'s search.

Not part of the official discovery/blind/validation pipeline. Never runs as part of an official
blind run and never influences one. It re-derives, from already-frozen inputs, the exact search
behind an *already-committed* official run (same dataset identity, seed, config, and
`discovery.engine` code), instrumented to record intermediate state `discover_candidates` computes
internally and then discards: which rules were generated at each depth, which were eligible, which
survived `_select_expansion_beam` into the next depth, and at what rank/score.

**The specific gap this closes.** `scripts/diagnose_candidate_pool_recall.py` (`ADR-038`,
`HANDOFF-055`) answered "is the ceiling in top-K selection or upstream of it" by inspecting the
*final, post-search* eligible pool. That pool is depth-agnostic: a rule absent from it may have been
pruned before it could ever be generated, or generated and found ineligible, or generated, scored,
and simply out-ranked. `TASK-069`'s research plan names that conflation explicitly. This script
therefore traces the search *during* expansion, per depth, so "pruned before reaching depth 2" and
"present but low-ranked at the end" become distinguishable, per pattern.

**Why opening `synthetic_data/evaluation/hidden_ground_truth.json` is legitimate here.** Travel's
hidden ground truth has been legitimately open since `TASK-028`'s first evaluation
(`docs/benchmark/task-029-benchmark-report-v1.md` §1, restricted SHA-256 recorded there), and every
run this script re-derives was frozen and committed via signed receipt
(`scripts/commit_blind_candidates.py`) *before* any evaluation opened it. This is the same
"already frozen, now graded" discipline `scripts/evaluate_benchmark.py` (`TASK-028`),
`ADR-025`/`HANDOFF-054`, `scripts/diagnose_candidate_pool_recall.py` (`ADR-038`/`HANDOFF-055`), and
`scripts/diagnose_g06_task065_b2b.py` (`TASK-067`) already established. This script never selects,
ranks, reports, or modifies an official candidate, and produces no artifact any official metric is
read from.

**Binding constraint from `TASK-069`'s own hard rule, restated because this script is exactly the
file most able to violate it.** `TASK-069` forbids any new search objective, scoring term, or
expansion policy being designed, scoped, or justified by reference to travel's specific pattern
identities or feature values; it permits this benchmark to read those identities *to explain
failures*. Accordingly this script is strictly diagnostic: it proposes no mechanism, tunes no
parameter, and writes nothing into `discovery.engine`. It contains **no hardcoded pattern id,
feature name, threshold, or rule** — every pattern's true condition set is parsed generically out
of `hidden_ground_truth.json`'s own `rule` string at runtime, and every atom it tests comes from
`discovery.engine`'s own `_atoms`. Whoever later designs a replacement mechanism must not carry any
per-pattern fact from this script's output into that mechanism's logic; the output is an
explanation of the current mechanism's failure modes, not a specification for its successor.

**Discipline maintained.** The traced search calls `discovery.engine`'s own
`_atoms`/`_metric`/`_eligible`/`_development_score`/`_select_expansion_beam`/`_temporal_consistency`/
`_apply_stability_credit`/`_greedy_diverse_select`/`_apply_feature_identity_cap` verbatim — nothing
here reimplements the search's arithmetic, only the same control flow `discover_candidates` uses,
with recording added. Fidelity is asserted, not assumed: the script refuses to report anything
unless (a) the reproduced `evaluated_hypotheses` equals the committed run's own figure and (b) the
reproduced final selection is condition-for-condition identical to the committed
`candidates.json`, whose SHA-256 is re-verified against its frozen `hashes.json` first.

**One deliberately disclosed diagnostic-only derivation.** A true pattern condition may reference a
field the analytical contract does not expose as a `DECISION_TIME` feature. Where such a field is a
calendar decomposition of a date column the frame does carry (`<x>_month` from `<x>_date`), this
script derives it *solely* to report how much narrower the true rule is than anything the search's
vocabulary can express. That derived column is never added to the search vocabulary, never becomes
an atom, and never enters any traced rule — it exists only to quantify the specificity gap.

**Stage 6 is an explicit counterfactual, labelled as such.** For patterns whose best representable
rule never reaches final selection, this script additionally asks "*had* it been selected, would it
have validated?" by calling `validation.apply.run_validation` — the real, unmodified contract — on a
throwaway candidate document containing those rules. That is a hypothetical, not a `TASK-019` run:
it produces no artifact under `artifacts/validation/`, and its Benjamini-Hochberg adjustment runs
over a different reported-p-value set than the official run's (family size is held at the committed
run's own `evaluated_hypotheses`). It answers "is search even the binding constraint for this
pattern", which a first-failing-stage ladder alone cannot.

Usage:
  uv run python scripts/diagnose_oracle_decomposition.py
  uv run python scripts/diagnose_oracle_decomposition.py \\
      --run-id task-064-beam-20260822-001 \\
      --raw-output docs/benchmark/task-069-oracle-decomposition-raw.json
"""

# pyright: reportPrivateUsage=false
# Reuses discovery.engine's own private search functions verbatim rather than reimplementing them
# (see module docstring) — deliberate, and the same precedent `diagnose_candidate_pool_recall.py`
# and `diagnose_g06_task065_b2b.py` already set, not a layering violation to ignore case by case.
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    DISCOVERY_METHOD_VERSION,
    Condition,
    DiscoveryConfig,
    Operator,
    SplitMetric,
    _apply_feature_identity_cap,
    _apply_stability_credit,
    _atoms,
    _development_score,
    _eligible,
    _greedy_diverse_select,
    _metric,
    _percentile,
    _select_expansion_beam,
    _temporal_consistency,
)
from policy_analytics.outcomes import (  # noqa: E402
    outcome_definition_from_manifest,
    primary_outcome,
)
from policy_analytics.validation.apply import load_analytical_frame, run_validation  # noqa: E402

DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
BLIND_ROOT = REPOSITORY / "artifacts/blind"
DEFAULT_RUN_ID = "task-064-beam-20260822-001"
DEFAULT_VALIDATION_PATH = (
    REPOSITORY / "artifacts/validation/task-019-official-20260822-task-064-beam-001.json"
)
DEFAULT_EVALUATION_PATH = REPOSITORY / "artifacts/evaluation/task-028-task-064-beam-001.json"
DEFAULT_RAW_OUTPUT = REPOSITORY / "docs/benchmark/task-069-oracle-decomposition-raw.json"

#: `P05`/`P07` are excluded from the scoreable denominator, the same pre-registered convention
#: `TASK-028`/`scripts/evaluate_benchmark.py` and `diagnose_candidate_pool_recall.py` already use.
#: Listed here as a scoring convention, not as pattern-specific search knowledge; the script still
#: traces every pattern in the file and only marks these two non-scoreable in its output.
NON_SCOREABLE_PATTERNS = ("P05", "P07")
#: `scripts/evaluate_benchmark.py`'s own pre-registered candidate/pattern matching statistic.
FULL_MATCH_RECALL = 0.5

_RULE_TOKEN = re.compile(
    r"^\s*(?P<feature>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<operator>>=|<=|!=|=|>|<|\bIN\b)\s*(?P<value>.+?)\s*$"
)


# --------------------------------------------------------------------------------------------
# Ground-truth rule parsing (generic: no pattern id, feature, or value is hardcoded anywhere)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TrueCondition:
    """One conjunct of a ground-truth pattern's own `rule` string, parsed generically."""

    feature: str
    operator: str
    value: object

    def render(self) -> str:
        return f"{self.feature}{self.operator}{self.value}"


def _coerce(raw: str) -> object:
    text = raw.strip().strip("'\"")
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_true_rule(rule: str) -> tuple[TrueCondition, ...]:
    """Parse `hidden_ground_truth.json`'s own `rule` string into structured conjuncts.

    Supports the grammar that file actually uses — `feature=value`, `feature>=value`,
    `feature<value`, and `feature IN [a,b,c]`, joined by ` AND ` — plus `>`/`<=`/`!=` for
    completeness. Raises rather than silently dropping a conjunct it cannot read: a
    mis-parsed rule would understate how specific the true pattern is and quietly bias every
    downstream stage verdict.
    """
    conditions: list[TrueCondition] = []
    for part in re.split(r"\s+AND\s+", rule.strip()):
        match = _RULE_TOKEN.match(part)
        if match is None:
            raise ValueError(f"unparseable ground-truth rule conjunct: {part!r} (in {rule!r})")
        feature = match.group("feature")
        operator = match.group("operator").upper()
        raw_value = match.group("value")
        value: object
        if operator == "IN":
            inner = raw_value.strip().strip("[]")
            value = tuple(_coerce(item) for item in inner.split(",") if item.strip())
        else:
            value = _coerce(raw_value)
        conditions.append(TrueCondition(feature, operator, value))
    if not conditions:
        raise ValueError(f"ground-truth rule parsed to zero conjuncts: {rule!r}")
    return tuple(conditions)


def true_condition_expr(condition: TrueCondition) -> pl.Expr:
    """The exact polars predicate for one true conjunct, used only to measure how much narrower
    the true rule is than its representable projection. Never used to build a search atom."""
    column = pl.col(condition.feature)
    operator = condition.operator
    value = cast(Any, condition.value)
    if operator == "=":
        return cast(pl.Expr, column == value)
    if operator == "!=":
        return cast(pl.Expr, column != value)
    if operator == ">=":
        return cast(pl.Expr, column >= value)
    if operator == ">":
        return cast(pl.Expr, column > value)
    if operator == "<=":
        return cast(pl.Expr, column <= value)
    if operator == "<":
        return cast(pl.Expr, column < value)
    if operator == "IN":
        return column.is_in(list(cast(tuple[Any, ...], condition.value)))
    raise ValueError(f"unsupported ground-truth operator {operator!r}")


# --------------------------------------------------------------------------------------------
# Bitmask row algebra — exact, and fast enough to scan the whole eligible pool
# --------------------------------------------------------------------------------------------


def _mask_int(values: list[bool | None]) -> int:
    """Pack a boolean row mask into one Python integer, bit `i` = row `i`.

    Rule masks are then intersections (`&`) and populations are `int.bit_count()`, which makes a
    full-pool recall scan cheap without approximating anything: identical arithmetic to counting
    the polars mask, cross-checked against it in `_assert_mask_agrees`.
    """
    packed = 0
    for index, value in enumerate(values):
        if value:
            packed |= 1 << index
    return packed


def _frame_mask(frame: pl.DataFrame, expression: pl.Expr) -> int:
    column = frame.select(expression.alias("m"))["m"]
    return _mask_int(cast("list[bool | None]", column.to_list()))


# --------------------------------------------------------------------------------------------
# Traced reproduction of `discover_candidates`
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class SearchTrace:
    """Everything `discover_candidates` computes internally and then throws away."""

    atoms: tuple[Condition, ...]
    evaluated: int
    scored: dict[tuple[Condition, ...], tuple[float, SplitMetric]]
    generated_at_depth: dict[int, set[tuple[Condition, ...]]]
    scored_ranked_at_depth: dict[int, list[tuple[Condition, ...]]]
    beam_at_depth: dict[int, list[tuple[Condition, ...]]]
    redundant_at_depth: dict[int, set[tuple[Condition, ...]]]
    selected: list[tuple[Condition, ...]]
    effective_score: dict[tuple[Condition, ...], float]
    phase_floor: dict[str, float]
    phase_reference: dict[str, float]

    @classmethod
    def empty(cls, atoms: tuple[Condition, ...]) -> SearchTrace:
        return cls(
            atoms=atoms,
            evaluated=0,
            scored={},
            generated_at_depth={},
            scored_ranked_at_depth={},
            beam_at_depth={},
            redundant_at_depth={},
            selected=[],
            effective_score={},
            phase_floor={},
            phase_reference={},
        )


def trace_search(
    frame: pl.DataFrame,
    feature_columns: tuple[str, ...],
    outcome: Any,
    config: DiscoveryConfig,
) -> SearchTrace:
    """Replicate `discover_candidates` exactly, recording per-depth state.

    Every computation is `discovery.engine`'s own function; only the recording is new. The control
    flow below is a line-for-line mirror of `discover_candidates` (engine `v0.6.0`), including the
    depth-`>1` parent-redundancy skip, the two-phase interactions-before-singletons selection, the
    `_IDENTITY_CAP_OVERSELECT_MULTIPLIER` widening (inert at the default
    `max_feature_identity_fraction=1.0`), and the final feature-identity cap.
    """
    development = frame.filter(  # pyright: ignore[reportUnknownMemberType]
        pl.col("split_label") == "development"
    )
    atoms = _atoms(development, feature_columns, config)
    evaluated = 0
    scored: dict[tuple[Condition, ...], tuple[float, SplitMetric]] = {}
    trace = SearchTrace.empty(atoms)
    trace.scored = scored
    frontier: list[tuple[Condition, ...]] = [(atom,) for atom in atoms]

    for depth in range(1, config.max_conditions + 1):
        trace.generated_at_depth[depth] = set(frontier)
        trace.redundant_at_depth[depth] = set()
        next_frontier: list[tuple[Condition, ...]] = []
        for rule in frontier:
            evaluated += 1
            metric = _metric(frame, rule, outcome, "development")
            if _eligible(metric, config):
                assert metric is not None
                if depth > 1:
                    parent_metrics = [
                        _metric(
                            frame, tuple(c for c in rule if c != removed), outcome, "development"
                        )
                        for removed in rule
                    ]
                    if any(
                        parent and parent.n_exposed == metric.n_exposed for parent in parent_metrics
                    ):
                        trace.redundant_at_depth[depth].add(rule)
                        continue
                scored[rule] = (_development_score(metric, depth, config), metric)

        trace.scored_ranked_at_depth[depth] = [
            rule
            for rule, _ in sorted(scored.items(), key=lambda item: (-item[1][0], item[0]))
            if len(rule) == depth
        ]
        beam = _select_expansion_beam(scored, depth, config)
        trace.beam_at_depth[depth] = beam
        if depth == config.max_conditions:
            break
        for rule in beam:
            used = {condition.feature for condition in rule}
            for atom in atoms:
                if atom.feature in used:
                    continue
                next_frontier.append(tuple(sorted((*rule, atom))))
        frontier = sorted(set(next_frontier))
    trace.evaluated = evaluated

    ranked_rules = sorted(scored, key=lambda rule: (-scored[rule][0], rule))
    interactions = [rule for rule in ranked_rules if len(rule) >= 2]
    singles = [rule for rule in ranked_rules if len(rule) == 1]

    selected: list[tuple[Condition, ...]] = []
    selected_exposures: list[frozenset[int]] = []
    atom_usage: dict[Condition, int] = {}
    max_overlap: dict[tuple[Condition, ...], float] = {}
    exposures: dict[tuple[Condition, ...], frozenset[int]] = {}
    effective_score: dict[tuple[Condition, ...], float] = {}

    def _prepare(pool: list[tuple[Condition, ...]]) -> None:
        for rule in pool:
            if rule not in exposures:
                mask = development.select(  # pyright: ignore[reportUnknownMemberType]
                    _rule_expr_local(rule).alias("exposed")
                )["exposed"].to_list()
                exposures[rule] = frozenset(
                    index for index, exposed in enumerate(cast("list[bool]", mask)) if exposed
                )
                max_overlap[rule] = 0.0
                info = _temporal_consistency(frame, rule, outcome)
                effective_score[rule] = _apply_stability_credit(
                    scored[rule][0], info.consistency, config.stability_credit_weight
                )

    for phase_name, pool in (("interactions", interactions), ("singletons", singles)):
        if phase_name == "singletons" and len(selected) >= config.top_k:
            break
        _prepare(pool)
        if pool:
            reference = _percentile(
                [effective_score[rule] for rule in pool], config.relevance_floor_percentile
            )
            trace.phase_reference[phase_name] = reference
            trace.phase_floor[phase_name] = config.min_diversity_relevance_ratio * reference
        _greedy_diverse_select(
            pool,
            effective_score,
            exposures,
            config,
            selected,
            selected_exposures,
            atom_usage,
            max_overlap,
        )
    if config.max_feature_identity_fraction < 1.0:
        selected = _apply_feature_identity_cap(selected, config)
    trace.selected = selected
    trace.effective_score = effective_score
    return trace


def _rule_expr_local(rule: tuple[Condition, ...]) -> pl.Expr:
    """Same predicate `discovery.engine._rule_expr` builds, rebuilt here only because `_prepare`
    needs it at the call site; identical semantics, verified by the byte-level selection check."""
    expression: pl.Expr | None = None
    for condition in rule:
        column = pl.col(condition.feature)
        if condition.operator == "eq":
            clause = column == condition.value
        elif condition.operator == "ge":
            clause = column >= condition.value
        else:
            clause = column < condition.value
        expression = clause if expression is None else expression & clause
    assert expression is not None
    return expression


# --------------------------------------------------------------------------------------------
# Oracle projection: the tightest rule the engine's own vocabulary can express
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProjectedCondition:
    true_condition: TrueCondition
    atom: Condition | None
    status: str
    detail: str
    exact: bool


def _numeric_thresholds(
    atoms: tuple[Condition, ...], feature: str, operator: Operator
) -> list[float]:
    return sorted(
        float(cast(float, atom.value))
        for atom in atoms
        if atom.feature == feature and atom.operator == operator
    )


def project_condition(
    condition: TrueCondition,
    atoms: tuple[Condition, ...],
    feature_columns: tuple[str, ...],
    frame_columns: frozenset[str],
    timing: dict[str, str],
) -> list[ProjectedCondition]:
    """Map one true conjunct onto the *tightest atom that still covers it*.

    Covering, never narrowing, is the point: a covering projection is guaranteed to expose every
    booking the true pattern affected, so its recall against that pattern is 1.0 by construction
    and `scripts/evaluate_benchmark.py`'s own `recall >= 0.5` matching statistic is satisfied
    whenever the projection is eligible at all. Anything a covering projection cannot do, no rule
    in this vocabulary can do — which is exactly what stage 1 needs to decide.

    Returns a list because a numeric equality has two covering bounds (`ge`/`lt`); the caller
    resolves the resulting same-feature collision, which the engine's expansion forbids.
    """
    feature = condition.feature
    if feature not in feature_columns:
        if feature not in frame_columns:
            classification = timing.get(feature)
            reason = (
                f"no column {feature!r} in the analytical frame"
                if classification is None
                else f"{feature!r} classified {classification}"
            )
            return [ProjectedCondition(condition, None, "UNREPRESENTABLE", reason, False)]
        classification = timing.get(feature, "UNKNOWN")
        return [
            ProjectedCondition(
                condition,
                None,
                "UNREPRESENTABLE",
                f"{feature!r} is {classification} but excluded from the search vocabulary",
                False,
            )
        ]
    if condition.operator == "IN":
        return [
            ProjectedCondition(
                condition,
                None,
                "UNREPRESENTABLE",
                "set membership has no atom form (atoms are single-value eq / ge / lt only)",
                False,
            )
        ]
    if condition.operator == "!=":
        return [
            ProjectedCondition(
                condition, None, "UNREPRESENTABLE", "negation has no atom form", False
            )
        ]

    categorical = [atom for atom in atoms if atom.feature == feature and atom.operator == "eq"]
    if categorical:
        if condition.operator != "=":
            return [
                ProjectedCondition(
                    condition,
                    None,
                    "UNREPRESENTABLE",
                    f"{feature!r} yields only equality atoms; {condition.operator!r} has no form",
                    False,
                )
            ]
        match = next((atom for atom in categorical if atom.value == condition.value), None)
        if match is None:
            return [
                ProjectedCondition(
                    condition,
                    None,
                    "UNREPRESENTABLE",
                    f"level {condition.value!r} absent from {feature!r}'s atom set",
                    False,
                )
            ]
        return [ProjectedCondition(condition, match, "EXACT", "categorical equality atom", True)]

    value = float(cast(float, condition.value))
    ge_thresholds = _numeric_thresholds(atoms, feature, "ge")
    lt_thresholds = _numeric_thresholds(atoms, feature, "lt")

    def _lower_bound() -> ProjectedCondition:
        covering = [t for t in ge_thresholds if t <= value]
        if not covering:
            lowest = f"{min(ge_thresholds):g}" if ge_thresholds else "none"
            return ProjectedCondition(
                condition,
                None,
                "UNREPRESENTABLE",
                f"no `ge` quantile threshold at or below {value:g} (lowest available {lowest})",
                False,
            )
        best = max(covering)
        exact = best == value
        return ProjectedCondition(
            condition,
            Condition(feature, "ge", best),
            "EXACT" if exact else "RELAXED",
            f"tightest covering threshold {best:g} for a bound at {value:g}",
            exact,
        )

    def _upper_bound(strict_value: float) -> ProjectedCondition:
        covering = [t for t in lt_thresholds if t >= strict_value]
        if not covering:
            highest = f"{max(lt_thresholds):g}" if lt_thresholds else "none"
            return ProjectedCondition(
                condition,
                None,
                "UNREPRESENTABLE",
                f"no `lt` quantile threshold at or above {strict_value:g} "
                f"(highest available {highest})",
                False,
            )
        best = min(covering)
        exact = best == strict_value
        return ProjectedCondition(
            condition,
            Condition(feature, "lt", best),
            "EXACT" if exact else "RELAXED",
            f"tightest covering threshold {best:g} for a bound at {strict_value:g}",
            exact,
        )

    if condition.operator in {">=", ">"}:
        return [_lower_bound()]
    if condition.operator == "<":
        return [_upper_bound(value)]
    if condition.operator == "<=":
        return [_upper_bound(value + 1.0)]
    # Numeric equality: covered by the conjunction of both bounds, which the engine cannot form
    # (expansion never adds a second condition on a feature a rule already uses).
    return [_lower_bound(), _upper_bound(value + 1.0)]


@dataclass(slots=True)
class OracleProjection:
    pattern_id: str
    true_rule: str
    true_conditions: tuple[TrueCondition, ...]
    projected: list[ProjectedCondition]
    atoms: tuple[Condition, ...]
    dropped_universal: list[Condition]
    dropped_collision: list[Condition]
    over_depth: bool
    notes: list[str]


def build_projection(
    pattern_id: str,
    true_rule: str,
    atoms: tuple[Condition, ...],
    feature_columns: tuple[str, ...],
    frame_columns: frozenset[str],
    timing: dict[str, str],
    development: pl.DataFrame,
    config: DiscoveryConfig,
) -> OracleProjection:
    conditions = parse_true_rule(true_rule)
    projected: list[ProjectedCondition] = []
    for condition in conditions:
        projected.extend(
            project_condition(condition, atoms, feature_columns, frame_columns, timing)
        )
    notes: list[str] = []
    kept = [item for item in projected if item.atom is not None]

    # A condition every development row already satisfies carries no information and can never be
    # eligible (`_eligible` requires `support <= max_support`), so it is dropped from the tightest
    # covering rule rather than spent as one of the `max_conditions` slots.
    dropped_universal: list[Condition] = []
    survivors: list[ProjectedCondition] = []
    for item in kept:
        atom = item.atom
        assert atom is not None
        support = development.select(  # pyright: ignore[reportUnknownMemberType]
            _rule_expr_local((atom,)).mean().alias("s")
        )["s"][0]
        if support is not None and float(cast(float, support)) >= 1.0:
            dropped_universal.append(atom)
            continue
        survivors.append(item)
    if dropped_universal:
        notes.append(
            "dropped universally-true covering atom(s) "
            + ", ".join(_render_rule((atom,)) for atom in dropped_universal)
            + " — support 1.0 exceeds max_support and carries no information"
        )

    # The engine's expansion never adds a second condition on a feature a rule already uses, so at
    # most one atom per feature can survive. Keep the more selective one and record the loss.
    dropped_collision: list[Condition] = []
    by_feature: dict[str, ProjectedCondition] = {}
    for item in survivors:
        atom = item.atom
        assert atom is not None
        existing = by_feature.get(atom.feature)
        if existing is None:
            by_feature[atom.feature] = item
            continue
        existing_atom = existing.atom
        assert existing_atom is not None
        keep, drop = (
            (item, existing_atom)
            if _atom_support(development, atom) < _atom_support(development, existing_atom)
            else (existing, atom)
        )
        by_feature[atom.feature] = keep
        dropped_collision.append(drop)
    if dropped_collision:
        notes.append(
            "dropped same-feature covering atom(s) "
            + ", ".join(_render_rule((atom,)) for atom in dropped_collision)
            + " — the engine's expansion forbids two conditions on one feature, so a numeric "
            "equality cannot be bracketed"
        )

    final_atoms = tuple(sorted(item.atom for item in by_feature.values() if item.atom is not None))
    over_depth = len(final_atoms) > config.max_conditions
    if over_depth:
        notes.append(
            f"tightest covering rule needs {len(final_atoms)} conditions, above "
            f"max_conditions={config.max_conditions}"
        )
    return OracleProjection(
        pattern_id=pattern_id,
        true_rule=true_rule,
        true_conditions=conditions,
        projected=projected,
        atoms=final_atoms,
        dropped_universal=dropped_universal,
        dropped_collision=dropped_collision,
        over_depth=over_depth,
        notes=notes,
    )


def _atom_support(development: pl.DataFrame, atom: Condition) -> float:
    value = development.select(  # pyright: ignore[reportUnknownMemberType]
        _rule_expr_local((atom,)).mean().alias("s")
    )["s"][0]
    return float(cast(float, value)) if value is not None else 0.0


def _render_rule(rule: tuple[Condition, ...]) -> str:
    return " AND ".join(f"{c.feature} {c.operator} {c.value}" for c in rule)


# --------------------------------------------------------------------------------------------
# Stage ladder
# --------------------------------------------------------------------------------------------

STAGES = (
    "S1_REPRESENTABLE",
    "S2_GENERATED",
    "S3_SURVIVES_EXPANSION",
    "S4_RANKED_PRE_SELECTION",
    "S5_SELECTED",
    "S6_VALIDATED",
)


def _ineligibility_reason(metric: SplitMetric | None, config: DiscoveryConfig) -> str:
    if metric is None:
        return "no exposed or no comparison rows on the development split"
    reasons: list[str] = []
    if metric.n_exposed < config.min_n:
        reasons.append(f"n_exposed={metric.n_exposed} < min_n={config.min_n}")
    if metric.support < config.min_support:
        reasons.append(f"support={metric.support:.4f} < min_support={config.min_support}")
    if metric.support > config.max_support:
        reasons.append(f"support={metric.support:.4f} > max_support={config.max_support}")
    if metric.harm_per_booking <= 0:
        reasons.append(f"harm_per_booking={metric.harm_per_booking:.2f} is not > 0")
    return "; ".join(reasons) if reasons else "eligible"


def rule_history(
    rule: tuple[Condition, ...],
    trace: SearchTrace,
    frame: pl.DataFrame,
    outcome: Any,
    config: DiscoveryConfig,
    pool_rank: dict[tuple[Condition, ...], int],
    pool_size: int,
) -> dict[str, Any]:
    """Everything the search did to one rule, at the depth it lives at."""
    depth = len(rule)
    generated = rule in trace.generated_at_depth.get(depth, set())
    metric = _metric(frame, rule, outcome, "development")
    eligible = _eligible(metric, config)
    redundant = rule in trace.redundant_at_depth.get(depth, set())
    scored_entry = trace.scored.get(rule)
    ranked = trace.scored_ranked_at_depth.get(depth, [])
    beam = trace.beam_at_depth.get(depth, [])
    depth_rank = ranked.index(rule) + 1 if rule in ranked else None
    in_beam = rule in beam
    phase = "interactions" if depth >= 2 else "singletons"
    record: dict[str, Any] = {
        "rule": _render_rule(rule),
        "depth": depth,
        "generated_at_this_depth": generated,
        "development_n_exposed": metric.n_exposed if metric else 0,
        "development_support": round(metric.support, 6) if metric else 0.0,
        "development_harm_per_booking": round(metric.harm_per_booking, 4) if metric else None,
        "eligible": bool(eligible),
        "ineligibility_reason": None if eligible else _ineligibility_reason(metric, config),
        "skipped_as_redundant_with_parent": redundant,
        "scored": scored_entry is not None,
        "development_score": round(scored_entry[0], 4) if scored_entry else None,
        "rank_within_depth": depth_rank,
        "eligible_rules_at_this_depth": len(ranked),
        "in_expansion_beam": in_beam if depth < config.max_conditions else None,
        "expansion_beam_size": len(beam) if depth < config.max_conditions else None,
        "rank_in_full_pool": pool_rank.get(rule),
        "full_pool_size": pool_size,
        "selection_phase": phase,
        "effective_score": (
            round(trace.effective_score[rule], 4) if rule in trace.effective_score else None
        ),
        "phase_relevance_floor": trace.phase_floor.get(phase),
        "clears_relevance_floor": (
            trace.effective_score[rule] >= trace.phase_floor[phase]
            if rule in trace.effective_score and phase in trace.phase_floor
            else None
        ),
        "selected": rule in trace.selected,
    }
    if record["phase_relevance_floor"] is not None:
        record["phase_relevance_floor"] = round(cast(float, record["phase_relevance_floor"]), 4)
    return record


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-id", type=str, default=DEFAULT_RUN_ID)
    parser.add_argument("--blind-root", type=Path, default=BLIND_ROOT)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--validation-report", type=Path, default=DEFAULT_VALIDATION_PATH)
    parser.add_argument("--evaluation-report", type=Path, default=DEFAULT_EVALUATION_PATH)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    parser.add_argument(
        "--skip-counterfactual-validation",
        action="store_true",
        help="skip stage 6's hypothetical `run_validation` call (slow: cluster bootstrap)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    blind_root = cast(Path, args.blind_root)
    run_id = cast(str, args.run_id)
    dataset_root = cast(Path, args.dataset_root)

    candidates_path = blind_root / f"{run_id}.candidates.json"
    metrics_path = blind_root / f"{run_id}.discovery_metrics.json"
    hashes_path = blind_root / f"{run_id}.hashes.json"
    for path in (candidates_path, metrics_path, hashes_path):
        if not path.exists():
            raise SystemExit(
                f"missing frozen artifact {path}; `artifacts/` is gitignored and per-checkout — "
                "point --blind-root at a checkout that holds this run's frozen outputs"
            )
    hashes = cast(dict[str, str], json.loads(hashes_path.read_text(encoding="utf-8")))
    actual = hashlib.sha256(candidates_path.read_bytes()).hexdigest()
    if actual != hashes.get("candidates.json"):
        raise SystemExit(
            f"candidate file SHA-256 {actual} does not match the frozen hashes.json entry "
            f"{hashes.get('candidates.json')} — refusing to trace a mutated run"
        )

    run_metrics = cast(dict[str, Any], json.loads(metrics_path.read_text(encoding="utf-8")))
    committed = cast(dict[str, Any], json.loads(candidates_path.read_text(encoding="utf-8")))
    manifest = cast(
        dict[str, Any], json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    )
    if run_metrics["dataset_identity_sha256"] != manifest["dataset_identity_sha256"]:
        raise SystemExit("dataset identity drifted since the committed run; results untrustworthy")
    if run_metrics["discovery_method_version"] != DISCOVERY_METHOD_VERSION:
        print(
            f"NOTE: committed run used {run_metrics['discovery_method_version']}; the installed "
            f"engine is {DISCOVERY_METHOD_VERSION}. The fidelity assertions below decide whether "
            "that difference is observable on this dataset."
        )

    seed = int(run_metrics["random_seed"])
    identity_fraction = float(run_metrics.get("max_feature_identity_fraction", 1.0))
    config = DiscoveryConfig(seed=seed, max_feature_identity_fraction=identity_fraction)

    timing_meta = cast(dict[str, dict[str, Any]], manifest["feature_timing"])
    timing = {name: str(meta["classification"]) for name, meta in timing_meta.items()}
    excluded_dates = {"booking_date", "travel_date"}
    frame = load_analytical_frame(dataset_root)
    feature_columns = tuple(
        name
        for name in frame.columns
        if timing.get(name) == "DECISION_TIME" and name not in excluded_dates
    )
    outcome = primary_outcome()
    development = frame.filter(  # pyright: ignore[reportUnknownMemberType]
        pl.col("split_label") == "development"
    )

    print(f"Tracing committed run {run_id} (seed {seed}, engine {DISCOVERY_METHOD_VERSION})")
    print(f"  feature vocabulary: {len(feature_columns)} DECISION_TIME columns")
    trace = trace_search(frame, feature_columns, outcome, config)
    print(f"  atoms={len(trace.atoms)}  evaluated_hypotheses={trace.evaluated}")

    if trace.evaluated != run_metrics["evaluated_hypotheses"]:
        raise SystemExit(
            f"evaluated_hypotheses mismatch: reproduced {trace.evaluated}, committed run reports "
            f"{run_metrics['evaluated_hypotheses']} — search did not reproduce identically"
        )
    committed_rules = [
        tuple(
            sorted(
                Condition(c["feature"], c["operator"], c["value"])
                for c in cast(list[dict[str, Any]], candidate["conditions"])
            )
        )
        for candidate in cast(list[dict[str, Any]], committed["candidates"])
    ]
    if committed_rules != trace.selected:
        raise SystemExit(
            "reproduced selection differs from the committed candidate set — refusing to report "
            "stage verdicts derived from a search that is not the committed one"
        )
    print(f"  FIDELITY OK: evaluated_hypotheses and all {len(committed_rules)} candidates match")

    pool_ranked = sorted(trace.scored, key=lambda rule: (-trace.scored[rule][0], rule))
    pool_rank = {rule: index + 1 for index, rule in enumerate(pool_ranked)}
    pool_size = len(pool_ranked)
    print(f"  full pre-selection eligible pool: {pool_size} rules")

    ground_truth = cast(dict[str, Any], json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8")))
    patterns = cast(list[dict[str, Any]], ground_truth["patterns"])
    booking_ids = cast("list[str]", frame["booking_id"].to_list())
    index_of = {booking_id: index for index, booking_id in enumerate(booking_ids)}
    pattern_masks: dict[str, int] = {}
    for pattern in patterns:
        packed = 0
        for booking_id in cast("list[str]", pattern["affected_booking_ids"]):
            packed |= 1 << index_of[booking_id]
        pattern_masks[str(pattern["id"])] = packed

    atom_masks = {atom: _frame_mask(frame, _rule_expr_local((atom,))) for atom in trace.atoms}

    def rule_mask(rule: tuple[Condition, ...]) -> int:
        packed = (1 << len(booking_ids)) - 1
        for condition in rule:
            packed &= atom_masks.get(condition) or _frame_mask(
                frame, _rule_expr_local((condition,))
            )
        return packed

    # Cross-check the bitmask algebra against polars on a real multi-condition rule before trusting
    # it for the pool-wide scan.
    for probe in pool_ranked[:3]:
        if rule_mask(probe).bit_count() != _frame_mask(frame, _rule_expr_local(probe)).bit_count():
            raise SystemExit("bitmask row algebra disagrees with polars — refusing to report")

    # Pool-wide best-recall scan, continuous with `diagnose_candidate_pool_recall.py`'s own figure.
    pool_best: dict[str, tuple[float, tuple[Condition, ...] | None]] = {
        pid: (0.0, None) for pid in pattern_masks
    }
    pool_full_matches: dict[str, int] = dict.fromkeys(pattern_masks, 0)
    for rule in pool_ranked:
        mask = rule_mask(rule)
        for pid, affected in pattern_masks.items():
            hits = (mask & affected).bit_count()
            recall = hits / affected.bit_count() if affected else 0.0
            if recall > pool_best[pid][0]:
                pool_best[pid] = (recall, rule)
            if recall >= FULL_MATCH_RECALL:
                pool_full_matches[pid] += 1

    frozen_validation = cast(
        dict[str, Any], json.loads(cast(Path, args.validation_report).read_text(encoding="utf-8"))
    )
    frozen_evaluation = cast(
        dict[str, Any], json.loads(cast(Path, args.evaluation_report).read_text(encoding="utf-8"))
    )
    verdict_by_candidate = {
        str(entry["candidate_id"]): str(entry["verdict"])
        for entry in cast(list[dict[str, Any]], frozen_validation["candidates"])
    }
    evidence_by_candidate = {
        str(entry["candidate_id"]): (
            str(entry["evidence_level"]),
            [str(pid) for pid in cast(list[str], entry["matched_patterns"])],
        )
        for entry in cast(list[dict[str, Any]], frozen_evaluation["candidate_scores"])
    }
    rule_by_candidate = dict(
        zip(
            (str(candidate["candidate_id"]) for candidate in committed["candidates"]),
            committed_rules,
            strict=True,
        )
    )
    candidate_by_rule = {rule: candidate_id for candidate_id, rule in rule_by_candidate.items()}
    # `TASK-028`'s own recovered-pattern set, read from the frozen evaluation rather than
    # re-derived, so this diagnostic can never disagree with the official metric it explains.
    recovered_patterns = {
        str(pid)
        for pid in cast(
            list[str],
            cast(dict[str, Any], frozen_evaluation["metrics"])["economic_weighted_recall"][
                "recovered_scoreable_patterns"
            ],
        )
    }

    frame_columns = frozenset(frame.columns)
    results: list[dict[str, Any]] = []
    counterfactual_rules: list[tuple[str, tuple[Condition, ...]]] = []

    for pattern in patterns:
        pattern_id = str(pattern["id"])
        true_rule = str(pattern["rule"])
        affected_mask = pattern_masks[pattern_id]
        n_affected = affected_mask.bit_count()
        projection = build_projection(
            pattern_id,
            true_rule,
            trace.atoms,
            feature_columns,
            frame_columns,
            timing,
            development,
            config,
        )

        # Diagnostic-only: what the engine would have made of the exact true rule, including
        # conditions its vocabulary cannot express. Never used to build an atom (module docstring).
        true_reference = _true_rule_reference(frame, projection.true_conditions, outcome, config)

        by_true_condition: dict[str, list[ProjectedCondition]] = {}
        for item in projection.projected:
            by_true_condition.setdefault(item.true_condition.render(), []).append(item)
        conditions_total = len(by_true_condition)
        representable_count = sum(
            1
            for items in by_true_condition.values()
            if any(item.atom is not None for item in items)
        )
        exact_count = sum(
            1 for items in by_true_condition.values() if all(item.exact for item in items)
        )
        stage1 = {
            "exactly_representable": (
                representable_count == conditions_total
                and exact_count == conditions_total
                and not projection.over_depth
                and not projection.dropped_collision
            ),
            "conditions_total": conditions_total,
            "conditions_representable": representable_count,
            "conditions_exact": exact_count,
            "tightest_representable_rule": (
                _render_rule(projection.atoms) if projection.atoms else None
            ),
            "over_max_conditions": projection.over_depth,
            "per_condition": [
                {
                    "true_condition": item.true_condition.render(),
                    "atom": _render_rule((item.atom,)) if item.atom else None,
                    "status": item.status,
                    "detail": item.detail,
                }
                for item in projection.projected
            ],
            "notes": projection.notes,
        }

        canonical: tuple[Condition, ...] | None = None
        traced: list[dict[str, Any]] = []
        if projection.atoms and not projection.over_depth:
            canonical = projection.atoms
        elif projection.atoms:
            # Over depth: the search can at best reach a sub-conjunction. Canonical = the most
            # specific reachable one (smallest development exposure), deterministic and derived
            # from the vocabulary, not from which sub-rule happens to score well.
            subsets = list(combinations(projection.atoms, config.max_conditions))
            canonical = min(
                subsets, key=lambda subset: (rule_mask(tuple(sorted(subset))).bit_count(), subset)
            )
            canonical = tuple(sorted(canonical))

        ancestors: list[tuple[Condition, ...]] = []
        if canonical is not None:
            for size in range(1, len(canonical) + 1):
                for subset in combinations(canonical, size):
                    ancestors.append(tuple(sorted(subset)))
        for rule in ancestors:
            record = rule_history(rule, trace, frame, outcome, config, pool_rank, pool_size)
            mask = rule_mask(rule)
            hits = (mask & affected_mask).bit_count()
            record["recall_against_pattern"] = round(hits / n_affected, 4) if n_affected else 0.0
            record["exposed_n_full_cohort"] = mask.bit_count()
            record["is_canonical"] = rule == canonical
            traced.append(record)

        canonical_record = next((r for r in traced if r["is_canonical"]), None)
        stage_verdict, stage_detail = _first_failing_stage(
            canonical_record, traced, pattern_id, recovered_patterns
        )
        stage6_actual: dict[str, Any] | None = None
        if canonical is not None and canonical_record is not None:
            if canonical_record["selected"]:
                candidate_id = candidate_by_rule[canonical]
                evidence, matched = evidence_by_candidate[candidate_id]
                stage6_actual = {
                    "candidate_id": candidate_id,
                    "verdict": verdict_by_candidate[candidate_id],
                    "evidence_level": evidence,
                    "matched_patterns": matched,
                }
            else:
                counterfactual_rules.append((pattern_id, canonical))

        best_recall, best_rule = pool_best[pattern_id]
        results.append(
            {
                "pattern_id": pattern_id,
                "name": str(pattern["name"]),
                "scoreable": pattern_id not in NON_SCOREABLE_PATTERNS,
                "true_rule": true_rule,
                "true_rule_affected_n": n_affected,
                "true_rule_engine_reference": true_reference,
                "realized_economic_impact_eur": pattern["true_effect"]["realized_economic_impact"],
                "stage_1_representability": stage1,
                "canonical_representable_rule": (
                    _render_rule(canonical) if canonical is not None else None
                ),
                "canonical_broadening_factor": (
                    round(canonical_record["exposed_n_full_cohort"] / n_affected, 2)
                    if canonical_record and n_affected
                    else None
                ),
                "traced_rules": traced,
                "pool_best_recall": round(best_recall, 4),
                "pool_best_rule": _render_rule(best_rule) if best_rule else None,
                "pool_best_rule_rank": pool_rank.get(best_rule) if best_rule else None,
                "pool_full_match_candidates": pool_full_matches[pattern_id],
                "recovered_by_committed_run": pattern_id in recovered_patterns,
                "stage_6_actual": stage6_actual,
                "oracle_branch_first_failing_stage": stage_verdict,
                "oracle_branch_first_failing_stage_detail": stage_detail,
            }
        )

    counterfactual: dict[str, Any] = {"status": "skipped"}
    if counterfactual_rules and not args.skip_counterfactual_validation:
        counterfactual = _counterfactual_validation(
            counterfactual_rules, dataset_root, manifest, metrics_path, frame, outcome, config
        )
        for entry in results:
            gate = cast(dict[str, Any], counterfactual.get("by_pattern", {})).get(
                entry["pattern_id"]
            )
            if gate is not None:
                entry["stage_6_counterfactual"] = gate

    payload: dict[str, Any] = {
        "diagnostic": "POST_HOC_DIAGNOSTIC",
        "task": "TASK-069 research-plan item 7 (oracle decomposition benchmark)",
        "disclosure": (
            "Not an official TASK-015/TASK-019/TASK-028 run. Produces no official metric, changes "
            "no frozen artifact, and proposes no mechanism. Stage 6 counterfactuals are "
            "hypothetical validations of rules that were never selected."
        ),
        "traced_run_id": run_id,
        "traced_candidates_sha256": actual,
        "engine_version_installed": DISCOVERY_METHOD_VERSION,
        "engine_version_committed": run_metrics["discovery_method_version"],
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "config": {
            "seed": config.seed,
            "min_n": config.min_n,
            "min_support": config.min_support,
            "max_support": config.max_support,
            "max_conditions": config.max_conditions,
            "beam_width": config.beam_width,
            "beam_rules_per_structure": config.beam_rules_per_structure,
            "max_expansion_beam_size": config.max_expansion_beam_size,
            "top_k": config.top_k,
            "min_diversity_relevance_ratio": config.min_diversity_relevance_ratio,
            "relevance_floor_percentile": config.relevance_floor_percentile,
            "max_feature_identity_fraction": config.max_feature_identity_fraction,
        },
        "search": {
            "feature_vocabulary": list(feature_columns),
            "atom_count": len(trace.atoms),
            "evaluated_hypotheses": trace.evaluated,
            "eligible_pool_size": pool_size,
            "per_depth": {
                str(depth): {
                    "generated": len(trace.generated_at_depth.get(depth, set())),
                    "eligible": len(trace.scored_ranked_at_depth.get(depth, [])),
                    "skipped_redundant_with_parent": len(
                        trace.redundant_at_depth.get(depth, set())
                    ),
                    "expansion_beam": (
                        len(trace.beam_at_depth.get(depth, []))
                        if depth < config.max_conditions
                        else None
                    ),
                }
                for depth in range(1, config.max_conditions + 1)
            },
            "phase_relevance_floor": {
                phase: round(value, 4) for phase, value in trace.phase_floor.items()
            },
        },
        "stage_ladder": list(STAGES),
        "patterns": results,
        "stage_6_counterfactual_validation": counterfactual,
    }
    raw_output = cast(Path, args.raw_output)
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print_report(payload)
    print(f"\nRaw diagnostic written to {raw_output}")


def _true_rule_reference(
    frame: pl.DataFrame,
    conditions: tuple[TrueCondition, ...],
    outcome: Any,
    config: DiscoveryConfig,
) -> dict[str, Any]:
    """What the engine would have made of the *exact* true rule, had its vocabulary contained it.

    Diagnostic reference only. Where a true conjunct names a calendar decomposition of a date
    column the frame carries (`<x>_month` from `<x>_date`), it is derived here purely to answer
    "would even the perfect rule have cleared the eligibility floors?" — a question no amount of
    search or scoring redesign can answer, and one that changes which of `TASK-069`'s directions
    could possibly help. The derived column never becomes an atom and never enters the traced
    search (module docstring).
    """
    working = frame
    derived: list[str] = []
    for condition in conditions:
        if condition.feature in working.columns:
            continue
        if not condition.feature.endswith("_month"):
            return {"available": False, "reason": f"cannot derive {condition.feature!r}"}
        source = condition.feature.removesuffix("_month") + "_date"
        if source not in working.columns:
            return {"available": False, "reason": f"no source column {source!r}"}
        working = working.with_columns(
            pl.col(source).str.to_date("%Y-%m-%d").dt.month().alias(condition.feature)
        )
        derived.append(f"{condition.feature} := month({source})")

    development = working.filter(  # pyright: ignore[reportUnknownMemberType]
        pl.col("split_label") == "development"
    )

    def _measure(subset: tuple[TrueCondition, ...]) -> dict[str, Any]:
        expression: pl.Expr | None = None
        for condition in subset:
            clause = true_condition_expr(condition)
            expression = clause if expression is None else expression & clause
        assert expression is not None
        exposed = development.filter(expression)  # pyright: ignore[reportUnknownMemberType]
        comparison = development.filter(~expression)  # pyright: ignore[reportUnknownMemberType]
        rendered = " AND ".join(item.render() for item in subset)
        if exposed.is_empty() or comparison.is_empty():
            return {
                "rule": rendered,
                "size": len(subset),
                "development_n_exposed": exposed.height,
                "development_harm_per_booking": None,
                "eligible_under_engine_floors": False,
                "ineligibility_reason": (
                    "no exposed or no comparison rows on the development split"
                ),
            }
        exposed_mean = cast(float, exposed[outcome.column].mean())
        comparison_mean = cast(float, comparison[outcome.column].mean())
        difference = exposed_mean - comparison_mean
        metric = SplitMetric(
            split="development",
            n_population=development.height,
            n_exposed=exposed.height,
            support=exposed.height / development.height,
            exposed_mean=exposed_mean,
            comparison_mean=comparison_mean,
            raw_difference=difference,
            harm_per_booking=difference * outcome.harm_multiplier,
            historical_exposure=difference * outcome.harm_multiplier * exposed.height,
        )
        eligible = bool(_eligible(metric, config))
        return {
            "rule": rendered,
            "size": len(subset),
            "development_n_exposed": metric.n_exposed,
            "development_support": round(metric.support, 6),
            "development_harm_per_booking": round(metric.harm_per_booking, 4),
            "eligible_under_engine_floors": eligible,
            "ineligibility_reason": None if eligible else _ineligibility_reason(metric, config),
        }

    # Every sub-conjunction of the exact true rule, so the report can answer the question a
    # first-failing-stage ladder cannot: *is there any expansion order at all* — under any beam,
    # any score, any lookahead — that reaches this rule? `discover_candidates` only ever expands a
    # rule already in `scored`, and `_eligible` requires `harm_per_booking > 0`, so a true rule is
    # reachable only if some chain of nested sub-conjunctions from a single condition up to the
    # whole rule is eligible at every step. Where no such chain exists, the effect is
    # interaction-only-positive and the eligibility gate itself — not the beam, the score, or the
    # selection policy — is what excludes it.
    ladder: list[dict[str, Any]] = []
    eligible_subsets: set[frozenset[str]] = set()
    for size in range(1, len(conditions) + 1):
        for subset in combinations(conditions, size):
            measurement = _measure(subset)
            ladder.append(measurement)
            if measurement["eligible_under_engine_floors"]:
                eligible_subsets.add(frozenset(item.render() for item in subset))

    def _chain_exists(subset: frozenset[str]) -> bool:
        if subset not in eligible_subsets:
            return False
        if len(subset) == 1:
            return True
        return any(_chain_exists(subset - {item}) for item in subset)

    full_key = frozenset(item.render() for item in conditions)
    full = ladder[-1]
    return {
        "available": True,
        "diagnostic_derived_columns": derived,
        "development_n_exposed": full["development_n_exposed"],
        "development_support": full.get("development_support"),
        "development_harm_per_booking": full["development_harm_per_booking"],
        "eligible_under_engine_floors": full["eligible_under_engine_floors"],
        "ineligibility_reason": full["ineligibility_reason"],
        "eligible_ancestor_chain_exists": _chain_exists(full_key),
        "sub_conjunction_ladder": ladder,
    }


def _first_failing_stage(
    canonical: dict[str, Any] | None,
    traced: list[dict[str, Any]],
    pattern_id: str,
    recovered: set[str],
) -> tuple[str, str]:
    """Where the *tightest representable rule's own branch* first dies.

    Deliberately separate from whether the pattern was recovered at all: the benchmark's matching
    statistic is recall-only, so a much broader rule can recover a pattern the pattern's own
    tightest representable branch never reaches. Both facts are reported; neither substitutes for
    the other.
    """
    if canonical is None:
        return (
            "S1_REPRESENTABLE",
            "no condition of the true rule maps to any atom in the search vocabulary",
        )
    if not canonical["generated_at_this_depth"]:
        depth = cast(int, canonical["depth"])
        parents = [
            record
            for record in traced
            if record["depth"] == depth - 1 and _is_ancestor(record["rule"], canonical["rule"])
        ]
        scored_parents = [record for record in parents if record["scored"]]
        if not scored_parents:
            cause = (
                f"no depth-{depth - 1} ancestor entered the scored pool at all ("
                + "; ".join(
                    f"[{record['rule']}] {record['ineligibility_reason']}"
                    if not record["eligible"]
                    else f"[{record['rule']}] skipped as redundant with its parent"
                    for record in parents
                )
                + ")"
            )
        elif not any(record["in_expansion_beam"] for record in scored_parents):
            cause = (
                f"every eligible depth-{depth - 1} ancestor ranked outside the expansion beam ("
                + "; ".join(
                    f"[{record['rule']}] rank {record['rank_within_depth']}/"
                    f"{record['eligible_rules_at_this_depth']}, "
                    f"beam {record['expansion_beam_size']}"
                    for record in scored_parents
                )
                + ")"
            )
        else:
            cause = "ancestor survived the beam but the expansion did not enumerate this rule"
        if canonical["eligible"] and not canonical["skipped_as_redundant_with_parent"]:
            consequence = "; the rule would have been eligible had it been generated"
        else:
            consequence = (
                f"; and it would itself have been ineligible even if generated "
                f"({canonical['ineligibility_reason']})"
            )
        return ("S2_GENERATED", cause + consequence)
    if canonical["skipped_as_redundant_with_parent"]:
        return (
            "S3_SURVIVES_EXPANSION",
            "generated and eligible, but discarded as exposure-identical to a parent rule — the "
            "extra condition partitions nothing, so the more specific rule never enters the pool",
        )
    if not canonical["eligible"]:
        return (
            "S3_SURVIVES_EXPANSION",
            f"generated but ineligible: {canonical['ineligibility_reason']}",
        )
    if canonical["clears_relevance_floor"] is False:
        return (
            "S4_RANKED_PRE_SELECTION",
            f"scored and pooled at rank {canonical['rank_in_full_pool']} of "
            f"{canonical['full_pool_size']}, but effective_score "
            f"{canonical['effective_score']} is below its phase's relevance floor "
            f"{canonical['phase_relevance_floor']}",
        )
    if not canonical["selected"]:
        if canonical["clears_relevance_floor"] is None:
            return (
                "S5_SELECTED",
                f"scored at pool rank {canonical['rank_in_full_pool']} of "
                f"{canonical['full_pool_size']}, but its selection phase "
                f"({canonical['selection_phase']}) never ran — interactions filled every slot",
            )
        return (
            "S5_SELECTED",
            f"cleared the relevance floor at pool rank {canonical['rank_in_full_pool']} of "
            f"{canonical['full_pool_size']} but lost every greedy-diverse selection round",
        )
    if pattern_id not in recovered:
        return ("S6_VALIDATED", "selected, but no validated candidate matched this pattern")
    return ("NONE", "selected, and the pattern reaches a validated evidence level")


def _is_ancestor(parent_rule: str, child_rule: str) -> bool:
    parent_parts = set(parent_rule.split(" AND "))
    child_parts = set(child_rule.split(" AND "))
    return parent_parts < child_parts


def _counterfactual_validation(
    rules: list[tuple[str, tuple[Condition, ...]]],
    dataset_root: Path,
    manifest: dict[str, Any],
    metrics_path: Path,
    frame: pl.DataFrame,
    outcome: Any,
    config: DiscoveryConfig,
) -> dict[str, Any]:
    """Ask the real, unmodified validation contract what it *would* have said about rules the
    search never selected. Hypothetical, never an official `TASK-019` run: no artifact is written
    under `artifacts/validation/`, and the reported-p-value set differs from the official run's."""
    document_candidates: list[dict[str, Any]] = []
    order: list[str] = []
    for index, (pattern_id, rule) in enumerate(rules, start=1):
        metric = _metric(frame, rule, outcome, "development")
        if metric is None:
            continue
        order.append(pattern_id)
        document_candidates.append(
            {
                "candidate_id": f"ORACLE-{index:03d}",
                "conditions": [
                    {"feature": c.feature, "operator": c.operator, "value": c.value} for c in rule
                ],
                "outcome": outcome.outcome_id,
                "sample_size": metric.n_exposed,
                "support": metric.support,
                "raw_effect": metric.raw_difference,
                "economic_exposure": metric.historical_exposure,
                "discovery_method": DISCOVERY_METHOD_VERSION,
                "description": f"POST-HOC DIAGNOSTIC oracle projection: {_render_rule(rule)}",
                "warnings": ["POST-HOC DIAGNOSTIC; never a discovered or selected candidate."],
            }
        )
    if not document_candidates:
        return {"status": "no unselected rules to test"}
    document = {
        "schema_version": "1.1.0",
        "run_id": "post-hoc-diagnostic-oracle-decomposition",
        "status": "PERSISTED",
        "candidates": document_candidates,
    }
    validation_outcome, outcome_version = outcome_definition_from_manifest(manifest, dataset_root)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "candidates.json"
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        validations, _summary = run_validation(
            dataset_root=dataset_root,
            candidates_path=path,
            outcome=validation_outcome,
            dataset_version=str(manifest["dataset_version"]),
            outcome_definition_version=outcome_version,
            analysis_run_id="post-hoc-diagnostic-oracle-decomposition",
            metrics_path=metrics_path,
        )
    by_pattern: dict[str, Any] = {}
    for pattern_id, validation in zip(order, validations, strict=True):
        report = validation.report
        by_pattern[pattern_id] = {
            "rule": report.pattern_definition,
            "verdict": validation.verdict,
            "evidence_level": report.evidence_level,
            "policy_readiness": report.policy_readiness,
            "failed_gates": sorted(
                str(gate.gate_id.value if hasattr(gate.gate_id, "value") else gate.gate_id)
                for gate in report.gate_results
                if gate.outcome == "fail"
            ),
        }
    return {
        "status": "COUNTERFACTUAL — these rules were never selected by the committed run",
        "family_size_source": str(metrics_path.name),
        "by_pattern": by_pattern,
    }


def _print_report(payload: dict[str, Any]) -> None:
    search = cast(dict[str, Any], payload["search"])
    print("\n=== Per-depth search shape ===")
    for depth, stats in cast(dict[str, dict[str, Any]], search["per_depth"]).items():
        print(
            f"  depth {depth}: generated={stats['generated']:>6}  eligible={stats['eligible']:>5}  "
            f"redundant_skips={stats['skipped_redundant_with_parent']:>5}  "
            f"expansion_beam={stats['expansion_beam']}"
        )

    print("\n=== Stage of death, per pattern ===")
    for entry in cast(list[dict[str, Any]], payload["patterns"]):
        tag = "" if entry["scoreable"] else "  (not scoreable)"
        print(f"\n{entry['pattern_id']} — {entry['name']}{tag}")
        print(f"  true rule: {entry['true_rule']}  (affected n={entry['true_rule_affected_n']})")
        reference = cast(dict[str, Any], entry["true_rule_engine_reference"])
        if reference.get("available"):
            print(
                f"  exact true rule under the engine's own floors: "
                f"dev n_exposed={reference['development_n_exposed']} "
                f"harm/booking={reference.get('development_harm_per_booking')} "
                f"eligible={reference['eligible_under_engine_floors']}"
                + (
                    f" ({reference['ineligibility_reason']})"
                    if reference.get("ineligibility_reason")
                    else ""
                )
            )
            if reference.get("diagnostic_derived_columns"):
                print(
                    "      diagnostic-only derived column(s): "
                    + ", ".join(cast(list[str], reference["diagnostic_derived_columns"]))
                )
            print(
                f"      eligible ancestor chain to the exact true rule exists: "
                f"{reference['eligible_ancestor_chain_exists']}"
            )
            for step in cast(list[dict[str, Any]], reference["sub_conjunction_ladder"]):
                flag = "OK " if step["eligible_under_engine_floors"] else "BLK"
                print(
                    f"        {flag} n={step['development_n_exposed']:>4} "
                    f"harm={step['development_harm_per_booking']} [{step['rule']}]"
                    + (
                        f"  <- {step['ineligibility_reason']}"
                        if step["ineligibility_reason"]
                        else ""
                    )
                )
        stage1 = cast(dict[str, Any], entry["stage_1_representability"])
        print(
            f"  S1 representable: {stage1['conditions_representable']}/"
            f"{stage1['conditions_total']} conditions, "
            f"{stage1['conditions_exact']} exact; "
            f"exactly_representable={stage1['exactly_representable']}"
        )
        for item in cast(list[dict[str, Any]], stage1["per_condition"]):
            print(f"      {item['status']:<16} {item['true_condition']:<38} -> {item['atom']}")
        for note in cast(list[str], stage1["notes"]):
            print(f"      note: {note}")
        print(f"  tightest representable rule: {entry['canonical_representable_rule']}")
        if entry["canonical_broadening_factor"] is not None:
            print(
                f"      exposes {entry['canonical_broadening_factor']}x the true pattern's "
                f"affected population"
            )
        for record in cast(list[dict[str, Any]], entry["traced_rules"]):
            marker = "*" if record["is_canonical"] else " "
            print(
                f"    {marker} d{record['depth']} [{record['rule']}]\n"
                f"        generated={record['generated_at_this_depth']} "
                f"eligible={record['eligible']} scored={record['scored']} "
                f"redundant={record['skipped_as_redundant_with_parent']}"
            )
            if record["scored"]:
                print(
                    f"        score={record['development_score']} "
                    f"rank_within_depth={record['rank_within_depth']}/"
                    f"{record['eligible_rules_at_this_depth']} "
                    f"in_beam={record['in_expansion_beam']} (beam={record['expansion_beam_size']}) "
                    f"pool_rank={record['rank_in_full_pool']}/{record['full_pool_size']}"
                )
                print(
                    f"        effective={record['effective_score']} "
                    f"floor={record['phase_relevance_floor']} "
                    f"clears_floor={record['clears_relevance_floor']} "
                    f"selected={record['selected']}"
                )
            elif not record["eligible"]:
                print(f"        ineligible: {record['ineligibility_reason']}")
            print(
                f"        recall_vs_pattern={record['recall_against_pattern']} "
                f"exposed_n={record['exposed_n_full_cohort']}"
            )
        print(
            f"  pool best recall={entry['pool_best_recall']} at rank "
            f"{entry['pool_best_rule_rank']}: [{entry['pool_best_rule']}]; "
            f"{entry['pool_full_match_candidates']} full-match rules in pool"
        )
        actual = cast("dict[str, Any] | None", entry.get("stage_6_actual"))
        if actual is not None:
            print(
                f"  S6 actual ({actual['candidate_id']}): verdict={actual['verdict']} "
                f"evidence={actual['evidence_level']} matched={actual['matched_patterns']}"
            )
        counterfactual = cast("dict[str, Any] | None", entry.get("stage_6_counterfactual"))
        if counterfactual is not None:
            print(
                f"  S6 COUNTERFACTUAL (never selected): verdict={counterfactual['verdict']} "
                f"evidence={counterfactual['evidence_level']} "
                f"failed_gates={counterfactual['failed_gates']}"
            )
        print(f"  pattern recovered by the committed run: {entry['recovered_by_committed_run']}")
        print(
            f"  >>> ORACLE BRANCH FIRST FAILING STAGE: {entry['oracle_branch_first_failing_stage']}"
        )
        print(f"      {entry['oracle_branch_first_failing_stage_detail']}")

    print("\n=== Summary (scoreable patterns) ===")
    print(f"  {'pattern':<8} {'recovered':<10} {'oracle branch dies at'}")
    for entry in cast(list[dict[str, Any]], payload["patterns"]):
        if not entry["scoreable"]:
            continue
        recovered = "yes" if entry["recovered_by_committed_run"] else "no"
        print(
            f"  {entry['pattern_id']:<8} {recovered:<10} "
            f"{entry['oracle_branch_first_failing_stage']}"
        )


if __name__ == "__main__":
    main()
