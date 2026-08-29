# TASK-075 — Forensic trace: why `T03` cleared `G00`–`G14` and reached `shadow_policy`

**Status: POST-HOC DIAGNOSTIC throughout, diagnosis only.** Every number here is produced by the
real, unmodified `policy_analytics.validation.apply` (`run_validation`, `_adjustment_pool`,
`_binned_adjustment_frame`, `_select_adjustment_columns`, `_stratified_adjustment`) called against
the already-frozen, `HANDOFF-075`-confirmed `task-073-official-20260829-001`. Nothing here is a new
official run, changes any frozen artifact, or touches `discovery.engine`, `apply.py`, or
`validation-contract.md`. **This task does not propose, scope, or design any fix, gate change,
threshold change, or eligibility change** — see §5 for exactly what is, and is not, being handed to
a future fix-design task. Raw computed output:
`docs/benchmark/task-075-t03-forensic-trace-raw.json`, produced by
`scripts/diagnose_task075_g06_confounding_coverage.py`.

**Fidelity, asserted not assumed, before anything below was reported:** (1) the frozen
`task-073-official-20260829-001.candidates.json`'s SHA-256 matches its own `hashes.json` entry
(`746be113a3…638144`); (2) the repository's `travel-bookings-analytical-v1.1.0` copy is byte-identical
(SHA-256, all four partitions checked) to the copy inside the frozen blind workspace this run
actually used; (3) a fresh `run_validation()` call reproduces `CAND-014`'s and `CAND-015`'s
`adjustment_columns_used`, `confounder_stratum_coverage`, and `policy_readiness` exactly against the
already-committed `artifacts/validation/task-019-official-20260829-task-073-001.json`. All three
checks pass (script output, reproduced in the raw JSON's `fidelity_checks_passed`).

## 0. What this task is answering

`task-073-official-20260829-001` promoted `CAND-014` (`acquisition_channel==paid_search AND
discount_rate>=0.08`) to `shadow_policy` at `adjusted_observational_association` with zero matched
true pattern (`best_pattern_recall=0.456`). `CAND-014` literally contains trap `T03`'s
`apparent_feature` (`acquisition_channel=paid_search`, `hidden_ground_truth.json`) and none of the
7 scoreable true patterns' conditions. This is the first clean confounding-trap promotion in this
project's official benchmark history. `HANDOFF-075` surfaced one concrete lead: `installments` — one
of `T03`'s three true `confounded_by` variables (`customer_type`, `discount_rate`, `installments`)
— is in `CAND-014`'s `adjustment_columns_considered` but not `adjustment_columns_used`. This
document traces *why*, mechanistically, gate by gate, and asks whether the same mechanism threatens
the other four traps.

## 1. Full gate-by-gate trace of `CAND-014`

Reproduced fresh (fidelity check 3 above), not merely re-read from the frozen artifact:

| Gate | Outcome | What it checked, and the real computed value |
|---|---|---|
| G00 Lineage | PASS | Candidate is `PERSISTED` with a resolvable dataset/outcome reference. |
| G01 Target leakage | PASS | Both condition features (`acquisition_channel`, `discount_rate`) are `DECISION_TIME`. |
| G02 Post-treatment controls | PASS | Adjustment set excludes the candidate's own two condition features — correctly, by construction (§2 below explains what this exclusion costs here). |
| G03 Sample adequacy | PASS | `n_exposed=645`, `clusters=2834`, `MDE80=88.5` EUR vs. observed harm `217.7` EUR — well powered. |
| G04 Uncertainty | PASS | 95% CI `[160.4, 278.7]` EUR — does not cross zero. |
| G05 Multiple comparisons | PASS | Normal-approx p `3.47e-13`, BH-adjusted p `1.28e-09` over `family_size=33085` — nowhere near marginal. |
| **G06 Confounding** | **PASS** | Adjusted for `(customer_type, manual_exception, customer_segment, party_size, payment_method, product_category)`: harm `217.7 → 209.0` EUR, attenuation `0.04`, coverage `0.73`, E-value `1.90` (floor `1.5`). **This is the gate that should have caught `T03` and, mechanically, could not — see §2.** |
| G07 Selection/collider | PASS | Zero missingness on either side. |
| G08 Survivorship | PASS | Full eligible cohort. |
| G09 Simpson | PASS | Sign reverses in strata covering `0.0%` of exposure (floor `20%`) — no heterogeneity reversal. |
| G10 Temporal stability | PASS | Same sign in all three splits; holdout retains `116%` of development magnitude. |
| G11 Seasonality | PASS | Max monthly concentration ratio `1.17` (threshold `1.5`). |
| G12 Robustness | PASS | 100% sign agreement over 11 perturbations (floor `90%`); max magnitude deviation `43%` (ceiling `50%`) — the `TASK-070`-fixed one-bin-relative semantics, not the pre-fix defect. `installments`/`discount_rate` play no role in G12; this gate is not implicated. |
| G13 Identification design | FAIL (expected) | Observational, no quasi-experimental design — caps evidence at level 3, exactly the contract's own disclosed ceiling for observational data. |
| G14 Randomization | FAIL (expected) | No prospective randomization — same expected ceiling. |
| G15 Economic materiality | PASS | Combined-window exposure 95% CI `[229826, 349149]` EUR, `4.945%` of outcome. |

Every gate ran at **full statistical power** in the `docs/benchmark/real-data-decision-gate.md` §1
sense — none of G03/G04/G05/G09/G10/G11/G12 silently narrowed for lack of sample. **G06 is the one
gate whose own internal *coverage-gated adjustment-set selection* narrowed** — not from a lack of
overall sample (`n_exposed=645`, `n_comparison=4354`, both ample), but from a mechanical property
of its own selection rule, detailed next. No other gate is implicated: `CAND-014` clears G01–G12 on
its own genuine statistical merits, at `adjusted_observational_association`
(`shadow_policy` follows automatically per §7's table — level 3, material, feasible).

## 2. Why G06's coverage gate dropped `installments` — traced, not assumed

`docs/analytics/validation-contract.md` §4b: the adjustment pool is every manifest-declared
`adjustment_eligible` `DECISION_TIME` feature outside the candidate's own condition features (16
declared, minus `acquisition_channel`/`discount_rate` = 14 pool columns for `CAND-014`). Numeric
columns with more than 6 distinct development-split values are quartile-binned to 4 groups
(`ADJUSTMENT_QUANTILE_BINS`); columns are tried **in ascending order of their own binned
distinct-value count** (ties alphabetical), each added only if the running joint stratification's
`confounder_stratum_coverage` stays at or above `0.50`.

Reproducing that selection exactly for `CAND-014` (development split: 645 exposed, 4354 comparison):

| Step | Column added | Cardinality (binned) | Coverage after adding | Kept? |
|---|---:|---:|---:|---|
| 1 | `customer_type` | 2 | 1.0000 | yes |
| 2 | `manual_exception` | 2 | 1.0000 | yes |
| 3 | `customer_segment` | 3 | 0.9860 | yes |
| 4 | `party_size` | 3 | 0.9736 | yes |
| 5 | `payment_method` | 3 | 0.9116 | yes |
| 6 | `product_category` | 3 | **0.7271** | yes |
| 7 | `booking_lead_days` | 4 | 0.3070 | **no** |
| 7′ | `customer_price_eur` | 4 | 0.4248 | no |
| 7″ | **`installments`** | **4** | **0.4434** | **no — below the 0.50 floor** |
| 7‴ | `quoted_cost_eur` | 4 | 0.4295 | no |
| 7⁗ | `supplier` | 4 | 0.3380 | no |
| 7‴′ | `trip_duration_days` | 4 | 0.3349 | no |
| 8 | `destination` | 5 | 0.2682 | no |
| 9 | `manager` | 8 | 0.1178 | no |

`installments` is not dropped for a `DECISION_TIME`-classification reason, and not for a
data-quality reason — it is genuinely `DECISION_TIME`, genuinely in `adjustment_columns_considered`,
and its own trial coverage (`0.4434`) is computed correctly. **It loses by 0.0566 of coverage,
tried seventh, at a point where the running joint stratification (6 already-selected low-cardinality
columns) has already consumed the coverage budget down to `0.7271` — one column's worth of headroom
above the `0.50` floor.** Cell-count confirmation: at 6 columns, the joint stratification has 210
distinct cells, of which 41 clear `MIN_STRATUM_CELL=5` on both sides; adding a 7th column (any of
them — `booking_lead_days` shown) grows the joint space to 605 cells while the number of *usable*
cells **falls** to 28 — the 645 exposed records get spread across more cells than before, and most
of the new cells are too thin to count. This is `docs/analytics/validation-contract.md` §4b's own
documented mechanism ("each additional column multiplies the number of joint strata by roughly its
own cardinality") operating exactly as designed — `installments` is not an edge case or a defect in
the gate's arithmetic, it is the gate's designed behavior landing on a column that happens to be a
true confounder.

**`discount_rate` (`T03`'s second confounder) never reaches this table at all.** `CAND-014`'s own
condition is `acquisition_channel==paid_search AND discount_rate>=0.08` — `discount_rate` is one of
the candidate's own two defining conditions, so `_adjustment_pool` excludes it before ordering ever
runs (G02's circularity guard: adjusting for the exposure's own defining variable is circular, and
this is correct in general). **This exclusion is not load-bearing for the failure, though** — traced
counterfactually against `T03`'s *pure* `apparent_feature` alone (`acquisition_channel==paid_search`,
no `discount_rate` compounding, so `discount_rate` *is* back in the pool), `discount_rate` is tried
8th at cardinality 6 and rejected at coverage `0.0622` — dropped by the identical coverage-floor
mechanism, not rescued by being eligible. Only `customer_type` (cardinality 2) survives in either
version. **Of `T03`'s three true confounders, one (`customer_type`) is low-cardinality and always
survives; the other two are dropped — one by direct coverage-floor rejection (`installments`,
in both the real and the counterfactual-pure trace), one by a structural exclusion that turns out
to be redundant with the same coverage-floor mechanism it would hit anyway.** G06 reports `PASS`
with `coverage=0.73` because that number describes the six columns it *did* select, not the
confounders it needed and did not.

## 3. The general mechanism (the deliverable this task exists to produce)

Not "why `paid_search`/`discount_rate` slipped through" — the property is:

**G06's adjustment-set selection orders candidate covariates by a purely mechanical property (their
own marginal cardinality in the development split) and stops permanently at the first covariate
whose joint addition would drop `confounder_stratum_coverage` below its fixed floor. Nothing in the
selection rule scores a covariate by its relevance to the candidate's exposure–outcome relationship
— cardinality determines try-order, and remaining sample coverage determines the stop point, and
those are the only two inputs. A true confounder is invisible to G06 exactly when (a) it is numeric
or otherwise higher-cardinality than enough of the rest of the eligible pool that it sorts late in
try-order, and (b) the pool contains enough lower-cardinality covariates — true confounders or pure
nuisance variables, the rule cannot tell them apart — to consume the coverage budget down near the
floor before the confounder's turn arrives. This is a joint property of one covariate's own
cardinality and the composition of the rest of the pool, never a property of whether that covariate
actually explains any of the association.**

Concretely, on this dataset: 4-of-16 adjustment-eligible columns are naturally low-cardinality
(2–3 levels: `customer_type`, `manual_exception`, `customer_segment`, `payment_method`,
`product_category`, and low-raw-cardinality numerics like `party_size`), and every remaining numeric
column above 6 raw distinct values collapses to exactly 4 bins under `ADJUSTMENT_QUANTILE_BINS` —
so 6 causally unrelated numeric columns (`booking_lead_days`, `customer_price_eur`, `installments`,
`quoted_cost_eur`, `supplier`, `trip_duration_days`) all tie at cardinality 4 and compete for
whatever coverage headroom the low-cardinality run left behind. Once ~6 low/mid-cardinality columns
have already been selected, coverage sits, by construction of a greedy stop-as-soon-as-you-breach
rule, *just above* the 0.50 floor — leaving essentially no slack for the next column, whichever one
it happens to be. This is a **cardinality cliff**: it is not that `installments` specifically is
hard to adjust for, it is that *anything* tried at that point in the order is likely to fail,
because the rule's stopping condition guarantees the selection halts right at the edge of
infeasibility rather than with room to spare.

This is the general shape the fix-design task named in `ADR-069` Branch 1 must derive from — never
a rule keyed on `installments`, `discount_rate`, `paid_search`, or `T03`'s identity.

## 4. Isolated to `T03`, or systematic? — checked empirically across all five traps

`T01`, `T02`, and `T05` have **never appeared as a persisted candidate in any official run in this
project's history** (`TASK-022`'s original 0/5 finding, reconfirmed here:
`task-073-official-20260829-001`'s own evaluation records
`trap_appeared_as_candidate: {T01: false, T02: false, T03: true, T04: true, T05: false}`). There is
no real candidate to trace for them. Per this task's own scope item 3 ("whether they simply haven't
been tested under a configuration that would expose it yet"), each trap's own `apparent_feature` was
traced counterfactually as a single-condition rule through the *same, real, unmodified* G06 selection
code (never a re-implementation) — exactly the discipline `diagnose_oracle_decomposition.py`'s stage
6 already established for this project. Full detail in the raw JSON; summary:

| Trap | Confounded-by (ground truth) | Real candidate this run? | Fate under G06 (real, or counterfactual if noted) |
|---|---|---|---|
| **T01** | `destination`, `booking_lead_days`, `party_size`, `trip_duration_days` | none, ever — counterfactual | `party_size` (card 3) survives; `destination`, `booking_lead_days`, `trip_duration_days` (all card 4–5) dropped by the coverage floor at step 7+, identical shape to `T03` |
| **T02** | `trip_duration_days`, `booking_month` | none, ever — counterfactual | `trip_duration_days` dropped by the coverage floor; `booking_month` is **not even in the manifest's `adjustment_eligible` pool** — no column of that name exists in the analytical schema at all (only `travel_month`, itself excluded as a calendar-derived field per §4b's own disclosed scope limit) — a second, independent gap, structural rather than coverage-driven |
| **T03** | `customer_type`, `discount_rate`, `installments` | yes, `CAND-014` — **promoted, clean** | `customer_type` survives (low cardinality); `installments` coverage-dropped; `discount_rate` structurally excluded (own condition) *and*, per the counterfactual check in §2, would also be coverage-dropped |
| **T04** | `booking_lead_days`, `destination` | yes — `CAND-007` (genuine `P06` recovery, not a trap escape) and `CAND-015` (ambiguous, promoted) | `CAND-007`: both confounders are literally `CAND-007`'s own condition features (the search found the true narrow rule, so restriction substitutes for adjustment) — structurally excluded, correctly harmless. `CAND-015`: **both confounders coverage-dropped**, identical mechanism to `T03` — `CAND-015` is saved from being a second clean false positive only because it happens to overlap `P06` (`best_pattern_recall=0.69`), not because G06 caught it |
| **T05** | `destination`, `party_size`, `trip_duration_days`, `booking_lead_days` | none, ever — counterfactual | `party_size` survives; the other three (`destination`, `trip_duration_days`, `booking_lead_days`) coverage-dropped — identical shape to `T01` (same confounder set) |

**Not isolated to `T03`. Systematic, and confirmed on real data, not only by inspection or
counterfactual construction:** the one other trap that has ever produced a real persisted candidate
in an official run (`T04`) hit the *exact same failure* in the *exact same run* — its true
confounders coverage-dropped from `CAND-015`'s adjustment set — and was saved from being a second
clean disqualifying promotion only by an unrelated coincidence (accidental overlap with a true
pattern), not by any gate working as intended. The three traps with no real candidate yet
(`T01`, `T02`, `T05`) were traced through the same unmodified code on their own literal
`apparent_feature` condition, and every one of them loses at least one true confounder to the
identical coverage-floor mechanism; `T02` carries a second, independent structural gap
(a confounded_by variable absent from the adjustment-eligible pool entirely). The one column
consistently exempt across all five traps — `party_size` — is exempt for the same general reason
`customer_type` is in `T03`: it is low-cardinality, not because it is somehow a "safer" trap.

## 5. What a future fix-design task would need to cover (named, not designed, per this task's hard rule)

This section names scope, per `ADR-069` Branch 1 and this task's own instruction — it is not itself
a proposal, and no threshold, rule, or eligibility change is suggested here.

- A replacement selection criterion would need to score a candidate adjustment covariate by
  something other than, or in addition to, its own marginal cardinality — the current rule cannot
  distinguish a covariate likely to explain confounding from one that merely happens to be cheap to
  add, because it never looks at the covariate's relationship to exposure or outcome at all. Any such
  criterion must remain a property of the covariate and the sample, computed identically for every
  candidate and every dataset, per this contract's own existing discipline (§4b: "no gate logic
  anywhere in this method references `T03`... by name").
- It must be validated against **negative controls**: the 6 real `PASS` candidates in
  `task-073-official-20260829-001` that reached `shadow_policy` on true patterns and must continue
  to pass, plus `CAND-007`'s correct, structurally-exclusion-based handling of `T04`.
- It must be validated against **positive controls**: `T01`, `T02`, `T03`, `T04`, `T05` all, not
  `T03` alone — since §4 shows every trap is vulnerable in the same way, a fix validated only
  against `T03`/`installments` risks re-deriving a `T03`-shaped patch by accident even without
  naming it. `T02`'s independent, non-coverage gap (`booking_month` absent from the adjustment-
  eligible pool) is a distinct defect a coverage-selection fix alone would not touch, and needs its
  own explicit disposition.
- It must address the structural-exclusion side of §2 separately from the coverage-floor side: a
  confounder that a search stage folds into a candidate's own condition set is invisible to G06 by
  construction (G02's circularity guard, operating correctly for its own stated purpose), and this
  is a different mechanism from the coverage floor even though, per §2's counterfactual check, it is
  not load-bearing for `T03` specifically. Whether and how the two interact in a case where a
  structurally-excluded confounder would *not* also fail on coverage is untested here and worth this
  future task's own explicit check.
- Per `TASK-070`'s own precedent (multi-domain non-regression), any fix should be measured across
  more than travel before being trusted — the cardinality cliff in §3 is a property of *this
  dataset's* covariate-cardinality composition (a handful of low-cardinality categoricals against a
  wall of quartile-binned numerics), and a differently-composed dataset could exhibit a differently
  shaped version of the same general mechanism.

## 6. What this task did not do

No threshold in `ValidationThresholds` was read as wrong, no gate's rule was called a defect, and no
replacement selection rule is proposed, sketched, or implied above beyond the shape named in §5. G06
reported `PASS` and `coverage=0.73` truthfully, for the six columns it selected; the gap is that its
own selection process, applied faithfully, does not guarantee the columns it selects are the ones
that matter, and this is disclosed already, in general terms, in
`docs/analytics/validation-contract.md` §11 ("A confounder requiring more covariates than a given
candidate's sample can jointly support remains invisible to G06... not from any judgment about which
confounders matter more"). What this task adds is not a new limitation but a concrete, reproduced,
cross-trap demonstration of exactly how and how often that already-disclosed ceiling binds in
practice on real official-run data.
