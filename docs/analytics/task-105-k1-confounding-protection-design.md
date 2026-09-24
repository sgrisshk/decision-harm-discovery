# TASK-105 Phase 2a — Single-condition (`k=1`) confounding protection: design document

**Owner:** STATISTICS (lead), ARCHITECT (support). **Recorded:** 2026-09-24. **Status:** DESIGN ONLY. Nothing in
`engine.py`, any gate, `apply.py`, `contract.py`, `grading.py`, `input_contract.py`, the generator, the catalogue, or any
threshold was changed. No mechanism code exists. Every "prediction" below is registered **before any mechanism run
exists** (there is nothing to run yet); it is frozen by the commit of this file and is not to be edited after a result is
seen (a change after seeing a result is a new, dated design version, never an edit).

> **REVISION 1 (2026-09-24), in response to the independent adversarial design review (APPROVED WITH REVISION NEEDED).**
> This file is now design version **v1 + Revision 1**. The original text (commit `7175f00`) is **kept**; where Revision 1
> supersedes a passage, the passage carries a `[Rev 1 ...]` marker at the place it occurs and the full replacement,
> the original values and the reasons are in **Section 9** (change log, corrected power arithmetic, superseding
> pre-registered predictions with the originals preserved, question triage, oracle-declaration statement). Section 10 holds
> the read-only measurements taken for Revision 1, appended **after** the Section 9 predictions were committed. Original
> predictions P3, P4, P5, P8 are **superseded, not edited**; P1, P1b, P2, P6, P7, P9-P13 stand. **The mechanism is unchanged**
> (pool, single-`Z`, validation split, Bonferroni family, thresholds, two-sidedness, attribution, 1.4.0 semantics). One
> estimand clarification (Section 9.3, raw baseline restricted to usable strata) and one reporting addition (Section 9.5,
> detection floor in the claim) are flagged there for the round-2 reviewer to confirm they are not mechanism changes.

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
    four indicators with **equal exposure weights**; `[Rev 1: the original wording "s = 0.25 each" was unverified on the
    outcome side; outcome-side shares are unmeasured in the design, measured in Section 10; and in the TASK-104 fixtures
    the bias share is the squared-weight share, Section 9.4]`) **is predicted not to be blocked**, so `T05`-as-catalogued and the
    equal-weight `T01` fixture are **predicted to stay at `SHADOW_POLICY`** (Section 4, P4). That is a direct consequence of
    `ADR-101`'s A7 (single-`Z` only, no subsets) combined with A4 (same contract); it is the "proven case" A7 says would
    justify a joint-`Z` hypothesis. It is reported, not hidden, and put to the founder (Q4).
12. Real-data power is low at the delivered sample size (Section 2.4): the mechanism would not detect the
    real-generator confounding-induced shifts (roughly 28-54 EUR for T01/T04/T05). The design's honest claim is bounded accordingly.
    `[Rev 1: the figures in Section 2.4 were 50%-power critical values, not detection floors; the 80%-power floors are
    about 1.3x larger and the comparison must be made against the required shift 0.5*H_raw + floor, Section 9.2.]`
13. **`[Rev 1]` Two more limits stated up front.** (a) The declared pool/tiering for the benchmark is **oracle-informed**
    (the author had read the generator): fixtures passing under it show the mechanism works *when the declarer knows the
    true structure*, not that it works under a customer-signed declaration (Section 9.5). (b) Whether ADR-101 A4
    ("no fixed percentage (no 50%)") permits reusing the contract's own 0.50 attenuation ceiling is genuinely ambiguous
    and is a founder question with both readings and consequences (Q12, Section 9.1/9.8); the design as written adopts the
    "contract's existing 0.50 is acceptable" reading and says so.

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

> **[Rev 1 supersedes the sentence above and the "Proposed catalogue-only correction" column below.]** Editing
> `confounded_by` in `synthetic_benchmark.py` is **not** a catalogue-only change: `hidden_ground_truth.json` is the direct
> serialization of that list, so it changes the regenerated file's bytes and sha256 (`5c41aab8...`, pinned by
> `test_default_config_still_reproduces_the_frozen_hidden_ground_truth`, described there as "a hard stop, not a value to
> update"; also `evaluation/checksums.json`; and `test_task105_generator_realization.py` lines ~258/519/547 compare the
> manifest and generator to the file). Under ADR-101 that is a benchmark identity change. **The proposal to edit the code
> catalogue is withdrawn.** The corrections live in a **separate, additive metadata layer**: new per-trap fields in
> `docs/benchmark/task-105-trap-manifests.json` (`authoritative_confounders`, `specified_not_realized`, `mediated_by`,
> `test_negative_controls`); the existing `intended_confounders` (= the frozen catalogue) is left untouched; generator
> output, `hidden_ground_truth.json` and all checksums stay byte-identical. Detail and the consistency fix for
> `T01`/`T04` in Section 9.7.

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

> **[Rev 1: policy consistency.]** The table above records `T02` `booking_month` and `T03` `customer_type`/`installments`
> as `specified_not_realized` (intent not inferred) but silently reclassified `T01` `party_size`/`trip_duration_days` and
> `T04` `destination` as "negative controls", i.e. it inferred intent toward the generator. ADR-101 says the difference
> "is information" and forbids auto-alignment. Revision 1 records **all** catalogued-but-not-realized columns
> (`T01` `party_size`, `trip_duration_days`; `T02` `booking_month`; `T03` `customer_type`, `installments`; `T04`
> `destination`) uniformly as `specified_not_realized`. "Negative control" is retained only as a **test-usage label**
> (`test_negative_controls`: columns the *generator* gives no exposure effect, so a correct mechanism must not block on
> them), which asserts nothing about intent. Whether `T01`/`T04` intended those columns as confounders (=> generator
> fix = new benchmark version) or over-listed them is now explicit founder question Q8b.

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

> **[Rev 1: the declaration is oracle-informed; this limits what any fixture result can claim.]** The author of this
> declaration had read `_generate_row` (Phase 1) and the tier boundaries (in particular putting `destination`,
> `booking_lead_days`, `trip_duration_days` before `manager`/`supplier`/`payment_method`/`manual_exception`, and
> `discount_rate` after `acquisition_channel`) are exactly the structure the generator has. "Derived from `semantic_meaning`
> strings" is therefore not independence. Consequently: (1) **fixtures passing under this declaration show that the
> mechanism works when the declarer knows the true structure; they do not show it works with a customer-signed
> declaration**, which can be wrong (a descendant declared as pre-exposure, or a true confounder left unlisted). (2) U13
> tests declaration *soundness* against the generator's data flow (a check that the declaration matches the truth),
> **not independence** of the declaration from the truth; it cannot be independent, and its result is not evidence about
> declaration quality in the field. (3) The effect of a wrong declaration is only *bounded by test* through the mutants
> (K6 mediator-admitting pool: false block) and P9; the field rate of wrong declarations is unmeasured. This sentence is
> required in the results document and in any claim made from these fixtures (Section 9.5).

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
`[Rev 1: when usable-stratum coverage < 1, "H_raw over all rows" is not like-for-like with H_Z, which is over usable strata
only (_stratified_adjustment returns the exposure-weighted effect over usable strata). The baseline is redefined as
H_raw,U (raw effect on the usable strata), Section 9.3; identical when coverage = 1.]`

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
  this is a choice, flagged (Q6), with a **non-binding** sensitivity at `0.05` and `0.20`. `[Rev 1: the "equals fdr_alpha"
  point is an analogy only. fdr_alpha controls the false discovery rate over the search family (G05, BH); alpha_k1 is a
  per-candidate family-wise error rate. They are different error rates and do not justify each other. The effective
  per-test level is small: block iff p_Z <= alpha_k1/m with p_Z = 2*min(p_att, p_E), i.e. each one-sided sub-test is at
  alpha_k1/(2m) = 0.0071 (m=7), 0.0050 (m=10), 0.0033 (m=15); the FWER 0.10 is an upper bound at the contract
  boundary, not the realized rate.]`

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

> **[Rev 1 supersedes the last column above and the "Reading"/"detection floor" statements below; original values kept
> here for traceability.]** The "approximate minimum violation `D` detectable" column (-55/-56/-52/-90 EUR) is the
> **50%-power critical value** `z_crit x SE(D)`, not a detection floor, and it is expressed in units of the test
> statistic `D = H_Z - 0.5*H_raw`, whereas the comparison below is made to a *shift* `H_raw - H_Z`. `SE(D)/SE_raw =
> 0.55-0.70` is an **assumption** (measured in Section 10). The E-value branch is tested on `H_Z` alone (unpaired), so its
> SE is about `SE_raw`, not `0.55-0.70 x SE_raw`. Corrected 80%-power figures and the like-for-like comparison are in
> Section 9.2. Original text follows unchanged.

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

> **[Rev 1: what "the same promotion contract" does and does not include.]** The design recomputes only sign,
> attenuation and E-value (the criteria G06 executes). It does **not** recompute on the `Z`-adjusted estimate: `G03`
> sample adequacy (the evaluation `n_exposed` is only reported and gated as a `WARN`, `min_exposed_records`), `G04`
> (interval excludes zero), or `G15` materiality. Assessment: (i) `G04`/`G15` on an adjusted estimate would make "not
> significantly positive" / "not materially large" a block condition, whose violation is the *default* outcome at the
> delivered power (Section 9.2), i.e. exactly the coverage-style veto A3 forbids, unless framed as "significantly below the
> bar", which needs its own multiplicity family and is a different (weaker-power) hypothesis; (ii) `G04`'s and `G15`'s
> unadjusted versions already run and are unchanged, so a candidate must still clear them on the raw estimate. Whether
> "same contract" should nonetheless include them is a founder decision folded into Q12 (Section 9.8), with consequences.
> The gap is stated here rather than resolved silently.

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
  says the check was not performed. **`[Rev 1: this sentence alone reads as clearance at low power. The required, user-facing
  field additionally carries, per Z, the 80%-power minimum detectable violation and the plain-language consequence; the
  final text is in Section 9.5 and supersedes this sentence for the user-facing field. The diagnostics-only placement of
  the minimum-detectable-violation in the list of fields below is superseded.]`**
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

> **[Rev 1: the original invariant below is self-contradictory and is superseded by the restatement that follows it.]**
> Original (kept): "`G17` can change any candidate's gate results, evidence level or readiness only if `k = 1` *and* the
> dataset carries a pre-exposure declaration. For every `k>=2` candidate, and for every dataset without a declaration,
> `G17` is `PASS` (`not_applicable_k_ge_2`) or `WARN` (`no_declared_causal_order`), and `G00`-`G16` are numerically
> identical (isolated RNG stream, no shared state)." Defect: `G17` is itself a new gate row, so "can change any
> candidate's gate results" is false at the row level, and for an undeclared `k=1` candidate the new `WARN` adds a
> `report.warnings` line and changes the serialized report.
>
> **Revised invariant (Rev 1):** **`G00`-`G16` gate outcomes and numeric diagnostics, evidence level and policy readiness
> are unchanged for every candidate, except that a `k=1` candidate on a dataset carrying a pre-exposure declaration may
> be capped by `G17` (evidence level / readiness change only via a `G17` FAIL).** What *does* change for every candidate,
> by construction, and is not covered by any "unchanged" claim: the report has a 17th gate row; for undeclared `k=1`
> candidates it has a new `WARN` `no_declared_causal_order` (a new `report.warnings` line; `WARN` is satisfied and never
> changes level/readiness); the contract-version string and `ValidationThresholds` (new field
> `k1_confounding_fwer_alpha`, `version`) change; serialized report bytes therefore differ. Reproduction claims are
> at **gate-outcome level** (Section 3.4 Rev 1 note).

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

> **[Rev 1: what `NONE_V0` does and does not reproduce.]** (1) `NONE_V0` reproduces **gate outcomes** (G00-G16 and
> readiness) of v1.3.0-with-G16, **not bytes**: the report says `1.4.0`, has a 17th gate row (`G17` PASS
> `semantics_not_in_contract_version`), and `ValidationThresholds` has an extra field and a different `version`. Any
> test or claim of "byte-reproduction" is withdrawn; the reproduction tests compare gate outcomes and numeric
> diagnostics only. (2) The proposed map `1.0.0`-`1.3.0 -> NONE_V0` records only "no G17"; it does **not** model that
> `G16` did not exist before 1.3.0 (`G16` has no semantics switch, `TASK-081`), so `NONE_V0` for versions `1.0.0`-`1.2.0` is
> **not** a reproduction of those versions' gate ladders (it would still emit `G16`). It is a "G17 off" switch, nothing
> more; the mapping test must be worded accordingly, and the 1.0.0-1.2.0 entries claim only "G17 absent", not "1.x
> behaviour reproduced". Reproduction of a pre-1.3.0 run is not offered by this design.

---

## 4. Test and kill-test plan (requirement 4); predictions registered first

### 4.1 Pre-registered predictions (frozen by this commit)

State the outcome *before* any run; report every row whether it is met or not.

| ID | Object | Prediction | Basis |
|---|---|---|---|
| **P1** | The 15 `TASK-103` `v0.6.2` grading candidates (`run1` = `run2`) | **0 of 15 change.** All 15 are `k=2` (I read every condition), so `G17 = PASS`, reason `not_applicable_k_ge_2`; `G00`-`G16`, evidence level and readiness identical to the recorded `validation.json`. Deviation = implementation defect | structure |
| **P1b** | All frozen candidate files I could open (13 files, 195 candidate rows: 10 blind runs, `task-015-candidates.json`, `TASK-103` `run1`/`run2`) | **0 `k=1` candidates.** The mechanism has never been exercised on a real frozen candidate set; its current realized recall cost **and** current realized protective value in real runs are both zero. `k=1` reaches promotion only via a future `reserve_k1_slot=True` run (`TASK-097`, default `False`) or an external candidate | counted |
| **P2** | Real-generator single-atom trap candidates on the delivered data (`T01`,`T02`,`T04`,`T05`) | Not reaching `SHADOW_POLICY` today (`TASK-104` §3: descriptive-only, wrong-signed, harm -29/-50/-30 EUR); `G17` credited blocks: **0**. Additionally the confounding shifts (roughly 28-54 EUR) are below the detection floor (2.4). **A 0 here must not be reported as safety** | Phase 1 B3, 2.4 |
| **P3** `[SUPERSEDED by P3r, Section 9.4; original retained]` | FX-A: X drawn with one admissible **`G06`-dropped** `Z*` (`destination`) carrying share `s`, remaining share spread evenly; raw harm ~400 EUR, TASK-104 noise; seeds 101-106; `G17` at validation-only evaluation. `G06` still runs unchanged | Attenuation from `Z*` ~ `s x resolution` (~1.0 for a 5-level categorical). Predicted credited-cap count: `s=1.0`: **6/6**; `s=0.8`: **6/6**; `s=0.6`: **between 2 and 5 of 6 (no point claim: the expected `D` is ~ -0.1 x 400 = -40 EUR vs a critical ~ 2.6 x SE(D))**; `s=0.5`: **<= 3/6**; `s=0.4`: **0/6**. `G06`-off has no effect (it was not the stopper); `G17`-off gives `SHADOW_POLICY` | 2.3-2.4, `TASK-104` §4c |
| **P4** `[REWORDED by P4r, Section 9.4: the "s = 0.25 each" basis was unverified; the 0/6 prediction itself is kept; original retained]` | FX-B: catalogue-equal weights (`T05` as catalogued and generated; `T01` fixture with four equal confounders) | **0/6 blocked by `G17`; remain at `SHADOW_POLICY`.** Each admissible `Z` carries `s = 0.25`; adjusting for one removes ~0.25 of the bias (attenuation ~0.25, and `TASK-104` measured 0.31-0.37 for `G06`'s broader set), below the 0.50 ceiling. **The `TASK-105` objective "`T01`/`T05` as catalogued become capped by the new mechanism" is therefore predicted NOT met.** This is the proven case `A7` names for a joint-`Z` hypothesis | additivity of the fixture bias |
| **P5** `[SUPERSEDED by P5r-a/P5r-b, Section 9.4; original retained]` | `T02`-type duration-only fixture (`Z* = trip_duration_days`, `s ~ 0.85-1.0`, real-generator shape: duration dominant, `destination` diluting) | Capped by `G17` with credit **>= 5/6** (`TASK-104` §4d found this form *not* capped by `G06`); numeric-bin resolution (top decile `>= 12` contains `>= 14`) may lower attenuation; recorded | 2.3 |
| **P6** | FX-C suppression: `X = supplier=Atlas`-shaped, `Z = trip_duration` positively confounded with `X` and *beneficial* to `Y`, so adjustment *strengthens* harm (`H_Z >= 1.5 H_raw`); candidate reaches `SHADOW_POLICY` without the mechanism | **0 blocks; `SHADOW_POLICY` unchanged; `p_att`, `p_E` ~ 1.** Deterministic in sign. Failing this falsifies the design (S2) | 2.6 |
| **P7** | FX-D negative control (`Z` outcome-associated, unrelated to exposure; e.g. `party_size` for a `destination`-driven `T01`) | Not established, FWER-bounded; expected block rate `<= 0.05` per candidate | 2.4 |
| **P8** `[SUPPLEMENTED by P8r boundary cells, Section 9.4: the cells below have true D = 0.5H strictly inside the null, so this row cannot fail; original retained]` | FX-E null (no confounding, genuine effect, invented columns; `m` in {3,7,10,15}; effect from `~2 SE` to `~10 SE`; >= 2,000 simulated datasets per cell) | False-block rate `<= alpha_k1 = 0.10` in every cell (Bonferroni bound, worst case at the contract boundary); **predicted realized `<= 0.03` for effects `>= 3 SE`**. The no-correction mutant exceeds 0.10 for `m >= 7` | 2.4 |
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
  exposure. This proves the *declaration* correct for the benchmark; the mechanism never reads the generator. `[Rev 1: U13 tests declaration
  soundness, not independence; the declaration was written by someone who had read the generator, so a pass shows
  consistency with the truth, not that a customer-signed declaration would be sound. See 2.2 Rev 1 note and 9.5.]`

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
| **S1** `[Rev 1: also applies to the P8r boundary cells, Section 9.4]` | False-block rate in FX-E null exceeds `2 x alpha_k1 = 0.20` in any cell, or exceeds 0.10 in any cell with effect `>= 3 SE` | any | SE method or family definition is wrong -> stop, redesign (do not raise `alpha`) |
| **S2** | `T02`-type suppression fixture (P6) is blocked in any seed | any | the two-sided design is wrong -> stop |
| **S3** | Any of K2-K9 mutants survives (not caught) | any | a degree of freedom is unguarded -> add test or redesign |
| **S4** `[Rev 1: adds S4b numeric-Z resolution cell and the real-scale cell, Section 9.4]` | Power: on FX-A `s = 1.0` and `s = 0.8` the credited-cap rate is `< 5/6` seeds | either | the mechanism cannot deliver even its bounded guarantee at these sample sizes on the primary split -> **recommend abandoning** as specified; the pooled-split variant is a *new registered hypothesis* (Q1), not an in-place change |
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

> **[Rev 1: triaged and de-led.]** Each question carries a status: **OPEN** (founder decision), **PARTLY DECIDED** (by
> the cited ADR text; only the residual is open) or **IMPLEMENTATION DETAIL** (a design parameter pre-registered here,
> reported with a sensitivity, not a founder question). The original "Recommendation:" / "(recommended)" framings in Q1,
> Q2, Q3, Q7 are removed (the original wording is preserved in Section 9.8); options are stated with consequences, and the
> lead's view, where any, is recorded in Section 9.8 under a separate "author's view" line so it is not embedded in the
> question. New questions: **Q12** (A4 reading), **Q13** (undeclared dataset), **Q14** (oracle-informed declaration),
> **Q8b** (T01/T04 intent).

- **Q1 Evaluation split. [PARTLY DECIDED: ADR-101 A8 says "preferably the existing held-out validation split".]** Open
  residual: `validation` only vs pooled `validation ∪ future_holdout` (2x power; consumes the final split). Power table
  in 2.4 / 9.2.
- **Q2 Partial independence. [OPEN]** Accept the disclosed partial independence (`stability_credit_weight = 0.5` uses
  later-split raw sign; `G10`), or require an engine setting (`stability_credit_weight = 0`) for the graded version so the
  evaluation split is untouched by selection. The latter is an engine/accepted-default change (`ADR-070` binding), out of
  scope here.
- **Q3 The `pre_exposure_order` declaration. [OPEN for the tier content and the signer; the source A vs B choice is an
  IMPLEMENTATION DETAIL.]** Approve, amend or replace the tier proposal in 2.2 (an assumption, not a measurement; see the
  oracle-informed statement and Q14), name who signs it for the benchmark and for a customer. Source: A (manifest
  `validation_roles` `1.1.0`, new dataset version) or B (hash-recorded sidecar for the frozen `v1.1.0` dataset).
- **Q4 Diffuse confounding (the headline). [OPEN]** Two options with consequences. (a) Keep the bounded single-`Z`
  guarantee: a single `Z` can only be established as violating when it carries a majority of the bias (with the 0.50
  ceiling; see Q12 for whether that ceiling is permitted); diffuse confounding (`T05`-as-catalogued, equal exposure
  weights) is predicted not to be caught. (b) Open the joint-`Z` hypothesis `A7` reserves for "a proven case" — `T05`-as-
  catalogued is a candidate for that case (`TASK-104`: 6/6 reach `SHADOW_POLICY`; but see 9.4, P17: real-generator outcome
  shares are measured in Section 10). If opened, its form (pre-declared pairs `m(m-1)/2` checks; one pre-declared
  whole-pool joint check with its own coverage rule; ...) is a new hypothesis with its own multiplicity family. Separate
  sub-question: redefine the `TASK-105` regression targets for `T01`/`T05` to the FX-A forms, or keep the catalogued forms
  as expected-miss reports.
- **Q5 Class (ii). [OPEN; see also Q13.]** `A3` says limitation only; `ADR-100` decision 3(ii) says a conservative state,
  not silent promotion. As designed: `WARN` (visible, non-blocking, readiness unchanged). Alternative: a readiness
  consequence.
- **Q6 Error control. [PARTLY DECIDED: ADR-101 A7 requires one family with correction/control. IMPLEMENTATION DETAIL: the
  per-candidate family scope and Bonferroni. OPEN: the level.]** Level `alpha_k1` in {0.05, 0.10, 0.20}; the design
  pre-registers 0.10 with the other two as non-binding sensitivities. The stated equivalence with `fdr_alpha` is an
  analogy only (FDR over the search is not per-candidate FWER); per-test level at m=10 is 0.005.
- **Q7 Contract version. [PARTLY DECIDED: ADR-101 requires "no silent change to frozen validation contract behavior" and
  cites the contract-versioning precedents, so a version distinction is required.]** Open residual: bump to `1.4.0`
  (`ADR-064` precedent) or reuse the `G16` "no-bump" label (`TASK-081`); and whether `G17` is default-on for new runs,
  given the (revised) compatibility statement (3.3).
- **Q8 Catalogue/generator. [PARTLY DECIDED: ADR-101 catalogue/generator policy (do not auto-align; record
  specified != generated) fixes the catalogue part. The proposal to edit the code catalogue is WITHDRAWN (Rev 1, Section
  1/9.7); the correction lives in the manifest layer, which is an IMPLEMENTATION DETAIL.]** Open: **Q8a** whether
  `T02`'s `booking_month` intent justifies a *new benchmark version* (would exercise class (ii)); not proposed as a Phase 2
  action. **Q8b** whether `T01` (`party_size`, `trip_duration_days`) and `T04` (`destination`) were *intended* as confounders
  (=> generator fix, new benchmark version) or over-listed (=> `specified_not_realized` stays the record).
- **Q9 `G06` contract-text vs code gap. [OPEN, out of scope here.]** Text: adjusted interval excludes zero; E-value exceeds
  strongest measured confounder-outcome association. Code: neither. The design binds to the *executed* criteria. Decide
  whether to open a `TASK-070`-style reconciliation.
- **Q10 Stratification resolution. [IMPLEMENTATION DETAIL.]** Raw levels `<= 12` else deciles (single-`Z`), vs `G06`'s
  quartiles; pre-registered and disclosed; quartile variant reported as a sensitivity; the numeric-`Z` resolution cell
  (S4b, Section 9.4) tests it.
- **Q11 Suppression and unlocking. [PARTLY DECIDED: ADR-101 A9 says strengthening alone is not grounds for blocking and the
  Phase 2 contract is "block only if...".]** Residual: confirm that strengthened adjusted evidence never *unlocks* a
  candidate another gate blocked (block-only action).
- **Q12 (new) The A4 reading. [OPEN]** See Section 9.1 (M1) for both readings and their consequences.
- **Q13 (new) What an undeclared dataset does. [OPEN]** See Section 9.8.
- **Q14 (new) Oracle-informed benchmark declaration. [OPEN]** See Section 9.5/9.8.

---

## 7. Traceability to `ADR-101`

| Clause | Where satisfied |
|---|---|
| A1 scope: `k=1` on the promotion path only | 2.1 (`k>=2` -> vacuous PASS; `G16` untouched) |
| A2 admissible `Z` from a pre-declared pool; no mediators/colliders/target-derived | 2.2 (R1-R3 existing; R5 declared strict-precedence order; safe default = empty pool) |
| A3 no coverage veto; limitation in provenance; block only on positive evidence | 2.6, 2.8 (`WARN` states; `NOT_EVALUATED` not used; established-violation rule) |
| A4 no fixed percentage; same promotion contract | 2.6 (G06's executed criteria, existing thresholds; the 0.50 is the *contract's*, not a new parameter). **[Rev 1: this row asserted satisfaction; whether reusing the contract's 0.50 is what A4 permits is ambiguous. Not satisfied-by-assertion: founder question Q12, Section 9.1. G03/G04/G15 not recomputed on the adjusted estimate: 2.6 Rev 1 note.]** |
| A5 `G12` not credited | 2.7 |
| A6 attribution | 2.7 (counterfactual readiness; credited flag; distinct reason) |
| A7 pool fixed before candidates; one multiplicity family; single-`Z`; no post-hoc `Z` | 2.2-2.4 (`m` fixed by declaration; Bonferroni; spy test U2; mutants K3, K7) |
| A8 independent evaluation data | 2.5 (validation split; edges from development; partial independence determined from the code and disclosed) |
| A9 two-sided; `T02` suppression must not block | 2.6, P6, U5, K5, S2 |
| Catalogue/generator policy | 1 (no auto-alignment; **[Rev 1: catalogue-code edit withdrawn, manifest-layer record only; uniform `specified_not_realized`]**; generator change flagged, not proposed; `T03` stays a mediator) |
| Phase 2 contract: recompute, block only if the adjusted result violates the contract, record coverage and attribution | 2.6-2.8 |
| Design -> review -> implement; contract versioning; no silent change | 3, this document is 2a; independent design review precedes 2b; official grading only after |

## 8. What this design does not do

It does not implement anything; does not change the generator, catalogue, engine, gates, thresholds or the frozen
`TASK-102` bar; does not raise `D2` Part B (stays 2/5); does not touch `TASK-057`/outreach; does not claim protection
against diffuse, latent, or month-driven confounding; does not use `G12`'s incidental blocks as evidence; does not
schedule any grading run (a new grading cycle of the changed version is required afterward and is a separate task).

---

## 9. Revision 1 (2026-09-24): response to the independent adversarial design review

Status: **registered before any Revision-1 measurement was run.** The predictions in 9.4 are frozen by the commit that
introduces this section; Section 10 (measurements) is appended by a later commit and never edits Section 9.

### 9.0 Change log (finding -> disposition -> where)

| Finding | Verified against source? | Disposition | Where |
|---|---|---|---|
| **M1** A4 tension unsurfaced; G03/G04/G15 not recomputed | yes: A4 text ("no fixed percentage (no \"50%\")"), ADR-100 D1, `apply.py` G06 block (`attenuation <= max_adjusted_attenuation`) | **Turned into founder question Q12** (both readings + consequences); G03/G04/G15 analysis added | 9.1, 2.6 note, Q12 |
| **M2** oracle-informed declaration | yes: the author read `_generate_row` in Phase 1 (already partly disclosed, not carried into the claim) | **Fixed**: stated in design, required claim language, results-doc requirement; Q14 | 2.2 note, 9.5, Q14 |
| **S-a** 2.4 figures are 50%-power critical values | yes: `z_crit x SE(D)`; `SE(D)/SE_raw` was an assumption | **Fixed**: 80%-power recomputed, like-for-like comparison, assumption flagged and measured (Section 10), E-branch unpaired SE stated | 9.2 |
| **S-b** attribution contamination when coverage < 1 | yes: `_stratified_adjustment` returns the exposure-weighted effect over usable strata; `H_raw` from `split_stats` is over all rows | **Fixed by restricting the baseline to the usable strata** (`H_raw,U`); flagged as an estimand clarification, not a mechanism change | 9.3 |
| **S-c** S1/P8 cannot fail; boundary size unsimulated; E-branch conditioning | yes: P8 cells have no confounding | **Fixed**: interior cells relabelled, boundary cells P8r pre-registered and simulated; conditioning addressed | 9.4 (P8r), Section 10 |
| **S-d** P3 too loose, P5 conflicts with resolution caveat; no numeric-Z cell | yes, **and a larger defect found**: the fixture parameter `s` is a *weight* share, but the bias share is the *squared-weight* share (TASK-104's own measured curve 0.25->0.33, 0.5->0.78, 0.6->0.89, 0.7->0.98). P3's `s=0.4/0.5/0.6` counts were mis-modelled | **Superseded, originals preserved**: P3r, P5r-a/b, new S4b numeric-Z resolution cell | 9.4 |
| **S-e** "T05 four equal weights, s=0.25" unverified on outcome side | yes: Phase 1 B2 outcome-side Wald 1084/961/499/2569 | **Fixed**: reworded to "equal exposure weights; outcome shares unmeasured"; measured in Section 10 (P17) | summary item 11, 9.4 |
| **S-f** claim reads as clearance at low power | yes | **Fixed**: 80%-power floor in the required user-facing field; new reporting-only limitation reason | 9.5 |
| **C-a** invariant self-contradictory | yes | **Fixed**: restated (3.3) | 3.3 |
| **C-b** `NONE_V0` not byte reproduction; G16 pre-1.3.0 not modelled | yes: `contract.py` (`ValidationThresholds.version`, no G16 switch), `ROBUSTNESS_SEMANTICS_BY_CONTRACT_VERSION` | **Fixed** (3.4 note) | 3.4 |
| **C-c** catalogue edit changes generator output | yes, and stronger than stated: `test_default_config_still_reproduces_the_frozen_hidden_ground_truth` pins sha256 `5c41aab8...` as "a hard stop"; verified `sha256sum synthetic_data/evaluation/hidden_ground_truth.json` = that value | **Catalogue-code edit withdrawn**; correction moves to a manifest metadata layer that leaves generator output byte-identical | Section 1 note, 9.7 |
| **Catalogue policy consistency** T01/T04 silently reclassified | yes | **Fixed**: uniform `specified_not_realized`; T01/T04 intent is founder question Q8b | Section 1 note, 9.7 |
| **Questions** missing / leading / already decided | yes | **Fixed**: triage table, neutral framing, Q12-Q14, Q8b; alpha analogy note | Section 6, 9.8, 2.4 note |
| **Traceability** TASKS.md branch text stale | yes: design is on `main` (commit `7175f00`) | **Fixed by appended correction** (TASKS.md, append-only) | TASKS.md TASK-105 |

Disputes: **none** of the findings is disputed. Two are strengthened by evidence: C-c (the change would fail a repo test that
describes itself as a hard stop) and S-d (the fixture-parameter model error, which also affects P3's `s=0.4/0.5` rows, not only `s=0.6`).
Two items are **flagged as candidate mechanism-adjacent changes for the round-2 reviewer**: 9.3 (baseline restricted to usable
strata) and 9.5 (reporting-only `not_powered_for_single_z_violation` limitation, maps to `WARN`, cannot change a block
decision). If round 2 judges either a mechanism change, it reverts to the original text and is reported, not silently kept.

### 9.1 M1: the A4 tension ("no fixed percentage (no 50%)")

The design's violation criterion for attenuation is `H_Z < (1 - 0.50) x H_raw`, the same `max_adjusted_attenuation = 0.50`
that `G06` executes. Its own headline (summary item 11) says this makes a single-`Z` check a *majority-single-confounder
detector*. `ADR-100` D1 rejected "at least 50% of confounding must sit on `party_size`" as a `G06` implementation artifact,
and `ADR-101` A4 says "no fixed percentage (no \"50%\")". `G17` re-encodes a 50% boundary at the single-`Z` level. The
text is genuinely ambiguous between two readings; the design as written silently took the first.

| | **Reading R1: "the contract's existing 0.50 is acceptable"** | **Reading R2: "no attenuation percentage anywhere"** |
|---|---|---|
| A4 read as | "no *new bespoke* percentage; test against the *same, already-frozen* contract" | "the block criterion must be outcome-level (does the adjusted result still satisfy the contract's absolute bars?), never a share-of-effect-explained" |
| Violation hypotheses | sign + attenuation `<= 0.50` (`H0_att`) and E-value `>= 1.50` (`H0_E`), as in 2.4 | drop `H0_att`; block only on a *significantly* failed absolute bar: sign reversal, E-value `< 1.50` on the adjusted estimate (`H_Z < h_E`, about 100 EUR at `sd = 776`), and, if founder wishes, G04/G15 on the adjusted estimate (own family, own power cost) |
| Detects | a single `Z` carrying a majority of the bias (with a power margin); nothing about how much each of several `Z`s carries | only near-complete removal or reversal: `H_Z` significantly below an absolute bar; a `Z` carrying 40% or 70% of the bias is not, by itself, a reason |
| Real-scale consequence | the floors in 9.2; at delivered `n` even complete removal is under-powered when `H_raw <~ 2 x c80` | the E branch is applicable only when the raw baseline itself has `E >= 1.5`, i.e. `H_raw >= h_E ~ 100 EUR`; for raw effects below that (all three real-generator single-atom shifts, 28-54 EUR) **no E test exists**, leaving sign reversal only. Effectively inert on real-scale candidates below ~100 EUR |
| Predictions | P3r, P4r, P5r stand | P3r's `s=0.4/0.5/0.6` rows would not block (`a` must exceed about `1 - h_E/H_raw`, ~0.9 for fixture `H_raw = 400`, `h_E ~ 39`); P3r/P5r would need re-registration |
| Coherence with `G06` | `G17` and `G06` share one semantics; they differ in `Z` set (single vs joint), split (validation vs development) and multiplicity | `G17` would accept adjusted estimates that `G06` (which executes the 0.50 ceiling) would reject if it saw the same `Z`: two different meanings of "the same promotion contract" inside one validator |
| Risk | inherits the "majority-single-confounder" limit, disclosed | much weaker guarantee; the ceiling that `ADR-100` D1 objected to is gone but so is most of the power |

This is founder question **Q12**. The lead's view, kept out of the question text: R1 keeps one meaning of the contract across
`G06` and `G17`; R2 is closer to a literal reading of "no percentage" but removes most of the protection at the delivered
scale. Neither is chosen by this revision.

*Should "same promotion contract" also include `G03` (sample), `G04` (interval) and `G15` (materiality) on the adjusted
estimate?* The design recomputes only sign, attenuation and E-value. Analysis (also recorded in the 2.6 Rev 1 note): `G03` is
data-not-estimate (the evaluation `n_exposed` is reported and warned on); `G04` and `G15` on an adjusted estimate would make
"adjusted interval includes zero / adjusted impact below the bar" a block condition, which at the delivered power (9.2) is the
*default* outcome, i.e. the coverage-style veto `A3` forbids, unless it is framed as "significantly below the bar" (a
different, lower-power hypothesis with its own family). The unadjusted `G03`-`G05`, `G15` still run unchanged on the raw
estimate. The question of including them is part of Q12: **Q12(b)**.

### 9.2 S-a: corrected power arithmetic (arithmetic only; no simulation)

Definitions. Test statistic `D = H_Z - 0.5 H_raw` (paired). One-sided critical `z_c = Phi^-1(1 - alpha_k1/(2m))`
(`alpha_k1 = 0.10`): m=3: 2.128; m=7: 2.450; m=10: 2.576; m=15: 2.713. The **50%-power critical value** is `z_c x SE(D)`;
the **80%-power minimum detectable violation in D-units** is `c80 = (z_c + 0.8416) x SE(D)` (`z_c + 0.8416` = 2.97, 3.29,
3.42, 3.56). `SE(D) = rho x SE_raw`, `rho` *assumed* 0.55-0.70 (the original range; **measured in Section 10, P14**); the
`rho = 1.0` column is a no-benefit-from-pairing bound.

Corrected table (m = 10, validation split, `SE_raw` as in 2.4; units EUR):

| Trap | `SE_raw` | 50%-power critical value, `rho` 0.55 / 0.70 / 1.0 (the original "-55" etc. column) | **80%-power floor `c80`, `rho` 0.55 / 0.70 / 1.0** |
|---|---:|---:|---:|
| T01 | 35 | 50 / 63 / 90 | **66 / 84 / 120** |
| T02 | 36 | 51 / 65 / 93 | **68 / 86 / 123** |
| T04 | 34 | 48 / 61 / 88 | **64 / 81 / 116** |
| T05 | 59 | 84 / 106 / 152 | **111 / 141 / 202** |

(The original "approx. -55 / -56 / -52 / -90" correspond to `rho` about 0.6, at 50% power.) At `m = 7` the numbers are about
4% lower (T01: 63 / 81 / 115 at 80%).

**Like-for-like comparison.** The test statistic is `D = H_Z - 0.5 H_raw`; a violation "in expectation" is
`H_Z <= 0.5 H_raw - c`. The *shift* the original text compared against the floor is `S = H_raw - H_Z`. Detection at power P
therefore needs `S >= 0.5 H_raw + c_P`, not `S >= c_P`. The largest adjusted harm that would be detected 80% of the time is
`H_Z <= 0.5 H_raw - c80`; it is positive only if `H_raw > 2 x c80`:

| Trap | `2 x c80` (`rho` 0.55 / 0.70) | meaning |
|---|---:|---|
| T01 / T02 / T04 | about 128-136 / 162-172 EUR | if the raw effect is below this, **even complete removal of the effect (`H_Z = 0`) is detected less than 80% of the time** |
| T05 | about 222 / 282 EUR | same |

The real-generator raw effects (Phase 1 B3: -29.5, +9.4, -47.6, -73.7 EUR at 400k rows; delivered-data raw diffs -13.9 to -81.6
EUR) are all well below these thresholds. **So at the delivered sample size the mechanism cannot reach 80% power even against
total single-`Z` confounding of a real-scale trap effect.** (P2's conclusion "0 credited blocks" is strengthened, not weakened; the 2.4
sentence that the shifts "are below this detection floor" is replaced by this stronger statement.)

**E-value branch.** `h_E = pooled_sd x ln(1.125)/0.91 = 0.1294 x pooled_sd` (about 100 EUR at `sd = 776`). The branch tests
`H_Z` alone (unpaired, `SE(H_Z) ~ SE_raw`, not `rho x SE_raw`; pairing removes the shared sampling noise only in `D`, and here the
null is the fixed bar `h_E`, not a multiple of `H_raw`). It rejects only when `H_Z < h_E - z_c x SE(H_Z)`: at `SE_raw = 35`,
`m = 10`: `H_Z < 10` EUR at 50% power, `H_Z < -20` EUR at 80% power (sign reversal territory). It is **applicable only if the
observed raw baseline has `E >= 1.5`**, i.e. `H_raw,obs >= h_E ~ 100` EUR; for every real-scale single-atom trap effect (<= 74 EUR)
it is not applicable at all. That applicability is decided on the same data (conditioning), addressed by P8r cell B-E2.

**Real-scale versus fixture power.** The TASK-104 fixtures use outcome noise `sd = 250` (delivered margin `sd ~ 776`) and raw
harm 400 EUR, so `SE_raw` about 11 EUR, `SE(D)` about 6-8 EUR, and the block margin about 0.04-0.06 (fraction of `H_raw`).
Fixture results therefore demonstrate the mechanism at fixture signal-to-noise, **not at the delivered-data power of the table
above**. A real-scale cell (P18) is registered for 2b.

### 9.3 S-b: attribution contamination when coverage < 1 (estimand clarification)

`_stratified_adjustment` returns the exposure-weighted effect over **usable strata only** and a coverage share, while
`H_raw` from `split_stats` is over **all** rows. When coverage < 1, `D = H_Z - 0.5 H_raw` mixes "exclusion of the unusable
strata" with "confounding". The paired-attribution statement in summary item 5 (raw baseline on the same rows makes the
difference attributable to adjustment) is therefore only true at coverage 1.

**Revision (like-for-like baseline):** the baseline for `Z` is `H_raw,U`, the raw exposed-minus-comparison harm on the
rows of the **usable strata of `Z`** (the strata that clear `MIN_STRATUM_CELL = 5` in both arms; identical to `H_raw` when
coverage = 1). `D_att = H_Z - 0.5 H_raw,U`; the attenuation and the E-baseline applicability use `H_raw,U`; the full-sample
`H_raw`, `H_raw,U`, coverage and the exclusion contribution `0.5 (H_raw - H_raw,U)` are all recorded per `Z`. The paired
bootstrap resamples both from the same replicate. `H_Z` still comes from the real, unchanged `_stratified_adjustment`; the
usable strata are identified by an own cross-tab in the new module using the same `MIN_STRATUM_CELL` (the function does not
return them). Coverage `< 0.50` remains `not_assessable(coverage)` (unchanged). Justification for restricting rather than
dropping the paired-attribution claim: at coverage in [0.5, 1) the contamination is bounded but not negligible (measured for
every declared `Z` on the delivered data in Section 10, P15); restricting keeps the claim true at every coverage level at
the price of one more computed quantity. **Flagged for round 2:** this redefines the raw baseline inside the same mechanism
(same gate, pool, split, family, thresholds); it does not change what is blocked at coverage 1. It is not the contract's
`G06` baseline (`G06` has the same mixture but is coverage-gated at 0.50 and is unchanged).

### 9.4 Superseding pre-registered predictions (frozen by this commit; originals preserved in 4.1)

Common model (used for the fixture rows). In the `TASK-104` fixtures `score = sum_j w_j I_j` (weights normalised), `X ~
Bernoulli(0.03 + 0.62 score)`, `Y = base - A score + noise`. `X` and `Y` both load on the *same* weights, so the bias
contributed by indicator `j` is proportional to `w_j x (imbalance of I_j) ~ w_j^2 Var(I_j)`. With `Var(I_j)` about equal
(median splits, `HIGH_DESTINATIONS` 0.4) the **bias share** of `Z_j` is `b_j = w_j^2 / sum_k w_k^2`, not `w_j`. For weight
share `s` on `Z*` and `(1-s)/3` on each of the other three: `b(s) = s^2 / (s^2 + (1-s)^2/3)`. This model reproduces
`TASK-104`'s measured curve for `party_size` (`G06`, 4 confounders): `s`=0 -> 0.11, 0.25 -> 0.33, 0.5 -> 0.78, 0.6 -> 0.89, 0.7
-> 0.98 (model: 0.00, 0.25, 0.75, 0.87, 0.94; `G06`'s set also removes small shares of the others). The original P3 used `s`
as the bias share ("attenuation ~ `s` x resolution"), which is the defect.

Predicted single-`Z` attenuation `a(s)` (categorical `Z*`, exact resolution): **s=1.0: 1.00; 0.8: 0.98; 0.6: 0.87; 0.5: 0.75;
0.4: 0.57; equal weights (0.25): 0.25.** (Uncertainty +-0.08.) Fixture power: `H_raw = 400`, `SE_raw ~ 11`, `SE(D) ~ 6-8`,
`m = 10`: 50%-power block margin about 0.04-0.05, 80%-power about 0.06-0.07 in units of `H_raw`. A cell blocks reliably iff
`a(s) - 0.5 >~ 0.07`.

| ID | Object | Prediction | Basis / falsifier |
|---|---|---|---|
| **P3r** (supersedes P3) | FX-A, `Z* = destination` (`G06`-dropped), weight share `s`, seeds 101-106, validation-only | Credited caps: `s=1.0`: **6/6**; `0.8`: **6/6**; `0.6`: **6/6**; `0.5`: **6/6**; `0.4`: **boundary probe, point 5/6, range 2-6/6** (a = 0.57 vs threshold 0.50 + 0.05); equal weights (0.25, = P4r): **0/6**. `G17` disabled: `SHADOW_POLICY` in all. | The model above. **Falsifier of the model** (not necessarily of the mechanism): any of `s >= 0.5` below 6/6 with a measured `a > 0.6`; or `s=0.4` <= 1/6 with measured `a > 0.6`. The original P3 predicted `s=0.6`: 2-5 of 6, `s=0.5`: <= 3/6, `s=0.4`: 0/6 (mis-modelled: those cells have bias share 0.87 / 0.75 / 0.57) |
| **P4r** (rewords P4) | FX-B, equal exposure weights on all four indicators (`T05` as catalogued *in exposure*; `T01` four-equal fixture) | **0/6 blocked; `SHADOW_POLICY`.** Fixture bias share per `Z` about 0.25 (equal weights, equal variances). For the *real generator* the outcome side is **not** equal-weighted by evidence: outcome shares are unmeasured in the original; Phase 1 B2 outcome-side Wald: destination 1084 / party 961 / duration 499 / lead 2569 (see P17). "Four equal weights, `s = 0.25` each" is **withdrawn** as a statement about the real generator | additivity; equal `Var(I_j)` |
| **P5r-a** (supersedes P5, fixture form) | `T02`-type duration-only, the *TASK-104 fixture* (`DURATION_ONLY`; median-threshold indicator whose cut coincides with a decile edge) | **6/6** credited caps; measured resolution factor about 1.0 | edge coincidence; `a` about 1.0 |
| **P5r-b** (new, S4b numeric-Z resolution) | Generator-shaped numeric indicators with the *generator's* cut and *development-decile* bins: `booking_lead_days < 14` (dev edges `[4, 23, 35, ...]`) and `trip_duration_days >= 14` (dev edges `[2,4,5,...,10,12]`, top bin `[12, inf)`), `s = 1.0` (indicator alone drives X and Y), fixture noise and `H_raw = 400` | Measured resolution factor `r` (attenuation of a fully confounding indicator): **lead `r` in [0.70, 0.90] (design estimate 0.79); duration `r` in [0.55, 0.90]**. Credited-cap rate at fixture noise: **lead 6/6; duration >= 4/6** (a knife-edge case only if `r < 0.55`); if `r < 0.5` the cell cannot block by construction | measurement in Section 10 (P16). The original P5's `>= 5/6` for duration-only ignored the design's own resolution caveat |
| **P8r** (supplements P8) | Boundary cells, numpy replica of the mechanism as designed (`n = 2,462`, exposed share about 0.27, noise `sd = 776`, row-level paired bootstrap `B = 200`, >= 2,000 datasets per cell). **B-att**: one observed `Z1` with true attenuation exactly 0.50 (calibrated by population enumeration with an unobserved second confounder `U`), plus `m-1` null noise columns; `m` in {3,7,10}, `H_raw` in {100,200,400}. **B-E**: `H_Z = h_E` exactly (true direct effect = `h_E`, attenuation about 0.33, so `H0_att` interior), raw baseline `H_raw = 150`. **B-E2**: `H_raw = H_Z = h_E` (no confounding; the E branch is applicable only when the *observed* raw E >= 1.5, conditioning on the same data) | Unconditional block rate **<= alpha_k1 = 0.10 in every cell**; **realized about `0.05 x (number of boundary Zs) / m` per cell** (m=3: <= 0.017-0.02; m=10: <= 0.005-0.01) because `p_Z = 2 min(p)` and Bonferroni both divide; for the single boundary `Z`: `P(p_att <= 0.05)` in [0.035, 0.065], `P(p_att <= 0.01)` in [0.005, 0.02] (nominal, within Monte-Carlo error at 2,000). **B-E2** realized rate **<= the B-E rate** (conditioning on raw E >= 1.5 selects datasets with larger `H_raw`, hence larger `H_Z`, conservative) | **Falsifier (S1):** any boundary cell with block rate > 0.10; or per-`Z` `P(p_att <= 0.05)` outside [0.03, 0.07]. The interior null cells of P8 are relabelled "plumbing checks: true `D = 0.5 H` strictly inside the null, cannot exceed by construction unless the SE is grossly wrong" |
| **P14** (new) | `SE(D)/SE_raw` on the delivered validation split, every declared-pool `Z` x {T01, T02, T04, T05}, paired row-level bootstrap `B = 500`; and `SE(H_Z)/SE_raw` | `rho` in [0.55, 0.70] for **>= 80%** of pairs (median about 0.6); `SE(H_Z)/SE_raw` in [0.95, 1.30] | the assumption in 2.4; reported per pair, not summarised away |
| **P15** (new) | Contamination when coverage < 1, same pairs: `H_raw`, `H_raw,U`, coverage, exclusion term `0.5 (H_raw - H_raw,U)` | coverage < 1 in **>= 1** pair (thin strata for multi-level `Z`); `abs(0.5 (H_raw - H_raw,U)) <= 10 EUR` in **>= 90%** of pairs; maximum could reach 25 EUR | 9.3 |
| **P16** (new) | Resolution factor `r` of the design's binning on real `Z` columns (noise-free population: `Y = -A I`, `X` depends on `I` only, real `_stratified_adjustment`): lead<14, duration>=14, `party_size >= 5` (raw levels), `destination in {Tokyo, Zanzibar}` (raw levels), and the fixture median-threshold indicators | party and destination `r >= 0.99`; median-threshold indicators `r >= 0.95`; lead and duration as in P5r-b | 2.3 |
| **P17** (new) | Outcome-side single-`Z` attenuation shares in the **real generator** (400k rows from the real `_generate_row`; real `_stratified_adjustment`; design binning) for T05 (and T01, T04, T02): `a_Z = 1 - H_Z/H_raw` for each tier-0 `Z`; note that `H_raw` contains the genuine pattern effects | T05: **booking_lead_days is the largest** (`a` in [0.30, 0.65]); destination [0.10, 0.30]; party [0.08, 0.30]; duration [0.03, 0.20]; **max `a` < 0.5 with probability about 0.75** (i.e. P4-on-the-real-generator holds); sum of the four singles in [0.7, 1.1]. If any `a >= 0.5`, `T05` as generated has a majority single confounder and the "diffuse, not blocked" statement is wrong for the real generator, reported as such | Phase 1 B2 outcome-side Wald 2569 for lead vs 499 for duration |
| **P18** (new, executed in 2b, registered now) | Real-scale power cell on the *real* gate: fixture with `sd = 776`, `Z*` = destination, `s = 1.0`, `H_raw` in {100, 200, 400}, >= 30 seeds | Block rate per seed about **0.25-0.55 at `H_raw = 100`; >= 0.95 at 200 and 400** (`rho` 0.6-0.7, m=10) | 9.2; needed because 6 fixture seeds at `sd = 250` say nothing about real-scale power |

**New stop condition S4b.** On the numeric-`Z` resolution cell (P5r-b) with generator cut and decile bins and `s = 1.0`, credited-cap
rate `< 5/6` at fixture noise means the design's numeric stratification is inadequate for threshold-shaped confounders
(`r < ~0.55`). Consequence: the numeric-`Z` claim is withdrawn from the bounded claim (the claim then covers categorical /
low-cardinality `Z` only) and the resolution is re-specified as a new registered hypothesis; not tuned in place.
**S4 is unchanged** (categorical `s = 1.0, 0.8`, `< 5/6` = abandon as specified) and **S1** now also covers P8r boundary cells
(any > 0.10, or the per-`Z` calibration falsifier). If boundary cells cannot be run, the size at the contract boundary is
stated **unverified**, not implied by the interior cells.

### 9.5 M2 and S-f: what may be claimed, and the required user-facing text

**Oracle-informed declaration (required statement, verbatim in the results document and in any claim made from the
benchmark fixtures):** *"The pool declaration and tiering used for the benchmark fixtures were written by someone who had
read the generator. Fixtures passing under this declaration show that the mechanism works when the declarer knows the true
causal structure; they do not show that it works with a declaration signed by a customer, which can be wrong. The declaration
soundness test (U13) checks the declaration against the generator's data flow; it tests soundness, not independence."*

**Required claim/report field (supersedes the diagnostics-only placement of minimum-detectable-violation).** The user-facing
field, produced whenever `G17` is `PASS`/`WARN` on a declared `k=1` candidate:

> "No confounding was established by the N checked, pre-declared, pre-exposure variables (list) on later-period data.
> This is **not evidence that confounding is absent.** For each checked variable the check would detect (80% power) only a
> reduction of the estimated effect of at least X EUR per record (Y% of the observed effect); smaller reductions, and any
> diffuse confounding spread over several variables, would likely pass unnoticed. [If `0.5 H_raw,U - c80 <= 0` for a
> variable: 'For variable V the check could not have detected even complete removal of this effect at 80% power.'] Not
> assessed: (list, reason). Declared but unobservable: (list). Unknown latent confounding is outside this check."

Per `Z` the required fields are `c80_D_eur`, `min_detectable_shift_eur_80 = 0.5 H_raw,U + c80`, its percentage of
`H_raw,U`, and `detectable_at_80_percent_power` (boolean; false iff `0.5 H_raw,U - c80 <= 0`). `SE(D)` used is the paired
bootstrap value for that `Z`. **Reporting-only state:** if `detectable_at_80_percent_power` is false for **every** assessed
`Z`, the gate outcome is `WARN` with reason code `not_powered_for_single_z_violation` (so the caveat reaches
`report.warnings`, not only the diagnostics) instead of `PASS`. This adds a limitation category to the existing "WARN iff
any limitation exists" rule; it can never produce `FAIL`, never changes evidence level or readiness, and never changes which
candidates are blocked. **Flagged for round 2** as a reporting addition. At the delivered sample size most `k=1` candidates
with realistic effects will show this `WARN`; that is the honest state.

### 9.6 Versioning and invariant text

Superseded statements are marked where they occur: 3.3 (invariant restated), 3.4 (`NONE_V0` is gate-outcome reproduction,
not bytes; `1.0.0`-`1.2.0` -> `NONE_V0` records only "G17 absent", not reproduction of those gate ladders, because `G16` has
no switch). No number in Sections 3.1-3.2 changes.

### 9.7 Catalogue and generator: metadata layer (C-c) and uniform treatment

Verified consequences of the withdrawn code edit: `hidden_ground_truth.json` (sha256 `5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506`,
matches the pinned `FROZEN_HIDDEN_GROUND_TRUTH_SHA256`) is the direct serialization of `confounded_by`; editing the lists in
`synthetic_benchmark.py` (lines ~830-865) would change the regenerated bytes, fail
`test_default_config_still_reproduces_the_frozen_hidden_ground_truth` (documented there as a hard stop), change
`evaluation/checksums.json`, and, per `ADR-101`, be a benchmark identity change with the "no silent comparison with 2/7 and
the ceiling analyses" consequence. `tests/analytics/test_task105_generator_realization.py` (lines ~258, 519, 547) also pins
`intended_confounders` to the file's `confounded_by`.

**Adopted:** an additive metadata layer in `docs/benchmark/task-105-trap-manifests.json`: new per-trap fields
`authoritative_confounders` (realized), `specified_not_realized`, `mediated_by`, `test_negative_controls`; the existing
`intended_confounders` (= the frozen catalogue) is untouched; no generator or catalogue-code edit; all delivered artifacts and
checksums stay byte-identical.

| Trap | `authoritative_confounders` (realized) | `specified_not_realized` (catalogued, not in the generator's exposure logic; intent not inferred) | other |
|---|---|---|---|
| T01 | `destination`, `booking_lead_days` | `party_size`, `trip_duration_days` | `test_negative_controls`: same two (test-usage label only) |
| T02 | `trip_duration_days`; `destination` (diluting, uncatalogued) | `booking_month` | class (ii) not in the data |
| T03 | none | `customer_type`, `installments`; `discount_rate` catalogued as a confounder but generated as a *child* of the exposure | `mediated_by`: `discount_rate` (a mediator is not reclassified as a confounder, ADR-101) |
| T04 | `booking_lead_days` | `destination` | `test_negative_controls`: `destination` |
| T05 | all four | none | none |

The original dispositions "fix catalogue" for T01/T03/T04 are **withdrawn** as inferences of intent. Consistent rule: where the
catalogue lists a column the generator does not realize, record `specified_not_realized`; whether the intent was real is
founder question Q8b (and Q8a for `booking_month`).

### 9.8 Question triage, new questions, original wording

The triage is in Section 6. Original wording that was replaced: Q1 "Primary = `validation` only (recommended, follows
`ADR-101` wording, leaves `future_holdout` unconsumed)"; Q2 "Recommendation: accept and disclose."; Q3 "Recommendation: A
generally, B for the frozen benchmark."; Q7 "Bump to `1.4.0` (recommended; ...)"; Q4/Q6 as printed in the original section 6
(Q4: "Accept the bounded guarantee ..., **or** open the joint-`Z` hypothesis"; Q6: "confirm (or `0.05`)"). The lead's views
that were embedded there, kept here so they are separate from the questions: Q1 validation-only; Q2 accept and disclose;
Q3 source A generally, B for the frozen benchmark; Q7 bump to 1.4.0.

**Q12 (A4 reading; M1).** Which reading of ADR-101 A4 is intended: R1 (contract's existing 0.50 ceiling acceptable) or R2 (no
attenuation percentage anywhere)? Both, with consequences, in 9.1. **Q12(b):** should "same promotion contract" also include
`G03`/`G04`/`G15` on the adjusted estimate (each with the power cost stated in 9.1)?

**Q13 (undeclared dataset).** Undeclared => `A(C) = {}` => `WARN no_declared_causal_order`, promotion unaffected. That
is the state of **every existing dataset and customer** (none has a `pre_exposure_order`), so every existing `k=1` candidate that
reaches promotion does so with a WARN and no check. `ADR-100` D4(b) says a `k=1` candidate on the promotion path must either
be shown robust to the admissible confounders or **stop promotion with an explicit insufficient/confounded-evidence
reason**; `ADR-101` A3 says incomplete coverage is a recorded limitation, not an automatic veto. Options: **(a)** WARN, no
readiness change (as designed; treats "no declaration" as incomplete coverage under A3; leaves D4 satisfied only for declared
datasets); **(b)** cap `k=1` promotion at a reason-coded level (e.g. `experiment_only`) when there is no declaration,
literally D4(b); consequence: every `k=1` candidate on every existing dataset, including the frozen benchmark unless the
sidecar declaration is supplied, is capped, an intended recall cost that bites only where `k=1` reaches promotion (today:
never; P1b). This design does not choose. (Q5 covers only declared-but-unobservable class (ii), not this case.)

**Q14 (oracle-informed declaration).** Accept the benchmark fixtures as evidence of "works when the declarer knows the truth"
(the statement in 9.5), or require the benchmark tiers to be drafted independently (a person who has not read the generator
drafts them from `semantic_meaning` only; disagreements with the current tiers are reported) before any fixture result is
interpreted. Independent drafting would need to happen before any mechanism run.

**Q8b.** See Section 6.

### 9.9 Measurement plan for Section 10 (read-only, scratch scripts outside the repo tree)

(1) P14/P15 on the delivered validation split with the real `_stratified_adjustment` and a paired row-level bootstrap,
every declared-pool `Z` for T01/T02/T04/T05 (T03: empty pool). (2) P16 resolution factors, real `Z` columns. (3) P17
real-generator outcome shares at 400k rows. (4) P8r boundary cells with a numpy replica of the designed statistic
(validated against the real `_stratified_adjustment` on exported datasets before use). (5) Fixture-model check of the
`b(s)` curve with the real function on the fixture recipe (test-side recipe copied into scratch, not the repo tests).
No repository code, test, threshold or generated artifact is changed by any of these.

### 9.10 What Revision 1 did not change

The pool rule and tiers; single-`Z` only; the `validation` split and development-fixed bin edges; Bonferroni `alpha_k1 = 0.10`
per candidate and the two contract sub-criteria; the two-sidedness and attribution designs; the `1.4.0` bump and `NONE_V0`
concept; the frozen `TASK-102`/`ADR-100`/`ADR-101` texts; and no code, generator, catalogue or threshold.
