# TASK-095 — Bounded `k==1` top-K reservation: design document

**Status: DESIGN ONLY. No implementation.** Nothing in this document changes, or proposes changing,
`discovery.engine`, `apply.py`, any `GateId`, any threshold value, `_development_score`, `_atoms`,
`_metric`, `_eligible`, `_select_expansion_beam`, or `validation-contract.md`. Where this document
names a function, field, or control-flow step, it is either describing the *existing* codebase (read,
not modified — every such reference is cited by file and line range below) or specifying what a
later, distinct implementation task would need to build, at the same level of concreteness
`docs/analytics/task-080-candidate-composition-safety-design.md` used for its own later-implementation
specification (§8.1a, §10). `CODE_REVIEWER` reviews this document; no implementation task opens until
that review completes, per `TASK-095`'s own binding instruction, matching `TASK-080`→`081`'s
precedent exactly.

**Illustrative-example discipline, stated once, matching `TASK-080` §0.** Every concrete number below
that comes from `docs/benchmark/task-094-k1-selection-scoping.md` (the `12,081.5` top single score,
the `26`-candidate eligible singleton pool, the `7.7%` qualifying rate, the `150/150`/`15/15`
all-interaction historical finding) is reused exactly as that document already published it, to
illustrate or bound a mechanism property — never as a target this design is shaped around. No pattern
identity, feature name, or travel-specific value appears anywhere in the mechanism itself (§4-§8
below); every threshold this design touches is either reused unchanged from `TASK-060`'s existing,
already-audited defaults, or is a structural property of the selection algorithm (e.g., "swap exactly
one slot") justified generically. This document would read identically with every travel-specific
noun deleted from its illustrative asides.

## 0. What this document answers, mapped to `TASK-095`'s six numbered requirements

| # | Requirement | Where answered |
|---|---|---|
| 1 | Strict floor-conditioned promotion, never guaranteed; exact fallback when nothing qualifies | §4.3 (mechanism), §7 (worked traces), §9 checklist item 1 |
| 2 | Reserved slot(s) from a bounded reduction in interaction slots, never `top_k` increase | §4.2, §4.3 step 3c |
| 3 | Zero change to any gate/threshold/estimator/search/eligibility stage | §9 |
| 4 | Explicit interaction analysis against all five `TASK-060` knobs | §5 |
| 5 | Determinism/permutation analysis and worked traces (common and uncommon case) | §6, §7 |
| 6 | Justify reserved-slot count of 1 before considering more | §8 |

## 1. The structural problem, restated generically (not re-litigated)

`discovery.engine.discover_candidates` (`packages/analytics/src/policy_analytics/discovery/engine.py`,
lines 699-768) ranks every scored rule by `(-development_score, rule)`, partitions the ranked list into
`interactions` (`k>=2`) and `singles` (`k==1`), and fills the `top_k` output slots from `interactions`
via `_greedy_diverse_select` **first**, only calling `_greedy_diverse_select` on `singles` if
`len(selected) < search_config.top_k` after the interactions phase. `docs/benchmark/task-094-k1-
selection-scoping.md` §2 measured directly (not merely quoted from the engine's own comment) that this
fallback condition essentially never fires: with real eligible-pool sizes in the tens of thousands and
`top_k=15`, interactions alone fill every slot in the common case, confirmed against the historical
record `ADR-080` compiled (150/150 candidates `k>=2` across ten recoverable frozen official runs,
zero `k==1`). §1 of that document also established, directly, that this is not because singles are
categorically weaker — the pool's single highest-`development_score` candidate overall, a `k==1` rule,
outranks every one of the pool's `k>=2` candidates, yet is structurally unreachable "regardless of
relative score" (`ADR-080`'s own quoted language, now demonstrated).

This design's job is narrow: give a genuinely high-quality `k==1` candidate a chance to compete for
**one** final-assembly slot, without weakening any of the machinery that already protects the
`k>=2` selection from noise, and without changing what happens when no such candidate exists.

## 2. What is reused without re-derivation

- **`TASK-094`'s own findings** (`docs/benchmark/task-094-k1-selection-scoping.md`,
  `docs/benchmark/task-094-k1-power-ceiling-raw.json`): no systematic power advantage for `k==1`
  in aggregate (7.7% BH-bound clearance vs. 11.2% for `k>=2`), but a real, decisively-clearing
  minority exists; no new safety gap (`G16` vacuous for `k==1` by construction, `G06` applies
  identically regardless of `k`); the quota approach is the lower-cost mechanism relative to a
  merged-pool/reordering redesign, because `TASK-060`'s four score-comparison knobs are phase-relative
  by design (`ADR-040`) and a quota can reuse them unchanged where a merged pool cannot. This design
  does not reopen any of that — it takes the "pursue, quota-shaped" recommendation as its starting
  point and produces the quota's actual mechanism.
- **`TASK-060`'s full tuning history** (`ADR-035`/`037`/`038`/`039`/`040`, and the engine's own
  per-field docstrings, `engine.py` lines 128-223): `diversity_discount_weight` (overlap discount,
  default `0.5`), `min_diversity_relevance_ratio` (relevance floor ratio, default `0.5`),
  `relevance_floor_percentile` (what the ratio is a fraction of — the phase pool's own 75th
  percentile, default `0.75`, `ADR-040`), `stability_credit_weight` (cross-split stability credit,
  default `0.5`, empirically null per `ADR-039` but retained), `max_feature_identity_fraction`
  (per-feature cap, default `1.0`/no-op, `ADR-057`). Its concrete failure-mode precedent
  (`TASKS.md` `TASK-060` entry, `ADR-036`): at full discount strength, a statistically thin,
  merely-disjoint rule (`CAND-012`) won a selection round "purely by being untouched by anything
  else," reaching `PASS`/`shadow_policy` on a confounding trap (`T03`) the fixed `G06` adjustment set
  did not catch — Top-10 precision fell 90%→40% on that iteration before `min_diversity_relevance_
  ratio` was added (`ADR-037`) to close exactly this failure mode generically. §5 and §10 below take
  this precedent seriously: any new path that lets a candidate reach the final set with a
  weakly-computed overlap discount reproduces this exact risk in a new corner, and §4.3/§10 are
  built specifically to not do that.
- **`ADR-080`**: `G16`'s unconditional `k>=2` cap is accepted product semantics, not reopened;
  today's 150/150/15/15 all-interaction historical record is exactly the situation this design
  responds to, not a claim this design revisits.

## 3. Solution space — confirming the quota approach remains right, not reasserting it

`TASK-094` §2 already named and cost-compared three shapes: (1) a bounded quota reusing
`_greedy_diverse_select`'s existing per-phase machinery; (2) a unified, score-ranked pool across
`k==1`/`k>=2`; (3) dropping the interactions-first ranking rule and sorting purely by score. It found
(2)/(3) materially more expensive because every one of `TASK-060`'s four score-comparison knobs is
computed **per phase**, over that phase's own pool — merging phases would require deciding, as a new
design question with no existing precedent to reuse, whether singles and compounds should share one
relevance floor or keep two, and would reopen `min_diversity_relevance_ratio`'s reference-point
question `ADR-040` already spent one full iteration resolving for the phase-relative case alone.

This design worked the quota mechanism through to full concreteness (§4-§8 below) and found no point
at which it became insufficient — no place where a merged pool would have been required to preserve
correctness or safety. The one real gap this design's own construction surfaced (§4.3's overlap-
seeding correction, §10.1) is a **local, bounded fix inside the quota's own probe step**, not evidence
that the quota shape itself is inadequate. Per `TASK-095`'s own instruction, the merged-pool
alternative is therefore not revisited here — the quota approach is confirmed sufficient by
construction, not merely carried forward by assumption.

## 4. Recommended design

### 4.1 New config surface (proposed, for a later implementation task)

```python
#: Whether final assembly reserves at most one top-K slot for the single best-qualifying k==1
#: candidate, when interactions alone would otherwise fill every slot (TASK-095). `False` (default)
#: is a byte-identical no-op: discover_candidates's control flow, output, and DISCOVERY_METHOD_VERSION
#: are all unchanged from discovery-engine-v0.6.1 when this field is False. Must be explicitly enabled
#: to take effect — matching this project's own convention for every prior TASK-060 addition
#: (diversity_discount_weight, min_diversity_relevance_ratio, stability_credit_weight,
#: relevance_floor_percentile, max_feature_identity_fraction all shipped with a no-op default that
#: reproduces the prior version exactly). Not a count: the reserved-slot count is fixed at 1 by this
#: design (see task-095-k1-reservation-design.md §8) and is deliberately not exposed as a tunable
#: integer — a larger count needs its own separate, checked justification, not a config value someone
#: can raise without one.
reserve_k1_slot: bool = False
```

`__post_init__` needs no new validation branch (a `bool` field has no range to check, matching
`identity_cap_active`'s own pattern at line 736).

This field is not required by `TASK-095`'s six numbered requirements verbatim, but it is the
generically-motivated, house-style way to satisfy requirement 1's "byte-identical to today" guarantee
**structurally** (any caller that does not opt in gets literally the same code path as today, not just
a code path that happens to produce the same output when nothing qualifies) and it gives a later
implementation task an explicit, reviewable on/off switch for staged rollout, matching `TASK-060`'s own
five-iteration rollout discipline. `asdict(config)` already includes it for free in the returned
`"search"` metadata (line 799), so every run's provenance record shows whether the mechanism was even
eligible to activate, at no additional bookkeeping cost.

### 4.2 Control-flow overview

Three stages, replacing nothing that exists today — stages 1 and 2 are **the current code,
unmodified**; stage 3 is new and runs only after them, only when `reserve_k1_slot` is `True`, and only
when stages 1-2's own combined output already reached `config.top_k` with zero `k==1` members.

```
Stage 1 (existing, engine.py:744-754, byte-identical):
    _prepare(interactions)
    _greedy_diverse_select(interactions, ..., config=search_config, selected=[], ...)
    -> selected now holds up to search_config.top_k interactions, in descending-marginal-gain order

Stage 2 (existing, engine.py:755-766, byte-identical — the current, already-existing k==1 fallback):
    if len(selected) < search_config.top_k:
        _prepare(singles)
        _greedy_diverse_select(singles, ..., config=search_config, selected, ...)  # continues filling

    if identity_cap_active:                       # existing, engine.py:767-768, byte-identical
        selected = _apply_feature_identity_cap(selected, config)
    final_selected = selected                      # real, config.top_k-sized (or smaller) result,
                                                     # exactly what discover_candidates returns today

Stage 3 (NEW, only if config.reserve_k1_slot):
    if len(final_selected) == config.top_k and all(len(rule) >= 2 for rule in final_selected):
        final_selected = _reserve_k1_slot(final_selected, singles, exposures, effective_score,
                                           atom_usage, config)
    # else: no-op. Covers both "interactions did not fill top_k" (Stage 2 already gave singles a
    # fair, unmodified shot) and "Stage 2 already promoted >=1 single into the final set" (nothing
    # further to reserve — see §5's max_feature_identity_fraction / §7's worked trace for why this
    # composes correctly with an active identity cap).
```

The trigger condition operates on `final_selected` — **after** any active `_apply_feature_identity_cap`
post-filter, not on the raw, possibly-oversold `selected` from Stage 1 (`search_config.top_k` is
inflated up to `_IDENTITY_CAP_OVERSELECT_MULTIPLIER * config.top_k`, line 739-742, when the identity
cap is active, so checking against `search_config.top_k` at that point would almost never be true and
would be measuring the wrong quantity). This ordering choice is deliberate and is examined for its own
correctness in §5's `max_feature_identity_fraction` analysis.

### 4.3 Stage 3 mechanism, in full

```python
def _reserve_k1_slot(
    final_selected: list[tuple[Condition, ...]],
    singles: list[tuple[Condition, ...]],
    exposures: dict[tuple[Condition, ...], frozenset[int]],
    effective_score: dict[tuple[Condition, ...], float],
    atom_usage: dict[Condition, int],
    config: DiscoveryConfig,
) -> list[tuple[Condition, ...]]:
    if not singles:
        return final_selected  # nothing to promote; identical to today by construction

    # 1. Prepare singles exactly as the existing fallback already would (unchanged helper, same
    #    exposures/temporal-consistency/effective-score computation as Stage 2 already performs
    #    when it runs at all).
    _prepare(singles)  # existing helper, engine.py:712-726, unmodified

    # 2. THE CORRECTION (see §10.1): seed each single's max_overlap against every incumbent in
    #    final_selected, not just 0.0. _prepare's own initialization (line 721) sets max_overlap to
    #    0.0 for any rule seen for the first time -- correct when a phase starts from an empty
    #    selected list (Stage 1's own first call), but wrong here, because Stage 3 always starts from
    #    a *full* top_k of incumbents. This step is new final-assembly-stage code; it calls no
    #    primitive that does not already exist (_jaccard, exposures) and it changes no value
    #    _greedy_diverse_select's own internals compute -- it only supplies the input the function's
    #    own docstring already says the discount should be measured against ("current maximum
    #    development-split exposure overlap ... with everything already selected").
    incumbent_exposures = [exposures[rule] for rule in final_selected]
    for single in singles:
        max_overlap[single] = max(
            (_jaccard(exposures[single], exposure) for exposure in incumbent_exposures),
            default=0.0,
        )

    # 3. Non-destructive probe: copy the mutable state _greedy_diverse_select mutates, run it with a
    #    budget of exactly one more than the current final_selected size. The while loop's own guard
    #    (`len(selected) < config.top_k`) then admits at most one candidate, through the *exact*
    #    same relevance-floor/overlap-discount/hard-jaccard-ceiling/atom-usage-cap logic interactions
    #    already went through in this run -- _greedy_diverse_select itself is called completely
    #    unmodified.
    probe_selected = list(final_selected)
    probe_selected_exposures = list(incumbent_exposures)
    probe_atom_usage = dict(atom_usage)
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
        return final_selected  # no single cleared the floor/overlap/atom-usage bar -- exact
                                # fallback, requirement 1

    promoted = probe_selected[-1]  # the one single _greedy_diverse_select's own marginal-gain
                                    # comparison picked

    # 4. Re-validate max_feature_identity_fraction's own invariant for the promoted single alone
    #    (see §5's dedicated analysis for why only the promoted single's own feature(s) need
    #    checking, never a full re-walk).
    if config.max_feature_identity_fraction < 1.0:
        max_per_feature = max(1, int(config.max_feature_identity_fraction * config.top_k))
        usage_without_dropped = _feature_usage(final_selected[:-1])  # counts with the
                                                                      # about-to-be-dropped
                                                                      # incumbent excluded
        if any(
            usage_without_dropped.get(feature, 0) >= max_per_feature
            for feature in {condition.feature for condition in promoted}
        ):
            return final_selected  # promotion would reopen the cap's own invariant -- decline,
                                    # exact fallback, requirement 1

    # 5. Commit: drop the weakest incumbent (final_selected's own last element -- see §4.4 for why),
    #    append the promoted single. Bookkeeping kept consistent for any future reader of
    #    atom_usage/max_overlap, though nothing downstream reads them again this run.
    dropped = final_selected[-1]
    for condition in dropped:
        atom_usage[condition] -= 1
    for condition in promoted:
        atom_usage[condition] = atom_usage.get(condition, 0) + 1
    return [*final_selected[:-1], promoted]
```

`_reserve_k1_slot` is called once, after Stage 2's identity-cap post-filter, immediately before
`discover_candidates`'s existing `candidates: list[Candidate] = []` construction loop (line 769) —
that loop, and everything in it (`candidate_id` numbering, `rank_score`, `warnings`, `actionability`),
is completely unmodified: it already treats `selected` as an opaque, ordered list of rule tuples and
does not care whether a given tuple has length 1 or ≥2.

**Recommended, non-mandatory auditability addition.** Append one disclosure string to the promoted
candidate's own `warnings` tuple (the same list that already carries "Harm direction is not stable...”
and "Actionability requires business review..." — line 776-782), e.g. `"Promoted via the bounded k==1
reservation quota (TASK-095), displacing a k>=2 candidate from the final top-K."`, and record a small,
purely-informational block in `discover_candidates`'s returned dict (sibling to `"search"`/`"outcome"`,
not inside either): `"k1_reservation": {"eligible": <bool, reserve_k1_slot and the trigger condition
held>, "activated": <bool>, "promoted_conditions": <str(promoted) or None>, "displaced_conditions":
<str(dropped) or None>}`. This is metadata only — no gate, no threshold, no evidence-level effect — and
gives a later implementation's test suite (§11) a cheap, direct assertion surface for the worked traces
in §7, matching this project's own preference for named, disclosed mechanism state (`ADR-080`'s own
`G16` reason-code discipline; `ADR-040`'s own "reference point" naming) over an undisclosed side effect.

### 4.4 Which incumbent to drop — alternatives considered

Three candidate rules were considered for "which of the `top_k` incumbent interactions makes room":

1. **Drop `final_selected[-1]` (adopted).** By construction, `_greedy_diverse_select`'s `selected`
   list is built in strictly non-increasing marginal-gain order (each round picks the single best
   remaining `marginal`, appends it, never reorders earlier picks) and `_apply_feature_identity_cap`
   preserves input order when it filters (line 615-623, an order-preserving subsequence). So
   `final_selected[-1]` is, without any new computation, the weakest-by-the-existing-process incumbent
   — no new comparison, no new tie-break rule, no new number.
2. **Drop the incumbent the promoted single overlaps most with.** Rejected: motivated by an intuition
   ("redundant with what's being added should go first"), not by any measurement `TASK-094`'s own
   diagnostic made (it never measured overlap between the top single and the top interactions) — would
   introduce a new comparison this design has no evidence-based way to calibrate, violating the same
   anti-overfitting discipline `TASK-080` §3 point 3 already applied to a differently-shaped proposal.
3. **Re-run the full `top_k`-slot greedy selection over the combined `interactions ∪ {promoted
   single}` pool.** Rejected: this is the merged-pool alternative §3 already declined, reintroduced at
   a smaller scale — it would let the promotion reorder or exclude incumbents having nothing to do with
   the promoted single, expanding blast radius for no evidenced benefit, and it re-triggers the
   phase-relative-floor question §3 named as the reason a merged pool costs more.

Option 1's cost, stated plainly: it is **not** globally optimal — it does not ask whether some other
incumbent's removal would let a *stronger* single in, or whether removing the single-most-overlapping
incumbent would improve the resulting set's own diversity more than removing the weakest one. This is a
deliberate trade-off for minimal, auditable blast radius (exactly one incumbent removed, one single
added, nothing else in the final list reordered or reconsidered) over marginal set-level optimality —
named explicitly here rather than left implicit, per this document's own self-critique obligation
(§10.3).

## 5. Interaction with each of `TASK-060`'s five selection knobs

### 5.1 `diversity_discount_weight` (default `0.5`)

**Reused unchanged as a formula and as a value.** The discount formula
(`marginal = effective_score[rule] * (1 - diversity_discount_weight * max_overlap[rule])`) executes
inside the Stage 3 probe exactly as it executes inside Stage 1/2 — `_greedy_diverse_select` is called
completely unmodified (§4.3 step 3). What changes is **not** the knob, but a correction to one of its
*inputs*: `max_overlap[single]`, seeded by the new §4.3 step 2 against the full incumbent set rather
than left at `_prepare`'s own `0.0` default. This is necessary precisely because of `ADR-036`'s
precedent (§2 above): the discount's entire safety property is that a weak, low-overlap candidate
cannot win "purely by being untouched" — a Stage 3 probe that left `max_overlap[single] = 0.0`
unconditionally (i.e., reused the existing Stage 2 fallback's own calling convention verbatim, without
this correction) would let *any* single with genuinely zero overlap against `interactions` sail through
regardless of how much it overlaps the `top_k - 1` incumbents that remain **after** the swap — the
exact failure shape `ADR-036`/`ADR-037` generically fixed for the interactions phase, reopened in a new
corner. §10.1 treats this as this design's own most important corrected defect.

### 5.2 `min_diversity_relevance_ratio` (default `0.5`) and `relevance_floor_percentile` (default `0.75`)

**Both reused entirely unchanged, computed exactly as today, from the singles pool's own score
distribution.** `_greedy_diverse_select`'s first two lines (`reference_score = _percentile([...for
rule in pool], relevance_floor_percentile)`, `score_floor = min_diversity_relevance_ratio *
reference_score`) execute inside the Stage 3 probe with `pool=singles` — the full singles pool, not a
combined interactions+singles pool. This is a deliberate design choice, not an oversight: comparing a
single's score against the *interactions'* score distribution (or a merged distribution) would be
exactly the merged-pool redesign §3 declined — it would silently change what the floor *means* for
every future singles-phase invocation, including Stage 2's pre-existing, untouched fallback. Keeping
the floor phase-relative means a genuinely strong single is judged against how strong *other singles*
in this run's pool are, matching the pool's own existing "in the phase's own upper quartile" semantics
(`ADR-040`) with zero new interpretation required.

### 5.3 `stability_credit_weight` (default `0.5`, empirically null per `ADR-039`)

**Reused entirely unchanged.** `_prepare(singles)` already computes `effective_score[single]` via
`_apply_stability_credit` (line 724-726) exactly as it does for interactions — this is existing code,
called by Stage 3's own step 1 with no modification. The only consequence of this design is that
`_prepare(singles)` now runs far more often (every eligible Stage-3-triggering run, not only the rare
Stage-2-triggering one) — a change in how *often* this existing computation executes, not in what it
computes. Because it was already found empirically null on the one run it was tested against
(`task-060-iteration-20260820-003`), no differential effect on singles is predicted or claimed here;
this is disclosed as a cost-frequency change only (§10.2), not a semantics change.

### 5.4 `max_candidate_jaccard` / `max_candidates_per_atom` (hard ceilings, not named in the required
five but load-bearing for the probe)

Not part of the required five, included for completeness since the mechanism depends on them.
**Reused entirely unchanged** — both are read directly inside `_greedy_diverse_select`'s own loop
(lines 546, 548-551), which Stage 3's probe calls unmodified. The `max_candidate_jaccard` ceiling now
has real, correctly-seeded `max_overlap[single]` values to check against (§5.1's correction), so a
single that duplicates an incumbent interaction's exposed population above the ceiling is skipped
outright by existing code, exactly as an interaction would be skipped against another interaction today.

### 5.5 `max_feature_identity_fraction` (default `1.0`, no-op)

**Reused-but-now-also-applied to the reserved candidate, via a new, narrow, targeted re-check — not a
change to the knob's own value, threshold, or the existing `_apply_feature_identity_cap` function
(which is not called a second time and not modified).** The reasoning has two parts:

1. **Why Stage 3 must run after `_apply_feature_identity_cap`, not before or in place of it.** When
   `identity_cap_active`, Stage 1 oversells (`search_config.top_k` inflated up to
   `_IDENTITY_CAP_OVERSELECT_MULTIPLIER * config.top_k`, line 738-742) specifically so
   `_apply_feature_identity_cap` has real alternatives to trim from. Checking Stage 3's own trigger
   condition (`len(...) == config.top_k`) against that inflated, pre-cap list would almost always be
   false (the oversold list is typically much larger than `config.top_k`) and would be asking the
   wrong question — "did interactions fill the oversampling budget," not "did interactions fill the
   real, reported top-K." Only `final_selected` (post-cap) answers the question this design actually
   needs answered.
2. **Why only the promoted single's own feature(s) need re-checking, not a full re-walk of
   `_apply_feature_identity_cap`.** Stage 3 only ever removes one incumbent (which can only *decrease*
   every feature's count, since removing a rule's conditions from the tally never increases any
   count) and adds one single (which can only *increase* the count of that single's own — exactly
   one, since `k==1` — feature). The per-feature cap (`engine.py` line 617:
   `feature_usage.get(feature, 0) >= max_per_feature`) can therefore only be newly violated for that
   one feature, by that one addition; every other feature's count only ever went down or stayed the
   same. A full re-walk would recompute a value that cannot have changed for any feature other than
   the promoted single's own — the targeted check in §4.3 step 4 is exact, not an approximation of a
   full re-walk, and costs `O(1)` instead of `O(top_k)`.

`max_feature_identity_fraction = 1.0` (default, `max_per_feature = config.top_k`) makes step 4 a
structural no-op for the same reason the field's own docstring already gives (line 606-608): no single
feature's count can reach `top_k` while `final_selected` itself holds only `top_k` entries. This
reproduces the "1.0 is a no-op" invariant `TASK-068`/`ADR-057` already established, extended correctly
to Stage 3's new call site rather than merely assumed to still hold there.

## 6. Determinism and permutation analysis

Every quantity Stage 3 touches is a pure function of the frozen candidate pool, the frame, and
`config` — no random sampling, no bootstrap, no wall-clock or hash-order dependence:

- `_percentile`/`_jaccard`/`_apply_stability_credit` (reused, §5) are already pure, closed-form
  functions over lists/frozensets — confirmed by reading their bodies (lines 405-467), not assumed.
- The new overlap-seeding step (§4.3 step 2) is a `max()` over a generator of `_jaccard` values against
  `incumbent_exposures`, a **list** (order-preserving, built from `final_selected`, itself
  order-preserving through every existing stage) — `max()` of a set of floats does not depend on
  traversal order for which *value* it returns, only (in principle) on tie-breaking among
  equal-maximum elements, and no tie-break is needed here because only the numeric maximum is used,
  never which incumbent produced it.
- `_greedy_diverse_select`'s own tie-break (`rule < best_rule`, line 557) is lexicographic comparison
  over `Condition` tuples; `Condition` is a frozen, `order=True` dataclass (line 87), so this is a
  total, deterministic order independent of dict/set iteration order or Python's per-process string
  hash randomization (`Condition.__lt__` compares field values directly, not hashes). The probe reuses
  this unmodified comparison.
- `probe_atom_usage`/`probe_max_overlap` are plain `dict.copy()`s consulted only by key lookup
  (`.get(condition, 0)`, `max_overlap[rule]`) inside the reused loop, never iterated in an
  order-sensitive way — hash-seed randomization affects dict *iteration* order, not key-lookup
  correctness, and nothing in `_greedy_diverse_select` or `_reserve_k1_slot` iterates these dicts
  directly (only the `remaining`/`singles`/`final_selected` **lists**, whose order is itself
  deterministic, are ever iterated).
- §4.3 step 4's `_feature_usage` re-check and step 5's drop/append are direct index/slice operations
  (`final_selected[-1]`, `final_selected[:-1]`) on an already-order-deterministic list.

**Conclusion: for a fixed `frame`, `feature_columns`, `outcome`, and `config` (including
`reserve_k1_slot`), Stage 3's outcome — whether it activates, which single (if any) it promotes, and
which incumbent (if any) it drops — is a deterministic function with no random component.** Running the
same inputs twice produces byte-identical `final_selected`, matching every other stage of
`discover_candidates` (`DiscoveryConfig.seed` exists for the frame/split construction upstream of this
module, not for anything `discover_candidates` itself does — confirmed no call in this module touches
Python's `random` module or a seeded RNG at all).

## 7. Worked traces

### 7.1 Common case — interactions alone already fill `top_k` (the historical norm, 150/150 and 15/15)

Using `docs/benchmark/task-094-k1-power-ceiling-raw.json`'s own real measurement as one concrete
instance of this *general* case (not as a target the mechanism is fitted to, per `TASK-095`'s hard
rule): `top_k=15`, `22,536` eligible interactions, `26` eligible singles.

1. Stage 1 (unchanged): `_greedy_diverse_select(interactions, ..., top_k=15, [])` fills all 15 slots
   from interactions, in descending marginal-gain order. `final_selected` (Stage 2's fallback does not
   fire — `len(selected) == 15 == search_config.top_k`) = these 15 interactions.
2. Stage 3 trigger: `len(final_selected) == 15 == config.top_k` and every member is `k>=2` — fires.
3. `_prepare(singles)` computes `exposures`/`effective_score` for the 26 eligible singles (a small,
   bounded, already-eligible pool — not a re-run of the 33,085-hypothesis search).
4. `max_overlap[single]` seeded against all 15 incumbents' exposures (§4.3 step 2).
5. Probe: `reference_score`/`score_floor` computed from the 26 singles' own `effective_score`
   distribution (§5.2); `remaining` = singles clearing that floor. The probe's greedy loop (budget
   `16`) considers each remaining single's `discount = diversity_discount_weight * max_overlap[single]`
   (now correctly seeded) and picks the single best marginal-gain candidate, if any clears
   `max_candidate_jaccard` and the atom-usage cap.
   - **If the pool's top-scoring single** (illustrative only — `development_score=12,081.5`,
     `harm_per_booking=€325.81`, `n_exposed=1,375`, per `task-094-k1-power-ceiling-raw.json`) clears
     its own phase's relevance floor and is not near-duplicate-overlapping any of the 15 incumbents:
     `probe_selected` grows to 16. §4.3 step 4's identity-fraction re-check passes (default `1.0`, a
     no-op per §5.5). Commit: `final_selected[-1]` (the weakest of the 15 interactions by marginal-gain
     order) is dropped; the single is appended. Result: **14 interactions + 1 single = 15 total.**
   - **If it does not clear** (e.g., below its own phase's floor, or overlapping an incumbent above
     `max_candidate_jaccard`): `probe_selected` stays at 15 — no promotion. Result: **the original 15
     interactions, byte-identical to Stage 1's own output and to today's `reserve_k1_slot=False`
     behavior.**

This is the case §1 identifies as the actual point of this design — the one where, without Stage 3, a
candidate that outscores every interaction in the pool is nonetheless structurally unreachable.

### 7.2 Uncommon case — interactions do not fill `top_k`

Illustrative construction (not a real run): `top_k=15`, only 10 eligible interactions exist.

1. Stage 1: fills 10 slots (all eligible interactions selected, `remaining` exhausted, loop condition
   `len(selected) < top_k` still true but `remaining` empty — line 542, unchanged).
2. Stage 2 (existing, **unmodified by this design**): `len(selected) == 10 < 15`, so the existing
   fallback fires exactly as it does today, filling up to 5 more slots from `singles` via
   `_greedy_diverse_select` called with `search_config` (its own `max_overlap` seeded at `0.0` by
   `_prepare`, per the pre-existing calling convention — this design does not change Stage 2's own
   overlap-seeding behavior; see §10.1's explicit disclosure of this asymmetry). Suppose 3 singles
   clear: `final_selected` now has 13 members (10 interactions + 3 singles).
3. Stage 3 trigger: `len(final_selected) == 13 != config.top_k (15)` — **does not fire.** No further
   mechanism runs; `final_selected` is exactly what Stage 2's own pre-existing fallback already
   produced.

This shows precisely why Stage 3's trigger is an exact `==` on `config.top_k`, not `>=`: the uncommon
case already has no crowding-out problem for Stage 3 to solve — Stage 2's own long-standing fallback
already gave every single an uncapped shot at the slots interactions left open.

### 7.3 Composition edge case — Stage 2 already promoted a single into a `top_k`-sized final set

Illustrative: interactions fill only 14 of 15 slots pre-cap, Stage 2 promotes exactly 1 single to reach
15, and (if `identity_cap_active`) that single survives `_apply_feature_identity_cap`. Stage 3 trigger:
`len(final_selected) == 15 == config.top_k` (true) **and** `all(len(rule) >= 2 for rule in
final_selected)` (false — one member has `len == 1`) — **does not fire.** No double promotion; the
`reserve_k1_slot` bound of "up to 1" (§8) is respected by construction, not by a separate counter.

## 8. Why the reserved-slot count is 1, not more

Per `TASK-095`'s own instruction, this starts from a hard cap of 1 and only considers more if
explicitly justified — the justification below is for staying at 1, not for exceeding it.

1. **The evidence this design responds to only supports a first slot.** `TASK-094` §1 established that
   the pool's single *highest*-scoring candidate overall, across both `k==1` and `k>=2`, is a `k==1`
   rule — a direct, measured reason to let the *top* contender compete regardless of its arity. It did
   not measure, and this design does not assert, anything about the pool's *second*-highest-scoring
   candidate's arity — there is no equivalent finding that the second-best candidate overall is
   disproportionately likely to also be a structurally-blocked single. Reserving a second slot would
   need its own version of `TASK-094`'s own check (does a real singles candidate clear the bar *after*
   the first one is already accounted for), which this design does not perform and is out of its
   scope.
2. **The measured qualifying rate does not support reserving capacity for a second candidate.**
   `TASK-094`'s own diagnostic found 7.7% (2 of 26) of the real eligible singleton pool clears even the
   most lenient multiplicity bound (`docs/benchmark/task-094-k1-selection-scoping.md` §1) — i.e., in
   the concrete pool this design's own worked trace (§7.1) uses illustratively, at most ~2 real
   candidates would even be expected to pass a bar this strict, and `_greedy_diverse_select`'s own
   floor (§5.2, phase-relative, not identical to `G05`'s multiplicity bound) is a *different*,
   generally less strict test — meaning even this 7.7% figure is not a direct estimate of how many
   clear *this* mechanism's own floor. There is no generic (non-travel-fitted) basis in the evidence
   this design is allowed to use for assuming a second slot would regularly find a second genuinely
   qualifying candidate rather than a materially weaker one.
3. **Cost is monotune in slot count, benefit is not shown to be.** Each additional reserved slot is
   one more interaction removed from the reported set (§4.2's own bound: reduction in interaction
   slots, never a `top_k` increase) — a second reserved slot doubles the number of incumbent
   interactions displaced for a class of candidate whose *aggregate* clearance rate is not higher than
   compounds' (§1, restated from `TASK-094`: 7.7% vs. 11.2%). Without evidence the second-best
   candidate specifically benefits from this treatment the way the single best one does, a second slot
   trades a known, bounded cost (one fewer interaction) for an unmeasured, not-evidently-positive
   benefit — exactly the asymmetry `TASK-095`'s own instruction flags as requiring its own explicit,
   checked argument, which this design does not have grounds to make.
4. **Structural simplicity.** A fixed count of 1 needs no new tie-break machinery among multiple
   candidate singles beyond `_greedy_diverse_select`'s own existing one (§4.3 step 3 already resolves
   "which single" via the reused marginal-gain comparison), no new question about whether 2 reserved
   singles should be diversity-selected against *each other* (a phase-within-a-phase question `TASK-
   060`'s own history never had to answer), and no new interaction with `max_feature_identity_fraction`
   beyond the single-feature, `O(1)` re-check §5.5 already specifies (2 promotions could plausibly
   share a feature, reopening exactly the crowding concern `ADR-057` built that cap to prevent, in a
   configuration this design has not analyzed).

**Determination: 1.** Any future task proposing more must redo this section's four checks with its own
evidence, not extend this design's config surface (§4.1) by simply raising a number — which is exactly
why §4.1 proposes a `bool`, not an `int`.

## 9. Scope compliance checklist

| Item | Touched? | Why |
|---|---|---|
| `G03`/`G05`/`G06`/`G16`/any `GateId`/`GateSpec` | No | Stage 3 runs entirely inside `discover_candidates`, which returns before any `apply.py` code runs. No gate module is imported, read, or referenced by §4's mechanism. |
| `_development_score` | No | Reused as already computed by Stage 1/2 (`scored[rule][0]`, `effective_score`); not recomputed or reweighted. |
| `_atoms`/`_metric`/`_eligible` | No | These run once, upstream, before `ranked_rules`/`interactions`/`singles` are ever formed (lines 645-702); Stage 3 never calls them. |
| `_select_expansion_beam` / beam search | No | Search/expansion completes before scoring; Stage 3 operates only on already-scored, already-partitioned candidate tuples. |
| `_greedy_diverse_select` (function body) | No | Called unmodified in §4.3 step 3; its own internals (lines 470-572) are not edited by this design. |
| `_apply_feature_identity_cap` (function body) | No | Called unmodified in Stage 2 (existing); §4.3 step 4 is a new, separate, narrow check, not an edit to this function. |
| `top_k`'s own semantics (report size) | No | `len(final_selected)` before and after Stage 3 is identical (`config.top_k`, or fewer in the uncommon case) — swap, never grow. |
| Any threshold value (`min_diversity_relevance_ratio`, `relevance_floor_percentile`, `diversity_discount_weight`, `stability_credit_weight`, `max_feature_identity_fraction`, `max_candidate_jaccard`, `max_candidates_per_atom`) | No | Every default and every comparison is reused verbatim (§5). |
| `Candidate` construction / `candidate_id` / `rank_score` / `actionability` | No | Unmodified; operates on `selected` as an opaque ordered list, oblivious to Stage 3. |
| New code surface | `discover_candidates` (new `reserve_k1_slot` field read, new call to `_reserve_k1_slot` after line 768) and one new private function `_reserve_k1_slot` | Both are final-assembly-stage code, per `TASK-095`'s own scope. |

## 10. Self-critique — what a reviewer would look for first

### 10.1 The defect this design's own construction found in itself

A naive version of this design — "just call the existing Stage 2 fallback's own code path with a
budget of 1" — would have reused `_prepare`'s `max_overlap[single] = 0.0` seeding verbatim, exactly as
Stage 2 already does. That would have been a **real, live defect**: Stage 2's own fallback only ever
runs today when interactions structurally fail to fill `top_k` (0 of 150 historical occasions), so its
`max_overlap=0.0` seeding gap has never been exercised in practice. Stage 3, by design, runs in the
*opposite*, common case — precisely when there are always `top_k` real incumbents whose overlap should
count. Reusing the naive calling convention would have reproduced `ADR-036`'s own named failure mode
(a candidate admitted "purely by being untouched by anything else") in a new, now-frequently-exercised
corner, the first time this design's own construction was checked against `TASK-060`'s history rather
than against the Stage 2 code alone. §4.3 step 2 / §5.1 fix this by seeding `max_overlap[single]`
against every incumbent before the probe runs — this is disclosed here as the single most important
correction this design made to itself, not left for a reviewer to find first.

### 10.2 Cost, disclosed

Enabling `reserve_k1_slot` means `_prepare(singles)` (which computes `_exposed_rows` and
`_temporal_consistency` — a frame filter plus two later-split metric computations per candidate) now
runs on every eligible common-case invocation, where today it is skipped entirely (line 713-714's own
comment: "singles are never touched at all when interactions alone already fill the top-K"). This cost
is bounded by the eligible singles pool's own size (26 in the one real measurement this design cites
illustratively — small relative to the tens-of-thousands-scale search this pool was already filtered
down from), not by the full evaluated-hypothesis count; it is a real, non-zero, but narrowly-bounded
addition, not a search-scale cost. Stated plainly rather than left implicit, matching `TASK-080`
§8.2's own cost-disclosure style for a structurally similar "only touches a small, already-filtered
set" argument.

### 10.3 Non-optimality, disclosed

§4.4 already discloses that dropping `final_selected[-1]` is not a globally-optimal choice of which
incumbent to remove. Restated here as a scope decision, not an oversight: this design optimizes for
minimal, auditable blast radius over marginal set-level optimality, and does not claim the resulting
`top_k` set is the best possible `top_k - 1`-interactions-plus-1-single combination available in the
pool — only that it is a deterministic, floor-respecting, bounded improvement over never considering
any single at all.

### 10.4 The asymmetry between Stage 2 and Stage 3, disclosed rather than quietly left standing

This design deliberately does not extend §4.3's overlap-seeding correction to Stage 2's own,
pre-existing fallback path (§7.2's worked trace runs it unmodified). This is a **conscious scope
boundary**, not an inconsistency overlooked: Stage 2 is existing, unmodified code that `TASK-095`'s own
requirement 3 places out of bounds beyond what this design's new Stage 3 needs; fixing Stage 2's latent
gap would be a behavior change to a path this task was not chartered to touch, needing its own
separate justification and its own regression check against the (currently zero) historical runs that
have ever exercised it. A reviewer may reasonably ask whether this asymmetry should instead be closed
by applying §4.3's fix inside `_greedy_diverse_select` itself (so both call sites benefit
automatically) — that would touch the function's own internals, which `TASK-095`'s scope places outside
this task (§9). This is named as an explicit, deliberate line, not a gap this document is unaware of.

### 10.5 What this design does not solve

Consistent with `TASK-080` §12's own discipline of disclosing unsolved edges rather than implying
completeness: this design does not change the fact that `_greedy_diverse_select`'s own relevance floor
(§5.2) can still exclude a genuine, weakly-powered single exactly as it already can for interactions
(`ADR-038`'s own already-disclosed cost, unchanged here); it does not give singles any different or
additional protection against confounding beyond what `G06` already provides identically to `k>=2`
candidates (`TASK-094` §3, not reopened); and it does not attempt to determine, for any specific
promoted candidate, whether promotion was "worth it" in recall or precision terms — per `TASK-095`'s
own explicit exclusion, this document makes no claim about expected outcome movement on any benchmark.

## 11. Test specification for a later implementation task (not performed here)

1. **`reserve_k1_slot=False` regression.** `discover_candidates`'s output (including
   `DISCOVERY_METHOD_VERSION`, if bumped) is byte-identical to the pre-`TASK-095` version, for every
   existing regression fixture `TASK-060`/`TASK-068`/`TASK-071` already established.
2. **No-qualifying-single fallback.** A synthetic pool where every single fails
   `min_diversity_relevance_ratio`'s floor (or fails `max_candidate_jaccard` against every incumbent):
   `final_selected` with `reserve_k1_slot=True` is byte-identical to `reserve_k1_slot=False` on the
   same input.
3. **Common-case promotion.** A synthetic pool with exactly one single that clears the floor and has
   low overlap against all incumbents: `final_selected` gains that single and loses
   `final_selected[-1]`'s pre-Stage-3 identity; assert on both the added and the removed member, not
   just the final count.
4. **The §10.1 correction, tested directly, not just described.** A synthetic single with a raw score
   high enough to clear the floor but exposure rows near-identical to an incumbent interaction's own
   exposure: assert it is **not** promoted (the corrected `max_overlap` seeding must trigger the
   existing `max_candidate_jaccard` ceiling or a heavy discount) — and, as a contrast fixture, assert
   the *naive* seeding (`max_overlap=0.0` unconditionally) **would** have promoted it, so the
   correction's own necessity is regression-tested, not merely asserted in prose.
5. **`max_feature_identity_fraction` re-check.** A synthetic incumbent set already at
   `max_per_feature` for the promoted single's own feature (with the about-to-be-dropped incumbent
   sharing a *different* feature): assert Stage 3 declines to promote; a variant where the
   about-to-be-dropped incumbent is the one holding that feature's last slot: assert promotion
   proceeds.
6. **Uncommon-case non-interference.** §7.2's construction: assert Stage 3 does not run at all
   (via the `"k1_reservation": {"eligible": False, ...}` metadata, §4.3) when interactions do not fill
   `top_k`.
7. **Already-one-single composition edge case.** §7.3's construction: assert Stage 3 does not run
   (`"eligible": False`) when Stage 2 already placed exactly one single in `final_selected`.
8. **Determinism.** Run the same synthetic pool through Stage 3 twice (fresh dict/list copies each
   time): byte-identical `final_selected` and `k1_reservation` metadata both times — a direct
   regression check for §6's analytical claim, not a substitute for it.
9. **Order-independence.** Mirroring `ADR-071`'s own adversarial standard (cited by `TASK-080` §4): the
   promoted single and dropped incumbent are identical regardless of the order rules were added to
   `interactions`/`singles` lists before sorting — a property already implied by `ranked_rules`'s own
   deterministic `(-score, rule)` sort key (line 699) plus §6's determinism analysis, verified directly
   against the real implementation rather than assumed to hold from the design alone.

## 12. Hard-rule compliance

No threshold, count, or control-flow branch in §4-§8 is justified by reference to travel's specific
pattern identities, feature names, or feature values. Every concrete number that appears
(`config.top_k`, `1` reserved slot, `_IDENTITY_CAP_OVERSELECT_MULTIPLIER`, the five reused `TASK-060`
defaults) is either a pre-existing threshold reused unchanged (cited to its own `ADR` above) or a
structural property of the algorithm itself (exactly one incumbent swapped for exactly one promoted
candidate). Every travel-specific number that appears (`12,081.5`, `26`, `7.7%`, `€325.81`, `1,375`) is
explicitly marked "illustrative" at first use (§0, §7.1, §8) and is drawn entirely from `TASK-094`'s
own already-published, already-reviewed diagnostic — used only to instantiate a general property (does
the mechanism correctly activate/decline in this real, concrete case), never to size, tune, or justify
any threshold this design introduces. §8's reserved-slot-count-of-1 determination is argued from the
*shape* of `TASK-094`'s evidence (what it did and did not measure) and from the algorithm's own
structural cost (one slot removed per reservation), not from any specific pattern's identity.

## 13. Recommendation

This design is complete against all six of `TASK-095`'s numbered requirements (§0's map) and against
its own self-critique (§10). It proposes no code change; it specifies, at `TASK-080`'s own level of
mechanism precision, what a later implementation task would need to build: one new `bool` config field
(§4.1), one new private function (§4.3) called once at one new call site, and one narrow correction to
how that function seeds `_greedy_diverse_select`'s existing overlap-discount input (§10.1) — with nine
concrete test obligations (§11) a later implementation task must satisfy before any official run uses
it. Per `TASK-095`'s own binding instruction, this document does not mark itself `APPROVED` or
`CLOSED` — that determination belongs to the independent adversarial `CODE_REVIEWER` pass this task
requires next, matching `TASK-080`→`081`'s precedent exactly.
