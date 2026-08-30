# TASK-084 — `CODE_REVIEWER` independent adversarial review (`ADR-086`)

**Verdict: APPROVED**, per `ADR-086`'s precisely-scoped approval criterion, with two disclosed
refinements (neither is a material, independent impact-estimation defect) recorded in §2 and §4
below. No estimator, discovery-engine, gate, or metric-6 definition was changed by this review.
Every check below uses the real, unmodified `policy_analytics` code; independent verification
scripts (new DGPs, new parameters, new seeds — never importing or reusing TASK-084's own diagnostic
scripts) are committed alongside their raw output, in addition to bit-exact reruns of TASK-084's own
three diagnostic scripts.

Raw output of every independent script this review ran:
`docs/benchmark/task-084-review-check1-independent-controls-raw.json`,
`docs/benchmark/task-084-review-check2-counterexample-raw.json`,
`docs/benchmark/task-084-review-check4-alt-order-raw.json`. Scripts:
`scripts/review_task084_check1_independent_controls.py`,
`scripts/review_task084_check2_counterexample.py`,
`scripts/review_task084_check4_alt_order_ablation.py`.

---

## Check 1 — independently reproduce the causal controls' directional claim (not just r)

**Verdict: PASSES, cleanly.**

TASK-084's own `scripts/diagnose_task084_branch4_controls.py` was rerun unmodified — output is
bit-for-bit identical to the committed `task-084-branch4-controls-raw.json` (deterministic seeding
confirmed). Positive-control sweep is monotonically increasing point-to-point (+27.5% → +56.6% →
+83.2% → +245.4% → +577.2% → +1124.1%); negative control bounces in a ±35pp band with no trend
(r≈0.07).

Beyond rerunning the existing script, this review built a **fully independent** control (different
DGP parameters — `N_BACKGROUND=4000` vs 6000, `N_TRUE=150` vs 200, `TRUE_HARM=55` vs 80,
`CONFOUND_C=22` vs 45 — a finer, non-matching dilution grid `{0,1,2,3,4,6,8,12,16,24}` vs
`{0,1,2,5,10,20}`, and 5 independent seeds averaged per point rather than one draw), calling the
same real `summarize_group`/`raw_difference`/`harm_score`/`cluster_cells`/
`cluster_bootstrap_replicates`/`percentile_ci`/`build_economic_impact_result` functions. Result:

- Positive control: **9/9 monotonically increasing steps** across the 10-point grid, `r≈0.9996`.
- Negative control: **5/9 increasing steps** (indistinguishable from a random walk), `r≈−0.40` (no
  trend; sign itself is unstable across an independent parameterization, which is the correct
  behavior for a true null).

This independently confirms the report's directional claim at the level `ADR-086` actually asks
for — genuine point-to-point monotonicity under a real, distinct construction, not merely a
correlation coefficient computed once.

---

## Check 2 — genuine attempt to break "the residual is the same mechanism"

**Verdict: PASSES, with one disclosed methodological limitation surfaced (not a demonstrated
estimator defect).**

`scripts/diagnose_task084_branch2_3_error_decomposition.py` was rerun unmodified (bit-identical to
the committed JSON: median 219.9% → 73.6% → 5.45%, r≈0.73/0.77/0.38 dilution-vs-error at each
stage). The per-candidate case table, the 9/9 whole-rule-overestimate / 9/9 attribution-narrowed
-underestimate sign pattern, and the doubly-narrowed vs. `recall_of_true_pattern` correlation were
all independently recomputed directly from `task-084-branch2-3-error-decomposition-raw.json` with a
hand-written Pearson implementation (not the script's own): **r≈0.935** between doubly-narrowed
signed error and `recall_of_true_pattern` — matches the report's r≈0.94, confirmed independently.
Note `r²≈0.87–0.88`, not 1.0 — about 12% of variance is not accounted for by recall alone. The
report's §3.4/§5(b) language ("leaving no unexplained variance to attribute to a separate
mechanism") slightly overstates the fit; the correlation is genuinely strong but not exact. This is
a precision note on the report's wording, not a finding that changes the verdict.

**The synthetic counterexample this check specifically requires** (`scripts/
review_task084_check2_counterexample.py`): built a DGP with **zero real surrogate-rule confounding**
(diluting records drawn i.i.d. with the pure background, `confound_c=0`) and `recall=0.65`, then
injected an **independent per-record measurement bias** (`BUG_DELTA=25` EUR, ~36% of the true
per-record effect) applied uniformly to every record the candidate's rule admits — both the true-
overlap records and the diluting records — representing a hypothetical estimator/pipeline defect
unrelated to dilution-confounding as a mechanism. Result, real estimator code, dilution ratio 0→20:

| k | whole-rule signed error | attribution-narrowed | **doubly-narrowed** |
|---:|---:|---:|---:|
| 0 | −12.3% | −12.8% | **−12.3%** |
| 2 | +32.0% | −56.1% | **−8.3%** |
| 5 | +92.8% | −67.8% | **−10.3%** |
| 10 | +206.6% | −72.1% | **−16.3%** |
| 20 | +435.3% | −74.6% | **−21.4%** |

**This is the counterexample the check asked for.** A genuinely independent, dilution-unrelated
per-record bug — present at ~36% of the true effect's magnitude — produces a doubly-narrowed
residual that stays small (roughly −8% to −21%) across a 20× dilution sweep, the same qualitative
shape (small, roughly stable/mildly growing) as the real data's 5.45% median. **The doubly-narrowed
diagnostic, by its own construction, cannot distinguish "population mismatch is the whole story"
from "an independent per-record bug that happens to apply broadly across whatever population the
candidate's rule admits."** Mechanically: any bias broadly present across the exposed set gets
divided down proportionally to `overlap_n / exposed_total` (the same ratio dilution itself shrinks
by) once you narrow to the overlap — this is a **structural blind spot of the diagnostic design**,
not specific to real confounding.

This is a real, disclosed limitation of the diagnostic **methodology**, but it is not, by itself,
evidence that such a bug **exists** in the real code. Direct reading of `apply.py`'s `split_stats`/
`summarize_group`/`raw_difference`/`harm_score` (§3 below) shows a plain, symmetric raw-mean-
difference computation with no hidden multiplicative or unit-conversion step that would produce a
bug of this shape — and this review found no affirmative evidence of one. Two other classes of
hypothetical independent defect were checked analytically and do **not** get hidden by narrowing: a
purely multiplicative formula bug (would show the same % bias at all three stages) and a fixed-
dollar (N-independent) additive bug (becomes proportionally **more** visible after narrowing, not
less, since the doubly-narrowed truth denominator is much smaller). Given the small, well-explained
doubly-narrowed residual and no evidence from direct code reading of a bug shaped like the one
counterexample that *would* hide, this review does not treat this as a material, independent
estimator defect — but the report's certainty language in §3.4/§5(b) should be read as "no evidence
found and the residual is small," not "definitively ruled out," and future reviewers relying on the
doubly-narrowed diagnostic alone should know this limit.

---

## Check 3 — estimator defect vs. estimand/population-target mismatch

**Verdict: the report's framing holds, independently confirmed by two sources it did not itself
cite.**

Direct reading of `apply.py` (lines ~857–913): `combined_mask = full_mask`, and `full_mask =
frame.select(rule_expr(conditions).alias("m"))["m"]` (line 509) — i.e. the estimator's `exposed`
population is **exactly** the candidate rule's own condition applied to the whole dataset, no
narrowing, no ground truth involved. `per_record_value = combined_stats.harm_per_booking` (a plain
`summarize_group`/`raw_difference`/`harm_score` mean-difference — `outcomes/aggregation.py` lines
42–122, read directly, confirmed to be a simple, symmetric, unbiased-by-construction group-mean
computation) and `historical_value = per_record_value * exposed_total`. This is arithmetically
correct **for the population the candidate rule itself selects** — there is no bug in this
computation relative to its own definition.

Independent confirmation the report did not cite: `docs/analytics/validation-contract.md` §8
("Economic impact") states the contract's own definition explicitly: impact is "affected records in
the observed window" × "per-record effect," and "at levels 1–3, impact is stated as *exposure* —
value at stake in these records — not as savings." **"These records" is the candidate's own exposed
set, by the contract's own words** — the production code is doing precisely what its governing
contract specifies. `economic_impact.py`'s own docstring (line 12–14, read directly) states the
same: "must not be extended to narrow exposure to a ground-truth-matched subpopulation." The
mismatch is entirely in `scripts/evaluate_benchmark.py`'s benchmark-only comparison of this quantity
against the *hidden true pattern's* impact — a different population, only knowable via ground truth
that production code never sees. **This is squarely an estimand/population-target mismatch between
what the estimator honestly reports and what the benchmark compares it against, not an ordinary
statistical bug in the estimator's own arithmetic.** `_eligible`'s `harm_per_booking > 0` requirement
(`discovery/engine.py` line 324-330) was also confirmed directly: discovery structurally selects for
rules whose *whole* exposed population already shows same-signed harm, supporting the report's
"selects for confounding by construction" claim.

One nuance flagged for completeness, not disputed: `apply.py` reports the **raw, unadjusted**
`harm_per_booking`, not `adjusted_effect` (the confounder-adjusted quantity computed elsewhere for
gating). This is a genuine methodology choice, disclosed by the report (§3.1). Whether raw-vs-
adjusted contributes materially within the true-overlap population specifically is bounded by the
same evidence Check 2 examined (doubly-narrowed median 5.45%) — small, and not distinguishable from
recall-driven undershoot with the data available.

---

## Check 4 — independently reproduce the regression decomposition

**Verdict: PASSES, with one genuine refinement this review's own alternate-order ablation
surfaced.**

`scripts/diagnose_task084_branch1_engine_regression.py` was rerun unmodified — bit-identical to the
committed JSON for all four configs (A/B: 209.4%, C: 186.1%, D: 219.9%). Every `DiscoveryConfig`
field override cited as "reproduces vX.Y.Z exactly" was checked directly against `engine.py`'s own
docstrings (lines 82–211) and confirmed accurate word-for-word: `beam_rules_per_structure=0`
reproduces v0.4.1's score-only beam; `diversity_discount_weight=0.0` reproduces v0.2.0's selection
sequence; `stability_credit_weight=0.0` reproduces v0.3.1; `relevance_floor_percentile=1.0`+
`stability_credit_weight=0.0` reproduces v0.3.1/v0.4.0; `max_feature_identity_fraction=1.0`
(current default) never binds, reproducing v0.5.0. `git diff` across every TASK-084 commit
(`5b85460^..9b9e69b`) confirms **zero changes** to any file under `packages/` — only `TASKS.md`,
`DECISIONS.md`, new `docs/benchmark/*.json|.md`, and new `scripts/diagnose_task084_*.py` — directly
confirming the "no estimator/discovery/gate/threshold touched" claim, not merely trusting the
report's own assertion.

**Independent alternate-order ablation** (`scripts/review_task084_check4_alt_order_ablation.py`):
TASK-084's own path adds `beam_rules_per_structure=2` **last** (C→D, with `TASK-060` diversity
already on). This review instead added `beam_rules_per_structure=2` **directly to config A/B**
(diversity still off) — configs E/F. Result: **median impact error is bit-identical to A/B (209.4%
exactly), and Top-10 precision, attribution-narrowed median all match A/B exactly too.**
`beam_rules_per_structure=2` has **zero measurable effect when `TASK-060`'s diversity mechanism is
off** — its entire +33.8pp amplifying effect is conditional on diversity-based selection being
active. Mechanistically plausible: `beam_rules_per_structure` only *retains* extra, lower-scoring
structurally-distinct rules during beam expansion; under pure score-order top-K selection (diversity
off) those rules still need to out-score the top-15 cut to be reported, which structurally-inferior
retained rules generally do not — so they never surface. Under diversity-discounted selection, the
same retained low-overlap rules *can* fill slots the discount opens up.

This does **not** contradict the report — it never claimed `beam_rules_per_structure` has an
unconditional, diversity-independent effect, only tested and characterized the C→D transition, which
this review reproduces exactly. But it **refines** the "amplifier" characterization: precisely
stated, `beam_rules_per_structure=2` amplifies metric 6's error **specifically through interaction
with `TASK-060`'s diversity-selection mechanism**, not as an independent property of beam retention
alone. This refinement should inform `TASK-076`/`TASK-077`'s already-open config-custody work (an
interaction, not just a standalone flagged default) but does not change branch 1's cause/amplifier/
correlated three-way classification, which this review confirms holds for the actual official
configuration path.

**No "revert to old config" conclusion** appears anywhere in the report (re-read in full to confirm)
and none is drawn here.

---

## Check 5 — the TASK-058 historical discrepancy (~37.5% vs. 209.4%)

**Verdict: appropriately bounded; independently spot-checked, not resolved (as the report itself
says).**

Cross-checked directly against `TASKS.md`'s own `TASK-058` entry (lines 1577–1642, not the report's
paraphrase): confirms the real historical numbers cited (37.5% median, dropped from 204%, PROMISING
band) and the two literal new candidate conditions (`CAND-012`, `CAND-014`) the report's §1.1
fidelity check relies on. Independently recomputed from the raw JSON: config A's 12 matched
candidates, sorted, median of the 6th/7th values = (1.9892+2.1993)/2 = 2.0943 → 209.4%, confirming
the reported figure is a real computation over real data, not asserted. `CAND-006`'s individual
error, read directly from `task-084-branch1-engine-regression-raw.json`, is `0.37457...` — matching
the "37.5% to three significant figures" claim exactly.

The report's own treatment already satisfies `ADR-086`'s bounding requirement: the validation-
contract-evolution lead is stated as "plausible," cites specific, dated, real ADRs (`ADR-036`/`042`,
`ADR-064`, `TASK-081`) that genuinely postdate `TASK-058`, and is explicitly labeled "not resolved,"
"named, not asserted." It is not used anywhere to refute the current 219.9%/73.6%/5.45% forensic
chain. This review did not find a way to resolve the gap further given the same missing
`task-058-remediation-20260817-001` frozen artifact — consistent with the report's own disclosed
limitation. Left unexplained, as required.

---

## Overall verdict

**APPROVED**, per `ADR-086`'s standard: after a genuine, multi-angle attempt at refutation
(independent DGPs, independent seeds/parameters, a purpose-built synthetic counterexample, an
alternate ablation order, direct reading of both the estimator code and its governing contract), the
bulk of metric 6's error is explained by a population/estimand mismatch between the candidate's own
broad surrogate-admitted population and the true pattern's population, and — after controlling for
both population count and per-record effect within the true overlap — no material, independent
impact-estimation defect was found to remain. Two refinements are recorded (Check 2's diagnostic
blind-spot disclosure; Check 4's diversity-interaction nuance on `beam_rules_per_structure`) — neither
rises to a demonstrated, independent estimator defect, and neither requires revision of the report's
completion-criterion findings (a)/(b)/(c). No fix or design task is opened by this review, per its
own mandate.
