# Benchmark Report v1 — First Compliant Blind Run

**Owner:** Statistics · **Task:** TASK-029 · **Status:** FROZEN, 2026-08-16

**Run scored:** `task-015-official-20260816-015` — the first `TASK-017`-compliant blind discovery
run (issued/verified/launched/frozen through `blind/`'s deterministic, networkless pipeline;
committed via signed receipt before `hidden_ground_truth.json` was opened for anything beyond this
scoring pass). Validated under validation contract **v1.1.0** (ADR-014/ADR-015 — the G05 fix).
Scored by `TASK-028` (`scripts/evaluate_benchmark.py`,
`artifacts/evaluation/task-028-benchmark-evaluation.json`).

This report does not edit `docs/benchmark/decision-gate.md`'s pre-registered sections — only its
"Post-benchmark comparison" table is appended to, separately.

## 1. What ran

- **Discovery:** 15 candidates persisted from 6,945 evaluated hypotheses, fit on `development`
  only, `status=PERSISTED`. Every candidate condition uses only `DECISION_TIME` features
  (`discount_rate`, `manual_exception`, `quoted_cost_eur`, `booking_lead_days`,
  `customer_price_eur`, `trip_duration_days`, `product_category`) — no manager, supplier,
  acquisition_channel, or payment_method appears in any candidate condition.
- **Validation:** all 16 gates, all 15 candidates, contract v1.1.0. **6 candidates PASS
  (`adjusted_observational_association`, `SHADOW_POLICY`); 9 DOWNGRADE
  (`descriptive_observation`, `EXPERIMENT_ONLY`).** None REJECT. Frozen at
  `artifacts/validation/task-019-official-20260816-015.json`.
- **Evaluation:** `hidden_ground_truth.json` opened only now, after both commitments above were
  already frozen. Restricted SHA-256 `5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506`
  (matches `HANDOFF-030`'s accepted artifact).

## 2. The six metrics

| # | Metric | Result | Band |
|---|---|---|---|
| 1 | Top-10 precision | **90%** (9/10) | STRONG (≥60%) |
| 2 | Economic-weighted recall | **45.2%** | PROMISING (25–49%) |
| 3 | Confounder trap rejection | 0/5 promoted, but see §4 | PROMISING (see caveat below) |
| 4 | Leakage violations | **0** | passes (hard-disqualifier floor) |
| 5 | Effect direction accuracy | **100%** (3/3 validated+matched) | STRONG (100%) |
| 6 | Economic impact estimation error | **median 204%** (69–380% range) | **FAILED** (>100%) |

Hard disqualifiers: none fired (leakage = 0; no trap promoted; no wrong-direction validated
finding). **Overall verdict is therefore driven by the weakest graded band, not a disqualifier:
metric 6 alone puts the overall verdict at FAILED**, regardless of how the "four vs. six metrics"
wording ambiguity in `docs/benchmark/decision-gate.md` (flagged in `HANDOFF-027`'s resolution) is
read — FAILED is the floor under every reading that includes metric 6.

### Ranking substitution, disclosed

`TASK-016` (candidate ranking) has not run. Top-10 selection here uses `economic_exposure`
(as self-reported by discovery) descending, as a documented stand-in — not `TASK-016`'s eventual
output. This is a real substitution, not a methodology gap: `economic_exposure` is a legitimate,
deterministic field in the candidate contract, just not the multi-factor ranking `TASK-016` is
scoped to produce.

## 3. Metric-by-metric detail

### 3.1 Top-10 precision — STRONG

9 of the top 10 candidates by reported economic exposure recover a real pattern (≥50% recall of
that pattern's `affected_booking_ids`, the preregistered matching statistic — see
`scripts/evaluate_benchmark.py`'s module docstring for why recall, not Jaccard, was chosen, and
that the 0.5 threshold was fixed before any overlap was computed). Only `CAND-007` (best recall
37%, below threshold) misses. This is a genuinely strong result: discovery's top-ranked candidates
by its own exposure metric are overwhelmingly not noise.

### 3.2 Economic-weighted recall — PROMISING

Of the 7 scoreable patterns (P01–P04, P06, P08, P09; P05/P07 excluded per the pre-registered
denominators), only **P01 and P06** are recovered by any validated (≥`predictive_association`)
candidate. **P02, P03, P04, P08, and P09 are not recovered at all** — no candidate's exposed
population reaches 50% recall of any of them. Recovered impact: €141,765 (P01) + €135,891 (P06) =
€277,657 of €510,081 total scoreable impact = 45.2%.

This is consistent with what the candidate conditions look like: every candidate is built from
`discount_rate`, `customer_price_eur`, `booking_lead_days`, and similar generic pricing/lead-time
features. P01 (BlueWing discount+short-lead) and P06 (Tokyo urgent bank-transfer) both involve
`discount_rate`-adjacent or lead-time-adjacent conditions that a generic "high discount" or
"short lead" rule partially subsumes. P02 (Zanzibar family summer), P03 (installment risk),
P04 (Atlas long winter), P08 (solo luxury long-lead), and P09 (DeltaSun autumn groups) each depend
on destination, party size, season, or supplier conditions the search never combined with the
discount/price/lead-time features it favored.

### 3.3 Confounder trap rejection — PROMISING, not STRONG, and here is exactly why

**No candidate condition matches any trap's `apparent_feature`** (`manager`, `supplier`,
`acquisition_channel`, `payment_method` never appear in any of the 15 candidates' conditions at
all; the one near-miss, `manual_exception`, appears only as `== False`, the *opposite* polarity
from trap T05's `== True`). So hard disqualifier 2 does not fire, and by the letter of the rule
("any trap promoted → FAILED") this run passes.

But `docs/benchmark/decision-gate.md`'s STRONG band for this metric requires "5/5 rejected **or
clearly downgraded**, **each with a stated confounding caveat**." There is no candidate to attach
a caveat to for any of the 5 traps — they were never proposed, so validation never had an
opportunity to actively catch and downgrade one. This is a materially weaker claim than "gate G06
correctly identified and downgraded a trap-shaped candidate," even though the practical outcome
(no trap promoted) is identical. Reported here as **PROMISING**, not STRONG, to avoid overstating
a result that is partly luck-of-the-search-space rather than demonstrated rejection.

The closest active analog: all 6 PASS candidates did independently clear gate G06 (manager ×
supplier stratified confounding adjustment) as part of ordinary `TASK-019` grading — so the
adjustment machinery this benchmark exists to stress-test was exercised and survived, just not
against a candidate that structurally resembles one of the 5 named traps.

### 3.4 Leakage violations — 0, passes

Every candidate's condition features are `DECISION_TIME` (gate G01, all 15 pass). No hard
disqualifier fires here.

### 3.5 Effect direction accuracy — STRONG

All 3 validated candidates that matched a pattern (`CAND-004`, `CAND-009`, `CAND-010`, all
matching P01 and/or P06) show the correct harmful direction (negative raw effect, matching
`decrease_is_harm`). 3/3 = 100%. (The other 3 PASS candidates — `CAND-007`, `CAND-012`,
`CAND-015` — did not reach the 50% recall matching threshold against any pattern and are excluded
from this metric by definition, not counted as errors.)

### 3.6 Economic impact estimation error — FAILED, and the mechanism is diagnosable

Median relative error **204%** (individual values: 69% per-booking-equivalent... see below —
headline figures are 380%, 45%, 204% on *total* reported exposure vs. matched ground-truth
impact). This is the run's dominant weakness and the reason the overall verdict is FAILED.

**Mechanism, verified directly:** the matched candidates' exposed populations are far larger than
the true patterns' affected populations —

| Candidate | Matched pattern(s) | Candidate exposed N (full cohort) | Pattern affected N | Candidate harm/booking | True effect/booking |
|---|---|---|---|---|---|
| CAND-004 | P01 | 2,239 | 142 | €311 | €998 |
| CAND-009 | P01, P06 | 1,596 | 142 + 134 | €246 | ~€1,006 |
| CAND-010 | P01 | 2,176 | 142 | €201 | €998 |

Each candidate's rule (e.g. `customer_price_eur < 3818 AND discount_rate ≥ 0.12`) captures roughly
15–16× more bookings than the exact injected pattern. This **dilutes** the per-booking effect
(candidates report 20–31% of the true per-booking harm — a large *underestimate* per booking) but
**inflates total exposure** (candidates report 2–4.8× the true total impact — a large *overestimate*
in aggregate), because the much larger population multiplies even a diluted mean into a bigger sum.
Both distortions are the same mechanism viewed from two angles: **the discovered rules are real and
correctly signed, but far broader than the exact causal mechanism, so neither the per-booking nor
the total-exposure number is a clean estimate of any single pattern's true effect.**

This is not the same failure mode as a wrong-signed or fabricated number — direction is correct
(§3.5) and the qualitative finding ("bookings meeting these conditions lose money") is real. It is
a **granularity** problem: interpretable conjunction-of-conditions discovery, tuned to maximize
exposure/support on the development split, tends to find rules broader than any single injected
mechanism, and this benchmark's economic-impact reporting (`TASK-023`, `G15` in the validation
engine) reports impact over the candidate's own population, not an isolated per-pattern
attribution — there is currently no step that separates "how much of this rule's exposure is
attributable to the specific subpopulation it overlaps with a known pattern" from "how much is the
rest of the rule's (still real, still harmful-on-average, but less severe) coverage."

## 4. Assessment: is this a fixable defect or a core-approach limitation?

Per `docs/benchmark/decision-gate.md`'s FAILED action: *"If Statistics/ML Discovery attribute the
failure to a fixable defect (bug, missing input, mis-specified split) — fix and rerun once."*

**Statistics' assessment:** this looks like a fixable, specific defect in economic-impact
granularity, not a limitation of the discovery mechanism itself. The evidence for that reading:

- Direction is 100% correct and Top-10 precision is 90% — the mechanism is finding real,
  correctly-signed signal, not noise.
- The estimation-error mechanism is fully diagnosed above (population-size dilution/inflation),
  not a mystery requiring a different discovery paradigm.
- A concrete remediation exists at the estimation layer without touching discovery's search
  algorithm: report a **range** bounded by (a) the current whole-rule exposure and (b) an
  attribution-narrowed exposure restricted to the subpopulation actually overlapping a matched
  pattern, and require both in any future finding presented as an impact estimate — this is a
  `TASK-021`/`TASK-023` refinement, not a `TASK-015` rewrite.

This attribution is **Statistics' half only**; `docs/benchmark/decision-gate.md`'s own text
requires ML_DISCOVERY's concurrence before the "fix and rerun once" path is authorized rather than
treating this as the first of two failures toward the core-approach-change trigger. Carried as
`HANDOFF-043` (new) to ML_DISCOVERY and FOUNDER_STRATEGY.

## 5. Overall verdict

**FAILED** (via weakest-graded-metric, not a hard disqualifier).

Per `docs/benchmark/decision-gate.md`: do not proceed to real customer data. Pending
ML_DISCOVERY's concurrence (§4), this is treated as a single, diagnosed, plausibly fixable
failure — not (yet) the two-strikes trigger for changing the core discovery approach.

## 6. What this run does establish

Despite the FAILED verdict, several things worth stating plainly, because a benchmark's value is
in what it reveals, not just the verdict letter:

- The full pipeline — blind discovery → validation (16 gates, v1.1.0 G05 fix live and exercised
  for the first time on a real, non-trivial result) → ground-truth scoring — ran end to end for
  the first time, deterministically, reproducibly, without a single hidden-ground-truth access
  before commitment.
- Discovery recovers real, correctly-directed, non-trap signal at useful precision (90% top-10,
  100% direction). The core mechanism is not producing noise.
- The identified weakness is specific and has a named, scoped fix path, not a diffuse "try
  something else."
