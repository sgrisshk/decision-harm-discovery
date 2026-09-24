# TASK-105 — `G17` design correction (Part A) and pre-code falsification plan (Part B), per `ADR-104`

**Owner:** STATISTICS (lead), ARCHITECT (support). **Recorded:** 2026-09-26. **Status:** DOCUMENT ONLY.
No code, no engine / gate / `apply.py` / `contract.py` / `input_contract.py` / generator / catalogue / threshold change; no
change to `ADR-100`/`101`/`102`/`103`/`104` or frozen `TASK-102`/`ADR-097` text; **no simulation, fixture or measurement of any
kind was run for this document**. Every prediction in Part B is registered here, before any run exists, and is frozen by the
commit of this file; a change after a result is seen is a new dated version, never an edit. The acceptance bar is
**deliberately not set here** (Section 8): it is an open founder decision that must be fixed, in writing, before anything is run.

**Read in full before writing:** `ADR-104`, `ADR-102`, `ADR-101`, `ADR-100`; `docs/analytics/task-105-2b-contract-freeze.md`
(incl. Revision 1, Sections 14-15); `docs/analytics/task-105-evidence/rev3_*` (scripts, `.json`, `.out`);
`docs/analytics/task-105-k1-confounding-protection-design.md`; the real code `packages/analytics/src/policy_analytics/validation/apply.py`
(`_stratified_adjustment` 337-381, `cluster_cells` 195-221, `cluster_bootstrap_replicates` 224-257, `percentile_ci` 253-260 region,
`G03`/`G04`/`G06` blocks 566-627) and `contract.py` (`ValidationThresholds` 220-293). Line citations are to this worktree.

**Vocabulary.** *Confirmed(H, I)* := `H > 0` and the lower end of the 95% cluster-bootstrap percentile interval `I` is `> 0`.
*Matched crude* `H_c`, *adjusted* `H_Z`, *full crude* `H_full` are as in the freeze Section 3.2 (same rows, same harm orientation).
*Declared confounder* := a declaration entry whose role is `confounder`. *NOT ASSESSED* is a `WARN` gate state (fail-open,
`ADR-102` Q13, `ADR-104` F5), never a `PASS` of the check and never a block.

---

## 0. Summary of what this document does and does not decide

| Item | Where decided |
|---|---|
| Roles, blocking only for declared confounders in a calibrated regime; collider / mediator / unknown / numeric / low coverage / low cluster count => NOT ASSESSED; `F10` (matched crude satisfies all); validation-stage separately-named test (`F11`, `F1`); `F4a-K` conjunct not accepted; `F2` not global; `F12` 0.50 as eligibility; 1.4.0 iff new semantics | **Decided by `ADR-104`** (Section 9 lists them; this document only makes them executable) |
| Declaration schema, hashing, verifiability, exact claim wording | **Specified here** (Section 1, 6) |
| Assessability ladder and blocking preconditions | **Specified here** (Section 2) |
| Attribution rule made precise | **Specified here** (Section 3); one reading choice flagged as an ambiguity of `ADR-104` (Section 9) |
| The decision test `DCAL-V` | **Specified here from first principles as far as it can be** (Section 4). **A null-referenced evidence requirement cannot be specified without a further statistical rationale; the missing rationale is listed (Section 4.5), not invented** |
| "Calibrated inference regime" | **Defined by what must be demonstrated** (Section 5); the minimum cluster count and any small-cluster method are **OPEN** (Section 5.4) |
| Falsification plan and predictions | **Specified here** (Sections 7, 10) |
| Acceptance bar (ceilings, power floor, regime boundary, whether mis-declaration counts) | **OPEN FOUNDER DECISION**, neutral options and consequences in Section 8; nothing chosen |
| Which result means "defer `G17`" | **Stated here** (Section 11) |

**Headline honesty statement.** The only decision rule that can be written down without a further statistical rationale is a
deterministic one (`R0`, Section 4.3): block iff the matched crude is confirmed on the same rows and the adjusted estimate
for a declared confounder is not, with attribution and regime preconditions. `R0` has **no error-rate control by
construction** (nothing references a null). Prior read-only evidence (the Revision 1 replica, Section 10.1) already measured
deterministic-flip rates of 0.4-20% in exact-null cells with a prognostic `Z`. This document therefore **predicts that `R0` fails any
no-confounding false-block ceiling of 0.05 or lower, and probably 0.10**, in prognostic-`Z` cells (Section 10.2). Whether to
spend a run confirming that, to supply the missing rationale first (a different final contract, needing its own predictions), or
to defer now is the first founder question (Section 8, Q-0). Nothing here optimises the rule against any result.

---

## 1. Causal-role declaration (`ADR-104` Decision 2)

### 1.1 What is declared, and by whom

A causal role is a property of a **triple (exposure column `x`, candidate `Z`, outcome `o`)**, not of `Z` alone: the same column can
be a confounder of `x -> o` and a collider of `x' -> o`. The declaration is therefore keyed by the triple. (`ADR-104` states the roles per `Z`; this
is the smallest change that makes them well-defined; flagged as an ambiguity in Section 9.)

```
causal_role_declaration (schema_version "1")
  outcome_id:            <outcome definition id>
  pre_exposure_order:    [[tier-0 columns], [tier-1 columns], ...]      # kept from the freeze Section 5.a-5.b
  entries: [
    { exposure_column: <x>,
      z_column:        <Z>,
      role:            "confounder" | "collider" | "mediator" | "unknown",
      kind:            "categorical" | "numeric",                      # declared; not inferred from storage type (ADR-104 F2)
      rationale:       <non-empty text; required for every role except "unknown">,
      basis:           "domain_knowledge" | "reviewed_dag" | "data_dictionary" | "other",
      signed_by, signed_at }
  ]
```

* **Default role is `unknown`** for any (`x`, `Z`, `o`) with no entry. There is no way to configure a different default.
* **Who declares:** the dataset owner at onboarding, the same role and step as `heterogeneity_column` / `seasonality_column`
  (freeze 5.e). Never the discovery engine, never the validator, never an agent working on the candidate. It is made before any candidate
  exists and is immutable once a validation run starts (changing it = a new declaration hash = a new run).
* **`G17` executes a declaration; it does not discover causal structure** (`ADR-104` Decision 2). No data-derived quantity may
  alter a role. Data-derived descriptives (e.g. association of `Z` with `X` and `Y`) may be reported but never gate.
  *Why data cannot decide:* the observed joint law of (`X`, `Z`, `Y`) does not identify the role; a pre-exposure `Z` that is a common
  cause of `X` and `Y` and a pre-exposure `Z` that is a collider of two independent causes (the `rev3` M-bias cell) both show `Z`
  associated with `X` and with `Y`, and both make the adjusted estimate differ from the crude one. The `rev3` confounded and M-bias
  cells illustrate this: adjusted differs from crude in both (crude 172.5 -> -0.3; crude 80.1 -> 22.6). Only the crude/adjusted difference is observable, not
  which one is closer to the truth.

### 1.2 What is verifiable and what is not

| Verifiable by the loader (fail-closed) | Not verifiable (an assumption, stated in every claim) |
|---|---|
| Schema well-formed; enumerations valid; `signed_by`/`signed_at` present | That the role is causally correct |
| Referenced columns exist; `Z != x`; `Z` has feature role `DECISION_TIME` and is in `adjustment_eligible` (`input_contract.py:141-146` pattern); no `OUTCOME`/`POST_DECISION`/`IDENTIFIER`/`UNKNOWN` column is referenced | That "pre-exposure" in the tier list is a causal fact, not only a recording-time fact |
| `role = confounder` requires `tier(Z) < tier(x)` strictly and both listed (freeze 5.b); same tier or unlisted => entry NOT ASSESSED (`declaration_inconsistent`) | That the declaration pre-dates the candidate, or was made without looking at outcomes (the hash is stored, not a proof) |
| No duplicate (`x`, `Z`) entries (conflict => loader error => whole declaration NOT ASSESSED, `declaration_invalid`) | Completeness (a missing confounder is undetectable: `ADR-100` class iii) |
| Declared `kind = categorical` is consistent with the frame (a `Float*` dtype declared categorical is `not_assessed(declared_kind_inconsistent_with_dtype)`); an integer dtype declared categorical is allowed **because the declaration says so**, not because of the storage type (`ADR-104` F2). A mislabelled numeric threshold `Z` produces many singleton strata and is caught by the coverage floor (Section 2), not by a cardinality heuristic | That `kind` reflects the variable's statistical nature |
| Hash recorded (Section 1.3) | Signer competence |

### 1.3 Hashing into the manifest

`causal_role_declaration_sha256 = sha256(canonical JSON)` where canonical JSON is the declaration object with keys sorted, entries sorted by
(`exposure_column`, `z_column`), columns sorted **within** each tier (tier order preserved), separators `(",", ":")`, ASCII-escaped. It replaces the
freeze's `pre_exposure_order_sha256` (the tier list is now inside the same hashed object). Recorded in the run manifest
(`apply.py:1572-1594` dict) as `causal_role_declaration_sha256` and `causal_role_declaration_source` (`manifest` / `sidecar` / `none`) and repeated in `G17`'s
diagnostics. Storage routes (manifest `validation_roles` 1.1.0 or explicit sidecar; both present = loader error) are the freeze's 5.f, unchanged.

### 1.4 The claim the mechanism may make

> **Conditional-capability claim.** *If the causal-role declaration is correct, `G17` can perform the intended adjustment check for the declared
> confounders that it was able to assess. It does not show that the declaration is correct, that a real user can supply a correct declaration, that
> the system can infer one, or that confounding is absent.* (`ADR-102` Q14, `ADR-104` Decision 2.)

A fixture declaration written by someone who has read the generator proves only the antecedent-conditional mechanism behaviour. Passing fixtures does not close `D2` Part B and is not external evidence.

---

## 2. Assessability ladder — when `G17` may compute and when it may block (`ADR-104` Decisions 3-4)

For a candidate `c` on the promotion path, evaluate **in this order**; the first rung that applies fixes the state of that
(candidate, entry) pair and **no later rung runs**. Rungs 1-7 involve no outcome value: they use the declaration, `Z`, the exposure mask and the cluster column only.

| Rung | Condition | State | Blocks? |
|---|---|---|---|
| 1 | `len(conditions) >= 2` | `PASS not_applicable_k_ge_2` (`G16` unchanged) | never |
| 2 | no declaration, or declaration invalid | `NOT ASSESSED (no_declaration | declaration_invalid)` | never |
| 3 | no entry for (`x`, `o`) with role `confounder` (only `collider`/`mediator`/`unknown`/none) | per entry: `not_an_adjustment_target(collider | mediator)`, `not_assessed(role_unknown)`; if no entry is a confounder, gate = NOT ASSESSED `no_declared_confounder` | never |
| 4 | entry inconsistent (tier / dtype / kind) | `not_assessed(declaration_inconsistent | declared_kind_inconsistent_with_dtype)` | never |
| 5 | `kind = numeric` | `not_assessed(numeric_not_supported)`, listed with the numeric-`Z` limitation text; **not counted** as checked (`ADR-102` Q15) | never |
| 6 | matched-strata **coverage** `< 0.50` (exposed rows in usable strata / all exposed rows; usable stratum = `>= 5` exposed and `>= 5` comparison, `MIN_STRATUM_CELL`) or no usable stratum or an empty arm | `not_assessable(coverage_below_eligibility_floor | no_usable_strata | empty_arm)`. **0.50 is a coverage-eligibility rule only; reaching it is not evidence of anything** (`ADR-104` F12). The `(0.0, 0.0)` return of `_stratified_adjustment` at `apply.py:374-375` is a sentinel, never an adjusted effect | never |
| 7 | the **inference regime** (Section 5) is not met for this candidate's matched rows (cluster count, and any further pre-declared condition) | `not_assessable(inference_regime_not_calibrated)` with the observed count and the required minimum | never |
| 8 | assessed | run the decision test `DCAL-V` (Section 4) | only per Section 4 |

Rules that follow directly from `ADR-104`:

* **Collider / mediator / unknown are never adjusted for by `G17`.** No adjusted estimate is computed or reported for them (avoids presenting an adjusted number for a role that
  the contract forbids adjusting for); the entry is listed with its role. (A descriptive crude is already in `H_full`.)
* **Missing declaration != pass.** Rung 2 renders exactly `confounding_assessment: unavailable — no admissible-Z declaration` (`ADR-102` Q13), shown to users as
  **"Confounding check: NOT ASSESSED — no admissible-Z declaration. This is not a pass of the check."**
* **Categoricality comes from the declaration** (`kind`), verified only for consistency with dtype; never from integer storage or cardinality (`ADR-104` F2). The freeze's F2-a/b/c cardinality options are withdrawn as
  the global rule.
* **Single-`Z` checks only** (`ADR-101` A7; freeze 2.e). A declaration with more than one confounder for the same `x` means several single-`Z` checks, each a *partial* adjustment; see the multiplicity gap in Section 9 (item A-4).
  A conservative option (v1 assesses only when exactly one declared confounder exists for `x`, otherwise NOT ASSESSED `multiple_declared_confounders_no_multiplicity_rule`) is presented as **O-m** in Section 8 and not chosen.

---

## 3. Attribution (`ADR-104` `F10`, `ADR-101` A5/A6)

A `G17` block is **credited** only if the candidate would really have been promoted without it. Precisely, both conjuncts must hold:

* **(A-1) contract-level counterfactual.** With `G17` replaced by `PASS`, the actual gate ladder (`G00`-`G16` as executed) yields policy readiness `>= SHADOW_POLICY` (freeze 8.6 counterfactual via the real
  `classify_evidence_level` / `assign_policy_readiness`). Incidental blocks by `G12` etc. get no credit (`ADR-101` A5).
* **(A-2) test-level attribution.** The **matched crude** on the validation rows of the entry satisfies **all** criteria that `DCAL-V` applies to the adjusted estimate (Section 4.2). A candidate whose matched crude already fails any of them is *not* blocked (nothing is attributable to
  adjustment). This is `F10` as decided: the matched crude satisfies **all** criteria; the "flipping criterion only" reading is withdrawn.

Consequence, stated plainly: the mechanism is silent where the validation split is weakest (a genuinely confounded candidate whose validation matched crude is not confirmed is never blocked). This is the freeze's `P2b-12`
behaviour and remains a disclosed limit, not a defect the design tries to remove. A block is recorded with `credited = true`; a `G17 FAIL` with `credited = false` (another gate already caps) is
reported but does not count toward "what the mechanism stopped".

---

## 4. The decision test: `DCAL-V` (Declared-Confounder Adjustment-Loss test on `validation`) (`ADR-104` `F11`, `F1`)

### 4.1 Name and what it is not

`DCAL-V` is a **new, separately named, validation-stage safety test**. It is **not**:

* a re-application of `G03` (sample adequacy and `MDE < |harm|`, executed on `development`, `apply.py:566-581`) or `G04` (development interval, `apply.py:583-602`);
* a re-evaluation of "the promotion contract after adjustment" (`ADR-102` Q12's framing is superseded by `ADR-104` `F11`);
* `G06` (attenuation `0.50`, E-value, joint adjustment on `development`, `apply.py:606-627`): **no percentage, no E-value, no `max_adjusted_attenuation` is used or reused**;
* `G05` (search-family multiplicity) or `G12` (robustness), which stay as executed;
* the `F4a-K` significance/knife-edge conjunct (Section 4.5 explains what its absence costs);
* a test of whether the effect exists, or of whether the declared confounder *explains* the effect. A block asserts only what is written in Section 4.4.

### 4.2 Estimand and the criterion set (first principles)

* **Estimand.** `_stratified_adjustment` weights within-stratum exposed-minus-comparison differences by the **exposed** counts of the usable strata. Under the declared assumptions (within usable strata, `x` is as-good-as-random given `Z`; positivity; `Z` is not affected by `x`) it targets
  the effect on the exposed (ATT). The crude difference on the same rows equals ATT plus the selection difference `E[Y0 | exposed] - E[Y0 | comparison]` over the same strata; hence `theta = H_c - H_Z` estimates the bias in the crude **attributable to `Z`**, with no
  contamination from effect heterogeneity across the `Z` levels. This is why the matched crude (same rows, Section 3.2 of the freeze) is the correct baseline, and why comparing with a full-sample crude would mix in a population shift.
* **What "the evidence for harm survives adjustment" is made of.** The single statistical object the validation split can supply about an effect estimate is the same for the crude and the adjusted estimate: sign and a 95% cluster-bootstrap percentile interval on identical
  clusters (from **one paired resample**, so the two intervals are jointly generated). Criterion set `S`:
  * **S1** `H > 0` (harm orientation);
  * **S2** the lower end of the 95% percentile interval `> 0` (`confidence_level` = 0.95 is the existing constant; intervals are widened to contain the point estimate exactly as `apply.py:587-591` does).

  `Confirmed(H, I) := S1 and S2`.
* **What is *not* in `S`, and why.** (i) `MDE < |harm|` (`G03`): with the same standard error it is a strictly stricter version of S2 (`|H| > 2.8 SE` versus `1.96 SE`) and would add a second knife-edge; it is a design-level detectability statement, not a property of an estimate. (ii) `n_exposed >= 50`, `clusters >= 5`,
  coverage `>= 0.50`, cluster-count regime: these are **eligibility** conditions of Section 2 evaluated once on the matched rows and identical for both estimates, so they can never "flip". (iii) materiality (`G15`/C4), temporal stability (C5),
  search-family multiplicity (C6), robustness (C7): not part of `DCAL-V` (`ADR-104` `F3a/F3b` are deferred and this test is not the promotion contract). If the founder later wants any of them inside `DCAL-V`, that is a new test version.
  *This choice of `S` is a specification made here from the estimand argument above, not an inherited constant; it is a point the independent reviewer should check (Section 9, A-6).*

### 4.3 The rule under test, `R0`

For a candidate with `k = 1`, exposure column `x`, and each entry `j` of the declaration with role `confounder` that survives the ladder of Section 2 (rung 8):

```
compute on validation rows of the usable strata of Z_j (one paired cluster bootstrap, B = 2000, deterministic isolated stream):
    H_c,  I_c    matched crude and its 95% percentile interval
    H_Zj, I_Zj   real _stratified_adjustment point estimate, and its interval from the same resamples
Block_j  :=  Confirmed(H_c, I_c)  AND  NOT Confirmed(H_Zj, I_Zj)  AND  (A-1 holds)
G17 = FAIL  iff  exists j with Block_j        (a block caps evidence at PREDICTIVE, freeze 7)
```

Properties that follow by construction (all become property tests / mutants at code time, not now):

1. A strengthening adjustment (`H_Z > H_c`, the suppression case, `ADR-101` A9) cannot be blocked on magnitude; there is **no magnitude criterion**. A crude of +100 adjusting to a still-confirmed +40 is not blocked (`ADR-102` Q12's example).
2. If the matched crude is not confirmed, nothing is blocked (`F10`).
3. Any state other than `Confirmed -> not Confirmed` for an assessed declared confounder is not a block. No collider / mediator / unknown entry ever reaches the rule.
4. No numeric constant is new **except the regime's minimum cluster count (Section 5.4), which is OPEN**: `confidence_level`, `B`, `MIN_STRATUM_CELL`, the 0.50 coverage eligibility, `min_exposed_records` are inherited. The freeze's static "no new constant" test (U12) must whitelist the regime constant explicitly.

### 4.4 What a block asserts (exact, and nothing more)

> "Promotion stopped by `G17` (`DCAL-V`): under the declaration that `Z` is a confounder of this exposure and outcome, on the validation split (matched strata), the
> exposed-vs-comparison harm estimate is confirmed without adjustment but is **not confirmed after adjustment for `Z`**. This does not establish that the effect is absent or that
> `Z` explains it; it establishes that the evidence for harm on this split does not survive the declared adjustment. Correctness of the declaration is assumed, not verified."

### 4.5 What cannot be specified without a further statistical rationale (stated, not invented)

`R0` contains no reference to a null hypothesis. A block can therefore be produced by sampling noise in the adjusted estimate alone: the adjusted estimator has its own variance, and whenever the crude is near the confirmation boundary the pair can fall on
opposite sides even if `Z` confounds nothing. The Revision 1 replica measured exactly this, for the deterministic flip (Section 10.1). The obvious repair, requiring statistical evidence that the reduction `theta > 0` (the freeze's `p_Z` /
`F4a`), is the extra conjunct `ADR-104` declined to accept "now": it "needs an independent statistical rationale, not a fix for an unpleasant simulation result". I therefore do **not** put it in `R0`. What that rationale would have to supply, and which I cannot supply from
the material in the repository:

| # | Missing item | Why it is not derivable here |
|---|---|---|
| M1 | **Which error is controlled, and over what population**: false block per *promoted candidate* (conditional on the crude being confirmed), or FWER per candidate over its declared confounders, or FDR across candidates | The contract has FDR over the *search* (`G05`); `ADR-104` declines BH (`F4b/F4c`) as blocking semantics; no per-candidate false-block error rate is stated by any ADR |
| M2 | **The null hypothesis and margin** that makes a block a rejection: `theta <= 0` (any reduction, collapses to a deterministic flip at large `n`) versus `theta <= delta` with `delta` a materiality of confounding | `delta` would be a new constant; `ADR-102` forbids a new attenuation percentage and `ADR-104` rejects the knife-edge conjunct; a materiality-derived `delta` needs an economic argument that does not exist |
| M3 | **A reference distribution that is valid at the stated cluster counts** for the paired statistic | The normal approximation on a bootstrap SE was measured anti-conservative at 5-10 clusters and over-conservative for a prognostic-neutral `Z`; `ADR-104` Decision 4 forbids a heuristic constant to repair it. This is the regime question of Section 5 |
| M4 | **Multiplicity across `m` declared confounders** without BH | `F4b/F4c` not ratified; under `R0` there are no `p`-values to correct, so `m` simply inflates the false-block rate (union of `m` flips, measured 13% for `m=1` to 19-20% for `m=3` in the replica's prognostic cells) |
| M5 | **How the confirmation level (0.95, S2) and any evidence level for `theta` relate**, i.e. who sets two levels and on what grounds | No inheritable second level |
| M6 | **Whether a mechanism whose power against complete removal at the delivered validation size is limited (design Section 10.1: 80%-power floors 58-111 EUR, `0.5 H_raw - c80 < 0` for all four exposures) should block at all**, or report only | A product decision, not a statistical derivation |

**Consequence for the plan.** Part B falsifies `R0` (the only fully specified rule). If the founder supplies M1-M5 before a run, the final contract becomes a different rule (`R1`) that needs its own dated predictions and **replaces** `R0` as the scored rule; only one rule is ever scored.
The falsification harness computes `theta_hat`, its bootstrap SE and the deterministic flip as **raw output** either way (they are needed to interpret a failure), but they are not scored variants.

---

## 5. The "calibrated inference regime" (`ADR-104` Decisions 3-4)

### 5.1 Definition by what must be demonstrated

A **regime** is the tuple *(estimator `E`, inference method `I`, admissible data range `Rg`, evaluated decision quantity `Q`)*. In v1:

* `E` = the real `_stratified_adjustment` (exposed-weighted, single `Z`, usable strata) and the matched crude on the same rows. Fixed.
* `I` = paired cluster bootstrap (`B = 2000`, resampling clusters with replacement, as `cluster_bootstrap_replicates` does), 95% percentile intervals. **`R0` uses no normal approximation and no `p`-value.** Any other `I` is a different regime.
* `Q` = the block decision of `R0` (and, reported, the coverage of each 95% interval for the true ATT).
* `Rg` = the ranges of matched-row cluster count (and any further pre-declared descriptors) over which the demonstration below was made.

A regime is **demonstrated calibrated** iff, for every null-structure family of Section 7 (no confounding by `Z`; the true adjusted effect fixed and above the confirmation boundary or on it), at every pre-declared grid point of `Rg`, the measured **false-block rate conditional on the matched crude
being confirmed** has a one-sided 95% Monte-Carlo upper bound `<= C_null` (the ceiling; **OPEN**, Section 8), using the real estimator path (Section 10A). "Calibrated" therefore has no built-in nominal level: it means *the false-block rate under the stated nulls is bounded by the pre-declared ceiling at the stated scale*. Interval coverage of the true ATT and of `theta` is
reported per cell; whether it is a further condition is B-8 in Section 8.

Consequences for the runtime: `G17` cannot measure calibration on a live dataset. The regime is a **pre-declared, hashed table** (from the falsification study id, committed) that a runtime check compares against the matched rows' descriptors. Outside the table the state is NOT ASSESSED (rung 7). Adding a regime, method, or grid point is a contract change (new version), not a runtime option.

### 5.2 The descriptors that define the runtime check (definition is OPEN, D-K)

The cluster count that a regime constrains is not uniquely defined. Options (neutral): **(K1)** raw count of distinct clusters among usable-strata evaluation rows; **(K2)** raw count among clusters that contribute at least one *exposed* usable row; **(K3)** an effective count that accounts for imbalance (e.g. the Kish
effective number `(sum n_k)^2 / sum n_k^2`). None is preferred here. The plan's imbalance and exposure-clustering cells (Section 7) are there to show whether the raw count is sufficient; if not, the regime must be defined on a descriptor that is (still without a heuristic constant).

### 5.3 What is *not* permitted

* No heuristic constant to make the existing normal approximation or the percentile bootstrap "work" at small `K` (`ADR-104` Decision 4).
* No choice of `K_min` after seeing which value passes: the selection rule is fixed in Section 5.4 before any run.
* No regime that mixes points that failed the ceiling with points that passed (a regime is a set of grid points **all** of which passed, and the boundary is the lowest such point with everything above it also passed).

### 5.4 OPEN — minimum cluster count and small-cluster inference (`R-1`, founder / statistical decision)

The rule for extracting a boundary from the data is fixed here: **`K_min` := the smallest grid value of the chosen descriptor such that every grid value `>= K_min` passes all null/fidelity cells at its ceiling; if no grid value qualifies, there is no regime** (=> `G17` cannot block => Section 11). What is **not** decided:

| Option | What it is | Consequence (neutral) |
|---|---|---|
| R-1a | Block only where the demonstration covers the delivered scale (K of order the row count, `~2,000`); everything else NOT ASSESSED | On the delivered dataset `G17` can block; on any customer dataset with tens or hundreds of clusters it never blocks. Smallest claim, cleanest evidence |
| R-1b | Block in the largest contiguous grid range that passes (`K_min` from the rule above) | Regime width is an empirical output; a lower `K_min` is only ever justified by a null result at that `K` |
| R-1c | Below `K_min`, keep NOT ASSESSED **until a small-cluster method is separately calibrated** (`ADR-104` Decision 4) | Method families that exist in the literature and are **not evaluated, ranked or recommended here**: a reference distribution with reduced degrees of freedom (CR2/Satterthwaite-type), a wild cluster bootstrap-t, randomization/permutation inference. Each would be a different regime `I` with its own full Part B |
| R-1d | No blocking regime in v1 (`G17` reports crude / matched crude / adjusted only; every outcome NOT ASSESSED for blocking purposes) | Equivalent to "defer the blocking claim", keeps the reporting; no false-block risk, no protection claim |

---

## 6. Interaction with the existing contract, versioning, reporting, compatibility

* **Existing gates.** `G00`-`G16` are untouched and still evaluated exactly as before on the raw effect; `G06` (development, joint adjustment, attenuation/E-value) stays as executed and is not weakened, strengthened, or replaced. `G17` is `k = 1` only; `G16` remains the `k >= 2` safety. `G12` and similar are not credited (`ADR-101` A5).
* **State mapping.** `FAIL` iff a credited block per Sections 3-4. `WARN` iff **no** declared confounder was assessed (rungs 2-7 for every entry, or none declared) — a NOT ASSESSED state, never a `PASS`. `PASS` otherwise (>= 1 declared confounder assessed, no block) **with the limitations list and the conditional-capability claim always attached**; `PASS` is a gate outcome, not a statement about the world. `NOT_EVALUATED` is not used (it grades like `FAIL`, `contract.py:99-101`). Whether *partial* NOT ASSESSED (some entries assessed, others not) also
  produces `WARN` is `F5a`, whose ratification `ADR-104` words ambiguously (Section 9, A-8); default in force: not `WARN`, listed in provenance.
* **Version.** `CONTRACT_VERSION 1.3.0 -> 1.4.0` **if and only if** a `G17` with these semantics is implemented (`ADR-104` `F9`): new gate id `G17_SINGLE_CONDITION_CONFOUNDING` (appended, never renumbered), `K1ConfoundingSemantics {NONE_V0, DECLARED_CONFOUNDER_V1}` mapped by contract version, `NONE_V0` for reproduction at gate-outcome level, per the `ADR-064` precedent (freeze Section 7). If Part B leads to deferral, **no bump and no code**. The regime table and its study id are part of the versioned constants; a change to either is a new version.
* **Reported fields (`diagnostics["k1_confounding"]`).** Per (candidate, entry): declared `role`, `kind`, `basis`, status/reason; for every **assessed** entry the **three estimates side by side** — `H_full` (full-sample crude, reported only), `H_c` (matched crude), `H_Z` (adjusted) — with the 95% intervals for `H_c` and `H_Z`, coverage, excluded levels and their exposed share, `Confirmed` flags, cluster count and the regime row that admitted it; `theta_hat` (`H_c - H_Z`) as a **descriptive** quantity (no `p`-value; nothing gates on it);
  **provenance:** `causal_role_declaration_sha256`, source, signer fields, `k1_evaluation_split = "validation"`, `k1_semantics_version`, the regime table id/hash; **attribution:** `{credited, reason, counterfactual readiness, actual readiness, other failed gates}` (Section 3); **limitations:** the conditional-capability claim, numeric-`Z` limitation, unknown latent confounding, the partial independence of the validation split from selection (freeze 1.2), and, for fixtures, the fixture-vs-declaration sentence.
* **Numeric-`Z` limitation text** is unchanged in substance from the freeze 8.2 and remains mandatory: *"`G17` coverage = categorical declared confounders only. Numeric-`Z` confounding protection is not assessed / not supported."*
* **NOT ASSESSED wording** (never a pass): `confounding_assessment: unavailable — <reason>`, rendered as *"Confounding check: NOT ASSESSED — <reason>. This is not a pass of the check."* with `<reason>` from the ladder. **Forbidden** in any field, warning, report or summary: "cleared", "ruled out", "safe", "verified not confounded", "passed the confounding check" without the qualifier, any wording implying numeric-`Z` protection or that role correctness was verified, and any reading of a `PASS` as protection.
* **Compatibility invariant** (to be a test at code time, freeze S-D): `G00`-`G16` outcomes, diagnostics, evidence level and policy readiness are **unchanged** for every undeclared candidate, every `k >= 2` candidate, and every candidate on which `G17` is NOT ASSESSED; only a credited `G17 FAIL` may lower level/readiness. What does change for everyone (and is not covered by "unchanged"): a 17th gate row, the version string, new manifest keys, and a `report.warnings` line for undeclared/NOT ASSESSED `k = 1` candidates (freeze 7.2 item 2 migration text, carried unchanged).
* **What the freeze defaults are now superseded** (recorded so no reader mixes them): `F4a/F4b/F4c` (`p_Z`, BH, alpha 0.10) not used; `F2-a/b/c` not used as a global rule; `F10-a/c` withdrawn; `F11-a/b/c` replaced by the named test; `F1` fixed to `validation` (`ADR-104`) with the freeze 1.2 partial-independence disclosure retained; `F3a/F3b` deferred.

---

## 7. Part B — the falsification plan: negative controls of the final contract

### 7.1 Purpose and rule of engagement

Falsify the **final** contract (`R0` of Section 4.3, unless the founder replaces the rule per Section 4.5 before any run) against pre-declared controls. **One rule is scored. No parameter-variant sweeps of the rule.** The DGP factors below are the structured
description of the *test population*, fixed in this document; they are not tuned after a result. Protocol: (1) this document is committed with the bar OPEN; (2) the founder fixes the bar (Section 8) in a dated record; (3) the harness (Section 10A) is committed **unrun**
with the predictions of Section 10 unchanged; (4) it is run once, outputs are committed unchanged with sha256s; (5) scoring is appended, never edited in; (6) independent freeze review; only then code. A harness or DGP bug found after the run is disclosed and the affected cells are rerun under a
new dated version, with the original result kept.

### 7.2 Shared design constants

Validation-split scale of the delivered data: `N = 2,462`, exposed share `0.27` (as the Revision 1 replica, for continuity), `SE_c` for Gaussian sd 250 = `250 * sqrt(1/665 + 1/1797) = 11.3` EUR (`b_50 := 1.96 SE_c`, `b_80 := (1.96 + 0.8416) SE_c`, `b_far := 6 SE_c`; with a prognostic `Z`, `gamma = 300`, total sd 350 and `SE_c = 15.9` EUR, as `rev3_g17_block_sim.py::cell_beta_bounds`). Clusters: the delivered dataset clusters on `customer_id` (~2.8k customers in the later splits, design Section 4: "close to row-level"), so the delivered-scale cell is **row-level clusters**; small-`K` cells exist for the regime question (Section 5), because the contract permits `K >= 5` (`G03`).
Datasets are generated from `numpy.random.SeedSequence([20260926, cell_index])`; seeds and cell table are committed with the harness.

**Grid of cluster counts (a calibration grid for Section 5, not a contract-variant sweep):** `K in {5, 10, 20, 50, 100, 500, row-level}` (row-level `~ 2,000`).
**Prognostic strength** of `Z` for outcome: `gamma in {0, 300}` (0 = prognostic-neutral; 300 = as in the replica, chosen then, kept for continuity, not fitted).

### 7.3 Controls

Each control gives: DGP, what the correct behaviour is, the metric, cells, `D`.

**Metric conventions (all controls).** *Conditional block rate* = (datasets with a credited block) / (datasets in which the matched crude is confirmed and A-1 holds); this is "wrong stops per legitimately promotable candidate" and is the quantity a user experiences. The *unconditional* rate is reported next to it. A dataset in which the crude is not confirmed is not in the denominator of a false-block rate (`F10`), and is reported as a count.

* **C1 — genuine confounder (must be blocked).** `Z` (declared confounder, `L in {3, 7}` levels) drives both `X` (exposed probability varies across levels, e.g. `0.10/0.27/0.44` for `L = 3`) and `Y` (`gamma = 300`); the true adjusted effect is `0` (**complete** confounding), the crude true effect set to `{2.5, 4, 7} SE_c`
  by scaling the `Z -> X` and `Z -> Y` strengths. Metric: **power** = conditional block rate. Cells: `L x K(10, 50, 500, row-level) x strength` = 24 cells (Gaussian); fidelity cells at `L = 3`, strength `4`, `K in {50, 500}` with `t3` noise, empirical residuals, outcome ICC 0.2 = 6 cells; plus **the two real fixtures** `T01`, `T05` generated by the real `_generate_row` at validation scale (`TASK-104` fixtures; declaration written test-side) = 2 cells. Also reported per cell: the unconditional rate, the share of datasets where the crude is not confirmed (silent).
  *Partial confounding with a remaining effect belongs to C5.*
* **C2 — collider / M-bias (must not be blocked).** `Z = 1[U1 + U2 > 0]`, `X` depends on `U1`, `Y` on `U2` (as `gen_mbias`), `beta in {80, 120}` (the replica's values, kept for comparability; **both true effects positive and the crude unbiased**).
  **C2-a (correct declaration: `Z` declared `collider`)**: NOT ASSESSED (`not_an_adjustment_target(collider)`) in 100% of datasets, zero blocks; deterministic code-path property, `D = 200`, no bootstrap should run for that entry.
  **C2-b (mis-declaration: `Z` declared `confounder`)**: the block rate is **measured and reported** (prior replica: 0.8345 at `beta = 80`, 0.018 at `beta = 120`, `K = 50`); cells `beta x K(50, 500, row-level)` = 6 cells, `D = 2,000`. Its status against the bar is the founder's decision (B-6, Section 8): it is an *identifiability* limit — no data-based rule can distinguish the mis-declared M-structure from a confounder (Section 1.1), so a bar that scores C2-b cannot be met by any rule that ever blocks.
* **C3 — mediator (not an adjustment target).** `X -> Z -> Y` with `Z` recorded pre-decision in the (wrong) metadata; total effect fully mediated (`beta_direct = 0`) and partially mediated. **C3-a (declared `mediator`)**: NOT ASSESSED in 100%, `D = 200`. **C3-b (declared `confounder` with a tier inconsistent with `x`)**: the loader must reject the entry (`declaration_inconsistent`), 100%,
  `D = 200`. **C3-c (mis-declaration: mediator declared confounder with a consistent-looking tier)**: block rate measured and reported, `2 x 2 = 4` cells (`K in {50, row-level}`), `D = 2,000`; the adjusted estimate removes the mediated share, so complete mediation is expected to be blocked at a high rate — a documented over-adjustment exposure, scored per B-6.
* **C4 — no confounding by the declared `Z` (low false-block rate).** `Z` declared confounder but truly independent of `X` (exact null for `theta`), genuine positive effect `beta`; `Z` prognostic-neutral (`gamma = 0`) or prognostic (`gamma = 300`). Grid: `K` (7) `x gamma` (2) `x beta in {b_50, b_80, b_far}` (3) = **42 core cells**, plus the `beta = 0` reporting cells (14; unscored: crude confirmation there is a false positive, not a legitimate candidate).
  **Fidelity cells:** from the anchor `(K = 50, gamma = 300, m = 1, Gaussian, ICC 0, row-independent exposure, equal cluster sizes)` deviate **one factor at a time**: `m = 3` independent declared confounders (the union across `m`, Section 4.5 M4); `t3` noise scaled to the same sd; empirical outcome residuals resampled from the delivered dataset's outcome column after removing the fitted `Z`-level means (if that gitignored frame is unavailable, the stand-in must be
  disclosed and this cell marked unresolved, not silently replaced); outcome ICC `0.2`; exposure assigned at cluster level; log-normal cluster sizes. `6` deviations `x K in {10, 50, 500} x beta (3)` = 54 cells. Metric: conditional block rate; worst-case over the `beta` grid per (K, structure) is the scored number.
* **C5 — suppression / correct adjusted candidate (must not be blocked merely because the magnitude changed).** `Z` drives `X` and `Y` with **opposite** signs so the crude is attenuated (`crude = 0.5 x adjusted`, adjusted true effect `in {b_80, 4 SE_c}`); and **partial confounding with an effect that remains** (`adjusted = 0.4 x crude`, both well above the boundary: the `ADR-102` "+100 -> +40" case).
  `2 x 2 x K(10, 50, 500, row-level)` = 16 cells. Metric: conditional block rate (the candidate is legitimately promotable in both). Correct behaviour: essentially never blocked; a large adjustment must not be a reason.
* **C6 — insufficient inference regime (NOT ASSESSED, deterministic).** Sub-cases (each `D = 200`, permuting the outcome must not change the state): `k = 2`; no declaration; invalid declaration; role `unknown`; role missing; `collider`; `mediator`; declared `numeric`; declared categorical on a `Float` column; integer column declared categorical with `> 50%` singleton strata (coverage below floor); coverage `0.4999` vs `0.5000` (boundary: `< 0.50` not assessable, `= 0.50` assessable; `>=` is the rule); `K_min - 1` vs `K_min` matched-row clusters; no usable stratum; empty arm.
  Correct behaviour: exact expected state and reason code in 100%, **zero blocks**, and never a `PASS`. Any single deviation fails the control (no MC tolerance applies to a deterministic property).

### 7.4 Number of datasets and Monte-Carlo SE

| Cell class | `D` | MC SE at rate `p` |
|---|---|---|
| C4 core and fidelity (false block), C5 | 4,000 | `p = 0.02`: 0.0022; `0.05`: 0.0034; `0.10`: 0.0047; `0.20`: 0.0063; upper 95% bound `= p_hat + 1.645 SE` |
| C1, C2-b, C3-c (power / exposure) | 2,000 | `p = 0.5`: 0.011; `0.9`: 0.0067; `0.95`: 0.0049 |
| Deterministic controls (C2-a, C3-a/b, C6) | 200 each | exactness required (100%); one failure fails the control |
| Real-path anchors and the `T01`/`T05` real-generator cells | 200 | `p = 0.5`: 0.035; `0.1`: 0.021 |

Sample size needed to certify a ceiling `c` with one-sided 95% when the true rate is `0.6 c`: `D >= 10.1 (1 - 0.6 c) / c` -> `c = 0.01: 1,008`; `0.05: 197`; `0.10: 95`. `D = 4,000` therefore certifies every ceiling in Section 8 with room; the real-path anchors (`D = 200`) can certify only ceilings `>= 0.05` and are scored with their (wide) bound. Total vectorised datasets ~ 584k (`(42 + 14 + 54 + 16) x 4,000 + (30 + 6 + 4) x 2,000`); cost is to be measured in a timing-only dry run that prints no decision
quantity; if unaffordable, `D` is reduced **uniformly** and the SE column recomputed, never for selected cells. No optional stopping; `D` and seeds are fixed before the run.

### 7.5 Pass/fail per control (as functions of the bar; the bar itself is Section 8)

| Control | Scored quantity | Pass condition (bar symbols, values OPEN) |
|---|---|---|
| C1 genuine confounder | conditional block rate (power) at each crude strength and `K` inside the regime, real-generator `T01`/`T05` cells | lower one-sided 95% bound `>= P_min` at every in-regime cell listed as "required" by the founder (B-3). A shortfall at delivered scale is reported as a **capability limit**, see Section 11 (D-3) |
| C2-a, C3-a/b, C6 | exact state + reason, zero blocks, no `PASS` | 100% |
| C2-b, C3-c (mis-declared) | reported block rates | scored only if B-6 says so; otherwise reported with the identifiability statement |
| C4 no confounding | worst-case (over `beta` grid) conditional block rate per (`K`, structure), one-sided 95% upper bound | `<= C_null` at every in-regime cell; cells below `K_min` are used to *locate* `K_min` (Section 5.4) and must be NOT ASSESSED at runtime |
| C5 suppression / partial confounding | conditional block rate, upper bound | `<= C_supp` (B-4) at every in-regime cell |
| Conformance of regime table | after `K_min` is set from C4, C1/C5/C6 rerun at `K_min - 1` and `K_min` are *not* new cells; they use the committed cells | — |
| Overall | all scored controls | **conjunctive**: every scored control must pass |

---

## 8. OPEN FOUNDER DECISION — the acceptance bar (not set here, not to be inferred from any result)

The bar must be fixed in writing **before the first run** and by no one who has seen a result. Options are stated neutrally with the statistical consequences; none is recommended and no value below was chosen by whether it lets `R0` (or any rule) pass. The consequences quote only what the registered predictions (Section 10) and the prior read-only replica imply, and are marked as such.

**Q-0. What is the final rule to be scored?** (a) `R0` as written; (b) the founder supplies rationale for M1-M5 (Section 4.5) first; the new rule `R1` is specified, its predictions registered, then scored; (c) defer now without a run.
Consequence: `R0` is **predicted to fail** any ceiling `<= 0.05` and probably `<= 0.10` in prognostic-`Z` cells (Section 10.2); (a) then costs a run to obtain a result already predicted, but that result is a clean, pre-registered "rule without null control is not calibrated"; (b) delays the run but can produce a rule whose null false-block is bounded *if* calibrated at the stated `K` (measured in the replica as not so at `K = 5-10`); (c) needs no run and forfeits the evidence.

**B-1. Maximum conditional false-block rate under no confounding, `C_null`.**

| Option | What is achievable / what it costs |
|---|---|
| 0.01 | Certifiable with `D = 4,000` (needs `D >= 1,008`). Prior replica evidence: the deterministic flip alone (no null conjunct) was 0.4-1.6% only with a prognostic-neutral `Z`, and **11-20%** with a prognostic `Z` at every `K` including `K = 50` (unconditional, includes a `MDE` criterion `R0` no longer has): a rule with no null reference is not expected to reach 0.01 in prognostic-`Z` cells |
| 0.05 | Same; a null-referenced rule could reach it where its test is calibrated, but the replica's rejection event was 0.095-0.12 (nominal 0.10) at `K = 50` and 0.12-0.26 at `K = 5-10` for a prognostic `Z` |
| 0.10 | The nominal level `ADR-102`/freeze inherited (`fdr_alpha`); note `ADR-104` does not ratify it as blocking semantics. Deterministic flip is 0.11-0.20 at every `K` for the prognostic-`Z` cells (replica) |
| other | e.g. tie it to a stated value of a wrong stop (a candidate lost for nothing) |

Statistical note: `C_null` is a bound on **conditional** false blocks per legitimately promotable candidate; the unconditional rate is roughly half of it at the `b_50` boundary and near it at `b_far`.

**B-2. Maximum block rate under a *correctly declared* collider / mediator.** Deterministic: 0 by construction (NOT ASSESSED). The only choice is whether the bar records that as a pass (it is a code-path property, not a statistical finding).

**B-3. Minimum power `P_min` on the genuine confounder, and *where* it is required.** Options for `P_min`: 0.80 / 0.90 / 0.95. Structural cap: for complete confounding with true adjusted effect 0, the adjusted 95% interval includes 0 with probability about 0.95 at best (nominal, before the widening rule of `apply.py:587-591`), so a floor above 0.95 is unattainable by construction, and 0.90-0.95 is attainable only at cells where the adjusted estimate is precise enough.
Options for *where*: (i) every in-regime cell; (ii) only the delivered-scale row-level cell and the `T01`/`T05` real-generator cells; (iii) synthetic cells only. Consequence: design Section 10.1 found the delivered validation split unable to detect a 50% reduction (c80 = 58-111 EUR); complete removal is the easy case, but (ii) may fail at the delivered scale where (iii) passes, which is exactly the "capability at delivered scale" question.

**B-4. Maximum block rate under suppression / a correct adjusted candidate, `C_supp`.** Options 0.01 / 0.02 / 0.05. Predicted near 0 at `K >= 50` (Section 10.2), so a low ceiling costs little; the ceiling matters at `K = 5-10`.

**B-5. Cluster-count regime boundary rule.** Fixed extraction rule in Section 5.4; the open choices are the grid (kept as Section 7.2 unless the founder edits it before the run), the descriptor (D-K: K1/K2/K3), and R-1a-d. Consequence of a coarse grid: `K_min` is coarser, the regime narrower; a finer grid costs a run but is not a parameter sweep of the rule.

**B-6. Are mis-declaration cells (C2-b, C3-c) scored against the bar?** (a) No: the contract claim is conditional on a correct declaration (Section 1.4); the cells are reported as the residual exposure; (b) reported and required to be *disclosed in every claim* (numbers in the report), not scored; (c) scored (block rate `<=` a ceiling). Consequence: **(c) cannot be met by any rule that ever blocks a confounder**, because a mis-declared M-structure or mediator is observationally indistinguishable from a real confounder (Section 1.1); (c) is therefore a decision to defer `G17` (Section 11, D-6). (a)/(b) accept that the protection is only as good as the declaration.

**B-7. Which fidelity cells are in scope of the bar.** (i) all (Gaussian, `t3`, empirical residuals, ICC, cluster-level exposure, imbalance); (ii) Gaussian and the empirical-residual cells only; (iii) Gaussian only (the replica's limit). Consequence: (iii) reproduces the fidelity limitation that `ADR-104`'s finding sits on; (i) is the most severe test and a single failing structure removes the regime (Section 5.3: a regime holds only if all its grid points pass).

**B-8. Whether interval coverage of the true ATT is a further condition of a "calibrated regime".** Reported for every cell either way. If it is a condition, the threshold value is another open number (e.g. nominal `-` a tolerance), for which no inheritable value exists.

**B-9. MC certification rule.** Default proposed for the record (not chosen as a constant of the contract): compare the **one-sided 95% upper (or lower) Monte-Carlo bound** with the ceiling (floor), not the point estimate; alternatives: the point estimate (less conservative), the two-sided 99% bound (more conservative). Consequence: with `D = 4,000` the difference between point and 95% bound is 0.004-0.008 at the relevant rates.

**O-m. Multiple declared confounders per exposure.** (i) assess every declared confounder singly, block if any qualifies (the union inflates the false-block rate with `m`; `m` is a factor in C4); (ii) v1 assesses only when exactly one confounder is declared for `x`, else NOT ASSESSED; (iii) wait for the multiplicity rationale (M4). Consequence: (i) has an uncontrolled `m` dependence under `R0`; (ii) narrows the claim; (iii) blocks the multi-confounder case until decided.

**D-K.** Cluster-count descriptor: K1 / K2 / K3 (Section 5.2).

**R-1.** Regime boundary options (Section 5.4): R-1a / R-1b / R-1c / R-1d.

---

## 9. What `ADR-104` already decided, and what it leaves ambiguous

**Already decided (this document does not reopen any):** the current `G17` is not implemented and the 83% false-block rate is not accepted as a price of safety; admissibility = pre-exposure **and** a justified causal role; roles `confounder` / `collider` / `mediator` / `unknown` with `G17` executing a declaration, and fixtures proving only conditional capability; blocking only for
declared confounders in a pre-declared calibrated regime; collider / mediator / unknown / unsupported numeric / insufficient coverage / insufficient cluster count => NOT ASSESSED, never PASS, never block; with 5-10 clusters `G17` v1 is NOT ASSESSED/WARN until a method is chosen and separately calibrated, no heuristic constant added; `F4b`/`F4c` (BH, alpha 0.10) not ratified;
`F10` matched crude satisfies all promotion criteria; `F11` new separately named validation-stage test, not "re-applying G03/G04"; `F1` evaluation on `validation`; `F4a-K` conjunct not accepted now; `F2` integer-as-categorical not global (from schema/declaration); `F5a/F5b` WARN/fail-open consistent; `F9` 1.4.0 iff a contract bump for new semantics; `F12` 0.50 as coverage eligibility, never evidence of absence; `F3a/F3b` deferred; next step = design correction + one narrow pre-code falsification with a pre-set bar; pass -> independent freeze review -> code; fail -> defer until real data or better causal machinery.
Also carried from `ADR-102`: no attenuation percentage; categorical-only; matched baseline; fixtures prove mechanism only.

**Ambiguities `ADR-104` leaves (each resolved provisionally in this document as noted; the founder should confirm or replace):**

| # | Ambiguity | How this document reads it | Where |
|---|---|---|---|
| A-1 | Roles are stated per `Z`; they are relative to (exposure, outcome) | Roles keyed by (`x`, `Z`, `o`) | 1.1 |
| A-2 | "The matched crude satisfies **all** promotion criteria": which set, on which split? (i) the whole `G00`-`G16` ladder (counterfactual promotion); (ii) all criteria the *new* test applies to the adjusted estimate, on `validation`; (iii) `G03`/`G04` applied to the validation crude (which `F11` says would be a transplant) | Both (i) and (ii) required; (iii) rejected | 3 |
| A-3 | "Calibrated inference regime" has no quantitative definition (nominal? ceiling? at what scale? who certifies?) | Defined by demonstrated bounded null false-block rate at pre-declared grid points on the real estimator path; ceiling OPEN | 5 |
| A-4 | `F4b/F4c` not ratified leaves **no multiplicity treatment** across several declared confounders; `A7` single-`Z` checks then mean a union of blocks | Flagged as M4 / O-m; not resolved | 4.5, 8 |
| A-5 | `F4a-K` "extra knife-edge significance conjunct": literally the `p_Z` conjunct; but a rule without it has no null control (Section 4.5), which sits in tension with Decision 5's "low false-block rate under no confounding" | Read as the `p_Z` conjunct; `R0` omits it; its consequence is stated and predicted | 4.5, 10 |
| A-6 | What "the criteria" of the new test are, given `F11` says they are not `G03`/`G04` | `S = {sign, 95% interval excludes 0}` derived from the estimand; `MDE` and sample-size items moved to eligibility; flagged for the reviewer | 4.2 |
| A-7 | Is the acceptance bar to be applied to **mis-declaration** (M-bias declared confounder)? Decision 5 says "collider / M-bias -> must not be blocked" | Correct declaration -> deterministic pass; mis-declaration measured and reported; scoring = B-6 (founder) | 7.3, 8 |
| A-8 | `F5a/F5b` "WARN / fail-open consistent with the bounded contract": ratifies which `WARN` scope (freeze `F5a` (i) or (ii)) and is a power `WARN` in or out | Default in force: `WARN` only when no declared confounder assessed; no power `WARN`; not ratified | 6 |
| A-9 | "Real data or better causal machinery": what would count as either, and what happens to `TASK-105` closure, the engine freeze and `TASK-106/107` (both blocked on `TASK-105` closing) if `G17` is deferred | Not decided; listed as residual question RQ-2 | 11, 12 |
| A-10 | Whether the falsification must run on the real estimator path when the decision test and the paired bootstrap do not exist in code | The real estimator functions are used; the paired bootstrap is a validated scratch reference implementation (Section 10A); a replica only as validated bulk engine | 10A |
| A-11 | "Pre-declared acceptance bar" vs Decision 5's "low false-block rate" without numbers | No number chosen; Section 8 | 8 |

---

## 10. Registered predictions (before any run) and prior evidence

### 10.1 Prior read-only evidence used to form the predictions (not new runs)

`docs/analytics/task-105-evidence/rev3_block_sim.json` (Revision 1, committed `8a3e1af`; a numpy replica of the freeze's rule; 2,000 datasets per cell; only the point estimates are validated against the real code, the rest is a replica). Relevant numbers **for the deterministic
flip without a `p`-value (`flip_A`)** (unconditional): prognostic-neutral `Z`: 0.000-0.016 across `K = 5, 10, 50`, `m = 1, 3`, all `beta` locations; prognostic `Z` (`gamma = 300`): `K = 50`, `m = 1`: 0.122 / 0.1315 / 0.125 at `b_c2 / b_c3 / midpoint`; `m = 3`: 0.156 / 0.19 / 0.188; `K = 10`: 0.1175-0.202; `K = 5`: 0.1105-0.203; 6 SE from a boundary: <= 0.001. Confounded control: 1.000. M-bias
(`K = 50`): 0.8345 (`beta = 80`), 0.018 (`beta = 120`). These include the `MDE` criterion `R0` no longer has and are unconditional; both differences are stated in the predictions.

**Fidelity limits of that replica (stated, per the request).** (1) **The replica used a cluster-level bootstrap, not a row-level one**: `boot()` resamples clusters with a multinomial draw over per-(cluster, stratum, arm) cell sums, which is distributionally the same as `cluster_bootstrap_replicates`' `rng.choices(population, k=len(population))` over sorted cell sums (`apply.py:224-257`). The caller's premise that it was row-level is not borne out by the script.
(2) But the **cluster assignment was uniformly random and independent of everything** (`cl = rng.integers(0, K)`), i.e. ICC = 0 for outcome and exposure and equal expected cluster sizes; a cluster bootstrap over random groups behaves like a row bootstrap with `K` groups. Real customers create within-cluster dependence in `Y` and possibly in `X` and `Z`, unequal sizes, and empty strata inside replicates at small `K`.
(3) **Gaussian noise (sd 250)**: no heavy tails or skew; percentile intervals for a mean at `N = 2,462` are fairly insensitive to it but the *sparse-strata* and *few-cluster* tails are not. (4) `pooled_sd`, the percentile/criteria layer and the sample-adequacy test are replica code, not the real modules; the real percentile widening rule (`apply.py:587-591`) and the real `bootstrap_standard_error` were not in the loop for the block decisions.
(5) One `Z` structure (3 levels, uniform, independent of everything else in the null cells). **Therefore the real estimator path (`_stratified_adjustment`, `cluster_cells`, the real interval construction) must supply every decision in the anchor cells; the vectorised engine is admissible only as a bulk engine validated against it** (Section 10A).

### 10.2 Predictions for `R0` (registered now; approximate, from the prior evidence and hand arithmetic; a prediction is never edited after a result)

| ID | Prediction | Falsifier |
|---|---|---|
| **PB-1** | C6 and C2-a, C3-a, C3-b: 100% expected state/reason, zero blocks, no `PASS`, and the states are invariant to permuting the outcome | any deviation = implementation defect |
| **PB-2** | **C4, `gamma = 0`, Gaussian, ICC 0, `K >= 50`**: conditional false-block rate **`<= 0.03`** at every `beta` (unconditional flip 0.000-0.016 in the replica; the conditional denominator is at most ~2x smaller at `b_50`) | `> 0.03` at any such cell |
| **PB-3** | **C4, `gamma = 300`, Gaussian, ICC 0, `K = 50`, `m = 1`**: worst-case over the `beta` grid in **[0.10, 0.35]** (replica 0.12-0.13 unconditional at the boundary locations; crude confirmed ~0.5-0.8 there, so conditional ~0.16-0.30); at `b_far` ~0. **Hence: `R0` fails a `C_null <= 0.05` and probably `<= 0.10` in this cell** | worst-case `< 0.06` (then the rule has more null control than the replica implied) |
| **PB-4** | C4 with `m = 3` (prognostic): worst-case **above** the `m = 1` value at the same `K`, in [0.15, 0.40] | `m = 3` not above `m = 1` |
| **PB-5** | C4 few clusters: `K = 5, 10` worst-case with `gamma = 300` at least as large as `K = 50` and in [0.10, 0.40]; `gamma = 0` `<= 0.05` | `K = 5/10` lower than `K = 50` by more than 2 MC SE |
| **PB-6** | Fidelity (low confidence): `t3` noise and outcome ICC 0.2 raise the worst-case false-block rate by a factor in [0.8, 2.0] relative to the Gaussian anchor; cluster-level exposure assignment and log-normal cluster sizes raise it by a factor in [1.0, 3.0] | a factor `< 0.8` or `> 3.0` |
| **PB-7** | **C1 power** (complete removal, conditional on crude confirmed): `>= 0.90` at crude `>= 4 SE_c` and `K >= 500`; `>= 0.85` at crude `2.5 SE_c`; `L = 7` lower than `L = 3` by `<= 0.10`; **the silent share (crude not confirmed)** at `2.5 SE_c` in [0.20, 0.45] | power `< 0.80` at crude `>= 4 SE_c`, `K >= 500` |
| **PB-8** | **C1 real fixtures `T01`, `T05`** at delivered scale: conditional power **below 0.80** for at least one of the two (design 10.1: c80 = 58-111 EUR against effect sizes for which `0.5 H_raw - c80 < 0` on all four exposures); wide (`D = 200`) | both `>= 0.80` |
| **PB-9** | **C2-b** (mis-declared M-bias, `K = 50`, conditional on crude confirmed): `beta = 80` in [0.70, 0.95] (replica 0.8345); `beta = 120` `<= 0.10` (replica 0.018) | outside the ranges |
| **PB-10** | **C3-c** full mediation declared confounder: conditional block **`>= 0.90`**; partial mediation lower and monotone in the mediated share | `< 0.70` |
| **PB-11** | **C5 suppression and partial confounding, `K >= 50`**: conditional block rate `<= 0.02` (no magnitude criterion; adjusted estimate stronger or well above the boundary); `K = 5-10`: `<= 0.05` | `> 0.02` at `K >= 50` |
| **PB-12** | Structure: every block has `Confirmed(matched crude)` and `not Confirmed(adjusted)` in the recorded fields; the credited-block count `<=` the count of datasets in which matched crude is confirmed and A-1 holds | any violation |
| **PB-13** | **Overall expectation (registered, not a recommendation):** with any `C_null <= 0.10`, `R0` fails in the prognostic-`Z` cells at every `K` in the grid; the result would then be "no calibrated regime for `R0`", i.e. Section 11 (D-1) | `R0` passes `C_null = 0.10` at `K >= 500` in prognostic cells |

### 10.3 Harness-validation criteria (fixed now; they concern the harness, not the contract)

* The point estimates `H_c`, `H_Z`, coverage and usable strata equal the real `_stratified_adjustment` output to `1e-9` on **every** real-path dataset and to `1e-6` on a random 1% of the vectorised datasets (`rev3_validate_estimator.py` is the precedent).
* For the anchor cells, the vectorised bulk engine and the real-path engine run on **identical datasets**; the block rates must agree within `2 sqrt(SE_real^2 + SE_vec^2)` per anchor cell and the median absolute difference of the 95% lower bounds (real vs vectorised) must be `<= 0.10 x` the median bootstrap SE. Failure => vectorised results are not scored; only real-path cells (with their wider MC bounds) are, and the plan's power to certify low ceilings is reported as lost. These two tolerances are harness-validation numbers, not contract constants.
* Invariants per dataset: `block => Confirmed(H_c) and not Confirmed(H_Z)`; `not assessed => no bootstrap run`; the `(0.0, 0.0)` sentinel never produces a state other than `not_assessable`.

---

## 10A. The estimator path and the fidelity limits (why the earlier replica is not enough)

(Belongs with Part B; referenced from Sections 5.1, 7.1, 10.1, 10.3.)

**What must be real.** `_stratified_adjustment(frame, mask, outcome, (Z,))` (`apply.py:337-381`), `cluster_cells` (`apply.py:195-221`), the sorted-key `population` and `rng.choices` resampling of `cluster_bootstrap_replicates` (`apply.py:224-257`), `percentile_ci` and the widening rule (`apply.py:587-591`), `MIN_STRATUM_CELL`, the coverage rule, the real `split_stats` for harm orientation, `classify_evidence_level`/`assign_policy_readiness` for A-1. A replica is **not** accepted as the scored engine for the anchor cells.

**What does not exist in code and therefore cannot be "the real path".** The **paired** cluster bootstrap for the crude and the adjusted estimate on the same resample, the matched-crude estimate on usable strata, and the `DCAL-V` decision itself. `cluster_bootstrap_replicates` returns only the unpaired exposed-minus-comparison mean. The harness therefore contains a **scratch reference implementation** of these (in `docs/analytics/task-105-evidence/`, not in the package),
built from the real functions above with the same per-cluster cell-sum structure extended to per-stratum, and validated by (i) point-estimate equality (Section 10.3), (ii) for the case in which every stratum is usable, exact equality of its crude replicate list with the real `cluster_bootstrap_replicates` output under the same seed and population order. This is the closest to "the real path" that is available before code exists; it must
be disclosed as a reference implementation in every result, and the eventual code (if any) must be shown equal to it (`U2`-style test) before being trusted.

**Cost.** A pure-Python bootstrap of `B = 2,000` over `~2,000` clusters with several strata is minutes per dataset; hence real-path anchors are `D = 200` per anchor cell (Section 7.4) and the bulk uses a vectorised engine validated on identical datasets. The actual cost is to be measured in a timing-only dry run that prints no decision quantity.

**Remaining fidelity limits even with the real estimator** (stated so a result is read correctly): the DGPs are invented; `Z` structures are small categorical; the empirical-residual cell borrows only the marginal outcome shape from the delivered dataset; real exposure/strata/cluster dependence beyond the listed factors is not modelled; the validation-split sign selection (`G10` conditioning, freeze 1.2) is **not** reproduced — the conditioning "crude confirmed" is imposed only in the metric
(the denominator), not in the DGP — so the selection-induced upward bias of a promoted candidate's crude estimate is **not** modelled; this is a disclosed limitation of every false-block number here. Its effect on the conditional false-block rate (through where promoted candidates sit relative to the confirmation boundary) is unknown; it is neither resolved nor corrected.

---

## 11. What result means "defer `G17` until real data / better causal machinery"

`G17` is **deferred** (no freeze review, no code; the recorded state is "NOT ASSESSED for all `k = 1` candidates; crude / matched crude / adjusted may be reported as descriptive, not gated") if any of the following holds on the pre-set bar (the bar values are Section 8; the *logic* is fixed now):

| # | Result | Meaning |
|---|---|---|
| D-1 | no `K_min` exists (Section 5.4 rule): for every grid point the C4 or fidelity cells exceed `C_null`, including the delivered row-level scale | The decision rule has no calibrated regime; a rule with a null reference (needs M1-M5) or a different estimator is required — "better causal machinery" |
| D-2 | the ceiling holds only for Gaussian / ICC-0 cells and fails in scoped fidelity cells at the delivered scale (B-7 (i)/(ii)) | The regime cannot be characterised by cluster count alone or is not robust to realistic noise; defer until structure/noise is characterised on real data |
| D-3 | power below `P_min` at the delivered-scale cells required by B-3 (incl. the `T01`/`T05` real-generator cells) | The bounded capability claim (Section 1.4) cannot be delivered at the size the product will see; a blocking claim would be empty — `S-E` analogue |
| D-4 | suppression / partial-confounding block rate above `C_supp` at any in-regime cell | Direct violation of `ADR-101` A9; mechanism unsafe |
| D-5 | the harness-validation criteria (Section 10.3) fail and cannot be repaired without changing the rule | Cannot falsify the final contract with the real estimator; do not fall back to the replica |
| D-6 | the founder scores mis-declaration (B-6 (c)) | Deferral by identifiability, independent of any run |
| D-7 | any deterministic control (C2-a, C3-a/b, C6) fails | Not a statistical result: implementation-design defect in the specification; fix the specification and re-register |

Pass (all scored controls meet the bar, a `K_min` exists, and the regime table is committed): independent freeze review, then code, as `ADR-104` Decision 5 states. **Partial** (pass only at large `K`, e.g. R-1a): `G17` may block only in that regime; everything else NOT ASSESSED; this is a narrower claim, not a failure. Deferral does not withdraw `ADR-102`'s other
decisions, and does not by itself close `TASK-105`, unblock `TASK-106`/`TASK-107`, or change `D2` Part B (2/5); those are the founder's (RQ-2).

**"Better causal machinery"** (named neutrally, not designed here): a rule with a null-referenced evidence requirement whose reference distribution is calibrated at the stated cluster counts; a small-cluster inference method separately calibrated; a declared causal graph from which the adjustment set is derived (rather than single `Z` checks); sensitivity analyses that do not rest on a chosen `Z`; joint adjustment with sparse-strata handling.
"Real data": customer datasets on which `G17` naturally activates, with declarations from the owners, so noise, clustering, and cluster-count structure are observed rather than assumed.

---

## 12. Residual founder questions (neutral; none answered here)

* **RQ-1 (= Q-0).** Score `R0` as written / supply the M1-M5 rationale first / defer now.
* **RQ-2.** If `G17` is deferred: does `TASK-105` close (with the categorical `G17` recorded as deferred), does the engine freeze that `ADR-103` conditions `TASK-106`/`TASK-107` on proceed with the engine as-is (`G17` absent, `k = 1` NOT ASSESSED), and what wording carries the limitation (`ADR-100` invariant (b) is not delivered)?
* **RQ-3.** The acceptance bar items B-1 ... B-9, O-m, D-K, R-1 (Section 8), decided in a dated record before any run.
* **RQ-4.** Who signs a real-dataset declaration and whether an independent second drafting is required (freeze `F6`); whether a declaration is mandatory for a claim of `G17` coverage.
* **RQ-5.** `F5a`/`F5b`: which limitations produce `WARN`, and whether a power `WARN` exists (Section 6, A-8).
* **RQ-6.** Whether the estimand statement of Section 4.2 (ATT via exposed weights; crude minus adjusted = bias attributable to `Z`) is the intended reading of "adjusted result", and whether ATE weights (not currently in code) are wanted.
* **RQ-7.** Whether `S = {sign, 95% interval excludes 0}` is acceptable as the new test's criterion set or the founder wants `MDE`, materiality (`F3a`) or stability (`F3b`) inside `DCAL-V`.
* **RQ-8.** Whether `future_holdout` may ever be used as a second evaluation split (only if `F1` is reopened; not proposed).
* **RQ-9.** The empirical-residual fidelity cell needs the gitignored delivered frame; authorization to read it for that purpose.

---

## 13. Compatibility and scope statement

Nothing in this document changes any gate, threshold or contract constant. No numeric constant is added by this document; the regime's minimum cluster count and the falsification ceilings are **open**. The freeze's statements of "no new constant" (Sections 0, 7.i, 12, U12, `S-H`) are superseded in one respect: a regime boundary derived from a committed study is a new versioned constant if `G17` is ever implemented.
Predictions and scripts for Part B will be committed unrun; results (if any run is authorised by the bar decision) are appended, not edited in. This document contains no run output.
