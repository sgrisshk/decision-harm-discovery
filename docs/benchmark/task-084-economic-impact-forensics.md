# TASK-084 — Forensic: the economic-impact-estimation defect (metric 6), four independent branches

**Status: DIAGNOSIS ONLY, throughout.** No estimator, search/discovery configuration, or metric 6
definition is changed anywhere in this document or the scripts it cites. Every number below is
produced by the real, unmodified `policy_analytics.discovery.engine`,
`policy_analytics.validation.apply`, `policy_analytics.validation.economic_impact`, and
`policy_analytics.outcomes` modules, and the real, unmodified `scripts/validate_candidates.py` /
`scripts/evaluate_benchmark.py` CLIs. Branch 1's config ablation is `DiscoveryConfig` parameter
overrides passed to the unmodified `discover_candidates`, never a shipped-default or source edit.
`G06`/`G16`/discovery's existing thresholds are untouched throughout. Ground truth
(`synthetic_data/evaluation/hidden_ground_truth.json`) is opened only for diagnostic decomposition
and synthetic-control comparison, matching every prior forensic task in this chain
(`TASK-069`/`070`/`075`/`078`/`079`) — never for a production-facing narrowing or estimator change.

Raw computed output, one file per branch:
`docs/benchmark/task-084-branch1-engine-regression-raw.json`,
`docs/benchmark/task-084-branch2-3-error-decomposition-raw.json`,
`docs/benchmark/task-084-branch4-controls-raw.json`. Scripts:
`scripts/diagnose_task084_branch1_engine_regression.py`,
`scripts/diagnose_task084_branch2_3_error_decomposition.py`,
`scripts/diagnose_task084_branch4_controls.py`.

**Binding constraint, honored throughout.** `TASK-059`'s attribution-narrowed metric and this
task's own new "doubly-narrowed" diagnostic (§3) stay diagnostic tools. Neither is proposed,
implied, or framed as a replacement for official metric 6 anywhere below. Official metric 6 in
`docs/analytics/validation-contract.md`/`decision-gate.md` is unchanged. Whether the product should
measure economic damage of the whole found candidate subgroup or of the true affected
subpopulation is a separate, later semantic/design decision this task does not make.

**Artifacts-limitation disclosure (matching `TASK-075`/`078`/`079`/`ADR-084`'s own established
pattern, not silently worked around).** This worktree's `artifacts/` is entirely gitignored and
empty. `TASK-083`'s frozen run is reachable at
`/private/tmp/policy-blind-runs/task-083-official-20260830-001/frozen/` and is used directly
(§2, §3). `TASK-073`'s and `TASK-058`'s (`task-058-remediation-20260817-001`) frozen artifacts were
checked for and are **not** reachable anywhere in this worktree or under `/private/tmp/` — only
`task-083-official-20260830-001` exists there. Branch 1 (§1) therefore cannot directly re-read the
original `task-058-remediation-20260817-001` validation/evaluation JSON; it instead reconstructs
that configuration from `engine.py`'s own documented "reproduces vX.Y.Z exactly" parameter values
and verifies the reconstruction against `TASK-058`'s own disclosed literal candidate conditions
(§1.1) — a real, checked fidelity anchor, not an assumption.

---

## 1. Branch 1 — engine-version/config regression ablation

### 1.1 Method and fidelity check

`engine.py`'s own docstrings state, for every `TASK-058`/`060`/`064`/`068` behavioral change, which
`DiscoveryConfig` field value "reproduces vX.Y.Z exactly" on the **current, real, unmodified**
module — no historical code snapshot was needed. Four configurations bisect one axis at a time from
`TASK-058`'s own `ADR-023` configuration to the current `discovery-engine-v0.6.0` default:

| Label | Dataset | Diversity mechanism (`TASK-060`) | `beam_rules_per_structure` | Isolates |
|---|---|---|---|---|
| A | v1.0.0 (`TASK-058`-era) | off (`diversity_discount_weight=0`, `min_diversity_relevance_ratio=0`, `stability_credit_weight=0`) | 0 (field did not exist pre-`TASK-064`) | baseline: `TASK-058`'s own config, reconstructed |
| B | v1.1.0 (current) | off, same as A | 0 | dataset-version axis (v1.0.0→v1.1.0, adds `travel_month`) vs A |
| C | v1.1.0 | on, at its final `v0.4.1` settings (all current defaults: `0.5`/`0.5`/`0.75`/`0.5`) | 0 | `TASK-060`'s whole diversity-selection mechanism vs B |
| D | v1.1.0 | on, same as C | 2 (current default) | `beam_rules_per_structure` alone vs C; **also the actual official current configuration** |

**Fidelity check 1 (config A reproduces `TASK-058`'s real historical candidates).** Config A's
discovered `CAND-012` = `booking_lead_days lt 23.0 AND discount_rate ge 0.08 AND supplier eq
BlueWing` and `CAND-014` = `booking_lead_days lt 23.0 AND destination eq Tokyo AND payment_method eq
bank_transfer` — an exact, literal match to the two conditions `TASK-058`'s own `TASKS.md` entry
disclosed on 2026-08-17 as new relative to `task-015-official-20260816-015`. Config A's aggregate
scores (Top-10 precision 90%, economic-weighted recall 45.2%, direction accuracy 100%, no trap
promoted) also match `TASK-058`'s own recorded numbers exactly. This confirms config A is a
faithful reconstruction of the real historical search, not a guess.

**Fidelity check 2 (config D reproduces `TASK-083`'s official numbers).** Config D — the literal
current `DiscoveryConfig()` defaults — reproduces `TASK-083`'s frozen, official metric-6 numbers
**exactly**: median impact error 219.9%, attribution-narrowed diagnostic median 73.6%, Top-10
precision 70%, economic-weighted recall 45.2%, no trap promoted, direction accuracy 100%. This is
the same reproduction discipline `ADR-084` used and confirms the whole harness (search → validate
→ evaluate, run fresh to scratch paths) is faithful end to end.

### 1.2 Results

| Config | `evaluated_hypotheses` | Top-10 precision | Econ-weighted recall | **Median impact error** | Attribution-narrowed median |
|---|---:|---:|---:|---:|---:|
| A (`v0.2.0` config, v1.0.0 data) | 6,557 | 90% | 45.2% | **209.4%** | 75.6% |
| B (`v0.2.0` config, v1.1.0 data) | 7,355 | 90% | 45.2% | **209.4%** | 75.1% |
| C (adds `TASK-060` diversity) | 7,355 | 70% | 45.2% | **186.1%** | 72.5% |
| D (adds `beam_rules_per_structure=2`, = official) | 33,085 | 70% | 45.2% | **219.9%** | 73.6% |

### 1.3 The central, unexpected finding

**Config A — `TASK-058`'s own exact discovery configuration, verified faithful by §1.1's two
independent checks, scored through today's real, unmodified validation/evaluation pipeline — gives
a median impact error of 209.4%, not the ~37.5% `TASK-058`'s own 2026-08-17 closing record
reported.** This is the single most important result of this branch: it means the historical
37.5%→204%+ trajectory this task was chartered to explain is **not** reproduced by re-running the
old discovery configuration alone. Whatever changed between 2026-08-17 and now, it is not fully — or
even mostly — a discovery-engine search-configuration effect, because holding discovery config fixed
at its exact historical value still yields today's high-error regime.

A striking, disclosed lead (not a proven finding, given §0's artifacts limitation): in config A's
own per-candidate detail, `CAND-006`'s individual relative error is **0.375 — exactly 37.5%, to
three significant figures**. `CAND-006` matches both `P01` and `P06` and is the single
lowest-dilution `P01`-matched candidate in the whole set (dilution 6.4×). This raises the concrete,
checkable possibility that the historically-reported "37.5% median" reflected a much smaller (or
differently defined) validated-and-matched candidate population at the time — most plausibly one
effectively dominated by, or equal to, this one candidate — rather than the 12-candidate median
config A actually computes today. Three real, dated facts support this being at least *plausible*
rather than merely a coincidence: the validation contract materially evolved after 2026-08-17 in
ways that can change which candidates classify into `VALIDATED_LEVELS` (`G06`'s adjustment-set
generalization, `ADR-036`/`ADR-042`, 2026-08-20 and later; `G12`'s threshold-perturbation fix,
`ADR-064`/contract v1.3.0, 2026-08-28; `G16`, `TASK-081`, 2026-08-30) — none of which existed when
`TASK-058`'s own `TASK-019` run graded these candidates. This lead is **not resolved** here — the
original frozen `task-058-remediation-20260817-001` validation/evaluation artifacts are not
reachable in this worktree (§0) — and is named, not asserted, as a concrete follow-on thread.

### 1.4 What the clean, controlled axes actually show

Holding today's validation/evaluation layer fixed and varying only discovery config:

- **Dataset version (A→B, v1.0.0→v1.1.0):** median impact error unchanged (209.4%→209.4%). This
  axis contributes nothing measurable. The extra `travel_month` feature v1.1.0 adds was never
  selected into any of the 15 candidates at either dataset version under this config.
- **`TASK-060` diversity-selection mechanism (B→C):** median impact error *decreases*
  (209.4%→186.1%), even though Top-10 precision drops (90%→70%) — the same trade this mechanism was
  always known to make (`ADR-036` et al.). This axis is not a contributor to metric 6's worsening;
  if anything it is mildly protective for this specific metric while being costly for a different
  one.
- **`beam_rules_per_structure=2` (C→D, the already-flagged, previously untested-in-isolation
  config-custody issue since `TASK-073`/`081`/`083`):** median impact error *increases*
  (186.1%→219.9%, +33.8pp), a real, one-axis, controlled effect — the largest single movement any
  tested axis produces, and it lands exactly on the actual official configuration.

### 1.5 Completion criterion (c): cause, amplifier, or correlated — stated explicitly

**`beam_rules_per_structure=2` is a demonstrated AMPLIFIER, not the sole CAUSE and not merely
CORRELATED.** The C→D ablation isolates it as the only tested variable and shows a real,
directionally-consistent (error worsens) increase of +33.8pp — a genuine, controlled causal effect,
not a coincidence of timing. It is not the sole cause because config C, without it, already scores
186.1% under today's pipeline — far above `TASK-058`'s historical 37.5%, and even config A (the
literal historical configuration, `beam_rules_per_structure` field not even existing) scores 209.4%.
**The dataset-version bump (v1.0.0→v1.1.0) is CORRELATED, non-causal**: it co-occurred in time with
the broader regression narrative but produces zero measurable effect in a controlled, one-axis test.
**`TASK-060`'s diversity-selection mechanism is neither a cause nor a relevant correlate of the
metric-6 worsening** — it moves the number in the opposite (improving) direction while being a real
cost elsewhere (Top-10 precision). **The single largest unexplained factor — the gap between
`TASK-058`'s reported ~37.5% and any reconstructed discovery configuration's ~186–209% under today's
pipeline — is not caused by any discovery-engine config axis tested here at all**; §1.3's lead points
at the validation/evaluation layer's own evolution as the more probable locus, but this is disclosed
as an open, evidenced-but-unconfirmed lead, not a closed finding, given the unreachable original
artifact.

---

## 2. Branch 2 — case-level error decomposition

### 2.1 Substrate

`TASK-083`'s frozen `candidates.json` reproduced through the real, unmodified
`scripts/validate_candidates.py` → `scripts/evaluate_benchmark.py` pipeline to a scratch path
(§1.1's fidelity check 2 applies identically here — same exact numbers reproduced). All 9
ground-truth-matched, validated candidates decomposed:

| Candidate | Pattern(s) | Dilution | Overlap fraction | Recall of true pattern | Whole-rule signed error | Attribution-narrowed signed error | **Doubly-narrowed signed error** |
|---|---|---:|---:|---:|---:|---:|---:|
| CAND-001 | P01 | 19.7× | 5.1% | 93.0% | +464.6% | −71.3% | **−4.8%** |
| CAND-002 | P01 | 3.8× | 26.1% | 100.0% | +84.5% | −52.2% | **−0.2%** |
| CAND-003 | P01 | 11.6× | 8.6% | 100.0% | +280.7% | −67.2% | **−0.2%** |
| CAND-004 | P01 | 19.3× | 5.2% | 72.5% | +314.0% | −78.6% | **−21.1%** |
| CAND-005 | P01 | 19.2× | 5.2% | 85.9% | +412.0% | −73.6% | **−15.8%** |
| CAND-006 | P01, P06 | 6.4× | 15.7% | 77.9% | +37.5% | −78.4% | **−22.7%** |
| CAND-007 | P06 | 1.4× | 70.5% | 100.0% | +6.5% | −24.9% | **+5.5%** |
| CAND-008 | P01 | 12.8× | 7.8% | 100.0% | +219.9% | −75.0% | **−0.2%** |
| CAND-015 | P06 | 22.9× | 4.4% | 69.4% | +137.3% | −89.7% | **−18.1%** |

"Doubly-narrowed" (new in this task, §3) recomputes the per-record effect itself — not just the
population multiplier — over the exact overlap population, using the real
`summarize_group`/`raw_difference`/`harm_score` functions, then scales by `overlap_n`. Median
absolute errors across the three variants: **219.9% (whole-rule) → 73.6% (attribution-narrowed) →
5.45% (doubly-narrowed)**.

### 2.2 Direction, not just magnitude

Every one of the 9 whole-rule errors is a positive (over-)estimate — `9/9`. Every one of the 9
attribution-narrowed errors is a negative (under-)estimate — `9/9`. This directional flip is exactly
what the two narrowing mechanisms predict mechanically: the whole-rule estimator's count term
(`exposed_total`, the candidate's full diluted population) always inflates the total upward past the
matched pattern's true impact; `TASK-059`'s attribution-narrowing rescales by the much smaller
`overlap_n` while reusing the same (already dilution-attenuated) per-record effect, which — per
§1.2/§4's algebraic result — over-corrects into a systematic undershoot. Doubly-narrowing removes
that over-correction (7 of 9 stay within ±5% signed error) except where `recall_of_true_pattern < 1`
(§3.3).

### 2.3 Does dilution explain direction AND magnitude, candidate by candidate?

Not perfectly monotonic (`ADR-084` already disclosed `CAND-006`/`CAND-015` as visible exceptions to
a clean relationship, and that remains true here), but the pattern holds at case level, not only in
aggregate: the two highest-error whole-rule candidates (`CAND-001` at +464.6%, `CAND-005` at
+412.0%) are both in the top-3 dilution band (19.2–19.7×); the lowest-error candidate (`CAND-007` at
+6.5%) is the least-diluted (1.4×, also the only candidate whose exposed set is *majority* true
pattern — 70.5% overlap fraction). Pearson dilution-vs-error is `r≈+0.73` for whole-rule error
(matching `ADR-084`'s aggregate figure, now confirmed at case level) and, notably, **`r≈+0.77` for
the attribution-narrowed error** — i.e. `TASK-059`'s existing diagnostic's own residual *still*
correlates with dilution about as strongly as the original whole-rule error does, which is direct
case-level evidence (not previously computed) that narrowing the population alone does not fully
remove the dilution mechanism. Doubly-narrowing collapses this correlation to `r≈+0.38` — most, not
all, of the remaining dilution-correlation is closed by also recomputing the effect over the
overlap.

---

## 3. Branch 3 — the 73.6% residual, its own object

### 3.1 Reading `economic_impact.py`/`apply.py` directly

- **Estimand.** Total dollar impact over the *combined* (development + validation + future_holdout)
  observed window for the candidate's *own full exposed population* — never restricted to any
  matched pattern's true affected population. `economic_impact.py`'s own docstring states this
  explicitly ("must not be extended to narrow exposure to a ground-truth-matched subpopulation").
- **Per-record effect.** `apply.py` (`combined_stats.harm_per_booking`) — a **raw, unadjusted**
  mean-difference between the candidate's full exposed set and everyone else, recomputed fresh over
  the combined window. This is *not* the confounder-adjusted effect (`adjusted_effect`) used
  elsewhere for gating; economic impact is reported off the unadjusted quantity.
- **Denominator/scaling.** `historical_impact = per_record_value × exposed_total`, where
  `exposed_total` is the candidate's own full exposed count — the same count, not an
  overlap-restricted one. `TASK-059`'s attribution-narrowed diagnostic (§2) rescales only this
  count term, deliberately reusing the whole-rule's own diluted `per_record_effect` unchanged
  (`evaluate_benchmark.py`'s own docstring on `_attribution_narrowed_impact` confirms this is by
  design — "the same linear scaling... just over `overlap_n`"). This is exactly the mechanism §2.2
  explains and §4 confirms causally.
- **Sign handling.** Harm-signed throughout (`harm_multiplier`); a candidate whose exposed group is
  *more* profitable than its comparison would report a legitimate negative impact, not clipped.
- **Heterogeneity within the overlap population.** Neither `apply.py` nor `economic_impact.py`
  models within-population heterogeneity at all — every quantity is a simple group mean. The
  candidate's own exposed population (let alone its overlap with any true pattern) is never assumed
  or checked to be homogeneous; it is simply averaged over.
- **Representability.** The candidate's surrogate rule and the exact injected true rule are
  different rules over different (though overlapping) populations by construction — overlap
  fractions in §2.1's table range 4.4%–70.5% of the candidate's own exposed set, and recall of the
  true pattern ranges 69.4%–100%.

### 3.2 A second, smaller-magnitude defect looked for, not assumed away

Per this task's own binding instruction, narrowing improving the headline number is not itself
grounds to declare the estimator otherwise sound. §2.1's doubly-narrowed column is exactly this
check: even after correcting *both* the population-count term and the per-record-effect term to the
same overlap population, a residual remains (median 5.45%, up to 22.7% signed for individual
candidates). **This residual is not a mystery — §3.3 characterizes it directly.**

### 3.3 Characterizing the residual: it is the same mechanism, a partial-coverage sub-form

The doubly-narrowed signed error correlates strongly with `recall_of_true_pattern`
(**Pearson r≈+0.94**, computed directly from §2.1's table): every candidate with
`recall_of_true_pattern = 1.00` (`CAND-002`, `003`, `007`, `008`) has a doubly-narrowed signed error
within **±5.5%** of zero; every candidate with `recall < 1.00` (`CAND-001` 93.0%, `CAND-004` 72.5%,
`CAND-005` 85.9%, `CAND-006` 77.9%, `CAND-015` 69.4%) shows a negative signed error whose magnitude
tracks `(1 − recall)` (7%→−4.8%, 27.5%→−21.1%, 14.1%→−15.8%, 22.1%→−22.7%, 30.6%→−18.1%). This is a
**mechanical, structural consequence of the estimand's own definition**, not a new estimation
defect: `truth_impact` is the matched pattern's *entire* true economic impact, but a doubly-narrowed
estimate is scaled by `overlap_n` — the candidate's overlap with the pattern, which is only ever
`recall × pattern_affected_total`. Scaling a (locally accurate) per-record effect by less than the
full true-affected count necessarily undershoots a truth defined over the full true-affected
population, in direct proportion to the shortfall.

### 3.4 Residual classification, stated explicitly (completion criterion (b))

**The 73.6% residual is substantially the SAME mechanism as the bulk of the 219.9% error —
population/localization mismatch — encountered twice, in two different forms, not a second,
independent mechanism.** First form (already known): the candidate's exposed population is far
broader than the true pattern's affected population (dilution, §1–2, §4). Second form (newly
isolated here): even after removing dilution, the candidate's overlap with the true pattern is
often *smaller* than the true pattern's own full extent (`recall < 1`), and any estimator scaled by
that smaller overlap will structurally undershoot a truth defined over the pattern's full extent.
Both forms are population-localization phenomena, at different stages of the same underlying
question: how much of, and how precisely, a discovered surrogate rule localizes the true affected
population. No evidence was found in this branch for the kind of independent, unrelated
per-booking-estimation defect `ADR-084`'s Finding 3 flagged as a live possibility (a uniform,
dilution-unrelated bias) — the residual's own magnitude and sign are fully accounted for by
`recall_of_true_pattern` once dilution itself is controlled for (§3.3's r≈+0.94), leaving no
unexplained variance to attribute to a separate mechanism.

---

## 4. Branch 4 — synthetic controls

### 4.1 Design, derived analytically first, then checked computationally

For a rule whose diluting (non-true-pattern) exposed records are literally drawn i.i.d. from the
comparison distribution (zero incremental association with the outcome), `historical_impact =
per_record_effect × exposed_total` is **algebraically exact in expectation regardless of dilution
level** — the per-record attenuation and the count inflation cancel exactly (full derivation in the
script's own docstring). This is the **negative control**'s precise, quantitative, falsifiable
prediction — not merely "should probably be fine." Whole-rule error should instead grow with
dilution specifically when the diluting population carries its *own*, non-true-pattern association
with the outcome (a **positive control**).

### 4.2 Results (both call the real `summarize_group`/`raw_difference`/`harm_score`/
`cluster_bootstrap_replicates`/`build_economic_impact_result` functions, unmodified)

| Dilution ratio k | Dilution factor | **Negative control** whole-rule error | **Positive control** whole-rule error | Positive control oracle (overlap-conditioned) error |
|---:|---:|---:|---:|---:|
| 0 | 1.0× | +27.5% | +27.5% | +27.5% |
| 1 | 2.0× | −0.3% | +56.6% | −0.4% |
| 2 | 3.0× | −29.9% | +83.2% | −4.2% |
| 5 | 6.0× | −34.8% | +245.4% | −3.3% |
| 10 | 11.0× | +15.1% | +577.2% | −9.2% |
| 20 | 21.0× | +0.5% | +1124.1% | −6.1% |

Negative control: Pearson dilution-vs-signed-error **r≈0.07** — no trend, error bounces in a
±35% band from small-sample bootstrap noise alone, exactly as the algebraic prediction requires.
Positive control: Pearson dilution-vs-signed-error **r≈0.998** — essentially perfect linear growth,
while the overlap-conditioned oracle estimand stays within roughly ±10% throughout the same sweep
(and *improves* as k grows, since the oracle's own comparison-group estimate gets more precise with
a larger background).

### 4.3 What this establishes

The population-localization/dilution hypothesis is not merely correlated with error in the real
data (`ADR-084`'s `r≈+0.73`, reconfirmed at case level in §2.3) — it is **causally demonstrated**
here: a controlled synthetic sweep, real estimator code, one variable (the diluting population's own
association with the outcome) switched on and off, produces exactly the predicted qualitative and
quantitative behavior in both directions. Critically, the negative control also rules out a naive
"big populations are inherently bad" reading — population growth alone, without a genuine
non-true-pattern association riding along with it, does not bias this estimator. The real mechanism
is specifically **surrogate-rule confounding**: a discovered rule's condition (e.g. a discount-rate
threshold) is generically likely to carry its own, non-injected association with the outcome for the
records it admits beyond the true pattern — and `discover_candidates`'s own eligibility filter
(`_eligible` requires `harm_per_booking > 0` over the *whole* exposed set) structurally selects for
rules whose full population already shows a same-signed average harm, i.e. selects for exactly this
confounding mechanism by construction, not by accident.

---

## 5. Completion criterion — three findings, stated separately, not collapsed

**(a) For the bulk of the 219.9% error:** the first sufficient mechanism is **surrogate-rule
confounding under population dilution** — a discovered candidate's exposed population is far
broader than the true pattern's affected population (§1–2), and because the surrogate condition
that admits the extra records carries its own, non-true-pattern association with the outcome
(§4), the raw-mean-difference-times-count estimator inflates without bound as dilution grows (§4.2's
positive control, r≈0.998). This belongs to the **validation/estimator layer**
(`policy_analytics.validation.apply`'s combined-window `harm_per_booking × exposed_total`
computation, `economic_impact.py`'s contract around it) — specifically, its choice to compute the
per-record effect and the population count over the candidate's *entire* exposed set rather than
any population-aware estimand — not to discovery/search composition, which (per §1.4) contributes a
real but much smaller amplifying effect (`beam_rules_per_structure`, +33.8pp) and, via `TASK-060`'s
diversity mechanism, actually moves the number in the *opposite* direction.

**(b) The 73.6% residual, classified separately:** **the SAME mechanism, a different, partial-
coverage sub-form of it — not a different mechanism, and not several.** §3.4's r≈+0.94 between
doubly-narrowed signed error and `recall_of_true_pattern` leaves no residual variance to attribute
to an independent per-booking effect-estimation defect. `ADR-084`'s Finding 3 (a possible "smaller,
more general per-booking effect-size estimation bias") is not confirmed by this branch's
higher-resolution evidence — what looked uniform in `ADR-084`'s 9-candidate attribution-narrowed
view resolves, once the per-record effect is also recomputed over the overlap, into a clean
recall-driven structural undershoot.

**(c) The engine/config regression (branch 1):** **`beam_rules_per_structure=2` is a demonstrated
AMPLIFIER** of an already-present defect (+33.8pp in a controlled, one-axis ablation), **not the
sole CAUSE** (the defect is already present at 186–209% under every discovery configuration tested,
including the literal historical `TASK-058` configuration) **and not merely a coincidental,
non-causal correlate** (its effect is real and directionally consistent under control). The
dataset-version bump (v1.0.0→v1.1.0) **is** merely correlated, non-causal — it produces no
measurable effect. `TASK-060`'s diversity-selection mechanism is neither a cause nor a relevant
correlate of the worsening — it improves this specific metric while costing Top-10 precision. The
largest single unexplained factor in the *historical* trajectory (`TASK-058`'s reported ~37.5%
against every reconstructed configuration's ~186–209% today) remains open, with a concrete,
evidenced, unconfirmed lead pointing at validation-contract evolution rather than discovery search
config (§1.3) — disclosed as open, not resolved, given the unreachable original artifact.

---

## 6. What a follow-on fix-design task would need to cover, if opened

Not opened, scoped, or performed here, per this task's own explicit-not-in-scope clause. Named only,
per `ADR-084`'s own precedent: **"how should economic impact be estimated for a discovered, broad
surrogate rule when the true affected subpopulation is unknown"** (not "how to fix the impact
estimator," and not a switch to `TASK-059`'s diagnostic as a production metric, per this task's own
binding constraint). A future task would need to weigh, at minimum: (i) that §4.3 shows the failure
mode is specifically surrogate-rule confounding, not population size per se, so any fix concept
needs to address confounding within the exposed-but-unmatched population, not merely population size
directly; (ii) that §3.3's recall-driven undershoot means any population-aware estimand still needs
an explicit position on how to handle a candidate that only partially covers a true pattern (scale up
by an assumed/estimated recall? report a range? something else?) even after localization is
otherwise solved; (iii) `beam_rules_per_structure`'s status as a real, still-unresolved
amplifier (§1.5) is a separate, already-named, still-open config-custody question (`TASK-076`/`077`,
`ADR-070`) this task does not reopen or resolve; (iv) the open validation-contract-evolution lead
(§1.3) is worth chasing on its own before any estimator redesign, since it may be a materially
different, independent contributor whose resolution changes how much of the current ~220% actually
needs a population-aware fix at all.
