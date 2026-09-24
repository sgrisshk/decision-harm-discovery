# TASK-105 Phase 2b-0 — Contract freeze for the categorical-only `G17` (specification only)

**Owner:** STATISTICS (lead), ARCHITECT (support). **Recorded:** 2026-09-25. **Status:** SPECIFICATION ONLY. Nothing in
`engine.py`, any gate, `apply.py`, `contract.py`, `grading.py`, `report.py`, `input_contract.py`, the generator, the
catalogue, any threshold, `ADR-100`/`ADR-101`/`ADR-102`, or the frozen `TASK-102`/`ADR-097` text was changed. **No
mechanism code exists and no run of any kind was made for this document** (no fixture, no simulation, no measurement).
Every prediction in Section 9 is registered before any 2b run exists and is frozen by the commit of this file; a change
after a result is seen is a new dated version, never an edit.

**Binding text (read in full):** `ADR-102` (overrides the attenuation/E-value/`D` parts of the design), `ADR-101`
(A1-A9), `ADR-100`; the design `docs/analytics/task-105-k1-confounding-protection-design.md` (Revisions 1-2, Sections
9-11, Q1-Q17); the real code under `packages/analytics/src/policy_analytics/validation/` (`contract.py`, `apply.py`,
`grading.py`, `report.py`, `input_contract.py`) and `discovery/engine.py`; `docs/analytics/validation-contract.md`; the
`ADR-064`/`TASK-070` versioning precedent and the `G16`/`TASK-081` precedent. Line citations are to this worktree at
commit `02a7616`.

**Where this document supersedes the design.** `ADR-102` removes the attenuation percentage (`max_adjusted_attenuation
= 0.50`), the E-value branch, the `D_att`/`D_E` statistics, the Bonferroni family and `alpha_k1`, and the numeric-`Z`
stratification from the *blocking* mechanism. Those parts of design Sections 2.4, 2.6, 9.1-9.5 and 11.1 are replaced by
the specification below. Design text not contradicted here (single-`Z`, per-candidate scope, declaration semantics,
attribution, versioning concept) is carried forward and re-stated so the freeze is self-contained.

---

## 0. How to read this document

Every item is in exactly one of two states:

- **[C] Constant.** A value or rule that already exists in the statistical/validation contract or code (exact
  file:line or ADR clause cited), **or** a mechanical consequence of cited constants with **no free parameter** (the
  derivation is shown so the reviewer can check nothing was chosen; marked **[C-derived]**). No value here was picked
  by looking at any fixture or run.
- **[O] OPEN FOUNDER DECISION.** Options and consequences are stated neutrally; **no option is chosen**; each is
  numbered `F1..F7` and `F9` (`F8` is unused: it was merged into `F4a` before commit) and collected in Section 11.

**Rule for undecided items.** Until the founder decides an [O] item, the implementation may not choose. The
**fail-closed default in force** for each [O] item is stated where it arises; it is the no-op / narrowest setting, it is
not a recommendation, and the founder's decision can only replace it. **`F1`, `F2`, `F3a`, `F3b`, `F4`, `F5`, `F9` are
BLOCKING for the start of 2b code** (they change what the gate computes or reports); `F3c`, `F6`, `F7` are not.

**No new numeric constant.** `G17` as specified introduces **zero** new numeric constants; every number it uses is an
existing contract/code constant (register in Section 12). A static test (U12, Section 9.1) asserts this. That is the
mechanical reason `ValidationThresholds` needs no new field (Section 7).

---

## 1. Evaluation split (item 1)

### 1.1 Constants

| # | Item | Class | Value | Citation |
|---|---|---|---|---|
| 1.a | Split names and order available to validation | [C] | `development`, `validation`, `future_holdout` (chronological, from the manifest `temporal_splits`; counts on the delivered travel dataset 4,999 / 2,462 / 2,539) | `apply.py:106` (`SPLITS`); manifest `temporal_splits`; `validation-contract.md` §3 (row "Chronological development / validation / future-holdout splits") |
| 1.b | Evaluation split for `G17` | [C] | **`validation`** only. Every `G17` estimate, interval, `p`-value and criterion is computed on `validation` rows only | `ADR-101` A8 ("preferably the existing held-out validation split"; "selecting `Z` on held-out and confirming on the same held-out is not independent"); `ADR-102` (independent evaluation split; freeze fixes it) |
| 1.c | What may be fitted on other splits | [C] | Nothing outcome-dependent. With categorical-only `Z` there are **no bin edges** (raw levels), so no quantity is fitted on `development`; the `Z` pool is a function of (declaration, exposure column) only (Section 2, U1) | `ADR-101` A2/A8; design 2.2 (pool purity) |
| 1.d | Matched-strata rule | [C] | The evaluation rows are restricted, per `Z`, to the usable strata of that `Z` (Section 3.2). Crude, matched-crude and adjusted are all reported (Section 8) | `ADR-102` Q17 |
| 1.e | Pooled `validation ∪ future_holdout` | [C] | **Not binding.** May be computed and reported as a labelled, non-binding sensitivity only; it never enters a gate outcome | design 2.5 (registered as non-binding sensitivity) |
| 1.f | Other `G17` inputs from other splits | [C] | `G17` does not read `development` or `future_holdout` outcomes at all (U3). The existing gates that do (`G03`-`G06`, `G10`, `G15`) are unchanged | design 2.6; `apply.py:516-529, 567-641, 741-757, 880-913` |

### 1.2 Independence of the split from candidate selection (disclosed, reused, not re-litigated)

What the code shows (all cited findings are from design 2.5 and re-verified against source here):

1. `discover_candidates` searches on `development` only; but `_prepare` calls `_temporal_consistency`
   (`discovery/engine.py:510-527`), which takes the **sign** of the raw harm on `validation` and `future_holdout`
   (`consistency` = share of later splits with harm `> 0`), and feeds `effective_score = raw * (1 + stability_credit_weight
   * consistency)` into top-K selection (`engine.py:530-541`, `stability_credit_weight = 0.5` at `engine.py:238`,
   used at `engine.py:957-959`). So one bit per later split (raw-harm sign) leaked into selection through a multiplier
   `<= 1.5`.
2. `G10` conditions promotion on the raw effect in **all** splits: same sign in `development`, `validation`,
   `future_holdout` and `future_holdout` retention `>= min_holdout_effect_retention` (0.50) of the development
   magnitude (`apply.py:741-757`; `contract.py:256`). Therefore any candidate on the promotion path has, by
   construction, a **positive raw harm on `validation`**, and `future_holdout` additionally carries a **magnitude**
   condition (retention), a stronger dependence than `validation` has.
3. The size of any `validation` effect, any `Z`, any adjusted estimate, and this gate were **not** inputs to selection.

**Statistical consequence (stated as a limitation, not resolved):** conditioning on "raw harm `> 0` on `validation`"
biases the observed `validation` crude estimate upward (a sign-selection effect), and the adjusted estimate shares
that sampling noise (same rows). Direction of the bias in the mechanism's decision: toward not blocking (a crude
effect selected to be positive is less likely to look "lost" after adjustment). No fully independent split exists in
the delivered data (a closed 24-month set).

**What ADR-102's "independent evaluation split" requires, made checkable.** (i) `G17` reads `validation` rows only
(U3); (ii) the `Z` pool and its declaration are fixed before the candidate is evaluated and are not functions of any
outcome (U1); (iii) no `G17` quantity is fitted on the evaluation rows and then confirmed on them (categorical-only
`Z` makes this vacuous: raw levels are not fitted); (iv) the run manifest records the evaluation split
(`k1_evaluation_split = "validation"`). What it cannot require, because the repo cannot provide it: independence
from selection. That residual is founder decision **F1**.

### 1.3 OPEN — F1 (evaluation split acceptance; residual of Q1/Q2)

`ADR-101` A8 says "preferably"; the freeze must fix a split; the disclosed partial independence (1.2) is a fact of the
delivered engine/contract, not a choice. Options (neutral):

| Option | What it is | Consequence |
|---|---|---|
| **F1-a** | Accept `validation`-only with the disclosed partial independence (as in 1.b) | Leaves `future_holdout` un-consumed by any new decision gate (it remains the headline-backtest split, `validation-contract.md` section on backtest, "Out-of-period first"); statistical power is that of `n = 2,462` rows; the sign-selection bias of 1.2 stays and is disclosed in every claim |
| **F1-b** | Use `future_holdout` only | Consumes the split that `G10` conditions on by *magnitude* (retention) as well as sign — a stronger selection dependence than `validation`; consumes the final untouched split |
| **F1-c** | Use pooled `validation ∪ future_holdout` as binding | About `1/sqrt(2)` the standard error (`n = 5,001`); consumes the final split; both later-split dependences of 1.2 apply |
| **F1-d** | Require an engine setting for the graded version so that later splits do not influence selection (`stability_credit_weight = 0.0`, which `engine.py:530-541` documents as returning `raw_score` exactly) | Removes the sign-selection leak (not the `G10` conditioning); is an accepted-default change under `ADR-070` custody, i.e. an engine change **outside** this task's scope and a new engine version |

**Fail-closed default in force until decided:** F1-a's *mechanics* (`validation` only) so that 2b can be specified,
with the partial-independence statement mandatory in every claim (Section 8). This is the ADR-101 A8 named
preference, not a founder ratification; the founder may replace it.

---

## 2. Adjustment pool (item 2)

### 2.1 Constants

| # | Item | Class | Value | Citation |
|---|---|---|---|---|
| 2.a | Outer bound of any pool | [C] | `Z` must be `DECISION_TIME`, in `validation_roles.adjustment_eligible`, and not the candidate's own condition column | `input_contract.py:141-146` (adjustment eligibility must be `DECISION_TIME`, fail-closed); `apply.py:384-393` (`_adjustment_pool`); design 2.2 R1-R3 |
| 2.b | Source of the admissible set | [C] | A **declaration** by the dataset owner (Section 5), a function of (declaration, exposure column) and of nothing else. No outcome, effect or data value enters the pool | `ADR-101` A2/A7 ("pre-declared adjustment pool"; "the adjustment pool is fixed before candidate evaluation"); design 2.2 |
| 2.c | Ordering/tiering rule | [C] | `Z` admissible for exposure column `x` iff `tier(z) < tier(x)` strictly, both listed (Section 5.1) | `ADR-101` A2 (pre-exposure, no mediators/colliders); design 2.2 R5 |
| 2.d | Scope | [C] | `k = 1` only (`len(conditions) == 1`); `k >= 2` is `PASS not_applicable_k_ge_2`; `G16` untouched | `ADR-101` A1; `contract.py:568-596` (`G16` vacuous at `k == 1`, complementary domain) |
| 2.e | Single-`Z` only | [C] | One stratification per `Z`; `m = |A_cat(c)|` checks; no pairs, subsets or greedy set | `ADR-101` A7 ("Phase 2 uses pre-declared single-`Z` adjustments only"); `ADR-102` Q16 |
| 2.f | Numeric `Z` | [C] | Not implemented, not assessed, **not counted** in "N assessed" or in `m`; listed with the limitation text (Section 8.2) | `ADR-102` Q15 |
| 2.g | Missing declaration | [C] | Empty pool; `G17 = WARN`; provenance string exactly `confounding_assessment: unavailable — no admissible-Z declaration`; never `PASS`, never a veto | `ADR-102` Q13 |
| 2.h | Level of stratification | [C] | Raw levels of `Z` on the evaluation rows; `null` is its own level | `apply.py:355-361` (`group_by` on the raw columns keeps `null` as a key) |
| 2.i | Usable stratum | [C] | A level with `>= 5` exposed **and** `>= 5` comparison rows (`MIN_STRATUM_CELL = 5`) | `apply.py:124, 369-371` |
| 2.j | Assessability floor | [C] | `coverage = exposed rows in usable strata / all exposed rows >= min_confounder_stratum_coverage = 0.50`, else that `Z` is `not_assessable(coverage_below_floor)` (**WARN limitation, not a veto**, `ADR-101` A3) | `contract.py:248`; `apply.py:380, 626`; `contract.py:585-586` (`G16` uses the same floor for "clears coverage") |

### 2.2 Categorical determination from the existing feature typing

What exists (three different notions, none authoritative for `G17`):

1. **Physical dtype** in the manifest (`partitions.features.schema`, e.g. `String`, `Float64`, `Int64`, `Boolean`) and
   in the loaded frame; the discovery engine's atom rule is `dtype.is_numeric()` -> numeric thresholds, else
   categorical `==` atoms if `<= max_categorical_levels = 12` distinct values (`engine.py:394-405`, `169`).
2. `G06`'s rule: a numeric column with `<= ADJUSTMENT_NUMERIC_RAW_LEVELS_MAX = 6` distinct **development** values is
   "effectively categorical" and used as raw levels; otherwise quartile-binned (`apply.py:133, 408-426`).
3. `feature_timing.classification` (roles) — carries no type.

The two numeric-few-levels rules disagree (6 vs 12): the delivered `party_size` (7 levels, `Int64`) is numeric under 6
and raw-levelled under 12. So the categorical determination for integer-coded columns is **not** uniquely inherited.

**Specification (fail-closed default in force, [C-derived] from `ADR-102` Q15 "numeric `Z` not implemented"):**
a declared `Z` is **categorical** iff its physical dtype is non-numeric (`String`, `Categorical`, `Enum`, `Boolean`;
in Polars: `not dtype.is_numeric()`), evaluated on the loaded analytical frame. **Every numeric dtype (`Int*`, `UInt*`,
`Float*`, `Decimal`) is numeric**, regardless of its number of distinct values, and is listed as not assessed. This rule
contains no numeric constant. Column-name heuristics, value-pattern heuristics and cardinality heuristics are **not
used** (they would re-introduce a model of what the column means).

### 2.3 OPEN — F2 (integer-coded low-cardinality columns)

| Option | What it is | Consequence |
|---|---|---|
| **F2-a** | Dtype-only (the default above) | Never treats a threshold-shaped numeric as resolved; loses integer-coded categories that raw levels would resolve exactly (`party_size`, `installments` on the delivered dataset); smallest attack surface; matches `ADR-102` Q15 literally |
| **F2-b** | Dtype non-numeric **or** numeric with `<= 6` distinct development values (raw levels) | Inherits `apply.py:133`; `party_size` (7 levels) stays numeric; `installments` becomes categorical; consistent with `G06`'s "effectively categorical" |
| **F2-c** | Dtype non-numeric **or** numeric with `<= 12` distinct development values (raw levels) | Inherits `engine.py:169`; `party_size` becomes categorical, resolved exactly (measured resolution 1.000 for `party_size >= 5`, design 10.2); the count of numeric-typed columns treated as categorical widens; departs from `G06`'s 6 |
| **F2-d** | Declaration marks each `Z` explicitly `categorical`/`numeric` | Moves the determination into the signed declaration (a human assertion the validator cannot check); a mislabelled numeric threshold `Z` would be stratified at raw levels without the validator noticing (many singleton strata -> coverage falls -> `not_assessable`) |

Neutral note: under F2-b/F2-c the level count is measured on `development` values only (as `apply.py:419` does), so no
evaluation-split data determines the column type. The founder's decision can only widen the default.

---

## 3. The exact post-adjustment promotion test (item 3)

### 3.1 What "the final promotion contract" is, and which part is re-evaluated

The promotion path is `SHADOW_POLICY`: evidence level `ADJUSTED_OBSERVATIONAL` with `G15` satisfied
(`grading.py:209-239`; `G13` is hard-`FAIL`, so `ADJUSTED_OBSERVATIONAL` is the ceiling, `apply.py:860-867`). The
contract gates that are **functions of the effect estimate** and can therefore be re-evaluated on an adjusted estimate
are enumerated below with the exact executed criteria (the contract *text* and the executed code differ for `G03`,
`G10`, `G15`; the freeze binds to the **executed** code and lists each gap):

| Criterion | Executed rule (cited) | Re-evaluated on the adjusted estimate? |
|---|---|---|
| **C1 sign** | `(adjusted_harm > 0) == (raw_harm > 0)` (`G06`, `apply.py:627`); same sign across splits (`G10`, `apply.py:741-743`) | **Yes — core.** Adjusted harm `> 0` (candidates on the path have positive raw harm; Section 1.2) |
| **C2 interval / significance** | 95% cluster-bootstrap percentile interval excludes zero (`G04`: `apply.py:583-602`; `confidence_level` `contract.py:238`; `percentile_ci` `apply.py:253`; interval widened to contain the point estimate `apply.py:587-591`) | **Yes — core.** On the evaluation rows; with C1, this is "lower bound `> 0`" |
| **C3 sample adequacy** | `n_exposed >= min_exposed_records (50)`, `clusters >= min_clusters (5)`, `MDE < |harm|` where `MDE = (Z_95 + Z_POWER_80) * pooled_sd * sqrt(1/n_e + 1/n_c)` (`G03`: `apply.py:567-581`; `minimum_detectable_effect` `apply.py:263-267`; `contract.py:232, 234`). **Text/code gap:** `contract.py:366-372` also states a binary-event floor (`min_outcome_events_binary = 25`, `contract.py:233`) and an MDE-vs-*materiality* comparison; the executed gate does neither (the field is not referenced in `apply.py`; the comparison is against the observed harm) | **Yes — core**, as executed (n, clusters, `MDE < |harm|`), computed on the matched strata rows of the evaluation split |
| C4 materiality | combined-window exposure CI lower bound `> 0` and (`>= min_material_annual_impact` 25,000 or outcome share `>= min_material_outcome_share` 0.005) (`G15`: `apply.py:903-913`; `contract.py:264-265`). **Not annualised in code** (`min_annualization_months`, `contract.py:263`, is unused in `apply.py`); computed on the **combined** three-split cohort | **OPEN — F3a** |
| C5 temporal stability | `G10` (`apply.py:741-757`); `required_same_sign_splits` (`contract.py:255`) is declared but **not referenced** by the gate — the code requires every split present with identical sign; the text's "overlapping intervals" (`contract.py:476-480`) is not executed | **OPEN — F3b** (Section 6) |
| C6 multiplicity over the search | `G05`: BH over `family_size` = hypotheses evaluated in the search, on the **development** raw `p` (`apply.py:609-610, 1504-1510`) | **No.** Its input is a development-split raw statistic that does not depend on `Z`, and its family is the search that produced the candidate; the evaluation split is confirmatory data for a single pre-specified candidate, on which the search-size penalty has no referent. `G05` stays as executed. (Founder may widen the contract scope: F3c) |
| C7 robustness | `G12` (`apply.py:802-858`) | **No.** Not re-run on an adjusted estimate (`ADR-101` A5: `G12`-type blocks are not credited as confounding protection; an adjusted robustness battery is a separate statistical design). Stays as executed (F3c) |
| C8 `G07`, `G09`, `G11` | selection, Simpson, seasonality | **No.** Not functions of the `Z`-adjusted effect; unchanged |

**Consequence stated plainly.** The post-adjustment promotion test is the **core sub-contract {C1, C2, C3}** (plus
whatever the founder adds through F3a-F3c). It is not the entire final contract; the un-re-evaluated gates keep
governing the raw estimate exactly as before. This is a scope statement of the freeze, not a claim of full-contract
re-evaluation.

### 3.2 Definitions (implementable)

Fix a candidate `c` with exactly one condition on column `x`; evaluation rows `E` = the `validation` split; exposed
mask `M_E` = the condition on `E`; `harm` orientation = `outcome.harm_multiplier * (exposed mean - comparison mean)`
(`grading`/`outcomes.aggregation.harm_score`). The declared, admissible, **categorical** pool is
`A_cat(c) = {Z_1..Z_m}`; `m` is fixed by the declaration and the frame's dtypes **before any evaluation** and counts
every `Z_j` including those later found not assessable.

For each `Z` in `A_cat(c)`:

1. **Strata.** Group `E` by `Z` (raw levels, `null` a level). `U_Z` = the set of levels with `>= 5` exposed and `>= 5`
   comparison rows (`apply.py:369-371`). `coverage_Z = exposed(U_Z) / exposed(E)`.
2. **Estimates on `U_Z`** (all in harm units, all on the same rows):
   - `H_full` = crude harm on all of `E` (existing `split_stats`, `apply.py:298-334`). *Reported only.*
   - `H_c` = **matched crude** harm on the rows of `U_Z` (own cross-tabulation; `_stratified_adjustment` does not
     return the usable strata).
   - `H_Z` = **adjusted** harm = the exposure-weighted stratified effect over `U_Z`, computed by the real, unchanged
     `_stratified_adjustment(E_frame, M_E, outcome, (Z,))` (`apply.py:337-381`) times `harm_multiplier`. A spy/equality
     test (U2) asserts the point estimate equals that function's output to `1e-9`.
3. **Cluster bootstrap, paired.** Clustering column from the manifest (`apply.py:567`); `B = DEV_BOOTSTRAP_REPS =
   2000` (`apply.py:107`); population sorted by key (`apply.py:239`, `HANDOFF-047`); seed derived deterministically from
   `BOOTSTRAP_SEED = 20260813` (`apply.py:109`), the candidate id and `Z`, in a **stream isolated from the shared
   `rng`** that `run_validation` threads through the candidates (`apply.py:1459-1463`), so no existing gate's random
   draws or order dependence changes (U11). In each replicate the *same* resampled clusters yield `H_c^*`, `H_Z^*`
   (`U_Z` is **fixed from the observed data**; a stratum with an empty arm inside a replicate is dropped from that
   replicate's weighted sum and the weights are the replicate's own exposed counts; a replicate with no usable stratum
   or an empty arm is skipped, mirroring `apply.py:247-248`). `theta^* = H_c^* - H_Z^*`.
4. **Intervals.** 95% percentile intervals (`percentile_ci`, `confidence_level`), widened to contain the point
   estimate exactly as `apply.py:587-591` does, for `H_c` and for `H_Z` (from `H_Z^*`, **not** the raw interval shifted
   by the adjustment as `apply.py:677-685` does).
5. **Reduction and its evidence.** `theta_hat = H_c - H_Z` (the reduction attributable to adjusting for `Z` on the
   matched rows). `SE_theta = bootstrap_standard_error(theta^*)` (`grading.py:90-105`; `inf` for `< 2` replicates).
   One-sided `p_Z` for `H0: theta <= 0` against `theta > 0`:
   `p_Z = normal_approx_two_sided_p(theta_hat, SE_theta) / 2` if `theta_hat > 0`, else `1 - normal_approx_two_sided_p(
   theta_hat, SE_theta) / 2` (`grading.py:108-134`; that is `Phi(-theta_hat / SE_theta)`). **[C-derived]** from the
   contract's own `p`-value function; the directional form is forced by `ADR-101` A9 (an adjustment that
   *strengthens* the association, `theta_hat < 0`, has `p_Z >= 0.5` and can never be rejected).
6. **Criteria** (Section 3.1: C1, C2, C3, plus F3 additions) are evaluated once on the matched-crude estimate and once
   on the adjusted estimate, each with its own interval from step 4, using the same `n_exposed`, `n_comparison`,
   cluster count and `pooled_sd` of the `U_Z` rows (so C3's counts are identical for the two estimates; only `|harm|`
   in `MDE < |harm|` differs). `F_c(Z)` = criteria failed by `H_c`; `F_adj(Z)` = criteria failed by `H_Z`.

### 3.3 The decision rule

```
Assessed(Z)          := coverage_Z >= 0.50  and  U_Z non-empty  and  both arms present on E
                        and  >= 2 valid bootstrap replicates with finite SE_theta > 0        (else not_assessable(reason))
AttributableLoss(Z)  := F_adj(Z) \ F_c(Z)  is non-empty       # adjusted fails a criterion that matched-crude satisfies
Family               := { p_Z : Z assessed },  family_size = m  (m counts every declared categorical Z)
Rejected             := Benjamini-Hochberg(Family, family_size = m) adjusted p  <=  fdr_alpha = 0.10
BLOCK (G17 FAIL)     := exists Z :  Assessed(Z)  and  Z in Rejected  and  AttributableLoss(Z)
```

A block caps evidence at `PREDICTIVE` (Section 7). No other `G17` state can change evidence level or readiness.

**The test in one paragraph (the falsifiable statement).** For a `k = 1` candidate with a declaration, take each
declared pre-exposure **categorical** `Z` one at a time (`m` checks, fixed before evaluation); on the `validation`
split restrict to the strata of `Z` that have at least 5 exposed and 5 comparison rows (assessable only if they hold
at least 50% of the exposed rows); compute, from one paired cluster bootstrap (2,000 replicates), the crude harm on
those same rows, the `Z`-adjusted harm, and the reduction `theta = crude - adjusted` with its bootstrap standard
error; evaluate the core promotion criteria — adjusted harm positive, its 95% percentile interval excluding zero, and
`n_exposed >= 50`, `clusters >= 5`, `MDE < |harm|` (the executed `G03`/`G04`/`G06`-sign rules with their existing
thresholds) — on the crude and on the adjusted estimate of those same rows; the candidate is stopped by `G17` iff for
some assessed `Z` the adjusted estimate fails a criterion that the matched crude satisfies **and** the reduction
`theta` is statistically established after Benjamini-Hochberg correction at `fdr_alpha = 0.10` across the `m` checks
(one-sided normal-approximation `p` from the bootstrap standard error, the contract's own `p` function). There is no
attenuation percentage, no E-value and no "size of the change" criterion: a large reduction that leaves adjusted
evidence promotable does not block, a small reduction that flips a criterion (and is established) does, a
strengthening adjustment never blocks, and anything not assessable or not attributable is reported and never blocks.

### 3.4 Why each component is fixed (derivation, so a reviewer can check no value was chosen)

- **Criteria tied to the contract, not to a percentage** — `ADR-102` Q12: "after admissible adjustment the candidate
  either still satisfies the promotion criteria or it does not." C1-C3 are the executed contract rules; thresholds are
  the existing ones (Section 12).
- **Matched baseline and attribution (`F_adj \ F_c`)** — `ADR-102` Q17 and `ADR-101` A6: comparing an adjusted subset
  with a full-sample crude mixes the adjustment effect with population/completeness shift. Because `H_c` and `H_Z`
  share the same rows, coverage loss, thin strata and evaluation-split power affect both identically; a criterion
  failed by both is **not** attributable to adjustment and never blocks (this is how coverage `< 1` and tiny strata
  become reporting, not veto, `ADR-101` A3).
- **The paired-reduction test (`p_Z`) exists because `ADR-101` A7 + `ADR-102` require a multiplicity-corrected family**:
  a correction needs a hypothesis and a `p`-value per check. The only percentage-free null under which rejection means
  "adjustment changed the evidence" is `theta <= 0` (`ADR-101` A9's direction). *If the founder does not accept that
  derivation, the alternative (a deterministic contract-flip with no `p`-value, so no family to correct) is F4a.*
- **Knife-edge, stated so it is not discovered later.** Because the rule is tied to a threshold contract, a small but
  established reduction that pushes an estimate across a criterion (e.g. an interval lower bound from `+0.3` to `-0.1`)
  blocks; a large reduction that stays across no criterion does not (`ADR-102` Q12's own +100 -> +40 example). The
  margin by which each criterion is met/failed is a required reported field (Section 8.1), so a knife-edge block is
  visible as one.
- **`G05`/`G12` excluded (C6/C7)** — reasons in the table; alternative is F3c.

### 3.5 Edge handling (all are reporting; none is a veto — `ADR-101` A3)

| Situation | State | Verdict effect |
|---|---|---|
| `coverage_Z < 0.50` | `not_assessable(coverage_below_floor)`; `H_full`, `H_c`, coverage and the excluded exposure share still reported | none (WARN limitation) |
| `0.50 <= coverage_Z < 1` | assessed on the matched strata; the excluded strata (levels and exposed share) are listed | none unless a block per 3.3 |
| Tiny/empty strata | excluded from `U_Z` by the `>= 5`/`>= 5` rule; listed | as above |
| **No usable stratum** — `_stratified_adjustment` returns `(0.0, 0.0)` (`apply.py:374-375`) | `not_assessable(no_usable_strata)`. **That `0.0` is a sentinel, never an adjusted effect of zero** (reading it as `H_Z = 0` would manufacture "complete removal") | none. Regression test U7 |
| Exposed or comparison arm empty on `E` (`split_stats` -> `None`, `apply.py:303`) | `not_assessable(empty_arm)` | none |
| Bootstrap degenerate (`< 2` valid replicates, or `SE_theta` not finite or `<= 0`) — the inherited behaviour of `bootstrap_standard_error` (`grading.py:100-102`) and `normal_approx_two_sided_p` (`grading.py:131-132`) | `not_assessable(bootstrap_degenerate)`. **No additional "valid-replicate share" threshold is added** (it would be a new constant; the freeze inherits the helper's behaviour as is) | none |
| Matched crude already fails a criterion the adjusted also fails | not attributable; recorded as `baseline_does_not_satisfy_contract_on_evaluation_split` with the failed criteria | none |
| Adjusted estimate cannot be computed for every declared `Z` | `G17 = WARN`, reason `no_assessable_z`, provenance `confounding_assessment: unavailable — no assessable categorical Z` | none; evidence level, readiness and every other gate unchanged |
| A candidate reaches `G17` with `k >= 2` | `PASS`, reason `not_applicable_k_ge_2` | none |

### 3.6 OPEN — F3 (scope of the re-evaluated contract beyond the core)

**F3a — materiality (C4).** `G15`'s executed rule compares a *combined-window* exposure interval against absolute
constants and does not annualise; the evaluation split is a 6-month window. Options:

| Option | What it is | Consequence |
|---|---|---|
| F3a-1 | No materiality re-evaluation; `G15` stays on the raw combined-window estimate only | A candidate whose *adjusted* effect is significant but economically trivial keeps its `G15` pass (computed on the crude estimate); no new window-scaling question |
| F3a-2 | Re-evaluate: adjusted per-record harm on `U_Z` x the **combined-window** exposed count (`apply.py:889`), with the validation-based bootstrap interval, against `min_material_annual_impact` / `min_material_outcome_share` (`contract.py:264-265`), matched-crude analogue computed identically | Adds an extrapolation (the validation effect assumed to hold over the combined window) and an interval wider than `G15`'s own; introduces a fourth criterion into `F_adj \ F_c` |
| F3a-3 | Same as F3a-2 but with the validation-window count and no extrapolation, against the same absolute constants | Constants are defined for the combined window; a 6-month figure against a constant meant for 24 months changes what is required, without a contract basis |

**F3b — temporal stability (C5)** — see Section 6.

**F3c — further contract gates on the adjusted estimate.** Add `G05`-style search-family significance and/or a `G12`
battery on the adjusted estimate? Options: none (as specified); `G05`-style with `family_size` = search size on the
evaluation `p` (would require an evaluation-split `p` of the adjusted estimate to be `<= BH threshold` at a search-size
family, which the confirmatory split does not need for a single pre-specified hypothesis and which is essentially
unreachable at `n = 2,462`); `G12` battery on the adjusted estimate (an adjusted robustness design that does not exist).
Consequence of any addition: a new criterion inside `F_adj \ F_c` and new tests; consequence of none: the core
sub-contract statement above stays the scope.

**Fail-closed default in force until decided:** the core {C1, C2, C3} only (no C4, no C5 beyond the precondition in
Section 6.1, no C6/C7).

---

## 4. Multiplicity (item 4)

### 4.1 Constants

| # | Item | Class | Value | Citation |
|---|---|---|---|---|
| 4.a | Family | [C] | The `m` single-`Z` checks of **one candidate**, `m = |A_cat(c)|` fixed by the declaration before evaluation and counting `Z`s later found not assessable. Numeric `Z` are not in `m` | `ADR-101` A7 ("m admissible `Z` = m known checks"; "all checked `Z` enter one multiplicity family"; single-`Z` only); `ADR-102` Q15 |
| 4.b | Correction method | [C] | Benjamini-Hochberg via the existing `benjamini_hochberg_adjusted(p_values, family_size=m)`; `family_size >= number of p-values` allowed exactly as `G05` uses it (assessed `Z` contribute a `p`; unassessable `Z` count in `m` and contribute none) | `grading.py:31-56` (esp. 46-47); `contract.py:390-411`; `apply.py:1465-1466` |
| 4.c | Alpha | [C] | `fdr_alpha = 0.10`, rejection iff BH-adjusted `p <= fdr_alpha` | `contract.py:240`; `apply.py:1506`; `validation-contract.md` §4 "Multiple comparisons" |
| 4.d | Source of each `p` | [C-derived] | Section 3.2 step 5 (the contract's `normal_approx_two_sided_p` on the bootstrap SE, made directional) | `grading.py:108-134`; `ADR-014`/`ADR-015` |
| 4.e | Computed where | [C] | Inside the per-candidate computation (the family is per candidate), not in the run-level BH pass that fills `G05` | `apply.py:1465-1466` is the run-level pass and is **not** reused for `G17` |

### 4.2 Plain statement on FWER vs the contract's FDR

- The contract's multiplicity control is **FDR** (BH) at 0.10 over the *search* family. `G17` needs a **per-candidate
  decision** ("block if any `Z` qualifies"). These are different error rates: FDR is the expected share of false
  rejections among rejections; the relevant error for a block decision is the probability of blocking a candidate
  that is not confounded by any declared `Z` (a family-wise, "any rejection", error).
- **Where the inherited method is an exact fit:** under the **complete null** (every declared check truly has
  `theta = 0`), FDR equals the probability of at least one rejection, so BH at `alpha` bounds P(any rejection) by
  `alpha` (under BH's own independence/positive-dependence assumption). That is the only situation in which "the
  candidate is not confounded by any declared `Z`" is true, i.e. the only situation in which a block is a false block.
  So for the **complete-null false-block probability**, BH at 0.10 is an inherited fit, and it is further reduced by
  the attributable-loss conjunct of 3.3.
- **Where it is an analogy only:** (i) when some `Z` is truly confounding and others are null, BH controls FDR, not the
  chance of extra rejections — irrelevant to the block decision (a real confounder already justifies the outcome
  provided the contract-loss condition holds), but the guarantee then is not "FWER 0.10"; (ii) BH's validity needs
  independence or positive regression dependence of the `p`-values, which the single-`Z` statistics are not proven to
  satisfy (the contract applies BH to correlated candidate `p`-values without addressing this either,
  `contract.py:390-411`); under arbitrary dependence the conservative BH variant (`alpha / sum(1/i)`) or Bonferroni/Holm
  would be the FWER-valid choices, and **neither exists in the contract**; (iii) the numeric `0.10` is inherited, its
  **meaning** is not (contract: expected false-discovery proportion over the search; `G17`: probability of a false
  block per candidate). `alpha = 0.10` is inherited because `ADR-102` requires alpha to "follow the existing
  statistical contract" and `fdr_alpha` is the only multiplicity alpha in the contract; the other candidate,
  `1 - confidence_level = 0.05` (`contract.py:238`), is an interval error rate, not a multiplicity level.
- Effective per-check level: BH's first step rejects the smallest `p` iff `p <= alpha/m` (`m = 3: 0.033`, `m = 7:
  0.014`, `m = 10: 0.010`), so `alpha = 0.10` is the contract-boundary bound, not the realised rate.
- **No value here was selected by any fixture or run.** The earlier design's Bonferroni `alpha_k1 = 0.10` (design
  2.4) is superseded; the `0.10 vs 0.05` selection `ADR-102` prohibits is not performed: only the contract's own
  0.10 exists.

### 4.3 OPEN — F4 (multiplicity ratification; decided before any 2b result, `ADR-102`)

| Sub-item | Options (neutral) | Consequence |
|---|---|---|
| **F4a** — is the paired-reduction test (Section 3.3 `Rejected`) part of the freeze? | (i) yes, as specified; (ii) no: the decision is the deterministic contract-flip `AttributableLoss(Z)` only, with no `p`-value and hence no family to correct | (i) gives multiplicity a hypothesis and bounds false blocks under the complete null; adds one statistical component; (ii) removes the false-block bound (a flip driven by noise on a threshold criterion is unbounded) and makes `m`/BH moot |
| **F4b** — method | (i) BH as inherited; (ii) a FWER-valid method (Holm/Bonferroni) not present in the contract; (iii) BH under arbitrary dependence (`alpha / sum(1/i)`) not present in the contract | (i) inherited, exact fit only under the complete null and BH's dependence assumption; (ii)/(iii) a new statistical method in a versioned contract, more conservative (fewer blocks), justified under arbitrary dependence |
| **F4c** — alpha | (i) `0.10` as inherited by the argument in 4.2; (ii) declare that no inheritable value exists and set a separate alpha now, **before any 2b result** | (i) no new constant; the numeric value's meaning differs from `G05`'s (4.2); (ii) introduces a new named threshold and a contract-versioned field, and its value must be fixed before any run and never by fixture outcome |

**Fail-closed default in force until decided:** none is silently applied; 2b code start is blocked on F4 because
alpha and method determine which candidates are blocked (`ADR-102`: "made before any 2b results are seen").

---

## 5. Declared ordering (item 5)

### 5.1 Constants

| # | Item | Class | Specification |
|---|---|---|---|
| 5.a | Object | [C] | `pre_exposure_order = [[tier0 columns...], [tier1 columns...], ...]` (`design 2.2`). Every column in tier `i` is determined before, and cannot be a consequence of, any column in a tier `> i`. Columns in the same tier are unordered relative to each other. Columns not listed are unordered |
| 5.b | "Strictly earlier tier" | [C] | For exposure column `x` and candidate `Z`: `Z` is earlier iff both are listed and `tier_index(Z) < tier_index(x)` (list position). **Same tier is excluded** (a same-tier column may be a descendant of `x`); **unlisted columns are excluded**; a listed `x` in tier 0 has an empty pool; an unlisted `x` has an empty pool |
| 5.c | What strict precedence does and does not rule out | [C] | Rules out descendants of `x` and colliders **of `x`** (a collider needs `x -> Z`). Does **not** rule out bias through a pre-exposure `Z` that is a collider of two unmeasured causes; that is class (iii) of `ADR-100` D3 and stays a stated limitation |
| 5.d | Fail-closed loader checks | [C] | Every listed column is `DECISION_TIME` and in `adjustment_eligible` (mirrors `input_contract.py:141-146`); no column appears in two tiers; `x` must be listed for a non-empty pool; the declaration may reference no `OUTCOME`/`POST_DECISION`/`IDENTIFIER`/`UNKNOWN` column |
| 5.e | Who declares | [C] | The dataset owner at onboarding, the same role and step that declares `heterogeneity_column`, `seasonality_column`, `robustness_group_column` (`input_contract.py:134-141`; `TASK-066`); recorded in the declaration as `signed_by`/`signed_at` provenance fields the validator stores but cannot verify. It is made before any candidate exists and may not be edited after a validation run starts |
| 5.f | Where it lives (both supported; no choice needed) | [C] | (A) `validation_roles` version `1.1.0` gains an optional `pre_exposure_order`; the loader accepts `1.0.0` (no declaration) and `1.1.0` (today `input_contract.py:113` rejects everything but `1.0.0`). (B) a sidecar declaration file passed explicitly to `run_validation`, for datasets whose manifest must not be re-issued (a new manifest version changes dataset identity; the frozen `travel-bookings-analytical-v1.1.0` is such a dataset). Both present -> loader error (fail-closed) |
| 5.g | Hashing | [C] | `pre_exposure_order_sha256 = sha256(canonical JSON)` where canonical JSON = the declaration object with columns sorted **within** each tier (tier order preserved), keys sorted, separators `(",", ":")`, ASCII-escaped. Recorded in the run manifest (`apply.py:1572-1594` dict) as `pre_exposure_order_sha256` and `pre_exposure_order_source` (`manifest`/`sidecar`/`none`) and repeated in `G17`'s diagnostics. The existing hash discipline is the manifest's per-partition `sha256` (`input_contract.py:36-72`) |
| 5.h | Limits of what the validator can enforce | [C] | The validator can enforce structure, purity (the pool is a function of the declaration and the exposure column only, U1) and recording the hash. It **cannot** verify that the declaration pre-dates the candidate or is causally correct (an assumption, not a measurement). Binding the hash into the discovery payload for a temporal-precedence check would be a discovery-manifest change outside this task and is not part of the freeze (`F6` covers the benchmark-content question) |
| 5.i | Fixture declarations | [C] | Test-side, written by someone who has read the generator: they prove **mechanism correctness under a correct declaration only**, never that a real user can supply a correct declaration or that the system can infer one (`ADR-102` Q14). The mandatory sentence is in Section 8.4 |

### 5.2 OPEN — F6 (declaration content and signer for a real dataset; Q3/Q14)

The tier content for the delivered travel dataset (design 2.2's proposal: tier 0 customer/trip attributes, tier 1
`manager`/`supplier`/`product_category`, tier 2 commercial terms) is an **assumption**, drafted by an author who had
read the generator (oracle-informed, design 2.2 Rev 1 note). Options: (i) approve/amend/replace that proposal and name
the signer; (ii) require an independent drafting from `semantic_meaning` only, disagreements reported, **before** any
mechanism run on that dataset; (iii) supply none (the benchmark then runs under the missing-declaration `WARN`).
**Not blocking for 2b**: all 2b tests use test-side fixture declarations (5.i) or neutral invented data, and `ADR-102`
excludes manufacturing `k = 1` candidates on frozen real datasets. It is blocking for any future run of `G17` on the
delivered dataset with a real declaration.

### 5.3 OPEN — F7 (declared-but-unobservable confounders, class (ii); Q5)

`ADR-101` A3 says incomplete coverage is a recorded limitation; `ADR-100` D3(ii) says such confounding must move to "a
conservative state, not silently promote". The declaration may carry an optional `declared_unavailable` list. Options:
(i) reported verbatim in the claim/provenance only, `G17` state unaffected (A3 reading); (ii) makes `G17` `WARN`
(visible in `report.warnings`) but changes no readiness; (iii) a readiness consequence (e.g. a cap on `k = 1` promotion
when a declared-unavailable confounder exists). Not blocking for 2b; **default in force:** (i).

---

## 6. Stability criterion (item 6)

### 6.1 Constants

| # | Item | Class | Specification | Citation |
|---|---|---|---|---|
| 6.a | Existing `G10` | [C] | Unchanged, on the raw effect: requires all splits present, identical sign, `future_holdout` retention `>= 0.50` of the development magnitude. It remains a prerequisite of the promotion path; `G17` does not recompute it. Executed-vs-text gaps recorded: `required_same_sign_splits` is not referenced by the gate; "overlapping intervals" is not executed | `apply.py:741-757`; `contract.py:255-256, 469-483` |
| 6.b | Temporal consistency required of the evaluation split | [C-derived] | Because `G10` requires same sign on `validation`, a candidate on the promotion path has raw `validation` harm `> 0`. `G17` requires as a **precondition of attribution** that the matched crude `H_c` satisfies C1 (sign) — this is `F_c` in 3.3, not a new rule: if `H_c <= 0`, C1 is failed by both estimates and nothing is attributable | 3.3; `apply.py:741-743` |
| 6.c | Reported, not gated | [C] | For each assessed `Z`: the ratio `H_full(E) / H_dev` (evaluation vs development raw harm) and the sign, so a reader sees how far the evaluation split sits from the search split | `apply.py:749` (`holdout_retention` analogue) |
| 6.d | Disclosed selection dependence of the evaluation split | [C] | Section 1.2 items 1-2 | `engine.py:510-541, 957-959` |

### 6.2 OPEN — F3b (adjusted stability)

`G10` is part of the promotion contract but is a function of raw split effects, so it does not change under a
`Z`-adjustment; whether the promotion test must additionally hold **on the adjusted estimate across splits** is a
contract-scope decision. Options:

| Option | What it is | Consequence |
|---|---|---|
| F3b-1 | No adjusted stability check (6.a-6.c only) | Simplest; the adjusted estimate is judged on one split; a `Z` whose adjusted effect flips sign only in another split is not seen |
| F3b-2 | Also require the adjusted estimate's sign on `future_holdout` (`Z`-adjusted, matched strata, same paired-bootstrap machinery, sign criterion only) | Uses the split `G10` conditions on by magnitude; consumes the final split as a second evaluation split; doubles the number of estimates entering the criteria |
| F3b-3 | Also require the adjusted estimate's sign on `development` (single-`Z`, matched strata) | The search split: not independent of selection (Section 1.2), and it is where `G06` already looks with a joint set |

**Fail-closed default in force until decided:** F3b-1.

---

## 7. Contract version and versioning plan (item 7)

### 7.1 Constants

| # | Item | Class | Value / rule | Citation |
|---|---|---|---|---|
| 7.a | Bump | [C] | `CONTRACT_VERSION` `"1.3.0" -> "1.4.0"` (minor bump, as every verdict-affecting contract change so far: `1.0.0 -> 1.1.0` `ADR-015`; `-> 1.2.0` `ADR-042`; `-> 1.3.0` `ADR-064`). `G17` changes verdicts for a subset of candidates | `contract.py:73`; `validation-contract.md` §2 ("Changing any threshold requires a new contract version..."; "Findings carry the version that graded them"); `ADR-101` ("no silent change to frozen validation contract behavior") |
| 7.b | Which precedent | [C] | `ADR-064` (prior semantics kept executable, mapping table, run-manifest field, reproduction tests). **Not** the `G16` (`TASK-081`) precedent: `G16` shipped with no bump and no switch (`contract.py:73` is still `"1.3.0"` with `G16` present), leaving two different validators under one version string, forcing downstream text such as "`1.3.0` plus `G16`" | `ADR-064`; `contract.py:175-180`; design 3.1 |
| 7.c | New gate id | [C] | `GateId.SINGLE_CONDITION_CONFOUNDING = "G17_SINGLE_CONDITION_CONFOUNDING"`, appended (ids are persisted and never renumbered) | `contract.py:135-136` ("never renumbered"), `154` (last id `G16`) |
| 7.d | Spec | [C] | `GateSpec(gate_id=G17, name="Single-condition confounding (categorical, pre-declared)", bias_class=BiasClass.CONFOUNDING, on_failure=FailureAction.CAP_EVIDENCE, max_level_on_failure=EvidenceLevel.PREDICTIVE)`, question/rule text quoting Section 3.3 | identical in kind to `G06` (`contract.py:412-426`) and `G16` (`contract.py:568-596`); `GateSpec.__post_init__` `contract.py:311-316` |
| 7.e | Evidence-level registration | [C] | Added to the `EvidenceLevel.ADJUSTED_OBSERVATIONAL` tuple of `_LEVEL_GATES`, so `LEVEL_REQUIREMENTS` for levels `>= 3` include it | `contract.py:601-629` (`G06`, `G16` are in that tuple) |
| 7.f | Registration route (files) | [C] | `contract.py` (`CONTRACT_VERSION`, `GateId`, `GATE_SPECS`, `_LEVEL_GATES`, semantics enum + `K1_CONFOUNDING_SEMANTICS_BY_CONTRACT_VERSION`); `input_contract.py` (`ValidationInput.pre_exposure_order`, loader `1.1.0`); new pure module `validation/single_condition_confounding.py` with `_stratified_adjustment` **injected** as `composition_safety.py` does (import-cycle avoidance and real-estimator reuse, `apply.py:648-650`); `apply.py` (`_validate_one` computes `G17` per candidate and puts it in `gates`; `run_validation` accepts `k1_confounding_semantics`, records the manifest keys, computes attribution after `G05`); `validation/__init__.py` exports; `docs/analytics/validation-contract.md` §2, new §4d, §5 gate table, §6 level-3 list, §11 limitations (the doc's §5/§6 tables currently list no `G16`, i.e. they already lag the code — 2b must record that, not silently repair it) | `apply.py:1481, 1512, 1520` iterate `GateId` and index `merged_gates[gate_id]` (a missing `G17` would raise), `grading.py:137-147` (`_result_map` requires every id) |
| 7.g | `NONE_V0` | [C] | `K1ConfoundingSemantics {NONE_V0, SINGLE_Z_VALIDATION_V1}`; `K1_CONFOUNDING_SEMANTICS_BY_CONTRACT_VERSION`: `"1.0.0".."1.3.0" -> NONE_V0`, `"1.4.0" -> SINGLE_Z_VALIDATION_V1`; `run_validation(..., k1_confounding_semantics=<current>)`, independent of `robustness_semantics`. Under `NONE_V0` `G17` is emitted as `PASS`, reason `semantics_not_in_contract_version` (so the ladder is complete). Current semantics is the default (as `ROBUSTNESS_SEMANTICS_VERSION`, `contract.py:171`) | `ADR-064` |
| 7.h | Reproduction level | [C] | **Gate-outcome level, not bytes.** `NONE_V0` reproduces `G00`-`G16` outcomes, numeric diagnostics, evidence level and readiness of v1.3.0-with-`G16` **as of HEAD**. It does not reproduce bytes: the report says `1.4.0` (`report.py:81-85` requires `contract_version == CONTRACT_VERSION`), has a 17th gate row and `ValidationThresholds.version` differs. The `1.0.0`-`1.2.0 -> NONE_V0` entries mean only "`G17` absent": `G16` has no switch, so they do **not** reproduce those versions' ladders. The run manifest, not the report string, is the source of truth for semantics (same as `FIXED_QUANTILE_V1` today) | design 3.4 Rev 1 note |
| 7.i | `ValidationThresholds` | [C] | **No new field** (no new numeric constant, Section 12); only `version` follows `CONTRACT_VERSION` | `contract.py:220-293` |
| 7.j | Compatibility invariant | [C] | `G00`-`G16` outcomes and numeric diagnostics, evidence level and policy readiness are unchanged for every candidate **except** that a `k = 1` candidate on a declared dataset may be capped by a `G17 FAIL`. What does change for every candidate and is not covered by "unchanged": a 17th gate row; the version string; the new manifest keys; for undeclared `k = 1` candidates a `WARN` line in `report.warnings` (`warnings_from` skips only `PASS`, `grading.py:203-204`) | design 3.3 Rev 1 restatement |
| 7.k | Grading cycle | [C] | Any run under `1.4.0` is new evidence needing its own grading cycle; comparing a `1.3.0` and a `1.4.0` result must state the version change, not only the candidate's change | `ADR-100` sequencing; `ADR-101`; `ADR-064` Consequences |

### 7.2 Migration text (to be carried into `validation-contract.md` §4d in 2b)

1. Contract `1.4.0` adds gate `G17_SINGLE_CONDITION_CONFOUNDING`; new runs use it; artifacts graded under `<= 1.3.0` keep
   their grading and are not re-graded.
2. **`report.warnings` consequence:** for every `k = 1` candidate on a dataset with no admissible-`Z` declaration,
   `report.warnings` gains the line `G17_SINGLE_CONDITION_CONFOUNDING warn: confounding_assessment: unavailable — no
   admissible-Z declaration` (`WARN` satisfies the gate and never changes level or readiness, `contract.py:99-101`).
   `k >= 2` candidates get `PASS` and no new line. Consumers that treat "no warnings" as a clean state or key on the
   count/content of `report.warnings` see a systematic change for undeclared `k = 1` candidates; if founder decision F5b
   adds a power `WARN`, the same applies to essentially every declared real-scale `k = 1` candidate.
3. The report has 17 gate rows; consumers indexing by gate count must be updated (`tests/analytics/test_tier3_structural.py:30`
   and `scripts/diagnose_validation_power.py:138` iterate `GateId`; `apps/api/app/findings/contracts.py` and
   `tests/unit/test_finding_contracts.py` must be baselined by the implementer).
4. `NONE_V0` reproduces gate outcomes, not bytes (7.h). The implementer must first run the existing suite at HEAD and
   record the baseline; `test_pre_v1_3_0_semantics_reproduce_the_previous_contract_versions_verdicts` pins verdicts on
   gitignored artifacts that predate `G16` and must be checked before "reproduces v1.3.0" is asserted.
5. `G17` protects only against confounding by a pre-declared **categorical** `Z` that the check could assess (Section
   8); it is a capability/safety mechanism, not proven product protection and not a recall change (`ADR-102` Q16).

### 7.3 OPEN — F9 (versioning ratification)

The bump and `NONE_V0` route follow the cited precedents; `ADR-102` lists "contract version" among the constants the
freeze fixes without deciding it. Options: (i) as specified (1.4.0, default-on for new runs, `NONE_V0` for
reproduction); (ii) the `G16` label-only route (no bump, no switch) — consequence: two validators under one version
string, no executable prior semantics; (iii) `1.4.0` but `G17` opt-in per run rather than default-on — consequence:
undeclared/default runs would not carry the `NOT ASSESSED` provenance line and a reader could not tell "not checked"
from "checked" without the manifest field. Blocking (it fixes what every report contains).
**Fail-closed default in force:** (i).

---

## 8. Reported fields and claim text (item 8)

### 8.1 Per-candidate record (`CandidateValidation.diagnostics["k1_confounding"]`, serialised beside the report like `composition_safety_*`)

| Field | Content |
|---|---|
| `semantics_version` | `single_z_validation_v1` / `none_v0` |
| `applicable` | `k == 1` |
| `evaluation_split`, `n_rows_evaluation`, `n_exposed_evaluation` | `validation`, counts |
| `declaration` | `{source: manifest/sidecar/none, sha256, signed_by, signed_at}` |
| `pool` | `declared_categorical_assessed_list`, `declared_categorical_not_assessable` (with reason), **`numeric_not_assessed_list`** (the numeric `Z` that strict precedence admits but the categorical rule excludes, with the limitation text 8.2), `excluded_reason_summary` (same tier / unlisted / own column) |
| `N_assessed` | number of categorical `Z` with status `assessed`; **numeric `Z` are not counted** (`ADR-102` Q15) |
| `m`, `multiplicity` | `m`; `{method: "benjamini_hochberg", alpha: fdr_alpha, family: "per_candidate_single_z_checks", family_size: m}` |
| per-`Z` row | `z`, `tier`, `status`, `n_levels`, `n_usable_levels`, `coverage`, `excluded_levels`+`excluded_exposed_share`; the **three estimates side by side** `H_full` (full-sample crude), `H_c` (strata-eligible crude), `H_Z` (adjusted), each with 95% interval (`H_c`, `H_Z`); `theta_hat`, `SE_theta`, `p_Z`, `bh_adjusted_p`, `rejected`; `F_c`, `F_adj`, `attributable_loss`; **criterion margins** for C1-C3 (each: value, threshold, met/failed, margin) on `H_c` and `H_Z`; `evaluation_vs_development` (6.c) |
| `detectability` | per assessed `Z` (categorical only; numeric `Z` get none): `min_detectable_reduction_eur_80`, its share of `H_c`, and `complete_removal_detectable_80` (8.3) |
| `decision` | `no_evidence_of_attributable_contract_loss` / `contract_loss_established` / a reason code (Section 8.5) |
| `established_z` | list of blocking `Z` with `H_c`, `H_Z`, `theta_hat`, adjusted `p`, failed criteria |
| `attribution` | `{credited: bool, reason: str, counterfactual_evidence_level, counterfactual_readiness, actual_evidence_level, actual_readiness, other_failed_gates_in_actual: [...], other_failed_gates_in_counterfactual: [...]}` (8.6) |
| `limitations` | list of strings (numeric-`Z` limitation, coverage, not assessable, unknown latent confounding, partial independence 1.2, fixture-vs-declaration caveat when applicable) |
| `claim` | the rendered text of 8.4 |

Run manifest gets: `k1_confounding_semantics_version`, `k1_evaluation_split`, `k1_multiplicity` (method/alpha), `pre_exposure_order_source`, `pre_exposure_order_sha256` (extends `apply.py:1572-1594`).

### 8.2 Numeric-`Z` limitation text (exact, mandatory whenever the declaration or the strict-precedence pool contains a numeric column, and in every `G17` claim)

> **"`G17` v1 coverage = categorical admissible `Z` only. Numeric-`Z` confounding protection is not assessed / not
> supported. Numeric variables (list) are not assessed and are not counted among the N variables checked."**

(`ADR-102` Q15, verbatim in substance.) No power/detectability figure is reported for a numeric `Z`; no numeric `Z`
appears in `N_assessed`, `m`, or the "checked" list.

### 8.3 Power/detectability field — kept, categorical only

Kept, because `ADR-101`'s bounded claim is "a check against a pre-declared set of observable, causally-admissible
confounders **that this mechanism could correctly assess**", and `G03` already sets the precedent of reporting the
minimum detectable effect "whether or not the gate passes" (`contract.py:369-372`; `apply.py:569-570`).

Form (no new constant; all inputs inherited): for each **assessed categorical** `Z`,

`min_detectable_reduction_eur_80 = (z_{1 - fdr_alpha/m} + Z_POWER_80) * sqrt(SE_c^2 + SE_Z^2)`

where `z_{1-a}` is the standard-normal quantile, `Z_POWER_80 = 0.841621` (`apply.py:104`, "matches
`DEFAULT_THRESHOLDS.power_target`", `contract.py:235`), `SE_c`, `SE_Z` are the cluster-bootstrap standard errors
(`grading.py:90`) of `H_c` and `H_Z`, and `1 - fdr_alpha/m` is BH's first-step threshold. **`complete_removal_detectable_80
:= (H_c >= min_detectable_reduction_eur_80)`**, `share = min_detectable_reduction_eur_80 / H_c`.

**Why the no-pairing form [C-derived]:** the paired standard error `SE_theta` observed when `Z` is unrelated to `X` and
`Y` is very small (the paired difference is nearly zero: design 10.1 measured `rho = SE(D)/SE_raw` at its `0.5` bound
for uninformative `Z`), which would claim sensitivity that would not exist if `Z` were a genuine confounder (under
complete removal `H_Z` is close to independent of `H_c`, so `SE_theta` approaches `sqrt(SE_c^2 + SE_Z^2)`; positive
covariance only lowers it). The formula is therefore an **upper bound on the reduction that would be detected at 80%
power** and is never optimistic. It covers stage-B detectability only; the contract-loss conjunct is reported through
the criterion margins (8.1).

Whether an additional `WARN` is raised when no assessed `Z` could detect complete removal is **F5b** (not a `PASS`-able
state at real scale: design 10.1 found this for all four real-scale exposures). **Fail-closed default in force:** field
reported and the sentence in 8.4 mandatory; no extra `WARN`.

### 8.4 Required claim text (render rules)

**Declared and at least one `Z` assessed, no block** (`G17` `PASS` or `WARN`):

> "No attributable loss of promotion evidence was established by the N checked pre-declared, pre-exposure
> **categorical** variables (list) on the validation split, evaluated on the matched usable strata of each variable.
> **This is not evidence that confounding is absent.** For each checked variable the check would detect (80% power)
> only a reduction of the estimated effect of at least X per record (Y% of the matched crude effect); smaller reductions,
> reductions that leave the adjusted evidence still meeting the promotion criteria, and confounding spread over several
> variables would pass unnoticed. [If `complete_removal_detectable_80` is false for a variable: 'For variable V the check
> could not have detected complete removal of this effect at 80% power.'] Not assessed: (list, reason). Numeric
> variables are not assessed (numeric-variable confounding protection is not supported): (list). Declared but
> unobservable: (list). Unknown latent confounding is outside this check. Independence of the evaluation split from
> candidate selection is partial (raw sign in later splits influenced selection)."

**Blocked** (`G17` `FAIL`): "Promotion stopped by `G17`: after adjusting for the pre-declared categorical variable V (validation split, matched
strata) the estimate falls from `H_c` to `H_Z` (reduction established, adjusted `p` = ...), and the adjusted estimate no
longer satisfies [criteria failed] that the matched crude estimate satisfies."

**No admissible-`Z` declaration** (exact, `ADR-102` Q13; the state is **NOT ASSESSED**, never a pass):

> `confounding_assessment: unavailable — no admissible-Z declaration` (rendered to users as **"Confounding check: NOT
> ASSESSED — no admissible-Z declaration. This is not a pass of the check."**)

Two further `NOT ASSESSED` strings (same class): `confounding_assessment: unavailable — declaration admits no
categorical Z for this exposure`; `confounding_assessment: unavailable — no assessable categorical Z`.

**Fixture claims** (any claim made from benchmark/fixture results) must carry, verbatim in substance (`ADR-102` Q14):

> "The fixture declaration was written by someone who had read the generator. Passing it shows only that the mechanism
> works **when the declaration is correct**; it does not show that a real user can supply a correct declaration, or that
> the system can infer one. This task does not address that second claim. Passing the `T01`/`T05` categorical fixtures
> with a kill-test closes **mechanical capability only**; it does not close `D2` Part B and is not external evidence."

**Forbidden language** in any `G17` field, warning, report or summary: "cleared", "ruled out", "confirmed unconfounded",
"safe", "verified not confounded", "passed the confounding check" without the qualifier above, and any wording that
implies numeric-`Z` protection. `PASS` is a gate outcome, not a statement about the world.

### 8.5 State mapping and reason codes

`FAIL` iff block (3.3). `WARN` iff not blocked **and** (declaration absent, or the pool is empty, or no `Z` assessable —
`ADR-102` Q13 and 3.5). `NOT_EVALUATED` is **not used** (it grades like `FAIL`, `contract.py:99-101`, and would be the
coverage veto `ADR-101` A3 forbids). `PASS` otherwise. Whether **further** limitations (numeric `Z` present but
unassessed, some categorical `Z` not assessable, declared-unavailable) also produce `WARN` is **F5a**.

Reason codes (diagnostic; never change cap severity): `not_applicable_k_ge_2`, `semantics_not_in_contract_version`,
`no_declaration`, `declaration_admits_no_categorical_z`, `no_assessable_z`, `baseline_does_not_satisfy_contract_on_evaluation_split`,
`no_evidence_of_attributable_contract_loss`, `contract_loss_established`. Per-`Z` statuses: `assessed`,
`not_assessable(coverage_below_floor | no_usable_strata | empty_arm | bootstrap_degenerate)`, `not_assessed(numeric_not_supported)`.
Distinct from `G12` (`robustness`) and `G16` (`confound_like` / `composition_risk_indeterminate`).

### 8.6 Attribution record (`ADR-101` A5/A6)

After all gate results exist (including `G05`, `apply.py:1504-1511`), compute the counterfactual with the real
`classify_evidence_level` and `assign_policy_readiness` (`grading.py:172, 209`) with the `G17` result replaced by
`PASS`. `credited = (G17 is FAIL) and (counterfactual readiness >= SHADOW_POLICY)`. A `G17 FAIL` whose counterfactual
is still below `SHADOW_POLICY` because of `G12`, `G06`, `G11`, ... is recorded with `credited = false` and reason
"already stopped by <gates>"; `G12`'s incidental caps get no credit under any circumstance. Only `credited = true`
counts toward any accounting of what the mechanism stopped. `G17` is computed for every `k = 1` candidate (information
even where another gate caps) but credited only on the promotion path.

### 8.7 OPEN — F5 (warning scope)

**F5a — which limitations produce `WARN`** (missing declaration is decided, `ADR-102` Q13). Options: (i) `WARN` iff any
declared-pool member is not assessed for any reason, including numeric `Z` present in the declaration; (ii) `WARN` only
for the missing declaration, an empty pool, or zero assessed `Z`; other limitations live in provenance/claim only.
Consequence: (i) makes `PASS` unreachable whenever any numeric `Z` sits in the admissible tiers (likely on real
datasets) and adds `report.warnings` lines broadly; (ii) surfaces fewer lines but a numeric-`Z` limitation would reach
the reader only through `diagnostics`/claim, since `warnings_from` skips `PASS` (`grading.py:203`).
**F5b — power `WARN`** (8.3). Options: (i) none (default); (ii) `WARN` `not_powered_for_single_z_violation` when
`complete_removal_detectable_80` is false for every assessed `Z`. Consequence of (ii): `report.warnings` changes on
essentially every declared real-scale `k = 1` candidate (design 10.1 found this at the delivered size for all four
exposures), `G17` `PASS` becomes practically unreachable there, and migration text item 2 extends.
**Fail-closed default in force until decided:** F5a-(ii), F5b-(i). Blocking (defines report content).

---

## 9. Pre-registered test plan for 2b (item 9)

No code is written by this freeze. **No prediction below has been checked against any run.** Arithmetic is by hand from
the fixture recipe (`tests/analytics/test_task104_trap_fixtures.py`: `TARGET_RAW_HARM_EUR = 400`, `NOISE_SD_EUR = 250`,
`X ~ Bernoulli(0.03 + 0.62 * s)`, `destination` indicator = `Tokyo`/`Reykjavik`) and the design's Section 10 replica
figures; every number is approximate and states its falsifier. **No recall claim is made and no `k = 1` candidate is
created on any frozen real dataset** (`ADR-102`).

### 9.1 Unit and property tests (neutral: invented columns, no dataset)

| ID | Test |
|---|---|
| U1 | Pool purity: `A(c)` depends only on (declaration, exposure column, dtype); replacing outcomes/rows leaves it byte-identical; own column, same tier, unlisted, lower-tier-`x` excluded; loader rejects non-`DECISION_TIME`/ineligible/duplicated-tier columns |
| U2 | Single-`Z`: spy on `_stratified_adjustment` — exactly `m` calls with `len(columns) == 1` per candidate on the evaluation frame; own point estimates equal the real function's to `1e-9`; no call with `>= 2` columns |
| U3 | Evaluation data: `G17` outputs are identical when `development` and `future_holdout` outcomes/`Z` values are permuted; only `validation` rows enter |
| U4 | Categorical determination: default rule (F2-a) on `String`/`Boolean`/`Int64`/`Float64`; if F2 later widens, the parameterised rule on `<= N` development levels with `N` from the decision; the level count uses `development` values only |
| U5 | Numeric `Z` are not assessed, not counted in `N_assessed`/`m`, appear in `numeric_not_assessed_list` with the 8.2 text, get no detectability field, and never block |
| U6 | Matched strata: `H_c == H_full` when coverage `= 1`; differ when thin strata exist; all three estimates reported; criteria evaluated on the same `n`/clusters/`pooled_sd` for `H_c` and `H_Z` |
| U7 | No usable stratum (`(0.0, 0.0)` return) -> `not_assessable(no_usable_strata)`, **never** treated as `H_Z = 0`; empty arm, coverage `< 0.50`, degenerate bootstrap -> `WARN`, verdict unchanged |
| U8 | Multiplicity: `benjamini_hochberg_adjusted(p, family_size=m)` with unassessed `Z` counted in `m`; `theta_hat <= 0` gives `p_Z >= 0.5` and is never rejected; `m` independent of the data |
| U9 | Attribution matrix: credited iff `G17 FAIL` and counterfactual `>= SHADOW_POLICY`; `G12`-only cap -> `credited = false`; reason codes disjoint from `G12`/`G16` |
| U10 | Inertness: `k >= 2` -> `PASS not_applicable_k_ge_2`; `NONE_V0` -> `PASS semantics_not_in_contract_version`; undeclared -> `WARN` with the exact ADR-102 string and unchanged verdict/readiness/evidence level |
| U11 | Isolation and determinism: `G04`/`G05` numeric diagnostics identical with and without `G17` and independent of candidate order (RNG stream isolated); identical output on identical inputs; invariant to row order and to the order of `Z` |
| U12 | **No new numeric constant:** static check that the `G17` module's numeric literals/thresholds are only names imported from `contract.py`/`apply.py` (Section 12); `ValidationThresholds` field set unchanged |
| U13 | Versioning: mapping test (every historical `CONTRACT_VERSION` maps to a semantics), `GATE_SPECS`/`LEVEL_REQUIREMENTS` shape (`G17` in the level-3 tuple, `CAP_EVIDENCE`, `PREDICTIVE`), loader accepts `validation_roles` `1.0.0`/`1.1.0` and rejects both-sources |
| U14 | **ADR-102 worked examples:** (a) neutral synthetic, large `n`: crude `+100` -> adjusted `+40`, both meeting C1-C3 -> **not blocked** despite the 60% drop; (b) a case where the crude sits just above the `MDE` bar and a small **established** reduction lowers the adjusted estimate below it -> **blocked** despite a small percentage change. Together they show the rule is contract-tied, not percentage-tied |
| U15 | Static: the `G17` module references neither `max_adjusted_attenuation` nor `min_e_value` nor `e_value` (`ADR-102` Q12) |

### 9.2 Fixture tests through the real `run_validation` (test-side builders; no gate re-implemented)

Reuse `build_fixture`, `ISOLATE_G12_ROLES`, the three-state style of `g06_disabled`/`g16_disabled`
(`test_task104_trap_fixtures.py:144, 264, 337, 382`), seeds `101-106`. Fixture declarations are test-side (5.i).
Fixture form **FX-A (categorical carrier):** exposure `X` and outcome `Y` driven by one categorical admissible `Z*`
(`destination`, raw levels, indicator `in {Tokyo, Reykjavik}`) with weight share `s` and the remaining share spread on
the other catalogued indicators; `T01`-shaped (`X = manager == "Manager 2"`, with `ISOLATE_G12_ROLES`) and
`T05`-shaped (`X = manual_exception`). Both traps list `destination` among their catalogued confounders
(`TRAP_SPEC`, `test_task104_trap_fixtures.py:84-108`). **Preconditions asserted per cell, and a cell that fails one is
reported as invalid, never silently replaced:** `Z*` is a declared categorical admissible `Z`; `Z*` is not among
`G06`'s `adjustment_columns_used` (else `G06` is the stopper and the cell says nothing about `G17`); the
`G17`-forced-`PASS` counterfactual reaches `SHADOW_POLICY` (else nothing is capturable); all non-`G17` gates are
identical to the `NONE_V0` run.

**Kill-test (the required three-state protocol)**, `g17_disabled()` context manager replacing the `G17` result with
`PASS` inside the test only, restoration asserted, on every FX-A cell registered as blocked: (1) enabled: `G17 FAIL`,
`credited = true`, caveat line in `report.warnings`, readiness below `SHADOW_POLICY`, evidence `<= PREDICTIVE`;
(2) disabled: `SHADOW_POLICY` **reached again** (this is what proves `G17` was the stopper and not an incidental
gate); (3) restored: stopped again with the attribution record. A cell that cannot pass the kill-test (e.g. the equal-
weight forms) is reported as expected-miss, not forced.

**Suppression fixture (FX-C, `ADR-101` A9):** `X` positively associated with a categorical `Z` that is **beneficial**
to `Y`, plus a direct harm from `X`, calibrated so the crude harm is positive and promotable and the adjusted harm is
`>= 1.5 x` the crude harm; the candidate reaches `SHADOW_POLICY` without `G17`.

**Missing declaration (FX-D):** the blocked FX-A cell re-run with **no** declaration.
**Numeric `Z` (FX-E):** confounding carried only by a numeric-typed column (`booking_lead_days >= median`, declared).
**Compatibility (CT):** the 15 frozen `TASK-103` candidates (`docs/benchmark/task-103-evidence/run1|run2`, all
recorded under `validation_contract_version 1.3.0`; the dataset is in the repo), and every fixture: `NONE_V0` vs
`SINGLE_Z_VALIDATION_V1` gate-by-gate for `G00`-`G16`, diagnostics, evidence level, readiness.

### 9.3 Pre-registered predictions (registered now; original text is never edited after a result)

Model used (approximate, from design 9.4/10.3): bias share of a weight-`s` indicator among four `b(s) = s^2/(s^2 +
(1-s)^2/3)` (a same-variance shape approximation; the measured `destination` replica ran 0.03-0.07 *below* it);
fixture `sd(Y | noise) = 250`, raw crude harm 400, evaluation `n_exposed` about 670 and `n_comparison` about 1,800; the
`MDE` criterion's `pooled_sd` includes the confounder-induced variance (hand estimate `pooled_sd ~ 350-370`, so
`MDE_U ~ 45-50 EUR`; the actual value is a required recorded quantity). Adjusted harm for weight share `s` is
`(1 - b(s)) * 400`, uncertainty `+-0.08` on `b`. Stage-B evidence is not the binding constraint in FX-A (`theta`
`>= 300` against `SE_theta ~ 6-15`).

| ID | Object | Prediction | Basis / falsifier |
|---|---|---|---|
| **P2b-1** | FX-A `s = 1.0`, `T01`-shaped and `T05`-shaped, seeds 101-106 | **6/6 blocked** by `G17`, `credited = true`; kill-test states (1)-(3) as registered above | Adjusted about 0 (`b ~ 1`): fails C1 (about half the seeds) and C2 and C3 in essentially all; crude 400 satisfies all. **Falsifier (S-E):** any seed not blocked while its preconditions hold |
| **P2b-2** | FX-A `s = 0.8` (`b ~ 0.93-0.98`, adjusted about 8-28 EUR) | **5-6/6 blocked; point 6/6**, credited | Adjusted `<` `MDE_U ~ 47`. Falsifier of the *model* (not necessarily of the mechanism): `< 4/6` with a measured adjusted `< 40` |
| **P2b-3** | FX-A `s = 0.6` (`b ~ 0.85-0.87`, adjusted about 52-60 EUR, near `MDE_U`) | **boundary probe: 0-3/6 blocked; no point claim**; whichever seeds are blocked are blocked because the adjusted estimate fell below the `MDE` bar, **not** because of a percentage. **A 6/6 or a >= 4/6 here would not be a success**: it would indicate a criterion evaluated more strictly than specified (report it as a defect signal) | 45-50 vs 52-60 with `SE(H_Z) ~ 11-14` |
| **P2b-4** | Catalogue equal-weight forms (four indicators, `s = 0.25` each; `b ~ 0.25`) | **0/6 blocked; remain at `SHADOW_POLICY`** in states (1)-(3). **This is an expected miss against the `T01`/`T05` catalogue forms, reported as such** (`ADR-102`: the objective is the observable, categorical, pre-declared case) | adjusted about 300 `>>` `MDE_U`; a block here is an unexplained false block -> S-A |
| **P2b-5** | FX-C suppression, seeds 101-106 | **0/6 blocked; `SHADOW_POLICY` unchanged; `p_Z >= 0.5`; `H_Z >= 1.5 x H_c`** | `theta_hat < 0`; deterministic in direction. **Falsifier (S-B):** any block |
| **P2b-6** | FX-D missing declaration | **`G17 WARN`, provenance string exactly `confounding_assessment: unavailable — no admissible-Z declaration`, `SHADOW_POLICY` reached 6/6 (the mechanism does not veto), claim "NOT ASSESSED"** | `ADR-102` Q13 |
| **P2b-7** | FX-E numeric `Z` only | **not assessed, not counted, 0/6 blocked, `SHADOW_POLICY` reached; limitation text present** (an expected miss, reported) | `ADR-102` Q15 |
| **P2b-8** | Compatibility (CT) | **0 of 15 frozen candidates change** at `G00`-`G16`/level/readiness (all `k = 2`, `G17` `PASS not_applicable_k_ge_2`); no `report.warnings` change for `k >= 2`; every fixture identical outside `G17` | structure (design P1/P11). A deviation is an implementation defect (S-D) |
| **P2b-9** | U14(a) `+100 -> +40` both promotable | **not blocked in 100% of simulated draws at the chosen large `n`** | criteria met by both estimates; `F_adj \ F_c = {}` |
| **P2b-10** | U14(b) knife-edge cell: crude at mean 100, bar 90, established reduction 20, `SE_c ~ 32` | **blocked rate about `Phi((bar + theta - mu)/sigma) - Phi((bar - mu)/sigma) = Phi(0.31) - Phi(-0.31) ~ 0.24` (range 0.15-0.35)** | shows a small reduction blocks only when the crude estimate sits within `theta` of the bar (Section 3.4 knife-edge) |
| **P2b-11** | Null calibration (scratch replica validated against the real estimator to `1e-6`, `>= 2,000` datasets per cell; `m` in `{1, 3, 7, 10}`; complete null `theta = 0` for every check; effect from 3 SE to 10 SE; Gaussian and heavy-tailed noise) | **False-block probability `<= fdr_alpha = 0.10` in every cell** (BH complete-null bound); expected well below (attributable-loss conjunct) with **no point claim**; the interval `P(p_Z <= 0.05)` for a single null `Z` in `[0.03, 0.07]` (calibration of the bootstrap SE at small `theta`, where `SE_theta` is small) | Falsifier (S-A): any cell `> 0.10`, or the `p_Z` calibration outside `[0.03, 0.07]` |
| **P2b-12** | Real-scale characterisation P18 (non-binding; `sd = 776`, `Z*` categorical, `s = 1.0`, `H_raw` in `{100, 200, 400}`, `>= 30` seeds; the actual `n`, `MDE_U`, `min_detectable_reduction_eur_80` recorded) | Block rate **non-decreasing in `H_raw`**; **`>= 0.90` at 200 and 400**; **`<= 0.60` at 100** (the crude effect there sits at the `MDE_U ~ 100` bar, so it is often non-attributable) | hand arithmetic `MDE ~ 2.8 x 35 ~ 99`. Reported as a limitation of what the mechanism can do at the delivered scale; **not** a pass criterion (`ADR-102`: capability only) |
| **P2b-13** | `T01` as shipped (`G12` group column intact) | `G17` may `FAIL` with `credited = false` (counterfactual still below `SHADOW_POLICY` via `G12`); no credit | `ADR-101` A5 |

### 9.4 Mutants (each must be caught by a named test; a surviving mutant means a missing test)

M1 evaluate on `development` (U3); M2 subset/joint `Z` (U2); M3 no multiplicity correction, raw `p <= alpha` (P2b-11,
U8); M4 an attenuation-percentage criterion imported (U14(a), U15); M5 two-sided "any large change" rule (P2b-5);
M6 full-sample crude baseline instead of matched (a coverage `< 1` cell where the verdicts differ, U6); M7 treating the
`(0.0, 0.0)` sentinel as adjusted zero (U7); M8 numeric `Z` counted as assessed (U5); M9 coverage veto / `NOT_EVALUATED`
for limitations (U7/U10); M10 credit given for a `G12`-only cap (U9/P2b-13); M11 mediator-admitting pool: a
`paid_search -> discount_rate -> margin`-shaped neutral case with `discount_rate` in the same/later tier must yield an
empty pool and no block (U1); M12 pool chosen after seeing effects (U1); M13 fitting anything on `validation` and
confirming on it (U3); M14 the paired-reduction test replaced by a deterministic flip (P2b-11, P2b-10 detects the
false-block bound); M15 adjusted interval taken as the raw interval shifted (`apply.py:677-685` style) (a case where
the paired interval and the shifted interval disagree).

### 9.5 How a null or harmful result is reported

- **Null on real-scale candidates** ("`G17` changed 0 of N", which is the expected outcome and true today: 0 of 195
  frozen candidate rows are `k = 1`, design P1b): reported beside `min_detectable_reduction_eur_80`/`complete_removal_
  detectable_80` and the sentence that a 0 is not evidence of safety and not a recall or evidence result.
- **Objective not met** (P2b-1 or P2b-2 fail): reported as *mechanical capability not demonstrated*; the mechanism is not
  tuned; a revised design is a new dated version.
- **Harmful** (false block above bound; suppression block; a block where the matched crude already failed the contract;
  a block where the adjusted evidence still met C1-C3): reported verbatim with fixture, seed and per-`Z` table; the design
  version is marked failed for that hypothesis; **no retuning of alpha, method, split, criteria or fixture parameters to
  recover it**.
- **Expected misses** (P2b-4, P2b-7, and real-scale non-detection) are reported in the same table as the passes.
- After implementation, kill-tests and independent review, **stop** (`ADR-102` Consequences). If frozen datasets still
  yield no `k = 1` candidates, no Phase 2c is opened to obtain a nicer `PASS`; no `k = 1` candidate is created on a
  frozen real dataset (no census, no `reserve_k1_slot=True` run on delivered data for this purpose).

---

## 10. Stop conditions and what would show the design is wrong (item 10)

Evaluated on the specification as frozen. None may be tuned away.

| ID | Condition | Consequence |
|---|---|---|
| **S-A** | Complete-null false-block probability `> fdr_alpha = 0.10` in any P2b-11 cell, or single-`Z` `p_Z` calibration outside `[0.03, 0.07]`; or any unexplained block of P2b-4 | SE method or family definition is wrong -> stop and redesign; do not raise or change alpha |
| **S-B** | Any block of the suppression fixture (P2b-5) | the two-sided/directional design is wrong -> stop |
| **S-C** | Kill-test failure: with the mechanism disabled a registered-blocked cell does **not** reach `SHADOW_POLICY` | `G17` was not the stopper (incidental gate) -> the cell is invalid and its credit void; it is never reported as mechanism success |
| **S-D** | Any `G00`-`G16` outcome, diagnostic, evidence level or readiness differs between `NONE_V0` and `SINGLE_Z_VALIDATION_V1` for any of the 15 frozen candidates or any fixture, other than a `k = 1` + declaration `G17 FAIL` | isolation broken -> defect; block release |
| **S-E** | P2b-1 (`s = 1.0`) blocked in `< 6/6` seeds with preconditions holding, or P2b-2 `< 4/6` | the mechanism cannot deliver even its bounded capability -> **recommend abandoning as specified**; any change of split (F1-c) or criteria is a new registered hypothesis, not an in-place fix |
| **S-F** | Any mutant of 9.4 survives | an unguarded degree of freedom -> add the test or redesign |
| **S-G** | A block is issued where the adjusted estimate still met C1-C3, or where the matched crude already failed the contract, or from a percentage-of-change rule | the rule departs from `ADR-102` Q12/Q17 -> defect |
| **S-H** | The `G17` module uses any numeric constant not in Section 12 (U12) | a constant was introduced outside the freeze -> defect |

**What would show the design itself is wrong (not only the code):** (i) S-A or S-B; (ii) the knife-edge behaviour of
P2b-10 turning out to dominate real blocks (blocks concentrated where the crude sits within `theta` of a criterion,
with `theta` small relative to the criterion margin — the rule then measures nearness to a bar, not confounding);
(iii) the categorical restriction leaving the mechanism with no assessable `Z` on any dataset the founder considers
representative (the mechanism then never runs and adds contract surface for nothing — the design-doc abandonment
criterion); (iv) the finding that `complete_removal_detectable_80` is false at the scale of every candidate of interest
(a disclosed limitation already; it becomes a design failure only if the founder's accelerator narrative would rely on
`G17` as protection, which `ADR-102` says it must not).

---

## 11. Register of open founder decisions and the status of Q1-Q17

### 11.1 Q1-Q17 versus `ADR-102`

| Q | Topic | Status after `ADR-102` | Where here |
|---|---|---|---|
| Q1 | evaluation split | partly decided by `ADR-101` A8 (preference); `ADR-102` delegates the constant to the freeze | Section 1; residual **F1** |
| Q2 | partial independence | **not decided** | **F1** |
| Q3 | declaration content/signer; source A vs B | content/signer **not decided**; source A vs B is an implementation detail (both supported, 5.f) | 5.1-5.2; **F6** |
| Q4 | diffuse confounding / joint `Z` | decided in substance: single-`Z` only (`ADR-101` A7), categorical-only narrow GO (`ADR-102` Q16); joint-`Z` not opened; the regression targets are the FX-A categorical-carrier forms, the equal-weight catalogue forms are expected-miss reports | 9.2-9.3 (P2b-4) |
| Q5 | class (ii) | **not decided** | **F7** |
| Q6 | error control level | rule decided (`ADR-102`: alpha follows the existing contract, else decided before results); value/method ratification open | Section 4; **F4** |
| Q7 | contract version | not decided by any ADR; `ADR-102` puts it in the freeze | Section 7; **F9** (ratification) |
| Q8/Q8a/Q8b | catalogue/generator intent (`booking_month`, `T01`/`T04` columns) | **not decided; not needed for 2b** (no generator/catalogue change; fixtures rewrite `X`,`Y` test-side) | remains open, non-blocking |
| Q9 | `G06`/`G03`/`G10`/`G15` contract-text vs executed-code gaps | **not decided; not needed for 2b**; the freeze binds to the executed code and lists each gap (3.1, 6.1) | remains open, non-blocking |
| Q10 | stratification resolution | **decided** (absorbed in Q15; categorical raw levels only) | 2.1 (2.h) |
| Q11 | suppression / unlocking | partly decided (`ADR-101` A9); block-only action is structural (`evidence_ceiling` only caps, `grading.py:150-169`); strengthening never unlocks another gate's block | 3.3, 3.2 step 5 |
| Q12 | A4 reading | **decided** (no attenuation %, no `G06` 0.50/E-value; tied to the final promotion contract); **Q12(b)** (which contract gates) turned into the concrete scope of Section 3.1 with **F3** for the extensions | Section 3 |
| Q13 | undeclared dataset | **decided** (`WARN`, NOT ASSESSED, no veto) | 2.1 (2.g), 8.4 |
| Q14 | oracle-informed declaration | **decided** (separate claim; mechanism correctness only) | 5.1 (5.i), 8.4 |
| Q15 | numeric `Z` | **decided** (not implemented; limitation) | 2.1 (2.f), 8.2 |
| Q16 | go/no-go | **decided** (narrow GO) | scope of this document |
| Q17 | matched baseline | **decided** (matched usable strata; three estimates side by side) | 1.1 (1.d), 3.2, 8.1 |

### 11.2 Open founder decisions (none chosen here)

| ID | Question | Options (see section) | Blocks 2b code? | Default in force until decided |
|---|---|---|---|---|
| **F1** | Accept `validation`-only with disclosed partial independence? | F1-a validation; F1-b holdout; F1-c pooled; F1-d `stability_credit_weight = 0` engine setting (1.3) | yes | validation only, with the mandatory partial-independence sentence |
| **F2** | Integer-coded low-cardinality columns: categorical or not | F2-a dtype only; F2-b `<= 6` levels; F2-c `<= 12` levels; F2-d declared per `Z` (2.3) | yes | F2-a |
| **F3a** | Materiality (`G15` analogue) in the post-adjustment test | F3a-1 none; -2 combined-window scaling; -3 validation-window (3.6) | yes | none (core only) |
| **F3b** | Adjusted stability across splits | F3b-1 none; -2 add `future_holdout`; -3 add `development` (6.2) | yes | F3b-1 |
| **F3c** | Further contract gates (`G05`-style, `G12`) on the adjusted estimate | none; `G05`-style; `G12` battery (3.6) | no (extensions) | none |
| **F4a** | Is the paired-reduction test part of the freeze? | yes; or deterministic contract-flip only (4.3) | yes | none applied silently |
| **F4b** | Multiplicity method | BH inherited; Holm/Bonferroni; BH under arbitrary dependence (4.3) | yes | none applied silently |
| **F4c** | Alpha | `0.10` inherited; or a separately decided value **before any 2b result** (4.3) | yes | none applied silently |
| **F5a** | Which limitations raise `WARN` | (i) any unassessed declared member; (ii) missing declaration / empty pool / zero assessed only (8.7) | yes | (ii) |
| **F5b** | Power/detectability `WARN` | none; `not_powered_for_single_z_violation` (8.7) | yes | none |
| **F6** | Declaration content and signer for a real dataset (delivered travel dataset) | approve/amend/replace design 2.2 tiers; independent drafting first; supply none (5.2) | no (2b uses test-side declarations) | none for real datasets: missing-declaration `WARN` |
| **F7** | Declared-but-unobservable (class (ii)) consequence | claim only; `WARN`; readiness consequence (5.3) | no | claim only |
| **F9** | Versioning ratification | 1.4.0 + `NONE_V0` default-on; label-only; opt-in (7.3) | yes | 1.4.0 + `NONE_V0`, default-on |

---

## 12. Register of inherited constants (with citations)

All numbers used by `G17` are in this table; nothing else is a numeric constant of the gate (U12).

| Constant | Value | Where it lives | Use in `G17` |
|---|---|---|---|
| `fdr_alpha` | 0.10 | `contract.py:240`; `apply.py:1506` | BH rejection level (4.c) — inheritance argument 4.2, ratification **F4c** |
| BH procedure | `benjamini_hochberg_adjusted(p, family_size)` | `grading.py:31-56` | per-candidate family (4.b) — ratification **F4b** |
| `normal_approx_two_sided_p`, `bootstrap_standard_error` | — | `grading.py:108-134`, `90-105` | `p_Z`, `SE_theta`, detectability SEs |
| `confidence_level` | 0.95 | `contract.py:238` | interval criterion C2, intervals in the record |
| `bootstrap_resamples` / `DEV_BOOTSTRAP_REPS` | 2000 | `contract.py:237`; `apply.py:107` | paired cluster bootstrap |
| `BOOTSTRAP_SEED` | 20260813 | `apply.py:109` | base of the isolated per-(candidate, `Z`) stream |
| `percentile_ci`, interval-widening rule | — | `apply.py:253-260, 587-591` | intervals |
| `min_exposed_records` | 50 | `contract.py:232`; `apply.py:572` | C3 |
| `min_clusters` | 5 | `contract.py:234`; `apply.py:573` | C3 |
| `MDE` formula, `Z_95 = 1.959964`, `Z_POWER_80 = 0.841621` | — | `apply.py:103-104, 263-267`; `power_target` 0.80 `contract.py:235` | C3's `MDE < |harm|`; detectability quantile |
| `MIN_STRATUM_CELL` | 5 | `apply.py:124, 369-371` | usable strata |
| `min_confounder_stratum_coverage` | 0.50 | `contract.py:248`; `apply.py:626`; `contract.py:585-586` | assessability floor (not a veto) |
| sign rule | `harm > 0` | `apply.py:627, 741-743` | C1 |
| evidence cap for a confounding gate | `CAP_EVIDENCE`, `PREDICTIVE` | `contract.py:424-425, 594-595` | `G17` failure action |
| level tuple for confounding gates | `ADJUSTED_OBSERVATIONAL` | `contract.py:616-626` | `G17` registration |
| harm orientation | `harm_multiplier` | `outcomes/aggregation.py:120-122`; `apply.py:584` | all harm quantities |
| evaluation split | `validation` | `ADR-101` A8; `apply.py:106` | 1.b — ratification **F1** |
| categorical determination | non-numeric dtype | `engine.py:394-405` (dtype rule); `ADR-102` Q15 | 2.2 — decision **F2** |
| **Explicitly NOT used** | `max_adjusted_attenuation` 0.50, `min_e_value` 1.50, `min_holdout_effect_retention` (as a `G17` criterion), `max_robustness_*`, `min_material_*` (unless F3a), any new alpha (unless F4c-ii) | `contract.py:242-243, 256, 260-261, 264-265` | `ADR-102` Q12 |

---

## 13. Traceability to `ADR-102` and `ADR-101`, and what this document does not do

| Clause | Where |
|---|---|
| `ADR-102` Q16: `k=1` -> pre-declared causally-admissible categorical `Z` -> independent evaluation split -> multiplicity -> adjusted promotion test -> attribution; numeric `Z` out; no manufactured `k=1` candidates | Sections 2, 1, 4, 3, 8.6; 2.1 (2.f); 9.5 |
| `ADR-102` Q12: no attenuation %, no `G06` 0.50/E-value; the block decision is "after admissible adjustment no longer satisfies the final promotion contract" | Section 3 (rule 3.3, exclusions 3.1), U14/U15, M4 |
| `ADR-102` Q13: missing declaration = `WARN`, NOT ASSESSED, never `PASS`, never a veto | 2.1 (2.g), 8.4-8.5, P2b-6 |
| `ADR-102` Q15: numeric `Z` limitation, not counted in "N assessed" | 2.2, 8.1-8.2, U5, P2b-7 |
| `ADR-102` Q17: matched baseline, three estimates side by side | 1.1 (1.d), 3.2, 8.1 |
| `ADR-102` Q14: fixture declaration proves mechanism correctness only | 5.1 (5.i), 8.4 |
| `ADR-102`: freeze constants (split, pool, multiplicity/alpha, ordering, stability, version, post-adjustment test); alpha inherited or decided before any result | Sections 1-7; F4 |
| `ADR-101` A1-A9 | 2.1 (A1, A2, A7), 3.5 (A3), 3.1 (A4), 8.6 (A5, A6), 4 (A7), 1 (A8), 3.2 step 5 (A9) |
| `ADR-100` D4 acceptance invariant; `ADR-101` bounded guarantee | 8.4 (claim), 10 (S-E, design-wrong signals) |
| `ADR-064`/`G16` versioning precedents | Section 7 |

**This document does not:** implement anything; change any gate, engine, contract, generator, catalogue or threshold;
choose any value of an open item; run any fixture, simulation or measurement; touch the frozen `TASK-102` bar; raise
`D2` Part B (stays 2/5); create any `k = 1` candidate on a frozen real dataset; open Phase 2c; change `TASK-057`/outreach
(`ADR-094`); or claim any recall, evidence or safety improvement. It fixes what 2b must build and how it will be judged,
before any result exists.

---

## 14. Revision 1 — pre-registered predictions for the read-only block-rule simulation (registered 2026-09-24, BEFORE any run of the block-rule simulation)

This section is committed in its own commit, together with the unrun scratch scripts `docs/analytics/task-105-evidence/
rev3_g17_block_sim.py` and `rev3_validate_estimator.py`, **before** the simulation was executed. The only thing run before
this commit was the estimator-arithmetic check (`rev3_validate_estimator.py`: the replica's adjusted point estimate and
coverage against the real `_stratified_adjustment`, six invented datasets, agreement to `1e-6`; it prints no rule outcome).
The rest of Revision 1 (Section 15 and edits to Sections 3-4, 8-11) is committed afterwards and cites these predictions
unchanged. A prediction below is never edited after a result; a wrong one is scored as wrong.

**Simulation design (fixed here).** Replica of the Section 3.3 rule on invented `validation`-sized data: `N = 2,462` rows,
`P(exposed) = 0.27`, noise sd 250, `B = 2,000` paired cluster-bootstrap replicates, percentile intervals as
`apply.py:253-260`, criteria C1-C3 evaluated as in Section 3.1 (pooled-within-arm `pooled_sd` on the usable rows; this
`pooled_sd` and the bootstrap/criteria layer are a replica, **not** validated against real code), one-sided `p_Z`, BH with
`family_size = m` at `fdr_alpha = 0.10`. 2,000 datasets per cell. Cells: (a) **exact null** (`Z` independent of `X` and
`Y`; true `theta = 0`): clusters `K in {5, 10, 50}` (random assignment, no cluster effect), prognostic strength
`gamma in {0, 300}` (each `Z` shifts `Y` by `gamma * (level - 1)`, 3 levels), `m in {1, 3}` independent `Z`, and true effect
`beta` at four locations computed analytically from `n` and `sd` only: `b_c2 = 1.96 * SE0` (crude at the C2 boundary),
`b_c3 = (1.96 + 0.8416) * SE0` (crude at the C3/`MDE` boundary), `b_mid` (their midpoint: crude usually passes C2 but fails
C3), `b_far = 6 * SE0`, with `SE0 = sd_total * sqrt(1/n_e + 1/n_c)`; (b) a **confounded positive control** (`Z` drives `X`,
`K = 50`, `gamma = 300`, `beta = 0`); (c) **M-bias** (`Z = 1[U1 + U2 > 0]`, `X` depends on `U1`, `Y` on `U2`, so `Z` is a
pre-exposure collider of two independent causes; `K = 50`, `beta in {80, 120}`). Two attribution variants are computed on
the same draws (Section 15.1): **S** = block iff rejected and `F_adj \ F_c != {}` (the Section 3.3 text as written);
**A** = block iff rejected and `F_c = {}` and `F_adj != {}` (the matched crude satisfies all core criteria). Reported per
cell: `reject_any` (BH rejects some assessed `Z`, whatever the criteria), `block_S`, `block_A`, deterministic-flip rates
`flip_S`, `flip_A` (no `p`-value; the F4a-(ii) alternative), the share of S-blocks with `F_c != {}`, mean `SE_theta`.

| ID | Prediction (approximate; hand arithmetic) | Falsifier |
|---|---|---|
| **R1-P1 (structure)** | In every dataset of every cell: `block_A => block_S`; `block_S => flip_S`; `block_S => reject_any` (deterministic implications) | any violation = defect in the replica |
| **R1-P2 (rejection event, large `K`)** | `K = 50`, `gamma = 0`: `reject_any` in `[0.07, 0.13]` for `m = 1` (one-sided uniform `p`, point 0.10) and for `m = 3` (independent `Z`, point 0.09-0.10) | outside the range: SE calibration of `theta` is off |
| **R1-P3 (few clusters are anti-conservative)** | `reject_any` **exceeds 0.10** at `K = 5` (`gamma in {0, 300}`, `m = 1`): predicted range `[0.13, 0.35]`; at `K = 10` predicted `[0.10, 0.20]`; at `K = 50` within `[0.07, 0.13]`. The bound `P(reject) <= alpha` is therefore **not** valid for the normal approximation on a bootstrap SE at `K` 5-10 | `reject_any <= 0.11` at `K = 5` |
| **R1-P4 (boundary block rate, prognostic-neutral `Z`)** | `gamma = 0`, `K = 50`, crude at `b_c2` and `b_c3`: `SE_theta` about 0.4 EUR (hand: `sd * sqrt(3 * 0.222 * (1/n_e+1/n_c) / n_c)`); `block_S <= 0.02` (point 0.003), `flip_S <= 0.06`. Rejection is near `alpha` but the attributable-loss conjunct is rarely met because `theta_hat` is tiny against the criterion's own SE | `block_S > 0.02` |
| **R1-P5 (boundary block rate, prognostic `Z`)** | `gamma = 300`, `K = 50`, `m = 1`, crude at `b_c2` and `b_c3`: `SE_theta` about 10-12 EUR (comparable to the criterion SE); `block_S` in `[0.005, 0.06]` (point 0.02) and **strictly greater than the `gamma = 0` cell at the same location**; `flip_S` in `[0.02, 0.15]`. So the false-block rate at a boundary is set by `SE_theta / SE_crude`, not by BH alone | `block_S` not greater than the `gamma = 0` cell, or `> 0.10` |
| **R1-P6 (cap)** | Across all exact-null cells with `K = 50`: `max block_S <= 0.06`; at `K in {5, 10}` no point claim, but the ordering `block_S <= reject_any` holds and `max block_S` at `K = 5` is reported; **if any null cell exceeds `block_S = 0.10` that is scored as an S-A stop-condition hit** (Section 10), not explained away | any null cell `> 0.10` |
| **R1-P7 (`b_far`)** | Crude 6 SE from every boundary: `block_S <= 0.005` at `K = 50` (all cells) | `> 0.01` |
| **R1-P8 (attribution variant, crude fails a different criterion)** | Cell `gamma = 300`, `K = 50`, `m = 1`, `beta = b_mid`: `block_S > block_A` with `block_S - block_A >= 0.003`, and **at least 50%** of the S-blocks have `F_c != {}` (the matched crude already fails C3 there); `block_A <= block_S` everywhere by R1-P1 | `block_S == block_A` in that cell |
| **R1-P9 (positive control)** | Confounded cell: `block_S >= 0.95` and `block_A >= 0.95` (crude about 170 EUR, adjusted about 0) | `< 0.90` = defect in the replica |
| **R1-P10 (M-bias, a wrongful-block route)** | `Z` a pre-exposure collider, crude unbiased: adjusted harm `<` crude harm in `>= 95%` of datasets; `beta = 80`: `block_S` in `[0.30, 0.95]` (point 0.70); `beta = 120`: `block_S <= 0.50` (point 0.15). The rule blocks a candidate whose crude estimate is correct, because it assumes adjusted is better | `block_S(beta = 80) < 0.20` (then the collider bias is smaller than the hand estimate of about -55 to -70 EUR) |

**Supersession statement (fixed now).** `P2b-10` (Section 9.3) treated the adjusted estimate as deterministic and ignored the
`p_Z` conjunct; `P2b-11` predicted the false-block probability "expected well below" 0.10 by virtue of the attributable-loss
conjunct. Both are superseded: `P2b-10R` := R1-P4/R1-P5 (knife-edge with the `p_Z` conjunct and a stochastic adjusted estimate) and
`P2b-11R` := R1-P2/P3/P6/P7 (null calibration with the crude exactly at the C2 and C3 boundaries and few-cluster cells). No
further prediction is added after the run; Section 15.4 only records the mapping and the scoring. The original rows stay as
written and are scored against the same simulation where they overlap.
