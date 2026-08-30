# Benchmark Decision Gate — Pre-Registered

**Owner:** FOUNDER_STRATEGY
**Recorded:** 2026-08-13, against commit `317bde01de76872322bec1936c8471d793120a3a`
**Status:** PRE-REGISTERED. Ground truth is confirmed unopened as of this commit (see below). This document must not be edited after `TASK-028`/`TASK-029` produce results — only appended to, under "Post-benchmark comparison."

## Why this exists, and why now

`docs/analytics/validation-contract.md` §10 already fixes a qualitative acceptance test for the validation methodology. This document is the founder-level companion to it: a business decision gate, using the six metrics `TASK-028` is scoped to compute, that turns those numbers into one of four verdicts — **STRONG / PROMISING / WEAK / FAILED** — and a bound action. It does not change discovery methodology, validation gates, or thresholds owned by `docs/analytics/validation-contract.md`; it interprets their output for a go/no-go call that is properly Founder's to make (`agents/FOUNDER_STRATEGY.md`: "go/no-go decisions", "prioritization").

**Confirmed pre-registration condition, checked before writing this document:** `TASK-017` (blind discovery test) is `BLOCKED`; `TASK-028` (ground-truth evaluator) is `BLOCKED`, depending on `TASK-022`/`TASK-023`, both `BLOCKED`. `TASK-015` itself was reverted to `BLOCKED` on 2026-08-13 because its existing candidate artifact predates the current pinned dataset identity and the formal `TASK-012` temporal-split contract, and must be rerun before it counts. No evaluation of `synthetic_data/evaluation/hidden_ground_truth.json` has occurred. These criteria are therefore genuinely fixed before anyone — including this agent — has seen a result.

## Scope

Applies to the first completed `TASK-017` blind run (run under the `ADR-008` allowlist-workspace protocol, not the earlier informal full-checkout `TASK-015` run) as scored by `TASK-028` and reported in `TASK-029`.

## Fixed denominators

From `synthetic_data/evaluation/hidden_ground_truth.json` (restricted; read only to write this pre-registration, not to shape it — these are counts, not directions or effect sizes):

- **9 true harmful patterns** exist: P01–P09.
- **7 are "scoreable"** for recall purposes: P01, P02, P03, P04, P06, P08, P09. **P05 and P07 are excluded from recall scoring**, matching `docs/analytics/validation-contract.md` §11's own preregistered position: P05 (n=23) is below any defensible power floor and a structural false negative "by construction, not analytical failure"; P07 has zero development-split rows and is undiscoverable under the mandated development-only fit split. Missing P05/P07 is not counted against the run. Wrongly *validating* either (if a candidate happens to touch them) is still subject to every other gate.
- **5 confounding traps** exist: T01–T05 (manager/supplier assignment artifacts, paid-search and payment-method composition artifacts, and the manual-exception main effect, per `docs/analytics/validation-contract.md` §10).

**K for Top-K precision = 10** — the floor of `TASK-015`'s own target range ("10–20 harmful candidate patterns") and the minimum plausible ranked set `TASK-016` would carry forward. If the run legitimately produces fewer than 10 candidates, precision is computed over however many exist, and that shortfall is itself reported alongside the metric, not hidden by a smaller denominator.

**"True pattern match"** — a candidate counts as recovering pattern Pxx if its exposed population overlaps that pattern's `affected_booking_ids` above the threshold `TASK-028` implements. The exact overlap statistic (e.g., Jaccard, precision/recall of membership) is `TASK-028`'s implementation and Statistics' methodological call, not fixed here — only the business consequence of the resulting count is fixed here.

## Hard disqualifiers (override every band below)

These mirror `docs/analytics/validation-contract.md` §10's own weighting ("a false-positive trap is weighted more heavily than a missed pattern") and are binary, not graded:

1. **Any leakage violation** (`TASK-028`'s leakage-violation count > 0) → overall verdict is **FAILED**, regardless of every other metric.
2. **Any confounding trap (T01–T05) reaches `SHADOW_POLICY` or `HIGH_CONFIDENCE` policy readiness**, i.e. is promoted rather than rejected/downgraded → overall verdict is **FAILED**, regardless of every other metric. A run that finds real patterns but also promotes a trap has failed, per the contract's own standing rule.
3. **Any single validated finding above the materiality threshold has the wrong effect direction** (sign contradicts the realized counterfactual ground truth) → overall verdict is **FAILED**, regardless of aggregate direction accuracy. One materially-sized wrong-direction recommendation is worse than several small misses — it tells a future customer to do the opposite of what helps them.

If none of these trigger, grade the four metrics below and take the **weakest** of the four bands as the overall verdict.

## Graded metrics

### 1. Top-K precision (K=10, true pattern vs. trap/noise)

| Band | Threshold |
|---|---|
| STRONG | ≥ 60% (6+ of top 10 are true patterns) |
| PROMISING | 30–59% |
| WEAK | 10–29% |
| FAILED | 0% (no true pattern in the top 10) |

### 2. Economic-weighted recall (share of total scoreable exposure, the 7 non-excluded patterns, captured by findings that reach at least `predictive_association` without being a trap)

| Band | Threshold |
|---|---|
| STRONG | ≥ 50% |
| PROMISING | 25–49% |
| WEAK | 5–24% |
| FAILED | < 5% |

### 3. Confounder trap rejection (of T01–T05) — see hard disqualifier 2 above for the binary floor; graded only above that floor

| Band | Threshold |
|---|---|
| STRONG | 5/5 rejected or clearly downgraded (capped below `SHADOW_POLICY`), each with a stated confounding caveat |
| PROMISING | 5/5 rejected/downgraded, but at least one caveat is weak or easy to miss in the write-up |
| WEAK / FAILED | Any trap promoted — this is hard disqualifier 2, not a graded outcome |

### 4. Leakage violations — see hard disqualifier 1; binary, not graded (0 = passes; any other value = FAILED overall)

### 5. Effect direction accuracy (validated findings only, at or above `predictive_association`)

| Band | Threshold |
|---|---|
| STRONG | 100% correct direction |
| PROMISING | 90–99% correct, with every wrong-direction case below the materiality threshold |
| WEAK | 70–89% correct |
| FAILED | < 70% correct, or any materially-sized miss — see hard disqualifier 3 |

### 6. Economic impact estimation error (median relative error of reported historical exposure vs. realized ground-truth effect, validated findings only)

| Band | Threshold |
|---|---|
| STRONG | ≤ 25% |
| PROMISING | 25–50% |
| WEAK | 50–100% |
| FAILED | > 100% (off by more than 2×), or an undisclosed systematic directional bias |

## Overall verdict and bound action

**Overall verdict = the weakest of the four graded bands, unless a hard disqualifier fires, in which case overall = FAILED.**

| Overall verdict | What it means | Action |
|---|---|---|
| **STRONG** | Mechanism reliably finds real, material, correctly-signed patterns and correctly rejects known traps, with usably accurate impact estimates. | Sufficient to proceed toward real customer data (`TASK-037`→`TASK-038` once `TASK-057` delivers a customer). No further synthetic iteration required first. Evidence language stays capped at `adjusted_observational_association` regardless — this gate is about the discovery mechanism, not a license to overclaim. |
| **PROMISING** | Mechanism works directionally but has a specific, named weak metric. | One more, narrowly-scoped synthetic iteration targeting the specific weak metric — not a change to the core discovery approach. Do not advance to real customer data until re-graded at STRONG or PROMISING-with-the-same-metric-improved. |
| **WEAK** | Mechanism finds little signal above noise, or impact estimates are unreliable, without a disqualifying failure. | Do **not** proceed to real customer data. Requires a real iteration cycle addressing the specific failing metric(s), owned by ML_DISCOVERY/STATISTICS. If a second independent blind run still grades WEAK or worse on the same metric, treat it as a **FAILED** outcome for the purpose of the core-approach trigger below. |
| **FAILED** | Either a hard disqualifier fired, or the mechanism cannot reliably separate signal from noise/confounding even with fully known ground truth. | Do not proceed to real customer data under any circumstance. If Statistics/ML Discovery attribute the failure to a fixable defect (bug, missing input, mis-specified split) — fix and rerun once. If two independent blind runs both fail (or the second is graded WEAK or worse on the same metric after a first remediation attempt), that is the trigger below. |

## When to change the core discovery approach

This is a process trigger, not a technical verdict — the diagnosis of *why* a run failed belongs to ML_DISCOVERY and STATISTICS, not to Founder. The trigger fires when **both** of the following hold:

1. Two independent blind runs (the original `TASK-017` run plus one remediation attempt) both grade **WEAK or worse on the same metric**, and
2. ML_DISCOVERY and STATISTICS confirm, in a handoff, that the cause is not a fixable defect (a bug, a missing input, a mis-specified split, an under-tuned parameter) but a limitation of the discovery method itself at this data richness.

When both hold, Founder convenes a mandatory review with ML_DISCOVERY, STATISTICS, and ARCHITECT before any further synthetic iteration or real-customer work proceeds, and records the outcome as a new `DECISIONS.md` entry. A single bad run — even a FAILED one — does not by itself justify changing the discovery approach; it justifies diagnosing why, first.

## Ownership note

The tier thresholds above are a founder-level business judgment about how much evidence justifies risking a real customer relationship on this mechanism — not a statistical methodology decision. The exact matching statistic for "true pattern match" (K's implementation), and confirmation that these numeric bands don't conflict with anything in `docs/analytics/validation-contract.md`, are Statistics' call. A handoff requesting that confirmation is recorded in `memory/HANDOFFS.md` (`HANDOFF-027`) and should resolve before `TASK-028` runs, so the bands are jointly owned by the time ground truth is opened — not just Founder-imposed after the fact.

## Post-benchmark comparison

**2026-08-16, Statistics.** `task-015-official-20260816-015` (the first `TASK-017`-compliant blind
run) scored by `TASK-028` (`scripts/evaluate_benchmark.py`,
`artifacts/evaluation/task-028-benchmark-evaluation.json`), validated under contract v1.1.0. Full
detail: `docs/benchmark/task-029-benchmark-report-v1.md`.

| Metric | Pre-registered band met | Actual result | Notes |
|---|---|---|---|
| Top-K precision | STRONG (≥60%) | 90% (9/10) | 1 of top 10 (`CAND-007`) below the 50% match-recall threshold |
| Economic-weighted recall | PROMISING (25–49%) | 45.2% | Only P01, P06 recovered of 7 scoreable patterns |
| Confounder trap rejection | PROMISING, not STRONG | 0/5 promoted | No trap appeared as a candidate at all — non-promotion by absence, not demonstrated active rejection with a stated caveat; see report §3.3 |
| Leakage violations | passes | 0 | Hard disqualifier 1 did not fire |
| Effect direction accuracy | STRONG (100%) | 100% (3/3) | Only validated+matched candidates counted, per spec |
| Economic impact estimation error | **FAILED (>100%)** | median 204% (69–380% range) | Diagnosed cause: candidate rules ~15–16× broader than the exact injected pattern population; see report §3.6 |
| **Overall verdict** | — | **FAILED** | Driven by metric 6 alone (weakest-graded-metric rule); no hard disqualifier fired |
| **Action taken** | — | Do not proceed to real customer data yet | Statistics attributes the failure to a fixable estimation-granularity defect (report §4), pending ML_DISCOVERY concurrence (`HANDOFF-043`) before authorizing a single remediation rerun under decision-gate's FAILED action |

**Document-quality note (Statistics, resolving `HANDOFF-027`):** this document's own text is
internally inconsistent about how many metrics are graded — it lists six numbered "Graded metrics"
subsections but the overall-verdict rule says "grade the four metrics below and take the weakest
of the four bands." Metrics 3 and 4 are each partially gating (a hard disqualifier can fire from
either), which may be the intended distinction, but the wording should say so explicitly rather
than leave "four" unreconciled with six numbered subsections. Recommend a future edit (by
FOUNDER_STRATEGY, this document's owner) clarify that the weakest-band rule applies across metrics
1, 2, 3 (when not disqualified), 5, and 6 — five bands — with metric 4 remaining purely a binary
disqualifier gate, never itself contributing a "band." This did not change this run's verdict:
FAILED is the floor under every reading, since metric 6 alone is FAILED.

---

**2026-08-17, Statistics/Architect.** Remediation rerun under the FAILED action's authorized
single-remediation path (`HANDOFF-043`, both parts): `task-058-remediation-20260817-001`
(`ADR-023`'s `discovery-engine-v0.2.0`, `population_score_exponent=0.5`), validated under contract
v1.1.0 (`artifacts/validation/task-019-official-20260817-task-058-remediation-001.json`), scored by
`TASK-028` (`artifacts/evaluation/task-028-task-058-remediation-001.json`). Full record:
`ADR-025`; resolves `HANDOFF-048`.

| Metric | Pre-registered band met | Actual result | Notes |
|---|---|---|---|
| Top-K precision | STRONG (≥60%) | 90% (9/10) | Unchanged from the original run |
| Economic-weighted recall | PROMISING (25–49%) | 45.2% | Unchanged — still only P01, P06 of 7 scoreable patterns |
| Confounder trap rejection | PROMISING, not STRONG | 0/5 promoted | Now a materially different case than the original run's "absence": `CAND-014` (`destination==Tokyo AND payment_method==bank_transfer`, a genuine `P06` recovery, `best_pattern_recall=1.0`) literally contains `T04`'s apparent-feature condition (`payment_method==bank_transfer`) as a subset and is therefore flagged `is_trap=True` by the evaluator's exact-tuple-membership check, alongside `matched_patterns=['P06']` — the evaluator cannot currently distinguish "trap condition alone" from "trap condition plus a genuine narrowing condition." `T04` did not promote (`policy_readiness=experiment_only`) either way, so the hard disqualifier and the graded band are unaffected, but the true positive/negative label for this one candidate is methodologically ambiguous, not a clean active rejection. Disclosed rather than smoothed over one way or the other. |
| Leakage violations | passes | 0 | Unchanged |
| Effect direction accuracy | STRONG (100%) | 100% (7/7) | More matched candidates than before (7 vs 3) because tighter candidates recall-match a single pattern more often; all still correctly signed |
| Economic impact estimation error | **PROMISING (25–50%)** | median 37.5% (6.9–381% range) | Down from 204%; diagnostic attribution-narrowed sibling (`TASK-059`) is 76.2% on this run — no longer the tighter of the two, consistent with `TASK-058` shrinking the gap between whole-rule and narrowed exposure directly, rather than the diagnostic doing the work |
| **Overall verdict** | — | **PROMISING** | Weakest graded band (metrics 2, 3, 6); no hard disqualifier fired |
| **Action taken** | — | See `ADR-025` | `TASK-058` done condition met (materially narrower exposed populations); real-customer-data question (`TASK-038`) not resolved by this entry alone — flagged to Founder in `ADR-025` given this document's own PROMISING action-row wording |

---

**2026-08-29, Statistics/Architect.** First official `TASK-015`-equivalent blind run under **today's
actual default engine configuration** (`TASK-073`, closing the gap `ADR-066` found: no prior official
entry reflected the current code default, and the diagnostic `2/2`/`3/7` figures cited around
`TASK-069`/`TASK-070`/`TASK-072` were never an official `TASK-019`/`TASK-028` cycle). Run
`task-073-official-20260829-001` — `discovery-engine-v0.6.0`, `beam_rules_per_structure=2`,
`max_feature_identity_fraction=1.0` (both are the genuine, unconditional code defaults; see the
disclosure note below) — followed the full `ADR-008`/`051`/`052` protocol (issue → verify → launch →
freeze → sign), validated under contract **v1.3.0**
(`artifacts/validation/task-019-official-20260829-task-073-001.json`), scored by `TASK-028`
(`artifacts/evaluation/task-028-task-073-official-001.json`). Blind-custody chain independently
re-verified in this same pass: all three frozen output files' SHA-256 hashes and the issued
manifest's HMAC evaluator signature were both re-derived from scratch (not merely re-run through the
tool's own internal checks) and matched exactly. Full record: `ADR-068`.

| Metric | Pre-registered band met | Actual result | Notes |
|---|---|---|---|
| Top-K precision | would be STRONG (≥60%) in isolation | 70% (7/10) | 3 of top 10 are not true patterns: `CAND-010` (noise), plus the two trap candidates below — moot given the hard disqualifier |
| Economic-weighted recall | would be PROMISING (25–49%) in isolation | 45.2% | Only P01, P06 recovered of 7 scoreable patterns — identical to both prior official entries; discovery's recall profile has not moved |
| Confounder trap rejection | **hard disqualifier 2 fires** | 2/5 promoted | `T03` (`CAND-014`: `acquisition_channel==paid_search AND discount_rate>=0.08`) reaches `policy_readiness=shadow_policy` (PASS at `adjusted_observational_association`, G06 attenuation 0.04, E-value 1.90) with **zero matched true pattern** — an unambiguous trap promotion, not the earlier ambiguous-overlap case. `T04` also reaches `shadow_policy`, via `CAND-015` (ambiguous: also matches `P06`, `best_pattern_recall=0.69`) — the same category of ambiguity disclosed on 2026-08-17's `CAND-014`, but `T03`'s promotion has no such ambiguity to hide behind. |
| Leakage violations | passes | 0 | Hard disqualifier 1 did not fire |
| Effect direction accuracy | STRONG (100%) | 100% (9/9) | All matched, validated-at-or-above-`predictive_association` candidates correctly signed |
| Economic impact estimation error | **FAILED (>100%)** | median 219.9% (6.5%–464.6% range) | Worse than either prior official entry (204% original, 37.5% remediated) — moot given the hard disqualifier, but recorded in full per this document's own convention |
| **Overall verdict** | — | **FAILED** | Hard disqualifier 2 fires (a confounding trap reached `shadow_policy`) — overall is FAILED regardless of the four graded bands, per this document's own rule. This is a *new* failure mode: neither prior official run, nor `task-064-beam-20260822-001` (rejected as an experiment, never officially graded), ever promoted a trap. |
| **Action taken** | — | See `ADR-068` | Do not proceed to real customer data. `TASK-072`'s "not yet" stands, now on stronger, non-diagnostic grounds — see `ADR-068` for the full statement on what this does and does not mean for `TASK-072`/`TASK-057`. |

**Configuration disclosure (Statistics, `TASK-073` scope item 1).** `engine.py`'s
`DiscoveryConfig.beam_rules_per_structure` default is `2` (`TASK-064`'s tested value), and there is
**no override path** anywhere in the real official-run pipeline: `scripts/run_discovery.py`
constructs `DiscoveryConfig` without passing it, and neither the blind-agent CLI/acceptance contract
nor the `Makefile` expose a flag for it (unlike `max_feature_identity_fraction`, which both do). Every
real official run — including this one — has therefore used `beam_rules_per_structure=2`
unconditionally since `discovery-engine-v0.5.0` shipped, which directly contradicts `TASK-064`'s own
closing language ("not adopted as default on the strength of this result... No further tuning of
`beam_rules_per_structure` authorized"): the code was never actually reverted to a lower/zero value
after that experiment was rejected, and this task did not change it either, per its own hard rule. A
narrow, documentation-only follow-on to reconcile `TASK-064`'s closure text with the code's real
default is named in `TASK-073`'s `TASKS.md` entry; it is not fixed here.
`max_feature_identity_fraction=1.0` (`TASK-068`'s diversity-floor post-filter) *is* correctly the
genuine default — the CLI/`Makefile` both default to `1.0` and require an explicit, signed override
to activate the cap — so no comparable discrepancy exists for that parameter; this run correctly did
not exercise `TASK-068`'s filter, matching the actual current default rather than testing it.

---

**2026-08-30, Statistics/Architect.** First official `TASK-015`-equivalent blind run under contract
**v1.3.0 with `G16_CANDIDATE_COMPOSITION_SAFETY` present** (`TASK-083`, pre-registered by `ADR-081`,
implementing `G16` per `TASK-081`'s independently `APPROVED` implementation of `TASK-080`/`ADR-078`'s
design, accepted as Branch A product semantics by `ADR-080`/`TASK-082`). Run
`task-083-official-20260830-001` — same engine version, config, seed, and dataset identity as
`TASK-073`'s own run (`discovery-engine-v0.6.0`, `beam_rules_per_structure=2` (still the unconditional,
undisclosed-as-such default — separately re-verified this run, not merely assumed unchanged; see the
configuration-disclosure note below), `max_feature_identity_fraction=1.0`, seed `1729`, dataset
`travel-bookings-analytical-v1.1.0`, identity
`b6128eb3c1bdb36515c90570aa4ccabfc3dff8d1026d9002f1c832774b60a683`) — followed the full
`ADR-008`/`051`/`052` protocol (rehearsal → issue → verify → launch → freeze) end to end, validated
under contract **v1.3.0** (`artifacts/validation/task-019-official-20260830-task-083-001.json`), scored
by `TASK-028` (`artifacts/evaluation/task-028-task-083-official-001.json`). Blind-custody chain
independently re-verified in this same pass: all three frozen output files' SHA-256 hashes and the
issued manifest's HMAC evaluator signature were both re-derived from scratch (own implementation, not
the tool's own internal check) and matched exactly; `engine.py`'s recorded provenance hash matches the
current checkout exactly (no drift). Full record: `ADR-082`.

**The two `ADR-081` questions, answered separately (its own central discipline).** (1) Is the pipeline
safe after `G16`? Not re-litigated here (`TASK-081` already answered it) — but this is the first
official-cycle confirmation at real scale: `T03` (`CAND-014`) and `T04` (`CAND-015`), the same two trap
candidates that appeared in `TASK-073`, both reappeared here (same seed/config/dataset) and both are
now capped at `predictive_association`/`experiment_only` by `G16` — **zero traps promoted**, down from
`TASK-073`'s two. (2) Is there still useful evidence yield under that safety? Yes, but it collapses
essentially completely for this run — see the evidence-level split below — and that collapse is shown
to be fully attributable to `G16`, not to a separate discovery-quality regression (the discovery-metric
set below is byte-identical to `TASK-073`'s own).

| Metric | Pre-registered band met | Actual result | Notes |
|---|---|---|---|
| Top-K precision | STRONG (≥60%) | 70% (7/10) | Identical composition to `TASK-073` (same candidates, same seed/config/dataset) |
| Economic-weighted recall | PROMISING (25–49%) | 45.2% | Identical to `TASK-073` — only P01, P06 recovered of 7 scoreable patterns |
| Confounder trap rejection | **PROMISING, not STRONG** | 0/5 promoted | `T03`/`T04` (`CAND-014`/`CAND-015`) both appeared as candidates and are both actively, demonstrably capped below `SHADOW_POLICY` by `G16` (reason `composition_risk_indeterminate`, explicit leave-one-out detail recorded and surfaced as a warning on each) — a real, caveated downgrade, not mere absence. `T01`/`T02`/`T05` did not appear as candidates at all, so only 2 of 5 traps carry an active caveat rather than absence; `decision-gate.md`'s own STRONG band requires "5/5 ... each with a stated confounding caveat," which this mixed case does not clear. **Hard disqualifier 2 does not fire** — a first for this project's official history. |
| Leakage violations | passes | 0 | Hard disqualifier 1 did not fire |
| Effect direction accuracy | STRONG (100%) | 100% (9/9) | Identical to `TASK-073` |
| Economic impact estimation error | **FAILED (>100%)** | median 219.9% (6.5%–464.6% range, n=9) | Identical to `TASK-073` — a pre-existing, `G16`-independent estimation-granularity defect (first diagnosed 2026-08-16), not caused or affected by `G16` in any way |
| **Overall verdict** | — | **FAILED** | No hard disqualifier fires this run (a categorical difference from `TASK-073`'s hard-disqualifier-driven FAILED) — driven purely by metric 6 alone under the weakest-graded-band rule, exactly as the very first (2026-08-16) entry was |
| **Action taken** | — | Do not proceed to real customer data | See `ADR-082` for the full statement distinguishing the (improved) safety result from the (unimproved) yield/estimation result |

**Evidence-level distributions, pre-`G16`-ceiling and final (`ADR-081` item 6 — the single most
important addition this cycle makes to this document's format).** Computed by re-calling the real,
unmodified `grading.classify_evidence_level` over each candidate's persisted gate results, once as-is
(confirmed to reproduce every candidate's frozen `evidence_level` exactly) and once with `G16`'s gate
result forced to `PASS`:

| Evidence level | Pre-`G16` (`G00`–`G15` alone) | Final (with `G16`) |
|---|---|---|
| `adjusted_observational_association` | 11 | **0** |
| `predictive_association` | 1 | 12 |
| `descriptive_observation` | 3 | 3 |

11 of 15 candidates — including both trap candidates — would have reached
`adjusted_observational_association` without `G16`; `G16` caps every one of them to
`predictive_association`. The other 4 candidates' levels are unaffected by `G16` either way (a different,
earlier gate already capped them). Net: `ADJUSTED_OBSERVATIONAL`-and-above findings go from 11/15 to
0/15 in this run.

**Singleton accounting (`ADR-081` item 7).** `0` of 15 candidates are `k==1`; `15/15` are `k>=2`.
Matches `TASK-082`'s own 150/150-`k>=2`, 0-`k==1` finding across this project's entire prior
recoverable candidate record — an unchanged, disclosed operational fact about `discovery.engine`'s
current selection behavior, not a `G16` failure.

**Capability/yield ceiling vs. discovery-quality problem, kept visibly separate (`ADR-081` items 5/9).**
The complete `ADJUSTED_OBSERVATIONAL`-and-above disappearance above is a measured capability/yield
ceiling of the current discovery-semantics + available-observational-information combination — not an
implementation failure, exactly as `ADR-081` named in advance. It is **not** the reason this run's
overall verdict is FAILED: every discovery-quality number (Top-10 precision, recall, candidate
composition, direction accuracy) is unchanged from `TASK-073`, and the metric that actually drives the
FAILED verdict (economic impact estimation error) is a pre-existing, `G16`-independent defect, unrelated
to and unaffected by the yield ceiling. Neither fact is used to excuse or launder the other.

**Configuration disclosure (Statistics, `TASK-083` scope item 2, separately re-verified, not assumed
unchanged).** `engine.py`'s `DiscoveryConfig.beam_rules_per_structure` default is still `2`, with no
override path anywhere in the real official-run pipeline (re-confirmed by reading `engine.py` and
`scripts/run_discovery.py` directly, not by trusting `TASK-073`'s prior disclosure) — unchanged since
`TASK-073` first disclosed this; the narrow documentation-only follow-on named there remains open and
unaddressed by this task, per its own hard rule. `max_feature_identity_fraction=1.0` remains the
correct, genuine, correctly-documented default. No new rejected-experimental-parameter-as-default case
was found.
