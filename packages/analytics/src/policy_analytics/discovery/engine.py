"""Deterministic, interpretable candidate-pattern discovery (TASK-015/TASK-016/TASK-058/TASK-060).

The engine searches conjunctions of simple decision-time conditions. It selects rules only on the
development split and reports later splits as stability diagnostics; it performs no inference and
makes no causal claim. `TASK-058` (`HANDOFF-043` remediation part 2) added a precision term to the
beam-survival score (`_development_score`) so candidates are not selected on raw total exposure
alone. `TASK-060` added greedy marginal-gain diversity to top-K *selection*
(`_greedy_diverse_select`) — a distinct concern from `_development_score`: fixing how well one rule
scores does not stop the reported set from being dominated by near-duplicate rescalings of the
single strongest mechanism. A live evaluation of that mechanism found it, at full strength, could
admit a statistically thin, low-quality-but-low-overlap candidate (including one that reached a
confounding trap validation's fixed adjustment set does not catch — see `ADR-036`); `v0.3.1` adds a
relevance floor (`min_diversity_relevance_ratio`) and a less aggressive default discount weight,
addressing the search side generically without touching validation. A follow-up diagnostic
(`scripts/diagnose_candidate_pool_recall.py`, `ADR-038`) then found that floor itself also excludes
genuine weak signal, not just the noise it was built to stop; `v0.4.0` (`ADR-039`) credits a rule's
cross-split stability (`_temporal_consistency`) before the floor/marginal-gain formula ever see its
score, rather than moving the floor itself. See all three functions' docstrings and
`docs/analytics/discovery-engine-v0.md`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol, cast

import polars as pl

from policy_analytics.discovery.actionability import actionability_label


class OutcomeDefinition(Protocol):
    @property
    def outcome_id(self) -> str: ...

    @property
    def column(self) -> str: ...

    @property
    def unit(self) -> str: ...

    @property
    def higher_is_worse(self) -> bool: ...

    @property
    def harm_multiplier(self) -> int: ...


Operator = Literal["eq", "ge", "lt"]
DISCOVERY_METHOD_VERSION = "discovery-engine-v0.4.0"


@dataclass(frozen=True, slots=True, order=True)
class Condition:
    feature: str
    operator: Operator
    value: str | float | bool


@dataclass(frozen=True, slots=True)
class DiscoveryConfig:
    seed: int = 1729
    min_support: float = 0.01
    max_support: float = 0.40
    min_n: int = 40
    max_conditions: int = 3
    beam_width: int = 80
    top_k: int = 15
    numeric_quantiles: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8)
    max_categorical_levels: int = 12
    max_candidate_jaccard: float = 0.85
    max_candidates_per_atom: int = 5
    #: Exponent applied to `n_exposed` in the beam-survival score (see `_development_score`).
    #: `1.0` reproduces `discovery-engine-v0.1.0`'s pure-total-exposure ranking exactly (linear in
    #: population). The default `0.5` (TASK-058, `HANDOFF-043` remediation part 2) dampens the
    #: reward for adding population that dilutes per-booking harm, so a rule that grows mainly by
    #: broadening rather than by finding a genuinely stronger effect no longer automatically beats
    #: a smaller, purer one. Must be in `(0.0, 1.0]`. Changing it is a discovery-method decision,
    #: not a per-run tuning knob — see `docs/analytics/discovery-engine-v0.md`.
    population_score_exponent: float = 0.5
    #: Weight of the overlap discount in top-K selection (see `_greedy_diverse_select`). At each
    #: selection round, a remaining rule's `_development_score` is multiplied by
    #: `1 - diversity_discount_weight * max_overlap_with_already_selected`. `0.0` disables the
    #: discount entirely, which makes greedy selection choose in pure score order — an exact
    #: reproduction of `discovery-engine-v0.2.0`'s selection sequence (regression-tested). The
    #: default `1.0` (TASK-060) applies the full discount: a rule that fully overlaps something
    #: already selected can contribute nothing further to the top-K regardless of its own raw
    #: score. `max_candidate_jaccard` remains a hard ceiling independent of this weight — a rule
    #: over that ceiling is skipped outright, never merely deprioritized.
    #:
    #: **v0.3.1 (TASK-060 iteration):** default lowered `1.0` -> `0.5`. At full strength, a rule
    #: with near-zero overlap against everything already selected keeps ~all of its own raw score
    #: regardless of how weak that raw score is — the classic failure mode of pure diversity
    #: search (maximal-marginal-relevance literature): once the strong, low-overlap candidates are
    #: exhausted, an obscure, statistically thin corner of the search space can out-rank a
    #: perfectly reasonable near-duplicate purely by being untouched by anything else, not by
    #: being a good candidate. `0.5` still rewards genuine diversity (see
    #: `min_diversity_relevance_ratio` below for the complementary floor) without letting overlap
    #: alone override raw quality as completely.
    diversity_discount_weight: float = 0.5
    #: Minimum raw `_development_score`, as a fraction of the strongest score in the same selection
    #: phase (interactions or singletons, scored independently), a rule must reach before the
    #: greedy-diverse loop will consider it at all (TASK-060 iteration). Diversity picks a rule
    #: because it does not overlap what is already selected; nothing in that criterion requires the
    #: rule to be any good on its own, so an otherwise-eligible but statistically thin rule can win
    #: a round purely by being in an unexplored corner of the search space. The floor blocks that:
    #: a rule below `min_diversity_relevance_ratio * best_score_in_phase` never enters the
    #: candidate pool for selection, however low its overlap. `0.0` disables the floor (the
    #: original TASK-060 behavior, too permissive on its own); must be in `[0.0, 1.0]`.
    #:
    #: **Unchanged by the `v0.4.0` stability-credit iteration below.** A live diagnostic
    #: (`scripts/diagnose_candidate_pool_recall.py`, `ADR-038`) found this floor's genuine cost:
    #: several true patterns' best-matching pool candidates sit at 0.11-0.33 of their phase's best
    #: raw score, well under `0.5`, so the floor that stops noise also blocks them. Lowering this
    #: ratio globally was considered and rejected (`ADR-039`) — it reopens the same noise/trap risk
    #: `v0.3.1` fixed. `stability_credit_weight` instead changes what gets compared against this
    #: same, unmoved floor.
    min_diversity_relevance_ratio: float = 0.5
    #: Credit applied to a rule's raw `_development_score` before either the relevance floor or the
    #: marginal-gain formula sees it (`TASK-060` iteration, `ADR-039`):
    #: `effective_score = development_score * (1 + stability_credit_weight * temporal_consistency)`,
    #: where `temporal_consistency` is the same later-split direction-agreement fraction already
    #: reported on every final candidate (`Candidate.temporal_direction_consistency`), just computed
    #: earlier so selection can use it too. A rule with no later-split exposure gets `0.0` credit,
    #: never treated as stable — the same conservative convention `TASK-016`'s ranking module uses.
    #: References no specific feature or trap; the same formula applies to every rule regardless of
    #: which columns its conditions touch. `0.0` reproduces `v0.3.1` exactly (regression-tested);
    #: must be in `[0.0, 1.0]`.
    stability_credit_weight: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 < self.population_score_exponent <= 1.0:
            raise ValueError("population_score_exponent must be in (0.0, 1.0]")
        if not 0.0 <= self.diversity_discount_weight <= 1.0:
            raise ValueError("diversity_discount_weight must be in [0.0, 1.0]")
        if not 0.0 <= self.min_diversity_relevance_ratio <= 1.0:
            raise ValueError("min_diversity_relevance_ratio must be in [0.0, 1.0]")
        if not 0.0 <= self.stability_credit_weight <= 1.0:
            raise ValueError("stability_credit_weight must be in [0.0, 1.0]")


@dataclass(frozen=True, slots=True)
class SplitMetric:
    split: str
    n_population: int
    n_exposed: int
    support: float
    exposed_mean: float
    comparison_mean: float
    raw_difference: float
    harm_per_booking: float
    historical_exposure: float


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    conditions: tuple[Condition, ...]
    fit_split: str
    development: SplitMetric
    validation: SplitMetric | None
    future_holdout: SplitMetric | None
    temporal_direction_consistency: float
    actionability: str
    rank_score: float
    warnings: tuple[str, ...]


def _condition_expr(condition: Condition) -> pl.Expr:
    column = pl.col(condition.feature)
    if condition.operator == "eq":
        return column == condition.value
    if condition.operator == "ge":
        return column >= condition.value
    return column < condition.value


def _rule_expr(rule: tuple[Condition, ...]) -> pl.Expr:
    expression = _condition_expr(rule[0])
    for condition in rule[1:]:
        expression &= _condition_expr(condition)
    return expression


def _metric(
    frame: pl.DataFrame, rule: tuple[Condition, ...], outcome: OutcomeDefinition, split: str
) -> SplitMetric | None:
    subset = frame.filter(  # pyright: ignore[reportUnknownMemberType]
        pl.col("split_label") == split
    )
    exposed = subset.filter(_rule_expr(rule))  # pyright: ignore[reportUnknownMemberType]
    comparison = subset.filter(~_rule_expr(rule))  # pyright: ignore[reportUnknownMemberType]
    if exposed.is_empty() or comparison.is_empty():
        return None
    exposed_mean = cast(float, exposed[outcome.column].mean())
    comparison_mean = cast(float, comparison[outcome.column].mean())
    difference = exposed_mean - comparison_mean
    harm = difference * outcome.harm_multiplier
    return SplitMetric(
        split=split,
        n_population=subset.height,
        n_exposed=exposed.height,
        support=exposed.height / subset.height,
        exposed_mean=exposed_mean,
        comparison_mean=comparison_mean,
        raw_difference=difference,
        harm_per_booking=harm,
        historical_exposure=harm * exposed.height,
    )


def _atoms(
    development: pl.DataFrame, features: tuple[str, ...], config: DiscoveryConfig
) -> tuple[Condition, ...]:
    atoms: set[Condition] = set()
    for feature in features:
        dtype = development.schema[feature]
        if dtype.is_numeric():
            for quantile in config.numeric_quantiles:
                value = development[feature].quantile(quantile, interpolation="nearest")
                if value is not None:
                    threshold = round(float(value), 8)
                    atoms.add(Condition(feature, "ge", threshold))
                    atoms.add(Condition(feature, "lt", threshold))
        else:
            values = development[feature].drop_nulls().unique().sort().to_list()
            if len(values) <= config.max_categorical_levels:
                atoms.update(Condition(feature, "eq", value) for value in values)
    return tuple(sorted(atoms))


def _eligible(metric: SplitMetric | None, config: DiscoveryConfig) -> bool:
    return bool(
        metric
        and metric.n_exposed >= config.min_n
        and config.min_support <= metric.support <= config.max_support
        and metric.harm_per_booking > 0
    )


def _development_score(metric: SplitMetric, condition_count: int, config: DiscoveryConfig) -> float:
    # historical_exposure = harm_per_booking * n_exposed rewards material, supported rules but is
    # linear in population: a rule that grows N mainly by absorbing bookings with a weaker (but
    # still same-signed) effect always scores higher than a smaller, purer rule with the same or
    # larger total exposure, even though the larger one is a worse estimate of any one underlying
    # mechanism (HANDOFF-043 §3.6: matched candidates' exposed populations ran ~15-16x larger than
    # the true patterns they partially recovered). Raising n_exposed to `population_score_exponent`
    # < 1 makes the score grow sub-linearly in population, so a narrower rule with a stronger
    # per-booking effect can now out-score a broader, more diluted one at comparable total
    # exposure — a geometric-mean-style balance between total materiality and per-booking purity,
    # not a preference for narrowness on its own (a genuinely broad, undiluted true effect still
    # wins). The mild complexity penalty prefers concise rules when descriptive exposure is
    # similar. No validation/holdout outcome enters either term.
    population_component = metric.n_exposed**config.population_score_exponent
    magnitude = metric.harm_per_booking * population_component
    return magnitude / (1.0 + 0.15 * (condition_count - 1))


def _exposed_rows(frame: pl.DataFrame, rule: tuple[Condition, ...]) -> frozenset[int]:
    mask = frame.select(_rule_expr(rule).alias("exposed"))["exposed"].to_list()
    return frozenset(index for index, exposed in enumerate(mask) if exposed)


def _jaccard(left: frozenset[int], right: frozenset[int]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


@dataclass(frozen=True, slots=True)
class _Stability:
    validation: SplitMetric | None
    future_holdout: SplitMetric | None
    consistency: float


def _temporal_consistency(
    frame: pl.DataFrame, rule: tuple[Condition, ...], outcome: OutcomeDefinition
) -> _Stability:
    """Share of available later chronological splits whose harm direction agrees with development
    (which is uniformly harmful for anything in `scored` — `_eligible` already requires
    `harm_per_booking > 0`, so no separate reference sign is needed). `0.0`, never omitted or
    treated as passing, when neither later split has any exposure — the same conservative
    convention `TASK-016`'s ranking module uses for missing stability.
    """
    validation = _metric(frame, rule, outcome, "validation")
    future = _metric(frame, rule, outcome, "future_holdout")
    available = [metric for metric in (validation, future) if metric is not None]
    consistency = (
        sum(metric.harm_per_booking > 0 for metric in available) / len(available)
        if available
        else 0.0
    )
    return _Stability(validation, future, consistency)


def _apply_stability_credit(raw_score: float, consistency: float, weight: float) -> float:
    """`effective_score` fed to top-K selection (`_greedy_diverse_select`), not to the beam search
    itself: a rule's raw `_development_score` credited by its own cross-split stability, so a
    weak-but-consistent rule can compete for a selection slot a raw-score-only comparison would
    never let it reach (`TASK-060` iteration, `ADR-039`). References no specific feature, trap, or
    pattern — the identical formula applies to every rule regardless of which columns its
    conditions touch. `weight=0.0` returns `raw_score` unchanged exactly, for any `consistency`.
    """
    return raw_score * (1.0 + weight * consistency)


def _greedy_diverse_select(
    pool: list[tuple[Condition, ...]],
    effective_score: dict[tuple[Condition, ...], float],
    exposures: dict[tuple[Condition, ...], frozenset[int]],
    config: DiscoveryConfig,
    selected: list[tuple[Condition, ...]],
    selected_exposures: list[frozenset[int]],
    atom_usage: dict[Condition, int],
    max_overlap: dict[tuple[Condition, ...], float],
) -> None:
    """Greedily fill remaining top-K slots from `pool`, by marginal gain rather than raw score
    (TASK-060). `_development_score` (TASK-058/ADR-023) already fixes how any single rule is
    scored; selecting purely by that score, as v0.1.0/v0.2.0 did, tends to fill the reported set
    with near-duplicate rescalings of whichever single mechanism has the strongest raw signal —
    differently-thresholded variants of the same underlying pattern, individually under
    `max_candidate_jaccard` but collectively redundant — rather than surfacing genuinely distinct
    mechanisms. On `task-058-remediation-20260817-001`, 13 of 15 reported candidates turned out to
    be rescalings of one pattern (`P01`); only 2 of the 9 true patterns were represented at all.

    Each round, every remaining eligible rule's own score is discounted by its current maximum
    development-split exposure overlap (Jaccard) with everything already selected — the discount
    is updated incrementally against only the most recently selected rule each round, not
    recomputed from scratch against the whole selected set every time. `max_candidate_jaccard`
    remains a hard ceiling independent of the discount: a rule still over it after discounting is
    skipped outright, never merely deprioritized (mirrors the pre-TASK-060 behavior, just no longer
    the *only* diversity control).

    Mutates `selected`/`selected_exposures`/`atom_usage`/`max_overlap` in place so two calls (one
    per pool) can share running state — `discover_candidates` uses this to keep the existing
    interactions-before-singletons preference: interactions fill the top-K first, singletons only
    considered for slots interactions didn't fill, exactly as before TASK-060.

    **v0.3.1 (TASK-060 iteration):** a live `TASK-019`/`TASK-028` run against
    `task-060-remediation-20260818-001` found this mechanism, at its original full strength,
    let a statistically thin, low-overlap-only candidate (`CAND-012`) into the top-K — Top-10
    precision fell 90%->40% and a confounding trap (`T03`) reached `PASS` (`ADR-036`,
    `HANDOFF-052`). Root cause diagnosed there is a validation-gate gap (`G06`'s fixed adjustment
    set), explicitly *not* patched here or in `apply.py` — doing so would tune methodology to a
    result seen only after opening `hidden_ground_truth.json`, exactly what `ADR-007` forbids. This
    function's own contribution to the failure — nothing in pure overlap-based marginal gain
    requires a "diverse" pick to be any good on its own — is addressed generically below via
    `min_diversity_relevance_ratio`, motivated by the general maximal-marginal-relevance lesson
    (diversity needs a relevance floor), not by this specific trap's features or confounders.

    **v0.4.0 (`TASK-060` iteration, `ADR-039`):** takes `effective_score`, not the raw
    `_development_score` — see `discover_candidates`, which blends in each rule's cross-split
    stability (`_temporal_consistency`) before either the floor or the marginal-gain formula ever
    sees a score. `min_diversity_relevance_ratio` and `diversity_discount_weight` are themselves
    unchanged; only what gets compared against them changed.
    """
    if not pool:
        return
    best_pool_score = max(effective_score[rule] for rule in pool)
    score_floor = config.min_diversity_relevance_ratio * best_pool_score
    remaining = [rule for rule in pool if effective_score[rule] >= score_floor]
    while remaining and len(selected) < config.top_k:
        best_rule: tuple[Condition, ...] | None = None
        best_marginal = float("-inf")
        for rule in remaining:
            if max_overlap[rule] > config.max_candidate_jaccard:
                continue
            if any(
                atom_usage.get(condition, 0) >= config.max_candidates_per_atom
                for condition in rule
            ):
                continue
            discount = config.diversity_discount_weight * max_overlap[rule]
            marginal = effective_score[rule] * (1.0 - discount)
            if best_rule is None or marginal > best_marginal or (
                marginal == best_marginal and rule < best_rule
            ):
                best_rule, best_marginal = rule, marginal
        if best_rule is None:
            break
        selected.append(best_rule)
        exposure = exposures[best_rule]
        selected_exposures.append(exposure)
        for condition in best_rule:
            atom_usage[condition] = atom_usage.get(condition, 0) + 1
        remaining.remove(best_rule)
        for rule in remaining:
            overlap = _jaccard(exposures[rule], exposure)
            if overlap > max_overlap[rule]:
                max_overlap[rule] = overlap


def discover_candidates(
    frame: pl.DataFrame,
    feature_columns: tuple[str, ...],
    outcome: OutcomeDefinition,
    config: DiscoveryConfig | None = None,
) -> dict[str, Any]:
    """Search and rank immutable candidate rules using development data only."""
    config = config or DiscoveryConfig()
    required = {*feature_columns, outcome.column, "split_label"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"discovery frame is missing columns: {missing}")
    if frame[outcome.column].null_count():
        raise ValueError(f"primary outcome {outcome.column} contains missing values")

    development = frame.filter(  # pyright: ignore[reportUnknownMemberType]
        pl.col("split_label") == "development"
    )
    atoms = _atoms(development, feature_columns, config)
    evaluated = 0
    scored: dict[tuple[Condition, ...], tuple[float, SplitMetric]] = {}
    frontier: list[tuple[Condition, ...]] = [(atom,) for atom in atoms]

    for depth in range(1, config.max_conditions + 1):
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
                        continue
                scored[rule] = (_development_score(metric, depth, config), metric)

        beam = [
            rule
            for rule, _ in sorted(scored.items(), key=lambda item: (-item[1][0], item[0]))
            if len(rule) == depth
        ][: config.beam_width]
        if depth == config.max_conditions:
            break
        for rule in beam:
            used = {condition.feature for condition in rule}
            for atom in atoms:
                if atom.feature in used:
                    continue
                expanded = tuple(sorted((*rule, atom)))
                next_frontier.append(expanded)
        frontier = sorted(set(next_frontier))

    ranked_rules = sorted(scored, key=lambda rule: (-scored[rule][0], rule))
    # Prefer interactions; singletons remain eligible fallbacks and diagnostics.
    interactions = [rule for rule in ranked_rules if len(rule) >= 2]
    singles = [rule for rule in ranked_rules if len(rule) == 1]

    selected: list[tuple[Condition, ...]] = []
    selected_exposures: list[frozenset[int]] = []
    atom_usage: dict[Condition, int] = {}
    max_overlap: dict[tuple[Condition, ...], float] = {}
    exposures: dict[tuple[Condition, ...], frozenset[int]] = {}
    stability: dict[tuple[Condition, ...], _Stability] = {}
    effective_score: dict[tuple[Condition, ...], float] = {}

    def _prepare(pool: list[tuple[Condition, ...]]) -> None:
        # Exposure/stability are only computed once per rule, and only for rules a phase actually
        # needs — singles are never touched at all when interactions alone already fill the top-K
        # (the common case), matching the pre-TASK-060 cost profile. Stability is computed here,
        # not only after selection, specifically so it can inform selection itself (v0.4.0) — the
        # final assembly loop below reuses the same cache rather than recomputing it.
        for rule in pool:
            if rule not in exposures:
                exposures[rule] = _exposed_rows(development, rule)
                max_overlap[rule] = 0.0
                info = _temporal_consistency(frame, rule, outcome)
                stability[rule] = info
                effective_score[rule] = _apply_stability_credit(
                    scored[rule][0], info.consistency, config.stability_credit_weight
                )

    # Two phases, not one combined greedy pass, so interactions still fill the top-K before any
    # singleton is considered regardless of relative score (matches pre-TASK-060 ordering exactly).
    _prepare(interactions)
    _greedy_diverse_select(
        interactions, effective_score, exposures, config, selected, selected_exposures,
        atom_usage, max_overlap,
    )
    if len(selected) < config.top_k:
        _prepare(singles)
        _greedy_diverse_select(
            singles, effective_score, exposures, config, selected, selected_exposures,
            atom_usage, max_overlap,
        )
    candidates: list[Candidate] = []
    for index, rule in enumerate(selected, start=1):
        score, development_metric = scored[rule]
        info = stability[rule]
        validation = info.validation
        future = info.future_holdout
        consistency = info.consistency
        warnings = ["Raw descriptive association; not adjusted and not causal."]
        if consistency < 1.0:
            warnings.append("Harm direction is not stable across all later chronological splits.")
        if actionability_label(rule) != "HIGH":
            warnings.append(
                "Actionability requires business review; condition may not be controllable."
            )
        candidates.append(
            Candidate(
                candidate_id=f"CAND-{index:03d}",
                conditions=rule,
                fit_split="development",
                development=development_metric,
                validation=validation,
                future_holdout=future,
                temporal_direction_consistency=consistency,
                actionability=actionability_label(rule),
                rank_score=score,
                warnings=tuple(warnings),
            )
        )
    return {
        "methodology_version": DISCOVERY_METHOD_VERSION,
        "search": {**asdict(config), "evaluated_hypotheses": evaluated},
        "outcome": {
            "outcome_id": outcome.outcome_id,
            "column": outcome.column,
            "unit": outcome.unit,
            "higher_is_worse": outcome.higher_is_worse,
        },
        "candidate_count": len(candidates),
        "candidates": [asdict(candidate) for candidate in candidates],
        "evidence_boundary": "Candidate discovery only; requires Statistics validation.",
    }
