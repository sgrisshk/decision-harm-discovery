# TASK-107 Phase 1 - Benchmark v2 specification and pre-registration

**Owner:** STATISTICS (lead), ARCHITECT (support). **Recorded:** 2026-09-25. **Status:** DRAFT SPECIFICATION for independent review; nothing here is frozen.
**[Rev 1] 2026-09-25 (STATISTICS, documentation-only, responding to independent review "APPROVED WITH REVISION NEEDED"):** corrections and tightenings are marked inline `[Rev 1]`; the change log is section 10. No code, generator, scorer, engine, gate, threshold, v1 artifact, raw evidence, `predictions-preregistration.md` or `ADR-*` was changed; no OPEN founder decision was chosen. Two claims of the first draft were false and are corrected: the RNG/covariate-identity claim (sections 1.4, 4.1, 4.2 item 4, 7) and the `specific <= coverage` invariant (sections 3.3, 5).
**[Rev 2] Phase 2a (STATISTICS lead, ARCHITECT support), after `ADR-107` (founder decisions D1-D13; the ADR text is dated 2026-09-28, the same ledger-date caveat as section 10.2 applies): the specification constants are now fixed (section 8.1); this revision is dated, additive and inline-marked `[Rev 2]`, with the change log in section 11. Status: constants frozen in this document; the BENCHMARK itself is NOT frozen (F3 pending). Phase 2a also delivered executable, tested v2 code (scorer, RNG-isolated generator skeleton) and the C5 measurement (section 11.2); no engine or discovery run took place on any v2 draw, the engine stays frozen (`discovery-engine-v0.6.2`, `engine.py` sha256 `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`, contract 1.3.0, no `G17`), and `predictions-preregistration.md` is not edited.**
**[Rev 4] Phase 2b (2026-09-30/2026-10-01, STATISTICS lead, ARCHITECT support), after `ADR-108` (Decisions 1-3: tau as a one-sided 95% Clopper-Pearson lower bound at 30/30; C5 executed and disclosed, not a gate; no trap exemption for unscoreable/NOT ASSESSED targets).** Implements `ADR-108` Decision 3 in the scorer (`benchmark_v2_scoring.py`: `Target.assessed`, `trap_provenance`, `PROV_EXEMPT`/`PROV_CONFIRMED`/`PROV_UNSCOREABLE`/`PROV_NOT_ASSESSED`); pre-declares the Core/Challenge/DECLARED_OVERLAP classification rule, seed ranges, the optional-stopping ban and a bounded dose-selection procedure (`docs/benchmark/task-107-evidence/rev4-preregistration.md`, committed before any calibration run); designs 20 new v2 targets (12 intended Core, 6 intended Challenge, 2 DECLARED_OVERLAP) on the RNG-isolated composite generator (`synthetic_benchmark_v2_targets.py`); calibrates on 30 fresh seeds (2001-2030, disjoint from 1001-1030 and from any future acceptance/final seeds) at family 60,000 primary with the real contract, plus sensitivities 36,791/26,213 and C5 re-run on the composite for reference. Result (section 12, this revision): **14 of the 20 targets reach calibration verdict `core_candidate` (30/30, CP-LB 0.905 >= 0.90)** under the pre-declared mechanical rule — exceeding the >= 8 requirement — including two (`C06`, `H01`) that were *designed* as Challenge candidates but reclassified up by outcomes alone, per the pre-declared "outcomes decide, never intention" rule. One DECLARED_OVERLAP target (`D01`) is oracle-qualified (30/30, C4 bare-trap-literal exposure-J <= 0.30 on every seed); the other (`D02`) is not (18/30). Disclosed prior-knowledge risk: a design pilot on spent seeds 9001-9010 (before the pre-declaration commit) showed every manager-literal design fails G12 (leave-one-manager-out) structurally; all Core candidates therefore avoid the `manager` feature, a structural (not an engine-output) exclusion, stated here. No engine or discovery run occurred on any v2 draw in Phase 2b. Phase 2c (fresh acceptance seeds, freeze, independent review) is NOT started by this revision.**
**Binding on:** `ADR-106` (read in full), `ADR-105`, `ADR-103`, `ADR-092`, `docs/benchmark/task-106-fn-autopsy.md` (with its R1-R5 corrections),
`docs/benchmark/task-108-scorer-trap-classification-spec.md` (section 7 disclosures, section 8 open item), `docs/benchmark/decision-gate.md`.

**Scope.** Document and read-only measurement only. No generator, scorer, engine, gate, threshold or v1 artifact was changed. The engine stays frozen
(`discovery-engine-v0.6.2`, `engine.py` sha256 `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`, validation contract 1.3.0, no `G17`).
**[Rev 1] No discovery search was run and no engine candidate output was produced or read on any v2 draw.** (The first draft said "No engine was run on any v2 draw"; that was imprecise.) Engine-package and TASK-106 code that *was* called on v2 draws, verified by reading the imports of `oracle_detectability.py`: the atom-grid builder `_atoms` with the default `DiscoveryConfig()` (`oracle_detectability.py` line 166), TASK-106's `build_projection` and `parse_true_rule` from `scripts/diagnose_oracle_decomposition.py` (the body of `build_projection` calls none of the search/beam/eligibility helpers that module imports), and the real `run_validation` (through `_validate_rules`) on the true rules. `jaccard_sanity.py` calls `_atoms` and `DiscoveryConfig` on the committed v1 dataset only. `N03`'s projection-J 0.61 is a `build_projection` output; it used no engine candidate output. `P02` is not used as a proven defect (it remains "A versus B/D", TASK-106 5.3). v1 and its `2/7` are preserved and never rewritten.

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
| [Rev 1] `rev1-predictions.md` (committed `a4deb82` before the script was run) | `d22443590b6ff652fb64bdf7885ad713f47b4029722048ab6ec45ef3b4ea6a96` |
| [Rev 1] `rev1_check.py` (read-only, reads committed raw JSON) | `df9b742caf5488bd7610737af206edf9d1d5e3f73362fa44314c2cdf94b1a06f` |
| [Rev 1] `rev1-check-output.txt` | `14db8e91e5de989936c3e953da2bb8143c1724a2974289333f42b9622f9192fb` |

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
4. **Dataset and generator identity.** Frozen manifest (section 7) records: v2 generator source sha256; the diff of the generator against `synthetic_benchmark.py` `6ce81eb4...`; per-seed analytical `dataset_identity_sha256`; per-seed ground-truth sha256; scorer, oracle, threshold-config and seed-list hashes; engine sha256; contract version.
   **[Rev 1] Correction.** The first draft said the design "keeps the same RNG draw sequence, so v2 covariates equal v1 covariates for equal seeds". That holds only with **no targets** (fidelity check: 0 of 10,000 rows differ, seed 20260813). With targets present it is false: `synthetic_benchmark.py` draws `scaled_uniform(rng, 0.82, 1.0, ...)` for `refund_ratio` (line 419) and `rng.randint(2, 75)` for the refund date (line 429) **only when `cancellation` is true**; a target raises the cancellation logit, changes which rows cancel, so the number of draws consumed per row changes and every later row's covariates change. Measured (`rev1_check.py`, seeds 1001-1030, `oracle-raw/` vs `oracle-raw-v1only-no-targets/`): `n_affected` differs in **115 of 120** (pattern, seed) pairs for `P01/P02/P03/P06` (170 of 180 including `P04`, `P09`); seed 1001: `P03` 369 vs 350, `P01` 179 vs 163, `P02` 133 vs 141, `P06` 129 vs 125. A v2 dataset at seed `s` is therefore **not** the v1 dataset at seed `s` plus targets, and the manifest must not claim covariate identity or v1-dataset reproducibility for v2 (see section 7, F1).
5. **Seed sets, disjoint by role.** Calibration seeds `C` (used to design; here 1001-1030, now spent for these target designs), acceptance seeds `A` (fresh, run once against the frozen code, no engine), engine-evaluation seeds `E` (fresh, run once).
   Counts are open (section 8, D4).

## 2. The five invariants as machine-checkable requirements

Notation: `P+` positive suite; `P-` ambiguous/underpowered stratum; `L` out-of-language challenge suite; `T` trap suite. Each check is a named function in the Phase 2 oracle module; a failing check blocks the freeze.

### Invariant (i) - every positive target is oracle-detectable

* **Oracle.** For a target `P` and seed `s`, the exact-condition oracle `O(P,s)` is the target's true conjunction expressed as real `Condition`s (eq/ge/lt on real columns, exact thresholds) and graded by the real, unmodified `run_validation` (contract 1.3.0)
  on that seed's analytical dataset with a fixed multiplicity family `M`. `pass(P,s) = 1` iff the level reaches `predictive_association` (v1 / TASK-028 recovery bar). Promotion cannot be the bar: `G16` returns unsatisfied for every k>=2 rule under contract 1.3.0.
* **Family and sensitivity.** Primary `M = 36,791` (the `TASK-103` evaluated-hypotheses count at `v0.6.2`); sensitivities `26,213` and `60,000` (the engine's real count on other draws was 34.8k-37.7k in TASK-106). Only G05 depends on `M`.
  **[Rev 1] Provenance and ADR-106 invariant 5.** `36,791` is the engine's own `v0.6.2` evaluated-hypotheses count on v1 (`TASK-103` run; also reproduced in the `TASK-101` entry, `TASKS.md` about line 8779): an **engine-output-derived quantity used as the oracle's multiplicity family**. `26,213` is likewise an engine count, from the earlier-engine runs on the same v1 dataset (`TASK-064`/`TASK-069`, `TASKS.md` about lines 2302, 3361, 3805, 3911). ADR-106 invariant 5 forbids tuning against engine results on v2 (none exists); using a v1-run count as a family size is not that, but it is engine output entering the oracle, and it is disclosed here so a reviewer can judge it. Sensitivity `60,000` is the only sensitivity not derived from an engine run; D8 is the founder's choice among them (unchanged). Requirement C1: `passrate(P)` at the primary family
  meets the pre-declared threshold `tau` (OPEN, D1); C2: the rate at `M=60,000` is within `delta` of the primary (`delta` OPEN, proposal 0.10), so a target is not accepted on a family-size coincidence.
* **Certification uncertainty.** With `S` acceptance seeds and `k` passes, the requirement is on the one-sided 95% Clopper-Pearson lower bound `LB(k,S) >= tau_lb` (OPEN, D1/D4), not on the point rate. With zero failures the lower bound is `0.05^(1/S)`: `S=29` certifies `p>=0.90`, `S=59` certifies `p>=0.95`, `S=14` certifies `p>=0.80`.
  The 30 calibration seeds used here can therefore not certify anything above about 0.90 (observed `30/30` has Wilson 95% `[0.89, 1.00]`).
  **[Rev 1] Two different bounds, do not mix.** The interval columns in section 4.2 are **two-sided Wilson 95%** (`30/30` gives lower bound 0.886). The certification requirement above is the **one-sided 95% Clopper-Pearson** lower bound (`30/30` gives `0.05^(1/30) = 0.905`). They differ by about 0.02 at `30/30`; a target "certified" under one is not thereby certified under the other, and the manifest must name the bound used.
* **Separation of calibration and acceptance.** Target parameters may be adjusted only on `C`; the accepted status is measured once on fresh `A` with the frozen code (winner's-curse guard). Seeds in `C` are spent for any design already examined.
  **[Rev 1] If a target fails its acceptance run on `A`:** it may be redesigned, but the redesign is a design edit informed by `A`, so `A` is spent for it; the redesigned target needs a new, fresh acceptance set `A'` (and, because targets couple through shared rows/levers, section 4.2 item 4, any change to any target requires the composite generator to be re-accepted on fresh seeds). Each redesign therefore costs a fresh seed set (about 5 minutes wall per seed with 10 processes, D4); the number of permitted redesign rounds is not fixed here.
* **What the oracle does not certify.** It is an optimistic statistical bound for an idealised handed-the-rule check; it says nothing about whether search can find or rank the rule.
* **[Rev 2] Constants (`ADR-107` D1, D4, D8, D12).** `tau = 0.90`; primary multiplicity family **60,000** (independent of any engine output; the engine-derived `36,791` and `26,213` are no longer acceptance inputs and may appear only as labelled continuity sensitivities); `N = 10,000`; calibration, acceptance and final-evaluation seed sets each >= 30, **fresh and disjoint** (`1001-1030` are spent for the Phase 1 target designs); seed counts may be increased, never decreased after results are seen; fresh acceptance seeds are not relaxed (D12). Pinned reading of `tau` (flagged for the reviewer, consistent with the certification requirement above and with ADR-107 D1's remark that 0.95 is costly to certify): `tau` is applied to the **one-sided 95% Clopper-Pearson lower bound**. Failures allowed at `LB >= 0.90` (computed): `S = 30`: 0; `S = 45`: 0; `S = 60`: 1; `S = 90`: ~~3~~ **4 [Rev 3 correction: at `S = 90`, 3 failures give LB 0.9161 and 4 failures give LB 0.9012, so 4 are allowed; full table in 12.2]**. So 30 acceptance seeds require 30/30. C2 (rate at another family within `delta` of the primary) is moot with a single primary family; no `delta` is needed.

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
  **[Rev 1] Pinned reading: the exemption uses the metric part of `SPEC` only.** `SPEC(C,P)` in section 3.3 has a validation clause "for headline purposes". For the trap exemption the clause is **not** applied: `C` is exempt from `trap_hit(C,T)` iff `J_e(C,P) >= theta_J` and `Cp(C,P) >= theta_p` and `K(C)` is non-empty for some `P` whose canonical rule contains `L`, regardless of `C`'s validation level. Reason: the exemption classifies what the candidate *is* (a localised rediscovery of `P`, not a bare-trap exposure); tying it to validation would let sampling noise in the evidence level flip a candidate between "pattern" and "trap" across seeds. Safety is not weakened by this because the hard disqualifier concerns promoted traps (`Tp`), and no `k>=2` candidate can be promoted under `G16`. The alternative reading (exempt only if validated `SPEC`) is stricter, would flag every un-validated precise rediscovery as a trap hit, and is noted as the reviewer's alternative; it can be substituted before freeze without touching any other definition.
  **[Rev 2] Superseded by `ADR-107` (author pin): the STRICT reading is adopted.** A candidate is exempt from `trap_hit(C, T)` only if the metric match (`J_e >= theta_J`, `Cp >= theta_p`, non-empty `K`) holds for some target whose rule contains `L` **and** `C` reaches `predictive_association` or above; geometric similarity to a positive never cancels trap semantics on its own. The Rev 1 metric-only reading above is kept as history. Implemented in `benchmark_v2_scoring.score` and tested (unvalidated precise `P06` stays a `T04` hit; validated exact `P06` is exempt; the ten TASK-108 shapes never exempt at any evidence level). Consequence noted, not softened: the exact `P04` rule with `booking_month=12` has exposure-J below 0.5 against `P04` (one month of three) and stays a `T02` hit.
* **Non-degeneracy of targets.** Every condition of a positive must be load-bearing: removing it grows the true exposure by at least `nu_design` (proposal 0.05, same `nu` as below), so no target is a trap literal plus a vacuous conjunct. **[Rev 1]** Vacuity is defined precisely (sequential, tie-broken) in section 3.3; the design check must be run with that same procedure so that `K(T_P) = T_P` for every target (otherwise a candidate equal to the truth would lose a true condition from `K` and could not satisfy the Exact bijection).

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
  **[Rev 1] C5 is a gated FREEZE-CHECKLIST blocker (FC1, section 7).** Until C5 (the literal-plus-confounder rule check) is computed on acceptance seeds and meets `tau_t`, the trap suite **as defined cannot test safety logic**: the bare-literal rules are rejected on power grounds before any confounding gate applies (section 4.3), so a "no trap promoted" result on such a suite would be uninformative. No freeze (F3) and no engine evaluation (F4) may proceed with C5 uncomputed; D5 is the founder's choice between reusing `T01`-`T05` (if C5 passes) and extending the suite (if it does not).

### Invariant (v) - no tuning against engine results; custody

See section 7 (custody and commit protocol). Design provenance: targets, doses and thresholds were **chosen** and committed (git) before any v2 draw was measured and before any engine output on v2 (none exists). **[Rev 1]** The first draft said the doses were "fixed from `P01`'s configured effect" / "derived"; that overstated it. Only the high dose `H` equals `P01`'s configured effect. `M` (300 EUR / +0.75 logit / +0.50 support) and `L` (240 / +0.50 / +0.30) are arbitrary fractions of `H` (about 0.73/0.71/0.67 for `M`, 0.59/0.48/0.40 for `L`: the ratios are not consistent across the three levers), chosen by the authors, not derived from any rule.

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
**[Rev 1] Vacuity procedure (pinned).** The per-condition definition above, applied to all conditions at once (simultaneous), can drop two mutually redundant conditions that are each individually vacuous (removing either alone changes exposure by under `nu`, but removing both changes it a lot), leaving `K` empty or wrong. The pinned procedure is **sequential**: compute `g(c)-1` for every condition of the current rule; if none is below `nu`, stop; otherwise drop the single condition with the smallest `g(c)-1` (ties broken by canonical order feature name, then operator, then value), and repeat on the reduced rule. Of two mutually redundant conditions exactly one is dropped. Consequence to be aware of: a genuinely true but weak condition whose removal grows exposure by under 5% is also dropped from `K`. That is harmless for Specific (`Cp` counts effective conditions that match, so dropping a true one cannot lower `Cp`, and `J_e` is exposure-based) but it **can break the Exact bijection** (`K` then lacks a true condition). This is why the design-time non-degeneracy check (section 2, invariant ii) requires every true condition of a target to be load-bearing at `nu`.
`Cp(C,P) = |{c in K(C) : exists t in T_P, mu(c,t)}| / |K(C)|` (0 if `K` is empty). `Cr(C,P) = |{t in T_P : exists c in K(C), mu(c,t)}| / |T_P|`.

* **Coverage / soft recovery** (unchanged from v1): `recall(C,P) = |E(C) ∩ A_P| / |A_P| >= 0.5`. Reported as `coverage_recall`. Also reported: the number of patterns each candidate covers (a candidate covering 3 or more is flagged "broad").
* **Specific recovery:** `SPEC(C,P)` iff `J_e(C,P) = |E ∩ A| / |E ∪ A| >= theta_J` **and** `Cp(C,P) >= theta_p` **and** `K(C)` non-empty, **and** for headline purposes the candidate reaches `predictive_association` or above under the real validation.
  Proposal: `theta_J = 0.5`, `theta_p = 1.0` (no effective condition without a counterpart in the truth). Rationale: exposure-J measures localisation semantically (the ADR pair is not conflated at the row level); the precision floor closes the measured gap of spurious confounder conditions (12 of 15 J >= 0.5 rules for `P03`) and the trap-literal-plus-confounder shape;
  it needs no `Cr` floor because dropping a true condition already costs exposure-J. **OPEN (D2):** `theta_J` (0.5, with sensitivity 0.3/0.7 always reported), `theta_p`, `nu`. Each candidate is credited to at most one pattern (the one with highest `J_e`, ties lexicographic).
  Headline: `specific_recall = (number of P+ targets with a validated SPEC candidate) / |P+ scoreable|`, per seed, then aggregated over evaluation seeds with an interval.
* **Exact recovery:** `EXACT(C,P)` iff there is a bijection between `K(C)` and `T_P` (a declared in-language canonical form `T_P^` per target) such that each pair has the same feature and direction/value and, for numeric conditions, `|rows(c) Δ rows(t)| <= eta * |rows(t)|` (threshold-tolerance rule; proposal `eta = 0.15`),
  **and** `|E(C) Δ E(T_P^)| <= eps_x * |A_P|` (proposal `eps_x = 0.10`). Both are OPEN (D2). `L`-suite targets have no in-language canonical form, so Exact is not defined for them.
* **Reporting rules.** Three fields (`coverage_recall`, `specific_recall`, `exact_recall`) are always printed together with their denominators, per suite; `specific <= coverage` is checked only under the guarantee stated next. **[Rev 1] Corrected.** The first draft said "`J >= 0.5` implies `recall >= 0.5`, so a violation (for any `theta_J >= 1/3`) is a scorer bug". That was wrong: `J = |E ∩ A| / |E ∪ A| <= |E ∩ A| / |A| = recall`, so `J >= theta` implies `recall >= theta` and nothing more; there is no `1/3` implication. `S ⊆ C` (every Specific target is also Coverage) is guaranteed **only for `theta_J >= 0.5`**, the Coverage recall threshold. At the `theta_J = 0.3` sensitivity setting a candidate with `J = 0.35` and `recall = 0.4` is Specific but not Coverage, so `S > C` there is legitimate arithmetic, not a scorer bug. Pinned reading: (1) the `S <= C` invariant and its "stop, scorer bug" consequence apply to the primary table and to any sensitivity at `theta_J >= 0.5`; at `theta_J < 0.5` the sensitivity table reports `S` and `C` but does not apply the stop rule (or, equivalently, defines `S` there over the Coverage-qualified subset and labels it so). (2) The Specific check uses the **same candidate pool** (all candidates emitted in the run, after the scorer's trap-exclusion step) and the **same exposure rows** `E(C)` on the full cohort as Coverage; the validation clause only removes candidates from `S`, so it cannot create `S > C`; the one-pattern-credit rule (highest `J_e`) applies to Specific, whereas Coverage credits every pattern with `recall >= 0.5`, which also cannot create `S > C` at pattern level for `theta_J >= 0.5`.
  No artifact may print a bare `N/N` for coverage; a headline reading "N/N" built from broad candidates that overlap several targets is forbidden (ADR-106). Sensitivity tables at `theta_J` in {0.3, 0.5, 0.7} are always attached.
  **[Rev 2] Constants and pins from `ADR-107` (D2, D3, D6, D7 and the author pins).** `theta_J = 0.50`, `theta_p = 1.00`, `nu = 0.05`, `eta = 0.15`, `eps_x = 0.10`, `rho_rep = 0.80`, `theta_T = 0.90`, Coverage recall `0.5` (unchanged). Exact is a strict diagnostic, not a mandatory headline denominator. **Strata** (never blended; each with its own denominator and headline): **Core** (reliably detectable, oracle-qualified; Core Recall), **Challenge** (deliberately borderline targets; Challenge Recall), **DECLARED_OVERLAP** (intentional trap-literal overlap, own metric; never in headline Specific Recall), plus the spec's out-of-language `L` suite when present. **Recovery wording (D7):** results are worded "N/M benchmark targets reached `predictive_association` under the v2 recovery contract", never "N/M patterns recovered by the product"; this is not promotion. **Sequential vacuity with Exact bijection (pin):** Exact requires the bijection between the candidate's RAW conditions and the target's canonical in-language conditions BEFORE any vacuity relaxation; a candidate that matches only after vacuous conditions are dropped is reported as `exact_after_vacuity` and is never counted as Exact, and the truth's own conditions are never relaxed, so removing a weak true condition can never silently turn near-exact into exact. Additional scorer pins made while implementing (flagged for the reviewer; none changes a constant): (a) credit is to the single highest-`J_e` scoreable target (ties: target id), the Specific test is applied to that target only, other metric-matching targets are reported in `specific_metric_also_holds_for`; (b) one shared candidate pool: every candidate that is not a genuine (non-exempt) trap hit feeds Coverage, Specific and Exact, and Coverage does not require validation; (c) `mu(c, t)` additionally requires compatible direction (`ge`/`ge`, `lt`/`lt`, `eq`-or-`in` with `eq`-or-`in`) and non-empty nested row sets (without it a vacuous `lt` would "match" a true `ge`); (d) the trap exemption may use any target containing the literal, including unscoreable ones (e.g. the exact `P05` rule exempts `T05`) while credit uses scoreable targets only; (e) `theta_J` sensitivities {0.3, 0.5, 0.7} are always computed, and the primary constant is always scored as well.

### 3.4 [Rev 1] Sensitivity of Specific to `theta_p`, measured on the committed v1 draw

Counts are read from `jaccard-sanity-raw.json` (`enumeration.per_pattern[*]`, all 122,674 engine-language rules, depth <= 3; field `with_spurious_effective_condition(Cp<1)`); no new computation. "Survive" = rules at the stated exposure-J floor that also have `Cp = 1` (`theta_p = 1`).

| pattern | rules at J >= 0.5 | of which Cp < 1 | survive `theta_p = 1` (J >= 0.5) | rules at J >= 0.3 | of which Cp < 1 | survive `theta_p = 1` (J >= 0.3) |
|---|---|---|---|---|---|---|
| P01 | 2 | 0 | 2 | 5 | 1 | 4 |
| P02 | 0 | 0 | 0 | 11 | 9 | 2 |
| P03 | 15 | 12 | **3** | 45 | 41 | 4 |
| P04 | 0 | 0 | 0 | 0 | 0 | 0 |
| P06 | 1 | 0 | 1 | 4 | 1 | 3 |
| P08 | 2 | 0 | 2 | 10 | 5 | 5 |
| P09 | 0 | 0 | 0 | 3 | 3 | 0 |

Reading: under `theta_p = 1` only **3 of the 15** `P03` rules at J >= 0.5 survive (12 of 15 have `Cp < 1`, as stated in section 3.1); `theta_p` therefore changes the number of Specific-eligible rules for `P03` five-fold, and by little for the other patterns. Rules at J >= 0.7 were not split by `Cp` in the raw file (`P01` 1, `P03` 1, `P06` 1, `P08` 1). Because the match `mu` compares only feature and nesting direction, never thresholds, `Cp = 1` is cheap for a wide threshold (for example `installments>=1` is a `mu`-match to a true `installments>=3`): `Cp` rejects spurious *features*, not sloppy *thresholds*, so **exposure-J must carry the localisation** and `theta_J` remains the load-bearing threshold for threshold looseness. The `theta_p = 0.67` alternative was not enumerated per rule (only the single `paid_search AND installments>=3 AND discount>=0.03` case, section 2, is known to flip). These are counts on one v1 draw, not rates.

## 4. The v2 target set design

### 4.1 Construction (prototype, not the frozen generator)

The prototype is the real `synthetic_benchmark._generate_row` source with one inserted hook (text substitution at import; nothing in the repository was modified). Targets only add to the same
loss / cancellation-logit / support-rate levers v1 patterns use. Fidelity: with no targets, 0 of 10,000 rows differ from the real generator (seed 20260813).
**[Rev 1] Correction.** The first draft added "It consumes exactly v1's RNG draws, so v2 covariates equal v1's for equal seeds". That is true only with no targets. With targets present the draw count per row depends on the outcome (`refund_ratio` line 419 and the refund date `rng.randint(2, 75)` line 429 are drawn only for cancelled rows; targets change cancellation), so the stream desynchronises and later rows' covariates differ; `n_affected` differs from the no-target run in 115 of 120 (pattern, seed) pairs (section 1.4). The with-target and no-target batches are different sampled datasets at the same seed. **It is a design-time feasibility instrument.** The frozen v2 generator (Phase 2) must re-run every measurement.

Effect doses (**chosen** and committed before any draw; not tuned afterwards): `H` = 410 EUR additional cost / +1.05 cancellation logit / +0.75 support rate (= `P01`'s configured effect); `M` = 300/0.75/0.50 and `L` = 240/0.50/0.30 are arbitrary author-chosen fractions of `H` with inconsistent ratios across levers (**[Rev 1]** the first draft's "fixed from `P01`'s effect" applies to `H` only).
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
4. **Coupling between targets (weakened by Rev 1).** With the ten targets present, `P03`'s real-condition oracle is 6/30 versus 15/30 in the v1-only replication at the same seeds with no targets; `P01` 28/30 -> 30/30; `P06` 25/30 -> 22/30.
   **[Rev 1] What this comparison can and cannot show.** The two batches are **different sampled datasets** at the same seed (targets change cancellation, so the RNG stream desynchronises after the first affected row; `n_affected` differs in 115 of 120 pairs, section 1.4). The comparison therefore does **not** isolate a causal effect of targets sharing rows/levers with `P03`; sampling noise is a live alternative. Two-sided Fisher exact (`rev1_check.py`): `P03` 15/30 vs 6/30 p = 0.029 (uncorrected; about 0.09 after a Bonferroni factor of 3 for the three patterns looked at, and the pattern was singled out after seeing the data), `P01` 28/30 vs 30/30 p = 0.49, `P06` 25/30 vs 22/30 p = 0.53: only the `P03` shift is even nominally distinguishable from noise, and the `P01`/`P06` shifts are within noise. The earlier phrase "adding targets changes the detectability of other patterns" is therefore a hypothesis, not a finding.
   The conclusion that **acceptance must be measured on the final composite generator, not per target or per pattern from another draw, is strengthened**: since a pattern's oracle rate depends on which dataset was sampled, and the composite dataset at a seed is not the v1 dataset at that seed, no per-target or v1-based rate transfers to the composite without re-measurement. (Different comparison-group composition remains a candidate mechanism; it was not isolated.)
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
(targets shaped toward categorical 2-3 condition rules the engine can plausibly express; or away from them). Mitigations: doses chosen and committed in advance (`H` = `P01`'s effect; `M`, `L` arbitrary fractions, section 2 invariant v, [Rev 1]); thresholds and rules committed (git) before any v2 draw was measured; targets chosen from the oracle contract, never from engine output on v2 (none exists); prior predictions recorded and partly falsified; calibration seeds separated from acceptance seeds.
**Un-removable residual:** the authors' choice of which ten rule shapes to write down is informed by that prior knowledge. A reviewer weighing the eventual result should treat the target set as "designed by people who know v0.6.2's behaviour on v1".

## 5. Pre-registered predictions and interpretation (before any engine run on v2)

Engine: unchanged `v0.6.2`. Evaluated once on evaluation seeds `E`, blind-workspace protocol, on frozen v2. Quantities: `C` = coverage recall, `S` = specific recall (validated), `X` = exact recall, all over `P+`; `Tp` = number of traps promoted (hard disqualifier, unchanged from `decision-gate.md`).

**Author's predictions, recorded now.** (1) `S` at most 0.35 (probability about 0.70); `S >= 0.70` probability at most 0.15. Basis: on v1 the engine returned broad candidates with no specific match. Counter-consideration: v2 `P+` targets are larger-effect, mostly categorical, low-order; the engine could do better. (2) `C` at least 0.80. (3) `X` at most 0.10.
(4) `Tp = 0`. (5) `S <= C` for every candidate and target at `theta_J >= 0.5` (a violation is a scorer bug, not a finding; **[Rev 1]** not asserted at `theta_J < 0.5`, where `S ⊆ C` is not guaranteed, section 3.3). (6) the candidate pool again contains a broad candidate matching at least 3 `P+` targets by coverage.

**Interpretation table (cutoffs proposed; founder-confirmable before freeze, D9).**

| Observation on `P+` | Reading |
|---|---|
| `S >= 0.70`, `Tp = 0` | the old `2/7` largely characterised the benchmark (undetectable/ambiguous targets), not pure discovery capability, for the in-language oracle-detectable regime |
| `0.35 < S < 0.70` | mixed: some in-language, oracle-detectable targets are lost; per-target first-failure autopsy is required before any conclusion; do not average away |
| `S <= 0.35` and `C >= 0.70` | real discovery problem of a **localisation / selection** kind: signal is covered by broad rules but not specified (matches the v1 `TASK-106` finding); not a power problem, because the oracle passes |
| `S <= 0.35` and `C < 0.70` | real **detection** problem for oracle-detectable targets |
| `S` and `C` both high but `X` low | the engine finds them with threshold/condition variants; exact is a representation question, report separately |
| `S > C` anywhere at `theta_J >= 0.5` (primary and the 0.5/0.7 sensitivities) | stop: scorer bug. **[Rev 1]** At the `theta_J = 0.3` sensitivity `S > C` can be legitimate (Specific with recall between 0.3 and 0.5 is not Coverage) and is reported, not a stop |
| `Tp >= 1` | hard disqualifier as in `decision-gate.md`, reported separately from discovery |

**Specific-vs-coverage divergence.** A large gap `C - S` means candidates overlap targets without localising them; it is the exact pattern ADR-106 withdrew "7/7" for. It is read as a localisation finding, never as recovery.

**Stop conditions.** Engine sha256 or contract version differs from the manifest; any frozen file hash differs; an accepted `P+` target fails the oracle in more than the pre-declared share of `E` seeds (the acceptance no longer holds: v2 evaluation is paused, results are not used to modify design); any scorer invariant violated (`S > C` at `theta_J >= 0.5` per section 3.3 [Rev 1], a candidate credited to two patterns under Specific); leakage; any run repeated selectively.
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
11. **[Rev 1]** The multiplicity family `36,791` is an engine-output-derived quantity (section 2, invariant i); v2 datasets are not the v1 datasets at the same seeds (section 1.4); the trap suite cannot test safety logic until C5 is computed (FC1).

## 7. Custody and commit protocol (invariant v; mirrors the blind-benchmark protocol and TASK-099 sections 10 and 13)

1. **F0** this specification (Phase 1): independent `CODE_REVIEWER` review against `ADR-106` and the code. Founder resolves the open decisions in section 8 in a dated `ADR` **before** F1.
2. **F1** implementation on a dedicated branch: v2 generator (proposed as an additive hook with no new RNG draws; **[Rev 1]** this does **not** give covariate identity with v1 or v1-dataset reproducibility, because the outcome-conditional draws (`refund_ratio`, refund date) still desynchronise the stream when targets change cancellation, section 1.4. Either the outcome-conditional draws are moved to separate RNG streams (a design change that must itself be verified; it also changes the no-target output relative to the v1 generator unless v1's stream is replayed for the covariates) or the identity/reproducibility claim is dropped from the manifest; FC2 below), oracle module (checks C1-C5, L1-L5), scorer changes (three recovery fields, precedence semantics, benchmark-id guard), threshold config, seed lists. No engine access.
3. **F2** acceptance run on fresh seeds `A`, no engine. Output: per-target pass rates with lower bounds, language checks, classification into `P+`, `P-`, `L`, `T`. Independent reviewer re-runs from the commit and reproduces every number.
4. **F3 freeze.** A single commit adds `benchmark-v2-freeze-manifest.json` (sha256 of generator, per-seed ground truth and dataset identity, scorer, oracle module, threshold config, seed lists, engine `fefceeaac20e8ff7...`, contract 1.3.0, this document) and a signed tag. The commit hash is recorded by the reviewer, not written into the manifest (TASK-099 chicken-and-egg). After F3 only an append-only, dated errata section is allowed; any other change creates version `2.1` with its own acceptance run.
5. **F4 first engine evaluation** is authorised only by a new `TASK`/`ADR` after F3 review. Blind workspace with allowlist, signed candidate commitment receipt (existing `blind_isolation`); ground truth opened only after commitment. One run per seed in `E`; no re-run except documented infrastructure faults; no selective reporting; results appended to a v2 ledger.
6. Roles: STATISTICS authors; CODE_REVIEWER independently verifies F0, F2, F3; a coordinator (not the author) runs F4; nobody who saw F4 output edits F1 artifacts.
7. **[Rev 1] FREEZE-CHECKLIST (each item is a blocker for F3; F4 is not authorised until all are closed and independently reviewed).**
   * **FC1 - C5 computed and passing.** The literal-plus-confounder rule check (section 2, invariant iv) is computed on acceptance seeds with its `tau_t` (D5) met, or the trap suite is extended (D5); until then the trap suite cannot test safety logic. Gate: no F3 without it. **[Rev 3] The wording "`tau_t` (D5) met" is Rev 1 and is superseded: `ADR-107` fixed no `tau_t`; what "C5 passes" means is an open founder statement (section 11.3, 12.4).**
   * **FC2 - RNG/identity claim resolved.** Separate RNG streams for outcome-conditional draws are implemented and verified, or the covariate-identity / v1-reproducibility claim is dropped from the manifest (sections 1.4, 4.1, F1).
   * **FC3 - Composite acceptance.** Every rate used for classification is measured on the final composite generator on fresh seeds `A`, never carried over from per-target or v1-only batches (section 4.2 item 4); any post-acceptance change to any target restarts it on a new set (section 2, acceptance rule).
   * **FC4 - Scorer rules pinned and tested.** The `S <= C` scope (`theta_J >= 0.5`), the shared candidate pool and matching for Specific and Coverage, the metric-only trap exemption **[Rev 3: superseded by the STRICT exemption of `ADR-107`, section 2 (ii) [Rev 2]; see the Rev 2 status line below]** and the sequential vacuity procedure (sections 2, 3.3) are implemented as specified with tests that include the `theta_J = 0.3` case and the two-redundant-conditions case.
   * **[Rev 2] Status after Phase 2a (`ADR-107` freeze order).** Spec freeze: this document (constants, section 8.1). FC1: C5 COMPUTED on 30 calibration seeds (section 11.2) but not yet satisfied (no `tau_t` in ADR-107; recompute on acceptance seeds; see 11.3). FC2: separate RNG streams IMPLEMENTED and demonstrated (`synthetic_benchmark_v2.py`; covariates byte-identical across target sets and equal to v1's; outcomes deliberately not reproduced), pending independent review. FC3: OPEN (needs the >= 8 core targets and the composite generator; Phases 2b/2c). FC4: IMPLEMENTED and tested (`benchmark_v2_scoring.py`, `scripts/evaluate_benchmark_v2.py`), with the exemption pin changed from metric-only (Rev 1) to STRICT by ADR-107 (the tests are written to the strict reading); pending independent review. Nothing here authorises F3 or F4.

## 8. OPEN FOUNDER DECISIONS (neutral; none is chosen here)

**[Rev 3] Pointer:** this table is the Rev 1 text of the open decisions. `ADR-107` decided D1-D13 (2026-09-28); the decided values are the constants in section 8.1 [Rev 2], which supersede the options below, in particular D1 (`tau = 0.90`), D2 (thresholds), D5 (traps retained, C5 mandatory), D7 (recovery wording) and D13 (ruff exclusion). Read section 8.1 first.

| # | Decision | Options and consequences (measured where possible) |
|---|---|---|
| D1 | Oracle-detectability probability `tau` (and `tau_lb`, `delta`) | 0.80: 5 in-language targets pass on the calibration point estimates (4.4), certifying needs `S >= 14` seeds with zero failures; 0.90: 4, needs `S >= 29`; 0.95: 4, needs `S >= 59`. Higher `tau` shrinks `P+` (coarser headline: 4 targets = 25% steps) and lowers the chance the engine is asked about hard targets; lower `tau` keeps more targets but admits ones that fail the oracle 10-20% of draws, which contaminates "FN" readings. `tau` must not be picked from the table above. |
| D2 | Specific and exact thresholds | `theta_J` 0.3 / 0.5 / 0.7 (0.5 accepts twice-dilute rules such as J 0.504; 0.7 sits 0.005 under a historical precise J 0.705); `theta_p` 1.0 vs 0.67 (0.67 turns `paid_search AND installments>=3 AND discount>=0.03` into a recovery); `nu` 0.05; `eta` 0.15; `eps_x` 0.10; `rho_rep` 0.80; `theta_T` 0.90. Not derivable from first principles. |
| D3 | Target count and mix | Number of `P+`, `L`, `P-`, trap targets; fewer than about 8 `P+` gives recall steps of 12.5% or more. Include designed boundary targets (dose `L`, small n) or only clear ones. |
| D4 | `N` and seeds | Keep 10,000 rows (about 4,999 development) or enlarge (raises detectability of all targets and changes v1 comparability); sizes of `C`, `A`, `E`; certification math in section 2; cost is about 5 minutes wall per calibration seed with 10 processes for about 60 oracle validations x 3 families. |
| D5 | Trap suite | **[Rev 1] Gated on C5 (FC1, section 7): until C5 is computed the trap suite as defined cannot test safety logic.** Reuse `T01`-`T05` (measured: bare rules never reach predictive; C5 unmeasured) or extend with traps built to have a real non-null association at the standard N; extending changes covariate weights (no new RNG draws needed) and is a new design. |
| D6 | Overlap-carried patterns (`P03`, `P04`, `P06`, `P05`) | (a) in `P+` under precedence semantics and the separability check; (b) in `P-` "declared overlap" stratum so `P+` is literal-disjoint. (a) keeps more of v1; (b) makes the structure clean and avoids relying on the scorer. |
| D7 | Recovery evidence level | `predictive_association` (the only level reachable at k>=2 under `G16`) or something higher (unreachable for all rules under contract 1.3.0). |
| D8 | Primary multiplicity family | 36,791 (v0.6.2 count) vs 60,000 (conservative); this moves `N01`, `N05`, `N07`, `P06` rates by up to 3 seeds of 30. |
| D9 | Interpretation cutoffs (0.35 / 0.70 / 0.70) | Confirm or replace before freeze; they encode ADR-103's "roughly 30%" reading. |
| D10 | **[Rev 1] CONFIRM:** whether v2 results may ever enter `decision-gate.md` bands | `ADR-106` already fixed the `TASK-102` bar (and `D2` Part B 2/5, outreach) as unchanged, so that part is not open; what remains is a confirmation of the default here (no: v2 results do not enter the bands unless the founder later adopts them). |
| D11 | v2 dataset composition | v1's nine patterns and five traps inside the v2 dataset (as prototyped; coupling observed) or a new-only dataset with v1 preserved separately. |
| D12 | Fresh-seed acceptance for any target changed after this document | Required here; the founder may relax. **[Rev 1] Flag:** relaxing D12 can weaken invariant 1's winner's-curse guard (a target adjusted on seeds that are then reused to "accept" it is selected on its own acceptance data), and, since targets couple (section 4.2 item 4), a single changed target can shift the others' rates. |
| D13 | **[Rev 1] Lint / type-check scope for evidence scripts** (recommendation only, not implemented) | On `39b5f7c`, `uv run ruff check docs/benchmark/task-107-evidence` reports 53 errors (51 E501, 1 RUF100, 1 SIM109) and `ruff format --check` would reformat 3 files (`jaccard_sanity.py`, `make_tables.py`, `oracle_detectability.py`); `docs/` is outside pyright's `include` (`apps/api/app`, `packages/analytics/src`, `packages/schemas/src`, `scripts`, `tools`); the repo already has several hundred ruff errors elsewhere (461 measured, of which 2 were from an unformatted draft of the new `rev1_check.py`, since fixed). These are evidence scripts, not shipped code, and were left byte-identical because they are hash-pinned in section 0. Recommendation for the founder: decide a per-path exclusion (for example a `per-file-ignores`/`extend-exclude` entry for `docs/benchmark/**`) rather than reformatting hash-pinned evidence; alternatively accept the errors. Not chosen here. |

ADR-106 ambiguities restated for the decision record: unspecified probability; "standard N"; evidence level; who fixes the specific thresholds; whether v1 patterns coexist inside v2; minimum size of `P+`.

### 8.1 [Rev 2] Founder decisions as specification constants (`ADR-107`; changing any requires a new dated ADR)

| # | Decision (as fixed) | Where it lives in this document / code |
|---|---|---|
| D1 | `tau = 0.90` (0.80 not to be returned to if targets are insufficient: design more targets on fresh acceptance seeds) | 2 (i) [Rev 2]; applied as the one-sided 95% CP lower bound (pinned reading) |
| D2 | Specific: `theta_J = 0.50`, `theta_p = 1.00`; Exact: `nu = 0.05`, `eta = 0.15`, `eps_x = 0.10`, `rho_rep = 0.80`, `theta_T = 0.90`; Coverage separate; Exact a strict diagnostic | 3.3 [Rev 2]; `theta_J`, `theta_p`, `nu`, `eta`, `eps_x`, `theta_T` in `Constants` in `benchmark_v2_scoring.py`. **[Rev 3] correction:** `rho_rep` is NOT in the scorer's `Constants`; it is an L5 oracle/measurement constant (per-draw grid representability, section 2 (iii)) applied where the projection check is run (Phase 2b/2c), not by the scorer |
| D3 | >= 8 oracle-qualified Core targets (diverse prevalence, dimensionality, effect structure); borderline targets only in a separate Challenge stratum with Challenge Recall; Core and Challenge never mixed | 3.3 [Rev 2]; Phase 2b duty (11.4) |
| D4 | `N = 10,000`; calibration, acceptance, final seeds each >= 30, fresh; counts only increased | 2 (i) [Rev 2] |
| D5 | `T01`-`T05` retained; C5 a mandatory freeze blocker; safety taxonomy not redesigned inside `TASK-107` | 11.2, 11.3; `c5-results.md` |
| D6 | Intentional overlaps in a separate `DECLARED_OVERLAP` stratum with its own metric; never silently in headline Specific Recall | 3.3 [Rev 2] |
| D7 | Evidence level `predictive_association`, disclosed as not promotion; wording "N/M benchmark targets reached `predictive_association` under the v2 recovery contract", never "recovered by the product" | 3.3 [Rev 2]; `render_report` |
| D8 | Family 60,000, pre-set, independent of any engine output; changeable only by a new benchmark version | 2 (i) [Rev 2] |
| D9 / D10 | Bands 0.35 / 0.70 / 0.70 are descriptive only, not decision thresholds; v2 does not change the `TASK-102` bar and does not enter `decision-gate.md` bands | section 5 (read with this row) |
| D11 | Clean v2: no v1 patterns as coupled positives; v1 stays a frozen historical benchmark; motifs may recur but literal targets are designed and accepted as v2. Consequence: `P01` cannot be a v2 target literally, so of the four Phase 1 "qualifying" targets only `N02`, `N03`, `N06` are candidates, and each must be re-accepted on the clean composite at family 60,000 (their Phase 1 rates were measured with v1 patterns present at family 36,791) | Phase 2b duty (11.4); `synthetic_benchmark_v2.py` has no v1 patterns in v2 outcomes |
| D12 | Fresh acceptance seeds, no relaxation | 2 (i); 11.4 |
| D13 | `docs/benchmark/**` evidence/data artifacts excluded from ruff; executable benchmark code (scripts/, packages/, tests/) stays linted | `pyproject.toml` `extend-exclude` + `force-exclude`; 11.2 |
| pins | strict trap exemption (metric match AND validation clause); sequential vacuity with Exact bijection BEFORE relaxation or `exact_after_vacuity` | 2 (ii), 3.3 [Rev 2]; tests |

## 9. Reproduction

```sh
uv run python docs/benchmark/task-107-evidence/jaccard_sanity.py                                   # ~4 s
uv run python docs/benchmark/task-107-evidence/oracle_detectability.py fidelity                    # 0 differing rows
uv run python docs/benchmark/task-107-evidence/oracle_detectability.py batch --seeds 1001 1030 --dir docs/benchmark/task-107-evidence/oracle-raw --procs 10   # ~25 min wall
uv run python docs/benchmark/task-107-evidence/oracle_detectability.py rates --dir docs/benchmark/task-107-evidence/oracle-raw --out docs/benchmark/task-107-evidence/oracle-rates.json
uv run python docs/benchmark/task-107-evidence/make_tables.py
python3 docs/benchmark/task-107-evidence/rev1_check.py        # [Rev 1] reads committed raw JSON only, about 1 s
```

## 10. [Rev 1] Change log and ledger notes (2026-09-25)

### 10.1 Change log (first-draft text is quoted, not silently replaced)

| # | Item | Disposition |
|---|---|---|
| 1 | "v2 covariates equal v1 covariates for equal seeds" / "consumes exactly v1's RNG draws" (1.4, 4.1, 4.2 item 4) | **Reviewer confirmed by my own run**: `n_affected` differs in 115/120 pairs (`rev1_check.py`). Corrected in 1.4, 4.1, 4.2 item 4, 7 (F1); coupling reading weakened (Fisher p 0.029 / 0.49 / 0.53); composite-acceptance conclusion strengthened; FC2 added |
| 2 | "`J >= 0.5` implies `recall >= 0.5`, so `S > C` for any `theta_J >= 1/3` is a scorer bug" (3.3, 5) | **Reviewer correct** (`J <= recall`). `S ⊆ C` guaranteed only at `theta_J >= 0.5`; stop rule scoped; pool/matching pinned (3.3, 5) |
| 3 | Trap exemption vs SPEC's validation clause | Pinned: exemption uses the metric part (J, Cp, K) only (2 ii); alternative noted |
| 4 | Vacuity simultaneous vs sequential; weak true condition | Pinned sequential with tie-break; Exact-bijection side effect stated (3.3, 2 ii) |
| 5 | `theta_p = 1` sensitivity | New 3.4 from `jaccard-sanity-raw.json`: `P03` 3 of 15 survive at J >= 0.5 (12 have Cp < 1), other patterns' counts given; `mu` is nesting-only, exposure-J carries localisation. Verified |
| 6 | "No engine was run on any v2 draw" | Reworded (header): no discovery search / candidate output; `_atoms`, `DiscoveryConfig`, `build_projection`, `run_validation` were called; verified from imports |
| 7 | Doses "fixed from P01's effect" | `H` = P01 effect; `M`, `L` chosen arbitrary fractions, ratios inconsistent (2 v, 4.1, 4.5) |
| 8 | Family 36,791 | Marked engine-output-derived; ADR-106 invariant 5 sentence; 26,213 sourced (`TASK-064`/`TASK-069`) (2 i) |
| 9 | Certification bounds | Wilson two-sided (0.886 at 30/30) vs one-sided Clopper-Pearson (0.905) labelled (2 i) |
| 10 | Acceptance-seed rule | Failing target on `A` needs fresh `A'`; composite re-acceptance (2 i) |
| 11 | Ledger nits | Disclosed in 10.2; predictions file not edited |
| a | C5 | FC1 gated blocker (7) and in D5 and 2 (iv) |
| b | D10, D12 | D10 relabelled CONFIRM; D12 winner's-curse flag |
| c | Lint | Recorded as D13 (recommendation, not implemented); verified 53 errors (51 E501, 1 RUF100, 1 SIM109), 3 files would reformat, `docs/` outside pyright `include`, 461 repo-wide ruff errors |

No OPEN founder decision (D1-D9, D11) was chosen; D10 is relabelled and D13 added, neither decided. No numeric result in sections 3.1-4.4 was altered.

### 10.2 Ledger notes (disclosed, nothing rewritten)

* `ADR-106` (`DECISIONS.md`) carries `Date: 2026-09-27` in its text but was committed 2026-09-24 (`ae3b80e`). The `TASK-107` released-status line and the `TASK-108` closed line in `TASKS.md` also say 2026-09-27, whereas their commits (`e6b0867`, `fbbe3d7`) are dated 2026-09-24.
* The `TASK-107` Phase 1 status entry in `TASKS.md` is dated 2026-09-25 (commit `39b5f7c`), earlier than the 2026-09-27 date in the inputs (`ADR-106`/released-status) it builds on. Both dates are as written; the commit dates are the reliable order.
* `predictions-preregistration.md` (committed `22f4b4d`, unedited since; sha256 above) says the calibration bands are "over calibration seeds (n=40)"; the run used **30** seeds (1001-1030). The bands do not depend on `n`; the file is not edited.
* The v1-only replication batch used the pre-spawn-fix script version (already disclosed in section 6 item 2).

## 11. [Rev 2] Phase 2a: change log, results, what is still open, and what each later phase must do

### 11.1 Change log (additive; Rev 1 text is not edited)

| # | Item | Disposition |
|---|---|---|
| 1 | Constants of `ADR-107` (tau 0.90; `theta_J` 0.50, `theta_p` 1.00; `nu` 0.05, `eta` 0.15, `eps_x` 0.10, `rho_rep` 0.80, `theta_T` 0.90; family 60,000; `N` 10,000; seeds >= 30 each, fresh; Core / Challenge / DECLARED_OVERLAP) | Baked in: 2 (i), 3.3, 8.1 [Rev 2] |
| 2 | Trap exemption: metric-only (Rev 1) -> STRICT (metric AND validation clause) | Superseded by `ADR-107`; 2 (ii) [Rev 2]; code and tests |
| 3 | Vacuity: sequential + tie-break kept; Exact bijection before relaxation or `exact_after_vacuity` | 3.3 [Rev 2]; code and tests |
| 4 | Recovery wording (D7) | 3.3 [Rev 2]; the renderer refuses any ratio not labelled `N/M benchmark targets` |
| 5 | Scorer-implementation pins (credit, pool, `mu` direction, unscoreable exemption, sensitivities) | 3.3 [Rev 2], flagged for review |
| 6 | FC status | 7 [Rev 2] |
| 7 | New code and evidence | 11.5 |

### 11.2 Phase 2a results (all measured; no engine, no discovery run on any v2 draw)

* **C5 / FC1** (`c5-results.md`, calibration seeds 1001-1030, family 60,000, best-of-15 composites by development t): bare literals reach `predictive_association` in 0/30 for all five traps on the clean v2 draw; on v1 draws the bare `T03` literal reached it (and `shadow_policy`) once (seed 1023). Literal-plus-confounder composites reach `predictive_association`: clean v2: `T03` 28/30, `T01`/`T02`/`T04`/`T05` 0/30; v1: `T03` 30/30, `T04` 19/30, `T01` 2/30, `T02`/`T05` 0/30. No k >= 2 composite reaches `shadow_policy` in any draw (`G16`). Implication (not a redesign): on clean v2 only `T03` exercises the trap logic; the others are rejected on power/uncertainty grounds first, and promotion of a composite is structurally impossible under contract 1.3.0.
* **Scorer v2** (FC4): `packages/analytics/src/policy_analytics/benchmark_v2_scoring.py` (pure core), `scripts/evaluate_benchmark_v2.py` (CLI, benchmark-id guard), tests `tests/analytics/test_benchmark_v2_scoring.py` and `tests/analytics/test_evaluate_benchmark_v2_cli.py` (**[Rev 3] soft claim, corrected:** the Phase 2a wording "a mutation test per rule component" was overstated; an independent mutation pass found survivors, killed in Rev 3 (12.1). Fixtures: the ten TASK-108 vacuous/bare/confounder shapes at three evidence levels; historical precise `P06` J 0.705 and dilute `P01` J 0.504; the 15 v0.6.2 candidates of both TASK-103 runs, none Specific at any sensitivity; both ADR-106 pair shapes; trap-must-stay-trap cases including a promoted `T03`; vacuity edge cases; Exact bijection and tolerance cases; strata; invariants; mutation tests, see 12.1). v1 scorer untouched.
* **RNG isolation** (FC2 prerequisite): `synthetic_benchmark_v2.py` + `rng-isolation-demo.json` (six seeds, 10,000 rows each): covariate sha256 identical for no targets, one target, three targets and the v1 generator; rows not touched by a target are fully identical to the no-target run. Reproduced relative to v1: every covariate column (`COVARIATE_COLUMNS`). NOT reproduced: every outcome and derived column (`OUTCOME_COLUMNS`), even with zero targets (separate outcome streams; no v1 patterns in v2). The Phase 2b hook is `TargetSpec` / `generate_v2`; no v2 target is designed or selected here.
* **Ruff (D13)**: `docs/benchmark` findings 57 -> 0 (`uv run ruff check docs/benchmark` before: 57 = the 53 of Rev 1 plus 4 from the new `c5_check.py`; after: no Python files under the exclusion, with `force-exclude`); repo-wide `ruff check .` 461 -> 404 (457 at the start of Phase 2a, +4 from `c5_check.py`); `scripts` 233 -> 233 and `packages` 0 -> 0, `tests` 0 -> 0 (unchanged; new code adds none).

### 11.3 Still open

* **Decision-level: exactly one, and it is a statement, not a new number.** `ADR-107` D5 makes C5 a mandatory freeze blocker but does not say what "C5 passes" means (Rev 1 had a `tau_t` placeholder). Measured (11.2): on clean v2 only `T03` is tempting; `T01`/`T02`/`T04`/`T05` are inert. The founder should state whether FC1 is satisfied by "computed and disclosed on the acceptance seeds" or requires a stronger trap set (a safety-taxonomy change, outside `TASK-107` by D5). Until then FC1 stays open and F3/F4 are not authorised.
* **Reviewer-facing pins** (not decision-level; each is listed in 2 (i), 3.3 [Rev 2]): the LB reading of `tau`; credit / pool / `mu` direction / unscoreable-exemption / sensitivity pins; the out-of-language `L` suite kept as a fourth reported stratum.
* **Design-time, not decision-level:** the pre-declared criterion for placing a target in Challenge instead of Core (to be written before any 2b calibration draw); the v2 ground-truth JSON schema (documented in the CLI docstring; fixed at 2c); fresh seed lists (to be recorded before use).

### 11.4 What each later phase must do

* **Phase 2b (target design and calibration; no engine).** Design >= 8 oracle-qualified Core targets (diverse prevalence, 2-3 conditions, effect structure) plus optional Challenge and DECLARED_OVERLAP targets, declared through `TargetSpec` on the RNG-isolated generator; no v1 pattern literal as a target (D11); not selected by what `v0.6.2` can find; expect several new designs beyond `N02`/`N03`/`N06`; pre-declare the Challenge placement criterion first; calibrate on calibration seeds (>= 30) with the real contract at family 60,000; re-check L1-L5, C3/C4 and non-degeneracy (`K(T_P) = T_P` at `nu`); commit predictions before each run; keep the trap suite as is.
* **Phase 2c (acceptance, freeze package, review).** Fresh acceptance seeds (>= 30, disjoint from 1001-1030 and from calibration and final seeds) run once on the frozen composite generator: per-target oracle pass rates with the CP lower bound against `tau = 0.90`, language checks, classification into Core / Challenge / DECLARED_OVERLAP / `L`, C5 recomputed on the composite, FC3 satisfied (no rate carried over); any post-acceptance target change restarts acceptance on new seeds (D12); write the v2 ground truth and freeze manifest (hashes of generator, scorer core and CLI, threshold constants, seed lists, engine `fefceeaa...`, contract 1.3.0, this document); independent review of the whole frozen benchmark; only after `APPROVED` may a separate `TASK`/`ADR` authorise the first engine evaluation on final v2 (F4). Engine stays frozen throughout.

### 11.5 Evidence and reproduction added in Phase 2a

```sh
uv run pytest tests/analytics/test_benchmark_v2_scoring.py tests/analytics/test_evaluate_benchmark_v2_cli.py tests/analytics/test_synthetic_benchmark_v2_rng_isolation.py -q
uv run python docs/benchmark/task-107-evidence/rng_isolation_demo.py                                  # about 1 min
uv run python docs/benchmark/task-107-evidence/c5_check.py batch --seeds 1001 1030 --draw v2clean --dir docs/benchmark/task-107-evidence/c5-raw-v2clean --procs 8   # about 6 min
uv run python docs/benchmark/task-107-evidence/c5_check.py batch --seeds 1001 1030 --draw v1 --dir docs/benchmark/task-107-evidence/c5-raw-v1 --procs 8            # about 6 min
uv run python docs/benchmark/task-107-evidence/c5_check.py rates --dir docs/benchmark/task-107-evidence/c5-raw-v2clean --out docs/benchmark/task-107-evidence/c5-rates-v2clean.json
```

New evidence files (`docs/benchmark/task-107-evidence/`): `c5-predictions.md` (committed before the script), `c5_check.py`, `c5-raw-v2clean/`, `c5-raw-v1/`, `c5-rates-v2clean.json`, `c5-rates-v1.json`, `c5-results.md`, `rng_isolation_demo.py`, `rng-isolation-demo.json`. Their sha256 and the code hashes are recorded in the `TASKS.md` Phase 2a entry (this document is edited afterwards, so its own hash cannot be self-referenced).

## 12. [Rev 3] Independent-review revisions to Phase 2a (2026-09-25; additive, nothing above is deleted)

Binding: `ADR-107`, this document. No engine, v1 generator/scorer/ground truth, gate or contract file changed (sha256 verified before and after, recorded in the `TASKS.md` Revision entry); no engine or discovery run on any v2 draw.

### 12.1 Scorer changes and tests

* **Trap literal by row-set equality (`benchmark_v2_scoring.py`).** The literal test was `CondSpec` equality, so `acquisition_channel IN ['paid_search'] AND installments>=3 AND discount_rate>=0.03` returned `trap_hits []` while its `eq` twin was a `T03` hit (the row sets are identical). A candidate condition now matches a trap literal iff it is on the same feature and its row set equals the literal's (non-empty). The engine language is unchanged (the engine never emits `in`); the change only removes a silent evasion for `in`-form candidates. Chosen over rejecting `in` candidates in the CLI because that would leave the scorer core unsound for any other caller and would hide, rather than classify, the candidate. The exemption side (`trap.literal in target.literals()`) still compares by `CondSpec` because target conditions come from the ground truth in engine language; a target written with a single-value `in` for a trap literal would need the same row-set rule (none exists; Phase 2b must not declare one).
* **Mutation pass.** The claim "a mutation test per rule component" was false: `_compatible` always True, `nested` replaced by "intersects", Exact not restricted to the trap-free pool, the dev-affected floor `min_dev_n`, `broad_min_targets` and the removal of the `_check_invariants` call from `score()` all survived. Tests now kill each. A scripted pass of 132 single-site mutants (constants, comparison boundaries, operators, pair metrics, Exact bijection, vacuity, trap classification, exemption, credit, pool, strata, invariants, safety, rendering) on a scratch copy: **before** the Rev 3 tests 77 killed / 55 survived; **after** 128 killed / 4 survived. The 4 survivors are equivalent mutants (no observable behavior change): `exact_verdict` relaxed branch without the `len(effective) != len(candidate)` guard (equal lengths make `effective` the same set as the candidate, so relaxed equals strict); `exact_verdict` returning `ExactVerdict(False, False)` instead of `None` (the caller ignores both alike; definedness is reported separately); `Target.literals()` including `in` conditions (an `eq` trap literal never equals an `in` condition); `elif` turned into `if` after `verdict.exact` (`ExactVerdict(True, False)` never has the relaxed flag).
* **Disclosure: Exact and Coverage need no validation.** Both use the shared trap-free pool and neither requires `predictive_association`, so a candidate that exactly reproduces a target but is not validated counts for Exact (and Coverage) and not for Specific: **Exact can exceed Specific**. The renderer's Exact line now says so; read Exact as a strict shape diagnostic, never as recovery.
* **Disclosure: latent date bug.** `_row_matches` returns False for date-typed values under `ge`/`lt` (only int/float, non-bool, are numeric). Harmless for engine-language v2 targets (the engine's features exclude the date columns; `booking_month` is materialised as an integer by the callers); do not declare a date-typed threshold. Documented in the code.
* **RNG wording.** "Constant number of calls" in the generator docstring is replaced by "constant call sequence": `randint` uses rejection sampling, so the number of Mersenne Twister words consumed per row varies, but only with `(seed, index)` (the per-row stream is keyed by them), never with targets, so isolation holds. Comment/docstring only.

### 12.2 Corrected tau / Clopper-Pearson table

One-sided 95% lower bound `LB(k, S)` = the `p` at which `P(X >= k | p, S) = 0.05` (exact, computed by bisection on the binomial tail); `f = S - k` failures; the last column is the largest `f` with `LB >= 0.90`.

| S | f=0 | f=1 | f=2 | f=3 | f=4 | f=5 | failures allowed at LB >= 0.90 |
|---|---|---|---|---|---|---|---|
| 14 | 0.8074 | 0.7033 | 0.6146 | 0.5343 | 0.4600 | 0.3904 | none (0.90 not reachable) |
| 29 | 0.9019 | 0.8466 | 0.7984 | 0.7539 | 0.7116 | 0.6711 | 0 |
| 30 | 0.9050 | 0.8514 | 0.8047 | 0.7614 | 0.7204 | 0.6810 | 0 |
| 45 | 0.9356 | 0.8989 | 0.8666 | 0.8366 | 0.8080 | 0.7805 | 0 (f=1 is 0.8989, just under) |
| 59 | 0.9505 | 0.9221 | 0.8971 | 0.8738 | 0.8515 | 0.8300 | 1 |
| 60 | 0.9513 | 0.9234 | 0.8988 | 0.8758 | 0.8539 | 0.8327 | 1 |
| 90 | 0.9673 | 0.9484 | 0.9317 | 0.9161 | 0.9012 | 0.8867 | **4** (the Rev 2 line said 3) |

Only the `S = 90` line of section 2 (i) was wrong; `S = 30, 45, 60` stand. The zero-failure statements (`S = 14 / 29 / 59` certify `p >= 0.80 / 0.90 / 0.95`) stand (0.8074, 0.9019, 0.9505). Whether the CP lower bound is the right reading of `tau` remains the reviewer-facing pin (11.3), not decided here.

### 12.3 Order of freeze steps (`ADR-107` "spec freeze first")

`ADR-107`'s "spec freeze first" was satisfied by Rev 1 plus `ADR-107` (constants in 8.1). Rev 2 (this document's Phase 2a update) was committed last, after the scorer, the generator skeleton and C5; no engine run happened in any order, so the freeze order carries no engine-result dependence.

### 12.4 Cross-pointers and what is not decided

The Rev 1 wording "`tau_t` met" (invariant iv, FC1) and "metric-only exemption" (FC4) is superseded by Rev 2 / `ADR-107` (strict exemption; no `tau_t`); each site now carries a pointer. Not decided here, awaiting founder statements: whether the trap exemption may use unscoreable targets (pin (d) in 3.3 [Rev 2]); the CP-LB reading of `tau`; what "C5 passes" means.

### 12.5 Lint scope

`[tool.ruff.format] exclude` now lists the frozen engine, discovery, validation (gate and contract) packages and the v1 generator/scorer, so a plain `ruff format .` (Makefile, CI) cannot reformat them; `ruff check` behavior is unchanged. `force-exclude = true` (Phase 2a) also applies to `extend-exclude`, and `apps/api/migrations/versions` was already in `extend-exclude`: with `force-exclude` it is now skipped even when named explicitly, which is harmless (generated migration files; nothing in the Makefile, CI or pre-commit passes them explicitly; checked in the `TASKS.md` Revision entry).

## 13. [Rev 4] Phase 2b: `ADR-108` Decision 3 in the scorer, pre-declarations, target design, calibration

Binding: `ADR-106`, `ADR-107`, `ADR-108` (read in full); sections 2-4, 11-12 above. Engine stays frozen (`fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`, contract 1.3.0); verified
unchanged before and after this phase, alongside the v1 generator/scorer/ground truth and every gate/contract file (`rev4-calibration-raw/` commits each record the check). **No engine or discovery run on any v2 draw.**
Only the atom-grid builder `_atoms`, `build_projection` and the real `run_validation` (through a local `_validate_rules`, same call shape as `diagnose_task106_fn_autopsy._validate_rules`) touch engine-package
code, exactly as in Phase 1/2a.

### 13.1 Step 0 - `ADR-108` Decision 3 in the scorer

`benchmark_v2_scoring.py`: `Target.assessed: bool = True` (False marks a target NOT ASSESSED); the exemption loop now requires, for every trap-literal or trap-equivalence hit, a target that (a) contains the
trap's literal, (b) is `scoreable` (`_is_scoreable`, which now also requires `assessed`), and (c) meets the metric match (`J_e >= theta_J`, `Cp >= theta_p`, non-empty `K`) **and** the candidate reaches
`predictive_association` or above (the `ADR-107` strict reading, unchanged). A denial is recorded with a provenance label distinguishing **no exemption** from **confirmed trap**:
`trap_provenance[trap_id]` in `{"exempt", "confirmed_trap", "no_exemption_unscoreable_target", "no_exemption_validation_not_assessed"}`; `confirmed_trap` only when every predicate was computable and failed.
`safety.no_exemption_not_confirmed_trap` lists every hit whose denial was for unverifiability, separately from genuine `trap_hits`. This supersedes Rev 2 pin (d) (3.3): the exact `P05` rule no longer exempts
`T05` because `P05` is unscoreable (n=23) — tested directly (`test_exact_p05_rule_gets_no_exemption_because_p05_is_unscoreable`). Tests: `tests/analytics/test_benchmark_v2_scoring.py` (9 new tests covering
scoreable/unscoreable/NOT-ASSESSED/missing-evidence/computed-and-failed cases, plus a safety-report test); a scripted single-site mutation pass
(`docs/benchmark/task-107-evidence/rev4_step0_mutation_check.py`, 6 mutants targeting the new scoreability gate, the NOT-ASSESSED flag, both denial-provenance branches, the dropped validation
requirement, and the safety-report filter) reports **6/6 killed** (`rev4-step0-mutation-output.txt`). `ruff format`/`ruff check`/`pyright` clean on every touched file (never run over frozen `packages/`
files other than the ones edited: `benchmark_v2_scoring.py` only).

### 13.2 Step 1 - pre-declarations (committed before any calibration run)

`docs/benchmark/task-107-evidence/rev4-preregistration.md` (sha256 `19a7d83bef87faf47e8dd292f9d4470822b66dd075291fbcb24f7169f7ab1ee6`) fixes, before any calibration seed was drawn:

* **Classification rule** (mechanical, outcomes only, never intention): per target, per acceptance/calibration seed, `pass` iff the real conjunction (real `Condition`s) reaches `predictive_association` or
  above under the real `run_validation` (contract 1.3.0) on the composite draw at the stated family; `k` = passes of `S` seeds. **Core** iff not `declared_overlap`, `k = S` (30/30), one-sided 95%
  Clopper-Pearson lower bound `>= 0.90`, and every structural check (L1-L5, `K(T)=T`, scoreable) holds on every seed. **DECLARED_OVERLAP** iff the design carries a trap literal (by declaration); `oracle_qualified`
  iff additionally `k=S`, CP-LB `>= 0.90` and C4 (exposure-J against the bare trap literal `<= 0.30`) holds on every seed. **Challenge** iff not Core/overlap/out-of-language and `15 <= k <= 29` (or `k=S` with a
  non-L1-L4 structural failure). **Underpowered** otherwise. A design *intended* Core that fails calibration is Challenge or Underpowered; a design *intended* Challenge that reaches 30/30 with clean structure is
  Core: **the class follows the outcomes, never the intention** — stated and then applied without exception (section 13.4).
* **Seed ranges** (disjoint, recorded before use): calibration 1001-1030 (Phase 1, spent), design seeds 9001-9010 / 9101-9110 / 9111-9120 / 9121-9130 (spent; real-oracle pilots, see 13.3), **Phase 2b
  calibration 2001-2030 (used in this revision)**, calibration round 2 (only if needed) 2101-2130, acceptance `A` 3001-3030, `A'`/`A''` 3101-3130/3201-3230, final evaluation `E` 4001-4030 (reserve
  4101-4130). None but 2001-2030 (and the design/pilot ranges, disclosed as spent) were touched in Phase 2b.
* **Optional-stopping ban** (`ADR-108`): no run is extended with extra seeds after its result is seen; a failing target is redesigned only on a fresh, disjoint set.
* **Bounded dose-selection procedure**: allowed only before the design-freeze commit, only on design seeds 9001-9010, only with a contract-free Welch-t power proxy (`design_dose_select.py`); each design has
  a fixed rule and a fixed effect-structure ladder (`mixed`/`loss`/`cancel`, `synthetic_benchmark_v2_targets.LADDERS`); rung = first rung with proxy `t_mean >= 7.0` and `t_min >= 5.8` (Core/overlap) or
  `t_mean >= 5.0` (Challenge); composite re-evaluated after every change, at most 12 rounds; forbidden after the design-freeze commit.
* **Disclosure of a design-stage pilot seen before the pre-declaration commit** (section 13.3 below, pre-registration section 0): one real-oracle run on seeds 9001-9010 was seen before Step 1 was
  committed; those seeds are recorded as spent and never reused for calibration/acceptance/final evaluation; the affected finding (every `manager=` literal fails G12 structurally) is a disclosed structural
  exclusion, not an engine-output-informed design choice (no `v0.6.2` discovery output exists or was used).

### 13.3 Step 2 - target design (no engine)

20 targets declared through `TargetSpec` on the composite generator (`packages/analytics/src/policy_analytics/synthetic_benchmark_v2_targets.py`): 12 intended Core, 6 intended Challenge, 2
DECLARED_OVERLAP (`D01` carries the `T03` literal `acquisition_channel=paid_search`, `D02` carries the `T04` literal `payment_method=bank_transfer`). No v1 pattern literal is reused (`D11`, tested); no trap
literal outside the two DECLARED_OVERLAP designs (tested); every pair of designs shares at most one categorical literal (tested); no design uses `manager=` (structural G12 exclusion, section 13.2); 1-3
conditions each, every condition on an engine feature with an engine-expressible operator (`eq` categorical, `ge`/`lt` numeric), on a grid atom stable across 10 design-check draws (9001-9010).
Design iteration (specs A through G, `docs/benchmark/task-107-evidence/rev4-design-stage/`) used only the contract-free power proxy on design seeds, plus real-oracle **confirm-only** pilots on three disjoint
hold-out ranges (9101-9110 on spec E, 9111-9120 on spec F, 9121-9130 on the final spec G): a Core candidate failing a pilot was dropped to Challenge (`C03`, `C05`, `C06` were dropped this way across the
pilots) rather than re-dosed — never a silent iteration. Two amendments to the overlap-coefficient structural rule (R5, `<= 0.25` -> `<= 0.35` for Challenge pairs -> `<= 0.45` for every pair) were made after
seeing check output on design seeds and are disclosed as such in `rev4-preregistration.md` sections 9-11; they affect design-seed structural bookkeeping only, never the calibration verdict.

| id | rule | dose (ladder) | intended class | conditions |
|---|---|---|---|---|
| C01 | `destination=Lisbon AND acquisition_channel=partner` | LO6 (loss) | Core | 2 |
| C02 | `destination=Rome AND customer_segment=corporate` | LO6 (loss) | Core | 2 |
| C03 | `product_category=premium AND acquisition_channel=partner AND discount_rate>=0.08` | LO6 (loss) | Challenge | 3 |
| C04 | `supplier=Cedar AND customer_segment=leisure AND trip_duration_days>=8` | LO5 (loss) | Core | 3 |
| C05 | `supplier=DeltaSun AND discount_rate>=0.12` | LO3 (loss) | Challenge | 2 |
| C06 | `destination=Reykjavik AND customer_type=returning AND discount_rate>=0.05` | LO5 (loss) | Challenge | 3 |
| C07 | `supplier=BlueWing AND acquisition_channel=direct AND party_size>=3` | CX1 (cancel) | Core | 3 |
| C08 | `payment_method=wallet` | H (mixed) | Core | 1 |
| C09 | `destination=Tokyo AND customer_segment=leisure AND product_category=standard` | LO6 (loss) | Core | 3 |
| C10 | `customer_type=new AND acquisition_channel=referral AND trip_duration_days>=6` | LO7 (loss) | Core | 3 |
| C11 | `destination=Tokyo AND customer_segment=family` | H (mixed) | Core | 2 |
| C12 | `acquisition_channel=direct AND product_category=premium AND customer_segment=leisure` | XL (mixed) | Core | 3 |
| C13 | `destination=Reykjavik AND product_category=standard AND payment_method=card` | LO6 (loss) | Core | 3 |
| C14 | `customer_segment=leisure AND supplier=BlueWing AND discount_rate>=0.08` | LO2 (loss) | Core | 3 |
| C15 | `customer_type=returning AND acquisition_channel=direct AND trip_duration_days>=6` | LO3 (loss) | Core | 3 |
| H01 | `supplier=BlueWing AND destination=Zanzibar AND customer_type=new` | LO6 (loss) | Challenge | 3 |
| H02 | `supplier=DeltaSun AND customer_segment=corporate AND product_category=standard` | H (mixed) | Challenge | 3 |
| H03 | `customer_type=returning AND payment_method=card AND trip_duration_days>=8` | LO3 (loss) | Challenge | 3 |
| D01 | `acquisition_channel=paid_search AND destination=Rome AND customer_type=returning` | LO7 (loss) | DECLARED_OVERLAP (`T03`) | 3 |
| D02 | `payment_method=bank_transfer AND product_category=standard AND discount_rate>=0.08` | ML (mixed) | DECLARED_OVERLAP (`T04`) | 3 |

**Prior-knowledge disclosure** (mirrors section 4.5): the authors know `v0.6.2`'s behaviour on v1. Target selection here used only oracle-structure facts (contract gate code: G12's leave-one-manager-out
design, G05's family arithmetic), the Phase 1 oracle rates on already-spent seeds, and the contract-free power proxy; no engine or discovery output on any v2 draw exists or was consulted; no design was chosen
or dropped by what `v0.6.2` finds or misses. The manager-literal exclusion is a structural fact about contract code (robustness group column = `manager`), not an engine-discovery result. Residual, un-removable
risk: choosing low-order categorical/threshold rules is itself informed by knowing the engine's language (stated in `ADR-107`/section 4.5 already; repeated here for Phase 2b's own designs).

### 13.4 Step 3 - calibration (2001-2030, family 60,000 primary; sensitivities 36,791/26,213; real contract; composite)

Raw output: `docs/benchmark/task-107-evidence/rev4-calibration-raw/` (30 files, all three families, all 20 targets; sha256 of each file is stable under `git log`). Rates:
`rev4-calibration-rates.json` (sha256 `0a0817a04bcf6c14987a2b2f44b2ad6d51a3ac5f453f515a7735caff6aa81091`). C5 re-run on the composite (reference only, `ADR-108` Decision 2, not a gate):
`rev4-c5-composite-raw/` and `rev4-c5-composite-rates.json` (sha256 `62e4019f77ab5f0b9d0f92156e66db92dedc0c55e8018ca9f434022b74a38324`).

| id | intended class | k/30 @60,000 | CP-LB (one-sided 95%) | calibration verdict | k/30 @36,791 | k/30 @26,213 |
|---|---|---|---|---|---|---|
| C01 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C02 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C03 | Challenge | 15/30 | 0.3389 | challenge_candidate | 15/30 | 15/30 |
| C04 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C05 | Challenge | 29/30 | 0.8514 | challenge_candidate | 29/30 | 29/30 |
| C06 | Challenge | 30/30 | 0.9050 | **core_candidate** (outcome promotes it) | 30/30 | 30/30 |
| C07 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C08 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C09 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C10 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C11 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C12 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C13 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C14 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| C15 | Core | 30/30 | 0.9050 | **core_candidate** | 30/30 | 30/30 |
| H01 | Challenge | 30/30 | 0.9050 | **core_candidate** (outcome promotes it) | 30/30 | 30/30 |
| H02 | Challenge | 28/30 | 0.8047 | challenge_candidate | 28/30 | 28/30 |
| H03 | Challenge | 29/30 | 0.8514 | challenge_candidate | 29/30 | 29/30 |
| D01 | DECLARED_OVERLAP | 30/30 | 0.9050 | **oracle_qualified** (C4 max exposure-J 0.091 <= 0.30, all 30 seeds) | 30/30 | 30/30 |
| D02 | DECLARED_OVERLAP | 18/30 | 0.4339 | not oracle_qualified (C4 max exposure-J 0.288 <= 0.30, holds, but k too low) | 18/30 | 18/30 |

Structural checks (L1-L5, `K(T)=T` at `nu=0.05`, on-grid, scoreable, projection-Jaccard `= 1.0`) hold on **every one of the 30 calibration seeds for every one of the 20 targets** — zero violations (checked
programmatically). Dominant failing gates on the non-qualifying targets, as predicted (P5): `G12_ROBUSTNESS` for `C03`/`C05`/`D02` (sign-agreement floor), `G10_TEMPORAL_STABILITY` for `H02`/`H03`. Sensitivity
families `36,791` and `26,213` give identical `k` to the primary `60,000` for every target (no family-size coincidence).

**Coverage of the >= 8 requirement: 14 of 20 targets reach `core_candidate` at calibration — comfortably above 8.** This includes the 12 originally-intended Core designs minus none (**all 12 pass**) plus two
originally-intended-Challenge designs (`C06`, `H01`) that the pre-declared mechanical rule promotes on outcomes alone, exactly as section 13.2's classification rule requires ("the class follows the outcomes,
never the intention"). No target needed a round-2 calibration seed set (2101-2130); section 4 of the pre-registration (design more before acceptance) does not apply this round.

**Predictions review** (`rev4-predictions.md`): P1 confirmed (all structural). P2 under-predicted: author predicted a median of 10 Core passes with `P(all 12) ~ 0.10`; the actual result is all 12 plus two
promotions (14 total) — stated plainly as an underestimate, not adjusted after the fact. P3-P5 confirmed in direction (dominant gate G12, then G10/G05). P7 (C5 composite, reference only) — **[Rev 4
correction, 2026-10-01, after independent review]: the original text here under-disclosed the composite shift and contained one false statement ("T01/T04/T05 stay inert"). Corrected, from
`rev4-c5-composite-rates.json` directly, not re-measured:**

| Trap | Bare, clean-v2 (Phase 2a) | Bare, composite | Composite-rule, clean-v2 (Phase 2a) | Composite-rule, composite |
|---|---|---|---|---|
| T01 | 0/30 | 0/30 | 0/30 | **22/30** |
| T02 | 0/30 | **27/30** | 0/30 | 29/30 |
| T03 | 28/30 | 29/30 | 28/30 | **11/30** |
| T04 | 0/30 | 0/30 | 0/30 | 0/30 |
| T05 | 0/30 | 0/30 | 0/30 | 0/30 |

(all reach at most `predictive_association`; no cell reaches `shadow_policy`, so `G16` still blocks promotion for every k>=2 rule in every cell). The original text disclosed only two of these four large
shifts (T02 bare, T03 composite-rule) and stated T01 "stays inert", which is false: T01's own composite-rule rate is 22/30 (73%), not 0. T02's composite-rule rate (29/30) and T03's bare rate (29/30) were
also previously unstated. Pre-registered prediction P7 (`rev4-predictions.md`) predicted composite-rule rates `<= 3/30` for T01/T02/T04/T05 — this holds for T04/T05 but fails badly for T01 (22 vs <= 3) and
T02 (29 vs <= 3); the original predictions-review text discussed this miss only via T02's *bare* rate, which was not what P7 predicted. All shifts are attributed to the same mechanism: with 20 targets active
simultaneously (vs. 0 or 1 in Phase 2a), `_outcome_columns` additively sums every active target's dosing on rows its predicate matches, shifting the comparison-group baseline used when grading any one
trap/composite — a foreseeable consequence of the additive composite design, not an RNG-isolation violation and not a gate change (confirmed by independent review reading `synthetic_benchmark_v2.py`). This
remains a disclosed benchmark property of the trap suite under a dense composite, not a gate failure and not evidence that C5 "passed" or "failed" (`ADR-108` Decision 2: C5 is executed and disclosed, never
a favourable-outcome gate) — but per that same Decision 2, C5's only safeguard is complete disclosure, so the under-disclosure itself was a real defect, now corrected here rather than silently.

**[Rev 4 note, 2026-10-01]** The design-stage overlap-coefficient relaxation disclosed in section 13.2 as Amendments A1/A3 (`R5`: `0.25 -> 0.35 -> 0.45`, +80% cumulative) occurred before design freeze and is
not itself a violation, but independent review flagged it as substantive enough — and plausibly related to the comparison-group effect above — to warrant explicit founder-level acknowledgment alongside this
correction, rather than being read as a minor implementation detail.

### 13.5 What Phase 2c must still do

Fresh acceptance seeds `A` (3001-3030, never touched here) re-run the same classification rule once on the frozen composite; C5 recomputed on `A` for reference; the v2 ground truth and freeze manifest are
written only after that; independent review of the whole frozen benchmark follows; the engine is not evaluated on v2 until a separate `TASK`/`ADR` authorises F4 after `APPROVED`. The 6 `challenge_candidate`
targets and the 1 non-qualifying DECLARED_OVERLAP (`D02`) stay in their strata unless a future, explicitly fresh redesign+reacceptance cycle changes them (never by relaxing `tau` or by reusing 2001-2030).
