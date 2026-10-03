# TASK-111 -- `H111` falsification/decomposition of `_development_score`'s broad-vs-specific preference

**Owner:** ML_DISCOVERY (lead). **Support:** STATISTICS, ARCHITECT. **Reviewer:** CODE_REVIEWER
(independent re-derivation pending -- this document is submitted for that re-derivation, not a
final verdict).

**Binding on this write-up:** `ADR-112`, `TASKS.md` `TASK-111`, `TASK-110`'s autopsy
(`docs/benchmark/task-110-specific-recovery-autopsy.md`) and its evidence
(`docs/benchmark/task-110-evidence/`), `TASK-109`'s raw seed evidence
(`docs/benchmark/task-109-evidence/engine-raw/seed-4001.json`...`seed-4030.json`), the `TASK-107`
freeze manifest.

**Read-only, falsification/decomposition only.** No change made anywhere in this task to
`engine.py`, any gate, `apply.py`, `contract.py`, the v2 generator, or the scorer.

## 0. Frozen-state verification

| File | sha256 | Matches freeze manifest |
|---|---|---|
| `packages/analytics/src/policy_analytics/discovery/engine.py` | `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549` | YES (confirmed before any work and re-confirmed at the end -- section 9) |

## 1. Method, disclosed upfront

**The real formula**, read directly from `engine.py` (lines 433-448), confirmed byte-identical to
the frozen file at the hash above:

```python
def _development_score(metric: SplitMetric, condition_count: int, config: DiscoveryConfig) -> float:
    population_component = metric.n_exposed**config.population_score_exponent
    magnitude = metric.harm_per_booking * population_component
    return magnitude / (1.0 + 0.15 * (condition_count - 1))
```

with `DiscoveryConfig.population_score_exponent` frozen at its default, `0.5`. So:
`score = harm_per_booking * n_exposed**0.5 / (1 + 0.15*(k-1))`, `k` = number of conditions.

**Instrumentation.** One script, `docs/benchmark/task-111-evidence/h111_decompose.py`, imports the
real, unmodified `_metric`, `_development_score`, `_eligible`, `Condition`, `DiscoveryConfig`
directly from `policy_analytics.discovery.engine`, and calls `v2_common.build_draw` +
`DiscoveryConfig(seed=seed)` byte-identically to `TASK-109`'s `run_blind_engine.py` and `TASK-110`'s
`search_trace.py` (same defaults, same seed, same designs module, nothing perturbed). For every one
of `TASK-109`'s 30 seeds (`4001`-`4030`) and all 11 targets (10 FNs + `C07`), it calls `_metric`
directly on: the canonical/specific rule, each of its single-literal and, for 3-literal targets,
each (k-1)-literal sub-rule (the eligibility necessary-condition for the real search's
depth-1-to-depth-k frontier construction, `engine.py` lines ~883, 925-932), the **universal broad
proxy** `U = (discount_rate>=0.03 AND manual_exception=False)` (the same unrelated structure
`TASK-110` found dominant for 5/10 targets; computed identically against every target as an
apples-to-apples cross-check, not re-picked per target),
and each target's own **named competitor** -- the literal top entry of `TASK-110`'s own
`stable-coverage-candidate-summary.json` per target (re-read programmatically from that committed
file, not re-typed from prose). **[Clarified, 2026-10-09, independent review]** Both numbers are
computed and disclosed for every target and agree in direction throughout, but the headline
Section 2 table below reports the target-specific **named competitor**, not the universal proxy —
the two coincide for 7 of 11 targets but differ for `C04, C08, C14, C15`, which use a different,
specifically-chosen rule. The universal proxy's own per-target numbers are in
`h111-analysis-summary.json` for the cross-check. A second script, `h111_analyze.py`, is pure aggregation (no engine
call) over that raw output: preference consistency, `Delta-score` margin distribution, and an
**exact log-additive decomposition** of the formula's three multiplicative components:

```
ln(score) = ln(harm_per_booking) + 0.5 * ln(n_exposed) - ln(1 + 0.15*(k-1))
Delta_ln(score_broad - score_specific) = Delta_ln(harm) + 0.5*Delta_ln(n_exposed) - Delta_ln(divisor)
```

Every one of the 330 (30 seeds x 11 targets) log-decomposition checks independently reconfirms
`total_log_delta == direct_log_delta_check` to `1e-9` (the decomposition exactly reproduces the real
score ratio; `log_decomp_all_checks_pass: true` for every target in
`h111-analysis-summary.json`) -- this is an algebraic identity, not a model fit.

Final-selection facts (whether a rule is in `TASK-109`'s own committed top-15) are read directly
from `docs/benchmark/task-109-evidence/engine-raw/seed-*.json` -- pure read, no engine call,
matched by a normalized `(feature, operator, value)` key (fixing an initial bug where the
committed JSON's `repr()`-based condition strings, e.g. `supplier eq 'BlueWing'`, did not
string-match this script's own `Condition.__str__`-style labels; fix verified against three known
facts -- `C07`'s `CAND-002` 29/30, `C11`'s `CAND-004` 26/30, `C14`'s full rule never in the top-15
-- before any aggregate number was trusted).

**Scope decision, disclosed.** This script does not re-run the full atoms-generation +
depth-1..3 frontier/beam search for all 30 seeds (that full re-derivation costs ~144s/seed, ~70+
minutes for 30 -- measured directly, see commit history). For the Delta-score decomposition
(preference consistency + margin, the task's primary requirement), that full re-derivation is not
needed: those are properties of the real `_development_score` applied to two fully-specified rules,
not of the search's own traversal order. For counterfactual reachability, this script directly
re-derives the **necessary condition** (eligibility of every single-literal/sub-pair) on all 30
seeds; for the **sufficient** side (does an eligible sub-rule actually survive the beam to depth k),
it relies on `TASK-110`'s own already-independently-reviewed 5-seed full search traces
(`search-trace-seed-{4001,4002,4010,4019,4030}.json`), disclosed explicitly per target below rather
than silently assumed to generalize.

## 2. Per-target Delta-score decomposition (all 30 seeds)

`Delta-score = score(named competitor) - score(specific/canonical)`, real `_development_score`,
development split, all 30 seeds. Log contributions are the **mean** per-seed log-additive
components (natural log units) explaining `ln(score_broad) - ln(score_specific)`.

| Target | Broad wins (named competitor) | Mean Delta | Median Delta | Min Delta | Max Delta | log-harm contrib | log-population contrib | log-complexity contrib | Reachability (necessary cond.) | In final top-15 |
|---|---|---|---|---|---|---|---|---|---|---|
| C02 | 30/30 | 9622.9 | 9785.3 | 5308.1 | 13400.3 | -0.472 | 1.548 | 0.000 | **2/30** | 0/30 |
| C04 | 30/30 | 8818.1 | 8843.8 | 5634.3 | 12508.7 | -0.343 | 1.184 | 0.123 | 30/30 | 0/30 |
| C06 | 30/30 | 9974.1 | 10324.5 | 6117.2 | 14251.7 | -0.542 | 1.432 | 0.123 | 30/30\* | 0/30 |
| C08 | **0/30** | -2144.7 | -2191.8 | -3920.0 | -827.6 | 0.087 | -0.108 | -0.140 | 30/30 | 0/30 |
| C09 | 30/30 | 8549.4 | 8530.7 | 4446.7 | 11964.6 | -0.407 | 1.168 | 0.123 | 30/30 | 0/30 |
| C11 | 26/30 | 2011.8 | 2242.3 | -3565.8 | 6965.1 | -1.131 | 1.278 | 0.000 | 30/30 | 26/30 |
| C12 | 30/30 | 5213.6 | 4976.6 | 178.3 | 8745.7 | -0.936 | 1.249 | 0.123 | 30/30 | 7/30 |
| C14 | 30/30 | 4762.2 | 4624.4 | 2444.3 | 7330.8 | 0.110 | 0.283 | 0.123 | 30/30 | 0/30 |
| C15 | 30/30 | 6337.7 | 6099.7 | 2607.6 | 10532.4 | -0.542 | 1.009 | 0.123 | 30/30 | 1/30 |
| H01 | 30/30 | 9288.5 | 9410.2 | 4419.7 | 12562.8 | -0.670 | 1.566 | 0.123 | 30/30 | 0/30 |
| **C07 (guard)** | 20/30 | 1000.2 | 1064.3 | -4600.0 | 5801.5 | -1.370 | 1.317 | 0.123 | 30/30 | 29/30 |

\* `C06`'s reachability nuance is disclosed in section 3 -- the *necessary* eligibility condition
holds on all 30 seeds, but `TASK-110`'s own 5-seed full search trace found actual beam-exclusion
(not eligibility failure) on 2/5 checked seeds; both facts are reported, not reconciled into one.

**Reading the log-decomposition, in plain terms.** For every target except `C08` (and `C14`'s harm
term, barely), the **population term** (`0.5 * Delta_ln(n_exposed)`, i.e. the sub-linear reward for
the broad rule's much larger exposed population) is the dominant positive contributor to the gap --
typically 1.0-1.6 natural-log units, versus a small, usually *negative* harm contribution (the
specific rule's higher per-booking harm is real but mathematically insufficient to offset the
population term) and a modest, mechanical complexity-penalty contribution (+0.123 whenever the
competitor has one fewer condition than the specific rule, 0 when they are the same length, as for
`C02`/`C11`). This is the formula's own stated design tension (`engine.py`'s own comment at lines
434-445): `population_score_exponent < 1` is supposed to let "a narrower rule with a stronger
per-booking effect ... out-score a broader, more diluted one at comparable total exposure" -- but
across 9 of the 10 FN targets plus the guard, the broad structures' total exposure is large enough
(`n_exposed` typically 3,000-4,000 vs. 150-900 for the true rules) that the sub-linear exponent does
not fully neutralize the population gap; it only *slows* it.

## 3. Counterfactual reachability, per target

- **`C02` -- EXCLUDED from `H111`'s evidence, as the task explicitly requires.** The necessary
  construction condition (>=1 single literal eligible) holds on only **2/30** seeds. On the other
  28/30, neither `destination=Rome` nor `customer_segment=corporate` is individually eligible
  (`harm_per_booking <= 0` alone, confirmed directly), so the 2-literal canonical rule is never
  constructed by the real incremental search at all on those seeds -- not outranked, never
  assembled. The direct score comparison (30/30 broad wins when computed off-pipeline) is real but
  irrelevant: there is no ranking decision to blame the objective for when the specific candidate
  was never in the race. This matches and extends `TASK-110`'s own 5-seed finding (4/5 blocked) to
  the full 30. **`C02`'s `S3` cause stands, independent of `H111`; it is not counted toward the kill
  criterion.**
- **`C04`, `C09`, `C12`, `C14`, `C15`, `H01`:** necessary condition holds on all 30/30 seeds (the
  canonical rule or at least one of its sub-rules is always eligible), consistent with `TASK-110`'s
  own 5-seed full search traces, which independently confirmed (real `_select_expansion_beam`,
  real `scored` dict) that the full rule is actually constructed and scored on every one of the 5
  seeds checked for each of these targets. The specific candidate is genuinely present before the
  ranking decision; its exclusion from the final top-15 is a scoring/ranking outcome, not a
  construction failure.
- **`C06`:** necessary condition holds 30/30 by this script's check, but `TASK-110`'s own 5-seed
  full trace found the full rule missing from `scored` entirely on 2/5 checked seeds (`4002`,
  `4010`) -- a beam-level exclusion that this script's cheaper necessary-condition check cannot
  detect (it only proves an anchor sub-rule is *eligible*, not that it *survives the beam*).
  Disclosed as a genuinely mixed case, same as `TASK-110`'s own classification: both a
  constructibility problem (some seeds) and a stable score-formula bias (every seed where the rule
  does reach `scored`, it is dominated; see section 2) are present.
- **`C11`:** necessary condition holds 30/30; reachability is not in question for this target --
  its canonical rule is the single most common best-Coverage candidate across all 30 seeds and
  reaches the final top-15 on 26/30.
- **`C08`:** necessary condition holds 30/30 (the single literal is always eligible, confirmed);
  its 0/30 final-top-15 result is independently and completely explained by phase ordering
  (`TASK-110` section 4.4), not by this hypothesis -- consistent with the 0/30 broad-wins result in
  section 2 (there is no score bias to speak of here, in either direction).
- **`C07` (guard):** necessary condition holds 30/30; the canonical rule is reliably constructed and
  reaches the final top-15 on 29/30 -- section 4 below.

## 4. `C07` guard finding -- reported explicitly, as required

**The hypothesized bias mechanism IS present for `C07`, but it is NOT necessary for `C07`'s own
reliable success.**

The universal broad proxy outscores `C07`'s own canonical rule on raw `_development_score` on
**20/30 seeds** (mean Delta = +1000.2, i.e. the same-direction, same-mechanism effect found for the
FN targets, just smaller in magnitude and not unanimous). Yet `C07`'s canonical rule still reaches
the final top-15 on **29/30 seeds overall** -- including **19 of the 20 seeds where the broad proxy
outscores it**. The one seed `C07` misses (`4009`) is a seed where the proxy *does* outscore it, but
so do 19 other broad-win seeds where `C07` is still selected regardless -- the broad proxy winning
the pairwise score contest is clearly not sufficient to exclude `C07`.

Two concrete reasons, both evidenced directly:
1. **Final selection is a top-15 diversity pick (`_greedy_diverse_select`), not a strict two-rule
   score gate.** Beating one named competitor on raw score is not required to win a slot among 15;
   `C07`'s rule and the universal proxy are not mutually exclusive for a slot.
2. **`C07`'s own raw score magnitude (11,129-16,756 across the 30 seeds) is already in the same
   order of magnitude as the dominant broad structures' typical range (10,000-18,000, per `TASK-110`
   section 4.3)** -- unlike the FN targets' canonical rules, whose raw scores (2,400-14,300 in
   absolute terms per target, but concentrated several-thousand *below* their own named competitor
   every single time with zero exceptions for 7 of 10 targets) never approach that range. `C07`'s
   own structural effect is strong enough in absolute terms that losing one pairwise comparison
   does not push it out of contention.

This is the delicate finding the guard was designed to surface: the score formula's breadth
preference is a real, general property of the formula (not an artifact unique to the FN targets'
own data), and `C07` is not magically exempt from it -- but `C07`'s success does not *depend* on
the bias being absent, because the final-selection step has enough slack (15 slots, diversity-based,
not winner-take-one) and `C07`'s own effect is large enough that losing the single named comparison
roughly a third of the time does not matter in practice.

## 5. `C09`/`C14` paired analysis

| | `C14` | `C09` |
|---|---|---|
| Specific/canonical rule | `customer_segment=leisure AND supplier=BlueWing AND discount_rate>=0.08` (3/3 true) | `destination=Tokyo AND customer_segment=leisure AND product_category=standard` (3/3 true) |
| Competing partial | `discount_rate>=0.08 AND supplier=BlueWing` (2/3 true, own subset) | `destination=Tokyo AND product_category=standard` (2/3 true, own subset) |
| Partial beats full, how many of 30 seeds | **30/30** | **30/30** |
| Delta-score (partial - full), range | 2,444.3 to 7,330.8 (mean 4,762.2) | 2,095.3 to 6,095.5 (mean 3,444.1) [corrected, 2026-10-09, independent review: originally read "2,145.8 to 6,095.5 (mean ~3,476)" — a transcription error in this prose table only; the underlying script/JSON (`h111-analysis-summary.json`) already had the correct values, and the max of 6,095.5 that the entire "largest margin on the success seed" argument rests on was correct both before and after this fix, so no conclusion changes] |
| Full rule ever in final top-15 | 0/30 | 0/30 |
| Partial rule in final top-15 | n/a (partial not separately tracked for `C14`; same structure as the dominant `discount+BlueWing` proxy already always present) | **1/30 -- seed 4019 only** |

**What changed on `C09`'s one success seed (4019)?** Not the score relationship: on `4019` the
partial beats the full rule by **6,095.5** -- the *largest* margin of all 30 seeds, not the
smallest (full=5,618.1, partial=11,713.6). If the hypothesis were "the specific candidate wins when
the bias happens to be weakest that draw," `4019` would be the last seed to expect a Specific hit --
it is instead the seed where the bias is strongest. What actually changes is downstream of the
score: the already-shortlisted partial candidate (consistently ranked top 3-6% of depth-2 rules on
every seed per `TASK-110`'s own trace) happens to win the final greedy-diverse selection race on
exactly this draw, and *also* happens to clear the Specific metric bar (`j_e=0.569 >= 0.50`) because
dropping `customer_segment=leisure` costs little exposure-Jaccard on that particular draw's row
composition. **The score-formula bias is the stable, constant upstream fact (30/30, never
reversing); which seed's downstream selection lottery the shortlisted partial happens to win is the
separate, genuinely stochastic fact.** This is the clearest, most literal demonstration in this
dataset of the `objective bias -> shortlist -> stochastic downstream selection` chain `ADR-112`
asks `TASK-111` to test for, directly comparable to `C14`'s every-seed, no-randomness-needed
reversal.

## 6. `S6` primary-vs-downstream determination, per target, with evidence

No target was reclassified in advance; each determination below follows directly from sections 2-3.

- **`C06` -- stable bias present, but mixed with a secondary constructibility mechanism.** Whenever
  the rule reaches `scored`, the universal/named proxy outscores it 30/30 (direct comparison,
  stable, substantial margin, mean 9,974.1). `TASK-110`'s own 5-seed trace additionally found actual
  non-construction (beam exclusion) on 2/5 seeds -- a second, independent mechanism. **Qualifies as
  evidence of the shared mechanism** (the score relationship is stable and causally decomposed, not
  merely correlated with the outcome), with the mixed-mechanism caveat disclosed rather than
  smoothed over.
- **`C09` -- stable bias is the primary upstream fact; stochastic selection is strictly
  downstream of it.** The partial beats the full rule 30/30, by a substantial and *stable* margin
  (section 5); the single success seed is determined by the final selection lottery, not by any
  weakening of the score bias (if anything, the bias is strongest on the success seed). **Clean,
  direct support for `objective bias -> shortlist -> stochastic downstream selection`, not
  independent search-variance.**
- **`C11` -- NOT supported; the named mechanism does not explain this target's misses.** The
  universal/named proxy outscores `C11`'s canonical rule on 26/30 seeds, but the 4 seeds where
  `C11`'s rule actually *beats* the proxy on raw score are **not** uniformly the same 4 seeds where
  it reaches the final top-15: of the 4 raw-score-win seeds (`4005`, `4013`, `4027`, `4028`), 3
  (`4013`, `4027`, `4028`) are *still excluded* from the final top-15, while the 4 seeds that *are*
  excluded from the top-15 (`4011`, `4013`, `4027`, `4028`) only overlap 3-for-3 with the
  raw-score-loss list and include one (`4011`) where the proxy *does* win. In short: winning or
  losing this pairwise score contest does not predict `C11`'s selection outcome. **This is genuine
  search/selection variance independent of the proposed objective-bias mechanism, consistent with
  `TASK-110`'s own "ordinary selection-margin noise" characterization** -- not forced to fit `H111`.
- **`C12` -- clean, direct support, independently reconfirmed on all 30 seeds (not just the 5-seed
  spot check `TASK-110`'s reviewer already flagged).** The named competitor beats `C12`'s canonical
  rule on raw score on **30/30** seeds, every time, by a substantial margin (178.3 to 8,745.7, never
  reversing) -- yet `C12`'s rule still wins the final top-15 slot on 7/30 seeds regardless. A
  stable, always-losing raw-score relationship coexisting with a seed-sensitive *final*-selection
  outcome is exactly the "bias narrows a shortlist; stochastic selection decides the winner among
  it" pattern.
- **`C15` -- new finding this task adds (not spotlighted by `TASK-110`'s own section 4.3, which
  named `C06/C04/H01/C02/C09` but not `C15`): a stable broad-over-specific preference also exists
  here, 30/30, never reversing (mean Delta 6,337.7).** `TASK-110`'s own characterization of `C15` as
  pure "rank volatility" (the rule's absolute rank among ~22,000 rivals swinging 99-1392) remains
  true and is not contradicted -- both facts hold simultaneously: this one named proxy *always*
  beats `C15`'s canonical rule (a stable relative fact), while the canonical rule's *absolute*
  position among the full, seed-varying pool of rivals is itself volatile (the stochastic fact).
  **Qualifies as evidence of the shared mechanism, with the volatility caveat disclosed.**

## 7. `S5` targets, reconfirmed on all 30 seeds

`C04`, `C14`, `H01` -- already classified `S5` by `TASK-110` on 5-seed spot checks -- are
reconfirmed here with the full 30-seed, exact-log-decomposition treatment: 30/30 broad wins for all
three, stable substantial margins, zero sign flips, reachability holding on all 30 seeds (the
specific rule is genuinely present and scored every time, it simply loses on ranking). No new
caveats; this section exists to record that the extension to all 30 seeds changes nothing about
these three targets' classification.

## 8. Kill criterion -- explicit evaluation

**Pre-stated threshold (`ADR-112`, `TASKS.md` `TASK-111`):** `H111` is supported only if the same
identifiable score mechanism is causally traced (via the 3-part decomposition, not mere
correlation) in **at least 5 of the 10 FNs, including at least 2 of the current `S6` targets**
(`C06, C09, C11, C12, C15`).

**Qualifying targets, with reasoning:**

| Target | Class | Qualifies? | Reasoning |
|---|---|---|---|
| C02 | S3 | **No** | Reachability fails (2/30) -- objective cannot be blamed where composition was never constructed. Explicitly excluded per the task's own instruction. |
| C04 | S5 | **Yes** | 30/30 stable broad win, reachable 30/30, zero sign flips. |
| C06 | S6 | **Yes** | 30/30 stable broad win whenever reachable; mixed with a disclosed secondary constructibility mechanism on some seeds, not a reason to exclude the score-bias finding itself. |
| C08 | S4 | **No** | 0/30 broad win on the named competitor; weak, inconsistent (17/30, near-zero mean) on the universal proxy. No bias mechanism present in either direction. |
| C09 | S6 | **Yes** | 30/30 stable broad win (partial vs. full), paired analysis directly demonstrates the shortlist->stochastic-selection chain (section 5/6). |
| C11 | S6 | **No** | 26/30 broad win is not causally linked to the actual miss pattern (section 6) -- the mechanism does not explain this target's misses. |
| C12 | S6 | **Yes** | 30/30 stable broad win, independently reconfirmed on all 30 seeds; seed-sensitive final selection sits on top of a non-seed-sensitive score relationship. |
| C14 | S5 | **Yes** | 30/30 stable broad win, the cleanest, deterministic case; no randomness needed. |
| C15 | S6 | **Yes** | 30/30 stable broad win, new finding this task adds; coexists with, does not contradict, `TASK-110`'s rank-volatility framing. |
| H01 | S5 | **Yes** | 30/30 stable broad win, reachable 30/30, zero sign flips. |

**Count: 7 of 10 FNs qualify** (`C04, C06, C09, C12, C14, C15, H01`), **including 4 of the 5 `S6`
targets** (`C06, C09, C12, C15` -- all but `C11`), well above the 5/10-including-2-`S6` threshold.
Even under the most conservative possible reading -- discounting `C06` for its disclosed mixed
mechanism and `C15` for being a new (not `TASK-110`-spotlighted) finding -- the count is still
**5 of 10, including exactly 2 `S6` targets** (`C04, C14, H01` + `C09, C12`), landing exactly on the
pre-stated threshold rather than below it. Under neither reading does the count fall below 5/10 or
below 2 `S6` targets.

**Verdict: `H111` SUPPORTED as a general remediation target**, per `ADR-112`'s exact threshold,
applied as pre-stated and not reinterpreted after the result. This finding does not itself open
`TASK-112` -- per `ADR-112`, that requires its own founder decision and is scoped to exactly one
pre-stated objective modification, evaluated two-sided, and may not use seeds `4001`-`4030` to
confirm any resulting improvement.

**What this verdict does NOT claim:** it does not claim fixing the score formula would resolve all
7 qualifying targets, nor that `S5`/`S6` are the same thing -- `C11` and `C08` remain genuinely
unexplained by this mechanism, and `C02`'s `S3` cause is untouched by it. It also does not claim any
specific remediation is safe or sufficient; that evaluation is explicitly out of this task's scope
and reserved for a possible future `TASK-112`.

## 9. Files

* This document: `docs/benchmark/task-111-h111-falsification.md`
* Scripts (read-only, real-function-calling, never touching `packages/`):
  `docs/benchmark/task-111-evidence/{h111_decompose.py,h111_analyze.py,h111_report_tables.py}`
* Raw/aggregate evidence: `docs/benchmark/task-111-evidence/{h111-decomposition-raw.json,
  h111-analysis-summary.json}`

## 10. Frozen-state re-verification (end of task)

Re-hashed `packages/analytics/src/policy_analytics/discovery/engine.py` after all of the above:
`fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549` -- **identical, byte for byte, to
the value verified at the start of this task and recorded in the `TASK-107` freeze manifest.**
`git diff --stat` against this branch's base (`0592349`) touches only files under
`docs/benchmark/task-111-evidence/`, this document, and the `TASKS.md` status append; nothing under
`packages/`, `docs/benchmark/task-109-evidence/`, `docs/benchmark/task-110-evidence/`, or any other
prior-task file.
