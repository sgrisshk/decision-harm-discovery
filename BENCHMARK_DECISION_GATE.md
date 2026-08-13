# Benchmark Decision Gate — Pre-Registered

**Owner:** FOUNDER_STRATEGY
**Recorded:** 2026-08-13, against commit `317bde01de76872322bec1936c8471d793120a3a`
**Status:** PRE-REGISTERED. Ground truth is confirmed unopened as of this commit (see below). This document must not be edited after `TASK-028`/`TASK-029` produce results — only appended to, under "Post-benchmark comparison."

## Why this exists, and why now

`docs/validation_contract.md` §10 already fixes a qualitative acceptance test for the validation methodology. This document is the founder-level companion to it: a business decision gate, using the six metrics `TASK-028` is scoped to compute, that turns those numbers into one of four verdicts — **STRONG / PROMISING / WEAK / FAILED** — and a bound action. It does not change discovery methodology, validation gates, or thresholds owned by `docs/validation_contract.md`; it interprets their output for a go/no-go call that is properly Founder's to make (`agents/FOUNDER_STRATEGY.md`: "go/no-go decisions", "prioritization").

**Confirmed pre-registration condition, checked before writing this document:** `TASK-017` (blind discovery test) is `BLOCKED`; `TASK-028` (ground-truth evaluator) is `BLOCKED`, depending on `TASK-022`/`TASK-023`, both `BLOCKED`. `TASK-015` itself was reverted to `BLOCKED` on 2026-08-13 because its existing candidate artifact predates the current pinned dataset identity and the formal `TASK-012` temporal-split contract, and must be rerun before it counts. No evaluation of `synthetic_data/evaluation/hidden_ground_truth.json` has occurred. These criteria are therefore genuinely fixed before anyone — including this agent — has seen a result.

## Scope

Applies to the first completed `TASK-017` blind run (run under the `ADR-008` allowlist-workspace protocol, not the earlier informal full-checkout `TASK-015` run) as scored by `TASK-028` and reported in `TASK-029`.

## Fixed denominators

From `synthetic_data/evaluation/hidden_ground_truth.json` (restricted; read only to write this pre-registration, not to shape it — these are counts, not directions or effect sizes):

- **9 true harmful patterns** exist: P01–P09.
- **7 are "scoreable"** for recall purposes: P01, P02, P03, P04, P06, P08, P09. **P05 and P07 are excluded from recall scoring**, matching `docs/validation_contract.md` §11's own preregistered position: P05 (n=23) is below any defensible power floor and a structural false negative "by construction, not analytical failure"; P07 has zero development-split rows and is undiscoverable under the mandated development-only fit split. Missing P05/P07 is not counted against the run. Wrongly *validating* either (if a candidate happens to touch them) is still subject to every other gate.
- **5 confounding traps** exist: T01–T05 (manager/supplier assignment artifacts, paid-search and payment-method composition artifacts, and the manual-exception main effect, per `docs/validation_contract.md` §10).

**K for Top-K precision = 10** — the floor of `TASK-015`'s own target range ("10–20 harmful candidate patterns") and the minimum plausible ranked set `TASK-016` would carry forward. If the run legitimately produces fewer than 10 candidates, precision is computed over however many exist, and that shortfall is itself reported alongside the metric, not hidden by a smaller denominator.

**"True pattern match"** — a candidate counts as recovering pattern Pxx if its exposed population overlaps that pattern's `affected_booking_ids` above the threshold `TASK-028` implements. The exact overlap statistic (e.g., Jaccard, precision/recall of membership) is `TASK-028`'s implementation and Statistics' methodological call, not fixed here — only the business consequence of the resulting count is fixed here.

## Hard disqualifiers (override every band below)

These mirror `docs/validation_contract.md` §10's own weighting ("a false-positive trap is weighted more heavily than a missed pattern") and are binary, not graded:

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

The tier thresholds above are a founder-level business judgment about how much evidence justifies risking a real customer relationship on this mechanism — not a statistical methodology decision. The exact matching statistic for "true pattern match" (K's implementation), and confirmation that these numeric bands don't conflict with anything in `docs/validation_contract.md`, are Statistics' call. A handoff requesting that confirmation is recorded in `memory/HANDOFFS.md` (`HANDOFF-027`) and should resolve before `TASK-028` runs, so the bands are jointly owned by the time ground truth is opened — not just Founder-imposed after the fact.

## Post-benchmark comparison

**PENDING — not filled in.** `TASK-017`/`TASK-028`/`TASK-029` have not run. Once `TASK-029`'s benchmark report exists, append (do not edit the sections above) a dated comparison here:

| Metric | Pre-registered band met | Actual result | Notes |
|---|---|---|---|
| Top-K precision | — | — | — |
| Economic-weighted recall | — | — | — |
| Confounder trap rejection | — | — | — |
| Leakage violations | — | — | — |
| Effect direction accuracy | — | — | — |
| Economic impact estimation error | — | — | — |
| **Overall verdict** | — | — | — |
| **Action taken** | — | — | — |
