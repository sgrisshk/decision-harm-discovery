# TASK-087 — A like-with-like economic-impact calibration metric: design determination

**Status: DESIGN ONLY. No implementation.** Nothing here changes `discovery.engine`,
`policy_analytics.validation.apply`, `economic_impact.py`, any `GateId`/`GateSpec`, any threshold in
`ValidationThresholds`, or `decision-gate.md`'s metric bands. Every script cited is a diagnostic,
committed alongside its raw JSON output, exactly matching `TASK-084`/`085`'s own precedent. `CODE_
REVIEWER` must independently review this document before any implementation task opens.

**Depends on:** `TASK-085` (`CLOSED — DESIGN APPROVED`, `ADR-089`) §7 (formal `O1`/`O2`/`O3`
estimands), §8 (the benchmark comparison and metric 6's retirement), §8.3 (the starting sketch this
document investigates). `TASK-084` (`APPROVED`, `ADR-086`) Branch 4 (the dilution/confounding
mechanism metric 6's replacement must not reintroduce) and its `CODE_REVIEWER` verification.

**Determination, stated first, per this task's own instruction not to bury it:** **a working design
exists and is recommended** — an out-of-sample, per-record-rate calibration check comparing a
development(+validation)-fit effect against its own candidate-defined population's realized effect
in `future_holdout`, formalizing `TASK-085` §8.3's sketch into a testable interval-coverage check.
It clears six of the seven required checks cleanly. **Check 4 is not cleanly, structurally clean —
it carries one real, disclosed, quantified, *pre-existing* caveat** (§4 below), not a newly
introduced one, and not one this investigation found any way to remove given the current engine
architecture. Given that caveat, and given `TASK-085` §8.3's own observation that this design mostly
reconfirms a property `TASK-084` already established, **the recommendation is to adopt this design as
a form-test/regression-suite check, never as a `decision-gate.md` founder-level graded metric** — see
§8/§9.

---

## 1. The design, precisely

**Metric name (working, for this document only):** out-of-sample per-record-rate calibration for
candidate exposure (`O1`).

**Predicted side.** For a candidate's own condition mask (`rule_expr(candidate.conditions)`, exactly
`apply.py`'s `full_mask` — no new mask logic), computed over the rows in `development` ∪ `validation`
only: the raw per-record effect `harm_per_booking`, via the real, unmodified
`policy_analytics.validation.apply.split_stats`, plus a cluster bootstrap (`customer_id`,
`cluster_cells`/`cluster_bootstrap_replicates`/`percentile_ci`, the same machinery `apply.py` already
uses for `O1`'s own CI) giving a 95% interval.

**Realized side.** The same `rule_expr(candidate.conditions)` mask, computed over `future_holdout`
rows only: the realized `harm_per_booking`, via the identical `split_stats` call.

**Verdict.** `calibration_ok` = the realized point value falls inside the predicted side's bootstrap
interval. This is a direct generalization of `G10`'s own existing `min_holdout_effect_retention`
floor (`apply.py` line ~739, `retention = |holdout.harm_per_booking / dev.harm_per_booking| ≥ 0.50`)
from a single ratio threshold to a full interval-coverage test — same inputs, same splits, more
statistically honest than a fixed ratio floor.

**What this explicitly does NOT do, by design:**
- Never touches `hidden_ground_truth.json` or any pattern-membership information (Check 3, §5).
- Never compares `O1` to `O3` — both sides of the comparison are the *same* estimand (candidate
  exposure's own per-record rate), evaluated on two disjoint time windows of the *same* rule-selected
  population. This is exactly the "like-with-like" reframing `TASK-085` §8.3 named as the alternative
  to the retired metric 6's cross-estimand comparison.
- Never validates the *total* dollar figure (`per_record_value × exposed_total`) — only the
  per-record rate. §6 explains why, and names this a real, disclosed scope limitation, not an
  oversight.

**A tier-2 variant, named but not built here:** once a candidate reaches `G06`, the identical check
could instead use `adjusted_effect` (fit by `_stratified_adjustment` on `development` alone, per
`TASK-085` §7's tier-2 correction) against `future_holdout`'s own realized rate for `E_dev`'s
population definition. This document recommends starting with the tier-1 raw-rate version (simpler,
already exactly `G10`'s own existing inputs) and treats the tier-2 variant as a natural, later
extension a form-test suite could add — not a blocker to adopting tier 1.

## 2. Check 1 — identical population masks on both sides

**Interpretation, stated precisely first.** A genuinely prospective check cannot use the literal same
*rows* on both sides — "predicted" and "realized" must occupy disjoint time windows by the nature of
an out-of-sample test, exactly as `G10`'s own existing temporal-stability check already does
(development vs. validation/`future_holdout`). "Identical population mask" therefore means: the same
mask-*generating rule* (`rule_expr(candidate.conditions)`), applied consistently, filtered only by
chronological split membership — never by any other criterion, and never by ground truth.

**Code trace, confirming this holds today.** `apply.py`'s `_validate_one` (lines ~505–518) already
computes exactly this: `full_mask = frame.select(rule_expr(conditions)...)`, then for each split,
`s_mask = full_mask.filter(split_frame_mask)` — the *same* `full_mask`, sliced by split, feeding
`split_stats` once per split. `split_results["development"]`, `split_results["validation"]`, and
`split_results["future_holdout"]` are **already computed today**, by the real, unmodified pipeline,
using this exact discipline — this design's predicted/realized sides require no new mask logic, only
a new *combination* (development+validation pooled, vs. future_holdout alone) and a new *comparison
formula* (interval coverage) over quantities the pipeline already produces per split.
`discovery/engine.py`'s own `_metric` (lines 277–301) independently confirms the identical discipline
at the discovery layer (`subset = frame.filter(split_label == split)`, then the same `_rule_expr`
applied within `subset`).

**Verdict: PASSES**, cleanly, by direct code trace — not by assumption.

## 3. Check 2 — identical economic unit and time horizon

**Unit.** Both sides use `harm_per_booking` — the identical `summarize_group`/`raw_difference`/
`harm_score` computation (`apply.py` lines 294–331, `outcomes/aggregation.py`), same `OutcomeDefinition`,
same `harm_multiplier` sign convention. No unit mismatch of the kind `TASK-085` §8.1 found between
`O1` (raw) and `O3` (`hidden_ground_truth.json`'s own `realized_economic_impact`, a differently-derived
figure) — here both sides are literally the same function, called twice.

**Time horizon — the real, disclosed asymmetry.** `development` ∪ `validation` spans 18 months
(2024-01-01–2025-06-30, `TemporalSplitConfig`); `future_holdout` spans 6 months (2025-07-01–
2025-12-31). This asymmetry is **structural to any prospective check** (a "predict" window must
precede a "realize" window; they cannot be the same length by definition here, since this project's
temporal splits are already fixed at these boundaries) — but it is the reason this design is
explicitly restricted to the **per-record rate**, not the total. A rate (EUR per booking, among
records the rule selects) is not mechanically a function of window length the way a total is; a
mismatched-length total comparison (an 18-month-fit total vs. a 6-month-realized total) would
reintroduce exactly the kind of horizon mismatch `TASK-085` §8.1 flagged for `O1` vs. `O3`'s
`active_booking_months` divergence. Restricting to the rate avoids re-creating that mismatch — this
is a design choice made *because of* Check 2, not a limitation discovered by accident. §6 states the
resulting scope limitation explicitly.

**Verdict: PASSES, with the horizon asymmetry named and designed around, not hidden.**

## 4. Check 4 — no leakage from `future_holdout` into discovery, fitting, or the calibration target

This is the check this investigation spent the most effort on, and where the finding is most
nuanced — reported in full, not simplified into a clean pass or fail.

### 4.1 The predicted-side computation itself: clean, confirmed by direct trace

The predicted side (`development` ∪ `validation` `harm_per_booking`) is computed by `split_stats`
called on a frame containing **zero** `future_holdout` rows (confirmed by the script in §4.3 — the
`frame.filter(pl.col("split_label") == split)` pattern used throughout `apply.py`/`engine.py` makes
this a structural guarantee, not a probabilistic one). `_stratified_adjustment` (tier-2 variant) fits
on `dev_frame = frame.filter(split_label == "development")` alone (`apply.py` line 523) — confirmed
directly, matching `TASK-085` §7's own tier-2 correction. **No row used to form either the tier-1 or
tier-2 "prediction" is ever drawn from `future_holdout`.** On this narrow reading — does the
prediction's own arithmetic use future information — Check 4 passes cleanly.

### 4.2 A different, real question: has `future_holdout` already shaped *which candidate exists*?

Direct code trace, `discovery/engine.py`: `_temporal_consistency` (lines 410–427) computes
`_metric(frame, rule, outcome, "future_holdout")` — i.e. it reads `future_holdout`'s own sign — **for
every candidate rule in the pool being considered for top-K selection**, before `apply.py` or
`economic_impact.py` ever runs. Its output feeds `_apply_stability_credit` (line 430):
`effective_score = development_score * (1 + stability_credit_weight * temporal_consistency)`. This
`effective_score`, not the raw development score, is what `_greedy_diverse_select` actually ranks and
thresholds candidates on (via `relevance_floor_percentile`) to decide the top-K set that is ever
handed to validation. `DiscoveryConfig.stability_credit_weight` defaults to `0.5` (non-zero), and
`scripts/run_discovery.py` — the real official-run entrypoint — does not override it (confirmed by
direct read: `config = DiscoveryConfig(seed=..., max_feature_identity_fraction=...)`, no `stability_
credit_weight` argument). **This is a real, unconditional, currently-shipped channel by which
`future_holdout` information enters the pipeline before any candidate is selected to be graded at
all** — not a hypothetical, and not "merely unused by convention," per this check's own binding
language.

### 4.3 Empirical test: does this channel actually change which candidates exist?

`scripts/diagnose_task087_check4_future_holdout_leakage.py` (committed, raw output
`docs/benchmark/task-087-check4-future-holdout-leakage-raw.json`) ran the real, unmodified
`discover_candidates` twice on the real `travel-bookings-analytical-v1.1.0` dataset, seed `1729`,
varying only `stability_credit_weight` (`0.5`, the real shipped default, vs. `0.0`, which
`_apply_stability_credit` reduces to `effective_score == development_score` unconditionally — a
provably `future_holdout`-blind-for-selection control). Result: **the resulting top-15 candidate
rule sets are byte-identical** (`top_k_set_only_in_default_count = 0`,
`top_k_set_only_in_zero_weight_count = 0`). At this dataset/seed/`top_k`, the channel exists in code
but has **zero measured effect** on which candidates are ever selected.

### 4.4 What this means, stated honestly, not rounded in either direction

- This is **not** evidence the channel can never matter — a null result at one seed/dataset/`top_k`
  does not retroactively prove the architecture is leakage-free; a future run, a different dataset, or
  a candidate pool with more genuinely mixed-sign later-split behavior near the `relevance_floor_
  percentile` cutoff could see this channel actually reorder or exclude a candidate. This
  investigation did not test candidate rank *order* within the top-15 (only set membership), nor did
  it characterize how many pool candidates have `temporal_consistency < 1.0` in this run — both would
  sharpen, not change, this disclosed uncertainty.
- This is **also not** a defect this design introduces. `future_holdout`'s use in
  `stability_credit_weight` is an existing, already-`ADR-039`-reviewed, currently-shipped engine
  behavior, not something newly discovered by or attributable to this design. **`G10`'s own existing
  temporal-stability gate already carries the identical property** — it, too, compares `development`
  to `future_holdout`, using inputs from the same pipeline stage that `stability_credit_weight`
  already consulted before that same candidate was ever selected. This design does not create a new
  category of contamination; it inherits one this project already accepted when it shipped `G10` and
  `stability_credit_weight` together.
- Given (a) the predicted side's own arithmetic is confirmed clean (§4.1), (b) the selection-stage
  channel is real but empirically null on the one real run tested (§4.3), and (c) an identical
  property is already load-bearing in an approved, shipped gate (`G10`), this document's
  determination is: **Check 4 is not cleanly, architecturally guaranteed clean, but it is not a
  demonstrated, material violation either** — a disclosed, quantified, pre-existing caveat, not a
  reason to withhold this design that a stricter standard did not also apply to withhold `G10`.

**Binding recommendation attached to this caveat, not a hand-wave:** any future change to
`stability_credit_weight`, `relevance_floor_percentile`, or any other discovery-selection mechanism
that reads `validation`/`future_holdout` must re-run `scripts/diagnose_task087_check4_future_holdout_
leakage.py` (or an equivalent check) before this calibration design continues to be trusted — exactly
the kind of binding-to-configuration discipline `TASK-076`/`077`/`ADR-070` already established for
`beam_rules_per_structure`. This document does not resolve that broader config-custody question (out
of scope, `TASK-076`/`077`'s own territory) — it only names the specific new dependency.

**Verdict: PASSES for the predicted-side computation itself; CONDITIONAL, with one real, disclosed,
pre-existing, empirically-quantified caveat, for candidate selection.** This is the single largest
factor behind this document's scope recommendation (§8) — not a reason to decline the design
outright.

## 5. Check 3 — no ground-truth overlap or narrowing anywhere

Neither side of the comparison (§1) opens `hidden_ground_truth.json`, reads `affected_booking_ids`,
or narrows `E` by any pattern-membership criterion. Both sides are functions only of
`rule_expr(candidate.conditions)` and `split_label`. This is verified by direct inspection of §1's
own formula — no code path exists for it to touch ground truth, structurally, not merely by
intention. The `scripts/diagnose_task087_check5_7_calibration_adversarial.py` cases (§7) use a
synthetic "true mechanism" column *only* to interpret and label the constructed cases for this
document's own readers — the metric computation itself (`_calibration_check`) never reads that
column, exactly mirroring how `review_task085_check2_metric6_adversarial.py` used ground truth only
for case construction/interpretation, never inside the tested formula.

**Verdict: PASSES, cleanly**, by construction and direct inspection — the prohibited path named in
`ADR-087`/`ADR-089` has no entry point here.

## 6. Check 6 — calibration error kept separate from candidate-localization quality

This design answers exactly one question: **is the per-record rate this rule's own condition implies,
estimated from `development`(+`validation`), a good predictor of the same rule's own realized rate in
`future_holdout`?** It never asks, and has no computational path to answer, "does this rule's
population look like the true mechanism's population" — that is `O2`'s question (`TASK-085` §4,
established not achievable from candidate-internal information alone), out of scope here by
construction, not merely by disclaimer. §7 (Check 7) demonstrates this separation empirically, not
just asserts it: Case C (zero ground-truth overlap, well-calibrated) and Case D (90% overlap, poorly
calibrated) show the verdict tracks calibration, never overlap.

**A related, load-bearing scope limitation, disclosed here rather than left implicit.** §3 restricts
this design to the per-record **rate**, never the **total** dollar figure `historical_value =
per_record_value × exposed_total` that is actually what `O1` reports and what `decision-gate.md`'s
retired metric 6 graded. `TASK-084` Branch 4's own positive control (`r≈0.998`) showed the *count*
term (`exposed_total`, driven by dilution/surrogate-rule confounding) is the dominant driver of the
old metric's error — and this design's rate-only scope means **it does not, and structurally cannot,
validate the part of `O1` `TASK-084` found most failure-prone.** This is not an oversight: a
total-dollar prospective check would need to know `future_holdout`'s own future population size in
advance, which is not "information available at prediction time" by any reading — attempting it would
either (a) smuggle in the real future count (violating the central criterion outright) or (b) require
forecasting the future population size, a materially different, unbuilt statistical problem this
document does not attempt. **This design validates `O1`'s per-record rate term's own out-of-sample
stability; it says nothing about whether `O1`'s reported total will hold up, and must never be
represented as doing so.**

**Verdict: PASSES for the separation this check actually asks about (calibration vs. localization);
a real, disclosed, adjacent scope limitation (rate-only, not total) is named for the record.**

## 7. Check 5 and Check 7 — population drift and adversarial cases

`scripts/diagnose_task087_check5_7_calibration_adversarial.py` (committed, raw output
`docs/benchmark/task-087-check5-7-calibration-adversarial-raw.json`), calling the real, unmodified
`split_stats`/`cluster_cells`/`cluster_bootstrap_replicates`/`percentile_ci`, composed with §1's own
comparison formula (defined and tested in this script, never imported from a gate — no such gate
exists):

**Check 7 — Case C (well-calibrated despite zero ground-truth overlap).** A candidate rule `E` with
zero rows shared with a synthetic true mechanism `A` (present in the frame, symmetrically in both
windows, specifically so its own presence does not asymmetrically bias one window's comparison mean —
the isolation-contamination pitfall `review_task085_check2_metric6_adversarial.py`'s Case B docstring
already named, and this script's first draft actually hit before being corrected, §7's own commit
history). `E`'s own effect is a genuine, exogenous, stable −300 EUR association, present identically
in both windows. Result: predicted rate 238.2 EUR, 95% CI `[228.5, 248.2]`, realized rate 237.1 EUR —
**`calibration_ok = True`**, independent of `E`'s zero overlap with `A`.

**Check 7 — Case D (poorly calibrated despite 90% ground-truth overlap).** A candidate rule `E`
overlapping `A` at 90% (a good localization by construction), where the true mechanism itself
genuinely ends between windows (injected only in the predict window, organically absent — reverted to
baseline — in the realize window: a real regime shift, zero estimator flaw). Result: predicted rate
700.8 EUR, 95% CI `[697.9, 703.7]`, realized rate 0.6 EUR — **`calibration_ok = False`**, independent
of `E`'s 90% overlap with `A`.

**Both cases pass** (`check7_metric_correctly_distinguishes_calibration_independent_of_overlap:
true`): the design's verdict tracks calibration quality, not ground-truth overlap — precisely the
property `ADR-089`'s own Check 2 showed the old metric 6 could not provide.

**Check 5 — Case E (population drift, rate stable, size shrinks).** The candidate rule's own realized
population shrinks to 30% of the predict-window reference count (`realized_n_exposed=180` vs.
`predicted_n_exposed_reference=600`) while the per-record rate stays genuinely stable. Result:
predicted rate 401.4 EUR, 95% CI `[399.7, 403.0]`, realized rate 399.9 EUR — **`calibration_ok =
True`**, with `population_size_ratio_realize_over_predict = 0.30` surfaced as a separate, explicit
diagnostic. **Defined behavior under population drift, stated plainly:** the coverage verdict is a
statement about the per-record rate alone; population-size drift is reported alongside it, never
blended into it. A candidate whose population genuinely shrinks or grows between windows still gets a
`calibration_ok` verdict purely about whether its rate held up — a reader must consult the size-ratio
diagnostic separately to learn whether the *population itself* also drifted, and must not infer
anything about the *total* dollar figure from `calibration_ok` alone (§6).

**Verdict: Check 5 PASSES (explicit, tested, disclosed behavior); Check 7 PASSES (both adversarial
cases constructible and correctly resolved, independent of ground-truth overlap).**

## 8. Scope questions

### 8.1 Decision-gate slot vs. form-test suite — recommendation: form-test suite, not a graded metric

**Recommendation: this design should be built as a form-test/regression-suite check (matching `test_
g05_multiplicity_fix.py`/`test_g12_robustness_fix.py`'s own posture — neutral, synthetic, invented
data, proving a property of the *estimator*, not grading any specific real candidate), never adopted
into `decision-gate.md`'s founder-level graded-metric slot.** Three independent reasons, not one:

1. **`TASK-085` §8.3's own observation, now directly confirmed rather than merely restated.** This
   design answers "is `O1`'s estimator well-calibrated for its own stated target" — a question §4.1
   of this document shows is **already, largely, answered**: `TASK-084`'s `CODE_REVIEWER` verification
   (Check 3, `ADR-086`) already independently confirmed the estimator computes exactly `O1`'s own
   population correctly; this design's own Check 4 investigation (§4.1) re-confirms the predicted-side
   computation is architecturally clean. A form test that reconfirms an already-established estimator
   property, on invented synthetic data, is exactly the `G05`/`G12` pattern — not a founder go/no-go
   signal.
2. **Check 4's disclosed caveat (§4) is not the standard a founder-level gate should be built on
   without further work.** A metric whose comparator-selection channel carries even a disclosed,
   currently-null, but not structurally eliminated leakage risk should not silently become one of the
   handful of numbers that decides STRONG/PROMISING/WEAK/FAILED for the whole product. A regression
   suite, re-run on every relevant engine change (§4.4's own binding recommendation), is the right
   home for a check still carrying an open, monitored dependency.
3. **A rate-only scope cannot honestly replace a total-dollar decision-gate metric.** §6 disclosed
   that this design validates `O1`'s per-record rate, never its total — precisely the part of the old
   metric 6 `TASK-084` Branch 4 showed dominates real-world error. Slotting a rate-only calibration
   check into `decision-gate.md`'s metric-6 position, under any name, would silently narrow what the
   gate actually protects against without saying so — exactly the kind of "quietly reintroduces a
   [gap] under a new name" outcome this task's own boundary condition warns against.

**Concretely:** `decision-gate.md` should carry **five graded metrics**, not six — metric 6's numbered
slot retired outright (already `TASK-085` §8.4's own disposition; this document does not reopen that),
with no replacement metric occupying it. This design's calibration check belongs in a new test file
(e.g. `tests/analytics/test_o1_temporal_calibration.py`, named for a later implementation task to
build, not this one), synthetic and neutral in the `G05`/`G12` tradition, run as part of this
project's regular test suite — never as a `TASK-028`/`evaluate_benchmark.py` benchmark-comparison
number.

### 8.2 `O2`'s tier-3 "accurately predicts `O3`" comparison (§8.3 question 2)

Unchanged from `TASK-085`'s own disclosure: this comparison requires a level 4–5 candidate to exist
first (a design-identified population `A` that `O2` is computed over, per `TASK-085` §5.2's tier 3),
and this project has never had one (`validation-contract.md` §1's own standing ceiling: observational
data caps this product at level 3). **Nothing in this investigation changes that.** What it would
need, concretely, once a level 4–5 candidate exists: the identical prospective-comparator discipline
this document just built for `O1` (a `development`-fit `O2` estimate, checked against a genuinely
later-arriving realization on the *design-identified* population `A`, not `E`) — likely a
`G13`/`G14`-scoped backtest extension (`policy_analytics.backtest`, already `future_holdout`-scoped
per its own module docstring), not a new mechanism. This remains a **future task's** scope, opened
only once a level 4–5 candidate first exists, exactly as `TASK-085` §8.3 already said.

### 8.3 Five metrics, not a differently-shaped sixth

Given §8.1's three independent reasons, this document's recommendation is unambiguous: **five graded
metrics, not a sixth of any shape.** A differently-shaped sixth metric was considered and rejected —
not because no design exists (§1–§7 show one does, for the form-test-suite home), but because the
*only* design this investigation found that clears all seven checks acceptably (with Check 4's
disclosed, monitored caveat) is scoped, by its own Check 6/Check 2 findings, to a narrower question
(rate calibration, not total-dollar accuracy) than a founder-level gate metric should be graded on.

## 9. Acceptance-criteria checklist

| Required check (`TASK-087`) | Verdict | Evidence |
|---|---|---|
| 1. Identical population masks on both sides | PASSES | §2 — code trace, `apply.py` lines 505–518, `engine.py` `_metric` |
| 2. Identical economic unit and time horizon | PASSES, asymmetry named and designed around | §3 — rate-only scope specifically avoids a horizon-mismatch reintroduction |
| 3. No ground-truth overlap or narrowing | PASSES | §5 — no code path touches `hidden_ground_truth.json` |
| 4. No leakage from `future_holdout` | CONDITIONAL — predicted side clean; selection-stage caveat disclosed, quantified, pre-existing (shared with `G10`), empirically null on the one real run tested | §4, `scripts/diagnose_task087_check4_future_holdout_leakage.py` |
| 5. Defined behavior under population drift | PASSES | §7 Case E — rate-only verdict, size-ratio surfaced separately |
| 6. Calibration kept separate from localization quality | PASSES; rate-vs-total scope limitation disclosed | §6, §7 Cases C/D |
| 7. Synthetic adversarial cases (Case A/B analog) | PASSES, both cases constructible and correctly resolved | §7, `scripts/diagnose_task087_check5_7_calibration_adversarial.py` |
| Explicit "no valid replacement" boundary respected | Not invoked — a design meeting the checks (with one disclosed caveat) was found | This document's own determination, §0 |
| Scope questions resolved, not assumed | §8 | Form-test suite, not decision-gate slot; five metrics; `O2`/tier-3 deferred to a future task |
| Real, disclosed recommendation (not a survey) | Given | §0, §8 |
| Design-only; no estimator/engine/gate change | Confirmed throughout | Banner; every diagnostic script is read-only against shipped code, using only existing `DiscoveryConfig` overrides (matching `TASK-084`'s own ablation discipline) |

## 10. What this document does not do

- Does not change `apply.py`, `economic_impact.py`, `discovery.engine`, any `GateId`/`GateSpec`, any
  `ValidationThresholds` value, or `decision-gate.md`'s text or bands.
- Does not build the recommended form-test file (`tests/analytics/test_o1_temporal_calibration.py`)
  — a distinct, later implementation task, per this project's decide/implement separation
  (`TASK-076`/`077`'s own precedent).
- Does not resolve the `stability_credit_weight` config-custody question this investigation surfaced
  (§4) — names it as a new, binding dependency for a future task, matching `TASK-076`/`077`/`ADR-070`.
- Does not touch `TASK-069`–`086` or any existing `ADR`.
- Does not reopen `TASK-085`'s own metric-6-retirement disposition (§8.4 there stands; this document's
  §8.3 only resolves what fills — or does not fill — the resulting slot).
