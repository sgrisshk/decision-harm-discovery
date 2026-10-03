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
score, rather than moving the floor itself — empirically null (the dominant pattern was itself
stable). `v0.4.1` (`ADR-040`) instead changes the floor's reference point from the pool's single
maximum score (always the dominant pattern) to a robust percentile of the pool's own score
distribution (`_percentile`), still without moving `min_diversity_relevance_ratio` itself. See all
four functions' docstrings and `docs/analytics/discovery-engine-v0.md`.

`v0.5.0` (`TASK-064`, `ADR-045`/`ADR-046`) changes only the expansion beam: the global score core
is supplemented by a bounded reserve for feature/operator structures, so an eligible lower-score
pair can form a third condition instead of every expansion right going to dominant rescalings.
It does not change eligibility, scoring, depth, or final selection.

`v0.6.0` (`TASK-068`, `ADR-056`/`ADR-057`) adds a feature-identity diversity cap at final
candidate selection — orthogonal to, and strictly additive over, `_greedy_diverse_select`
(`TASK-060`) and the expansion beam (`TASK-064`), neither of which is modified. A portability
postmortem (`ADR-055`) found every one of a run's committed candidates anchored on the same one
or two features, a crowding axis neither existing mechanism guards: population-overlap diversity
does not stop many candidates from differing only in threshold/category on the same dominant
feature, and the expansion beam's structural reserve operates on `(feature, operator)` shape only
during search, not on final-selection feature identity. `_apply_feature_identity_cap` runs
strictly after `_greedy_diverse_select` returns,
trimming an already-ranked, already-diversified selection down to `top_k` while capping how many
final slots any single feature name may occupy — never re-ranking, never reconsidering a rule
`_greedy_diverse_select` already excluded. See its docstring and
`docs/analytics/discovery-engine-v0.md`.

`v0.6.1` (`TASK-071`) is a local correctness fix to the depth->1 leave-one-out redundancy check in
`discover_candidates`, not a mechanism change: it compares each rule's exposed *row set*
(`_exposed_rows`) against each immediate leave-one-out parent's exposed row set, instead of only
their `n_exposed` counts. A conjunctive child rule's exposed rows are always a subset of an
immediate parent's (dropping a required condition can only admit more rows), so equal counts there
already implied equal row sets — verified both by proof and empirically (two full real searches,
69,311 child/parent pairs, zero disagreements between the two checks) — so this changes no
candidate-stage outcome on any domain checked. It replaces an implicit, non-obvious subset argument
with a comparison that is correct by construction and does not depend on that argument continuing
to hold if this call site is ever changed. See its inline comment and
`docs/analytics/discovery-engine-v0.md`.

`TASK-097` (implementing `TASK-095`'s twice-reviewed design,
`docs/analytics/task-095-k1-reservation-design.md`) adds a bounded, opt-in Stage 3 to final
candidate assembly: `DiscoveryConfig.reserve_k1_slot` (default `False`) reserves at most one final
top-K slot for the single best-qualifying `k==1` candidate when interactions alone would otherwise
fill every slot (`docs/benchmark/task-094-k1-selection-scoping.md` found this is the structural
norm, not an edge case, and that a genuinely high-quality single can be unreachable "regardless of
relative score" purely because of the interactions-first ordering). `False` is a genuine no-op,
confirmed structurally: the new `_reserve_k1_slot` code path is never evaluated, not merely
output-equivalent, and `DISCOVERY_METHOD_VERSION` does not change either way — this addition does
not bump it, matching the design's own explicit "unchanged... when this field is False" scoping of
that claim. See `_reserve_k1_slot`'s own docstring for the mechanism and
`docs/analytics/task-095-k1-reservation-design.md` §4 for the full, twice-reviewed specification.

`v0.6.2` (`TASK-101`, `ADR-096`) changes `_eligible()`'s handling of `DiscoveryConfig.max_support`
only. `TASK-100` found `OL01` (`seller_customer_cross_state -> OUTCOME_LATE`, real Olist data)
oracle-detectable at both tested scales but never found by search: its raw rule has ~66% support,
above `max_support=0.40`, so `_eligible()` excluded it at depth 1 regardless of the effect's real
strength or safety. Tracing why `max_support` exists at all
(`docs/analytics/discovery-design.md` §3, `TASK-015`'s own pre-code design) found the ceiling
protects against a comparison group too small/unstable to make the exposed-vs-comparison contrast
meaningful — and that same design text already specified a second, independent condition
(`comparison_n satisfies the same absolute minimum count`) that `_eligible()` never actually
implemented in any version through `v0.6.1`. `v0.6.2` implements exactly that: a rule over
`max_support` is now also eligible when its comparison group's absolute size clears the same
`min_n` floor already required of the exposed side. `max_support=0.40` itself is untouched — every
rule at or below it keeps exactly the prior verdict (a strict widening, not a raised ceiling); no
new tunable is introduced. This is a genuine, unconditional behavior change (no opt-in flag, unlike
`v0.6.0`'s `max_feature_identity_fraction` or `TASK-097`'s `reserve_k1_slot`), hence the version
bump. See `_eligible()`'s own docstring, `DiscoveryConfig.max_support`'s field docstring, and
`ADR-096`/`docs/analytics/task-101-max-support-search-eligibility-fix.md` for the full citation
trail, both-direction regression evidence, and cross-domain check.

`v0.6.3` (`TASK-112`, `ADR-113`) changes `_development_score`'s volume/support component only --
the first actual engine code change in the whole `TASK-092`-`TASK-112` diagnostic arc. `TASK-111`
(`H111`, independently reviewed `SUPPORTED`, 7/10 FNs incl. 4/5 `S6`) found the real formula's
`n_exposed**population_score_exponent` term structurally rewards a candidate for covering more
rows even at equivalent per-booking evidence quality, because every broad competitor examined has
far larger `n_exposed` than the corresponding specific/canonical rule (7-23x median, `C14`
excepted at 1.77x) -- the volume term inflates the broad side's score far more than the specific
side's, regardless of which is the better estimate of a true, undiluted effect. `ADR-113`
authorized exactly one parameter-free fix: removing the volume term entirely (its own natural
`exponent -> 0` case -- a deletion, not a new coefficient picked by experiment):

```
OLD: score = harm_per_booking * n_exposed**population_score_exponent / (1 + 0.15*(k-1))
NEW: score = harm_per_booking                                        / (1 + 0.15*(k-1))
```

`DiscoveryConfig.population_score_exponent` itself is untouched (default `0.5`, bounds unchanged)
per `ADR-113`'s "every other component, weight ... untouched" scope -- it simply stops being read
by `_development_score`; see that field's own docstring note. `_eligible()`'s `min_n` floor
(default `40`, unchanged) already gates how little exposure a rule may have before it is scored at
all, so a purely rate-based score does not newly admit statistically thin rules -- reliability is
enforced by eligibility, not by the score shape. This is a genuine, unconditional behavior change
(no opt-in flag), hence the version bump, following the same precedent as `v0.6.2`
(`TASK-101`/`ADR-096`) above. Pre-registered counterfactual, Mechanism PASS evaluation, regression/
kill tests, and the paired `4101-4130` go/no-go are in
`docs/benchmark/task-112-specificity-neutral-score-results.md` and
`docs/benchmark/task-112-evidence/`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
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
DISCOVERY_METHOD_VERSION = "discovery-engine-v0.6.3"


@dataclass(frozen=True, slots=True, order=True)
class Condition:
    feature: str
    operator: Operator
    value: str | float | bool


@dataclass(frozen=True, slots=True)
class DiscoveryConfig:
    seed: int = 1729
    min_support: float = 0.01
    #: Support ceiling `_eligible()` enforces below (`TASK-015`, commit `317bde0`). The design
    #: authority (`docs/analytics/discovery-design.md` §3, TASK-015's own pre-code design) states
    #: the reason directly: "The maximum support rejects broad near-baselines masquerading as
    #: subgroups" — a high-support rule leaves too small/unstable a *comparison* group for its
    #: descriptive contrast to mean anything, not "high support is itself suspicious." That same
    #: §3 pseudocode already specified the actual protected quantity as a **second, independent**
    #: condition — `comparison_n satisfies the same absolute minimum count` [as the exposed side]
    #: — alongside the fractional ceiling below. `engine.py`'s shipped `_eligible()` (every version
    #: through `discovery-engine-v0.6.1`) implemented only the fractional ceiling; the comparison-
    #: count floor the design already called for was never wired in. `TASK-100` found this ceiling
    #: structurally excludes `OL01` (`seller_customer_cross_state -> OUTCOME_LATE`, real Olist
    #: data, ~66% support) from ever being scored, independent of the effect's real strength/safety
    #: (`ADR-096`, `TASK-101`). `TASK-101` recovers the design's own dropped comparison-count floor
    #: (`_eligible()` now also accepts `support > max_support` specifically when
    #: `n_population - n_exposed >= min_n` — the same absolute reliability bar already required of
    #: the exposed side, reused rather than inventing a new tunable) instead of raising this number:
    #: `0.40` is unchanged and still gates the common case exactly as before (every rule at or below
    #: it is unaffected, byte-for-byte); only rules above it get a second, principled chance keyed
    #: to the quantity §3 actually named. See `_eligible()`'s own docstring and `ADR-096`.
    max_support: float = 0.40
    min_n: int = 40
    max_conditions: int = 3
    beam_width: int = 80
    #: In addition to the global top-`beam_width` rules at each expandable depth, retain up to this
    #: many best rules per structural signature (`(feature, operator)` tuples, values excluded).
    #: This gives a lower-scoring but eligible feature/operator combination a bounded chance to
    #: form a deeper interaction instead of allocating every expansion right to rescalings of the
    #: globally strongest structures. `0` reproduces v0.4.1's score-only beam exactly. The default
    #: `2` is the smallest quota that distinguishes two categorical combinations sharing the same
    #: feature/operator structure while remaining independent of feature names and values.
    beam_rules_per_structure: int = 2
    #: Hard ceiling on the combined score-core plus structural reserve at every depth. Keeps the
    #: expanded hypothesis family bounded when a future dataset has many eligible feature/operator
    #: structures. Must be at least `beam_width`; the default leaves headroom above the 418-rule
    #: depth-2 beam observed in the pre-code public trace without encoding any target identity.
    max_expansion_beam_size: int = 512
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
    #:
    #: **No longer read by `_development_score` as of `v0.6.3` (`TASK-112`, `ADR-113`).** `TASK-111`
    #: (`H111`) found this term structurally rewards covering more rows at equivalent per-booking
    #: evidence quality; `ADR-113` authorized the one parameter-free fix available -- removing the
    #: term entirely rather than picking a different exponent (any other value would just be a new
    #: hand-tuned coefficient, the thing `ADR-113` explicitly forbids). The field itself, its
    #: default, and its validation bounds are untouched (`ADR-113`: "every other component, weight
    #: ... untouched") -- kept, not deleted, so this stays a minimal, legible diff and so any future
    #: task re-introducing a volume term has a documented prior value to reason about; it currently
    #: has no effect on search or scoring. See `_development_score`'s own docstring and the module
    #: docstring's `v0.6.3` entry.
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
    #: Minimum `effective_score`, as a fraction of a reference value drawn from the same selection
    #: phase's pool (interactions or singletons, scored independently — see
    #: `relevance_floor_percentile` below for what the reference actually is), a rule must reach
    #: before the greedy-diverse loop will consider it at all (TASK-060 iteration). Diversity picks
    #: a rule because it does not overlap what is already selected; nothing in that criterion
    #: requires the rule to be any good on its own, so an otherwise-eligible but statistically thin
    #: rule can win a round purely by being in an unexplored corner of the search space. The floor
    #: blocks that: a rule below `min_diversity_relevance_ratio * reference` never enters the
    #: candidate pool for selection, however low its overlap. `0.0` disables the floor (the
    #: original TASK-060 behavior, too permissive on its own); must be in `[0.0, 1.0]`.
    #:
    #: **Value unchanged by the `v0.4.0`/`v0.4.1` iterations below** — both changed what this ratio
    #: is measured *against*, never the ratio itself. A live diagnostic
    #: (`scripts/diagnose_candidate_pool_recall.py`, `ADR-038`) found this floor's genuine cost:
    #: several true patterns' best-matching pool candidates sit at 0.11-0.33 of their phase's
    #: *maximum* raw score, well under `0.5`, so the floor that stops noise also blocked them.
    #: Lowering this ratio globally was considered and rejected (`ADR-038`) — it reopens the same
    #: noise/trap risk `v0.3.1` fixed. `stability_credit_weight` (`v0.4.0`, `ADR-039`, empirically
    #: null) and `relevance_floor_percentile` (`v0.4.1`, `ADR-040`) each change what gets compared
    #: against this same, unmoved ratio instead.
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
    #:
    #: **Empirically null on `task-060-iteration-20260820-003` (`ADR-039`):** the dominant pattern
    #: and the pool's best genuinely-distinct candidates turned out equally or more stable than it,
    #: so a uniform credit could not differentiate them — the resulting official run was
    #: byte-identical to the one before this field existed. Retained (not reverted: a real,
    #: correctly-working capability, just insufficient alone) — `v0.4.1` below changes a different
    #: axis instead.
    stability_credit_weight: float = 0.5
    #: What `min_diversity_relevance_ratio` is a fraction *of* (`TASK-060` iteration, `ADR-040`).
    #: `1.0` (the `v0.3.1`/`v0.4.0` behavior) uses the single largest `effective_score` in the
    #: phase's pool — which `ADR-038`'s diagnostic showed is always the dominant rescaling family
    #: (largest population x effect), so the floor ends up measured against one outlier rather than
    #: the pool's typical quality, systematically excluding weaker genuine patterns (`P02`/`P08`/
    #: `P09` sat at 0.11-0.33 of that maximum) without regard to whether they are noise or signal.
    #: The default `0.75` instead uses the pool's own 75th-percentile `effective_score` (computed
    #: once per phase, before selection runs) as the reference — a standard robust-statistics
    #: choice: far less sensitive to a single extreme outlier than the maximum, while still
    #: requiring a rule to be in its phase's upper quartile, unlike the median (`0.5`), which would
    #: let roughly half the eligible pool through regardless of what the diversity mechanism then
    #: does. `min_diversity_relevance_ratio` itself is unchanged; only what it multiplies changed.
    #: References no specific feature, trap, or pattern — a property of the pool's own score
    #: distribution only. Must be in `(0.0, 1.0]`; `1.0` reproduces `v0.4.0` exactly
    #: (regression-tested).
    relevance_floor_percentile: float = 0.75
    #: Maximum fraction of `top_k` final selected slots any single feature identity — a condition's
    #: `feature` string, independent of its operator/value/threshold — may occupy
    #: (`TASK-068`, `ADR-056`/`ADR-057`). `1.0` (default) never binds: the resulting per-feature cap
    #: equals `top_k` itself, which no feature can exceed within a `top_k`-sized final set, so the
    #: default reproduces `discovery-engine-v0.5.0` selection exactly (regression-tested). A
    #: portability postmortem (`ADR-055`) found every one of a run's committed candidates anchored
    #: on the same one or two features — a crowding axis neither `_greedy_diverse_select`'s
    #: population-overlap diversity (`TASK-060`) nor the expansion beam's
    #: `(feature, operator)`-structure reserve (`TASK-064`) guards: many candidates can differ only
    #: in threshold/category on the same dominant feature without ever having high row-level
    #: overlap or sharing an exact atom. Every feature a rule's conditions touch counts toward that
    #: feature's own tally (not one designated "primary" feature per rule — see
    #: `_apply_feature_identity_cap`'s docstring for why); a rule is skipped once *any* of its
    #: features would exceed `max(1, floor(max_feature_identity_fraction * top_k))` uses. Applied
    #: strictly after `_greedy_diverse_select` returns, as a pure post-filter over an
    #: already-ranked, already-diversified selection — it never reconsiders a rule that mechanism
    #: excluded and never changes its overlap/relevance-floor/stability computations. References no
    #: specific feature, domain, or dataset; only features the caller already classified
    #: `DECISION_TIME` can appear in any rule's conditions at all, so this cap can never see a
    #: `POST_DECISION`/`OUTCOME`/`UNKNOWN` field. Must be in `[0.0, 1.0]`.
    max_feature_identity_fraction: float = 1.0
    #: Whether final assembly reserves at most one top-K slot for the single best-qualifying k==1
    #: candidate, when interactions alone would otherwise fill every slot (`TASK-095`/`TASK-097`,
    #: `docs/analytics/task-095-k1-reservation-design.md`). `False` (default) is a byte-identical
    #: no-op for candidate selection: the new Stage 3 code path (`_reserve_k1_slot`) is not even
    #: evaluated when this is `False` — `discover_candidates`'s control flow and the selected
    #: candidates themselves (identity, order, count, every per-candidate field) and
    #: `DISCOVERY_METHOD_VERSION` are all unchanged from `discovery-engine-v0.6.1` when this field
    #: is `False`. This does NOT mean the full returned dict is byte-identical: the `"search"`
    #: metadata block already includes `asdict(config)`, which will unconditionally report
    #: `reserve_k1_slot: False` as one more key once this field exists — exactly as every prior
    #: `TASK-060`/`TASK-068` config field addition already changed that same metadata block's key
    #: set, expected and not a defect, but distinct from candidate-selection byte-identity. Must be
    #: explicitly enabled to take effect — matching this project's own convention for every prior
    #: `TASK-060` addition (`diversity_discount_weight`, `min_diversity_relevance_ratio`,
    #: `stability_credit_weight`, `relevance_floor_percentile`, `max_feature_identity_fraction` all
    #: shipped with a no-op default that reproduces the prior version exactly). Not a count: the
    #: reserved-slot count is fixed at 1 by design (`task-095-k1-reservation-design.md` §8) and is
    #: deliberately not exposed as a tunable integer — a larger count needs its own separate,
    #: checked justification, not a config value someone can raise without one.
    reserve_k1_slot: bool = False

    def __post_init__(self) -> None:
        if self.beam_width < 1:
            raise ValueError("beam_width must be at least 1")
        if self.beam_rules_per_structure < 0:
            raise ValueError("beam_rules_per_structure must be non-negative")
        if self.max_expansion_beam_size < self.beam_width:
            raise ValueError("max_expansion_beam_size must be at least beam_width")
        if not 0.0 < self.population_score_exponent <= 1.0:
            raise ValueError("population_score_exponent must be in (0.0, 1.0]")
        if not 0.0 <= self.diversity_discount_weight <= 1.0:
            raise ValueError("diversity_discount_weight must be in [0.0, 1.0]")
        if not 0.0 <= self.min_diversity_relevance_ratio <= 1.0:
            raise ValueError("min_diversity_relevance_ratio must be in [0.0, 1.0]")
        if not 0.0 <= self.stability_credit_weight <= 1.0:
            raise ValueError("stability_credit_weight must be in [0.0, 1.0]")
        if not 0.0 < self.relevance_floor_percentile <= 1.0:
            raise ValueError("relevance_floor_percentile must be in (0.0, 1.0]")
        if not 0.0 <= self.max_feature_identity_fraction <= 1.0:
            raise ValueError("max_feature_identity_fraction must be in [0.0, 1.0]")


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
    """`TASK-101`/`ADR-096`: `max_support` bounds a real risk (`DiscoveryConfig.max_support`'s own
    docstring, `docs/analytics/discovery-design.md` §3) — a comparison group too small/unstable to
    give the exposed-vs-comparison contrast any meaning, not "support above X is inherently bad."
    A rule over `max_support` is still eligible when its *comparison* group's absolute size
    (`n_population - n_exposed`) clears the same `min_n` reliability floor already required of the
    exposed side — the literal quantity §3's own eligibility pseudocode named
    ("comparison_n satisfies the same absolute minimum count") but `_eligible()` never implemented
    before this change. Below/at `max_support`, this reduces to the original comparison
    unconditionally (every rule this project has ever scored at <= max_support keeps exactly the
    same eligibility verdict — this is a strict widening, never a narrowing). No new tunable is
    introduced: `min_n` is reused, not a fresh knob invented to fit any one rule's number.
    """
    if not (
        metric and metric.n_exposed >= config.min_n and metric.harm_per_booking > 0
    ):
        return False
    if metric.support < config.min_support:
        return False
    if metric.support <= config.max_support:
        return True
    n_comparison = metric.n_population - metric.n_exposed
    return n_comparison >= config.min_n


def _development_score(metric: SplitMetric, condition_count: int, config: DiscoveryConfig) -> float:
    # historical_exposure = harm_per_booking * n_exposed rewards material, supported rules but is
    # linear in population: a rule that grows N mainly by absorbing bookings with a weaker (but
    # still same-signed) effect always scores higher than a smaller, purer rule with the same or
    # larger total exposure, even though the larger one is a worse estimate of any one underlying
    # mechanism (HANDOFF-043 §3.6: matched candidates' exposed populations ran ~15-16x larger than
    # the true patterns they partially recovered). `v0.1.0` through `v0.6.2` addressed this by
    # raising n_exposed to `population_score_exponent` < 1 (default 0.5) so the score grows
    # sub-linearly in population -- a geometric-mean-style balance, not a removal of the volume
    # reward. `TASK-111` (`H111`, independently reviewed SUPPORTED, 7/10 FNs incl. 4/5 S6) found
    # that balance still structurally favors a broad, low-specificity rule over a specific one at
    # equivalent per-booking evidence quality, because real broad competitors' n_exposed runs
    # 7-23x the specific rule's (median across 30 seeds, TASK-112 Step 1 pre-registration) --
    # enough for even a damped sqrt(n_exposed) term to dominate. `v0.6.3` (`TASK-112`, `ADR-113`)
    # removes the volume term entirely rather than picking a different exponent (any other value in
    # (0, 1) is just a new hand-tuned coefficient, which ADR-113 explicitly forbids): this is the
    # term's own natural `exponent -> 0` case, i.e. deletion, not a newly-invented free parameter.
    # The resulting score is purely rate-based: two rules with identical harm_per_booking and
    # condition_count score identically regardless of how many rows either one covers. This does
    # not newly admit statistically thin rules -- `_eligible()`'s `min_n` floor (unchanged) already
    # gates how little exposure a rule may have before it is scored at all; reliability is enforced
    # by eligibility, not by this score's shape. `config` is accepted for call-site/signature
    # stability but no longer consulted here; `DiscoveryConfig.population_score_exponent` is
    # unchanged (default, bounds) and simply unread -- see that field's own docstring note. The
    # mild complexity penalty still prefers concise rules when per-booking evidence is similar. No
    # validation/holdout outcome enters either term.
    del config  # population_score_exponent intentionally no longer consulted -- see docstring.
    magnitude = metric.harm_per_booking
    return magnitude / (1.0 + 0.15 * (condition_count - 1))


def _beam_structure(rule: tuple[Condition, ...]) -> tuple[tuple[str, Operator], ...]:
    """Feature/operator shape used only for beam survival; threshold/category values stay blind.

    Two rules with the same columns and operator directions compete inside the same bounded bucket.
    The signature contains no domain taxonomy, feature allow/deny list, pattern ID, or trap hint.
    """
    return tuple((condition.feature, condition.operator) for condition in rule)


def _select_expansion_beam(
    scored: dict[tuple[Condition, ...], tuple[float, SplitMetric]],
    depth: int,
    config: DiscoveryConfig,
) -> list[tuple[Condition, ...]]:
    """Select rules allowed to produce the next depth (`TASK-064`, `ADR-045`).

    The score-core preserves the previous global top-`beam_width` behavior. A bounded structural
    reserve then adds the best `beam_rules_per_structure` rules for each feature/operator shape.
    This changes only whether an already-eligible rule may be expanded; it changes neither
    eligibility, `_development_score`, maximum depth, nor final top-K selection.
    """
    ranked = [
        rule
        for rule, _ in sorted(scored.items(), key=lambda item: (-item[1][0], item[0]))
        if len(rule) == depth
    ]
    core = ranked[: config.beam_width]
    if config.beam_rules_per_structure == 0:
        return core

    selected = set(core)
    structure_usage: dict[tuple[tuple[str, Operator], ...], int] = {}
    for rule in ranked:
        structure = _beam_structure(rule)
        used = structure_usage.get(structure, 0)
        if used >= config.beam_rules_per_structure:
            continue
        selected.add(rule)
        structure_usage[structure] = used + 1
    return [rule for rule in ranked if rule in selected][: config.max_expansion_beam_size]


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


def _percentile(values: list[float], fraction: float) -> float:
    """Linear-interpolation percentile (matches the standard "linear" method): `fraction=1.0`
    returns exactly `max(values)`, `fraction=0.0` returns exactly `min(values)`. Pure statistics
    over whatever `values` it is given — no notion of which rule or feature produced any of them.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    weight = position - lower_index
    return ordered[lower_index] * (1.0 - weight) + ordered[upper_index] * weight


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
    unchanged; only what gets compared against them changed. Empirically null on
    `task-060-iteration-20260820-003` (`ADR-039`) — the dominant pattern turned out at least as
    stable as the genuinely distinct candidates it was competing with, so the credit could not
    tell them apart.

    **v0.4.1 (`TASK-060` iteration, `ADR-040`):** the floor's *reference point* — what
    `min_diversity_relevance_ratio` is a fraction of — changes from the phase's single maximum
    `effective_score` to its `relevance_floor_percentile`-th percentile. `ADR-038`'s diagnostic
    found the maximum is always the dominant rescaling family (largest population x effect), so
    the floor was measured against one outlier rather than the pool's typical quality. The default
    75th percentile is a standard robust-statistics choice: far less sensitive to that outlier than
    the maximum, while still requiring a rule to be in its phase's upper quartile — unlike the
    median, which would let roughly half the pool through regardless of what selection then does.
    `relevance_floor_percentile=1.0` reproduces `v0.4.0`'s reference exactly (the maximum), so
    combined with `stability_credit_weight=0.0` it reproduces `v0.3.1` exactly too
    (regression-tested).
    """
    if not pool:
        return
    reference_score = _percentile(
        [effective_score[rule] for rule in pool], config.relevance_floor_percentile
    )
    score_floor = config.min_diversity_relevance_ratio * reference_score
    remaining = [rule for rule in pool if effective_score[rule] >= score_floor]
    while remaining and len(selected) < config.top_k:
        best_rule: tuple[Condition, ...] | None = None
        best_marginal = float("-inf")
        for rule in remaining:
            if max_overlap[rule] > config.max_candidate_jaccard:
                continue
            if any(
                atom_usage.get(condition, 0) >= config.max_candidates_per_atom for condition in rule
            ):
                continue
            discount = config.diversity_discount_weight * max_overlap[rule]
            marginal = effective_score[rule] * (1.0 - discount)
            if (
                best_rule is None
                or marginal > best_marginal
                or (marginal == best_marginal and rule < best_rule)
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


#: How many multiples of `top_k` worth of extra candidates `discover_candidates` asks
#: `_greedy_diverse_select` for when `max_feature_identity_fraction` is active, so
#: `_apply_feature_identity_cap` has genuinely different alternatives to fall back on instead of
#: only being able to shrink the final set. A fixed, generic bound (not tuned to any domain's
#: result) trading a modest, predictable extra cost for headroom; `_greedy_diverse_select` itself
#: is called completely unmodified — only its own pre-existing `top_k` parameter is set higher for
#: this one internal call, exactly as it would be for any other caller requesting more candidates.
_IDENTITY_CAP_OVERSELECT_MULTIPLIER = 5


def _apply_feature_identity_cap(
    ranked: list[tuple[Condition, ...]], config: DiscoveryConfig
) -> list[tuple[Condition, ...]]:
    """Trim an already-ranked, already-diversified candidate list down to `config.top_k`, capping
    how many final slots any single feature identity may occupy (`TASK-068`, `ADR-056`/`ADR-057`).

    Pure post-filter: `ranked` is exactly `_greedy_diverse_select`'s own output (in the priority
    order it picked things, typically overselected beyond `top_k` — see
    `_IDENTITY_CAP_OVERSELECT_MULTIPLIER`) and this function never re-scores, re-ranks, or
    reconsiders a rule that mechanism already excluded via its overlap/relevance-floor/stability
    logic. It only decides which already-eligible, already-ordered rules make the final `top_k`.

    Every feature a rule's conditions touch counts toward that feature's own tally — not one
    designated "primary" feature per rule. A per-condition designation (e.g. "the first feature in
    canonical sorted order is the anchor") was considered and rejected: canonical order is
    alphabetical, an artifact of `Condition`'s own sort key with no relationship to which feature
    actually drives a rule's effect, so it would crown an arbitrary "anchor" rather than a
    meaningful one. Counting every feature a rule touches instead directly caps how often any
    feature can co-occur in the final set at all, which is what a crowding axis defined at the
    *feature* level (not the "one anchor per rule" level) requires, and needs no dominance
    heuristic — only feature identity as a string key, exactly as `ADR-056` specifies.

    `max_feature_identity_fraction=1.0` (default) is a no-op: `max_per_feature` equals `top_k`,
    which no single feature's count can reach before `final` itself already holds `top_k` entries
    and the loop has stopped — so this reproduces `discovery-engine-v0.5.0` selection exactly.
    """
    if not ranked:
        return ranked
    max_per_feature = max(1, int(config.max_feature_identity_fraction * config.top_k))
    feature_usage: dict[str, int] = {}
    final: list[tuple[Condition, ...]] = []
    for rule in ranked:
        features = {condition.feature for condition in rule}
        if any(feature_usage.get(feature, 0) >= max_per_feature for feature in features):
            continue
        final.append(rule)
        for feature in features:
            feature_usage[feature] = feature_usage.get(feature, 0) + 1
        if len(final) == config.top_k:
            break
    return final


def _reserve_k1_slot(
    final_selected: list[tuple[Condition, ...]],
    singles: list[tuple[Condition, ...]],
    exposures: dict[tuple[Condition, ...], frozenset[int]],
    effective_score: dict[tuple[Condition, ...], float],
    atom_usage: dict[Condition, int],
    max_overlap: dict[tuple[Condition, ...], float],
    config: DiscoveryConfig,
    prepare: Callable[[list[tuple[Condition, ...]]], None],
) -> tuple[list[tuple[Condition, ...]], dict[str, Any]]:
    """Bounded `k==1` top-K reservation (`TASK-095`/`TASK-097`,
    `docs/analytics/task-095-k1-reservation-design.md` §4.3 — the six steps below are numbered to
    match that document's own, round-2-revised numbering exactly).

    Called by `discover_candidates` only when `config.reserve_k1_slot` is `True` and Stage 1/2
    already filled `config.top_k` with zero `k==1` members — the common case
    (`docs/benchmark/task-094-k1-selection-scoping.md`) where interactions alone crowd out every
    single regardless of relative score. Probes exactly one additional slot via the real,
    unmodified `_greedy_diverse_select` and, on a qualifying single, drops `final_selected[-1]`
    (the weakest incumbent by marginal-gain order — `_greedy_diverse_select` builds `selected` in
    strictly non-increasing marginal-gain order and `_apply_feature_identity_cap` preserves that
    order, so no new comparison is needed to find it) in its favor. Exact fallback — returns
    `final_selected` unchanged — when no single qualifies. `top_k` itself never grows: this is a
    bounded reduction in interaction slots, never a `top_k` increase.

    `max_overlap` and `atom_usage` are the same shared accumulators `_greedy_diverse_select`
    mutated during Stage 1/2; both are mutated in place here too (consistent with that existing
    convention), though nothing downstream reads either again once this function returns.
    `prepare` is `discover_candidates`'s own `_prepare` closure, passed in explicitly so this stays
    a plain, directly testable top-level function; it is idempotent (only computes for rules not
    already cached), matching step 1 below.

    Returns the (possibly updated) selected list and a disclosed `"k1_reservation"` metadata dict
    (design §4.1/§4.3): `{"eligible": True, "activated": bool, "promoted_conditions": str | None,
    "displaced_conditions": str | None}`. `"eligible"` is always `True` here — the caller only
    invokes this function once its own trigger condition (`len(final_selected) == config.top_k`
    and every member is `k>=2`) already holds; a caller that does not invoke this function at all
    (`reserve_k1_slot=False`, or the trigger did not hold) reports `"eligible": False` itself.
    """
    metadata: dict[str, Any] = {
        "eligible": True,
        "activated": False,
        "promoted_conditions": None,
        "displaced_conditions": None,
    }
    if not singles:
        return final_selected, metadata  # nothing to promote; identical to today by construction

    # 1. Prepare singles exactly as the existing fallback already would (unchanged helper, same
    #    exposures/temporal-consistency/effective-score computation as Stage 2 already performs
    #    when it runs at all).
    prepare(singles)  # existing helper (discover_candidates's own _prepare), unmodified

    # 2. FIRST CORRECTION -- self-found before round 1 review (design §10.1): seed each single's
    #    max_overlap against every incumbent in final_selected, not just 0.0. _prepare's own
    #    initialization sets max_overlap to 0.0 for any rule seen for the first time -- correct
    #    when a phase starts from an empty selected list (Stage 1's own first call), but wrong
    #    here, because Stage 3 always starts from a *full* top_k of incumbents.
    incumbent_exposures = [exposures[rule] for rule in final_selected]
    for single in singles:
        max_overlap[single] = max(
            (_jaccard(exposures[single], exposure) for exposure in incumbent_exposures),
            default=0.0,
        )

    # 3. SECOND CORRECTION -- found by round 1 independent review, not self-found (design §10.6):
    #    recompute atom_usage relative to final_selected too, the identical discipline step 2 just
    #    applied to max_overlap. The atom_usage dict this function receives is Stage 1/2's own raw
    #    accumulator, which can carry phantom counts for atoms belonging only to candidates
    #    _apply_feature_identity_cap dropped (it trims via its own, separate, local feature_usage
    #    counter and never decrements the shared atom_usage dict for whatever it drops). Recomputed
    #    fresh here instead, counting only conditions actually present in final_selected's own
    #    rules -- exactly what max_candidates_per_atom's own name says it should be measuring. No
    #    branch on identity_cap_active is needed: when the cap is not active, final_selected ==
    #    selected (nothing was ever trimmed), so this recomputation is provably identical, count
    #    for count, to what atom_usage already holds -- a strict generalization, not a special case.
    atom_usage_for_probe: dict[Condition, int] = {}
    for rule in final_selected:
        for condition in rule:
            atom_usage_for_probe[condition] = atom_usage_for_probe.get(condition, 0) + 1

    # 4. Non-destructive probe: copy the mutable state _greedy_diverse_select mutates, run it with
    #    a budget of exactly one more than the current final_selected size. The while loop's own
    #    guard (`len(selected) < config.top_k`) then admits at most one candidate, through the
    #    *exact* same relevance-floor/overlap-discount/hard-jaccard-ceiling/atom-usage-cap logic
    #    interactions already went through in this run -- _greedy_diverse_select itself is called
    #    completely unmodified.
    probe_selected = list(final_selected)
    probe_selected_exposures = list(incumbent_exposures)
    probe_atom_usage = atom_usage_for_probe  # step 3's correction -- NOT dict(atom_usage)
    probe_max_overlap = dict(max_overlap)
    _greedy_diverse_select(
        singles,
        effective_score,
        exposures,
        replace(config, top_k=len(final_selected) + 1),
        probe_selected,
        probe_selected_exposures,
        probe_atom_usage,
        probe_max_overlap,
    )
    if len(probe_selected) == len(final_selected):
        return final_selected, metadata  # no single cleared the floor/overlap/atom-usage bar --
        # exact fallback, requirement 1

    promoted = probe_selected[-1]  # the one single _greedy_diverse_select's own marginal-gain
    # comparison picked

    # 5. Re-validate max_feature_identity_fraction's own invariant for the promoted single alone
    #    (design §5.5 -- only the promoted single's own feature(s) need checking, never a full
    #    re-walk: Stage 3 only ever removes one incumbent, which can only *decrease* every
    #    feature's count, and adds one single, which can only *increase* the count of that single's
    #    own -- exactly one -- feature). Inlined directly, not via a separate helper (design §14
    #    revision 2): the same accumulation pattern _apply_feature_identity_cap itself already uses,
    #    restricted here to final_selected's surviving incumbents.
    if config.max_feature_identity_fraction < 1.0:
        max_per_feature = max(1, int(config.max_feature_identity_fraction * config.top_k))
        usage_without_dropped: dict[str, int] = {}
        for rule in final_selected[:-1]:  # the about-to-be-dropped weakest incumbent excluded --
            for condition in rule:  # its own feature(s) can only ever help this check, never hurt
                usage_without_dropped[condition.feature] = (
                    usage_without_dropped.get(condition.feature, 0) + 1
                )
        if any(
            usage_without_dropped.get(feature, 0) >= max_per_feature
            for feature in {condition.feature for condition in promoted}
        ):
            return final_selected, metadata  # promotion would reopen the cap's own invariant --
            # decline, exact fallback, requirement 1

    # 6. Commit: drop the weakest incumbent (final_selected's own last element), append the
    #    promoted single. The shared atom_usage/max_overlap dicts (not the fresh
    #    atom_usage_for_probe from step 3) are updated too, though nothing in this run reads either
    #    again after this point -- discover_candidates's own remaining code treats `selected` as an
    #    opaque ordered list of rule tuples and never looks at either dict again. Kept consistent
    #    for any future reader, not because this run depends on it.
    dropped = final_selected[-1]
    for condition in dropped:
        atom_usage[condition] -= 1
    for condition in promoted:
        atom_usage[condition] = atom_usage.get(condition, 0) + 1
    metadata["activated"] = True
    metadata["promoted_conditions"] = str(promoted)
    metadata["displaced_conditions"] = str(dropped)
    return [*final_selected[:-1], promoted], metadata


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
                    # Exposure-identical means the leave-one-out parent's exposed *rows* are the
                    # exact same set as the child's, not merely the same count (TASK-071).
                    # `n_exposed` equality used to stand in for that directly. It is not actually
                    # a coincidence-prone proxy here: `rule` is `parent_rule` AND one extra
                    # condition, so `_exposed_rows(rule)` is always a strict subset of
                    # `_exposed_rows(parent_rule)` (conjunction only ever removes rows). A subset
                    # with equal cardinality is the same set, so the old count check was already
                    # exact for this specific parent/child relationship — confirmed empirically
                    # against every depth->1 eligible rule in two full real searches (travel,
                    # b2b_sales; 69,311 child/parent pairs, zero disagreements). This still moves
                    # to the direct, self-evidently-correct row-set comparison rather than relying
                    # on that subset invariant implicitly: it removes a non-obvious correctness
                    # argument from the code's actual behavior and stays correct even if some
                    # future change to this comparison (e.g. comparing to non-immediate ancestors)
                    # broke the subset guarantee.
                    parent_rules = [tuple(c for c in rule if c != removed) for removed in rule]
                    parent_metrics = [
                        _metric(frame, parent_rule, outcome, "development")
                        for parent_rule in parent_rules
                    ]
                    child_exposed_rows = _exposed_rows(development, rule)
                    if any(
                        parent is not None
                        and _exposed_rows(development, parent_rule) == child_exposed_rows
                        for parent_rule, parent in zip(parent_rules, parent_metrics, strict=True)
                    ):
                        continue
                scored[rule] = (_development_score(metric, depth, config), metric)

        beam = _select_expansion_beam(scored, depth, config)
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
    #
    # TASK-068: when the feature-identity cap is active, _greedy_diverse_select is called
    # completely unmodified but with a temporarily larger top_k (its own pre-existing parameter),
    # so _apply_feature_identity_cap has real alternatives to fall back on afterward instead of
    # only being able to shrink the final set. `search_config` never leaves this block — the
    # `search` metadata below reports the caller's real `config`, not this internal widening.
    identity_cap_active = config.max_feature_identity_fraction < 1.0
    search_config = config
    if identity_cap_active:
        overselect_target = min(
            len(interactions) + len(singles), config.top_k * _IDENTITY_CAP_OVERSELECT_MULTIPLIER
        )
        search_config = replace(config, top_k=max(overselect_target, config.top_k))

    _prepare(interactions)
    _greedy_diverse_select(
        interactions,
        effective_score,
        exposures,
        search_config,
        selected,
        selected_exposures,
        atom_usage,
        max_overlap,
    )
    if len(selected) < search_config.top_k:
        _prepare(singles)
        _greedy_diverse_select(
            singles,
            effective_score,
            exposures,
            search_config,
            selected,
            selected_exposures,
            atom_usage,
            max_overlap,
        )
    if identity_cap_active:
        selected = _apply_feature_identity_cap(selected, config)

    # TASK-097 (TASK-095's design, docs/analytics/task-095-k1-reservation-design.md §4.2/§4.3):
    # Stage 3, new, runs only when opted in and only when Stage 1/2's own combined output already
    # reached config.top_k with zero k==1 members -- covers both "interactions did not fill top_k"
    # (Stage 2 already gave singles a fair, unmodified shot) and "Stage 2 already promoted >=1
    # single into the final set" (nothing further to reserve). This trigger check operates on
    # `selected` *after* the identity-cap post-filter above, per the design's own §4.2 ordering
    # requirement (checking the pre-cap, oversold list would ask the wrong question).
    k1_trigger_met = len(selected) == config.top_k and all(len(rule) >= 2 for rule in selected)
    k1_reservation: dict[str, Any] = {
        "eligible": config.reserve_k1_slot and k1_trigger_met,
        "activated": False,
        "promoted_conditions": None,
        "displaced_conditions": None,
    }
    if config.reserve_k1_slot and k1_trigger_met:
        selected, k1_reservation = _reserve_k1_slot(
            selected,
            singles,
            exposures,
            effective_score,
            atom_usage,
            max_overlap,
            config,
            _prepare,
        )
    # Design §4.3's own recommended (non-mandatory) auditability addition: the promoted single, if
    # any, is always selected[-1] (step 6 appends it last) -- identified here, not inside
    # _reserve_k1_slot, so that function stays a pure selection primitive with no Candidate/warnings
    # knowledge, matching _greedy_diverse_select's own separation of concerns.
    k1_promoted_rule = selected[-1] if k1_reservation["activated"] else None

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
        if rule == k1_promoted_rule:
            warnings.append(
                "Promoted via the bounded k==1 reservation quota (TASK-095), displacing a k>=2 "
                "candidate from the final top-K."
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
        "k1_reservation": k1_reservation,
    }
