# TASK-116 — Frozen-engine capacity-allocation autopsy: results

**Status: COMPLETE, awaiting independent `CODE_REVIEWER` re-derivation.** `H116` is **NOT
SUPPORTED** against the pre-registered criterion. Reported plainly, not reinterpreted, per this
project's hard-stop discipline (same discipline `TASK-112`/`TASK-115` were held to).

**Owner:** STATISTICS. **Support:** ML_DISCOVERY, ARCHITECT. **Reviewer:** CODE_REVIEWER.
**Depends on:** `ADR-117`, `TASK-114`'s revised verdict, `TASK-115`'s result,
`docs/benchmark/task-107-freeze-manifest.md`.
**Scope:** read-only. `packages/analytics/src/policy_analytics/discovery/engine.py` (frozen
`discovery-engine-v0.6.2`) was never modified — verified by sha256 before and after every one of
this task's script invocations.

## 0. Engine integrity (binding invariant)

- sha256 **before** this task: `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`
- sha256 **after** this task (just reconfirmed): `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`
- **Unchanged.** Every evidence script in `docs/benchmark/task-116-evidence/` self-verifies this
  hash before running and again after, and none of them import, edit, or monkeypatch
  `engine.py`'s own module object — they call its real, unmodified top-level functions
  (`discover_candidates`, `_atoms`, `_metric`, `_eligible`, `_exposed_rows`,
  `_development_score`) directly from a separate script.

## 1. Method: reconstructing the real admissible-descendant pool without touching `engine.py`

`TASK-115` (`ADR-116`) added, then reverted after a `NOT SUCCESS` verdict, a bounded one-literal
refinement mechanism (`discovery-engine-v0.6.4`, `_refinement_candidates`) to the (now-restored)
frozen engine. That mechanism's exact generation/admissibility logic was recovered from git
history (`git show 5e84c4f^:.../engine.py`, the commit immediately before `TASK-115`'s revert) and
re-implemented **in this task's own diagnostic script**
(`docs/benchmark/task-116-evidence/step1_build_pool.py`) — never added back to `engine.py` itself.
For each seed:

1. Call the real, frozen `discover_candidates()` (no `refine_with_validation` argument — pure
   `v0.6.2` acquisition) to get the real top-`config.top_k=15` shortlist.
2. Compute the same frozen `_atoms()` vocabulary used by the real search.
3. For every shortlisted parent with room (`len(parent) < max_conditions=3`) and every atom on an
   unused feature: form the one-literal descendant, keep it only if the real, unmodified
   `_eligible()` accepts it and its development-split exposed row set
   (`_exposed_rows`) differs from its parent's (the identical non-redundancy guard
   `discover_candidates` itself already applies at depth>1). Score every admissible descendant
   with the real, unmodified `_development_score()`.

**Correctness check:** seed 4001 reproduces exactly 889 admissible descendants and the exact
per-target best-`j_e` numbers already published in `TASK-115`'s own
`step3_diagnose_capacity_cap.py` output (C04 0.370, C06 0.354, C09 0.344, C14 1.000, C15 0.248) —
byte-for-byte agreement with an independently-authored script from a prior task, confirming this
re-implementation matches the real mechanism, not an approximation of it.

Every admissible descendant was scored against all 6 targets (`C04, C06, C09, C14, C15, C07`)
using the real, unmodified `benchmark_v2_scoring` functions (`effective_rule`, `pair_metrics`,
`metric_specific`, `theta_j=0.50`, `theta_p=1.00`). A target's **productive descendant** for a
seed is the admissible pool item with the highest `j_e` among those that clear `metric_specific`
(Specific recovery); if none clears it, the target has **no productive descendant that seed**.

Real, frozen `run_validation` (contract 1.3.0) was then called once per seed (batched, reusing
that seed's own real `evaluated_hypotheses` as the family size — same precedent as
`TASK-114`/`115`'s own probe-validation scripts), covering the top-60-by-score pool items (for the
`K/2K/4K` curve) plus every target's identified productive descendant specifically (the decisive
unlimited-cap test), regardless of its rank.

## Seed sample

**30 of the 60 development seeds**, split evenly across both halves: `4001-4015` (15 seeds) and
`4101-4115` (15 seeds) — a balanced sample including the full first half of `4101-4130`, not just
seed `4001` (`TASK-115`'s own headline example). All numbers below are counted over exactly these
30 seeds; seed-level detail is in `docs/benchmark/task-116-evidence/step1-pool-raw/`,
`step2-validation-raw/`, `step3-measurements-results.json`, `step4-verdict-results.json`.

## 2. Measurement 1 — counterfactual unlimited-cap (the decisive test)

| Target | seeds with a productive descendant (/30) | of those, passes real validation under unlimited cap | of those, capacity cutoff is first cause of loss (criteria 1+2+3 all hold) |
|---|---|---|---|
| C04 | 0 | — | — |
| C06 | 0 | — | — |
| C09 | 4 | 4/4 | 4/4 |
| C14 | 21 | 21/21 | 21/21 |
| C15 | 0 | — | — |
| C07 (negative control) | 16 | 16/16 | 3/16 (13/16 already kept at real K=15, not displaced) |

**C04, C06, C15 never generate a productive descendant from any real shortlisted parent, in any
of the 30 seeds observed.** This is not a capacity failure — it happens *before* capacity ever
enters: no real top-15 shortlist member in any observed seed is a clean one-or-two-literal subset
of these targets' canonical rules for the one-literal mechanism to extend. This matches `TASK-114`
Decision/finding exactly: `C04`, `C06`, `C15` have **zero** real-top-15 ("Method A") support across
all 60 development seeds in that task's own closed, independently-re-derived result — the absence
is not new here, it is the same structural fact surfacing again under a different diagnostic lens.

**For C09 and C14, where a productive descendant does exist, measurement 1 is unambiguous and
100% consistent:** every single applicable seed (4/4 for C09, 21/21 for C14) shows the descendant
genuinely admissible (generated, eligible, non-redundant), excluded by the real K=15 capacity
cutoff, and — when given to the real, unmodified `run_validation` directly — passing with verdict
`DOWNGRADE` (never `REJECT`) in every case. Representative example (seed 4001, `C14`): the exact
canonical rule `customer_segment=leisure AND discount_rate>=0.08 AND supplier=BlueWing`
(`j_e=1.000`) sits at rank 307 of 889 admissible descendants by `_development_score`; real
validation verdict `DOWNGRADE`. Representative example (seed 4108, `C09`): canonical rule
`customer_segment=leisure AND destination=Tokyo AND product_category=standard` (`j_e=1.000`), rank
371 of 974; verdict `DOWNGRADE`.

**C07's own best-matching descendant is comparatively shallow** (rank 1-29 across its 16
applicable seeds, median well inside the real top-15/top-30), so capacity crowds it out in only
3/16 seeds — consistent with `TASK-115`'s own finding that `C07`'s baseline guard holds regardless
of the refinement mechanism (append-only design).

## 3. Measurement 2 — displacement accounting

At the real `K=15` cap, for every seed/target where the productive descendant is excluded, the
boundary slot (the lowest-scoring of the 15 kept refinement descendants) was classified against
the productive descendant as **broad ancestor** / **sibling** / **unrelated** / **duplicate-
equivalent structure** (same `(feature, operator)` signature):

| Target | broad ancestor | sibling | unrelated | duplicate-equivalent | (already kept, not displaced) |
|---|---|---|---|---|---|
| C09 | 0 | 0 | **4/4** | 0 | — |
| C14 | 0 | 0 | **21/21** | 0 | — |
| C07 | 0 | 1 | 2 | 0 | 13 |

**100% of C09/C14 displacements (25/25) are by an "unrelated" candidate** — a one-literal
descendant of a *different* shortlisted parent entirely, sharing no structural lineage with the
productive descendant. Representative example (seed 4001, `C14`): the productive descendant's
parent is `discount_rate>=0.08 AND supplier=BlueWing`-adjacent
(`customer_segment=leisure AND discount_rate>=0.08 AND supplier=BlueWing`); the real K=15 boundary
slot is `discount_rate>=0.08 AND installments<3.0 AND manual_exception=False` — a descendant of
`discount_rate>=0.08 AND manual_exception=False`, an entirely different acquisition parent. The
one documented `C07` "sibling" case (seed 4011) has both the productive descendant and the
boundary slot extending the *same* parent (`acquisition_channel=direct AND supplier=BlueWing`)
with different atoms (`party_size>=2.0` vs `quoted_cost_eur>=1632.9`).

**Reading:** the crowding is not driven by near-duplicate rescalings of the *same* lineage (which
would show up as "sibling" or "duplicate-equivalent") — it is driven by `_development_score`
ranking descendants of *entirely different* acquisition parents above the target-matching one,
because those other parents' own population/effect combination happens to score higher under the
same population-exponent/harm formula `TASK-114`'s `H114` already showed prefers breadth.

## 4. Measurement 3 — capacity-sensitivity curve (diagnostic only; NOT a benchmark-improvement
proposal; does NOT recommend any new `K`)

Replayed on the real, already-ordered pool at `K=15` (real), `2K=30`, `4K=60`, and unlimited:

| Target | survives/passes at K=15 | at K=30 | at K=60 | at unlimited |
|---|---|---|---|---|
| C09 (4 applicable seeds) | 0/4 | 0/4 | 0/4 | **4/4** |
| C14 (21 applicable seeds) | 0/21 | 0/21 | 0/21 | **21/21** |
| C07 (16 applicable seeds) | 13/16 | **16/16** | 16/16 | 16/16 |

For `C09`/`C14`, doubling or quadrupling `K` makes **no difference whatsoever** in this sample —
the productive descendant's rank (`C09`: 335-432; `C14`: 260-565, both out of pools sized
~700-1080) sits far beyond even `4K=60`. The deficit does not shrink gradually as `K` grows in a
locally-reasonable range; it only closes once the cutoff is removed entirely. This is reported
exactly as the diagnostic question asked ("does a finite, reasonable `K` make productive
refinements reachable, or does the problem keep shifting outward without bound") — for these two
targets, in this sample, it is the latter: no tested finite `K` helps, consistent with `TASK-115`'s
own §3.1 diagnosis for `C14` specifically, now shown to generalize (`21/21` applicable seeds, not
one). `C07` recovers fully by `K=30`, underscoring that `C07`'s own guard was never a deep-crowding
case to begin with.

**This is not a proposal to raise `K` to some larger value** — `C09`/`C14`'s own ranks (up to 565)
show that any single finite constant large enough to rescue even most applicable seeds would
approach "no cap," which is a different architecture question entirely (`ADR-117` Decision 6,
explicitly out of scope here).

## 5. Measurement 4 — role competition

**Structural fact, confirmed by reading the reverted `v0.6.4` code (`discover_candidates`'s own
tail, `_refinement_candidates`'s wiring):** the real mechanism **appends** refinement candidates
*after* the untouched acquisition shortlist; the two phases are structurally separate output
segments, each with its own `config.top_k`-sized budget. **Acquisition's own top-15 slots and
refinement's own top-15 slots are never literally the same list positions.** In the strictest
reading of `H116`'s own words ("competition... for a single capacity budget"), this is a
**qualification the hypothesis's own framing needs**, not a detail this task can paper over:
acquisition candidates and refinement descendants do not displace each other from one shared list.

**What genuinely is shared, and is where the real competition happens:** (a) `config.top_k` itself
is reused, unmodified, as *both* the refinement stage's validation-batch size *and* its
stop-once-filled threshold (`ADR-116` Decision 2's own tie-break rule) — the same number, not an
independent one chosen for refinement; (b) `_development_score` — the identical ranking function
that governs which candidates the acquisition stage selects in the first place — is also the sole
tie-break ranking every refinement descendant competes under. Measurement 2 shows this second
sharing is where the real damage is done: the one-literal descendants that win the refinement
stage's own 15 slots are, in every C09/C14 case observed (25/25), descendants of *different*
acquisition-shortlisted parents, ranked above the target-matching descendant purely because
`_development_score` (the same score that already decided the acquisition shortlist) favors their
parent's population/effect combination. So while acquisition and refinement do not compete for
literal output-list slots, they **do** compete — indirectly but completely deterministically — for
the *same scarce validation/keep budget*, under the *same ranking rule* that already shaped which
parents reached the shortlist to begin with. Whether this counts as "a single capacity budget" in
`H116`'s sense is a judgment call for the reviewer: this task's position is that `H116`'s causal
story (one scarce, score-ranked resource that productive refinements lose to competing rules) is
substantively correct and the direct empirical cause of the C09/C14 loss, but its literal
"single budget" phrasing should be read as "the same score function gating a same-sized budget at
two sequential stages," not "one shared list" — `ADR-117` Decision 3 item 4 anticipated exactly
this possibility ("if they don't \[share slots\], `H116`'s causal story needs revision") and this
is the honest form that revision takes: the mechanism is real, the slot-sharing metaphor is not
literal.

(A secondary, weaker signal was also computed: of the real K=15 refinement slots filled per seed,
a mean of 10.9/15 touch *some* strong target's own canonical feature name. This is not a strong
signal on its own — canonical features like `discount_rate`/`supplier` recur across several
targets' own definitions, so "touches a canonical feature" is a loose criterion — and is reported
only for completeness, not as independent evidence beyond the displacement finding above.)

## 6. C07 negative-control guard

The known pathological-narrowing literal (`+party_size>=4.0` on an `acquisition_channel=direct AND
supplier=BlueWing`-lineage parent, `TASK-114`'s own `step3_negative_control_mining.py` finding)
was checked explicitly in every seed's admissible pool: **333 hits across the 30 seeds** (mean
11.1/seed — this literal addition is admissible on most shortlisted `BlueWing`/`direct` parents
whenever one is shortlisted at all). **Zero of these 333 hits ever reach `is_specific`
(`j_e>=0.50 AND cp>=1.00`)** — consistent with the original finding that this literal collapses
`C07`'s coverage (`recall` dropping below 0.5) rather than genuinely sharpening it, so it never
even clears the bar to compete as a "productive descendant" in this task's own measurement. Zero
of the 333 received a real `REJECT` verdict either (they validate as ordinary, mediocre
descriptive-association rules — unremarkable, not somehow flagged). **Guard holds: unlimited
capacity never makes this negative-control literal indistinguishable from genuine refinement, on
any feature checked (j_e, validation verdict, or structure) and on any of the 30 seeds.**

## 7. `H116` verdict against the pre-registered criterion

**Criterion (fixed before analysis, `ADR-117` Decision 4):** SUPPORTED only if, for **at least 4 of
the 5** strong targets, all of (1) productive descendant exists, (2) capacity cutoff is the first
cause of loss, (3) passes real validation under unlimited cap, (4) holds on most applicable
seeds — simultaneously.

| Target | n seeds with productive descendant (/30) | n seeds all 3 criteria hold | fraction | qualifies? |
|---|---|---|---|---|
| C04 | 0 | 0 | — | **No** (never applicable) |
| C06 | 0 | 0 | — | **No** (never applicable) |
| C09 | 4 | 4 | 100% | **Yes** |
| C14 | 21 | 21 | 100% | **Yes** |
| C15 | 0 | 0 | — | **No** (never applicable) |

**2 of 5 strong targets qualify. The bar is 4 of 5. `H116` is NOT SUPPORTED**, reported plainly
against the fixed, pre-registered criterion, not reinterpreted after seeing the result.

This is an important, honest nuance, not a simple "no": for the 2 targets where the question is
even answerable (a productive descendant exists to test), the capacity-cutoff mechanism `H116`
describes is **completely and unambiguously confirmed** (100% of applicable seeds, both targets,
25/25 total) — the counterfactual-unlimited-cap test, the displacement accounting, and the
capacity-sensitivity curve all point the same direction with no exceptions observed. What sinks
the overall verdict against the pre-registered 4-of-5 bar is that for 3 of the 5 strong targets
(`C04`, `C06`, `C15`), the question never gets to the capacity stage at all — no real shortlisted
parent is ever close enough to their canonical rule for the one-literal mechanism to produce a
Specific-level descendant, in any of the 30 seeds observed. That is a **generation/reachability**
gap (the acquisition shortlist never contains a usable starting point), not the capacity-ranking
gap `H116` is specifically about. `ADR-117` Decision 3 item 1 anticipated this exact possibility
("if productive descendants still die after capacity is lifted... the capacity hypothesis is
false" — more precisely here: for 3/5 targets there is nothing for capacity to have killed in the
first place) and this task reports it exactly that way, not folded into a vaguer "mostly
supported."

## 8. Evidence-bar discipline

**Reliable Specific Recall remains 1/11 and Exact remains 0/11**, from `TASK-109`'s last valid
blind measurement. This task, even if `H116` had been fully SUPPORTED, would **not** have moved
that number — it is a mechanistic-understanding result only, exactly like `TASK-112` and
`TASK-115` before it. No claim in this document should be read as narrowing the gap to the
evidence bar.

## 9. What this result does and does not license

Per `ADR-117` Decision 6/7: `H116`'s capacity-ranking mechanism is real and completely confirmed
for the 2 targets where it is even testable, but the hypothesis as a whole does not clear its own
pre-registered 4-of-5 bar, primarily because 3 of 5 targets never reach the capacity stage at all.
Per `ADR-117` Decision 7 ("if `H116` is not SUPPORTED, no further local scorer/tie-break/capacity
development proceeds without a reconsideration of the search architecture itself"): this task does
**not** propose a new `K`, does **not** design or implement partitioned/reserved capacity or any
other architecture, and does **not** claim to narrow the gap to the evidence bar. Three consecutive
cycles (`TASK-112` engine-change, `TASK-115` engine-change, `TASK-116` read-only autopsy) have now
each returned a reproducible negative or partial result on strictly local interventions/diagnoses;
per `ADR-117`'s own framing, the next step, if any, is a founder-authorized reconsideration of the
search architecture itself, not a fourth local variant.

## 10. Files

- Scripts: `docs/benchmark/task-116-evidence/step1_build_pool.py` (pool reconstruction),
  `step2_validate_pool.py` (real validation probes), `step3_measurements.py` (the four
  measurements), `step4_verdict.py` (the pre-registered verdict), `step5_aggregate_report.py`
  (summary tables used in this document).
- Raw data: `step1-pool-raw/pool-seed-*.json` (30 seeds), `step2-validation-raw/val-seed-*.json`
  (30 seeds), `step3-measurements-results.json`, `step4-verdict-results.json`.
- Branch: `task-116-capacity-allocation-autopsy` (worktree-local, not pushed/merged).

## 11. For the independent reviewer

Every number above is reproducible by re-running, in order: `step1_build_pool.py --seeds <seed>`,
`step2_validate_pool.py --seeds <seed>`, `step3_measurements.py`, `step4_verdict.py`,
`step5_aggregate_report.py` — all against the real frozen engine and the real frozen
`run_validation`, no stubs, no simulated verdicts anywhere a real call was feasible (the only
simulation is the capacity-cutoff *batching order* itself at Measurement 3's `K=30`/`K=60` levels,
which replays already-known real verdicts rather than guessing any). The one methodological choice
most worth independent scrutiny: the "productive descendant" is defined as the pool's own
highest-`j_e` item clearing `metric_specific`, which can differ in identity (though apparently
never in substance, per the seed-4001 cross-check against `TASK-115`'s own numbers) from
`TASK-114`'s Method A/B canonical-literal chains — worth an independent spot-check that this
definition is not silently more generous than `TASK-114`'s own.
