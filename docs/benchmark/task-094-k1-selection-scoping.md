# TASK-094 scoping determination — increasing `k==1` representation in final top-K selection

**Status: SCOPING DETERMINATION, not implementation.** Per `TASK-094`'s own binding scope
(`ADR-066`/`ADR-070` decide/implement precedent), this document answers the three required scope
questions with real, checked evidence and produces a disclosed recommendation. It changes no code,
gate, threshold, or `discovery.engine` behavior. Diagnostic script:
`scripts/diagnose_task094_k1_power_ceiling.py`. Raw output:
`docs/benchmark/task-094-k1-power-ceiling-raw.json`.

## 0. Custody and scope declaration

This diagnostic opens **no hidden ground truth** — `synthetic_data/evaluation/hidden_ground_truth.json`
is never read by `scripts/diagnose_task094_k1_power_ceiling.py`. It asks a purely structural
question (does `k==1` differ from `k>=2` in its power/safety characteristics), not a
pattern-recovery question, so no pattern identity is ever available to shape any conclusion here —
consistent with `TASK-094`'s own hard rule, satisfied by construction rather than by discipline
alone.

The script locally reproduces the real, unmodified `discovery.engine` search (`_atoms`, `_metric`,
`_eligible`, `_development_score`, `_select_expansion_beam`, `_exposed_rows` — called verbatim, not
reimplemented) against the real travel analytical dataset (`travel-bookings-analytical-v1.1.0`,
identity `b6128eb3c1bdb36515c90570aa4ccabfc3dff8d1026d9002f1c832774b60a683`, matching `ADR-082`'s own
recorded identity), under the actual current production default `DiscoveryConfig()` — the same
configuration `scripts/run_discovery.py` uses. This is the same reproduction technique
`scripts/diagnose_candidate_pool_recall.py` (`TASK-060`, `ADR-038`) and
`scripts/diagnose_validation_power.py` (`TASK-069` item 1) already established, updated to mirror
`discover_candidates`'s current redundancy-pruning logic exactly (`TASK-071`'s exposed-row-set
comparison). One additional check runs the real, unmodified `validation.apply.run_validation`
end-to-end on one real pool candidate — the same technique `TASK-081`'s independent `CODE_REVIEWER`
review used to prove the `G16` `k==1`/`k>=2` boundary (that review's check 3).

## 1. Question 1 — does more `k==1` representation actually buy anything?

**Answer: partially, and the "partially" is precise, not hedged.** The same fundamental tension
`ADR-092`/`TASK-069` measured for `k>=2` compound rules (development-split power vs. `n`) also
governs `k==1` candidates — but the *mechanism* differs, and it does not uniformly favor either
side. Measured against the real, current eligible pool (`discovery-engine-v0.6.1`, seed `1729`,
`evaluated_hypotheses=33,085`, real `G03`/`G05` formulas applied with an optimistic unclustered
standard error, exactly `TASK-069`'s own one-directional-bound convention):

| | eligible `k==1` (26 candidates) | eligible `k>=2` (22,536 candidates) |
|---|---:|---:|
| `n_exposed`: min / median / max | 522 / 1,062 / 1,999 | 50 / 240 / 1,912 |
| median `\|harm_per_booking\|` | €49.11 | €94.03 |
| median MDE (G03's own formula) | €71.57 | €139.22 |
| clears G03 power (`\|harm\| > MDE`) | 9/26 (34.6%) | 7,069/22,536 (31.4%) |
| clears BH rank-1 bound (G05, most lenient possible) | 2/26 (**7.7%**) | 2,532/22,536 (**11.2%**) |

**The structural fact `ADR-092`'s Q2/`discovery.engine`'s own comment already name is confirmed
directly, not just cited**: singletons have systematically larger `n_exposed` (median 1,062 vs.
240, ~4.4×) because they never narrow the population with an extra conjunctive condition — verified
as an exact structural invariant, not a tendency, over the real pool: **0 violations across 66,218
checked parent/child pairs** where every `k>=2` rule's `n_exposed` was confirmed `<=` every one of
its leave-one-out parents' `n_exposed`.

**But that `n_exposed` advantage does not translate into a systematically easier time clearing
`G03`/`G05`**, because it is offset by effect dilution: median `|harm_per_booking|` for singles is
about half that of compounds (€49 vs. €94), because a single, non-narrowed condition captures a
more heterogeneous, less specifically-targeted population. The two effects roughly cancel in the
aggregate — singles and compounds clear `G03`'s power check at nearly the same rate (34.6% vs.
31.4%), and singles clear the strict `G05` multiplicity bound *less* often (7.7% vs. 11.2%). **There
is no aggregate, structural power advantage to being `k==1` — if anything, this real pool shows a
slightly worse multiplicity-clearance rate for singletons than for compounds.** This directly
answers the question the task poses: "does the same power ceiling bind on singletons" — yes, via a
different but equally real route (effect dilution instead of small `n`), not a free pass.

**However, "does not help on average" is not the same as "helps nobody," and the minority that does
clear is decisive, not marginal.** 2 of the 26 eligible singles clear even the strictest (rank-1)
BH bound, and the strongest one clears by an enormous margin — not a borderline case. The pool's
single highest-`development_score` candidate overall (higher than **every** one of the 22,536
eligible `k>=2` candidates — `12,081.5` vs. the top interaction's `9,665.0`) is a real `k==1` rule:
`n_exposed=1,375`, `harm_per_booking=€325.81`, optimistic unclustered `p≈3.4e-44` against a
BH rank-1 bound of `3.0e-6` — clears by roughly 38 orders of magnitude, not a knife-edge pass.

**This was then checked against the real full pipeline, not left at the arithmetic bound.** Running
this exact candidate through the real, unmodified `validation.apply.run_validation()` (same
technique `TASK-081`'s reviewer used for its own two independently-constructed `k==1` synthetic
candidates): **it reaches `evidence_level = adjusted_observational_association`** — the tier every
one of this project's `k>=2` output is unconditionally capped below `G16`, per `ADR-080`/`082`'s own
150/150 and 15/15 findings. Its only two failed gates are `G13_IDENTIFICATION_DESIGN` and
`G14_RANDOMIZATION_INTEGRITY` — the definitional ceiling every observational candidate fails
regardless of `k`, domain, or anything else (`TASK-093`'s independent finding: these are "definitional
ceilings for any `IdentificationDesign.OBSERVATIONAL` candidate," not a discriminating gate at all).
**This candidate reaches the maximum evidence tier any observational finding in this system can ever
reach.** Combined with `TASK-081`'s own reviewer finding an independently-constructed `k==1`
candidate doing the same, this is now two independent, real, full-pipeline confirmations that
`k==1` candidates are not just theoretically unaffected by `G16` (`TASK-081`'s own structural
proof) but can and do clear every other gate in the chain too, in practice, on real data.

**Net answer to Q1:** more `k==1` representation would **not** systematically unlock a large new
class of `adjusted_observational_association`-tier findings — the aggregate pool shows no power
advantage for singletons, and most eligible singles (24/26 in this measurement) do not clear even
the most lenient multiplicity bound. But it is not nothing either: a small number of genuinely
strong, naturally single-condition signals exist in this project's own real search pool, they
score *higher* than every compound candidate under the search's own existing scoring function, and
at least one is now doubly-confirmed (arithmetic bound and full real pipeline) to clear every gate
up to the observational design ceiling — a tier `G16` currently makes structurally unreachable for
100% of what actually gets selected. The honest framing is **small, real, non-guaranteed yield**,
not "singletons are an untapped goldmine" and not "singletons are pointless."

## 2. Question 2 — what's the actual mechanism, and what does it cost?

**The mechanism is not "compounds score higher, so they deserve to win" — it is a hard phase
partition that overrides score, and this is now shown concretely, not just quoted from the design
doc's comment.** `discovery.engine.discover_candidates` (lines ~699–766) splits `ranked_rules` into
`interactions` (`k>=2`) and `singles` (`k==1`) **before** selection, then runs
`_greedy_diverse_select` on `interactions` first with the *caller's real* `top_k` (15 by default),
and only calls `_prepare`/`_greedy_diverse_select` on `singles` `if len(selected) < search_config.top_k`.
The measurement above shows why that fallback essentially never fires: the eligible `k>=2` pool
(22,536 candidates in this real run) vastly exceeds `top_k=15` in every realistic case, so
`interactions` alone always fills every slot — matching `ADR-080`'s own 150/150 and `ADR-082`'s own
15/15 historical finding exactly. **This happens regardless of relative score**: this measurement's
own top-scoring single (`12,081.5`) outranks the top-scoring interaction (`9,665.0`) by the search's
own `_development_score`, yet under the current code it can never be selected, because the phase
split is structural, not score-based.

**What a lever would concretely have to do, named without designing it:**
1. **A reserved top-K quota** (e.g., "after `_greedy_diverse_select` fills interactions, replace
   the lowest-scoring/most-overlapping selected interaction slot with the single highest-qualifying
   `k==1` candidate, if one exists that clears the same relevance-floor/quality bar interactions are
   held to") — the narrowest, most surgical option. Cost: it must not bypass
   `min_diversity_relevance_ratio`/`relevance_floor_percentile` (`TASK-060`, `ADR-038`/`ADR-040`) —
   admitting a single unconditionally, without the same quality floor compounds are held to, would
   reopen exactly the "diversity purchased with noise" risk `TASK-060`'s own closing note warns
   against. It also needs its own overlap/marginal-gain treatment against whatever is already
   selected (a single with near-total row overlap with an already-selected interaction buys nothing),
   which means routing the reserved candidate through `_greedy_diverse_select`'s own marginal-gain
   machinery rather than appending it raw.
2. **A unified, score-ranked pool across `k==1` and `k>=2`** (remove the phase split entirely, let
   `_greedy_diverse_select` run once over the combined pool). This is a materially larger change: it
   changes what `min_diversity_relevance_ratio`'s reference score is computed *over* — currently a
   phase-local quantity (`ADR-040`'s own design: "the phase's own `effective_score` distribution") —
   and would need its own decision about whether singles and compounds should compete on one
   relevance floor or two, a real design question `TASK-060`'s own history does not already answer
   (that history tunes the floor's reference *within* a phase, never merges phases).
3. **Reconsidering the interactions-first ranking rule itself** (drop the phase preference,
   sort purely by score) is the least scoped option named in `ADR-080`/`TASK-094`'s own text — it is
   the same as option 2 in effect, with the largest surface area and the least precedent to build on.

**Interaction with `TASK-060`'s existing machinery, stated concretely.** Every knob `TASK-060`
tuned (`diversity_discount_weight`, `min_diversity_relevance_ratio`, `stability_credit_weight`,
`relevance_floor_percentile`) is computed **per phase**, over that phase's own pool
(`_prepare`/`_greedy_diverse_select` called once for `interactions`, once for `singles`). A quota
mechanism (option 1) can reuse this machinery essentially unchanged — it only needs to decide *how
many* slots go to which phase, not *how* a phase's own candidates are ranked within it. A merged-pool
mechanism (options 2/3) cannot reuse it unchanged — every one of those four knobs' current semantics
is phase-relative, and `TASK-060`'s own five-iteration tuning history (`v0.3.0` through `v0.4.1`, all
recorded in that task's `TASKS.md` entry) shows this kind of selection-stage change has repeatedly
had non-obvious, only-empirically-discoverable side effects (a floor that looked safe in the
abstract suppressed genuine weak signal; a stability credit that looked reasonable was empirically
null) — real precedent for taking this seriously as its own design-and-review cycle, not a
same-day patch.

**Net answer to Q2:** the mechanism is concretely nameable (a bounded quota reusing
`_greedy_diverse_select`'s existing marginal-gain/relevance-floor logic, applied to a small,
explicitly-carved-out number of slots) and its cost is concrete too (it must not bypass the existing
quality floor, and — unlike a merged-pool redesign — it does not require reopening
`TASK-060`'s own phase-relative tuning). This is real, scoped implementation-shape information, not
a vague "reconsider the rule."

## 3. Question 3 — does promoting more `k==1` candidates reopen a safety gap?

**No — checked directly against the real gate code, not inferred from the design doc's prose
alone.**

**`G16`'s own protection is structurally inapplicable to `k==1`, not merely unused.**
`composition_safety.py`'s own module doc states it plainly ("`k == 1`: no check applies — nothing to
leave one atom out of"), and `classify_composition_safety`'s `GateResult` for a `k==1` candidate is
`NOT_APPLICABLE_SINGLE_ATOM`, `satisfied=True`, vacuously — confirmed by reading the gate code
directly, matching `TASK-081`'s own independent reviewer finding (check 3: a real `k==1` candidate
reached `adjusted_observational_association`, `G16` outcome `PASS`). This is correct, not a gap:
`G16`'s specific risk (one condition *within* a compound rule acting as a confound-like proxy that a
leave-one-out check against the rule's *own other conditions* can expose) has no analog when there
is only one condition — there is nothing to leave out.

**`G06` (confounding-adjustment) applies to `k==1` exactly as it applies to `k>=2` — verified by
reading `apply.py`'s `_select_adjustment_columns`/`_validate_one` directly, not assumed from
gate-tier prose.** The adjustment pool is `_adjustment_pool(inputs.adjustment_features,
condition_features)` — every eligible `DECISION_TIME` feature *except the candidate's own condition
features* — computed identically regardless of how many condition features the candidate has (one
or several); the greedy joint-stratification growth in `_select_adjustment_columns` has no
`k`-based branch anywhere (confirmed by grep: the only `k == 1` reference in the entire module is
the comment documenting `G16`'s own vacuity, not a `G06` special case). A `k==1` candidate goes
through the identical `G06` code path a `k>=2` candidate does.

**This means the honest framing is "no new gap," not "fully protected" — and that distinction is
already precisely on the record for a `k>=2` candidate, so it is not new here.** `G06`'s known,
already-disclosed limitation (`TASK-060`'s own `ADR-036` finding: `T03`/`CAND-012`, a **`k=2`**
candidate, cleared `G06` cleanly at attenuation `0.02` because its true confounders were not in
`G06`'s adjustment pool) is a pre-existing property of `G06` itself — a coverage/pool-completeness
limitation that already applies to compound candidates today, not something `k==1` promotion would
newly introduce. Promoting more `k==1` candidates exposes them to exactly the same confounding
check, with exactly the same already-known limitations, that every `k>=2` candidate is already
exposed to. There is no risk class here that is uncovered *specifically because* a candidate is
`k==1` — `G16`'s risk class (intra-rule composition risk) cannot exist for `k==1` by construction,
and `G06`'s risk class (external-covariate confounding) is covered identically regardless of `k`.

**Net answer to Q3:** promoting more `k==1` candidates does not reopen `G16`'s closed gap (that gap
never applied to `k==1` in the first place) and does not create a new, currently-uncovered risk
class (`G06` already covers the relevant risk class for `k==1` exactly as it does for `k>=2`, with
the same pre-existing, already-disclosed limitations — not a new discovery of this task).

## 4. Overall determination

**Recommendation: pursue, scoped narrowly as a DESIGN task (not an implementation task) — matching
this project's own `TASK-080`→`081` precedent for `G16` itself.** The evidence supports a real,
bounded, non-zero benefit (a small number of genuinely strong `k==1` candidates exist in this
project's own real search pool, outscore every compound candidate under the search's own scoring
function, and at least one is doubly-confirmed to clear every gate up to the observational design
ceiling — a tier presently unreachable by 100% of what the search actually selects). It also
supports a concrete, low-blast-radius mechanism shape (a bounded quota reusing `TASK-060`'s existing
per-phase machinery, not a wholesale selection redesign) and rules out a new safety gap. None of the
three findings is being used to *justify* the recommendation beyond what it actually shows: the
expected yield is small (on this real measurement, at most 1–2 additional `adjusted_observational`-
eligible candidates per run out of `top_k=15`, not a step-change in recall or evidence coverage),
and this is disclosed plainly rather than oversold.

**Why this clears `ADR-092`'s own bar for not re-litigating discovery-mechanism redesign.** `ADR-092`
Q1 declined a *discovery-mechanism* redesign bet specifically because it would spend scarce,
accelerator-deadline-constrained runway against a proven, unmovable sample-size ceiling
(`P04`/`P08`/`P09`, 514×–143,000× short even with the exact true rule). This recommendation is not
that bet: it is a bounded *final-selection-stage* change, explicitly the narrower category `ADR-092`
Q2 itself named as worth pursuing separately ("a final-assembly/selection-stage question, not
discovery-mechanism redesign"), it does not touch `G03`/`G05`/`G16`/`G06`/the estimator/the search
algorithm, and — given the currently accelerator-acceptance-weighted goal (evidence-tier
productization, not synthetic-benchmark recall) — even a small, reliable increase from 0 to
occasionally 1 `adjusted_observational_association`-tier finding per run is a different kind of
result than moving a recall percentage that `ADR-092` already showed cannot move.

**Follow-on opened: `TASK-095`** — design-only, scoped to producing a specific quota/reservation
mechanism proposal (not the merged-pool/rule-reordering alternatives, which this document found
carry materially higher cost against `TASK-060`'s own phase-relative tuning history), reviewed
adversarially before any implementation task is opened on it, matching `TASK-080`'s own precedent
exactly.

## 5. Reproduction

```sh
uv run python scripts/diagnose_task094_k1_power_ceiling.py
```

No frozen artifact is required — this script reproduces the search fresh against the real,
git-tracked travel analytical dataset and the real, current `discovery.engine`/`validation.apply`
code; it opens no hidden ground truth and depends on no gitignored `artifacts/` directory.
