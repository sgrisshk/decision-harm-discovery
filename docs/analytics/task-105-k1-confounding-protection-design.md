# TASK-105 Phase 2a — Single-condition (`k=1`) confounding protection: design document

**Owner:** STATISTICS (lead), ARCHITECT (support). **Recorded:** 2026-09-24. **Status:** DESIGN ONLY. Nothing in
`engine.py`, any gate, `apply.py`, `contract.py`, `grading.py`, `input_contract.py`, the generator, the catalogue, or any
threshold was changed. No mechanism code exists. Every "prediction" below is registered **before any mechanism run
exists** (there is nothing to run yet); it is frozen by the commit of this file and is not to be edited after a result is
seen (a change after seeing a result is a new, dated design version, never an edit).

**Binding text:** `ADR-101` (A1-A9, catalogue/generator policy, Phase 2 contract) and `ADR-100` (decisions 1-5), both read
in full. Context: `docs/benchmark/task-105-single-condition-confounding-threat-model.md` (Phase 1: spec, manifests, C3/C4),
`docs/benchmark/task-104-trap-fixture-results.md`, `validation/apply.py` (`_stratified_adjustment`,
`_select_adjustment_columns`, `_adjustment_pool`, G06/G09/G11/G12/G16 blocks, `run_validation`), `validation/contract.py`,
`validation/composition_safety.py`, `validation/grading.py`, `validation/input_contract.py`, `discovery/engine.py`
(`discover_candidates`, `_temporal_consistency`, `_prepare`), and the project precedents `TASK-070`/`ADR-064`,
`ADR-015`, `TASK-080`/`TASK-081`/`ADR-078` (`G16`), `TASK-095` (design -> review -> implement).

---

## 0. Summary (what is proposed, in twelve lines)

1. A new gate **`G17_SINGLE_CONDITION_CONFOUNDING`**, sibling of `G16`, in a new module (dependency-injected like
   `composition_safety.py`), vacuous for `k >= 2` (`G16`'s domain is untouched).
2. For a `k=1` candidate, the pool is `A(C)` = columns in a **declared pre-exposure order** strictly *earlier* than the
   exposure column, minus the exposure column, intersected with the existing `adjustment_eligible` / `DECISION_TIME`
   pool. The declaration is a dataset-owner artifact made before any candidate exists. **Undeclared => empty pool =>
   no adjustment is attempted and a WARN limitation is recorded; never a block.**
3. Each `Z in A(C)` is one **single-`Z`** stratified adjustment (`m = |A(C)|` checks; no subsets), reusing the real
   `_stratified_adjustment` unchanged.
4. Evaluation is on the **`validation` split** (not the search split), with bin edges fixed on `development`; `Z`-pool
   specification uses no data at all. Independence from candidate selection is **partial, not complete** (Section 2.5):
   `discover_candidates` uses the *sign* of the later-split raw effect in its stability credit, and `G10` conditions
   promotion on it. No fully independent split exists in the repo.
5. A `Z` is "positive evidence of confounding" iff the `Z`-adjusted validation-split estimate **violates G06's own
   executed criteria** (sign, attenuation `> 0.50`, E-value `< 1.50`) **and the violation is statistically established**;
   the raw estimate on the same rows is the baseline (attribution to adjustment, not to noise or drift).
6. One multiplicity family per candidate = its `m` single-`Z` checks (x2 contract sub-criteria); **Bonferroni FWER
   `alpha = 0.10`**. Chosen because the decision is "block if any", it is valid under arbitrary dependence between `Z`s, and
   it is auditable; the power cost is quantified (Section 2.4).
7. Block only on established violation; every other state (not assessable, coverage, no declaration, declared-but-
   unobservable confounder) is `WARN` with the limitation recorded in the gate detail, `report.warnings`, diagnostics and
   the run manifest. **No fixed percentage; no veto for incomplete coverage.**
8. Two-sided by construction: the tested null is "the adjusted result still satisfies the contract"; a `Z` whose
   adjustment *strengthens* the association makes the violation statistic strongly positive and cannot block (T02
   suppression test).
9. Attribution: recorded `counterfactual_readiness` with `G17` forced to pass; credit only if that readiness is
   `>= SHADOW_POLICY` and `G17` FAILED. Distinct gate id / reason code from `G12` and `G16`.
10. Contract version **1.3.0 -> 1.4.0** with an executable prior semantics (`NONE_V0`) and a mapping test, following
    `ADR-064`'s "strengthened `ADR-015`" precedent (not `G16`'s no-bump precedent, Section 3.4).
11. **Headline finding (not a footnote): with single-`Z` checks and the contract's existing 0.50 attenuation ceiling,
    the mechanism is a *majority-single-confounder* detector.** A `Z` that carries `s` of the confounding removes about `s`
    of the bias, so it can only violate the ceiling when `s > 0.5`. Diffuse confounding (T05 as catalogued and generated:
    four equally weighted indicators, `s = 0.25` each) **will not be blocked**, so `T05`-as-catalogued and the
    equal-weight `T01` fixture are **predicted to stay at `SHADOW_POLICY`** (Section 4, P4). That is a direct consequence of
    `ADR-101`'s A7 (single-`Z` only, no subsets) combined with A4 (same contract); it is the "proven case" A7 says would
    justify a joint-`Z` hypothesis. It is reported, not hidden, and put to the founder (Q4).
12. Real-data power is low at the delivered sample size (Section 2.4): the mechanism would not detect the
    real-generator confounding-induced shifts (roughly 28-54 EUR for T01/T04/T05). The design's honest claim is bounded accordingly.

---

## 1. Authoritative threat specification per trap, and disposition (requirement 1)

Policy applied (`ADR-101`): define the authoritative spec first; then (a) catalogue misdescribes intent -> fix catalogue;
(b) catalogue right, generator does not realize it -> fix generator = **new versioned benchmark**; (c) intentional -> keep
both, record *specified != generated*. Below, `realized` = measured by Phase 1 on the real `_generate_row` (400k rows;
generator reproduces the delivered CSV with 0 mismatching rows). No generator change is proposed here. No `TASK-104`
fixture needs one (they rewrite `X` and `Y` test-side).

The authoritative record is the Phase 1 manifest `docs/benchmark/task-105-trap-manifests.json`; Phase 2 extends it with a
per-trap `disposition`, a `negative_controls` list, and `specified_not_realized`. Frozen delivered artifacts
(`hidden_ground_truth.json`, `synthetic_data/**`) are **not** rewritten (a rewrite changes a restricted, checksummed
artifact for no functional gain); the catalogue text in `synthetic_benchmark.py` (used by future regenerations) and the
manifest file are the two places corrected.

| Trap | Exposure | Authoritative threat spec (class per `ADR-100`) | Catalogue as is | Disposition | Proposed catalogue-only correction |
|---|---|---|---|---|---|
| **T01** | `manager = Manager 2` | Class (i) observable, common causes **`destination`** (`in {Tokyo, Zanzibar}`) and **`booking_lead_days`** (`< 14`), acting through the OR `destination_hit OR lead<14` on the manager draw. `party_size`, `trip_duration_days` are **not** causes of exposure; they are outcome-associated (Y-side Wald 961 / 499) => **negative controls** | 4 listed | **fix catalogue** | `confounded_by = [destination, booking_lead_days]`; add `negative_controls = [party_size, trip_duration_days]` (kept, they are useful: a correct mechanism must not block on them) |
| **T02** | `supplier = Atlas` | Class (i): **`trip_duration_days`** (`>= 14`) dominant; `destination = Tokyo` weakly *dilutes* Atlas (raises BlueWing weight). `booking_month` is **specified but not realized** (Wald 10.1 < 31.3) => class (ii) *content is absent from the data*, not merely unavailable | `trip_duration_days`, `booking_month` | **fix catalogue for the realized part; keep `booking_month` as `specified != generated`** (intent for a seasonal trap is plausible, so this is not silently dropped) | `confounded_by = [trip_duration_days, destination]`; add `specified_not_realized = [booking_month]` with note "would exercise class (ii); requires a new benchmark version" |
| **T03** | `acquisition_channel = paid_search` | **No common-cause confounding realized.** `discount_rate` is a *child* of the exposure (mediator); `customer_type`/`installments` do not affect it. Outside the class-(i) obligation set; `ADR-101`: a mediator is **not** reclassified as a confounder | `customer_type`, `discount_rate`, `installments` | **fix catalogue** (it currently *calls a mediator a confounder*) | `confounded_by = []`; add `mediated_by = [discount_rate]`; `customer_type`/`installments` -> `specified_not_realized`. `T03` keeps its role as a **mediator guard** in the tests (Section 4) |
| **T04** | `payment_method = bank_transfer` | Class (i): **`booking_lead_days`** (`< 14`) single common cause. `destination` is not a cause of exposure => negative control | `booking_lead_days`, `destination` | **fix catalogue** | `confounded_by = [booking_lead_days]`; `negative_controls = [destination]` |
| **T05** | `manual_exception = true` | Class (i): four equally weighted indicators (`destination in {Tokyo,Zanzibar}`, `lead<14`, `party>=5`, `duration>=14`), `P(exc) = 0.025 + 0.055 * complexity` | 4 listed | **no change** (catalogue = generator, measured) | none |

Why "fix catalogue" and not "fix generator" for `T01`/`T04`: the generator is what produced every existing result (`2/7`,
ceiling analyses, `TASK-103`); changing it versions the benchmark and forbids comparison with earlier results
(`ADR-101`). There is no evidence the four-confounder `T01` intent was more than a catalogue over-listing, so correcting
the description is the smaller and reversible act. **This is flagged for the founder (Q8)** because for `T02` the
`booking_month` intent may be real; if so the alternative is a *new benchmark version* (`v1.1.0`) that realizes it, which
is a founder decision and is not proposed as a Phase 2 action.

Test consequence (2b work, listed here so the reviewer can see it): the 12 strict-xfail tests of Phase 1 flip as
described in Phase 1 §Tests; the per-confounder `intended_not_implemented` xfails assert against generator measurements
and therefore stay xfail unless converted to `specified_not_realized` expectations. The conversion is part of applying the
corrections and must not weaken any measurement assertion.

---

## 2. The mechanism (requirement 2), honoring `ADR-101` clause by clause

### 2.1 Scope (`A1`)

`G17` computes only when `len(conditions) == 1`. For `k >= 2` the gate is `PASS` with reason
`not_applicable_k_ge_2` (exactly parallel to `G16`'s `not_applicable_single_atom`); compound rules stay under `G16`.
"Promotion path" is defined operationally: a `k=1` candidate whose readiness *would be* `>= SHADOW_POLICY` with `G17`
forced to pass (this is also the attribution counterfactual, 2.7). `G17` is computed for **every** `k=1` candidate (cheap;
gives information even where another gate already caps), but is *credited* only on the promotion path.

### 2.2 The pre-declared adjustment pool (`A2`, `A7`), where it comes from

`A(C)` is a function of exactly two things: the dataset's declaration and the candidate's exposure column. **No outcome,
no candidate effect, no data value enters it** (property test, Section 4.2 U1: permuting rows / replacing outcomes leaves
the pool byte-identical).

Existing repo sources, used as the *outer* bound (unchanged):

| Rule | Source | Status |
|---|---|---|
| R1 `DECISION_TIME` | `feature_timing` roles -> `ValidationInput.decision_time_features` | existing |
| R2 `adjustment_eligible` | `manifest["validation_roles"]["adjustment_eligible"]` -> `ValidationInput.adjustment_features` (already fail-closed: must be `DECISION_TIME`) | existing |
| R3 not the candidate's own condition column | `_adjustment_pool` (`eligible - condition_features`) | existing |
| **R5 declared causal order** | **new, see below** | **new input** |

R1-R4 are necessary but not sufficient (Phase 1 A2: a single `DECISION_TIME` bucket cannot exclude descendants or
colliders of a given `X`; measured counter-example `T03`/`discount_rate`). **R5 is the only new information.**

**Declaration (who, what, when, default).**

- *What:* an ordered list of tiers, each a list of column names: `pre_exposure_order = [[tier0...], [tier1...], ...]`.
  Semantics: every column in tier `i` is determined **before, and cannot be a consequence of, any column in a tier `> i`.**
  Columns in the same tier are **not ordered** relative to each other. Columns not listed are unordered.
- *Rule:* for exposure column `x` in tier `t(x)`: `A(C) = { z in R1 ∩ R2 : t(z) defined, t(x) defined, t(z) < t(x) }` (strictly
  earlier). Same-tier columns are **excluded** (we cannot rule out that one is a descendant of the other); so are
  unlisted columns. Strict precedence rules out descendants of `X` and colliders **of `X`** (a collider needs `X -> Z`).
  It does **not** rule out M-bias through a pre-exposure `Z` that is a collider of two *unmeasured* causes; that is class
  (iii), stated as a limitation, not claimed away.
- *Who:* the dataset owner at onboarding, i.e. the same role and step that already declares `heterogeneity_column`,
  `seasonality_column`, `robustness_group_column` (`TASK-066`, "domain-aware gate inputs"): Data Engineer produces the
  manifest, STATISTICS reviews the roles, the **customer/founder signs the ordering** for a real customer. It is declared
  **before any candidate exists** and hashed into the run manifest; it may not be edited after a validation run starts.
- *Where it lives:* (A, canonical) `validation_roles` version `1.1.0` adds `pre_exposure_order`; the loader accepts
  `1.0.0` (=> no declaration) and `1.1.0`, fail-closed (every listed column must be `DECISION_TIME` and in
  `adjustment_eligible`; no column in two tiers). (B, for the already-frozen `travel-bookings-analytical-v1.1.0`, which
  should not be re-issued because a new dataset version changes its identity) a sidecar declaration file whose sha256 is
  recorded in the run manifest and passed explicitly to `run_validation`. Q3 asks the founder to choose; recommendation:
  A as the general contract, B for the frozen benchmark.
- **Safe conservative default: no declaration => `A(C) = {}` => no adjustment check is run => `G17` is `WARN` with reason
  `no_declared_causal_order` and the limitation is recorded.** It never blocks (`A3`) and never silently passes as if
  checked.

**Proposed declaration for `travel-bookings-analytical-v1.1.0`** (for founder approval, Q3; derived from the manifest's
`semantic_meaning` strings and business logic, **not** from `hidden_ground_truth.json`; frozen by this document *before*
any mechanism run; and I disclose that I read the generator source in Phase 1, so a soundness test — 4.2 U13 —
independently checks the declaration against the generator's own data flow, without the mechanism ever reading the
generator):

| Tier | Columns | Rationale (semantic_meaning) |
|---|---|---|
| 0 | `acquisition_channel`, `customer_segment`, `customer_type`, `destination`, `party_size`, `trip_duration_days`, `booking_lead_days` | customer / trip request attributes and source, fixed by the customer before any seller action |
| 1 | `manager`, `supplier`, `product_category` | seller-side allocation of the booking |
| 2 | `quoted_cost_eur`, `customer_price_eur`, `discount_rate`, `payment_method`, `installments`, `manual_exception` | commercial terms set at approval; may respond to tiers 0-1 |
| unlisted | `booking_date`, `travel_date`, `travel_month` | already excluded from adjustment by `analytical_dataset.py` (handled by `G09`/`G11`) |

Resulting pools (`m`): `T01` (`manager`, tier 1): 7 (`{acquisition_channel, customer_segment, customer_type, destination,
party_size, trip_duration_days, booking_lead_days}`); `T02` (`supplier`): the same 7; `T04` (`payment_method`, tier 2): 10
(tier 0 + `manager`, `supplier`, `product_category`); `T05` (`manual_exception`, tier 2): 10; `T03` (`acquisition_channel`,
tier 0): **0** => `WARN no_admissible_z`. `T03`'s mediator `discount_rate` (tier 2) can never enter `T03`'s pool: the
mediator exclusion is a property of the declaration, not a special case. The declaration is an *assumption* (e.g.
"`customer_type` is not a consequence of `acquisition_channel`" is not testable from the data); it is exactly the
assumption `ADR-100`'s "causally admissible" requires someone to make explicitly. The tier boundaries are judgments; the
`destination`/`lead` position (tier 0, before `manager`) is what makes `T01` assessable.

### 2.3 Single-`Z` adjustments only (`A7`)

For each `Z in A(C)`: exactly one call to the real, unchanged `apply._stratified_adjustment(frame, mask, outcome, (Z,))`
on the **validation-split** frame. `m` admissible `Z` = `m` calls; no pair, no subset, no greedy set (a spy test asserts
every call has one column and that the call count equals `m`; a subset-search mutant must fail it, 4.4 K3).

*Stratification of `Z` (a design parameter, fixed now, not tuned):* categorical/boolean `Z` and numeric `Z` with `<= 12`
distinct development values (the engine's own `max_categorical_levels`) use raw levels; other numeric `Z` use development-
split deciles. Bin **edges are computed on the `development` split only** and applied to the validation rows (the
adjustment specification is therefore not fitted on the evaluation data, `A8`). This intentionally differs from `G06`'s
joint binning (raw only `<= 6`, quartiles) because a single-`Z` stratification has no joint-coverage constraint, so a finer
resolution is affordable; the difference and its cost are disclosed: at deciles a numeric threshold indicator still sits
inside a bin. Measured on the delivered development split: `booking_lead_days` decile edges `[4, 23, 35, ...]` put the
generator's `lead < 14` cut inside bin `[4, 23)` (I estimate the between-bin explained share of that indicator at ~0.79);
`party_size` (7 levels) is used raw so `party >= 5` is exactly resolved; `trip_duration_days` edges `[2,4,5,...,10,12]`
leave `>= 14` inside the top bin. **Predicted effect: attenuation from a fully-confounding numeric `Z` is understated by
its resolution factor (~0.6-0.9), which lowers power, not specificity.** A quartile (`G06`-binning) variant is reported as
a **non-binding sensitivity**.

Coverage per `Z` uses the existing `MIN_STRATUM_CELL = 5` and the existing threshold `min_confounder_stratum_coverage`
(0.50): a `Z` whose usable-stratum coverage is below it is `not_assessable(coverage)`; this is a *limitation*, never a
block (`A3`).

### 2.4 The multiplicity family and its control (`A7`), justified at these sample sizes

*Estimand per `Z`.* On the evaluation rows `L` (validation split), with orientation such that harm is positive
(`outcome.harm_multiplier`): `H_raw` = raw harm (existing `split_stats`), `H_Z` = `Z`-adjusted harm, `pooled_sd` = existing.

*The two hypotheses per `Z`,* each the negation of a G06 criterion applied to the adjusted estimate (Section 2.6):

- `H0_att,Z : H_Z >= (1 - max_adjusted_attenuation) * H_raw` (sign preserved and attenuation `<= 0.50`). One-sided statistic
  `D_att = H_Z - 0.5 * H_raw`, `p_att = Phi(D_att / SE_att)`.
- `H0_E,Z : H_Z >= h_E`, where `h_E` is the adjusted harm at which `e_value(., pooled_sd) = min_e_value` (closed form:
  `RR* = E^2/(2E-1) = 1.125`, `h_E = pooled_sd * ln(RR*)/0.91 ~ 0.129 * pooled_sd`). Evaluated **only if the raw baseline on
  `L` itself has `e_value >= min_e_value`** (otherwise a low E-value is not attributable to adjustment; that is `G10`/`G04`
  territory), `p_E = Phi((H_Z - h_E)/SE_E)`.
- `p_Z = min(1, 2 * min(p_att, p_E))` (Bonferroni over the two contract sub-criteria; `p_Z = min(1, 2*p_att)` if the E test
  is not applicable).

*Standard errors.* Paired **cluster bootstrap** of the same replicate for `H_raw` and `H_Z` (so `D` is a paired
difference), clustering on the manifest's clustering column (`customer_id` here; ~2.8k customers in the later splits, so
close to row-level), `B = DEV_BOOTSTRAP_REPS = 2000`, population sorted by key (`HANDOFF-047`), normal approximation on the
bootstrap SE exactly as `G05` (`bootstrap_standard_error`, Wald `Phi`; not the empirical tail count, `ADR-014`). The RNG
stream is **isolated** (seeded from `BOOTSTRAP_SEED` and the candidate id) so no existing gate's random draws shift. Cell
sums per (cluster, `Z`-stratum, arm) let a replicate avoid re-scanning the frame (there is no numpy dependency; expected
cost is seconds per `k=1` candidate, and `k=1` candidates are rare today). A candidate with fewer than 90% valid replicates
is `not_assessable(bootstrap_degenerate)`.

*The family and the control.* **Family = the `m` single-`Z` checks of one candidate** (`m = |A(C)|`, fixed by the
declaration before evaluation, *including* `Z`s that later prove not assessable, so `m` cannot depend on the data).
**Control = Bonferroni FWER at `alpha_k1 = 0.10`:** block iff `min_Z p_Z <= alpha_k1 / m`. New named threshold
`k1_confounding_fwer_alpha = 0.10` in `ValidationThresholds` (a contract-versioned change, 3.4).

Justification (why this and not the alternatives):

- The decision is one bit per candidate, "block if any `Z` is established". The relevant error is a *false block of a
  genuine effect* (a recall cost), whose family-wise rate must be bounded per candidate. Bonferroni bounds it at `alpha`
  under **arbitrary dependence** between the `Z` checks (the `Z`s are correlated), with no assumption to defend.
- Holm gives the same "any" decision (its first step *is* Bonferroni) and adds only a list of established `Z`s; the full
  `p_Z` table is reported anyway.
- BH/FDR is the wrong question here (`G05` already uses it across the *search*; a false-discovery *proportion among
  `Z`s* is not what a block decision needs). `G05`'s family and p-values are not altered.
- A cross-candidate family is rejected: a candidate's block would then depend on how many other `k=1` candidates the run
  contains (order/size dependence). Per candidate, expected false blocks across a run are `<= alpha_k1 * N_k1`, stated.
- `alpha_k1 = 0.10` equals the contract's existing `fdr_alpha` (a value the project already accepts as its error budget);
  this is a choice, flagged (Q6), with a **non-binding** sensitivity at `0.05` and `0.20`.

Power cost at these sample sizes (computed from the delivered data, `sd(contribution_margin) ~ 776` on validation;
`validation` = 2,462 rows; `future_holdout` = 2,539; `development` = 4,999). `SE_raw = sd * sqrt(1/n_e + 1/n_c)`;
because `H_Z` and `H_raw` are highly correlated on the same rows, `SE(D) ~ 0.55-0.70 * SE_raw` (assumed range, to be
*measured* in 2b, not asserted). Critical `z` for `p_att <= alpha_k1/(2m)`: `m = 7 -> 2.45`, `m = 10 -> 2.58`, `m = 15 -> 2.71`
(uncorrected one-sided 0.10 would be 1.28).

| Trap exposure | `n_e` validation | `n_e` later splits pooled | `SE_raw` validation | approx. minimum violation `D` detectable, `m=10` (validation) |
|---|---:|---:|---:|---:|
| T01 `manager=Manager 2` | 667 | 1,336 | ~35 EUR | ~ -55 EUR |
| T02 `supplier=Atlas` | 634 | 1,273 | ~36 EUR | ~ -56 EUR |
| T03 `paid_search` | 679 | 1,391 | ~35 EUR | (pool empty) |
| T04 `bank_transfer` | 793 | 1,584 | ~34 EUR | ~ -52 EUR |
| T05 `manual_exception` | 191 | 350 | ~59 EUR | ~ -90 EUR |

Reading: `D = H_Z - 0.5*H_raw`, so blocking a candidate with `H_raw = 200 EUR` at `T01` scale requires `H_Z <~ 45 EUR`
(a `Z` that explains ~78% of the effect); for `T05` scale, `H_Z <~ 10 EUR`. **Consequence stated up front:** the real-
generator confounding shifts measured in Phase 1 B3 (catalogue-explained parts `-39`, `-28`, `-54` EUR against
`SE_raw` 25-60 EUR) are *below* this detection floor, so the mechanism is predicted to block none of the real-data
single-atom trap candidates at the delivered size (P2). That is a statement about power, not about safety; the report
language (2.8) must not imply the candidate was cleared beyond "no established confounding by the checked `Z`s".

### 2.5 Independent evaluation evidence (`A8`), determined from the code

What I read, and what it implies:

- `discover_candidates` searches on `split_label == "development"` only (atoms, beam, `_development_score`).
- **But** `_prepare` calls `_temporal_consistency(frame, rule, outcome)` on the *full* frame and feeds
  `effective_score = raw_score * (1 + stability_credit_weight * consistency)` into top-K selection
  (`stability_credit_weight = 0.5`, accepted default, "empirically null" per `ADR-039` but not zero). `consistency` is the
  share of later splits (validation, future_holdout) whose raw harm direction agrees with development. So **the *sign* of
  the raw effect in both later splits influences which candidates are selected.** Neither split is untouched by selection.
- `G06` (existing) is evaluated on the **development** split, i.e. on the very rows the candidate was searched on, so
  existing `G06` is *not* independent of selection. (`G05` corrects for search size; `G06` does not need to be
  re-litigated here.)
- `G10` requires same sign on all three splits and holdout retention `>= 0.5`; a candidate on the promotion path has
  therefore already passed a raw-effect condition on the later splits.
- The `Z`-pool specification uses no data (2.2); bin edges use development `Z` values only (2.3).

Determination: **the `validation` split is the closest thing to independent evidence the repo has, and it is only
*partially* independent of candidate selection.** What leaked into selection: one bit per later split (raw harm sign) via a
score multiplier `<= 1.5`. What did **not**: the size of any effect, any `Z`, any adjusted estimate, this mechanism. The
direction of the residual bias: selection/conditioning on a sign-consistent, retained raw effect inflates `H_raw` on the
later split, and `H_Z` shares that noise (same rows), so `D = H_Z - 0.5*H_raw` is inflated as well: **the bias is toward *not*
blocking** (anti-conservative for safety, conservative for recall). No fully independent evidence exists in the delivered
data (it is a closed 24-month set); real independence needs a later window or a customer dataset. This is a disclosed
limitation of the claim, and the natural place a pilot customer's data would strengthen it.

**Primary evaluation split: `validation` only** (following `ADR-101`'s "preferably the existing held-out validation
split"; it also leaves `future_holdout` un-consumed by any *new* decision-making gate). Pooling `validation ∪
future_holdout` doubles `n` (T05: 191 -> 350 exposed) at the price of consuming the final split. Pre-registered as a
**non-binding sensitivity**, and as Q1 for the founder. If the primary underpowered outcome triggers stop condition S4, the
switch is a *new registered hypothesis*, not a silent re-run.

### 2.6 Promotion-relevant evidence recomputed under the *same* contract (`A4`, `A9`)

"The same pre-existing promotion contract" is made exact:

- **Criteria applied to the `Z`-adjusted validation estimate = `G06`'s four executed conditions, verbatim thresholds**
  (`ValidationThresholds`, unchanged): (1) coverage `>= 0.50` -> treated as **assessability**, not violation (`A3`);
  (2) sign of adjusted harm equals sign of raw harm; (3) attenuation `<= max_adjusted_attenuation = 0.50`;
  (4) E-value `>= min_e_value = 1.50`, computed with the existing `e_value()`. (2)+(3) are one hypothesis (`H0_att`, since
  `H_Z >= 0.5 H_raw > 0` implies both), (4) is `H0_E`.
- **What it is not:** it is not "adjusted interval excludes zero". The contract *text* for `G06` lists that criterion and
  "E-value exceeds the strongest measured confounder-outcome association"; **the shipped code implements neither**
  (`_validate_one` checks only coverage, sign, attenuation, E-value; `adjusted_effect`'s interval is the raw interval
  shifted). I bind to the executed criteria and **flag the text/code gap** for the founder (Q9), as `TASK-070` did for
  `G12`, rather than silently choosing. "Interval includes zero" is additionally excluded *by principle*: its violation is
  the default outcome under low power, so making it a block criterion would turn incomplete evidence into a veto (`A3`).
- **Evidence-level rule:** `G17` is added to `_LEVEL_GATES` at `ADJUSTED_OBSERVATIONAL` (so `LEVEL_REQUIREMENTS` for levels
  `>= 3` include it) with `FailureAction.CAP_EVIDENCE`, `max_level_on_failure = PREDICTIVE` — identical in kind to `G06`
  and `G16`. `assign_policy_readiness` is unchanged: a candidate capped at `PREDICTIVE` gets `EXPERIMENT_ONLY`; nothing
  reaches `SHADOW_POLICY` without `ADJUSTED_OBSERVATIONAL`. `G15` materiality and `G13`/`G14` are untouched.
- **What is recomputed and what is not.** `G17` recomputes only the *adjustment-sensitive* evidence (2)-(4) on the
  evaluation split. It does not recompute `G03`-`G05`, `G10`, `G12`, `G15` (their inputs are not `Z`-dependent), does not
  overwrite `report.adjusted_effect`, and does not touch `exposure_tier2` (which reuses `G06`'s development-split adjusted
  effect). The `Z`-adjusted evaluation numbers live in `G17`'s own detail and diagnostics.

**Block only on positive evidence.** "Positive evidence of confounding from a correctly assessable `Z`" =
`p_Z <= alpha_k1/m` for at least one `Z` with status `assessed`. The point-estimate violation alone (attenuation `> 0.5` in
the sample) is **not** enough, because with `m = 10` and small effects a noise-only point violation is near-certain
(this is the quantitative reason multiplicity control is required: for `H_raw ~ 2 SE(D)` each single `Z` has a ~16%
chance of a noise-only point violation, so ~83% for some `Z` among ten).

**Two-sidedness (`A9`).** The tested null is "the adjusted result still satisfies the contract". If adjustment
*strengthens* the association, `H_Z > H_raw`, then `D_att = H_Z - 0.5 H_raw > 0` and `E_Z` is larger: both `p` values are
near 1, so it cannot block, no matter how large `|H_Z - H_raw|` is. There is deliberately **no** "large change" criterion
(a symmetric change-magnitude rule would block `T02`-type suppression). The mechanism is block-only in *action* and
symmetric in *evidence*: strengthened evidence does **not** unlock a candidate that another gate blocked (Q11).

### 2.7 Attribution (`A5`, `A6`) and distinguishability from `G12`/`G16`

- `G17` is its own gate id in `failure_modes` and its own warning line, with reason code
  `confounding_established` (contrast: `G12` = `robustness`, `G16` = `confound_like` / `composition_risk_indeterminate`).
- After all gate results exist, compute the counterfactual: `classify_evidence_level` and `assign_policy_readiness` with the
  `G17` result replaced by `PASS`. Store `k1_confounding.attribution = {counterfactual_evidence_level,
  counterfactual_readiness, credited}`, `credited = (G17 FAIL) and (counterfactual_readiness >= SHADOW_POLICY)`.
- **Credit rule:** only `credited = true` counts toward the invariant/`D2` accounting. `G17 FAIL` with `credited = false`
  (the candidate was already capped by `G12`, `G06`, `G11`, ...) is recorded and *explicitly not credited*. `G12`'s
  incidental caps (`T01` as shipped) get no credit; a `G17` FAIL on `T01`-as-shipped is `credited = false` because the
  counterfactual is still below `SHADOW_POLICY` via `G12`.
- Distinguishability test: for a candidate capped by `G12` only, `G17` is PASS/WARN and `failure_modes` contains `G12` only;
  for a candidate capped by `G17` only, the reverse; for both, both appear and `credited` reflects the counterfactual.

### 2.8 Report / evidence fields, warnings, reasons

- `GateResult(G17)`: `outcome` in {`PASS`, `WARN`, `FAIL`}; `detail` = one line naming reason, `m`, `m_assessed`, the
  established `Z`s (if any) with `H_raw`, `H_Z`, attenuation, `p_Z`, the critical `alpha_k1/m`, evaluation split and
  `n_exposed`. `warnings_from` already surfaces every `WARN`/`FAIL`, so limitations reach `report.warnings` with no new
  channel.
- Reason codes (`K1ConfoundingReason`, diagnostic, never changes cap severity): `not_applicable_k_ge_2`,
  `semantics_not_in_contract_version`, `no_declared_causal_order`, `no_admissible_z`, `no_assessable_z`,
  `no_evidence_of_confounding`, `confounding_established`.
- State mapping: `FAIL` iff a `Z` is established. Else `WARN` iff any limitation exists (declaration absent, empty pool,
  any `Z` not assessable, declared-unavailable confounders listed, evaluation exposure below `min_exposed_records`).
  Else `PASS`. `NOT_EVALUATED` is **not** used for coverage/limitation states (it is treated like `FAIL` for grading and
  would be exactly the coverage veto `A3` forbids).
- Diagnostics block `k1_confounding` (goes in `CandidateValidation.diagnostics`, serialised beside the report like the
  existing `composition_safety_*`): semantics version, evaluation split and row counts, `n_exposed`, `pool_declared`,
  `pool_source` + declaration sha256, `m`, `alpha_k1`, critical `p`, per-`Z` rows (`z`, `tier`, `binning`, `coverage`,
  `H_raw`, `H_Z`, attenuation, `E_raw`, `E_Z`, `p_att`, `p_E`, `p_Z`, `status`, `not_assessable_reason`, minimum-
  detectable-violation), decision, `declared_unavailable` list (class (ii)), `limitations[]`, `attribution`, plus the
  bounded claim string below.
- **Bounded-claim disclosure (the `ADR-101` sentence, made a required field):** "This result passed a check against N
  pre-declared observable, pre-exposure variables (list) on later-period data. Not assessed: (list, with reason).
  Declared but unobservable: (list). Unknown latent confounding is outside this check." Absent a declaration the field
  says the check was not performed.
- Run manifest gets `k1_confounding_semantics_version`, `k1_confounding_fwer_alpha`, `k1_evaluation_split`,
  `pre_exposure_order_source`, `pre_exposure_order_sha256`.

**Class (ii) (declared-but-unavailable) handling, stated with its tension.** `ADR-100` decision 3(ii) says such
confounding "must move to a conservative state, not silently promote"; `ADR-101` A3 says incomplete coverage is *recorded
as a limitation* and blocks only on positive evidence. I follow `A3` (later, narrower, explicit): a declared-but-
unavailable confounder (a `declared_unavailable` list in the declaration; the benchmark declaration would be empty: no
ground-truth leakage, Phase 1 A2) makes `G17` `WARN`, which is *visible* (warnings, diagnostics, claim string) but does not
change readiness. Whether class (ii) should carry a readiness consequence is Q5.

### 2.9 Interaction with existing gates, `T01`/`T05` fixture behavior (requirement 3)

| Gate | Interaction | Change |
|---|---|---|
| `G06` | Untouched (development split, joint coverage-gated greedy set, same four conditions). `G17` is *complementary*: it sees single `Z`s that `G06`'s coverage gate dropped (`destination`, `booking_lead_days`, `trip_duration_days` per `TASK-075`/`TASK-104`). When `G06` already fails, `G17` is still computed and recorded with `credited = false` | none |
| `G09` | Simpson on `customer_segment`; unchanged. `customer_segment` is tier 0 so it is also one of the `m` `Z`s | none |
| `G11` | Seasonality by month; unchanged and the *only* mechanism for month-driven confounding (`T02`); `G17` cannot see `booking_month` | none |
| `G12` | Unchanged; its incidental caps get **no** credit; the `T01` group-column artifact remains and is neutralized in tests the way `TASK-104` did (`ISOLATE_G12_ROLES`) | none |
| `G16` | `k>=2` only; `G17` is its `k=1` complement; reason codes disjoint | none |
| `G05` | Own BH family across the search; `G17`'s family is separate; no p-value shared | none |
| `G10` | Prerequisite of the promotion path; its selection effect is the partial-independence caveat | none |
| `G15`/`G13`/`G14` | Untouched | none |

Expected fixture behavior (registered in Section 4.3 P-table): **`T01`/`T05` forms in which one admissible, `G06`-dropped
`Z` carries a majority of the confounding become capped by `G17` with credit; the catalogue-equal-weight forms do not.**

---

## 3. Versioning plan (requirement 3, continued)

### 3.1 What the precedents actually did

| Precedent | Version bump | Old behaviour kept executable | Reproduction test |
|---|---|---|---|
| `ADR-014`/`ADR-015` (`G05`) | 1.0.0 -> 1.1.0 | no (artifact left alone) | none executable |
| `ADR-036`/`ADR-042` (`G06`) | 1.1.0 -> 1.2.0 | no | migration text only |
| `ADR-064`/`TASK-070` (`G12`) | 1.2.0 -> 1.3.0 | **yes**: `RobustnessSemantics.FIXED_QUANTILE_V1`, `ROBUSTNESS_SEMANTICS_BY_CONTRACT_VERSION`, run-manifest field | `test_pre_v1_3_0_semantics_reproduce_the_previous_contract_versions_verdicts`, `test_no_gate_other_than_g12_moved...` |
| `TASK-081` (`G16`, new `GateId`) | **none** (labelled "v1.3.0 plus G16" in `TASK-083`/`TASK-103`) | no switch | none |

The `G16` row is the weak precedent and I do **not** follow it: it left two different validators under one version string
(`ValidationReport.contract_version` is compared to the single constant), forcing downstream documents to write "contract
`1.3.0` (with `G16`)". `ADR-101` says "no silent change to frozen validation contract behavior". I follow `ADR-064`.

### 3.2 Proposed versioning

- `CONTRACT_VERSION = "1.4.0"` (defined to be exactly: v1.3.0 + `G16` as shipped + `G17`).
- `GateId.SINGLE_CONDITION_CONFOUNDING = "G17_SINGLE_CONDITION_CONFOUNDING"` appended (ids are never renumbered); `GateSpec`
  (`BiasClass.CONFOUNDING`, `CAP_EVIDENCE`, `PREDICTIVE`); added to the `ADJUSTED_OBSERVATIONAL` requirement tuple.
- `ValidationThresholds` gains `k1_confounding_fwer_alpha = 0.10` (existing fields unchanged; frozen `TASK-102` outreach
  thresholds are a different document and are unchanged).
- `K1ConfoundingSemantics` (`NONE_V0`, `SINGLE_Z_VALIDATION_V1`) and `K1_CONFOUNDING_SEMANTICS_BY_CONTRACT_VERSION`
  (`1.0.0`-`1.3.0` -> `NONE_V0`; `1.4.0` -> `SINGLE_Z_VALIDATION_V1`); `run_validation(..., k1_confounding_semantics=<current>)`,
  independent of `robustness_semantics`. Under `NONE_V0` `G17` is emitted as `PASS` with reason
  `semantics_not_in_contract_version` (the gate ladder stays complete; `_result_map` requires all ids).
- `input_contract.py`: `ValidationInput.pre_exposure_order` (default `None`); loader accepts `validation_roles` versions
  `1.0.0` and `1.1.0`.
- New module `validation/single_condition_confounding.py` (pure; `stratified_adjustment` injected exactly as in
  `composition_safety.py`, to avoid an import cycle and to reuse the real function).
- Docs: `validation-contract.md` §2 (versioning), a new §4d ("G17, v1.4.0, `ADR-101`, `TASK-105`") with the migration text,
  §5 gate table, §11 known limitations (the bounded-guarantee wording).

### 3.3 The compatibility invariant (checkable, and the reason default-on is acceptable)

> **`G17` can change any candidate's gate results, evidence level or readiness only if `k = 1` *and* the dataset carries a
> pre-exposure declaration.** For every `k>=2` candidate, and for every dataset without a declaration, `G17` is
> `PASS` (`not_applicable_k_ge_2`) or `WARN` (`no_declared_causal_order`), and `G00`-`G16` are numerically identical
> (isolated RNG stream, no shared state).

Consequences: (a) `test_pre_v1_3_0_semantics...` and every existing test on `k>=2` candidates or undeclared manifests keep
their verdicts; they need `k1_confounding_semantics` only if they assert the gate *count* or contract-version string
(implementer must baseline the suite first and enumerate: `tests/analytics/test_validation_contract.py`,
`test_validation_apply.py`, `test_validation_input_contract.py`, `test_g16_*.py`, `test_tier3_structural.py`,
`test_task104_trap_fixtures.py`, `tests/unit/test_finding_contracts.py`, `apps/api/app/findings/contracts.py`, and scripts
that iterate `GateId`). (b) Note: `test_pre_v1_3_0_...` pins verdicts (e.g. `CAND-004: PASS`) on gitignored
`artifacts/discovery/task-015-candidates.json`, which predate `G16`; the implementer must first establish whether it
passes at HEAD and record that baseline, because "reproduces v1.3.0" must mean *v1.3.0 as of HEAD*.

### 3.4 Reproduction tests (2b)

1. `NONE_V0` reproduces the **recorded** `docs/benchmark/task-103-evidence/run1/validation.json` gate outcomes for all 15
   candidates (a committed artifact that was produced under v1.3.0 + `G16`; the delivered dataset is in the repo).
2. `test_no_gate_other_than_g17_moved`: `NONE_V0` vs `SINGLE_Z_VALIDATION_V1` on the 15 candidates and on every fixture:
   `G00`-`G16` outcomes and numeric diagnostics identical; only `G17` differs, and only for `k=1`+declaration.
3. Mapping test: every historical `CONTRACT_VERSION` maps to the semantics it shipped with.
4. Old artifacts (`validation_contract_version` `1.3.0`) still load and interpret; nothing is re-graded.
5. Any candidate/run graded under `1.4.0` is new evidence needing its own grading cycle (`ADR-100` sequencing). Comparing a
   `1.3.0` result to a `1.4.0` result must state the version change, not just the candidate's change.

Known imperfection inherited from precedent: `ValidationReport.__post_init__` requires `contract_version == CONTRACT_VERSION`,
so a report produced under `NONE_V0` still says `1.4.0`; the run manifest's semantics field is the source of truth (same as
`FIXED_QUANTILE_V1` today). Fixing that is out of scope.

---

## 4. Test and kill-test plan (requirement 4); predictions registered first

### 4.1 Pre-registered predictions (frozen by this commit)

State the outcome *before* any run; report every row whether it is met or not.

| ID | Object | Prediction | Basis |
|---|---|---|---|
| **P1** | The 15 `TASK-103` `v0.6.2` grading candidates (`run1` = `run2`) | **0 of 15 change.** All 15 are `k=2` (I read every condition), so `G17 = PASS`, reason `not_applicable_k_ge_2`; `G00`-`G16`, evidence level and readiness identical to the recorded `validation.json`. Deviation = implementation defect | structure |
| **P1b** | All frozen candidate files I could open (13 files, 195 candidate rows: 10 blind runs, `task-015-candidates.json`, `TASK-103` `run1`/`run2`) | **0 `k=1` candidates.** The mechanism has never been exercised on a real frozen candidate set; its current realized recall cost **and** current realized protective value in real runs are both zero. `k=1` reaches promotion only via a future `reserve_k1_slot=True` run (`TASK-097`, default `False`) or an external candidate | counted |
| **P2** | Real-generator single-atom trap candidates on the delivered data (`T01`,`T02`,`T04`,`T05`) | Not reaching `SHADOW_POLICY` today (`TASK-104` §3: descriptive-only, wrong-signed, harm -29/-50/-30 EUR); `G17` credited blocks: **0**. Additionally the confounding shifts (roughly 28-54 EUR) are below the detection floor (2.4). **A 0 here must not be reported as safety** | Phase 1 B3, 2.4 |
| **P3** | FX-A: X drawn with one admissible **`G06`-dropped** `Z*` (`destination`) carrying share `s`, remaining share spread evenly; raw harm ~400 EUR, TASK-104 noise; seeds 101-106; `G17` at validation-only evaluation. `G06` still runs unchanged | Attenuation from `Z*` ~ `s x resolution` (~1.0 for a 5-level categorical). Predicted credited-cap count: `s=1.0`: **6/6**; `s=0.8`: **6/6**; `s=0.6`: **between 2 and 5 of 6 (no point claim: the expected `D` is ~ -0.1 x 400 = -40 EUR vs a critical ~ 2.6 x SE(D))**; `s=0.5`: **<= 3/6**; `s=0.4`: **0/6**. `G06`-off has no effect (it was not the stopper); `G17`-off gives `SHADOW_POLICY` | 2.3-2.4, `TASK-104` §4c |
| **P4** | FX-B: catalogue-equal weights (`T05` as catalogued and generated; `T01` fixture with four equal confounders) | **0/6 blocked by `G17`; remain at `SHADOW_POLICY`.** Each admissible `Z` carries `s = 0.25`; adjusting for one removes ~0.25 of the bias (attenuation ~0.25, and `TASK-104` measured 0.31-0.37 for `G06`'s broader set), below the 0.50 ceiling. **The `TASK-105` objective "`T01`/`T05` as catalogued become capped by the new mechanism" is therefore predicted NOT met.** This is the proven case `A7` names for a joint-`Z` hypothesis | additivity of the fixture bias |
| **P5** | `T02`-type duration-only fixture (`Z* = trip_duration_days`, `s ~ 0.85-1.0`, real-generator shape: duration dominant, `destination` diluting) | Capped by `G17` with credit **>= 5/6** (`TASK-104` §4d found this form *not* capped by `G06`); numeric-bin resolution (top decile `>= 12` contains `>= 14`) may lower attenuation; recorded | 2.3 |
| **P6** | FX-C suppression: `X = supplier=Atlas`-shaped, `Z = trip_duration` positively confounded with `X` and *beneficial* to `Y`, so adjustment *strengthens* harm (`H_Z >= 1.5 H_raw`); candidate reaches `SHADOW_POLICY` without the mechanism | **0 blocks; `SHADOW_POLICY` unchanged; `p_att`, `p_E` ~ 1.** Deterministic in sign. Failing this falsifies the design (S2) | 2.6 |
| **P7** | FX-D negative control (`Z` outcome-associated, unrelated to exposure; e.g. `party_size` for a `destination`-driven `T01`) | Not established, FWER-bounded; expected block rate `<= 0.05` per candidate | 2.4 |
| **P8** | FX-E null (no confounding, genuine effect, invented columns; `m` in {3,7,10,15}; effect from `~2 SE` to `~10 SE`; >= 2,000 simulated datasets per cell) | False-block rate `<= alpha_k1 = 0.10` in every cell (Bonferroni bound, worst case at the contract boundary); **predicted realized `<= 0.03` for effects `>= 3 SE`**. The no-correction mutant exceeds 0.10 for `m >= 7` | 2.4 |
| **P9** | Mediator guard (`T03`-shaped: `paid_search -> discount -> margin`) | Pool empty => `WARN no_admissible_z`; no block. The **mediator-admitting mutant** blocks a genuine total effect (shows why R5 exists) | 2.2 |
| **P10** | `T01` **as shipped** (`G12` artifact intact), any of P3's forms | `G17` may FAIL but `credited = false` (counterfactual still capped by `G12`); the credited kill-test therefore uses `ISOLATE_G12_ROLES` as in `TASK-104` | 2.7 |
| **P11** | Contract invariance | `G00`-`G16` identical between `NONE_V0` and `SINGLE_Z_VALIDATION_V1` for 100% of candidates and fixtures | 3.3 |
| **P12** | Evaluation-split sensitivity (non-binding) | Decisions on P3 (`s >= 0.8`) concordant between `validation`-only and pooled in >= 90% of seeds; the pooled variant has strictly more blocks at `s in {0.5, 0.6}` | 2.4-2.5 |
| **P13** | `T02` month-driven fixture (`booking_month` only) | `G11` caps (unchanged, `TASK-104`); `G17` does nothing (month is not a column); class (ii) is *not* exercised by the benchmark | Phase 1 |

### 4.2 Unit and property tests (`tests/analytics/test_g17_*.py`, neutral where possible: invented columns, no dataset)

- **U1 pool purity:** `A(C)` depends only on (declaration, exposure column); replace outcomes/rows -> identical; exposure
  column and same-tier and unlisted columns excluded; empty declaration -> empty pool; declaration listing a
  non-`DECISION_TIME`/non-eligible column -> loader rejects (fail-closed).
- **U2 single-`Z` count:** spy on `_stratified_adjustment`: exactly `m` calls with `len(columns) == 1` for the `Z` checks;
  none with `>= 2`.
- **U3 evaluation data:** the frames given to the estimator contain only `validation` rows; bin edges computed from
  development `Z` values only (changing later-split outcomes or later-split `Z` leaves edges identical).
- **U4 multiplicity:** neutral null simulation (P8): `P(block) <= alpha_k1` per cell; the no-correction mutant fails it.
- **U5 two-sided:** strengthening designs (P6 and a sweep of `H_Z/H_raw` in [1, 5]) never block.
- **U6 attribution:** credited iff counterfactual `>= SHADOW_POLICY`; a `G12`-only cap -> `credited = false`; `G16`
  untouched; reason codes disjoint.
- **U7 inertness:** `k>=2` -> `PASS not_applicable_k_ge_2`; `NONE_V0` -> `PASS semantics_not_in_contract_version`; undeclared
  dataset -> `WARN no_declared_causal_order`; verdicts unchanged.
- **U8 isolation:** numeric `G04`/`G05` diagnostics identical with and without `G17` in the same run (RNG stream isolated).
- **U9 limitations never block:** coverage below floor, `bootstrap_degenerate`, `raw_harm_not_positive`, exposure below
  `min_exposed_records` -> `WARN` with the reason in the detail and in `report.warnings`; never `FAIL`/`NOT_EVALUATED`.
- **U10 determinism/permutation:** identical output on identical inputs; invariant to row order and to the order of `Z`.
- **U11 E-value sub-criterion:** applicable only when raw baseline `E >= 1.5`; closed-form `h_E` matches `e_value()` inversion.
- **U12 versioning:** mapping test, `GATE_SPECS`/`LEVEL_REQUIREMENTS` shape, loader accepts `1.0.0`/`1.1.0` roles.
- **U13 declaration soundness (benchmark only):** the proposed `travel` declaration is checked against the real generator's
  data flow (the Phase 1 `ast` parent analysis): no declared-admissible `Z` for any trap is a descendant of that trap's
  exposure. This proves the *declaration* correct for the benchmark; the mechanism never reads the generator.

### 4.3 `TASK-104` fixtures re-run (test-side; reuse `build_fixture` and the real `run_validation`; no gate is re-implemented)

Families FX-A ... FX-E of P3-P8 with seeds 101-106 (nulls: >= 2,000 simulated datasets, seeds recorded). Each fixture
asserts its *precondition* (e.g. `Z*` not in `G06`'s `adjustment_columns_used`; if `G06` retains it, the fixture is **invalid
and reported as such**, never silently substituted). Every result table is published in full, including rows that
contradict a prediction.

### 4.4 Adversarial kill-tests (the `TASK-104` three-state protocol, plus mutants)

**KT1 (the required one).** `g17_disabled()` context manager (same style as `g06_disabled`/`g16_disabled`: replaces the
`G17` result with `PASS`, restores the original object, restoration asserted). On FX-A (`s = 1.0`, `s = 0.8`, `T01` with
`ISOLATE_G12_ROLES`, and `T05`): assert in order: (1) capped by `G17` with `credited = true`, caveat in `report.warnings`,
below `SHADOW_POLICY`; (2) mechanism disabled -> `G17` PASS, caveat absent, **`SHADOW_POLICY` reached again**; (3) restored ->
capped again. The **catalogue-equal** forms (P4) are expected to stay at `SHADOW_POLICY` in all three states and are
reported as such (they *cannot* pass a kill-test the mechanism cannot satisfy).

**Mutants (each must be caught by a named test, else the design has an unguarded degree of freedom):**
K2 evaluate on `development` instead of `validation` (caught by U3 and by an FX-E leakage check); K3 subset search over
`Z` (U2); K4 no multiplicity correction (U4/P8); K5 two-sided "large change" rule (U5/P6 blocks `T02`); K6 mediator-
admitting pool (P9 shows a false block; U1); K7 pool chosen after seeing candidate effects (U1 property); K8 point-estimate
rule without significance (P8/P7 false blocks); K9 coverage veto (U9). A mutant that survives means a needed test is
missing, not that the mutant is acceptable.

### 4.5 False-positive / recall-cost checks on existing candidates

- **`v0.6.2` 15 candidates (`docs/benchmark/task-103-evidence/`):** which change? **None** (P1): all `k=2`, already capped by
  `G16` at `predictive_association`/`descriptive_observation`, `experiment_only`. Verified by the reproduction tests, not
  assumed.
- **All frozen candidate files:** 0 `k=1` (P1b). So "recall cost on existing benchmark candidates" is **0 and unmeasurable
  there**. I refuse to fabricate a number from a population that is empty.
- **`k=1` census (the honest substitute), run once, after implementation:** enumerate the engine's single atoms on the delivered
  development split, validate them under `1.3.0`/`NONE_V0` and `1.4.0` with the proposed declaration; report (i) how many
  reach `SHADOW_POLICY` today, (ii) how many `G17` blocks, credited or not, (iii) for each, the per-`Z` table, (iv) any
  block of a component the benchmark's pattern match (`TASK-028`) labels true-positive. Prediction: few single atoms reach
  `SHADOW_POLICY`; credited blocks `<= ceil(alpha_k1 * N_promotable)` plus genuine confounded ones; **no prediction of a
  specific count** because I cannot enumerate it without running the pipeline (that run is part of 2b).
- **`reserve_k1_slot=True` discovery on the delivered data** (deterministic, `TASK-097`): the reserved single is evaluated the
  same way.

### 4.6 Reporting a null or harmful result

- **Null** (no candidate changes; the expected outcome on real candidates): reported as "`G17` changed 0 of N", with the
  detection-floor table (2.4) beside it and the sentence that a 0 is not evidence of safety. Not framed as success.
- **Diffuse-confounding miss** (P4): reported as an *objective not met* against the `TASK-105` regression target, not as a
  pass of the design on its own terms.
- **Harmful** (a false block in nulls above bound; a `T02` suppression block; a true-pattern `k=1` blocked): reported verbatim
  with the fixture, seed, per-`Z` table; the design version is marked failed for that hypothesis; no retuning of `alpha`,
  bins, tiers or the split to recover it. A revised design is a new dated version with a new registration.
- The results document is created in 2b and contains the full tables of 4.1 with observed values next to predictions.

---

## 5. Pre-registered risks and stop conditions (requirement 5)

Evaluated on the **primary** specification (validation-only, deciles/12-raw bins, `alpha_k1 = 0.10`, Bonferroni). None
of these may be tuned away.

| ID | What would show the design is wrong | Threshold | Consequence |
|---|---|---|---|
| **S1** | False-block rate in FX-E null exceeds `2 x alpha_k1 = 0.20` in any cell, or exceeds 0.10 in any cell with effect `>= 3 SE` | any | SE method or family definition is wrong -> stop, redesign (do not raise `alpha`) |
| **S2** | `T02`-type suppression fixture (P6) is blocked in any seed | any | the two-sided design is wrong -> stop |
| **S3** | Any of K2-K9 mutants survives (not caught) | any | a degree of freedom is unguarded -> add test or redesign |
| **S4** | Power: on FX-A `s = 1.0` and `s = 0.8` the credited-cap rate is `< 5/6` seeds | either | the mechanism cannot deliver even its bounded guarantee at these sample sizes on the primary split -> **recommend abandoning** as specified; the pooled-split variant is a *new registered hypothesis* (Q1), not an in-place change |
| **S5** | `G00`-`G16` differ between `NONE_V0` and `SINGLE_Z_VALIDATION_V1` for any candidate | any | isolation broken -> defect, block release |
| **S6** | On the `k=1` census, `G17` blocks more than `2` benchmark-true-positive `k=1` components of at most `10` (`> 2 x` the expected `alpha` rate), or the census has too few promotable candidates to say anything | see text | report as "insufficient/harmful"; do not claim precision |
| **S7** | The declaration soundness test (U13) fails for the proposed tiers | any | declaration wrong -> fix the declaration *before* any fixture result is looked at; if discovered after, the run is void and re-registered |

**Expected costs (registered):**

- *Recall:* per genuinely unconfounded `k=1` candidate, false-block probability `<= 0.10` worst case (contract boundary),
  `<= ~0.03` for effects `>= 3 SE`; realized real-candidate recall cost **0** today (P1b). Expected extra recall cost with
  `reserve_k1_slot=True`: `<= 0.10 x` (number of reserved singles), at most one per run by `TASK-095`'s design.
- *Precision/safety:* **the guarantee is weak by construction.** It catches confounding that (i) runs through one admissible,
  declared `Z` carrying a majority of the bias, (ii) exceeds the detection floor of 2.4 (tens to ~90 EUR at the delivered
  size), (iii) is resolvable at the chosen stratification. It does **not** catch diffuse multi-`Z` confounding (P4),
  M-bias through a pre-exposure collider, month-driven confounding (`G11`'s job), or anything latent. Expected credited
  precision on real data is low because there is little to catch and little power to catch it.
- *Cost of the declaration:* a new customer-side step; an absent declaration means the mechanism does nothing (WARN).

**Evidence that would make me recommend abandoning it:** S4 fails (cannot detect even a total single-`Z` confounder at the
delivered `n`); or S1/S2 (it harms genuine or suppressed candidates); or a pilot customer cannot supply a defensible
`pre_exposure_order` (the mechanism then never runs and adds a contract surface for nothing). If S4 passes only with
pooled splits, the recommendation goes to the founder as a trade (power vs the last untouched split) rather than being
decided by the results.

**Risks acknowledged (not stop conditions):** the `pre_exposure_order` is an unverifiable assumption; the partial-
independence caveat (2.5); numeric bin resolution understates attenuation (2.3); `SE(D)/SE_raw` ratio assumed 0.55-0.70
until measured; performance of the paired bootstrap in pure Python; the `G06` contract-text/code gap is inherited
(Q9); `G17` default-on under 1.4.0 changes safety semantics, so any earlier grading no longer characterizes the new version
and a new grading cycle is required (`ADR-100`/`ADR-101`).

---

## 6. Open questions that need a founder decision (labelled)

- **Q1 Evaluation split.** Primary = `validation` only (recommended, follows `ADR-101` wording, leaves `future_holdout`
  unconsumed) vs pooled `validation ∪ future_holdout` (2x power; consumes the final split). Power table in 2.4.
- **Q2 Partial independence.** Accept the disclosed partial independence (`stability_credit_weight = 0.5` uses later-split
  raw sign; `G10`), or require an engine setting (`stability_credit_weight = 0`) for the graded version so the evaluation
  split is untouched by selection. The latter is an engine/accepted-default change (`ADR-070` binding), out of scope here.
  Recommendation: accept and disclose.
- **Q3 The `pre_exposure_order` declaration.** Approve the tier proposal in 2.2 (an assumption, not a measurement), name who
  signs it for the benchmark and for a customer; choose source A (manifest `validation_roles` `1.1.0`, new dataset
  version) vs B (hash-recorded sidecar for the frozen `v1.1.0` dataset). Recommendation: A generally, B for the frozen
  benchmark.
- **Q4 Diffuse confounding (the headline).** Accept the bounded guarantee (single-`Z` can only catch a majority
  confounder), **or** open the joint-`Z` hypothesis `A7` reserves for "a proven case" — `T05`-as-catalogued *is* that case
  (`TASK-104`: 6/6 reach `SHADOW_POLICY`). If opened, what form (pre-declared pairs `m(m-1)/2` checks; one pre-declared
  whole-pool joint check with its own coverage rule; ...) is a new hypothesis with its own multiplicity family. Also:
  redefine the `TASK-105` regression targets for `T01`/`T05` to the FX-A forms, or keep the catalogued forms as
  expected-miss reports.
- **Q5 Class (ii).** `A3` says limitation only; `ADR-100` decision 3(ii) says a conservative state. I implemented `WARN`
  (visible, non-blocking). Confirm, or require a readiness consequence.
- **Q6 Error control.** `alpha_k1 = 0.10` Bonferroni per candidate as a new named threshold in `ValidationThresholds`;
  confirm (or `0.05`).
- **Q7 Contract version.** Bump to `1.4.0` (recommended; defined as 1.3.0 + `G16` + `G17`) rather than following `G16`'s
  no-bump precedent; and confirm default-on for new runs, given the compatibility invariant (3.3).
- **Q8 Catalogue/generator.** Apply the catalogue-only corrections (Section 1) to the code catalogue and the manifest, not
  to frozen restricted artifacts; and decide whether `T02`'s `booking_month` justifies a *new benchmark version* (would
  exercise class (ii)); not proposed as a Phase 2 action.
- **Q9 `G06` contract-text vs code gap.** Text: adjusted interval excludes zero; E-value exceeds strongest measured
  confounder-outcome association. Code: neither. Out of scope here; the design binds to the *executed* criteria. Decide
  whether to open a `TASK-070`-style reconciliation.
- **Q10 Stratification resolution.** Raw levels `<= 12` else deciles (single-`Z`), vs `G06`'s quartiles; pre-registered
  and disclosed; quartile variant reported as a sensitivity.
- **Q11 Suppression and unlocking.** `G17` is block-only; strengthened adjusted evidence never unlocks a candidate that
  another gate blocked. Confirm that is the intended reading of `A9`.

---

## 7. Traceability to `ADR-101`

| Clause | Where satisfied |
|---|---|
| A1 scope: `k=1` on the promotion path only | 2.1 (`k>=2` -> vacuous PASS; `G16` untouched) |
| A2 admissible `Z` from a pre-declared pool; no mediators/colliders/target-derived | 2.2 (R1-R3 existing; R5 declared strict-precedence order; safe default = empty pool) |
| A3 no coverage veto; limitation in provenance; block only on positive evidence | 2.6, 2.8 (`WARN` states; `NOT_EVALUATED` not used; established-violation rule) |
| A4 no fixed percentage; same promotion contract | 2.6 (G06's executed criteria, existing thresholds; the 0.50 is the *contract's*, not a new parameter) |
| A5 `G12` not credited | 2.7 |
| A6 attribution | 2.7 (counterfactual readiness; credited flag; distinct reason) |
| A7 pool fixed before candidates; one multiplicity family; single-`Z`; no post-hoc `Z` | 2.2-2.4 (`m` fixed by declaration; Bonferroni; spy test U2; mutants K3, K7) |
| A8 independent evaluation data | 2.5 (validation split; edges from development; partial independence determined from the code and disclosed) |
| A9 two-sided; `T02` suppression must not block | 2.6, P6, U5, K5, S2 |
| Catalogue/generator policy | 1 (no auto-alignment; catalogue fixes; generator change flagged, not proposed; `T03` stays a mediator) |
| Phase 2 contract: recompute, block only if the adjusted result violates the contract, record coverage and attribution | 2.6-2.8 |
| Design -> review -> implement; contract versioning; no silent change | 3, this document is 2a; independent design review precedes 2b; official grading only after |

## 8. What this design does not do

It does not implement anything; does not change the generator, catalogue, engine, gates, thresholds or the frozen
`TASK-102` bar; does not raise `D2` Part B (stays 2/5); does not touch `TASK-057`/outreach; does not claim protection
against diffuse, latent, or month-driven confounding; does not use `G12`'s incidental blocks as evidence; does not
schedule any grading run (a new grading cycle of the changed version is required afterward and is a separate task).
