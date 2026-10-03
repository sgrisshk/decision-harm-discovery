# TASK-107 Phase 2c — acceptance results on seeds 3001-3030 (one-shot, closed before use)

**Owner:** STATISTICS (lead), ARCHITECT (support). **Recorded:** 2026-10-03. **Binding on:** `ADR-109` (read in full), `ADR-108`, `ADR-107`, `ADR-106`, the spec (`docs/benchmark/task-107-benchmark-v2-specification.md`, Rev 1-4 and Rev 5 below), the scorer (`benchmark_v2_scoring.py`), the 20 target designs (`synthetic_benchmark_v2_targets.py`), and the Phase 2b evidence (`rev4-preregistration.md`, `rev4-calibration-rates.json`, the corrected C5-composite table in spec section 13.4).

**Scope and binding facts, stated up front.** This is the one-shot acceptance run `ADR-109` Decision 3 item 1 requires on seeds 3001-3030. Those seeds were verified closed before use (`git grep` of the whole repository for `3001`/`3030`/any file under `3001-3030` before this run found only prose references to the *reserved range* in `TASKS.md`, `DECISIONS.md` and the spec — no raw output, no per-seed file, nothing touched). The run uses the real contract oracle (`run_validation`, contract 1.3.0) on the composite generator with all 20 Phase 2b targets active simultaneously (`docs/benchmark/task-107-evidence/v2_oracle.py`, unmodified from Phase 2b, called `batch`/`rates`), same method as the Phase 2b calibration run. **No engine or discovery run occurred on any v2 draw** — only the atom-grid builder `_atoms`, `build_projection`, and the real `run_validation` touch engine-package code, exactly as in every prior phase. Frozen-file sha256 (`engine.py`, `validation/contract.py`, `discovery/*.py`, `validation/*.py`, v1 `synthetic_benchmark.py`, v1 `scripts/evaluate_benchmark.py`, v1 `hidden_ground_truth.json`, v1 `checksums.json`) were verified **identical before the run and after every commit** (see "Frozen-file verification" below); no `ruff format` was run over `packages/`.

Raw output: `docs/benchmark/task-107-evidence/rev5-acceptance-raw/` (30 files, one per seed, all 20 targets, 3 families each — `60000` primary, `36791`/`26213` sensitivity-only), committed in 3 batches (`87133cb` seeds 3001-3006, `6673975` seeds 3007-3016, `f03d437` seeds 3017-3030, each preceded/followed by a frozen-hash check). Rates: `rev5-acceptance-rates.json` (sha256 `6fc4c8d4e65a4f9b08e016214fd1fd04621ba430cd51b3878721ff91be52e42f`).

## Decision 3 item 1 — acceptance results, 14 Core candidates (ADR-109's exact list) plus D01

Core requires 30/30 (one-sided 95% Clopper-Pearson lower bound >= 0.90, computed `0.9050` at 30/30, `0.8514` at 29/30). **29/30 is Core-FAIL — no exceptions, no extension, no re-run.**

| id | k/30 @60,000 | CP-LB (one-sided 95%) | verdict | failing seed(s) | failure detail |
|---|---|---|---|---|---|
| C01 | 29/30 | 0.8514 | **Core-FAIL** | 3016 | `descriptive_observation`; failed gates `G09_SIMPSON_AND_HETEROGENEITY`, `G13_IDENTIFICATION_DESIGN`, `G14_RANDOMIZATION_INTEGRITY`, `G16_CANDIDATE_COMPOSITION_SAFETY` (none of these are LEVEL2; `level2_failed_gates` empty) |
| C02 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| C04 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| C06 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| C07 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| C08 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| C09 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| C10 | 29/30 | 0.8514 | **Core-FAIL** | 3001 | `descriptive_observation`; `level2_failed_gates = [G10_TEMPORAL_STABILITY]` ("holdout retains 50% of development magnitude (floor 50%)") |
| C11 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| C12 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| C13 | 29/30 | 0.8514 | **Core-FAIL** | 3022 | `descriptive_observation`; `level2_failed_gates = [G10_TEMPORAL_STABILITY]` ("holdout retains 44% of development magnitude (floor 50%)") |
| C14 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| C15 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| H01 | 30/30 | 0.9050 | **Core-PASS** | — | — |
| D01 (DECLARED_OVERLAP) | 30/30 | 0.9050 | **oracle_qualified** (C4 max exposure-J 0.0918 <= 0.30, all 30 seeds) | — | — |

**Result: 11 of the 14 Core candidates PASS acceptance; 3 (`C01`, `C10`, `C13`) FAIL at 29/30 and are not Core in this version.** `D01` passes its own `oracle_qualified` acceptance test (30/30, CP-LB 0.9050, C4 holds on every seed). Sensitivity families `36,791` and `26,213` give identical `k` to the primary `60,000` for every one of these 15 rows (checked; no family-size coincidence) — see the full table below.

**Non-binding, reported for completeness only (per `ADR-109` Decision 3 item 1's "you may still compute their acceptance-seed rates for completeness if useful, clearly labeled as non-binding"):**

| id | class | k/30 @60,000 | CP-LB |
|---|---|---|---|
| C03 (Challenge-only) | Challenge | 14/30 | 0.3085 |
| C05 (Challenge-only) | Challenge | 27/30 | 0.7614 |
| H02 (Challenge-only) | Challenge | 30/30 | 0.9050 |
| H03 (Challenge-only) | Challenge | 29/30 | 0.8514 |
| D02 (non-qualifying DECLARED_OVERLAP) | DECLARED_OVERLAP | 17/30 | 0.4016 | not oracle_qualified (dominant gate `G12_ROBUSTNESS`, 13/30 seeds) |

None of these five are treated as Core candidates in this phase, per `ADR-109`'s explicit instruction; they were never part of the 14-item acceptance list and their acceptance-seed rates do not gate anything.

**Full per-target table, all three families, all 20 targets (sensitivity only for 36,791/26,213):**

| id | declared class | k/30 @60,000 | k/30 @36,791 | k/30 @26,213 | CP-LB @60,000 |
|---|---|---|---|---|---|
| C01 | Core | 29 | 29 | 29 | 0.8514 |
| C02 | Core | 30 | 30 | 30 | 0.9050 |
| C03 | Challenge | 14 | 14 | 14 | 0.3085 |
| C04 | Core | 30 | 30 | 30 | 0.9050 |
| C05 | Challenge | 27 | 27 | 27 | 0.7614 |
| C06 | Core | 30 | 30 | 30 | 0.9050 |
| C07 | Core | 30 | 30 | 30 | 0.9050 |
| C08 | Core | 30 | 30 | 30 | 0.9050 |
| C09 | Core | 30 | 30 | 30 | 0.9050 |
| C10 | Core | 29 | 29 | 29 | 0.8514 |
| C11 | Core | 30 | 30 | 30 | 0.9050 |
| C12 | Core | 30 | 30 | 30 | 0.9050 |
| C13 | Core | 29 | 29 | 29 | 0.8514 |
| C14 | Core | 30 | 30 | 30 | 0.9050 |
| C15 | Core | 30 | 30 | 30 | 0.9050 |
| H01 | Core | 30 | 30 | 30 | 0.9050 |
| H02 | Challenge | 30 | 30 | 30 | 0.9050 |
| H03 | Challenge | 29 | 29 | 30 | 0.8514 |
| D01 | DECLARED_OVERLAP | 30 | 30 | 30 | 0.9050 |
| D02 | DECLARED_OVERLAP | 17 | 17 | 17 | 0.4016 |

Structural checks (`K(T)=T` at `nu=0.05`, on-grid, projection-Jaccard = 1.0, scoreable) hold on every one of the 30 acceptance seeds for every one of the 20 targets — zero violations (checked programmatically, same as Phase 2b). The three Core-FAILs are pure evidence-level failures (one seed each falling to `descriptive_observation` for structural/temporal reasons), not structural-check violations.

## Decision 4 — final Core count for this version

**14 intended Core candidates -> 11 Core in this version** (`C01`, `C10`, `C13` are Core-FAIL and are NOT redesigned, NOT re-run on other seeds, and NOT dropped quietly — they are recorded here, plainly, as Core-FAIL). Final Core list: `C02, C04, C06, C07, C08, C09, C11, C12, C14, C15, H01` (11 targets) plus `D01` as the one `oracle_qualified` DECLARED_OVERLAP target (reported in its own stratum, never mixed into the Core denominator). **11 >= 8, so `ADR-107` D3's minimum-Core requirement is still met.** No repair, redesign, or seed substitution was performed on `C01`/`C10`/`C13`; per `ADR-109` Decision 3 item 4, any future rescue of these three would require a new target/version and a completely fresh acceptance set under `D12` — not inside this version.

## Decision 3 item 2 — C5 on 3001-3030 (informational only; full five-trap disclosure, bare AND composite)

Re-run of the same pre-declared protocol as the corrected Phase 2b table (`c5_composite.py`, unmodified; same best-of-15 composite-by-development-t search over engine-language conjunctions containing each trap's literal, family 60,000). Raw: `docs/benchmark/task-107-evidence/rev5-c5-composite-raw/` (30 files, committed in 3 batches — `ca396cc` seeds 3001-3005, `007a083` seeds 3006-3017, `1d66d52` seeds 3018-3030). Rates: `rev5-c5-composite-rates.json` (sha256 `48b0bb283755236162ae8047d2fa0836fc59581c0c8669c59ab82345877f7186`).

**Per `ADR-109` Decision 3 item 2: this result is not an admission condition for the benchmark and does not trigger any v2 change in this cycle, regardless of outcome. All five traps' bare and composite rates are disclosed in full below — none omitted, including ones that look inert.**

| Trap | Bare predictive (k/30) | Bare promoted to shadow_policy+ | Composite-rule predictive (k/30, best-of-15) | Composite promoted to shadow_policy+ | Dominant gate on top-ranked composite |
|---|---|---|---|---|---|
| T01 | 0/30 | 0/30 | **21/30** | 0/30 | `G12_ROBUSTNESS` 9, `G05_MULTIPLE_COMPARISONS` 8, `G10_TEMPORAL_STABILITY` 2 |
| T02 | 29/30 | 0/30 | 29/30 | 0/30 | `G05_MULTIPLE_COMPARISONS` 30, `G03_SAMPLE_ADEQUACY` 28, `G04_UNCERTAINTY` 22, `G10_TEMPORAL_STABILITY` 14, `G12_ROBUSTNESS` 14 |
| T03 | 28/30 | 0/30 | 10/30 | 0/30 | `G05_MULTIPLE_COMPARISONS` 18, `G12_ROBUSTNESS` 11, `G10_TEMPORAL_STABILITY` 5, `G03_SAMPLE_ADEQUACY` 3 |
| T04 | 1/30 | 0/30 | 0/30 | 0/30 | `G05_MULTIPLE_COMPARISONS` 30, `G10_TEMPORAL_STABILITY` 9, `G03_SAMPLE_ADEQUACY` 2, `G12_ROBUSTNESS` 2 |
| T05 | 0/30 | 0/30 | 1/30 | 0/30 | `G05_MULTIPLE_COMPARISONS` 28, `G10_TEMPORAL_STABILITY` 12, `G03_SAMPLE_ADEQUACY` 6, `G12_ROBUSTNESS` 4 |

**No cell reaches `shadow_policy` or above in either the bare or composite form, for any trap, on any of the 30 acceptance seeds — `G16_CANDIDATE_COMPOSITION_SAFETY` still structurally blocks promotion for every k>=2 rule under contract 1.3.0.** This matches the Phase 2b (2001-2030) corrected finding exactly in direction and approximate magnitude:

| Trap | Phase 2b composite (2001-2030) bare | Phase 2c acceptance (3001-3030) bare | Phase 2b composite-rule | Phase 2c composite-rule |
|---|---|---|---|---|
| T01 | 0/30 | 0/30 | 22/30 | 21/30 |
| T02 | 27/30 | 29/30 | 29/30 | 29/30 |
| T03 | 29/30 | 28/30 | 11/30 | 10/30 |
| T04 | 0/30 | 1/30 | 0/30 | 0/30 |
| T05 | 0/30 | 0/30 | 0/30 | 1/30 |

The small seed-to-seed drift (e.g. T01 22 -> 21, T04 0 -> 1, T05 0 -> 1) is consistent with ordinary sampling variation on a fresh, disjoint 30-seed draw, not a new mechanism; it is disclosed here rather than smoothed over. The underlying mechanism (same as Phase 2b's corrected disclosure) is unchanged: with 20 targets dosed simultaneously, `_outcome_columns` additively sums every active target's dosing on rows its predicate matches, shifting the comparison-group baseline used when grading any one trap/composite. This is a disclosed property of the trap suite under a dense composite, not a gate failure, not an RNG-isolation violation, and — per `ADR-108` Decision 2 and `ADR-109` Decision 3 item 2 explicitly — **not treated as an admission condition and not used to change v2 in this cycle.**

## Frozen-file verification

`frozen_hashes.py` output identical before the acceptance run, after each of the 6 commits (3 acceptance-oracle batches + 3 C5-composite batches), and after this results write-up:

```
fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549  packages/analytics/src/policy_analytics/discovery/engine.py
a55fdc94c7e520cc4e287c6627d345e5a2335bfc1bd684db584218790b7403cd  packages/analytics/src/policy_analytics/validation/contract.py
6ce81eb489580d2b8a81824b94d8fe868505b2027aa8b172af88e5ab323e8d52  packages/analytics/src/policy_analytics/synthetic_benchmark.py
13b141136e6cae78233f89311893d7402a2b09579937f61c34566b525e70930b  scripts/evaluate_benchmark.py
5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506  synthetic_data/evaluation/hidden_ground_truth.json
b1df77f66b275d5c5eb4513b0929deec457f9a5674117062340d92206cd4d75f  synthetic_data/evaluation/checksums.json
```

(plus every file under `discovery/*.py` and `validation/*.py`, all identical across every check — full listing in the freeze manifest). **No engine or discovery run occurred on any v2 draw in this phase; `ruff format` was never run over `packages/`.**

## What this result means for Phase 2c's two legitimate outcomes (`ADR-109` Decision 4)

No substantive defect in the frozen artifact was found by this run: the three Core-FAILs are exactly the kind of result the acceptance design is supposed to be able to produce (a target that calibrated 30/30 on 2001-2030 and fails 29/30 on a fresh, disjoint set is direct evidence of calibration/acceptance sampling variation at a lower bound that is deliberately strict, not evidence of a scorer or generator bug). This result is handed to independent review as a candidate `APPROVED` outcome with an honest, disclosed 11-of-14 Core yield; it is not this document's place to declare `APPROVED` itself.
