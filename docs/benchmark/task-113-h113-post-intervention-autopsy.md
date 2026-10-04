# TASK-113 -- Post-intervention autopsy: does the volume term separate signal acquisition from specificity refinement? (`H113`)

**Status: COMPLETE.** Read-only throughout. `engine.py` sha256 verified unchanged before and
after every probe run: `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`
(frozen `discovery-engine-v0.6.2`). See `docs/benchmark/task-113-evidence/` for every script and
raw data file this document cites; it narrates them, it does not replace them.

## Step 1 -- which 8 Core targets lost Coverage (verified, not assumed)

Script: `docs/benchmark/task-113-evidence/step1_identify_losses_and_candidates.py` ->
`step1-identification-results.json`. Reads ONLY `TASK-112`'s own already-committed raw per-seed
files (`docs/benchmark/task-112-evidence/step5-paired-4101-4130/{baseline,modified}-seed-*.json`),
recomputing "ever-recovered under baseline (any of 30 seeds), never-recovered under modified
(across all 30 seeds)" directly from each candidate's own `covers_targets` /
`per_target[target]["recall"] >= 0.5` field (`benchmark_v2_scoring.Constants.coverage_recall`,
confirmed by reading `benchmark_v2_scoring.py` directly) -- cross-checked both directions (every
`recall>=0.5` candidate is asserted present in `covers_targets` and vice versa) -- not assumed
from the prose summary in `docs/benchmark/task-112-specificity-neutral-score-results.md`, which
this independently reproduces.

**Verified result: `C02, C04, C06, C08, C09, C14, C15, H01`** -- matches `ADR-114`'s narrative
exactly, confirmed here independently from the raw data rather than taken on its word. `C07`,
`C11`, `C12` are correctly excluded: each retains partial Coverage under the modified engine
(15/30, 2/30, 1/30 respectively), so Coverage was not lost *entirely* for them.

**Structural finding from this same step.** For 7 of these 8 targets, the first baseline-covering
seed (lowest seed number, 4101-4130) is the same: **seed 4101**. In every one of those 7 cases,
the baseline candidate credited with Coverage is one of only **three** distinct two-condition
rules, all anchored on `discount_rate`:

| rule | conditions | `best_j` | covers (recall>=0.5, seed 4101) |
|---|---|---|---|
| R1 (`CAND-001`) | `discount_rate ge 0.08` AND `manual_exception eq False` | 0.162 | C06, C14 |
| R2 (`CAND-013`) | `discount_rate ge 0.05` AND `trip_duration_days ge 4.0` | 0.115 | C04, C06, C08, C09, C14, C15, H01 |
| R3 (`CAND-014`) | `discount_rate ge 0.08` AND `trip_duration_days ge 6.0` | 0.160 | C14 |

All three have low `best_j` (0.11-0.16): none is "the" canonical/precise rule for any one target
-- each is a generically **broad** rule that happens to sweep >=50% recall of several targets'
true populations at once, by breadth alone. `C02`'s first covering seed is 4102, credited to two
similarly broad, low-`best_j` candidates (`CAND-009`: `customer_price_eur lt 3785.73` AND
`discount_rate ge 0.03`; `CAND-013`: `discount_rate ge 0.05` AND `manual_exception eq False`).

None of R1/R2/R3 nor `C02`'s two candidates appear anywhere in the real modified engine's own
committed final top-15 for the same seed (`present_in_modified_final_top15_same_seed: false` for
every one, directly from `modified-seed-4101.json`/`modified-seed-4102.json`).

This gives exactly **2 distinct seeds** (4101, 4102) to trace to cover all 8 targets' first
baseline-Coverage occurrence -- no other seeds were needed.

## Step 2 -- dual-formula stage trace (methodology + fidelity validation)

Script: `docs/benchmark/task-113-evidence/step2_dual_trace.py`. READ-ONLY. Reimplements
`discover_candidates()`'s own control flow (atoms -> depth loop -> beam -> final greedy-diverse
selection) by calling the real frozen engine's own internal functions directly -- `_atoms`,
`_metric`, `_eligible`, `_development_score`, `_select_expansion_beam`, `_exposed_rows`,
`_temporal_consistency`, `_apply_stability_credit`, `_greedy_diverse_select` -- every one
imported and called unmodified, none copied or edited -- for two score variants in parallel at
every search depth:

- **baseline**: the real `_development_score` (v0.6.2), called as-is.
- **modified**: `harm_per_booking / (1 + 0.15*(k-1))` -- a plain arithmetic recomputation of
  `TASK-112`'s own documented Step-2 formula, applied to real `SplitMetric` values produced by the
  real, unmodified `_metric()`. This is the same "mechanically recomputed, no new engine run"
  technique `TASK-112`'s own Step 1 used, extended across the full search tree instead of one
  pairwise comparison. **The v0.6.3 code itself is never written, imported, or executed anywhere
  in this task** -- it no longer exists on `main`, correctly, and stays that way.

Because `_atoms`/`_eligible` never depend on `_development_score`, the two variants' atom sets and
depth-1 eligible pools are provably identical (`atoms_identical: true`, confirmed per seed, not
assumed). They diverge from `_select_expansion_beam` onward.

**Fidelity validation (critical, checked before trusting anything else from this probe):** for
each traced seed, the simulation's own "baseline" final top-15 is compared byte-for-byte
(conditions, in exact order) against the real, already-committed `baseline-seed-<N>.json`, and the
simulation's "modified" final top-15 is compared the same way against the real, already-committed
`modified-seed-<N>.json`.

| seed | baseline sim == committed (exact order) | modified sim == committed (exact order) |
|---|---|---|
| 4101 | **true** | **true** |
| 4102 | **true** | **true** |

Both checks pass exactly, for both seeds -- the reimplementation is byte-faithful to the real
engine in both directions, including order. This means every intermediate-stage number below
(which the committed data alone cannot show, since it only records final top-15 output) is
trustworthy evidence, not a narrated guess: the simulation that produced it is proven to reproduce
what the real engine (both the real v0.6.2 run and, via arithmetic recomputation, the real v0.6.3
run) actually did.

Raw traces: `docs/benchmark/task-113-evidence/step2-dual-trace-raw/trace-seed-4101.json`,
`trace-seed-4102.json`.

## Step 3 -- per-target stage-of-disappearance classification

Script: `docs/benchmark/task-113-evidence/step3_classify_targets.py` ->
`step3-classification-results.json`. For each lost-Coverage candidate (R1, R2, R3, and `C02`'s two
candidates -- 13 (target, candidate) pairs covering all 8 targets, since several targets share the
same credited candidate), checks:

1. Did each depth-1 parent single-condition survive the depth-1 beam under the modified formula?
2. Was the full depth-2 rule ever constructed/scored under the modified formula at all (i.e.
   present in the modified `scored` pool at depth 2)?
3. If constructed, did it survive to the real final top-15 (checked against both the simulation's
   own final selection and the real committed `modified-seed-*.json`)?
4. If not, by what specifically?

**Result: all 13 (candidate, target) pairs -- 8/8 targets -- classify identically:**

| target | candidate | depth-1 parents both eligible & beam-surviving under modified? | constructed/scored at depth 2 under modified? | survived final selection under modified? | classification |
|---|---|---|---|---|---|
| C02 | CAND-009 (seed 4102) | yes | yes (score 223.6) | no | **REFINEMENT-STAGE CROWDING** |
| C02 | CAND-013 (seed 4102) | yes | yes (score 248.7) | no | **REFINEMENT-STAGE CROWDING** |
| C04 | CAND-013/R2 (seed 4101) | yes | yes (score 245.6) | no | **REFINEMENT-STAGE CROWDING** |
| C06 | CAND-001/R1 (seed 4101) | yes | yes (score 328.6) | no | **REFINEMENT-STAGE CROWDING** |
| C06 | CAND-013/R2 (seed 4101) | yes | yes (score 245.6) | no | **REFINEMENT-STAGE CROWDING** |
| C08 | CAND-002 (seed 4101) | yes | yes (score 660.2) | no | **REFINEMENT-STAGE CROWDING** |
| C08 | CAND-013/R2 (seed 4101) | yes | yes (score 245.6) | no | **REFINEMENT-STAGE CROWDING** |
| C09 | CAND-013/R2 (seed 4101) | yes | yes (score 245.6) | no | **REFINEMENT-STAGE CROWDING** |
| C14 | CAND-001/R1 (seed 4101) | yes | yes (score 328.6) | no | **REFINEMENT-STAGE CROWDING** |
| C14 | CAND-013/R2 (seed 4101) | yes | yes (score 245.6) | no | **REFINEMENT-STAGE CROWDING** |
| C14 | CAND-014/R3 (seed 4101) | yes | yes (score 343.7) | no | **REFINEMENT-STAGE CROWDING** |
| C15 | CAND-013/R2 (seed 4101) | yes | yes (score 245.6) | no | **REFINEMENT-STAGE CROWDING** |
| H01 | CAND-013/R2 (seed 4101) | yes | yes (score 245.6) | no | **REFINEMENT-STAGE CROWDING** |

**Zero of the 13 is an acquisition failure.** Every single depth-1 parent condition survives the
depth-1 beam under the modified formula with room to spare -- at both seeds, depth 1 has only
44-45 total eligible single conditions against `beam_width=80`, so the depth-1 beam performs *no
cut at all* regardless of which score formula ranks them (`eligible_count == beam_size` exactly,
both variants, both seeds). The depth-2 rule is therefore constructed and scored under the
modified formula every single time, with a real, specific recomputed score (223-660). The failure
is 100% concentrated at the **final greedy-diverse selection** stage.

### The same, specific, named, reproducible mechanism

Comparing the full real final-15 depth composition, both traced seeds:

| seed | baseline final-15 depth mix | modified final-15 depth mix |
|---|---|---|
| 4101 | 12x k=2, 3x k=3 | **15x k=3 (100%)** |
| 4102 | 12x k=2, 3x k=3 | **15x k=3 (100%)** |

Under the modified (rate-only) formula, the real final top-15 **inverts completely** from a
k=2-dominated mix to a 100% k=3 (maximal-depth, most-conditions-allowed) mix, at both seeds. The
real modified-engine final-15 candidates (e.g., seed 4101: `acquisition_channel eq 'direct'` AND
`payment_method eq 'wallet'` AND `product_category eq 'premium'`, score 1375.9; `destination eq
'Tokyo'` AND `party_size ge 3.0` AND `payment_method eq 'wallet'`, score 1139.8; etc. -- full list
in `trace-seed-4101.json`'s `final_scores_modified`) are narrow, maximal-conjunction, high
per-booking-rate pockets built on feature combinations with no apparent connection to any Core
target's defining structure. Every one of R1/R2/R3's and `C02`'s candidates' recomputed modified
scores (223-660) falls below or near the bottom of this real distribution (579.3 minimum in the
real top-15, both seeds) -- not because they failed to compose, and not because the depth-1/2 beam
pruned them, but because the rate-only formula gives **no reward whatsoever for population size**
beyond the mild, fixed `1/(1+0.15*(k-1))` complexity discount, so a candidate can always improve
its score by narrowing further (shrinking `n_exposed`, raising `harm_per_booking`) all the way to
`k=3` (the configured `max_conditions` ceiling) with no population penalty to offset it -- while
the broader, k=2, true-Coverage candidates get no such escape (adding a third condition to R1/R2/R3
themselves, if anything, only shrinks their own population further without first fixing the
missing reward for the breadth they already have). This is the exact mechanism `TASK-112`'s own
Step 6 narrative speculated about ("many small, high-variance, unrelated candidates newly
competitive for every one of the ~15 final top-K slots... crowding out genuine broad recoveries
search-wide") -- now localized to a specific, reproducible, named stage (final greedy-diverse
selection) and a specific, named cause (loss of the population term's dampening effect on
`_development_score`, demonstrated directly via real `SplitMetric` values and the real, unmodified
selection function, not inferred).

## Step 4 -- concentration verdict (`ADR-114`'s pre-stated 6/8 threshold, evaluated exactly as stated)

> "`H113` is supported only if the mechanism explains Coverage loss in at least 6 of the 8
> targets." (`ADR-114`, fixed before any target was examined.)

**Count: 8 of 8 targets (100%) show the identical mechanism** -- refinement-stage crowding at
final top-15 selection, with zero acquisition-stage impairment, driven by the same, specific,
reproducible cause (the rate-only formula's unconstrained preference for maximal-depth narrow
conjunctions, confirmed by the real final-15 depth-mix inversion at both independently-traced
seeds covering all 8 targets).

**Verdict: `H113` SUPPORTED**, per `ADR-114`'s exact, literal threshold (8/8 >= 6/8). This is not
a reinterpretation of the threshold to fit the result: the threshold is a plain count and 8 clears
6.

**Disclosed nuance (required for precision, not a reinterpretation of the verdict above).** The
concentration count is unambiguous, but the *specific* mechanism found refines `H113`'s own
narrative in one respect worth stating plainly: `H113` frames the volume term as helpful "early"
(acquisition) and harmful "late" (refinement, via its own broadness bias). What this autopsy
actually finds is that the volume term's absence causes **zero** damage at the acquisition/
composition stage (every relevant depth-1 parent survives the beam easily, under either formula,
at both seeds) and **all** of the damage at the refinement/final-selection stage -- but the
refinement-stage damage is not "the volume term's broadness bias correctly getting out of the
way"; it is the opposite: refinement-stage selection, without the volume term, collapses into
uncontrolled narrowing (every slot taken by `k=3` rules), actively displacing genuine broad
recoveries rather than merely declining to reward broadness. So while the two stages *are* shown to
be separable (the acquisition stage's behavior is untouched by the term's removal; 100% of the
observed effect is attributable to the refinement/selection stage alone -- exactly the kind of
stage-separation `H113`/`TASK-113` asked whether the existing trajectory already exhibits), the
direction of the refinement-stage effect is that the term is still needed there too, just for a
different and more specific reason (bounding the maximal-narrowing incentive) than the "broadness
bias" `H111`/`H113` originally named. This is reported as a finding, not acted on: per `TASKS.md`
TASK-113 / `ADR-114`, no scoring or search change and no two-stage architecture is proposed,
designed, or treated as pre-approved by this result -- the concentration verdict above stands on
its own literal terms regardless of this nuance.

## Reproducibility

Everything above is derived from the three committed scripts and their raw JSON outputs in
`docs/benchmark/task-113-evidence/`, run against `docs/benchmark/task-112-evidence/`'s own
already-committed raw data and the real, frozen, unmodified `engine.py`
(sha256 `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`, verified before and
after every run). An independent reviewer can re-run `step1_identify_losses_and_candidates.py`,
`step2_dual_trace.py --seeds 4101 4102`, and `step3_classify_targets.py` (via `uv run python`) to
re-derive every number in this document from scratch.

## Explicitly out of scope (per `TASKS.md` TASK-113 / `ADR-114`)

No scoring or search change of any kind is proposed or implemented here. No two-stage search
architecture is designed or recommended, whether or not `H113` is supported -- that is a possible
future *consequence*, requiring its own separate founder decision and task, never pre-approved by
this one. No new seed reserve was consumed: this task analyzes only the already-spent `4101-4130`
range and `TASK-112`'s own already-produced data, plus read-only probes on those same seeds.
