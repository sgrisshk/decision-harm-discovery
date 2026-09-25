# TASK-107 Phase 1 - Benchmark v2 specification and pre-registration

**Owner:** STATISTICS (lead), ARCHITECT (support). **Recorded:** 2026-09-25. **Status:** DRAFT SPECIFICATION for independent review; nothing here is frozen.
**Binding on:** `ADR-106` (read in full), `ADR-105`, `ADR-103`, `ADR-092`, `docs/benchmark/task-106-fn-autopsy.md` (with its R1-R5 corrections),
`docs/benchmark/task-108-scorer-trap-classification-spec.md` (section 7 disclosures, section 8 open item), `docs/benchmark/decision-gate.md`.

**Scope.** Document and read-only measurement only. No generator, scorer, engine, gate, threshold or v1 artifact was changed. The engine stays frozen
(`discovery-engine-v0.6.2`, `engine.py` sha256 `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`, validation contract 1.3.0, no `G17`).
**No engine was run on any v2 draw.** `P02` is not used as a proven defect (it remains "A versus B/D", TASK-106 5.3). v1 and its `2/7` are preserved and never rewritten.

**Evidence and process order (verifiable in `git log`).** Predictions and the unrun Jaccard script were committed first (`22f4b4d`); the Jaccard run and its outcome table followed
(`900b1cc`, `f67f4d2`); the oracle prototype script was committed unrun (`83bc106`) before its first execution. Predictions in `docs/benchmark/task-107-evidence/predictions-preregistration.md`
were not edited after being committed. Several were falsified; the outcomes are reported below and in `jaccard-sanity-results.md`, not hidden.

Evidence files (all under `docs/benchmark/task-107-evidence/`) with sha256 at the time of writing:

| File | sha256 |
|---|---|
| `predictions-preregistration.md` | `3a7d0e2e80ac59a1d0a1b80e074d15cd2e151eeef9cd0e4dbdbb36d33f444ee0` |
| `jaccard_sanity.py` | `96f5074628f67b930e7a5840ce9729f1647a2b3dc462837d58f2fc2eb061f891` |
| `jaccard-sanity-raw.json` | `5d0a8a0bc697f250e6b3aca9eb89c4b0eaf50b23136de873fe512d6194f43df2` |
| `jaccard-sanity-results.md` | `cee69380d67cfd9fae1d3beae3920e8f8779dab82c461dd7983cefd42b02129b` |
| `oracle_detectability.py` (final, post spawn-fix) | `217b3e0e312d08a4a4a5174fe7880d42a7d555de5df8173dd800462a234a6c65` |
| `oracle-rates.json` (v2 prototype, seeds 1001-1030; raw per-seed files in `oracle-raw/`) | `59a61992053e023875022b62f0f8cacd3dc844d9b39accde07efe59e24210fca` |
| `oracle-rates-v1only-no-targets.json` (raw in `oracle-raw-v1only-no-targets/`) | `47ac2df2b172181f70246341b891b9274e2ca05e859425b43701e8f1167ea4bd` |
| `make_tables.py` / `oracle-tables.md` | `a6ae9ca5...` / `95ac4bb7...` |

Inputs referenced: `synthetic_benchmark.py` `6ce81eb489580d2b8a81824b94d8fe868505b2027aa8b172af88e5ab323e8d52`; `evaluate_benchmark.py`
`13b141136e6cae78233f89311893d7402a2b09579937f61c34566b525e70930b`; `contract.py` `a55fdc94c7e520cc4e287c6627d345e5a2335bfc1bd684db584218790b7403cd`; v1 `hidden_ground_truth.json`
`5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506`; v1 committed analytical dataset identity `b6128eb3c1bdb36515c90570aa4ccabfc3dff8d1026d9002f1c832774b60a683`.

## 0. What ADR-106 already decided (not reopened here) and what it leaves open

Decided: engine frozen throughout; v2 is a benchmark-design task, not tuning; `P02` not used as a proven defect; recovery is never one number (Coverage/soft, Specific, Exact; headline
= Specific, separately from Coverage; Exact separately; formula and threshold "fixed in advance"); `Jaccard >= 0.5` not adopted without sanity analysis; no headline may again read "7/7" for
broad candidates partially overlapping targets; five invariants (oracle-detectable positives; consistent positive/trap definitions; discoverability matches engine language else labelled
out-of-language; discovery and safety measured separately; no tuning against engine results with everything frozen and independently reviewed before the first engine evaluation);
v1 and `2/7` preserved; `D2` Part B 2/5, the frozen TASK-102 bar and outreach unchanged.

Left ambiguous (each becomes an open decision in section 8): the "pre-set probability"; what "standard N" is (this document takes the v1 size, 10,000 rows, about 4,999 development rows, as the working meaning);
at which evidence level the oracle must "pass" (contract 1.3.0 makes promotion impossible for any k>=2 rule via `G16`, so the only reachable level is `predictive_association`);
who fixes the specific-recovery thresholds and how; whether v2 keeps v1's nine patterns inside the same dataset; how many positives are enough for the headline to have any resolution.

## 1. Benchmark identity and versioning

1. **Identifier.** `benchmark_id = "travel-v2"`; `benchmark_version` in the v2 ground truth is `2.x.y` (draft `2.0.0-draft`, frozen `2.0.0`). v1 is `travel-v1`, `benchmark_version 1.0.0` (dataset `travel-bookings-analytical-v1.1.0`
   identity above). v2 lives alongside v1 under a separate root (proposed `synthetic_data_v2/`), never replacing or regenerating a v1 file. The v1 generator, ground truth, checksums and dataset roots stay byte-identical (verifiable by the existing checksums).
2. **Results are never silently compared.** Every result artifact carries `benchmark_id`, `benchmark_version`, `ground_truth_sha256`, `scorer_sha256`, `engine_sha256`, `contract_version`. The Phase 2 scorer refuses (`SystemExit`) when the
   ground truth's `benchmark_id` differs from `--benchmark-id`, and writes `"comparable_to_other_benchmark_ids": false`. Any table mixing ids must be labelled per-row; a headline number is always printed as `travel-v2 / specific recall`,
   never bare.
3. **History ledger (append-only, quoted not restated).** v1: `2/7` lenient recovery for `v0.2.0`-`v0.5.0` and `v0.6.0` (45.2% economic-weighted); `7/7` lenient and 0 specific candidates for `v0.6.2` (TASK-103 run; TASK-106 D1, D2). These stay as recorded.
   ADR-106 withdrew the reading "29% discovery recall". v2 numbers start a new ledger.
4. **Dataset and generator identity.** Frozen manifest (section 7) records: v2 generator source sha256; the diff of the generator against `synthetic_benchmark.py` `6ce81eb4...` (the design keeps the same RNG draw sequence, so v2 covariates equal v1 covariates for equal seeds; verified here
   by a fidelity check, 0 of 10,000 rows differing with no targets); per-seed analytical `dataset_identity_sha256`; per-seed ground-truth sha256; scorer, oracle, threshold-config and seed-list hashes; engine sha256; contract version.
5. **Seed sets, disjoint by role.** Calibration seeds `C` (used to design; here 1001-1030, now spent for these target designs), acceptance seeds `A` (fresh, run once against the frozen code, no engine), engine-evaluation seeds `E` (fresh, run once).
   Counts are open (section 8, D4).

## 2. The five invariants as machine-checkable requirements

Notation: `P+` positive suite; `P-` ambiguous/underpowered stratum; `L` out-of-language challenge suite; `T` trap suite. Each check is a named function in the Phase 2 oracle module; a failing check blocks the freeze.

### Invariant (i) - every positive target is oracle-detectable

* **Oracle.** For a target `P` and seed `s`, the exact-condition oracle `O(P,s)` is the target's true conjunction expressed as real `Condition`s (eq/ge/lt on real columns, exact thresholds) and graded by the real, unmodified `run_validation` (contract 1.3.0)
  on that seed's analytical dataset with a fixed multiplicity family `M`. `pass(P,s) = 1` iff the level reaches `predictive_association` (v1 / TASK-028 recovery bar). Promotion cannot be the bar: `G16` returns unsatisfied for every k>=2 rule under contract 1.3.0.
* **Family and sensitivity.** Primary `M = 36,791` (the `TASK-103` evaluated-hypotheses count at `v0.6.2`); sensitivities `26,213` and `60,000` (the engine's real count on other draws was 34.8k-37.7k in TASK-106). Only G05 depends on `M`. Requirement C1: `passrate(P)` at the primary family
  meets the pre-declared threshold `tau` (OPEN, D1); C2: the rate at `M=60,000` is within `delta` of the primary (`delta` OPEN, proposal 0.10), so a target is not accepted on a family-size coincidence.
* **Certification uncertainty.** With `S` acceptance seeds and `k` passes, the requirement is on the one-sided 95% Clopper-Pearson lower bound `LB(k,S) >= tau_lb` (OPEN, D1/D4), not on the point rate. With zero failures the lower bound is `0.05^(1/S)`: `S=29` certifies `p>=0.90`, `S=59` certifies `p>=0.95`, `S=14` certifies `p>=0.80`.
  The 30 calibration seeds used here can therefore not certify anything above about 0.90 (observed `30/30` has Wilson 95% `[0.89, 1.00]`).
* **Separation of calibration and acceptance.** Target parameters may be adjusted only on `C`; the accepted status is measured once on fresh `A` with the frozen code (winner's-curse guard). Seeds in `C` are spent for any design already examined.
* **What the oracle does not certify.** It is an optimistic statistical bound for an idealised handed-the-rule check; it says nothing about whether search can find or rank the rule.

### Invariant (ii) - positive and trap definitions are consistent

* **C3 literal-disjointness (structural).** No positive's canonical rule contains any trap's `apparent_feature` literal. All ten new candidates below satisfy it by construction (no `manager=Manager 2`, `supplier=Atlas`, `acquisition_channel=paid_search`,
  `payment_method=bank_transfer`, `manual_exception=true`). Checked mechanically from the two rule grammars.
* **C4 carried overlaps.** v1 patterns whose rule contains a trap literal (`P03`/`T03`, `P04`/`T02`, `P06`/`T04`, `P05`/`T05`) are `overlap-carried`. They may sit in `P+` only under the explicit precedence semantics below **and** the separability check
  `J(A_P, E(L)) <= 0.30` (exposure Jaccard of the pattern's affected set with the bare-literal exposure; v1 real values: `P03` 0.122, `P04` 0.040, `P06` 0.044 from `jaccard-sanity-raw.json`).
  Policy for carried overlaps is open (D6: place them in `P+` under precedence, or in the `P-` "declared overlap" stratum so `P+` stays literal-disjoint).
* **Precedence semantics (resolves the TASK-108 section 8 open item).** For candidate `C` and trap `T` with literal `L`: `trap_hit(C,T)` iff `L` is a condition of `C` **or** `J(E(C), E(L)) >= theta_T` (exposure-equivalent reformulation; `theta_T` OPEN, proposal 0.90), **and not**
  `SPEC(C,P)` (section 3) for some `P` whose canonical rule contains `L`. The exemption is therefore keyed to **Specific** recovery, not to the lenient recall match. This closes the vacuous-threshold hole: every TASK-108 section-3 fixture
  (`bank_transfer AND lead<400`, `paid_search AND installments>=1`, `Atlas AND trip_duration>=1`, `bank_transfer AND lead<60`, `paid_search AND customer_type=new`) has exposure-J against its pattern of 0.195 or less (measured, `jaccard-sanity-raw.json`), so none is Specific and all stay trap hits.
  One measured boundary case is disclosed: `paid_search AND installments>=3 AND discount_rate>=0.03` has exposure-J 0.507 against `P03` (431 exposed, 333 affected) yet contains `discount_rate`, a `confounded_by` feature of `T03` that is not in `P03`'s rule.
  Under the proposed condition-precision floor (`Cp = 1`) it is not Specific and stays a trap hit; with `Cp >= 2/3` it would become a pattern recovery. The floor value is therefore load-bearing (D2).
* **Non-degeneracy of targets.** Every condition of a positive must be load-bearing: removing it grows the true exposure by at least `nu_design` (proposal 0.05, same `nu` as below), so no target is a trap literal plus a vacuous conjunct.

### Invariant (iii) - discoverability matches engine language (without changing the engine)

Engine language, read from the frozen code (recorded in the manifest, not assumed): `max_conditions = 3`; features are `DECISION_TIME` columns excluding `booking_date`/`travel_date` (so `booking_month` does not exist, `travel_month` does, as a numeric);
operators `eq` for categoricals with at most 12 levels, `ge`/`lt` at four dev-split quantiles (0.2/0.4/0.6/0.8) for numerics; at most one condition per feature. The atom grid is recomputed per draw from the development split (96 atoms on the committed draw).

* **L1** conditions <= 3. **L2** every feature in the engine feature set. **L3** operators expressible (categorical = eq; numeric = threshold; **no set-valued or calendar-decomposed atom**). **L4** at most one condition per feature.
* **L5 per-draw grid representability.** `build_projection` (the real, existing projection code) gives the tightest engine-expressible rule; requirement `Jaccard(projection, A_P) >= rho_rep` (OPEN, D2; proposal 0.80) **per seed**, with its own oracle pass rate (the "projection oracle").
  Measured lesson: pinning thresholds to the committed draw's grid is fragile. `N03` (`trip_duration_days>=10`) has median projection-J only 0.61 over the 30 draws although `ge 10` is a grid value on some draws, because the quantile grid moves with the draw. Representability is measured per seed, not asserted from one draw.
* **Classification.** Targets that pass L1-L5 and the oracle requirement are `P+`. Targets that pass the oracle requirement but fail L1-L5 are `L` (out-of-language challenge): reported in their own table with their own denominator, never in `P+`, never labelled an ordinary FN.
  Targets that fail the oracle requirement are `P-` regardless of language. The engine is not changed to make an `L` target expressible; expressibility is decided in the generator by choosing the rule.

### Invariant (iv) - discovery and safety measured separately

* Four suites with separate denominators, frozen at freeze time from the acceptance run: `P+` (recall denominator = number of `P+` targets scoreable in the seed), `L`, `P-` (never a denominator), `T` (own table).
* A target is scoreable in seed `s` iff `affected_n >= min_exposed_records (50)` and `n_dev >= min_n (40)` (v1's rule plus the engine's own floor; `P08` is scoreable in only 10 of 30 draws, measured). Scoreability is reported, not silently imposed.
* Discovery metrics (`coverage_recall`, `specific_recall`, `exact_recall`) are computed over `P+` only. Safety metrics (traps appearing, traps promoted, hard disqualifiers) are computed over `T` only. No blended score. Field names in the Phase 2 scorer never use bare `recall`.
* **Trap non-triviality (new, required by (iv), found by measurement).** A trap suite that cannot tempt the contract measures nothing. In this prototype the **bare-literal** rule of every trap reaches `predictive_association` in **0/30** draws
  (`T03` fails `G03` 30/30, `T04` 30/30; table in section 4.3), contradicting prediction B3. Rejecting such a trap says nothing about the safety gates. Requirement C5 (computed in Phase 2, not here): for each trap, over acceptance seeds, the best
  engine-language rule that **contains the trap literal** (depth <= 3, eligible, enumerated as in `jaccard_sanity.py`) reaches `predictive_association` in at least `tau_t` of draws (OPEN, D5). v1 history (TASK-073/083: `paid_search AND discount_rate>=0.03` reached `shadow_policy`) suggests literal-plus-confounder shapes can; this is not yet measured on v2.

### Invariant (v) - no tuning against engine results; custody

See section 7 (custody and commit protocol). Design provenance: targets, doses and thresholds were fixed from `P01`'s configured effect and the public engine language before any v2 draw and before any engine output on v2 (none exists).

## 3. Three recovery levels, declared in advance

### 3.1 Jaccard sanity analysis (done BEFORE the specific definition; `jaccard_sanity.py`, real v1 ground truth, committed dataset)

Two different Jaccards circulate and both were analysed. **Condition-set Jaccard** (the ADR-106 example) is syntactic; **exposure Jaccard** (TASK-106's "specific") is over rows.

* **The ADR pair is exact arithmetic:** truth of 4 conditions; "2 correct, nothing extra" = 2/4 = 0.5; "3 correct + 2 spurious" = 3/(3+2+4-3) = 0.5 (condition precision 1.0 vs 0.6, condition recall 0.50 vs 0.75).
* **On real data exposure-Jaccard does not conflate that pair, but only mildly separates it.** `P02` (4 true conditions, 137 affected): the six "2 true, nothing extra" rules have exposure-J 0.084-0.396 (median about 0.22); the 10,900 "3 true + 2 spurious" rules have median 0.103 and 3.5% at or above 0.5.
  Pre-registered prediction A2 (median gap > 0.2) was **not confirmed** (gap about 0.12). Condition-set Jaccard is nearly uninformative about exposure: at condition-set J = 0.5 on `P02` the exposure-J spans 0 to 1.0.
* **Dropping a true condition multiplies exposure 4-6x.** "2 of 3 true conditions, nothing extra" has exposure-J 0.171-0.275 on `P01`, 0.195-0.612 on `P03` (only `installments>=3 AND paid_search` reaches 0.612), see `jaccard-sanity-raw.json` for `P06`; the v0.6.2 candidate `CAND-005` (`booking_lead_days<23 AND discount_rate>=0.12`) is exactly this shape: exposure-J 0.261, condition precision 1.0, condition recall 2/3.
* **Enumeration of every engine-language rule (122,674 rules, depth <= 3; 108,236 pass an eligibility proxy).** Rules with exposure-J >= 0.3 / 0.5 / 0.7: `P01` 5/2/1; `P02` 11/0/0; `P03` 45/15/1; `P04` 0/0/0; `P06` 4/1/1; `P08` 10/2/1; `P09` 3/0/0.
  Specific-level rules exist for only four of seven scoreable patterns (prediction A4 said at most three and none for `P08`: falsified in part). Among the 15 rules at exposure-J >= 0.5 for `P03`, **12 contain an effective condition matching no true condition** (Cp < 1; e.g. `paid_search AND installments>=3 AND manual_exception=False`, J 0.596, recall 0.93, precision 0.62).
  So exposure-J alone does admit rules with a spurious condition.
* **Failure modes at the same J.** J >= 0.5 rules are "dilute" (recall >= 0.9, precision < 0.75; 15 rules) or "balanced"; **no** "partial" rule (precision >= 0.9, recall < 0.75) has J >= 0.5 anywhere (prediction A3 falsified). A dilute rule at exactly the threshold exposes about twice the affected set: the historical
  `P01` candidate `lead<23 AND discount>=0.08 AND BlueWing` has recall 1.0, precision 0.5, J 0.504. So `0.5` is a knife-edge, and on `P06` the historical precise rule's J 0.705 sits only 0.005 above a 0.7 threshold.
* **Real shapes.** All 15 `v0.6.2` run1 candidates have best exposure-J <= 0.086 except `CAND-005` (0.261), while lenient matches per candidate range 1 to 7 patterns (`CAND-004` matches all seven). Historical precise `P06` (`lead<23 AND Tokyo AND bank_transfer`): J 0.705, Cp 1, Cr 1. `P01` grid projection: J 0.947.
* **Vacuous and superset shapes.** Nine of ten TASK-108 fixtures have exposure-J <= 0.195 (prediction A6 said all under 0.2: the tenth, above, is 0.507). Condition-level precision/recall >= 2/3 alone accepts `bank_transfer AND lead<60` (exposure 1825 vs 3077 bare, J 0.073) and `paid_search AND customer_type=new` (1706 exposed, J 0.195): it rewards names and directions while ignoring a 5-13x dilution.

### 3.2 Alternatives compared (measured; illustration candidates from v0.6.2 were NOT used to select)

| Definition | Exact/grid-projection fixtures | Vacuous and bare-trap fixtures | Confounder-plus-literal (`paid_search AND installments>=3 AND discount>=0.03`) | Verdict |
|---|---|---|---|---|
| Lenient recall >= 0.5 (v1) | accept | accept all (also bare traps) | accept | Coverage only |
| Condition-set J >= 0.5 | accept | accepts 2 dilute fixtures | accept | rejected: syntactic, blind to 4-13x dilution |
| Condition precision and recall >= 2/3 | accept | accepts 2 dilute fixtures | accept | rejected for the same reason |
| Exposure J >= 0.3 | accept | rejects | accept | too permissive (P03 has 45 such rules) |
| Exposure J >= 0.5 | accept (incl. J 0.504 dilute rule) | rejects | accept (0.507) | admits a spurious confounder condition |
| Exposure J >= 0.7 | accept (P06 hist 0.705 barely) | rejects | reject | brittle near the historical precise rules |
| **Exposure J >= theta_J AND condition precision >= theta_p on effective conditions** (proposed) | accept | rejects | rejects at `theta_p = 1` | proposed |

### 3.3 Proposed definitions (formulas; thresholds marked OPEN where not derivable)

Let `C` be a candidate; `E(C)` its exposed rows on the full cohort (as the v1 scorer); `A_P` the affected set; `T_P` the canonical true conditions; `n = |E(C)|`.
**Vacuity.** For a condition `c` in `C`, removing it grows exposure by factor `g(c) = |E(C \ c)| / |E(C)|`. `c` is vacuous iff `g(c) - 1 < nu` (proposal `nu = 0.05`, OPEN). The **effective rule** `K(C)` drops vacuous conditions. Exposure-based metrics are unaffected (a vacuous
condition changes exposure by under `nu`), so `K` only matters for condition-level checks and trap literals: a candidate equal to a bare trap plus a vacuous condition reduces to the bare trap. **Match** `mu(c,t)`: same feature and nested marginal row sets (same direction, or same categorical value); thresholds are not compared (exposure carries threshold sloppiness).
`Cp(C,P) = |{c in K(C) : exists t in T_P, mu(c,t)}| / |K(C)|` (0 if `K` is empty). `Cr(C,P) = |{t in T_P : exists c in K(C), mu(c,t)}| / |T_P|`.

* **Coverage / soft recovery** (unchanged from v1): `recall(C,P) = |E(C) ∩ A_P| / |A_P| >= 0.5`. Reported as `coverage_recall`. Also reported: the number of patterns each candidate covers (a candidate covering 3 or more is flagged "broad").
* **Specific recovery:** `SPEC(C,P)` iff `J_e(C,P) = |E ∩ A| / |E ∪ A| >= theta_J` **and** `Cp(C,P) >= theta_p` **and** `K(C)` non-empty, **and** for headline purposes the candidate reaches `predictive_association` or above under the real validation.
  Proposal: `theta_J = 0.5`, `theta_p = 1.0` (no effective condition without a counterpart in the truth). Rationale: exposure-J measures localisation semantically (the ADR pair is not conflated at the row level); the precision floor closes the measured gap of spurious confounder conditions (12 of 15 J >= 0.5 rules for `P03`) and the trap-literal-plus-confounder shape;
  it needs no `Cr` floor because dropping a true condition already costs exposure-J. **OPEN (D2):** `theta_J` (0.5, with sensitivity 0.3/0.7 always reported), `theta_p`, `nu`. Each candidate is credited to at most one pattern (the one with highest `J_e`, ties lexicographic).
  Headline: `specific_recall = (number of P+ targets with a validated SPEC candidate) / |P+ scoreable|`, per seed, then aggregated over evaluation seeds with an interval.
* **Exact recovery:** `EXACT(C,P)` iff there is a bijection between `K(C)` and `T_P` (a declared in-language canonical form `T_P^` per target) such that each pair has the same feature and direction/value and, for numeric conditions, `|rows(c) Δ rows(t)| <= eta * |rows(t)|` (threshold-tolerance rule; proposal `eta = 0.15`),
  **and** `|E(C) Δ E(T_P^)| <= eps_x * |A_P|` (proposal `eps_x = 0.10`). Both are OPEN (D2). `L`-suite targets have no in-language canonical form, so Exact is not defined for them.
* **Reporting rules.** Three fields (`coverage_recall`, `specific_recall`, `exact_recall`) are always printed together with their denominators, per suite; `specific <= coverage` must hold for every candidate and target: `J >= 0.5` implies `recall >= 0.5`, so a violation (for any `theta_J >= 1/3`) is a scorer bug and a stop condition.
  No artifact may print a bare `N/N` for coverage; a headline reading "N/N" built from broad candidates that overlap several targets is forbidden (ADR-106). Sensitivity tables at `theta_J` in {0.3, 0.5, 0.7} are always attached.

## 4. The v2 target set design

### 4.1 Construction (prototype, not the frozen generator)

The prototype is the real `synthetic_benchmark._generate_row` source with one inserted hook (text substitution at import; nothing in the repository was modified). It consumes exactly v1's RNG draws, so v2 covariates equal v1's for equal seeds; targets only add to the same
loss / cancellation-logit / support-rate levers v1 patterns use. Fidelity: with no targets, 0 of 10,000 rows differ from the real generator (seed 20260813). **It is a design-time feasibility instrument.** The frozen v2 generator (Phase 2) must re-run every measurement.

Effect doses (fixed from `P01`'s configured effect before any draw; not tuned): `H` = 410 EUR additional cost / +1.05 cancellation logit / +0.75 support rate (= `P01`); `M` = 300/0.75/0.50; `L` = 240/0.50/0.30.
Candidate targets were drafted from the contract's own scale (P01/P06-like dose, prevalence about 1-3.5%), each with distinct literals, no trap literal, grid-aligned thresholds where a threshold is used, and 2 or 3 conditions:

| id | rule | dose | intended class |
|---|---|---|---|
| N01 | `customer_segment=corporate AND destination=Reykjavik AND booking_lead_days<23` | H | P+ (3 cond) |
| N02 | `product_category=premium AND acquisition_channel=partner AND discount_rate>=0.08` | M | P+ |
| N03 | `supplier=Cedar AND customer_segment=family AND trip_duration_days>=10` | H | P+ |
| N04 | `manager=Manager 6 AND destination=Rome AND installments>=2` | M | P+ |
| N05 | `customer_segment=corporate AND payment_method=wallet` | M | P+ (2 cond) |
| N06 | `destination=Lisbon AND acquisition_channel=referral` | M | P+ (2 cond) |
| N07 | `manager=Manager 7 AND acquisition_channel=direct AND trip_duration_days>=8` | H | P+ |
| N08 | `payment_method=card AND customer_segment=family AND installments>=3` | L | P+ |
| O1 | `destination=Rome AND customer_segment=family AND party_size>=5 AND product_category=premium` | H | L (4 conditions > max 3) |
| O2 | `manager=Manager 8 AND customer_segment=leisure AND booking_month IN [1,2,12]` | H | L (calendar atom not expressible) |

v1 patterns are carried into the same dataset unchanged (P01-P09), classified by the same mechanical rule (section 4.4).

### 4.2 Measured oracle detectability, calibration seeds 1001-1030 (30 draws)

Rates are passes at `predictive_association` under contract 1.3.0 with Wilson 95% intervals. "exact-cond" = the true conditions as real `Condition`s (the primary oracle); "ideal-atom" = the true membership as one boolean (`TASK-106`'s exact-rule oracle); "grid projection" = the tightest engine-expressible rule.
Columns for `M = 26,213` and `60,000` are in `oracle-tables.md`; `60,000` lowers several rates by 0-3 seeds.

| id | n_aff (median) | n_dev (median) | exact-cond oracle @36,791 | ideal-atom oracle @36,791 | grid-projection oracle @36,791 | proj. J (median) | cond oracle @60,000 | cond oracle @26,213 |
|---|---|---|---|---|---|---|---|---|
| P01 | 152 | 75 | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] | 0.92 | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] |
| P02 | 135 | 65 | n/a | 30/30 [0.89-1.00] | 19/30 [0.46-0.78] | 0.30 | n/a | n/a |
| P03 | 350 | 177 | 6/30 [0.10-0.37] | 30/30 [0.89-1.00] | 6/30 [0.10-0.37] | 1.00 | 6/30 [0.10-0.37] | 6/30 [0.10-0.37] |
| P04 | 86 | 44 | n/a | 0/30 [0.00-0.11] | 0/30 [0.00-0.11] | 0.12 | n/a | n/a |
| P06 | 129 | 64 | 22/30 [0.56-0.86] | 22/30 [0.56-0.86] | 19/30 [0.46-0.78] | 0.68 | 20/30 [0.49-0.81] | 23/30 [0.59-0.88] |
| P08 | 54 | 26 | 0/10 [0.00-0.28] | 0/10 [0.00-0.28] | 0/10 [0.00-0.28] | 0.93 | 0/10 [0.00-0.28] | 0/10 [0.00-0.28] |
| P09 | 122 | 57 | n/a | 0/30 [0.00-0.11] | 0/30 [0.00-0.11] | 0.25 | n/a | n/a |
| N01 | 120 | 59 | 17/30 [0.39-0.73] | 18/30 [0.42-0.75] | 14/30 [0.30-0.64] | 0.98 | 15/30 [0.33-0.67] | 18/30 [0.42-0.75] |
| N02 | 351 | 179 | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] | 1.00 | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] |
| N03 | 173 | 88 | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] | 27/30 [0.74-0.97] | 0.61 | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] |
| N04 | 106 | 53 | 0/30 [0.00-0.11] | 0/30 [0.00-0.11] | 0/30 [0.00-0.11] | 1.00 | 0/30 [0.00-0.11] | 0/30 [0.00-0.11] |
| N05 | 163 | 82 | 13/30 [0.27-0.61] | 14/30 [0.30-0.64] | 13/30 [0.27-0.61] | 1.00 | 12/30 [0.25-0.58] | 17/30 [0.39-0.73] |
| N06 | 271 | 138 | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] | 1.00 | 30/30 [0.89-1.00] | 30/30 [0.89-1.00] |
| N07 | 165 | 85 | 26/30 [0.70-0.95] | 0/30 [0.00-0.11] | 25/30 [0.66-0.93] | 1.00 | 23/30 [0.59-0.88] | 27/30 [0.74-0.97] |
| N08 | 339 | 171 | 22/30 [0.56-0.86] | 29/30 [0.83-0.99] | 22/30 [0.56-0.86] | 1.00 | 22/30 [0.56-0.86] | 22/30 [0.56-0.86] |
| O1 | 108 | 55 | 24/30 [0.63-0.91] | 24/30 [0.63-0.91] | n/a | - | 23/30 [0.59-0.88] | 24/30 [0.63-0.91] |
| O2 | 155 | 77 | n/a | 0/30 [0.00-0.11] | 0/30 [0.00-0.11] | 0.25 | n/a | n/a |

Observations (measured, not tuned away):

1. **Only four targets exceed 0.95 observed at 30/30:** `P01`, `N02`, `N03`, `N06` (Wilson lower bound 0.89). `N07` 26/30, `O1` 24/30 (language-excluded), `N08` 22/30, `P06` 22/30, `N01` 17/30, `N05` 13/30, `P03` 6/30, `N04` 0/30.
2. **Predictions:** of the pre-registered bands, `N02`, `N03`, `N06`, `N07`, `N08`, `O1` fell inside; **`N01` (predicted >= 0.85, observed 0.57), `N04` (predicted 0.3-0.85, observed 0/30, gates `G12` 28, `G05` 22, `G03` 9), `N05` (predicted 0.6-1.0, observed 0.43), and `O2` (predicted >= 0.8 as an ideal atom, observed 0/30)
   were falsified.** Prediction B3 (bare `T03`/`T04` reach predictive in >= 50%) was falsified: 0/30 for all five traps. B1 (coarse discrete thresholds do worse) is mixed: `N04`, `N08`, `N02` differ (`N02` 30/30), so it is not supported as a general rule. B2 (projection within 10 points of exact for grid-aligned targets) holds except `N01` and `N03` at the edge (`N03` 27 vs 30).
3. **The ideal-atom oracle has an artifact and must not be the primary oracle.** `N07` is 0/30 as an atom (G12 fails 30/30) but 26/30 as real conditions; `N04` and `O2` atoms fail G12 30/30 as well. `P03` is the reverse (atom 30/30, real conditions 6/30 on G12). The atom oracle is optimistic for some targets and pessimistic for others, so it is used only where no real-condition form exists (`P02`, `P04`, `P09`, `O2`), and `O2`'s 0/30 is not a reliable estimate (needs a proper derived-column oracle in Phase 2).
4. **Coupling between targets.** With the ten targets present, `P03`'s real-condition oracle falls from 15/30 (v1-only replication, same seeds, no targets) to 6/30; `P01` 28/30 -> 30/30; `P06` 25/30 -> 22/30. Adding targets that share rows and levers changes the detectability of other patterns.
   Acceptance must be measured on the final composite generator, not per target. (Different comparison-group composition is a candidate cause; the cause was not isolated.)
5. **Grid fragility (invariant iii).** Projection Jaccard medians: `N03` 0.61 (0.92 for `P01`, 0.68 `P06`); the grid moves with the draw.
6. **Only 30 seeds:** an observed 30/30 cannot certify 0.95 (section 2, certification).

### 4.3 Trap suite measurement

Bare-literal trap rules through the same contract (same 30 draws; family 36,791; identical at 26,213 and 60,000):

| trap (bare literal) | reaches predictive | level-2 gate failures (of 30) |
|---|---|---|
| T01 `manager=Manager 2` | 0/30 | G03 30, G04 28, G05 30, G10 26, G12 30 |
| T02 `supplier=Atlas` | 0/30 | G03 30, G04 26, G05 30, G10 14, G12 16 |
| T03 `acquisition_channel=paid_search` | 0/30 | G03 30, G04 29, G05 30, G10 25, G12 24 |
| T04 `payment_method=bank_transfer` | 0/30 | G03 30, G04 26, G05 30, G10 25, G12 19 |
| T05 `manual_exception=true` | 0/30 | G03 23, G04 18, G05 30, G10 24, G12 12 |

Reading: at the standard N the contract rejects every bare trap on plain power/uncertainty grounds, before any confounding gate is relevant. A trap suite of bare literals is therefore not a test of safety logic (section 2, invariant iv, C5). The literal-plus-confounder forms the engine actually emits were not enumerated here (cost); C5 specifies the computation.

### 4.4 How targets are classified, and how v1 reuse is explained without cherry-picking

Mechanical, pre-declared rule (applied identically to every v1 and v2 pattern; the result depends on `tau` (D1), which is not chosen here): (1) L1-L5 fail -> `L` if the statistical oracle passes, else `P-`; (2) oracle requirement fails -> `P-`; (3) overlap-carried -> per D6; (4) otherwise `P+`.
No v1 pattern is deleted: each stays in the ground truth and in the report in whichever stratum the rule places it.

Illustrative placement of the measured rates only (not a choice of threshold; counts are `P+` candidates by exact-cond oracle at 36,791, in-language, literal-disjoint, and excluding overlap-carried `P03`, `P06`):

| If tau were | P+ members (point estimates) |
|---|---|
| 0.95 | P01, N02, N03, N06 (4) |
| 0.85 | + N07 (5) |
| 0.70 | + N08 (6), plus overlap-carried P06 (0.73) if D6 allows |
| 0.50 | + N01 (7) |

`P01` enters because it passes every listed tau; `P06` is borderline and overlap-carried; `P03` fails (0.20). `P02/P04/P08/P09` are not in-language or are 0/30 (`P02`: 4 conditions plus `booking_month`, projection J 0.30 -> `L` if its atom pass rate of 30/30 is accepted, with the atom-oracle caveat). `P05` and `P07` remain structurally unscoreable exactly as in v1.
That `P01` is the only v1 pattern in `P+` at strict tau is a consequence of the rule, not a selection.

### 4.5 Prior-knowledge risk (mirrors TASK-099 section 7)

The authors know the following before drafting: `v0.6.2` returned 15 broad candidates on v1 and 0 specific matches; `P01` is oracle-detectable in 61/61 draws, `P06` marginal, `P04/P08/P09` undetectable; the engine's atom grid and `max_conditions = 3`; the trap gates. This can bias the design in two directions
(targets shaped toward categorical 2-3 condition rules the engine can plausibly express; or away from them). Mitigations: doses fixed from `P01`; thresholds and rules committed (git) before any v2 draw was measured; targets chosen from the oracle contract, never from engine output on v2 (none exists); prior predictions recorded and partly falsified; calibration seeds separated from acceptance seeds.
**Un-removable residual:** the authors' choice of which ten rule shapes to write down is informed by that prior knowledge. A reviewer weighing the eventual result should treat the target set as "designed by people who know v0.6.2's behaviour on v1".

## 5. Pre-registered predictions and interpretation (before any engine run on v2)

Engine: unchanged `v0.6.2`. Evaluated once on evaluation seeds `E`, blind-workspace protocol, on frozen v2. Quantities: `C` = coverage recall, `S` = specific recall (validated), `X` = exact recall, all over `P+`; `Tp` = number of traps promoted (hard disqualifier, unchanged from `decision-gate.md`).

**Author's predictions, recorded now.** (1) `S` at most 0.35 (probability about 0.70); `S >= 0.70` probability at most 0.15. Basis: on v1 the engine returned broad candidates with no specific match. Counter-consideration: v2 `P+` targets are larger-effect, mostly categorical, low-order; the engine could do better. (2) `C` at least 0.80. (3) `X` at most 0.10.
(4) `Tp = 0`. (5) `S <= C` for every candidate and target (a violation is a scorer bug, not a finding). (6) the candidate pool again contains a broad candidate matching at least 3 `P+` targets by coverage.

**Interpretation table (cutoffs proposed; founder-confirmable before freeze, D9).**

| Observation on `P+` | Reading |
|---|---|
| `S >= 0.70`, `Tp = 0` | the old `2/7` largely characterised the benchmark (undetectable/ambiguous targets), not pure discovery capability, for the in-language oracle-detectable regime |
| `0.35 < S < 0.70` | mixed: some in-language, oracle-detectable targets are lost; per-target first-failure autopsy is required before any conclusion; do not average away |
| `S <= 0.35` and `C >= 0.70` | real discovery problem of a **localisation / selection** kind: signal is covered by broad rules but not specified (matches the v1 `TASK-106` finding); not a power problem, because the oracle passes |
| `S <= 0.35` and `C < 0.70` | real **detection** problem for oracle-detectable targets |
| `S` and `C` both high but `X` low | the engine finds them with threshold/condition variants; exact is a representation question, report separately |
| `S > C` anywhere | stop: scorer bug |
| `Tp >= 1` | hard disqualifier as in `decision-gate.md`, reported separately from discovery |

**Specific-vs-coverage divergence.** A large gap `C - S` means candidates overlap targets without localising them; it is the exact pattern ADR-106 withdrew "7/7" for. It is read as a localisation finding, never as recovery.

**Stop conditions.** Engine sha256 or contract version differs from the manifest; any frozen file hash differs; an accepted `P+` target fails the oracle in more than the pre-declared share of `E` seeds (the acceptance no longer holds: v2 evaluation is paused, results are not used to modify design); any scorer invariant violated (`S > C`, a candidate credited to two patterns); leakage; any run repeated selectively.
**What invalidates v2 (benchmark version withdrawn, new version required):** any generator/oracle/scorer/threshold/seed change after the freeze commit; design edits informed by engine output on v2; acceptance seeds reused for engine evaluation; a discovered scorer or oracle defect that changes any verdict; the frozen generator differing from the one measured.
v2 results never revise the v1 record; the `TASK-102` frozen bar and `decision-gate.md` bands are not applied to v2 unless the founder adopts them (D10).

## 6. Residual risks

1. 30 calibration seeds are few; the four best targets are only bounded below by 0.89 (section 2).
2. The prototype is not the frozen generator; every number must be re-measured on frozen code and fresh seeds. The v1-only replication batch used the pre-fix script version (`83bc106`), which did not register targets under `spawn`, and is retained as the no-target run.
3. The ideal-atom oracle is unreliable for `G12` (section 4.2 item 3); `O2` is unmeasured.
4. The engine's atom grid is draw-dependent (section 2 iii), so grid-aligned thresholds are not guaranteed.
5. Promotion is impossible for k>=2 rules (`G16`), so the positive suite cannot test promotion; safety of promoted findings remains untested for positives.
6. Target coupling (section 4.2 item 4); composite acceptance required.
7. Traps are not tempting in bare form (section 4.3); the trap suite may be uninformative without extension.
8. Prior-knowledge risk (section 4.5); single synthetic domain (travel); the "standard N" is inherited, not justified.
9. The scorer's trap logic under the proposed precedence is specified here but not implemented or tested (Phase 2).
10. `P02` is not treated as a defect; its L classification depends on the atom oracle's caveat.

## 7. Custody and commit protocol (invariant v; mirrors the blind-benchmark protocol and TASK-099 sections 10 and 13)

1. **F0** this specification (Phase 1): independent `CODE_REVIEWER` review against `ADR-106` and the code. Founder resolves the open decisions in section 8 in a dated `ADR` **before** F1.
2. **F1** implementation on a dedicated branch: v2 generator (proposed as an additive hook with no new RNG draws), oracle module (checks C1-C5, L1-L5), scorer changes (three recovery fields, precedence semantics, benchmark-id guard), threshold config, seed lists. No engine access.
3. **F2** acceptance run on fresh seeds `A`, no engine. Output: per-target pass rates with lower bounds, language checks, classification into `P+`, `P-`, `L`, `T`. Independent reviewer re-runs from the commit and reproduces every number.
4. **F3 freeze.** A single commit adds `benchmark-v2-freeze-manifest.json` (sha256 of generator, per-seed ground truth and dataset identity, scorer, oracle module, threshold config, seed lists, engine `fefceeaac20e8ff7...`, contract 1.3.0, this document) and a signed tag. The commit hash is recorded by the reviewer, not written into the manifest (TASK-099 chicken-and-egg). After F3 only an append-only, dated errata section is allowed; any other change creates version `2.1` with its own acceptance run.
5. **F4 first engine evaluation** is authorised only by a new `TASK`/`ADR` after F3 review. Blind workspace with allowlist, signed candidate commitment receipt (existing `blind_isolation`); ground truth opened only after commitment. One run per seed in `E`; no re-run except documented infrastructure faults; no selective reporting; results appended to a v2 ledger.
6. Roles: STATISTICS authors; CODE_REVIEWER independently verifies F0, F2, F3; a coordinator (not the author) runs F4; nobody who saw F4 output edits F1 artifacts.

## 8. OPEN FOUNDER DECISIONS (neutral; none is chosen here)

| # | Decision | Options and consequences (measured where possible) |
|---|---|---|
| D1 | Oracle-detectability probability `tau` (and `tau_lb`, `delta`) | 0.80: 5 in-language targets pass on the calibration point estimates (4.4), certifying needs `S >= 14` seeds with zero failures; 0.90: 4, needs `S >= 29`; 0.95: 4, needs `S >= 59`. Higher `tau` shrinks `P+` (coarser headline: 4 targets = 25% steps) and lowers the chance the engine is asked about hard targets; lower `tau` keeps more targets but admits ones that fail the oracle 10-20% of draws, which contaminates "FN" readings. `tau` must not be picked from the table above. |
| D2 | Specific and exact thresholds | `theta_J` 0.3 / 0.5 / 0.7 (0.5 accepts twice-dilute rules such as J 0.504; 0.7 sits 0.005 under a historical precise J 0.705); `theta_p` 1.0 vs 0.67 (0.67 turns `paid_search AND installments>=3 AND discount>=0.03` into a recovery); `nu` 0.05; `eta` 0.15; `eps_x` 0.10; `rho_rep` 0.80; `theta_T` 0.90. Not derivable from first principles. |
| D3 | Target count and mix | Number of `P+`, `L`, `P-`, trap targets; fewer than about 8 `P+` gives recall steps of 12.5% or more. Include designed boundary targets (dose `L`, small n) or only clear ones. |
| D4 | `N` and seeds | Keep 10,000 rows (about 4,999 development) or enlarge (raises detectability of all targets and changes v1 comparability); sizes of `C`, `A`, `E`; certification math in section 2; cost is about 5 minutes wall per calibration seed with 10 processes for about 60 oracle validations x 3 families. |
| D5 | Trap suite | Reuse `T01`-`T05` (measured: bare rules never reach predictive; C5 unmeasured) or extend with traps built to have a real non-null association at the standard N; extending changes covariate weights (no new RNG draws needed) and is a new design. |
| D6 | Overlap-carried patterns (`P03`, `P04`, `P06`, `P05`) | (a) in `P+` under precedence semantics and the separability check; (b) in `P-` "declared overlap" stratum so `P+` is literal-disjoint. (a) keeps more of v1; (b) makes the structure clean and avoids relying on the scorer. |
| D7 | Recovery evidence level | `predictive_association` (the only level reachable at k>=2 under `G16`) or something higher (unreachable for all rules under contract 1.3.0). |
| D8 | Primary multiplicity family | 36,791 (v0.6.2 count) vs 60,000 (conservative); this moves `N01`, `N05`, `N07`, `P06` rates by up to 3 seeds of 30. |
| D9 | Interpretation cutoffs (0.35 / 0.70 / 0.70) | Confirm or replace before freeze; they encode ADR-103's "roughly 30%" reading. |
| D10 | Whether v2 results enter `decision-gate.md` bands or the TASK-102 bar | Default here: no. |
| D11 | v2 dataset composition | v1's nine patterns and five traps inside the v2 dataset (as prototyped; coupling observed) or a new-only dataset with v1 preserved separately. |
| D12 | Fresh-seed acceptance for any target changed after this document | Required here; the founder may relax. |

ADR-106 ambiguities restated for the decision record: unspecified probability; "standard N"; evidence level; who fixes the specific thresholds; whether v1 patterns coexist inside v2; minimum size of `P+`.

## 9. Reproduction

```sh
uv run python docs/benchmark/task-107-evidence/jaccard_sanity.py                                   # ~4 s
uv run python docs/benchmark/task-107-evidence/oracle_detectability.py fidelity                    # 0 differing rows
uv run python docs/benchmark/task-107-evidence/oracle_detectability.py batch --seeds 1001 1030 --dir docs/benchmark/task-107-evidence/oracle-raw --procs 10   # ~25 min wall
uv run python docs/benchmark/task-107-evidence/oracle_detectability.py rates --dir docs/benchmark/task-107-evidence/oracle-raw --out docs/benchmark/task-107-evidence/oracle-rates.json
uv run python docs/benchmark/task-107-evidence/make_tables.py
```
