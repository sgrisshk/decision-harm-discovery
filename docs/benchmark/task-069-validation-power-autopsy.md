# TASK-069 validation power autopsy — travel, `task-064-beam-20260822-001`

**Status: POST-HOC DIAGNOSTIC throughout.** Every number in this document is produced by
`scripts/diagnose_validation_power.py`, run for real on 2026-08-28 against already-frozen,
already-committed artifacts. Nothing here is a new official `TASK-015`/`TASK-019`/`TASK-028` run,
changes any frozen artifact, threshold, gate, or recorded verdict, or touches
`packages/analytics/src/policy_analytics/validation/` or any other production module. Raw computed
output: `docs/benchmark/task-069-validation-power-autopsy-raw.json`.

**What this closes.** `TASK-069`'s reprioritization, **item 1 — validation power autopsy**, named
there as "the single most useful next number". Item 7
(`docs/benchmark/task-069-oracle-decomposition.md`) established *that* every one of the six missing
patterns' oracle branches caps at `descriptive_observation`, and recorded only the *names* of the
failing gates. This document answers the question item 1 actually asks: **which gate is binding for
each pattern, with the real computed value against the real preregistered threshold**, and whether
that failure is a data-volume ceiling or a property of the test's own construction. **It is not
design work and starts none. Items 2–6 remain untouched.**

**Binding constraint, restated.** `TASK-069`'s hard rule — extended by the reprioritization to the
validation and eligibility layers — forbids any validation-gate change, eligibility-gate redesign,
or estimator change being designed, scoped, or justified by reference to travel's seven specific
pattern identities or feature values, while explicitly permitting a diagnostic to read those
identities *to explain failures*. This document therefore reports where each pattern's evidence
ceiling comes from and what *class* of cause it is. **It proposes no replacement gate, no threshold,
no estimator, and no perturbation rule, and no per-pattern fact in it may be carried into the design
of one.** Section 6 states explicitly what would and would not be legitimate follow-up work, without
doing any of it.

## 0. Custody and scope declaration

This diagnostic reads: the frozen candidate file
`artifacts/blind/task-064-beam-20260822-001.candidates.json` (SHA-256
`9f55dddc17e22a6064af42a89fd0c3951b4ee09a5f43595c6a3a4cc618fa6d09`, re-verified by the script
against its frozen `hashes.json` before anything else runs), its sibling `discovery_metrics.json`,
the frozen `TASK-019` report `artifacts/validation/task-019-official-20260822-task-064-beam-001.json`,
the frozen `TASK-028` report `artifacts/evaluation/task-028-task-064-beam-001.json`, the public
travel analytical dataset/manifest, item 7's committed raw output
`docs/benchmark/task-069-oracle-decomposition-raw.json`, `validation/apply.py`'s real unmodified
functions, and `synthetic_data/evaluation/hidden_ground_truth.json`.

Opening travel's hidden ground truth here is the established discipline, not an exception: it has
been legitimately open since `TASK-028`'s first evaluation
(`docs/benchmark/task-029-benchmark-report-v1.md` §1), the traced run was frozen and committed via
signed receipt before any evaluation opened it, and this is the same "already frozen, now graded"
precedent set by `scripts/evaluate_benchmark.py` (`TASK-028`, `ADR-025`),
`scripts/diagnose_candidate_pool_recall.py` (`ADR-038`/`HANDOFF-055`),
`scripts/diagnose_g06_task065_b2b.py` (`TASK-067`) and `scripts/diagnose_oracle_decomposition.py`
(item 7). No blind run was issued; no new domain was touched; no other domain's ground truth was
opened.

**`artifacts/` is gitignored and per-checkout.** The script takes `--blind-root`; reproducing this
document requires a checkout holding the frozen run's outputs.

## 1. Fidelity — asserted, not assumed

`scripts/diagnose_validation_power.py` refuses to print anything unless all four of the following
hold, and all four did:

1. the frozen candidate file's SHA-256 matches its `hashes.json` entry;
2. all **9** oracle projections re-derived from `hidden_ground_truth.json` (via item 7's own
   `build_projection`, against `discovery.engine`'s own `_atoms`) are condition-for-condition
   identical to the ones item 7 committed;
3. the counterfactual validation — same eight rules, same order, same family size 26,213, the real
   unmodified `validation.apply.run_validation` — reproduces item 7's committed evidence level and
   failed-gate set **exactly**, for every pattern. The numbers below therefore explain *those*
   verdicts, not new ones;
4. the per-check robustness decomposition reproduces `validation.apply._robustness_battery`'s own
   sign-agreement, magnitude-deviation and check-count outputs exactly, to 1e-12.

`P06` is handled differently and deliberately: its oracle projection *was* selected (committed
`CAND-007`), so its gate numbers are read from the frozen official `TASK-019` report, not recomputed
counterfactually. It is the control in every table below — the one pattern that cleared the
evidence gates.

### Which gates can actually cap a candidate at `descriptive_observation`

Read from `contract.LEVEL_REQUIREMENTS`, not restated: `descriptive_observation` requires
`G00`/`G01`/`G08`; `predictive_association` adds exactly **G03, G04, G05, G10, G12**. Those five,
and only those five, decide the `descriptive → predictive` step. `G06`/`G07`/`G09`/`G11` cap at
level 3 and `G13`/`G14` fail for every observational candidate by construction — they appear in item
7's failed-gate lists but are irrelevant to the ceiling this task is about. Filtering item 7's lists
to the level-2 five is the first thing this autopsy does, and it changes the picture immediately.

## 2. Headline result — the per-pattern table

`min_exposed_records = 50`, `min_clusters = 5`, `fdr_alpha = 0.10`,
`min_holdout_effect_retention = 0.50`, `min_robustness_sign_agreement = 0.90`,
`max_robustness_magnitude_deviation = 0.50`, contract `v1.2.0`. Every threshold quoted below is the
real preregistered value from `ValidationThresholds`; every "actual" is the real computed value.

| Pattern | Level-2 gates failing | **Binding gate** | Actual value vs. real threshold | **Classification** |
|---|---|---|---|---|
| **P01** | G12 | **G12 robustness** | max magnitude deviation **66.2%** vs ceiling **50%** (sign agreement 100% vs floor 90%). Every other level-2 gate passes with room: MDE80 **236.0 €** vs observed harm **938.8 €**; 95% CI **[715.3, 1184.1] €**; raw p **9.96e-15** vs BH requirement **3.81e-6** at rank 1 (adjusted **2.6e-10** ≤ 0.10); holdout retention **67%** vs 50% | **2 — inefficient test** |
| **P02** | G05, G12 | **G05 multiplicity** | raw p **8.553e-4** vs BH requirement **1.144e-5** at rank 3 of family **26,213** → **74.7× short**; adjusted p **1.0**. G03/G04/G10 all pass (MDE80 143.4 € vs harm 239.5 €; CI [106.4, 379.7] €; holdout 172%) | **1 — insufficient data** *(dilution-induced; see §4)* |
| **P03** | G12 | **G12 robustness** | max magnitude deviation **71.3%** vs **50%** (sign agreement 100%). Every other level-2 gate passes: MDE80 **172.8 €** vs harm **396.1 €**; CI **[262.3, 552.2] €**; raw p **6.86e-8** vs requirement **7.63e-6** (111× headroom); holdout 125% | **2 — inefficient test** |
| **P04** | G03, G04, G05, G10, G12 | **G03 sample adequacy** | MDE80 **105.7 €** vs observed \|harm\| **41.6 €** → **2.54× underpowered**, and the sign is wrong: the representable branch measures **−41.6 €** (protective, not harmful). CI **[−105.6, 34.6] €** straddles zero; raw p **0.247**; holdout sign flips. Exposed n needed for 80% power: **5,878** in a **4,999-row** development split — unreachable | **1 — insufficient data** |
| **P06** | *none* | — reaches `predictive_association` | G03 MDE80 **222.2 €** vs harm **724.2 €**; CI **[418.8, 1063.8] €**; p **9.59e-6** → adjusted **0.018** ≤ 0.10; holdout 60%; G12 **32%** vs 50%. Capped at level 2 (not 3) by G11 seasonality (concentration **1.84** vs **1.50**), G13, G14 | **control** |
| **P08** | G03, G04, G05, G12 | **G03 sample adequacy** | n_exposed **35** < `min_exposed_records` **50**; MDE80 **357.3 €** vs harm **158.4 €** → **2.26× underpowered**; CI **[−148.4, 543.6] €** includes zero; raw p **0.366**; exposed n needed: **183** vs **35** available | **1 — insufficient data** |
| **P09** | G03, G05, G12 | **G03 sample adequacy** | MDE80 **142.4 €** vs harm **124.3 €** → **1.15× underpowered**; exposed n needed **305** vs **229** available; G05 raw p **0.0476** vs requirement **1.526e-5** → **3,122× short** | **1 — insufficient data** |

Two categories, committed per pattern, no hedging: **P01 and P03 are estimator/test-construction
problems. P02, P04, P08 and P09 are data problems.** P06 is neither — it clears every level-2 gate.

### Item 7 transcription correction

Item 7's §3 counterfactual table lists P09's failed gates as `G05, G06, G12, G13, G14`. Its own raw
JSON records **`G03, G05, G06, G12, G13, G14`** — `G03_SAMPLE_ADEQUACY` was dropped in
transcription. The raw JSON is correct and is what this autopsy uses; `G03` is P09's *binding*
level-2 gate, so the omission mattered. The item-7 document has been corrected with a dated
footnote; no number in its raw output changed.

## 3. Category 1 in detail — the four genuine data ceilings

These are honest ceilings to disclose, not bugs and not things to engineer around. The claim being
made is strong, so it is tested at its strongest: for each pattern, the script applies G03's and
G05's **own formulas** to the **exact true rule**'s development exposure (as item 7 committed it in
`true_rule_engine_reference`) using an *unclustered* standard error — deliberately optimistic,
because clustering the bootstrap on `customer_id` can only widen the interval. The resulting
p-value is a **lower bound** on what the real contract would compute, and is used one-directionally:
when even this bound cannot clear Benjamini–Hochberg's most lenient requirement
(`fdr_alpha / family_size = 0.10 / 26,213 = 3.815e-6`, the rank-1 case), "no estimator could have
promoted this rule at this sample size" is settled, not argued.

| Pattern | Exact true rule: dev n | dev harm/booking | MDE80 (own formula) | Optimistic unclustered p | vs. 3.815e-6 | Verdict |
|---|---:|---:|---:|---:|---|---|
| P01 | 75 | +987.05 € | 245.1 € | **1.6e-29** | clears | data is ample |
| P02 | 69 | +880.29 € | 255.4 € | **4.6e-22** | clears | data is ample |
| P03 | 152 | +396.06 € | 173.5 € | **1.6e-10** | clears | data is ample |
| **P04** | 58 | +307.45 € | 278.2 € | **1.96e-3** | **514× short** | **conclusively unpromotable** |
| P06 | 59 | +1,153.06 € | 275.9 € | **1.1e-31** | clears | data is ample |
| **P08** | **33** | +79.55 € | **367.9 €** | **0.545** | **~143,000× short** | **conclusively unpromotable** |
| **P09** | 60 | +242.13 € | **273.6 €** | **0.0132** | **3,450× short** | **conclusively unpromotable** |

**P04, P08 and P09 cannot reach `predictive_association` at travel's actual `n` under any honest
test** — not with a different estimator, not with a different multiplicity correction, not with a
different stratification. Their exact true rules fail the gates' own arithmetic by factors of
5×10² to 1×10⁵, with the most generous standard error available. P08 additionally sits below
`min_exposed_records` on both its exact rule (33) and its representable branch (35), and its true
effect is +79.55 €/booking against an outcome standard deviation of **751.9 €** — a standardized
effect of 0.106. P09's true rule at n=60 has MDE80 273.6 € against a 242.1 € effect: underpowered
even before the representable branch's 3.58× broadening dilutes it further.

**P02 is Category 1 but for a different reason, and the distinction is load-bearing.** Its *exact*
true rule (n=69, +880.29 €) clears BH's most lenient bar at p ≤ 4.6e-22. What fails is the **oracle
branch**, which the vocabulary forces to be **3.34× broader** than the pattern (225 exposed vs 137
affected records), diluting the measured effect from +880 € to **+239.5 €**. At that effect and that
`n`, closing a 74.7× p-value gap means moving z from 3.34 to 4.39 — a 31% standard-error reduction,
i.e. roughly **1.73× more exposed records at the same effect**. No reweighting of a difference in
means on n=225 against a 751 € standard deviation delivers that. So the branch as tested is
genuinely underpowered; the reason it is underpowered is **representability, upstream** — the
constraint the reprioritization already scoped as item 4, not a validation-layer problem and not an
estimator problem. Classified Category 1, with that attribution stated rather than hedged.

## 4. Category 2 in detail — G12, and why it is not a data problem

### 4.1 G12 is the one gate every non-promoted candidate fails

| Population | G12 failures |
|---|---|
| The six missing patterns' oracle branches (counterfactual) | **6 / 6** |
| The committed run's own 15 official candidates (frozen `TASK-019` report) | **11 / 15** |
| Committed candidates reaching ≥ `predictive_association` | **0 of the 4** — all four that got there passed G12 |

Every single official candidate that failed G12 landed at `descriptive_observation`. Every one that
passed it reached at least `predictive_association`. That is the whole run, not a selected slice.

### 4.2 The binding check, decomposed per candidate

`_robustness_battery` runs four families of check: leave-one-`manager`-out (8 refits), winsorising
the outcome's top/bottom 1%, the alternative outcome `gross_profit_eur`, and a numeric-threshold
perturbation at the **fixed column quantiles 0.15 and 0.25** for each numeric condition. Recorded
per check:

| Pattern | Winsorise | Leave-one-out (max of 8) | Alt outcome `gross_profit_eur` | Threshold perturbation (max) | Binding |
|---|---:|---:|---:|---:|---|
| P01 | 4.6% | 8.4% | 45.3% | **66.2%** | perturbation |
| P02 | 10.5% | 41.6% | **89.0%** *(sign flips)* | 38.2% | alt outcome |
| P03 | 1.1% | 10.3% | **70.1%** | **71.3%** | both |
| P04 | 0.2% | **91.3%** | **138.4%** | 20.8% | alt outcome |
| **P06** | 12.4% | 19.6% | 31.8% | 29.6% | *(none — all under 50%)* |
| P08 | 7.3% | **55.6%** | **88.3%** *(sign flips)* | 71.7% *(both `booking_lead_days` refits flip sign; one `party_size` refit is empty)* | alt outcome |
| P09 | 15.3% | 30.4% | **75.6%** | **93.2%** *(sign flips at q0.25)* | perturbation |

Two sub-checks do essentially all the work, and neither of them is measuring effect instability.

### 4.3 The numeric-threshold perturbation is only "one bin" for low thresholds

`docs/analytics/validation-contract.md` §5 describes G12 as "one-bin perturbation of every numeric
threshold". The implementation replaces the candidate's threshold with the column's **fixed** 0.15
and 0.25 development quantiles, regardless of where the candidate's own threshold sits. Recorded
shift, in percentile points of the development distribution:

| Condition | Threshold's own dev percentile | Perturbed to | Shift | Exposed n before → after | Deviation |
|---|---:|---|---:|---|---:|
| `booking_lead_days lt 23.0` (P01) | 20.0% | 16.0 / 29.0 | **±5.0 pts** | 79 → 59 / 102 | 16.6% / 17.3% |
| `booking_lead_days lt 23.0` (P06) | 20.0% | 16.0 / 29.0 | **±5.0 pts** | 90 → 70 / 102 | 29.6% / 11.6% |
| `discount_rate ge 0.12` (P01) | 72.5% | **0.0** / 0.03 | **+57.5 / +47.5 pts** | 79 → **320** / 264 | **66.2% / 58.6%** |
| `installments ge 3.0` (P03) | 78.8% | **1.0** / 1.0 | **+63.8 / +53.8 pts** | 152 → **829** | **71.3%** |
| `party_size ge 4.0` (P09) | 78.9% | **1.0** / 2.0 | **+63.9 / +53.9 pts** | 229 → **1,138** / 862 | **89.7% / 93.2%** |
| `party_size ge 4.0` (P02) | 78.9% | **1.0** / 2.0 | **+63.9 / +53.9 pts** | 225 → **278** | 38.2% |
| `party_size lt 2.0` (P08) | 24.0% | 1.0 / 2.0 | +9.0 / −1.0 pts | 35 → **0** / 35 | *(empty refit)* |

For a `lt` atom placed at the 0.2 quantile the perturbation moves the threshold by 5 percentile
points — a genuine one-bin nudge, and the resulting deviations (12–30%) sit comfortably under the
50% ceiling. For a `ge` atom placed at the 0.6 or 0.8 quantile — which is what
`discovery.engine._atoms`' 0.2/0.4/0.6/0.8 grid produces for any "high value is harmful" rule — the
same code moves the threshold by **48 to 64 percentile points**, deleting the condition outright
(`discount_rate ge 0.0` and `installments ge 1.0` are satisfied by every row) and growing the
exposed group by **4.1× to 5.5×**. The refit is not a perturbation of the candidate; it is a
different, far broader candidate. That its estimate differs by 60–93% is arithmetic, not evidence
about stability.

**The run's own natural experiment.** Three committed candidates differ only in where the same
feature's threshold sits:

| Committed candidate | Condition | Dev percentile | G12 max deviation | G12 | Evidence level |
|---|---|---:|---:|---|---|
| `CAND-006` | `discount_rate ge 0.05` | 30.9% | **32%** | pass | `adjusted_observational_association` |
| `CAND-009` | `discount_rate ge 0.08` | 53.7% | **44%** | pass | `predictive_association` |
| `CAND-002` | `discount_rate ge 0.12` | 72.5% | **62%** | **fail** | `descriptive_observation` |

Same feature, same dataset, near-identical rules, monotone in the threshold's percentile. G12's
verdict here tracks *where the threshold sits relative to the fixed 0.15/0.25 perturbation
quantiles*, not how stable the effect is. That is a property of the test's construction.

`party_size lt 2.0` also shows the degenerate case: perturbed to `lt 1.0` it selects **zero** rows,
`split_stats` returns `None`, and `_record` counts it as a check that ran and did not agree —
dropping P08's sign agreement to **71%** against a 90% floor on a refit that produced no estimate at
all.

### 4.4 The alternative-outcome check compares two differently-scoped outcomes on a magnitude scale

`outcomes/contract.py` defines `gross_profit_eur` as `decomposition_of` `contribution_margin_eur`:
net revenue minus base cost and refunds, **before** support cost, additional realized cost, and
payment fees. Its own description says a pattern "that appears only after subtracting downstream
costs is an operational-harm pattern", and that it is "never a ranking outcome on its own".

Read from `hidden_ground_truth.json`: **every one of the nine ground-truth patterns is configured
entirely through `additional_cost_location_delta_eur`, `support_case_rate_delta`, and
`cancellation_logit_delta`.** The first two are subtracted only in contribution margin; only the
cancellation channel reaches gross profit, through refunds. So by construction every true pattern in
this benchmark is an operational-harm pattern, and its gross-profit effect is *expected* to be
smaller or absent — that divergence is precisely the diagnostic value the outcome contract assigns
to the decomposition.

G12 nonetheless uses `gross_profit_eur` as an equal-footing robustness refit and requires the
effect's magnitude to stay within ±50% and its sign to agree. Result: the check fails for five of
the seven scoreable patterns (P02 89% with a sign flip, P03 70%, P04 138%, P08 88% with a sign flip,
P09 76%), and the two it does not fail — P01 at 45.3% and P06 at 31.8% — are the two patterns with
the largest configured `cancellation_logit_delta` (1.05 and 1.15), i.e. the two whose harm most
reaches the one channel gross profit can see. The check is measuring the outcome decomposition the
contract designed it to expose, and scoring it as instability.

### 4.5 Why P01 and P03 are Category 2, stated precisely

**P01.** Its only level-2 failure is G12, and G12's only failing checks are the two `discount_rate`
perturbations (66.2%, 58.6%). Every other check is under the ceiling, the alternative outcome
included (45.3%). Its data is not marginal: MDE80 236.0 € against a 938.8 € effect (3.98× headroom),
a raw p of 9.96e-15 against a 3.81e-6 requirement (**six orders of magnitude** of headroom), and an
exposed n of 79 where 4.9 would have sufficed for 80% power. No amount of additional data would
change the G12 result, because the failing quantity is not a function of sample size.

**P03.** Same shape, with one extra constraint worth stating rather than glossing: **two** checks
exceed the ceiling, the perturbation (71.3%) *and* the alternative outcome (70.1%). So P03's G12
failure is not attributable to a single sub-check. Its data is likewise decisive — MDE80 172.8 €
against a 396.1 € effect, raw p 6.86e-8 against a 7.63e-6 requirement (111× headroom), n=152 where
28.2 would have sufficed — and it is the benchmark's sharpest case in every other respect too: item
7 found it **exactly representable**, exact recall 1.0, broadening 1.00×, pool rank 835/17,381,
above the relevance floor.

## 5. Do all seven cap for the same reason?

**No — and the answer matters more than a yes would have.** There is one gate common to all six
non-promoted patterns (G12), but the *binding* constraints split three ways:

| Binding constraint | Patterns | What kind of follow-up it implies |
|---|---|---|
| G12's test construction, with decisive data behind it | **P01, P03** | estimator/test-design question |
| Sample size at travel's actual `n`, conclusively | **P04, P08, P09** | data-volume question — nothing to engineer |
| Sample size *induced by* a 3.34× representability broadening | **P02** | representability question (already item 4) |
| *(none — promoted)* | **P06** | — |

Calling G12 "a single architectural bottleneck" would be true and misleading at once: it is the only
gate all six fail, and for exactly two of the seven it is the only thing between the pattern and
`predictive_association`. For the other four, a perfect G12 changes nothing — they would still cap
at `descriptive_observation` on G03/G05 grounds that this autopsy shows are honest.

## 6. What this settles for `TASK-069`, and what it deliberately does not

**Settled, and it is the number item 1 was opened to get.** The achievable-at-this-`n` denominator
is **at most 3 of the 7** scoreable patterns — P01, P03, P06. P04, P08 and P09 cannot reach
`predictive_association` at travel's sample size under any honest test, by factors of 5×10² to
1×10⁵ measured with the gates' own formulas and the most generous standard error available. P02
cannot at the current vocabulary's resolution. Of those three achievable patterns, the committed run
already recovers two (P01 and P06, `TASK-028`'s own frozen metric). **The headline "unique-pattern
recall = 2/7 (29%)" is measured against a denominator of which at least three, and arguably four,
entries are unreachable by construction** — the reprioritization's item 2 (benchmark semantics) is
not a housekeeping task, it is the difference between reporting 29% and reporting 2 of 3.

**Settled about sequencing.** Items 5 and 6 (search/selection defects, then a new search algorithm)
have a hard ceiling of **3/7** even executed perfectly, and can move the metric for exactly one
pattern that is not already recovered — P03, which item 7 separately flagged as trap-`T03`-unsafe
to chase until G06's generalization is evaluated on its own schedule. A search improvement that
raises `candidate_recall` or `selection_recall` with zero change in `validation_upgrade_rate` is
still real, disclosed progress, exactly as the reprioritization's proposed engineering metrics
anticipated.

**Continuation (2026-08-28, same day).** `TASK-069`'s reformulation opened **item 2** on the first of
the questions below — whether `G12` measures genuine instability or instability of a discrete
representation of a continuous boundary. It is answered in
`docs/benchmark/task-069-g12-form-investigation.md`: **form-mismatched**, established on neutrally-
constructed synthetic data whose stability is known by construction, with the
`gross_profit_eur` refit confirmed as a second, independent form problem. That document likewise
designs nothing; the remaining questions below stay open.

**Explicitly not settled, and not to be settled here.** Whether G12's numeric-threshold perturbation
should be defined relative to the candidate's own threshold, whether a decomposition outcome should
be judged on direction rather than ±50% magnitude parity, whether an empty refit should count as a
disagreeing check, and whether `min_exposed_records`/`min_n` should be split into search and
evidence floors are all **real design questions that this document does not answer and is forbidden
from answering**. Answering any of them here would be designing a validation-gate change against
travel's seven known pattern identities — precisely what `TASK-069`'s hard rule prohibits, and the
reason a mechanism reaching 7/7 by fitting these specifics would be a worse outcome than the honest
2/7. Any such change must be motivated generically, specified before it is measured against this
benchmark, and versioned under §2 of the validation contract, which requires re-grading every
finding graded under the previous version. **None of that is authorized by this document, and none
of it has started.**

## 7. Reproduction

```sh
uv run python scripts/diagnose_validation_power.py
uv run python scripts/diagnose_validation_power.py --blind-root /path/to/checkout/artifacts/blind
```

Requires a checkout holding `artifacts/blind/task-064-beam-20260822-001.*` and
`artifacts/validation/task-019-official-20260822-task-064-beam-001.json` (both gitignored,
reproducible). Runtime is dominated by the counterfactual cluster bootstrap (~1 min); unlike item
7's script this one does not re-run the depth-3 search, because it asserts item 7's committed
projections instead of re-deriving the search that produced them.
