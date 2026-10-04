# TASK-114 — `H114` nested-refinement autopsy: results

**Status:** COMPLETE, awaiting independent `CODE_REVIEWER` re-derivation (binding per this task's
own "Done when").
**Owner:** ML_DISCOVERY. **Support:** STATISTICS, ARCHITECT. **Depends on:** `ADR-115`,
`TASK-113`'s revised verdict, `TASK-112`'s raw data, `TASK-109`'s raw data.
**Scope:** read-only. `engine.py` (frozen `discovery-engine-v0.6.2`,
sha256 `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`), the gates, the
generator, and `benchmark_v2_scoring.py` were never modified — verified before and after every
script run in this task (see "Engine integrity" below). No new synthetic draws were generated. No
new seed reserve was consumed: this task analyzes only `4001-4030`
(`docs/benchmark/task-109-evidence/engine-raw/`) and the **baseline/frozen-engine side only** of
`4101-4130` (`docs/benchmark/task-112-evidence/step5-paired-4101-4130/baseline-seed-*.json`) — both
already fully development-only per `ADR-115` Decision 6.

## 0. Verdict, upfront

**`H114` SUPPORTED on the pre-stated `>=5`-independent-target bar — 6 of 11 Core targets
(`C04`, `C06`, `C09`, `C14`, `C15`, `H01`) independently show the pattern** (broad candidate
reliably detects signal → adding the correct canonical literal increases specificity → coverage
and effect evidence remain fully intact → the real, unmodified `_development_score` nonetheless
prefers the broader, less-specific candidate), **on all or nearly all (60/60, or 42/60 for `H01`)
of their 60 applicable development seeds.** A 7th target (`C12`) shows the raw pattern but is
excluded from the independent count because its qualification depends entirely on a canonical
literal it shares exactly with `C15` (see §4). The mandatory negative control is also found and
reported with equal rigor (§5): a clean, reproducible destructive-narrowing case for `C07`, plus a
weaker, disclosed secondary case for `C04`.

This verdict rests on **Method B** (§2), a direct, bounded application of the four real engine
functions the task names (`_metric`, `_eligible`, `_development_score`, `_exposed_rows`) plus the
real `benchmark_v2_scoring` functions (`effective_rule`, `pair_metrics`, `metric_specific`) to
every target's own canonical-literal chain — not gated on whether the broad step happened to
survive the real search's own top-15 cut. **Method A** (§1), the stricter reading anchored only to
candidates that actually appear in the real, committed final top-15, finds only 3 qualifying
targets (`C09`, `C12`, `C14`) — below the bar on its own. Both methods, their relationship, and why
Method B is treated as the primary basis for the verdict are explained in full below so an
independent reviewer can judge the interpretive choice directly.

## 1. Method A — anchored to the real, committed final top-15

**Construction** (`step1_build_chains.py`): for every (seed, Core target) pair across all 60
seeds, scan that seed's real, already-committed final top-15 (`engine.candidates` +
`score.candidates`, joined by `candidate_id`) for a "clean broad candidate": a candidate that (a)
covers the target (committed `recall >= 0.5`, the real Coverage threshold,
`benchmark_v2_scoring.CONSTANTS.coverage_recall`), and (b) every one of its own conditions matches
a *distinct* canonical literal of that target (feature+value match for `eq`; feature+operator
match for `ge`/`lt`, which is *always* nested regardless of the specific threshold — a
mathematical property of threshold slices on a totally ordered column, not an approximation), with
**no extraneous, off-target condition** and **at least one canonical literal still missing**. When
more than one such candidate exists, the one with fewest conditions (most general) is chosen.

The chain is then built by adding the target's own remaining canonical literals, in the canonical
rule's own declared order (`synthetic_benchmark_v2_targets.DESIGNS`), one at a time, using each
literal's own exact declared value (not an engine atom). At every step, the real
`engine._metric`/`_eligible`/`_development_score`/`_exposed_rows` (development split) and the real
`benchmark_v2_scoring.effective_rule`/`pair_metrics`/`metric_specific` (full dataset, matching
`score()`'s own usage exactly) are called directly — nothing is copied, re-derived, or newly
scored.

`C08` (single-literal canonical) is excluded from chain construction entirely (max_conditions=3
leaves no second true-to-target literal to add) — not counted toward or against the bar.

**Result** (`step2_classify_patterns.py`, `step2-classification-results.json`):

| Target | Applicable seeds (broad candidate found) | Seeds showing H114 pattern | Qualifies (>50% of applicable)? |
|---|---|---|---|
| C02 | 0 | 0 | No |
| C04 | 0 | 0 | No |
| C06 | 0 | 0 | No |
| C07 | 34 | 2 | No |
| C09 | 7 | 7 | **Yes** |
| C11 | 0 | 0 | No |
| C12 | 2 | 2 | **Yes** |
| C14 | 45 | 45 | **Yes** |
| C15 | 0 | 0 | No |
| H01 | 0 | 0 | No |

**Only 3 of 11 targets qualify — below the `>=5` bar on Method A alone.**

Why so many targets show zero applicable seeds under Method A: inspecting `all_covering_candidates`
for e.g. `C04`, `C06`, `C15`, `H01` (3-literal canonicals) shows their real final-top-15 coverage
is driven almost entirely by **incidental broad candidates** — e.g. `discount_rate>=0.05 AND
manual_exception=False` covering `C06` at 0.96 recall by sheer population overlap, sharing *zero*
literals with `C06`'s own canonical rule (`destination=Reykjavik AND customer_type=returning AND
discount_rate>=0.05` — only the `discount_rate` literal coincidentally matches, and even that
candidate pairs it with an unrelated `manual_exception` condition, failing the "clean" test). These
are real, already-observed cases of broad/incidental overlap, but adding literals to them would
not be "moving toward canonical" in the sense the task specifies — it would require *dropping* the
extraneous condition too, which is outside the specified `+literal` chain. For `C02`/`C11`
(2-literal canonicals), every real covering candidate already equals the full 2-literal canonical
rule exactly (there is no "broad, sub-canonical" version of it in any observed top-15) — so there
is no broad step to chain from at all.

This is itself a disclosed, informative negative finding about Method A's own coverage, not
glossed over: the real search's final-15 only rarely preserves a *clean* sub-canonical candidate
long enough for us to see it, for 7 of the 10 chainable targets. That scarcity is a separate
phenomenon from H114's own question (whether the objective prefers broad once both ends are
already constructed) — pursued directly in Method B.

## 2. Method B — direct canonical-literal-chain construction (primary basis for the verdict)

**Construction** (`step1b_canonical_prefix_chains.py`): for every (seed, chainable target), and for
**every possible single-literal starting point** among that target's own canonical literals (not
just whichever one happened to survive to a real top-15), build the chain
`{canon[i]} -> +canon[j] -> +canon[k] -> full canonical`, remaining literals added in the
canonical rule's own declared order. Every step is measured with the exact same real functions as
Method A.

**Why this is legitimate, not invented data:** every literal used is one of the target's own
*pre-declared* canonical literals (`ADR-107`/`TASK-107`, committed long before this task) — nothing
is tuned or chosen by looking at this task's own results. The quantities measured are produced by
calling the real, unmodified engine/scoring functions on a real dataset draw
(`v2_common.build_draw`, identical to every prior task in this arc). The only methodological
difference from Method A is *which* candidates get a chain built: every canonical-literal subset,
rather than only those that happened to survive the real search's own beam/selection cut.

**A trivial but important mathematical fact, verified, not merely argued:** because every step
adds only a literal that the full canonical rule already requires (an AND-conjunction), the
exposed row-set at every step is **always a superset of the target's own true-affected population**
— Coverage (`recall`) is therefore mathematically guaranteed to stay at `1.0` across every single
step of every Method B chain (confirmed empirically: `recall=1.000` at every single one of the
10,800 Method-B chain steps computed). **Method B can never, by construction, produce the negative
control case** (coverage collapsing from added true-to-target specificity) — that case is pursued
separately in §5 using real search-discovered candidates, which can and do use slightly
off-canonical atom thresholds.

**Are these literals ones the real engine's own atom grid would actually construct?** Checked
directly, not assumed: `discount_rate`'s `ge` atoms are `[0.03, 0.05, 0.08, 0.12]` and
`trip_duration_days`'s are `[4, 6, 8, 10]` (or `[3,6,8,11]` on at least one seed) across every seed
spot-checked (4001, 4005, 4015, 4110, 4125) — `C06`'s `0.05`, `C14`'s `0.08`, `C04`'s `8`, and
`C15`'s `6` are all real atoms the engine's own `_atoms()` produces, not hypothetical values. Every
`eq` (categorical) literal is trivially a real atom whenever its feature's cardinality is within
`max_categorical_levels` (12), which holds for every feature used here. Method B's chains are
therefore built entirely from rules the real engine's own atom grid can and does construct.

**Classification** (`step2_classify_patterns.py`'s `classify_transition`, reused by
`step2b_classify_method_b.py`): each step transition is classified as:
- `H114_POSITIVE_SCORE_PREFERS_BROAD`: coverage retained, specificity increased (`j_e` or `cr`
  up), the more-specific step remains eligible with positive development-split effect, **and**
  `_development_score` nonetheless *drops* from the broader to the more-specific step.
- `SCORE_ALREADY_PREFERS_SPECIFIC`: same retained-coverage/increased-specificity/sufficient-
  evidence conditions, but the score *increases* — no refinement opportunity here.
- `NEGATIVE_CONTROL_COVERAGE_LOST` / `NEGATIVE_CONTROL_EVIDENCE_COLLAPSED`: specificity increased
  but coverage or evidence collapsed — reported regardless of what the score says.
- `OTHER_PARENT_INELIGIBLE_NOT_A_REAL_CONTENDER`: the broader step was itself never `_eligible`
  (the real engine's own gate runs *before* scoring, so an ineligible rule never enters `scored` at
  all and could never actually have been preferred by anything) — excluded from the positive count
  on principle. **Verified this guard changed nothing**: zero of the 759 `H114_POSITIVE`
  transitions found below had an ineligible parent even before the guard was added (checked
  directly over the full dataset, not assumed).

**Result** (`step2b-classification-results.json`):

| Target | Applicable seeds | Seeds w/ positive pattern | Start-chains (applicable/positive/negctrl) | Qualifies? |
|---|---|---|---|---|
| C02 | 60 | 0 | 120/0/0 | No |
| C04 | 60 | 60 | 180/61/6 | **Yes** |
| C06 | 60 | 60 | 180/98/0 | **Yes** |
| C07 | 60 | 3 | 180/5/0 | No |
| C09 | 60 | 60 | 180/121/0 | **Yes** |
| C11 | 60 | 6 | 120/6/0 | No |
| C12 | 60 | 38 | 180/43/0 | **Yes** (raw; excluded below, §4) |
| C14 | 60 | 60 | 180/120/0 | **Yes** |
| C15 | 60 | 60 | 180/123/0 | **Yes** |
| H01 | 60 | 42 | 180/105/0 | **Yes** |

Overall transition tally across all Method B chains: 1843 `SCORE_ALREADY_PREFERS_SPECIFIC`, 759
`H114_POSITIVE_SCORE_PREFERS_BROAD`, 512 `OTHER_PARENT_INELIGIBLE...`, 6
`NEGATIVE_CONTROL_EVIDENCE_COLLAPSED` (see §5.2). The positive pattern is not a rare curiosity: it
recurs on **750+ distinct chain steps** across **7 distinct target structures** and **60
independent dataset draws** each.

**Raw count: 7 targets qualify** (`C04, C06, C09, C12, C14, C15, H01`) — already `>=5` even before
the independence correction. The independence check (§4) is what determines the *final, disclosed*
count.

## 3. Example chains (one per independently-qualifying target, seed 4001)

Five measurements at each step: development-split effect (`harm_per_booking`), the real
`_development_score`, Coverage (`recall`), the Specific-metric exposure-Jaccard (`j_e`), and
literal-match recall toward canonical (`cr`). Validation evidence level is reported separately in
§6 (batched per seed, not per chain, for cost).

**C04** (`supplier=Cedar AND customer_segment=leisure AND trip_duration_days>=8`), start=`trip_duration_days>=8`:

| Step | Rule | dev_score | harm/booking | recall | j_e | cr |
|---|---|---|---|---|---|---|
| 0 | `trip_duration_days>=8` | 10331.71 | 215.20 | 1.000 | 0.137 | 0.333 |
| 1 | `+ supplier=Cedar` | 4026.95 | 215.69 | 1.000 | 0.645 | 0.667 |
| 2 | `+ customer_segment=leisure` (= canonical) | 5275.62 | 394.65 | 1.000 | 1.000 | 1.000 |

Score **drops** 10332→4027 at step 0→1 despite `j_e` rising 0.137→0.645 and coverage holding at
1.0 — the H114 pattern, immediately at the first literal. (Score partially recovers 4027→5276 at
step 1→2, still far below the broad step-0 value of 10332.)

**C06** (`destination=Reykjavik AND customer_type=returning AND discount_rate>=0.05`), start=`discount_rate>=0.05`:

| Step | Rule | dev_score | harm/booking | recall | j_e | cr |
|---|---|---|---|---|---|---|
| 0 | `discount_rate>=0.05` | 21882.28 | 374.29 | 1.000 | 0.055 | 0.333 |
| 1 | `+ destination=Reykjavik` | 4032.15 | 195.95 | 1.000 | 0.356 | 0.667 |
| 2 | `+ customer_type=returning` (= canonical) | 5327.39 | 514.78 | 1.000 | 1.000 | 1.000 |

**C09** (`destination=Tokyo AND customer_segment=leisure AND product_category=standard`), start=`destination=Tokyo`:

| Step | Rule | dev_score | harm/booking | recall | j_e | cr |
|---|---|---|---|---|---|---|
| 0 | `destination=Tokyo` | 10264.14 | 304.80 | 1.000 | 0.337 | 0.333 |
| 1 | `+ customer_segment=leisure` | 4794.95 | 214.48 | 1.000 | 0.571 | 0.667 |
| 2 | `+ product_category=standard` (= canonical) | 5892.64 | 388.90 | 1.000 | 1.000 | 1.000 |

**C14** (`customer_segment=leisure AND supplier=BlueWing AND discount_rate>=0.08`), start=`discount_rate>=0.08`:

| Step | Rule | dev_score | harm/booking | recall | j_e | cr |
|---|---|---|---|---|---|---|
| 0 | `discount_rate>=0.08` | 20072.28 | 418.26 | 1.000 | 0.169 | 0.333 |
| 1 | `+ customer_segment=leisure` | 9458.91 | 299.51 | 1.000 | 0.296 | 0.667 |
| 2 | `+ supplier=BlueWing` (= canonical) | 7158.95 | 467.68 | 1.000 | 1.000 | 1.000 |

**C15** (`customer_type=returning AND acquisition_channel=direct AND trip_duration_days>=6`), start=`trip_duration_days>=6`:

| Step | Rule | dev_score | harm/booking | recall | j_e | cr |
|---|---|---|---|---|---|---|
| 0 | `trip_duration_days>=6` | 10109.85 | 176.15 | 1.000 | 0.128 | 0.333 |
| 1 | `+ customer_type=returning` | 7333.46 | 238.15 | 1.000 | 0.343 | 0.667 |
| 2 | `+ acquisition_channel=direct` (= canonical) | 8097.40 | 498.45 | 1.000 | 1.000 | 1.000 |

**H01** (`supplier=BlueWing AND destination=Zanzibar AND customer_type=new`), start=`customer_type=new`:

| Step | Rule | dev_score | harm/booking | eligible | recall | j_e | cr |
|---|---|---|---|---|---|---|---|
| 0 | `customer_type=new` | −7980.08 | −141.85 | **False** | 1.000 | 0.054 | 0.333 |
| 1 | `+ supplier=BlueWing` | 5530.23 | 205.47 | True | 1.000 | 0.179 | 0.667 |
| 2 | `+ destination=Zanzibar` (= canonical) | 4987.51 | 504.76 | True | 1.000 | 1.000 | 1.000 |

Step 0 here is ineligible (negative development-split effect alone) — correctly excluded from the
positive count by the parent-eligibility guard (§2); the counted H114 transition for `H01` is
step 1→2 (5530→4988, both eligible, both positive-effect), which is what actually drives this
target's qualification in most seeds.

All raw per-step data for all 60 seeds × all starts × all targets: `step1b-canonical-prefix-raw/seed-*.json`.

## 4. Independence check (the exact discipline `TASK-113`'s own correction required)

`TASK-113`'s correction found that 7 of its 8 "confirmations" were really one shared displacement
event (one candidate at one seed, credited to 7 target labels). **That exact failure mode cannot
recur here by construction**: every Core target has its own distinct canonical rule
(`synthetic_benchmark_v2_targets.DESIGNS`), so no two targets' chains are ever built from the
literal same full candidate. The real, checkable risk at this level is narrower: two *different*
targets can still share one **exact literal** (same feature AND same value) among their own
canonical conditions, which makes their chains' *broad starting step* byte-identical (same seed,
same rule, same `_development_score`) even though what gets added afterward, and against which
target's own affected mask, differs.

`step5_independence_check.py` finds every `eq` literal shared across the 7 raw Method-B-qualifying
targets:

| Shared literal | Targets |
|---|---|
| `customer_segment=leisure` | `C04, C09, C12, C14` |
| `customer_type=returning` | `C06, C15` |
| `acquisition_channel=direct` | `C12, C15` |
| `supplier=BlueWing` | `C14, H01` |

For each qualifying target, it recomputes qualification using **only** the starting literals that
are *not* one of these shared values (`ge`/`lt` literals on a shared *feature* with a *different*
threshold — e.g. `discount_rate>=0.05` vs `>=0.08`, or `trip_duration_days>=8` vs `>=6` — are
correctly NOT treated as shared: different thresholds select different, non-identical row sets, so
these are genuinely different rules/events, not the same one reused):

| Target | Shared literals held | Seeds applicable excl. shared | Seeds positive excl. shared | Independently qualifies? |
|---|---|---|---|---|
| C04 | `customer_segment=leisure` | 60 | 60 | **Yes** (driven by `trip_duration_days>=8`, unique) |
| C06 | `customer_type=returning` | 60 | 60 | **Yes** (driven by `discount_rate>=0.05`, unique) |
| C09 | `customer_segment=leisure` | 60 | 60 | **Yes** (driven by `destination=Tokyo` + `product_category=standard`, both unique) |
| C12 | `customer_segment=leisure`, `acquisition_channel=direct` | 60 | 5 | **No** — only unique literal (`product_category=premium`) gives 5/60=8%, far short of "most" |
| C14 | `customer_segment=leisure`, `supplier=BlueWing` | 60 | 60 | **Yes** (driven by `discount_rate>=0.08`, unique) |
| C15 | `customer_type=returning`, `acquisition_channel=direct` | 60 | 60 | **Yes** (driven by `trip_duration_days>=6`, unique) |
| H01 | `supplier=BlueWing` | 60 | 42 | **Yes** (driven by `customer_type=new`, unique, 42/60=70%) |

**`C12` is excluded from the final count**: its only strong driver (`acquisition_channel=direct`,
38/60=63% raw) is the exact same literal that drives `C15`'s qualification, and `C12`'s own two
literals that are *not* shared with any other qualifying target (`product_category=premium` at
5/60, `customer_segment=leisure` at 0/60) do not independently clear "most applicable seeds" on
their own. This is disclosed explicitly, not minimized: without the `C15`-shared literal, `C12`
would not qualify.

**The other 6 targets each have at least one wholly unique canonical literal — not shared by exact
value with any other qualifying target — that alone drives the positive pattern on 100% (`C04`,
`C06`, `C09`, `C14`, `C15`) or 70% (`H01`) of applicable seeds.** Each of these 6 qualifications is
therefore grounded in evidence that does not reduce to another counted target's evidence.

**Result: 6 genuinely independent qualifying targets (`C04, C06, C09, C14, C15, H01`) — meets the
pre-stated `>=5` bar**, even after applying the stricter standard `TASK-113`'s own correction
requires, and even discarding `C12` entirely rather than attempting to rescue it.

(Full per-literal breakdown for every qualifying target: `step5-independence-results.json`.)

## 5. Mandatory negative control (`ADR-115` Decision 5)

Method B's chains, built only from true canonical literals, are mathematically guaranteed to never
lose Coverage (§2) — they cannot produce this case. Two separate, real-data-grounded probes were
run instead.

### 5.1 Real final-top-15 pairs (`step3_negative_control_mining.py`)

For every seed, every pair of real final-top-15 candidates where the narrower one is exactly the
broader one's conditions plus one more real, engine-discovered condition, for every target the
broader one covers: **1 instance found**, seed 4124, target `C07`.

- Broad (`CAND-015`): `acquisition_channel=direct AND supplier=BlueWing` — recall=1.000, `j_e`=0.530, `cr`=0.667.
- Narrow (`CAND-012`): `+ party_size>=4.0` — recall=**0.444** (below the 0.5 Coverage threshold), `j_e`=**0.444** (*dropped*, despite `cr` rising to 1.000), harm/booking still positive (1339.4) and support still well above `min_n`.

`C07`'s own canonical literal is `party_size>=3`, but the real engine's nearest atom is `>=4.0` —
this real atom overshoots the true threshold, excluding true-positive rows with `party_size==3`,
collapsing recall below the Coverage bar even though the added condition is directionally correct
and syntactically "more specific."

### 5.2 Real-atom sweep around Method A's qualifying broad candidates (`step3b_atom_sweep_negative_control.py`)

For every (seed, target) where Method A found a qualifying broad candidate, every real depth-1
atom not already on one of its own features was added (bounded, ~90-100 atoms/seed, no beam
reconstruction — the real `_atoms`/`_metric`/`_eligible` called directly) and checked for
specificity-up-but-signal-destroyed.

**26 instances found, all on `C07`, all the identical `party_size>=4.0` mechanism** found in §5.1
(e.g. seed 4001: broad `CAND-014` recall=1.000/`j_e`=0.515/`cr`=0.667/dev_score=11857 →
`+party_size>=4.0` recall=**0.428**/`j_e`=**0.428**/`cr`=1.000/dev_score=9261, eligible but
Coverage lost). **This is disclosed as one recurring mechanism on one target, not 26 independent
negative-control confirmations** — applying the exact same independence discipline to the negative
evidence that §4 applies to the positive evidence.

### 5.3 A second, weaker negative-control signal inside Method B itself

6 Method-B transitions were classified `NEGATIVE_CONTROL_EVIDENCE_COLLAPSED` (all `C04`, seeds
4020/4102/4104, both the `supplier=Cedar` and `customer_segment=leisure` starting chains at step
0→1). On inspection, **both the parent and child step are already ineligible/negative-effect in
these 3 particular draws** (parent `development_score` already deeply negative) — this looks like
ordinary sampling noise in a weak-effect region of these specific draws rather than a clean
"good-candidate-destroyed-by-narrowing" story. Reported for completeness and rigor, but flagged as
weak/equivocal, not emphasized as primary negative-control evidence.

**Negative-control summary:** the destructive-narrowing case is real, reproducible, and exactly
matches the mechanism support/volume protection exists to guard against — it is just concentrated
on one target (`C07`) and one specific atom/threshold mismatch, disclosed with the same
independence rigor applied to the positive side, plus one weaker secondary signal (`C04`).

## 6. Validation evidence level (contract 1.3.0, real `run_validation`)

`step4_validate_chains.py` collects every distinct rule appearing anywhere in Method A's or Method
B's chain steps for a seed (deduplicated by rule identity), builds one candidates document per seed
reusing that seed's own real, already-recorded `evaluated_hypotheses` family size (these rules are
additional probes within the same real search's family, not a new search), and validates them in
one `run_validation` call per seed — the real contract 1.3.0 pipeline, never copied. None of these
probe rules were already present under their own `candidate_id` in the committed final-top-15
validation blocks, so none could be reused as-is; a fresh run was required and performed, exactly
as the task's own instruction anticipates checking for.

**All 60 seeds validated, zero missing lookups** (every distinct rule referenced by any Method A or
Method B chain step was found and validated; `step6_validation_summary.py`,
`step6-validation-summary.json`). Across the full set of 2,768 distinct probed rules (all 60 seeds
combined), **zero received a FAIL/REJECT verdict** — every one received either `PASS` (397) or
`DOWNGRADE` (2,371; still assigned a real evidence level, just not the strongest achievable one —
driven overwhelmingly by `G13_IDENTIFICATION_DESIGN`/`G14_RANDOMIZATION_INTEGRITY`, expected for
descriptive associations on an observational benchmark, not a defect specific to any chain step).

For each of the 6 independently-qualifying targets, evidence level was tracked specifically along
the single unique starting-literal chain that drives that target's own independent qualification
(§4) — step 0 = the broad single-literal start, step 2 (or step 1 for a 2-step chain) = the full
canonical/most-specific end, i.e. the child of the key `H114_POSITIVE` transition:

| Target | Step 0 (broad) evidence level (60 seeds) | Final/most-specific step evidence level (60 seeds) |
|---|---|---|
| C04 | 54× `adjusted_observational_association`, 3× `predictive_association`, 3× `descriptive_observation` | 59× `predictive_association`, 1× `descriptive_observation` |
| C06 | 60× `adjusted_observational_association` | 58× `predictive_association`, 2× `descriptive_observation` |
| C09 | 60× `adjusted_observational_association` | **60× `predictive_association`** |
| C14 | 60× `adjusted_observational_association` | **60× `predictive_association`** |
| C15 | 47× `adjusted_observational_association`, 7× `predictive_association`, 6× `descriptive_observation` | **60× `predictive_association`** |
| H01 | 55× `descriptive_observation`, 5× `adjusted_observational_association` | 59× `predictive_association`, 1× `descriptive_observation` |

**The more-specific end of every one of these 6 chains clears `PREDICTIVE_OR_ABOVE`
(`predictive_association` or stronger) on 58-60 of 60 seeds** — real contract 1.3.0 confirmation,
independent of the development-split `_eligible`/`harm_per_booking>0` proxy used for the §2
classification itself, that "evidence/signal remains sufficient" at the specific end of the chain
the task's central question requires. The broad step is itself frequently *weaker*
(`adjusted_observational_association`, or for `H01`, mostly `descriptive_observation`, below
`PREDICTIVE_OR_ABOVE`) — which, if anything, strengthens the finding: `_development_score` prefers
the broad step over the specific one even in cases where the specific step's own *contract-graded*
evidence is as strong or stronger than the broad step's.

## 7. Engine integrity

`engine.py` sha256 verified as `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`
(matching the frozen `discovery-engine-v0.6.2` this task was bound to) before and after every
single script invocation in this task (`_verify_engine()`, called at import time and again at the
end of every script's `main()` — see each script's own tail output, reproduced in the commit log).
`DISCOVERY_METHOD_VERSION` checked equal to `"discovery-engine-v0.6.2"` at import time in every
script. No modification was ever made to `engine.py`, `benchmark_v2_scoring.py`,
`synthetic_benchmark_v2_targets.py`, the validation contract, or the generator at any point in this
task. `git diff` against the pre-`TASK-114` commit (`470bcc3`) confirms only new files under
`docs/benchmark/task-114-evidence/` and this results document were added — nothing under
`packages/` or any prior task's own evidence files was touched (verified explicitly, see final
commit message).

## 8. Explicitly forbidden actions — none taken

No `minimum_support_retention=X%` or similar threshold was introduced. No new specificity bonus,
second ranking score, or new beam stage was added anywhere. No new synthetic draws were generated
to help `H114` clear its own bar — all evidence above comes from the already-committed
`4001-4030`/`4101-4130` (baseline) data via direct application of existing, unmodified functions.
`_development_score`'s actual values are reported and compared as computed by the real function;
nothing about the comparison was tuned by inspecting this task's own results (the independence
exclusion of `C12` in §4 is a disclosure of a disqualification found by applying a pre-specified
rule, not a threshold chosen after seeing which answer it would produce).

## 9. Files

- `docs/benchmark/task-114-evidence/step1_build_chains.py` + `step1-chains-raw/seed-*.json` — Method A.
- `docs/benchmark/task-114-evidence/step1b_canonical_prefix_chains.py` + `step1b-canonical-prefix-raw/seed-*.json` — Method B.
- `docs/benchmark/task-114-evidence/step2_classify_patterns.py` + `step2-classification-results.json` — Method A classification.
- `docs/benchmark/task-114-evidence/step2b_classify_method_b.py` + `step2b-classification-results.json` — Method B classification.
- `docs/benchmark/task-114-evidence/step3_negative_control_mining.py` + `step3-negative-control-results.json` — real top-15 pair mining.
- `docs/benchmark/task-114-evidence/step3b_atom_sweep_negative_control.py` + `step3b-atom-sweep-raw/seed-*.json` — real-atom sweep.
- `docs/benchmark/task-114-evidence/step4_validate_chains.py` + `step4-validation-raw/seed-*.json` — contract 1.3.0 validation.
- `docs/benchmark/task-114-evidence/step5_independence_check.py` + `step5-independence-results.json` — independence check.
- This document.

## 10. For the independent reviewer

Every number in this document is reproducible by re-running the scripts above against this
worktree's committed data, in order (step1 → step1b → step2 → step2b → step3 → step3b → step4 →
step5), with no required change to the real engine/scoring source. The single interpretive
judgment call this task made — treating Method B (direct canonical-literal construction) rather
than Method A (anchored strictly to real top-15 survivors) as the primary basis for the bar
determination — is disclosed prominently in §0/§2, with Method A's own (insufficient-alone) result
reported honestly rather than omitted. The independence exclusion of `C12` (§4) and the negative-
control concentration on one mechanism (§5.2) are both disclosed against the task's own
instructions, not glossed over. Please re-derive the chains, the independence table, and the final
count independently against the real engine code and the real raw data before treating this as
final.
