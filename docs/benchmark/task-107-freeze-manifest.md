# TASK-107 benchmark v2 (`travel-v2`) freeze manifest

**Owner:** STATISTICS (lead), ARCHITECT (support). **Recorded:** 2026-10-03, after the Phase 2c acceptance and C5 results exist (`docs/benchmark/task-107-evidence/rev5-acceptance-results.md`) and before any discovery/engine run on v2 — per `ADR-109` Decision 3 item 3. **Status:** this manifest plus the acceptance results document together constitute the frozen artifact handed to independent review; it does not itself declare `APPROVED` (`ADR-109` Decision 4, reserved for the reviewer/founder).

**Binding on:** `ADR-109` (full text), `ADR-108`, `ADR-107`, `ADR-106`, the specification Rev 1-5 (`docs/benchmark/task-107-benchmark-v2-specification.md`), `docs/benchmark/task-107-evidence/rev4-preregistration.md`, `docs/benchmark/task-107-evidence/rev5-acceptance-results.md`.

---

## 1. Hashes (sha256)

### 1.1 v2 generator and scorer (the files this phase is certifying)

| File | sha256 |
|---|---|
| `packages/analytics/src/policy_analytics/synthetic_benchmark_v2.py` | `2d6231001ec5ba4e526263e2ad7e67b84d651408be2183fcc024b927fc1627da` |
| `packages/analytics/src/policy_analytics/synthetic_benchmark_v2_targets.py` | `4a9e75a8d27284dbaa20ba0467d43871d0df20db6e16268ca01af208eb9d2059` |
| `packages/analytics/src/policy_analytics/benchmark_v2_scoring.py` | `0878811a737ad3608f2ee14568f10a67fc92fd052d866c261d44c9650a8ada1b` |

(`benchmark_v2_scoring.py`'s hash moved from its Rev 3 value `dcd2192d7bb1ad6a...` because of the Phase 2b Step 0 `ADR-108` Decision 3 change — `Target.assessed`, `trap_provenance`, the `assessed`-gated exemption; see section 5 below. No change to this file in Phase 2c.)

### 1.2 Frozen-engine components — confirmed unchanged before this phase's first run and after every one of its 6 commits

| File | sha256 |
|---|---|
| `packages/analytics/src/policy_analytics/discovery/__init__.py` | `28ece5a5738938efaff2733a13fbdb333d109042e22c6283f8d7f2c6d78c56c6` |
| `packages/analytics/src/policy_analytics/discovery/actionability.py` | `66243fe2451af8ca4f633ad093e1764ef5aca53ec9e8d0096fea55caee5a71f0` |
| `packages/analytics/src/policy_analytics/discovery/engine.py` | `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549` |
| `packages/analytics/src/policy_analytics/discovery/ranking.py` | `ea11b2f9d7011c0353e5b4879cc450f49d43d5353fd3b728c215b6924f3d55d9` |
| `packages/analytics/src/policy_analytics/discovery/ranking_signals.py` | `bd83ace80afae6c63a51020e0b495602b19f41cf7baa27f95ee6cf639933796f` |
| `packages/analytics/src/policy_analytics/validation/__init__.py` | `1880dbdb0343bffbf15419215bd8cd7b12a32b7e94f82534c27a20dcec581d6a` |
| `packages/analytics/src/policy_analytics/validation/apply.py` | `0c1df74cb648c573912da274981b6d328c6d175755b9ee90c5849fbe24047228` |
| `packages/analytics/src/policy_analytics/validation/composition_safety.py` | `78999f3554e74ef3a9d465e8ebdda30d9aea7d14c910263fd7537f2c6e8a8af8` |
| `packages/analytics/src/policy_analytics/validation/contract.py` | `a55fdc94c7e520cc4e287c6627d345e5a2335bfc1bd684db584218790b7403cd` |
| `packages/analytics/src/policy_analytics/validation/economic_impact.py` | `14e631870f8d59631b8369523865f7514c8f5873cbdbc41f67e88e846aa245a2` |
| `packages/analytics/src/policy_analytics/validation/exposure_disclosure.py` | `30e8db8988326a8b960ce936fbc853d9e5a73818041e58200d693a9792078df5` |
| `packages/analytics/src/policy_analytics/validation/grading.py` | `665e88666638ad59196a58c4759f2326f4f23208989086b6ce4e8c769bac17b8` |
| `packages/analytics/src/policy_analytics/validation/input_contract.py` | `4ed7abfeb3013c19df47c44ad85469bbd50420604a19f9cfc45e38aea9ec83e9` |
| `packages/analytics/src/policy_analytics/validation/report.py` | `801286591b69c4ca9b9fa963290ac0f276da64ac2173bb714ce8e83d5cccab65` |
| `packages/analytics/src/policy_analytics/synthetic_benchmark.py` (v1 generator) | `6ce81eb489580d2b8a81824b94d8fe868505b2027aa8b172af88e5ab323e8d52` |
| `scripts/evaluate_benchmark.py` (v1 scorer) | `13b141136e6cae78233f89311893d7402a2b09579937f61c34566b525e70930b` |
| `synthetic_data/evaluation/hidden_ground_truth.json` (v1 ground truth) | `5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506` |
| `synthetic_data/evaluation/checksums.json` | `b1df77f66b275d5c5eb4513b0929deec457f9a5674117062340d92206cd4d75f` |

Engine identity: `discovery-engine-v0.6.2`, `engine.py` sha256 prefix `fefceeaac20e8ff7` (full hash above), validation contract **1.3.0**, no `G17`. Verified identical immediately before Phase 2c's first run and immediately after each of its 6 commits (3 acceptance-oracle batches + 3 C5-composite batches) — see `docs/benchmark/task-107-evidence/rev5-acceptance-results.md` "Frozen-file verification".

### 1.3 Supporting evidence files cited by this manifest

| File | sha256 |
|---|---|
| `docs/benchmark/task-107-evidence/rev4-preregistration.md` | `19a7d83bef87faf47e8dd292f9d4470822b66dd075291fbcb24f7169f7ab1ee6` |
| `docs/benchmark/task-107-evidence/rev4-calibration-rates.json` | `0a0817a04bcf6c14987a2b2f44b2ad6d51a3ac5f453f515a7735caff6aa81091` |
| `docs/benchmark/task-107-evidence/rev4-c5-composite-rates.json` | `62e4019f77ab5f0b9d0f92156e66db92dedc0c55e8018ca9f434022b74a38324` |
| `docs/benchmark/task-107-evidence/rev5-acceptance-rates.json` | `6fc4c8d4e65a4f9b08e016214fd1fd04621ba430cd51b3878721ff91be52e42f` |
| `docs/benchmark/task-107-evidence/rev5-c5-composite-rates.json` | `48b0bb283755236162ae8047d2fa0836fc59581c0c8669c59ab82345877f7186` |

**No v2 ground truth exists as a single frozen per-row file the way v1's `hidden_ground_truth.json` does.** v2 is a generator (`synthetic_benchmark_v2.py`) plus a fixed set of `TargetSpec`/`TargetDesign` records (`synthetic_benchmark_v2_targets.py`), evaluated across many disjoint seeds rather than materialized once; there is no single "the v2 dataset". The canonical v2 ground truth is therefore: (a) the 20 `TargetDesign` records in the hashed file above, each a fixed rule (real `Condition`s) plus a declared class, and (b) the final-class table in section 2 below, which is this manifest's record of what each target actually is after acceptance. This is stated explicitly rather than fabricating a v1-shaped artifact that would misrepresent the design.

---

## 2. Target definitions and final classes

20 targets total, declared in Phase 2b (`synthetic_benchmark_v2_targets.py`, `TargetDesign` records), unchanged since. Final class is the Phase 2c **acceptance**-seed outcome (`rev5-acceptance-results.md`), which supersedes the Phase 2b **calibration**-seed outcome per the pre-declared "the class follows the outcomes, never the intention" rule (`rev4-preregistration.md` section 5) and `ADR-108`'s winner's-curse-guard separation of calibration and acceptance.

| id | rule | conditions | calibration verdict (2001-2030) | **final class (3001-3030, binding)** |
|---|---|---|---|---|
| C01 | `destination=Lisbon AND acquisition_channel=partner` | 2 | core_candidate (30/30) | **Core-FAIL** (29/30, CP-LB 0.8514) |
| C02 | `destination=Rome AND customer_segment=corporate` | 2 | core_candidate (30/30) | **Core** (30/30, CP-LB 0.9050) |
| C03 | `product_category=premium AND acquisition_channel=partner AND discount_rate>=0.08` | 3 | challenge_candidate (15/30) | Challenge (non-binding acceptance rate 14/30, reported for completeness only) |
| C04 | `supplier=Cedar AND customer_segment=leisure AND trip_duration_days>=8` | 3 | core_candidate (30/30) | **Core** (30/30, CP-LB 0.9050) |
| C05 | `supplier=DeltaSun AND discount_rate>=0.12` | 2 | challenge_candidate (29/30) | Challenge (non-binding acceptance rate 27/30) |
| C06 | `destination=Reykjavik AND customer_type=returning AND discount_rate>=0.05` | 3 | core_candidate (30/30, outcome-promoted; designed Challenge) | **Core** (30/30, CP-LB 0.9050) |
| C07 | `supplier=BlueWing AND acquisition_channel=direct AND party_size>=3` | 3 | core_candidate (30/30) | **Core** (30/30, CP-LB 0.9050) |
| C08 | `payment_method=wallet` | 1 | core_candidate (30/30) | **Core** (30/30, CP-LB 0.9050) |
| C09 | `destination=Tokyo AND customer_segment=leisure AND product_category=standard` | 3 | core_candidate (30/30) | **Core** (30/30, CP-LB 0.9050) |
| C10 | `customer_type=new AND acquisition_channel=referral AND trip_duration_days>=6` | 3 | core_candidate (30/30) | **Core-FAIL** (29/30, CP-LB 0.8514) |
| C11 | `destination=Tokyo AND customer_segment=family` | 2 | core_candidate (30/30) | **Core** (30/30, CP-LB 0.9050) |
| C12 | `acquisition_channel=direct AND product_category=premium AND customer_segment=leisure` | 3 | core_candidate (30/30) | **Core** (30/30, CP-LB 0.9050) |
| C13 | `destination=Reykjavik AND product_category=standard AND payment_method=card` | 3 | core_candidate (30/30) | **Core-FAIL** (29/30, CP-LB 0.8514) |
| C14 | `customer_segment=leisure AND supplier=BlueWing AND discount_rate>=0.08` | 3 | core_candidate (30/30) | **Core** (30/30, CP-LB 0.9050) |
| C15 | `customer_type=returning AND acquisition_channel=direct AND trip_duration_days>=6` | 3 | core_candidate (30/30) | **Core** (30/30, CP-LB 0.9050) |
| H01 | `supplier=BlueWing AND destination=Zanzibar AND customer_type=new` | 3 | core_candidate (30/30, outcome-promoted; designed Challenge) | **Core** (30/30, CP-LB 0.9050) |
| H02 | `supplier=DeltaSun AND customer_segment=corporate AND product_category=standard` | 3 | challenge_candidate (28/30) | Challenge (non-binding acceptance rate 30/30) |
| H03 | `customer_type=returning AND payment_method=card AND trip_duration_days>=8` | 3 | challenge_candidate (29/30) | Challenge (non-binding acceptance rate 29/30) |
| D01 | `acquisition_channel=paid_search AND destination=Rome AND customer_type=returning` | 3 | oracle_qualified DECLARED_OVERLAP (`T03`) | **DECLARED_OVERLAP, oracle_qualified** (30/30, CP-LB 0.9050, C4 max exposure-J 0.0918) |
| D02 | `payment_method=bank_transfer AND product_category=standard AND discount_rate>=0.08` | 3 | not oracle_qualified DECLARED_OVERLAP (`T04`), 18/30 | DECLARED_OVERLAP, not oracle_qualified (acceptance rate 17/30, dominant gate `G12_ROBUSTNESS`) |

**Final Core set (11): `C02, C04, C06, C07, C08, C09, C11, C12, C14, C15, H01`.** `C01`, `C10`, `C13` are Core-FAIL, permanently recorded as such; they are not redesigned, re-run, or dropped quietly within this version. `D01` is the sole `oracle_qualified` DECLARED_OVERLAP target, reported in its own stratum. `C03`, `C05`, `H02`, `H03` remain Challenge-only, never Core, exactly as `ADR-109` instructed (informational acceptance-seed rates shown above, non-binding). `D02` remains non-qualifying DECLARED_OVERLAP.

11 Core targets satisfies `ADR-107` D3's "at least 8 oracle-qualified core positive targets" requirement.

---

## 3. Thresholds (frozen, `ADR-107`/`ADR-108`/`ADR-109`)

| Constant | Value | Role |
|---|---|---|
| `tau` | 0.90 | Oracle-qualification bar, applied as a one-sided 95% Clopper-Pearson lower bound (not the point rate) |
| `theta_J` | 0.50 | Specific-recovery exposure-Jaccard floor |
| `theta_p` | 1.00 | Specific-recovery effective-condition precision floor |
| `nu` | 0.05 | Vacuity threshold: removing a condition must grow true exposure by >= this fraction for the condition to be load-bearing |
| `eta` | 0.15 | Exact-recovery threshold tolerance |
| `eps_x` | 0.10 | Exact-recovery exposure-equivalence tolerance |
| `rho_rep` | 0.80 | L5 per-draw engine-language representability floor (projection Jaccard) |
| `theta_T` | 0.90 | Trap exposure-equivalence floor (`trap_hit` reformulation) |
| Multiplicity family (primary) | **60,000** | `ADR-107` D8; independent of any engine output; used for every acceptance/calibration verdict in this manifest |
| Multiplicity family (sensitivity) | 36,791 / 26,213 | Engine-output-derived continuity sensitivities only, never acceptance inputs |
| `N` | 10,000 | Rows per generator draw |
| `min_exposed_records` | 50 | Scoreability floor (affected rows) |
| `min_n` (dev) | 40 | Scoreability floor (development-split exposed rows) |
| C4 (DECLARED_OVERLAP separability) | exposure-J <= 0.30 | Bare-trap-literal exposure vs. target's affected set, every seed |
| R5 (design-stage structural overlap-coefficient bound) | **0.45 (final)** | See section 6, provenance |
| Acceptance/calibration seed set size | >= 30, fresh, disjoint per role | `ADR-107` D4/D12 |
| `max_conditions` (engine language) | 3 | L1 |

---

## 4. RNG / seed ranges, full TASK-107 history, with disposition

| Range | Role | Disposition |
|---|---|---|
| `1001-1030` | Phase 1/2a prototype oracle calibration (clean v2, no composite) | **Spent** |
| `9001-9010` | Design-stage pilot (Phase 2b), real-oracle result seen before the Step 1 pre-declaration commit; disclosed | **Spent** (never reused for calibration/acceptance/final) |
| `9101-9110` | Confirm-only pilot #1 (design-spec E) | **Spent** |
| `9111-9120` | Confirm-only pilot #2 (design-spec F) | **Spent** |
| `9121-9130` | Confirm-only pilot #3 (final design-spec G) | **Spent** |
| `2001-2030` | **Phase 2b calibration** (composite generator, 20 targets, 3 families; used to classify intended Core/Challenge/DECLARED_OVERLAP) | **Spent — calibration** |
| `2101-2130` | Calibration round 2 reserve | **Untouched** (not needed; 14 of 20 reached `core_candidate` at round 1) |
| `3001-3030` | **Phase 2c acceptance `A`** (this phase: one-shot acceptance oracle run + informational C5) | **Spent — acceptance** (closed before use; verified no prior reference via whole-repo grep; now the binding result) |
| `3101-3130` | Acceptance reserve `A'` | **Untouched** (reserved for a future, explicitly fresh redesign+reacceptance cycle only; never for `C01`/`C10`/`C13` inside this version) |
| `3201-3230` | Acceptance reserve `A''` | **Untouched** |
| `4001-4030` | Final evaluation `E` (first blind engine run, a later, separately authorized step) | **Reserved, untouched** |
| `4101-4130` | Final evaluation reserve | **Reserved, untouched** |

No seed outside `2001-2030` (calibration, spent) and `3001-3030` (acceptance, now spent) was used to produce any binding verdict in this manifest. The pilot ranges (`9001-9010`, `9101-9130`) were used only for design-stage structural confirmation and dose selection, never for a calibration or acceptance verdict, and are disclosed as spent per `rev4-preregistration.md`.

---

## 5. Scorer semantics

`packages/analytics/src/policy_analytics/benchmark_v2_scoring.py` (current hash in section 1.1):

* **Coverage (soft recovery).** The existing v1-style definition: a candidate finds part of the true signal (lenient match on the affected-row set). Never the headline.
* **Specific recovery (headline).** `SPEC(C, P)` iff exposure-Jaccard `J_e(C, P) >= theta_J` (0.50) **and** effective-condition precision `Cp(C, P) >= theta_p` (1.00) **and** the candidate's effective condition set `K(C)` is non-empty, with **sequential, tie-broken vacuity**: a condition is dropped from `K` if removing it does not shrink true exposure by >= `nu` (0.05); the construction is sequential with a canonical tie-break so `K(T_P) = T_P` for every true target (verified on every acceptance/calibration seed, zero violations). Credit on ties goes to the highest-`J` target.
* **Exact recovery.** Raw canonical-form bijection, checked **before** vacuity relaxation (or reported as `exact_after_vacuity` if only the vacuity-relaxed form bijects), with threshold tolerance `eta` (0.15) and exposure-equivalence tolerance `eps_x` (0.10); a separate strict diagnostic, never the mandatory headline denominator, and may exceed Specific because Exact and Coverage need no validation clause.
* **Strict trap exemption (`ADR-107` author pin, `ADR-108` Decision 3).** A candidate hit on trap `T` with literal `L` is exempt from `trap_hit(C,T)` only if: (a) some target `P` whose canonical rule contains `L` satisfies the Specific metric match (`J_e >= theta_J`, `Cp >= theta_p`, non-empty `K`) against `C`, **and** (b) `C` reaches `predictive_association` or above, **and** (c) `P` is `scoreable` **and** `assessed` (`ADR-108` Decision 3: no exemption for an unscoreable or NOT-ASSESSED target). Provenance per hit: `trap_provenance[trap_id]` in `{"exempt", "confirmed_trap", "no_exemption_unscoreable_target", "no_exemption_validation_not_assessed"}`; `confirmed_trap` only when every predicate was computable and failed. `safety.no_exemption_not_confirmed_trap` lists every denial-for-unverifiability hit, kept separate from genuine `trap_hits` — **absence of verifiability is never recorded as positive evidence of a trap.**
* **Strata, never mixed.** Core (own denominator), Challenge (own `Challenge Recall`, own denominator), DECLARED_OVERLAP (own metric, `oracle_qualified` sub-flag; never in Core or Challenge), out-of-language (own denominator, never an ordinary FN), Underpowered (no denominator at all). Discovery metrics (`coverage_recall`, `specific_recall`, `exact_recall`) computed over Core (`P+`) only; safety metrics (trap hits, promotions, hard disqualifiers) computed over the trap suite (`T`) only — no blended score, ever.
* **Classification rule applied in this manifest** (`rev4-preregistration.md` section 5, acceptance-binding version): **Core** iff not `declared_overlap` AND `k = 30/30` AND one-sided 95% Clopper-Pearson lower bound `>= 0.90` AND every structural check holds on all 30 seeds. **29/30 is Core-FAIL, unconditionally** — this is what produced the `C01`/`C10`/`C13` result in section 2.

---

## 6. R5 full provenance (overlap-coefficient structural bound) — permanent record, not reverted

**R5** is a *design-stage structural* rule (`rev4-preregistration.md` section 6): the pairwise overlap coefficient `|A_i & A_j| / min(|A_i|,|A_j|)` between any two targets' affected sets must stay under a bound, checked on design seeds `9001-9010` before any calibration seed was drawn. It is a design-time guard against two targets being near-duplicates of each other on the generator's row space, not a scoring threshold and not a gate in `run_validation`.

| Value | When | Commit | Rationale (as stated at the time) |
|---|---|---|---|
| **0.25** (original) | Step 1 pre-declaration, before any design iteration beyond the first was checked | `f8527cd` ("TASK-107 Phase 2b Step 1: pre-declarations...") | Initial, arbitrary-but-principled conservative bound chosen before seeing any design-seed check output. |
| **0.35** for Challenge-involving pairs (Amendment A1); Core-Core/Core-overlap pairs kept at 0.25 | Design stage, before the design-freeze commit, after seeing design-seed check output | `8a5c636` ("TASK-107 Phase 2b: design freeze ... amendments A1-A3 ... committed before any calibration run on 2001-2030") | Challenge designs in the then-current design iteration violated the 0.25 bound (observed max 0.32, `H03`\|`D01`); rather than iterate further, the bound was relaxed for pairs involving a Challenge candidate only. Disclosed in `rev4-preregistration.md` section 9 as "a relaxation made after seeing the check output". |
| **0.45** for every pair (Amendment A3), final | Design stage, same commit as A1, before design freeze | `8a5c636` | After Amendment A2 added three new Core candidates (`C13`-`C15`) and a second confirm-only pilot, the 0.35 bound was still violated (observed max 0.452, `C15`\|`H03`); amended to a single 0.45 bound for every pair. Stated rationale: the many shared common categorical levels (`returning`, `standard`, `card`, `corporate`) made a tighter bound incompatible with rule R3 (every pair of designs shares at most one categorical literal) without further design iteration; overlap is additive-effect coupling whose actual consequence is measured on the composite in calibration, not assumed from the static coefficient alone. Disclosed in `rev4-preregistration.md` section 11 and spec section 13.2/13.3. |

**Both amendments were made and committed entirely during Phase 2b design freeze (commit `8a5c636`, 2026-09-30/10-01), before the Phase 2b calibration run on `2001-2030`, and long before the Phase 2c acceptance seeds `3001-3030` existed or were drawn (2026-10-03).** This satisfies `ADR-109` Decision 2's condition ("conditional on independent review confirming `R5` was fixed before the acceptance seeds existed or were run") as a matter of plain commit-order fact, verifiable via `git log`. `R5` is **not reverted to 0.25** in this manifest or anywhere else — `ADR-109` Decision 2 explicitly forbids reverting it now that calibration/acceptance evidence has been seen, since doing so would itself be exactly the kind of after-the-fact threshold adjustment this project's discipline (`ADR-007`/`ADR-012`) exists to prevent. The cumulative relaxation is +80% relative (0.25 -> 0.45) and is recorded here, permanently, as a material design choice — not routine prose, not softened, not hidden in a footnote.

**Independent review flagged R5's relaxation (Phase 2b) as plausibly related to the C5-composite comparison-group shift** (spec section 13.4, Rev 4 note) — both are disclosed side by side in this manifest and in `rev5-acceptance-results.md`'s C5 table, without either one being used to adjust the other.

---

## 7. Acceptance outcomes (summary; full detail in `rev5-acceptance-results.md`)

* **14 ADR-109-listed Core candidates: 11 PASS (`C02,C04,C06,C07,C08,C09,C11,C12,C14,C15,H01`), 3 FAIL (`C01,C10,C13`, each 29/30, CP-LB 0.8514).**
* **D01 (DECLARED_OVERLAP): PASS, `oracle_qualified` (30/30, CP-LB 0.9050, C4 max exposure-J 0.0918).**
* Non-binding, reported for completeness: `C03` 14/30, `C05` 27/30, `H02` 30/30, `H03` 29/30 (all Challenge-only, never Core); `D02` 17/30 (non-qualifying DECLARED_OVERLAP).
* **C5 on 3001-3030 (informational only, never a gate): T01 bare 0/30 / composite 21/30; T02 bare 29/30 / composite 29/30; T03 bare 28/30 / composite 10/30; T04 bare 1/30 / composite 0/30; T05 bare 0/30 / composite 1/30. No cell reaches `shadow_policy` or above for any trap.**
* No seed set was extended, supplemented, or re-run after seeing any result. No Core-FAIL target was redesigned, repaired, or substituted inside this version.

This manifest and `rev5-acceptance-results.md` together are the frozen artifact for independent review. The engine has not been run on any v2 draw at any point in `TASK-107`'s history, including this phase.
