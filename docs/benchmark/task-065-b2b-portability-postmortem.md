# TASK-065 b2b_sales/comparable portability postmortem

**Run:** `task-065-b2b-comparable-20260822-001`
**Author:** A freshly-spawned Statistics session, produced under `ADR-051`/`ADR-052`'s independent
post-recusal review chain, separate from and later than the `TASK-065-INDEPENDENT-EVALUATOR` who
produced the frozen artifacts this document analyzes.
**Status:** Read-only postmortem. No production code, threshold, matching logic, or frozen
artifact was changed to produce this document.
**Companion document:** `docs/benchmark/task-065-b2b-portability-report.md` (the original,
shorter closing report). This document goes deeper into the same frozen artifacts; it does not
supersede the verdict recorded there, and neither document is edited to contradict the other.

## 0. Custody and eligibility declaration

`DECISIONS.md` ADR-048 records that an earlier Statistics session opened
`b2b_sales/comparable/evaluation/hidden_ground_truth.json` before `TASK-065`'s own discovery run
had happened, and recuses "the ADR-048 Statistics session and any continuation, fork, or actor
seeded with its exposed context" from evidence grading and interpretation of this specific result,
permanently (`ADR-051`, reinforced by `ADR-052` and the governance addendum in `memory/HANDOFFS.md`
HANDOFF-067).

This session was spawned fresh for this postmortem task, with no conversation history prior to this
task, no context inherited from any prior session (contaminated or otherwise), and no memory of any
prior exposure to `b2b_sales` hidden ground truth. It took no part in `b2b_sales` discovery,
candidate generation, candidate selection, or the earlier `TASK-065-INDEPENDENT-EVALUATOR` run that
produced the frozen `TASK-019`/`TASK-028` artifacts this postmortem reads. It did not open
`synthetic_data_domains/b2b_sales/comparable/evaluation/hidden_ground_truth.json` or any other
domain's `hidden_ground_truth.json` at any point while producing this document — every claim below
is derived from already-frozen, already-published JSON artifacts and already-published documents
named in `engineering rules`'s required-reading list, `docs/benchmark/task-065-b2b-portability-report.md`,
and public analytical-dataset manifests. Where a claim would require opening hidden ground truth to
verify (for example, confirming *which* public pattern description in
`docs/benchmark/multi-domain-benchmarks.md` corresponds to which `Bxx` identifier, or diagnosing
*why* a specific pattern's true mechanism produces the effect it does), this document says so
explicitly and stops short of the claim, rather than inferring it.

This is exactly the fresh, independent identity `ADR-051`'s custody chain requires for interpreting
this result, and this document is scoped as analysis/interpretation of an already-closed,
already-frozen cycle — not a new validation or evaluation run, and not a continuation of `TASK-065`
itself.

## 1. Frozen inputs read for this postmortem

- `artifacts/blind/task-065-b2b-comparable-20260822-001.candidates.json` (SHA-256
  `ec3b1c17c9826724dfaa6adec1a1db431768bad772b228d33cf906be6ab49bcc`, per `memory/HANDOFFS.md`
  HANDOFF-067's `CUSTODY_VERIFIED` record) and its sibling public artifacts
  (`.discovery_metrics.json`, `.run_report.md`, `.receipt.json`, `.hashes.json`).
- `artifacts/validation/task-019-task-065-b2b-comparable-20260822-001.json` (SHA-256
  `873db1f40a4c35ef693f8195dd2cc046164847c803f60c7de85112a27bf69f3c`).
- `artifacts/evaluation/task-028-task-065-b2b-comparable-20260822-001.json` (SHA-256
  `02ad8ca8996cd411cc3d86aa8ce6db41243ac55f456c2b07f6e5cbb0600ffca1`).
- `synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0/manifest.json`,
  `split_manifest.json`, `missingness.json` (public analytical-dataset artifacts).
- `synthetic_data/analytical/travel-bookings-analytical-v1.1.0/manifest.json`,
  `split_manifest.json` (public, for the domain-contract comparison in §3).
- `docs/benchmark/multi-domain-benchmarks.md` §"Domain 5: B2B sales pipeline" (already-published
  design documentation, not hidden ground truth).
- `docs/analytics/validation-contract.md` v1.2.0, `docs/benchmark/decision-gate.md`,
  `docs/benchmark/blind-benchmark-protocol.md`.
- `DECISIONS.md` ADR-007, ADR-008, ADR-014/015, ADR-023–ADR-025, ADR-035–ADR-053; `TASKS.md`
  TASK-019, TASK-028, TASK-060–TASK-066; `memory/HANDOFFS.md` HANDOFF-052–HANDOFF-068;
  `memory/CURRENT_STATE.md`.
- Filesystem existence checks only (no file contents opened) for
  `synthetic_data_domains/<domain>/comparable/evaluation/hidden_ground_truth.json` across all six
  `TASK-061` domains, for §6.

`packages/analytics/src/policy_analytics/validation/contract.py`'s `ValidationThresholds` defaults
(`max_adjusted_attenuation = 0.50`, `min_e_value = 1.50`, `min_confounder_stratum_coverage = 0.50`,
`fdr_alpha = 0.10`, `min_exposed_records = 50`) were read to interpret gate results; no threshold
was changed.

## 2. Metric-by-metric deep dive

### 2.1 Top-10 precision — 90% (9/10)

`artifacts/evaluation/task-028-task-065-b2b-comparable-20260822-001.json`
`metrics.top_k_precision.value = 0.9`, `true_pattern_count = 9`, over
`top_k_candidate_ids = [CAND-001, CAND-002, CAND-003, CAND-005, CAND-004, CAND-007, CAND-009,
CAND-011, CAND-012, CAND-008]`. Only `CAND-010` (matches no true pattern and no trap; per
`candidate_scores`, `is_true_pattern=false`, `is_trap=true`, matching `BT02`) is outside the
"true pattern" count in the top 10. Candidate-level precision is high: the search and ranking
correctly separated real statistical structure from pure noise at the top of the ranked list, at
the same level (90%) travel achieved on its own two PROMISING-graded runs
(`docs/benchmark/decision-gate.md` "Post-benchmark comparison").

### 2.2 Ordinary and economic-weighted recall

Two distinct recall numbers exist in the frozen artifacts, and the published report already
distinguishes them; this section derives both directly rather than repeating the report's prose:

- **Unique scoreable-pattern recall (candidate-match sense): 1/6 (16.7%).** Derived from
  `candidate_scores[].matched_patterns` across all 15 candidates
  (`task-028-task-065-b2b-comparable-20260822-001.json`): the only scoreable pattern id
  (`inputs.scoreable_pattern_ids = [B01, B02, B03, B04, B08, B09]`) that appears in any candidate's
  `matched_patterns` is `B03` — it appears in 9 of 15 candidates, at `best_pattern_recall` between
  0.263 and 0.992. `B01`, `B02`, `B04`, `B08`, and `B09` appear in zero candidates' `matched_patterns`
  anywhere in the frozen candidate set. (`B07` also appears, in `CAND-001`/`CAND-004`/`CAND-005`,
  but is not in `scoreable_pattern_ids` — excluded from recall scoring by the same rule that
  excludes travel's `P05`/`P07`, per `docs/benchmark/decision-gate.md`'s fixed-denominators section
  and `_scoreable_pattern_ids`'s generic `affected_n >= min_exposed_records` /
  development-split-presence rule, `HANDOFF-065`.)
- **Validation-qualified / economic-weighted recall: 0/6 (0%).** `metrics.economic_weighted_recall
  = {value: 0.0, recovered_impact_eur: 0, recovered_scoreable_patterns: []}`. This is 0 not because
  `B03` was never found — it was found repeatedly and with high recall — but because every
  candidate that matched it was `DOWNGRADE`d by `TASK-019` to `descriptive_observation`, which is
  below the `predictive_association` floor the recall metric requires (`docs/benchmark/decision-
  gate.md` metric 2's own definition: "findings that reach at least `predictive_association` without
  being a trap").

The gap between these two numbers (16.7% candidate-match recall vs. 0% validation-qualified recall)
is the single most important fact this postmortem's root-cause analysis turns on: discovery and
ranking did their job on `B03`; validation is what zeroed the business-facing metric, and did so
for a stated, gate-by-gate reason (§2.7), not silently.

### 2.3 Direction accuracy — not estimable

`metrics.effect_direction_accuracy = {correct: 0, total: 0, value: null}`. The metric is defined
only over "validated findings... at or above `predictive_association`" that also matched a
scoreable pattern (`docs/benchmark/decision-gate.md` metric 5). Zero candidates meet that
conjunction (every candidate is capped at `descriptive_observation` by G06), so the denominator is
zero and the metric is undefined, not zero and not passing. This is a direct, mechanical
consequence of §2.7's G06 result, not a separate finding.

### 2.4 Impact estimation error — not estimable

`metrics.economic_impact_estimation_error = {details: [], median_relative_error: null}`, and the
same is true of the benchmark-only diagnostic sibling
(`economic_impact_estimation_error_attribution_narrowed_diagnostic`, `TASK-059`). Both require an
eligible validated-and-matched candidate to compute a relative error against a realized
ground-truth effect; none exists. Category 6 (economic impact, direction correct/magnitude wrong)
is addressed on this basis in §4 — it does not apply here at all, because the failure occurred one
gate earlier than where a magnitude question becomes askable.

### 2.5 Leakage violations — 0

`metrics.leakage_violations.value = 0`. Every candidate's `gate_results` shows
`G00_LINEAGE_PREREGISTRATION` and `G01_TARGET_LEAKAGE` as `pass` (`task-019-...json`, all 15
candidates). No hard disqualifier 1 (`docs/benchmark/decision-gate.md`) fired.

### 2.6 Trap promotion / rejection

`metrics.confounder_trap_rejection`: `any_trap_promoted = false`;
`trap_appeared_as_candidate = {BT01: false, BT02: true, BT03: true, BT04: true, BT05: false}`;
`trap_promoted` is `false` for all five. Concretely: `CAND-010` and (per `candidate_scores`)
`CAND-015` each literally contain `BT02`/`BT03`'s apparent-feature condition and are flagged
`is_trap=true`; `CAND-001`/`CAND-013` similarly contain `BT04`'s. All four of these candidates are
`DOWNGRADE`d by `TASK-019` (same G06 mechanism as every other candidate) and none reaches a
promoted `policy_readiness` (`experiment_only` is the ceiling for every one of the 15 candidates —
`task-019-...json` `verdict_counts = {DOWNGRADE: 15}`, no candidate anywhere in the run reaches
`shadow_policy` or `HIGH_CONFIDENCE`). No hard disqualifier 2 fired. This category is addressed
fully in §4 — it is not implicated in the FAILED verdict; trap safety worked.

### 2.7 PASS / DOWNGRADE / REJECT distribution and failing gates

`task-019-task-065-b2b-comparable-20260822-001.json` `verdict_counts = {DOWNGRADE: 15}` — 0 PASS,
15 DOWNGRADE, 0 REJECT. Every one of the 15 candidates' `gate_results` shows the identical failing
set: `G06_CONFOUNDING` (fail), `G13_IDENTIFICATION_DESIGN` (fail — expected and non-diagnostic:
this is observational data with no quasi-experimental design, the same as every travel candidate
ever graded), `G14_RANDOMIZATION_INTEGRITY` (fail — same, expected for retrospective data). G09 is
`NOT_EVALUATED` for all 15 (§3). Every other gate (`G00`–`G05`, `G07`, `G08`, `G10`–`G12`, `G15`)
passes for all 15 candidates. G06 is therefore the sole gate that actually differentiates this run
from a passing one; G13/G14 would fail identically even for a candidate that cleared G06, because
this product's observational ceiling is `adjusted_observational_association`
(`docs/analytics/validation-contract.md` §1, §6) — no candidate here or in travel's own graded
history has ever cleared G13/G14, by design.

### 2.8 Support and temporal stability

G03 (sample adequacy) and G04 (uncertainty) pass for all 15 candidates; `exposed_records` range
from the low hundreds to several thousand and every candidate's bootstrap confidence interval
excludes zero by a wide margin (e.g. `CAND-001`: 95% CI `[21059.7, 23899.6]` USD on a point estimate
of `22370.9`). G10 (temporal stability) and G12 (robustness) pass for all 15:
`temporal_stability` shows the same raw sign across `development`/`validation`/`future_holdout` for
every candidate, with `holdout_retention` between 95% and 99%
(`docs/benchmark/task-065-b2b-portability-report.md` already states this range; the per-candidate
`diagnostics.holdout_retention` field confirms it, e.g. `CAND-001: 0.9808`). This is a materially
*better* stability signature than several of travel's own historically-graded runs — the raw
statistical signal in every one of these 15 candidates is strong, well-powered, and stable across
time. The FAILED verdict is not a "weak signal" story; every candidate's problem is confounding,
not statistical noise.

### 2.9 Adjustment (G06) coverage and attenuation — the actual failure mechanism

Computed directly from `task-019-task-065-b2b-comparable-20260822-001.json`'s 15
`diagnostics`/`validation_report` blocks:

| Statistic | Min | Mean | Max |
|---|---|---|---|
| `confounder_stratum_coverage` | 0.501 | 0.697 | 0.973 |
| Attenuation (`1 − \|adjusted\| / \|raw\|`) | 0.892 | 0.954 | 0.997 |
| `e_value` | 1.042 | 1.173 | 1.324 |

Every one of the 15 candidates fails G06 on **both** of its two independent conditions at once:
attenuation (89.2%–99.7%, against a `max_adjusted_attenuation = 0.50` ceiling — every candidate
loses far more than half its raw magnitude, not a borderline miss) and E-value (1.04–1.32, against
a `min_e_value = 1.50` floor). Critically, `confounder_stratum_coverage` is **not** collapsing the
way it did for travel's one disclosed residual G06 case (`ADR-042`/`ADR-043`, coverage `0.51` on
that specific candidate, near the floor): here the mean coverage is `0.70` and the minimum is still
right at the `0.50` floor rather than below it, meaning the joint stratification had a genuinely
adequate development-split sample to work with for every candidate, not a coverage-starved partial
adjustment. `adjustment_columns_used` ranges from 4 to 6 of the 9–11 eligible pool columns per
candidate (e.g. `CAND-001`: `('competitor_involved', 'decision_maker_engaged', 'company_size_band',
'lead_score')`, coverage `0.565`).

This combination — adequate coverage, near-total and highly consistent attenuation across all 15
candidates, and a uniformly failing E-value — is the statistical signature of a genuine,
well-powered adjustment result, not of a gate malfunctioning or an artifact of small samples. §4
returns to what this does and does not establish.

One further observable, directly from `validation_report.pattern_definition` across all 15
candidates (public field, not hidden ground truth): **every single one of the 15 committed
candidates uses `deal_size_usd` or `company_size_band` (a banded version of the same quantity) as
one of its exactly two conditions.** No candidate in the committed set is anchored on any other
feature alone. This is discussed as search/selection-stage evidence in §4, categories 2–3.

## 3. Domain contract differences: travel vs. b2b_sales

All figures below are read directly from each domain's public `manifest.json`/`split_manifest.json`
(travel: `synthetic_data/analytical/travel-bookings-analytical-v1.1.0/`; b2b:
`synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0/`). No hidden ground truth
was opened to build this table.

| Property | Travel (`v1.1.0`) | b2b_sales (`v1.0.0`) |
|---|---|---|
| `outcome_contract.status` | `ATTACHED` (TASK-013, Statistics-reviewed) | `PROVISIONAL` (TASK-062, explicitly out of scope for a TASK-013-grade review) |
| `outcome_contract.version` | `1.1.0` | `0.1.0-provisional` |
| Primary outcome `missing_data_policy` | `complete_no_missingness_expected` | `not_yet_classified` (label only — empirically 0.0% missing on `net_deal_contribution_usd` in `development`, per `missingness.json`; the gap is a review/process gap, not a demonstrated data-quality defect) |
| `validation_roles.heterogeneity_column` (G09) | `customer_segment` | `null` → G09 `NOT_EVALUATED` for all 15 candidates |
| `validation_roles.robustness_group_column` | `manager` | `null` (G12 still ran and passed for all 15 via the generic winsorize/threshold-perturbation checks, which do not require this field) |
| `validation_roles.alternative_outcome_id` | `gross_profit_eur` | `null` |
| `validation_roles.seasonality_column` (G11) | `booking_date` | `deal_created_date` (present; G11 passed for all 15) |
| Total classified columns | 33 | 25 |
| `DECISION_TIME` feature columns | 19 | 12 |
| G06 adjustment-eligible pool size | 16 | 11 |
| Derived decision-time calendar atom | `travel_month` (added `ADR-047`, purpose-built after `P04` was diagnosed vocabulary-blocked, `ADR-045`) | none — only the raw `deal_created_date` timestamp, itself excluded from the G06 pool as date-like |
| `record_count` | 10,000 | 10,000 |
| Development-split rows (search-fit) | 4,999 | 5,028 |
| Validation-split rows | 2,462 | 2,491 |
| Future-holdout rows | 2,539 | 2,481 |
| Discovery method version | `discovery-engine-v0.5.0` (both, as of the compared runs) | `discovery-engine-v0.5.0` |
| Evaluated hypotheses | 6,557–26,213 across different graded runs | 7,202 |

Record counts and split sizes are essentially identical between the two domains — sample size is
not a differentiator. The differentiators are: (1) b2b's outcome/validation-role contract is a
deliberately provisional, TASK-061/062-scoped stand-in, never brought to travel's TASK-013 review
standard; (2) b2b has roughly a third fewer decision-time features and adjustment-eligible
covariates than travel; (3) b2b has no derived calendar atom analogous to `travel_month`; (4) G09
cannot evaluate at all for b2b, capping every candidate below level 3 for a second, independent
reason beyond G06 (moot for this run only because G06 already caps every candidate first).

## 4. Root-cause analysis by category

Per the task's constraint, a category is only populated with a finding where the frozen artifacts
actually support one; several categories below are explicitly reported as not implicated.

### 4.1 Discovery vocabulary — partially implicated, not confirmed

`docs/benchmark/multi-domain-benchmarks.md` §"Domain 5: B2B sales pipeline" (already-published,
public design prose, not hidden ground truth) describes b2b_sales's nine patterns in prose,
including at least two in explicitly seasonal/quarter terms ("a Q4 retail budget-season bulk-deal
cost pattern", "a Q1 tech West-region renewal-push cost pattern"). The b2b analytical dataset has no
derived calendar/month/quarter feature at all — only the raw `deal_created_date` timestamp, which
(consistent with `ADR-045`'s finding for travel's own un-derived date columns, and with §4b/§11's
disclosed general exclusion of date-like columns from G06) is not a discovery atom. Travel only
gained its own analogous atom (`travel_month`) after its seasonal pattern `P04` was specifically
diagnosed as vocabulary-blocked (`ADR-045`, `ADR-047`); no equivalent remediation has ever been
scoped for b2b.

This postmortem cannot confirm whether either of the two seasonally-described b2b patterns is among
the five unrecovered scoreable patterns (`B01`, `B02`, `B04`, `B08`, `B09`) or among the two
excluded-from-scoring patterns, because `docs/benchmark/multi-domain-benchmarks.md` publishes no
`Bxx`-to-description mapping and resolving that would require opening
`hidden_ground_truth.json`, which this document does not do. Independent of that mapping, the
underlying vocabulary gap is real and general: unlike travel, b2b_sales was never given a decision-
time calendar atom, and `docs/analytics/validation-contract.md` §4b/§11's general policy already
disqualifies raw date columns from adjustment for every domain. This is flagged as a concrete,
actionable gap regardless of whether it explains this specific run's misses.

### 4.2 Search reachability — indeterminate from frozen artifacts

Whether `B01`/`B02`/`B04`/`B08`/`B09` were representable and scored somewhere in the full
7,202-hypothesis pool but simply ranked below the beam/top-K cutoff (as `ADR-038`'s
`scripts/diagnose_candidate_pool_recall.py` established for travel's `P02`/`P08`/`P09`) cannot be
determined from the artifacts this postmortem is scoped to read. The full evaluated-hypothesis pool
for `task-065-b2b-comparable-20260822-001` is not itself a persisted artifact — only the final 15
committed candidates are frozen and public. `scripts/diagnose_candidate_pool_recall.py` exists and
is precedented for exactly this kind of already-committed-run, post-hoc pool inspection (its own
module docstring states the "already frozen, now graded" discipline it relies on), but running it
requires opening `b2b_sales`'s `hidden_ground_truth.json` directly — outside this postmortem's hard
constraint. This category is neither confirmed nor ruled out; it is named as a specific, well-scoped
gap for a future, separately-authorized diagnostic task, not as a finding.

### 4.3 Ranking/selection — implicated, with direct evidence

Every one of the 15 committed candidates anchors on `deal_size_usd` or its banded proxy
`company_size_band` as one of exactly two conditions (§2.9, `pattern_definition`, public field).
`docs/analytics/discovery-engine-v0.md` documents `_development_score` as (population raised to a
configurable exponent) × effect magnitude, and its own prior diagnosis (`ADR-039`/`ADR-040`,
written for travel) states directly that "that maximum is always the dominant rescaling family
(largest population × effect, by construction of `_development_score`)". `docs/benchmark/multi-
domain-benchmarks.md` independently and publicly documents that b2b_sales's five confounding traps
were deliberately designed to "ride a multiplicative pathway that scales with `deal_size_usd` (the
dominant driver of variance)" in this domain specifically — i.e. this domain was built, by design,
with one covariate dominating outcome variance more than any prior `TASK-061` domain.

Put together: a domain whose outcome variance concentrates unusually heavily on one covariate, fed
into a score that rewards population × effect magnitude, is exactly the condition under which a
single dominant covariate can crowd an entire top-K with its own rescalings — the same generic
"dominant-pattern-rescaling" failure mode `ADR-035`/`ADR-036` first diagnosed for travel before
diversity selection existed. `TASK-060`'s existing diversity mechanism (`_greedy_diverse_select`)
guards against **population overlap** between selected candidates, not against repeated use of the
same anchor **feature** — two candidates conditioned on `deal_size_usd < X AND product_line = Y` vs.
`deal_size_usd < X AND discount_requested_pct >= Z` can have very different exposed populations
(low Jaccard overlap) while still sharing the same dominant, and in this run apparently-confounded,
anchor feature. That mechanism therefore would not, by construction, prevent exactly the pattern
observed here. This is a directly-evidenced, general (not b2b-specific) selection-stage gap, and is
the basis for §5's proposed next mechanism.

### 4.4 Validation — candidates found, correctly downgraded (on the evidence available)

`B03` was found by 9 of 15 candidates at recall between 0.26 and 0.99 (§2.2) and then downgraded by
G06 in every case, with the statistical signature described in §2.9: adequate stratification
coverage (not a sample-starved partial adjustment), near-total and strikingly consistent attenuation
across all 15 independently-conditioned candidates (89–100%), and a uniformly failing E-value. A
gate that is failing because it ran out of sample (coverage collapse, as in travel's one disclosed
residual case, `ADR-042`/`ADR-043`) produces a different, messier statistical signature than what is
observed here — 15 independently-derived candidates converging tightly on "almost the entire raw
effect disappears once decision-time covariates are jointly stratified" is not the signature of an
underpowered or malfunctioning gate. This postmortem cannot certify from public artifacts alone
that these are *correct* rejections in the sense of matching the domain's true generative
mechanism (that would require opening hidden ground truth), but the internal evidence available
without doing so is consistent with the gate performing its preregistered job
(`docs/analytics/validation-contract.md` §10: "judged by whether it rejects things that deserve
rejection") rather than with a validation defect. No evidence in the frozen artifacts points to G06
malfunctioning, mis-specified, or gate-crashing for this run.

### 4.5 Confounding safety — not implicated

All five traps (`BT01`–`BT05`) ended at `trap_promoted = false`; three appeared as literal
conditions in committed candidates and were rejected by the same G06 mechanism as every other
candidate (§2.6). This category has no finding: trap safety worked as designed on this run.

### 4.6 Economic impact — not implicated (no eligible denominator)

Direction accuracy and impact estimation error both have `value: null` with zero eligible
candidates (§2.3–2.4). There is no magnitude-error question to assess here, because the failure
occurred one gate (G06) earlier than where a magnitude question becomes askable. This category has
no finding on this run.

### 4.7 Domain contract — implicated, with direct evidence

§3's comparison table is itself the evidence: b2b_sales's outcome contract is explicitly
`PROVISIONAL` (never brought to travel's `TASK-013`-reviewed `ATTACHED` standard, by TASK-062's own
explicit scope decision), has roughly a third fewer decision-time/adjustment-eligible features than
travel, has no reviewed heterogeneity role (G09 `NOT_EVALUATED` for every candidate — moot for this
run's verdict only because G06 already caps every candidate first, but a real, independent ceiling
that would matter the moment any candidate ever clears G06), and no derived calendar atom (§4.1).
None of this caused the specific G06 failure on `B03`-matching candidates directly, but it does mean
this run's domain contract is measurably thinner than the one every prior travel-only decision-gate
verdict was produced against, and that gap was disclosed as deliberately deferred rather than
silently assumed equivalent (`TASK-061`/`TASK-062`'s own "explicitly not in scope" language).

### 4.8 Benchmark mismatch — weakly implicated, flagged as an open question, not confirmed

There is a legitimate question, only partially resolvable from frozen artifacts, about whether
"economic-weighted recall" is measuring the property this decision-gate cares about when the
dominant-variance covariate in a domain also happens to mediate most of the top-ranked candidate
pool: a domain built (by public design, `docs/benchmark/multi-domain-benchmarks.md`) so that one
covariate dominates outcome variance more than in any prior domain will, through the mechanism in
§4.3, tend to produce a candidate pool that is both high-precision (§2.1 — real statistical
structure) and — if that same covariate is also a genuine common cause of the outcome and of several
conditions — correctly and near-uniformly downgraded by G06. In that scenario, a 0% economic-
weighted-recall verdict could reflect the benchmark's own variance concentration interacting with
the search's known dominant-covariate-crowding tendency (§4.3) more than it reflects the validation
methodology being unable to separate real transportable patterns from confounded ones in general.
This is not confirmed: distinguishing "the five missing patterns were never structurally
representable in the committed pool because of dominant-covariate crowding" (which would make this
substantially a §4.3 story) from "the five missing patterns are themselves confounded by the same
dominant covariate and would have been correctly downgraded even if surfaced" (which would make the
metric's zero a correct read of a genuinely low-portability run) requires the same pool-reachability
diagnostic flagged as out of scope in §4.2. This category is named because the evidence partially
but not fully supports it, per the task's own instruction not to force a finding where evidence is
absent, but also not to omit one where evidence is genuinely present.

## 5. Determination: methodology defect vs. domain-adaptation requirement

**This is primarily an expected domain-adaptation requirement, compounded by a real but
pre-existing general-purpose search/selection-stage gap that this domain exposes more severely than
travel does — not a new methodology defect.**

Evidence for "not a new defect": G06 itself behaved exactly as its own acceptance test requires
(§4.4) — it is not crashing, not coverage-starved, not producing an inconsistent or noisy result,
and its correction from a fixed two-variable pair to a generalized, coverage-gated, per-candidate
pool (`ADR-042`, `TASK-063`) is precisely what let it evaluate 9–11 real b2b covariates per
candidate instead of failing closed for lack of a hand-authored b2b-specific adjustment set. Every
other gate (G00–G05, G07, G08, G10–G12, G15) passed cleanly and the underlying raw statistical
signal is strong and temporally stable (§2.8) — nothing here indicates the core discovery, ranking,
or gate-sequencing machinery is broken.

Evidence for "domain-adaptation requirement": §3 and §4.7 show b2b_sales's own analytical/outcome/
validation-role contract was deliberately built to a lower, explicitly-provisional standard than
travel's (TASK-061/062's own scope decision, not an oversight), is missing a calendar atom travel
only received after its own equivalent gap was diagnosed (§4.1), and has no reviewed heterogeneity
role. None of this is a defect in the general validation methodology; it is unfinished domain-
specific input work that was always going to be needed before a second domain could be judged on
equal footing with travel.

Evidence for "a real, pre-existing general-purpose gap, more severely exposed here": §4.3's
selection-stage crowding mechanism (`_development_score` rewarding population × effect magnitude,
`_greedy_diverse_select` guarding population overlap rather than feature identity) is not new to
this run — it is the same class of mechanism `ADR-035`/`ADR-036` diagnosed for travel before
diversity selection existed. It was not previously observed to fully dominate a committed candidate
set (travel's own graded runs show more anchor-feature variety), which is consistent with, though
not proof of, b2b_sales's publicly-documented unusually concentrated outcome variance (§4.3) making
this particular gap bite harder here than it has on travel to date.

## 6. Proposed next general-purpose mechanism

**Mechanism:** add a feature-identity diversity floor to the final top-K/beam-survivor selection
stage, orthogonal to and independent of the existing population-overlap diversity mechanism
(`_greedy_diverse_select`, `TASK-060`) and the existing structural (feature, operator)-signature
beam-survival reserve (`discovery-engine-v0.5.0`, `TASK-064`). Concretely: cap the number of
final selected slots (Top-K, or beam-survivor quota, whichever stage is judged the more principled
place to apply it) that may share the same top-level anchor feature identity, as a configurable
fraction of K — e.g. no single feature name may anchor more than `ceil(K / 3)` of the final
selection, with `K/1` (no cap) as the value that reproduces current behavior exactly for regression
testing. The cap operates purely on feature *identity* (a string key), never on feature *values* or
which feature happens to be capped in any specific run — fully feature-identity-agnostic and
domain-neutral, in the same sense every prior `TASK-060`/`TASK-063`/`TASK-064` mechanism was
required to be (`ADR-037`, `ADR-039`, `ADR-042`, `ADR-046`).

This is the single most direct response to §4.3's evidence (100% of this run's committed candidates
anchor on one of two closely related feature identities) and is scoped as a natural extension of
already-existing, already-tested selection-stage machinery rather than a new statistical method.

### 6.1 How to test it on a new, not-yet-opened domain

1. Implement and version the mechanism (e.g. `discovery-engine-v0.6.0`), with a zero/no-cap default
   that reproduces `v0.5.0` exactly, following the same regression-test discipline as every prior
   `discovery-engine-v0.x` change.
2. Verify it with a truth-free deterministic rehearsal, and — for engineering verification only,
   never for tuning — a diagnostic run against `travel` and/or the now-open `b2b_sales` ground
   truth, exactly the "already-committed, already-open" precedent `ADR-025`/`HANDOFF-054`/`ADR-038`
   already established. No parameter may be chosen or adjusted based on what this diagnostic shows
   about `b2b_sales` specifically — the anchor-feature cap fraction must be fixed from general
   reasoning (e.g. "no single feature should be allowed to anchor more than a third of a Top-10")
   before any new domain's candidates are generated, exactly as `ADR-040`'s percentile choice was
   fixed from general shape reasoning rather than solved for a known outcome.
3. Select the test domain by the same rule `TASK-065` itself used: lexicographically first
   `domain_id` among the registered, still-unopened `TASK-061` domains (§7) — currently `ecommerce`.
4. Run the full existing `ADR-008`/`ADR-051`-style blind protocol: fresh isolated Blind Discovery
   actor, signed commitment, independent Code Reviewer custody verification, then a fresh
   independent Statistics/evaluator actor for `TASK-019` (frozen before truth access) and `TASK-028`
   (only after that freeze) — the same ordered custody chain `ADR-051`/`ADR-052` established for
   `b2b_sales`, reused because it is now the project's standing protocol for any non-travel domain,
   not because `ecommerce` carries any special contamination risk of its own.
5. Also run the same protocol with the mechanism at its zero/no-cap default on the same domain (or
   reuse a prior `v0.5.0` run on that domain if one exists) as the same-domain baseline the new
   mechanism is compared against — never compared only to `b2b_sales`'s own numbers, which are a
   different domain.

### 6.2 Preregistered success and kill criteria (fixed before `ecommerce`'s ground truth is opened)

**Structural check (available before any ground truth is opened, from the committed candidate file
alone):** the new mechanism must increase the count of distinct top-level anchor-feature identities
represented in the committed Top-10/Top-K, relative to the same-domain `v0.5.0` baseline. If it does
not, the mechanism failed to achieve its own stated structural target and the remaining criteria
are not evaluated — this is a **kill** on its own, decided without opening truth.

If the structural check passes, open `ecommerce`'s ground truth via `TASK-028` and grade against the
existing `docs/benchmark/decision-gate.md` metrics:

- **Success:** economic-weighted recall (or, failing that, unique scoreable-pattern candidate-match
  recall — the same distinction §2.2 draws) is strictly higher than the same-domain `v0.5.0`
  baseline, **and** Top-10 precision, direction accuracy, and trap rejection (0 promoted traps) are
  not degraded relative to that same baseline, per `docs/benchmark/decision-gate.md`'s own hard
  disqualifiers and graded bands.
- **Kill:** any of — (a) the structural check above fails; (b) a trap is promoted that was not
  promoted under the baseline; (c) Top-10 precision or direction accuracy degrades relative to the
  baseline; (d) the structural check passes but economic-weighted and unique scoreable-pattern
  recall are both unchanged or worse than the baseline. On any kill outcome, this specific mechanism
  is not iterated a second time on the same lever (the same two-strikes discipline
  `ADR-041`/`ADR-049` already apply to selection-stage and beam-search tuning respectively) — the
  honest negative result is recorded and a genuinely new mechanism is required for any further
  attempt.

Neither branch authorizes any b2b-specific, ecommerce-specific, or pattern-identity-specific tuning
at any point; the anchor-feature cap fraction is fixed once, from general reasoning, before
`ecommerce`'s candidates are even generated.

## 7. Remaining eligible `TASK-061` domains

`packages/analytics/src/policy_analytics/domain_benchmarks/registry.py` registers six `TASK-061`
domains: `ecommerce`, `saas`, `insurance`, `manufacturing`, `b2b_sales`, `healthcare`.

Filesystem-existence check only (no file contents opened) confirms every domain has a materialized
`synthetic_data_domains/<domain>/comparable/evaluation/hidden_ground_truth.json` on disk — all six
were generated together as part of `TASK-061`'s build-out (`TASKS.md` TASK-061 domain 1–6 progress
entries). Existence of the file is not the same as disclosure: only `b2b_sales`'s file has actually
been opened/read by any agent, per `ADR-048`'s disclosure and the absence of any equivalent
disclosure entry in `DECISIONS.md` or `memory/HANDOFFS.md` for any other domain. The `TASK-061`
domain-content review work recorded for `ecommerce` (`HANDOFF-053`, and the parallel work recorded
for `saas`/`insurance`/`manufacturing`/`healthcare` in `TASKS.md`'s `TASK-061` entry) verified trap
wiring using generated `noise`/`traps_only`/`comparable` sample statistics (`raw_marginal_effect`,
a function of generated rows under different `active_traps` configurations) — it never opened or
required opening any domain's `hidden_ground_truth.json` file, so it does not count as disclosure
under `ADR-048`'s definition.

**Eligible for the next test (§6): `ecommerce`, `saas`, `insurance`, `manufacturing`, `healthcare`
— all five remaining `TASK-061` domains are genuinely unopened.** `b2b_sales` is excluded going
forward per `ADR-048`/`ADR-051`. Per §6.1's domain-selection rule (lexicographically first among
registered, still-unopened domains), `ecommerce` is the next domain in line if this mechanism is
authorized and implemented.

## 8. Task/decision references

This postmortem's findings are recorded factually in `DECISIONS.md` `ADR-055`, which also concurs
with the concurrently-recorded `ADR-054` (Founder Strategy's portability-track path decision) and
records this session's Statistics-side attribution for `TASK-067` (diagnosis of the `TASK-065` G06
failure — general/fixable, not `b2b_sales`-specific, per §4.4 and §4.3 above; ML_DISCOVERY
concurrence requested in `HANDOFF-069`). §6's proposed mechanism is scoped as `TASK-068`, created
`BLOCKED` pending `TASK-067`'s concurrence, not implemented by this document.

## 9. What this postmortem does not establish

Consistent with the hard constraints given for this task: this document does not identify which
real-world feature or mechanism any specific `Bxx` pattern or `BTxx` trap actually represents beyond
the bare public IDs and the already-published prose descriptions in `docs/benchmark/multi-domain-
benchmarks.md`; it does not confirm or rule out §4.2's search-reachability question or fully resolve
§4.8's benchmark-mismatch question, both of which require a pool-level diagnostic this postmortem's
scope excludes; and it proposes no code, threshold, or matching-logic change — §6's mechanism is
scoped, not implemented, and is recorded as a new `TODO`/`BLOCKED` task, never as work performed
under this document.
