# TASK-107 Phase 2a - C5 (FC1) results: literal-plus-confounder composites for T01-T05

Author: STATISTICS. Read-only measurement. Definition and predictions: `c5-predictions.md` (committed `bf024bd`, before the script existed). Script: `c5_check.py` (committed unrun `74a35d5`; a numpy-import fix `a38b491`, also before any run). Raw per-seed output: `c5-raw-v2clean/`, `c5-raw-v1/`; aggregates `c5-rates-v2clean.json`, `c5-rates-v1.json`. No engine, no discovery search: only `_atoms` and the real `run_validation` (contract 1.3.0, `discovery-engine-v0.6.2` sha `fefceeaa...`, no `G17`) on hand-built rules. Seeds 1001-1030 (calibration seeds, NOT acceptance seeds: this is a design-time check and must be repeated on the fresh acceptance seeds in Phase 2c). Multiplicity family 60,000 (ADR-107 D8).

Draws: **v2-clean** = `synthetic_benchmark_v2.generate_v2(V2Config(seed), ())` (no targets, no v1 patterns; covariates identical to v1); **v1** = the real v1 generator at the same seed (P01-P09 present). Composite family per trap: literal `L` plus one or two engine-language atoms on that trap's `confounded_by` features (`booking_month` excluded, not an engine feature), depth <= 3, eligibility proxy (dev exposure >= 40, full-cohort exposure <= 40%); ranked by development-split Welch t (harm direction, primary outcome `contribution_margin_eur`); the top `K = 15` plus the bare literal are validated. Numbers are seeds out of 30 (Wilson 95% in the JSON).

| trap | draw | bare literal reaches `predictive_association` | bare literal reaches `shadow_policy`+ | best-of-15 composite reaches `predictive_association` | any composite reaches `shadow_policy`+ |
|---|---|---|---|---|---|
| T01 `manager=Manager 2` | v2-clean | 0/30 | 0/30 | 0/30 | 0/30 |
| T01 | v1 | 0/30 | 0/30 | 2/30 | 0/30 |
| T02 `supplier=Atlas` | v2-clean | 0/30 | 0/30 | 0/30 | 0/30 |
| T02 | v1 | 0/30 | 0/30 | 0/30 | 0/30 |
| T03 `acquisition_channel=paid_search` | v2-clean | 0/30 | 0/30 | **28/30** | 0/30 |
| T03 | v1 | **1/30** (seed 1023) | **1/30** (seed 1023: `adjusted_observational_association`, `shadow_policy`) | **30/30** | 0/30 |
| T04 `payment_method=bank_transfer` | v2-clean | 0/30 | 0/30 | 0/30 | 0/30 |
| T04 | v1 | 0/30 | 0/30 | **19/30** | 0/30 |
| T05 `manual_exception=true` | v2-clean | 0/30 | 0/30 | 0/30 | 0/30 |
| T05 | v1 | 0/30 | 0/30 | 0/30 | 0/30 |

Every composite that reached `predictive_association` (186 on v2-clean, 389 on v1) has `policy_readiness = experiment_only` and fails `G16_CANDIDATE_COMPOSITION_SAFETY` (k >= 2 rules cannot be promoted under contract 1.3.0). The only promotion observed is the bare `T03` literal (k = 1) on v1 seed 1023: `G06` passed, `G13`/`G14` failed, level `adjusted_observational_association`, readiness `shadow_policy`.

Typical `T03` composite (both draws): `paid_search AND discount_rate>=0.08` (optionally plus `installments`/`customer_type`): `discount_rate` is a `confounded_by` feature of `T03` and also a direct driver of the primary outcome (net revenue = price x (1 - discount)), so the composite carries a genuine association that the contract accepts at `predictive_association`.

## Prediction scorecard (`c5-predictions.md`)

* **P1** (bare literals reach predictive in 0/30 on both draws): **falsified** by one draw, `T03` on v1 seed 1023 (which also reached `shadow_policy`). All other bare rules 0/30.
* **P2** (v1: `T03` and `T04` composites >= 50%): **confirmed** (30/30 and 19/30).
* **P3** (v2-clean: every trap composite < 50% and at least three of five < 20%): **first clause falsified** (`T03` 28/30); second clause holds (`T01`, `T02`, `T04`, `T05` all 0/30).
* **P4** (composites reach `shadow_policy` in 0/30 of draws, `G16`): **confirmed**, 0/30 for every trap on both draws. Not covered by P4 and found here: a bare k = 1 `T03` literal can be promoted (1/30 on v1).
* **P5** (`T01`, `T02`, `T05` composites < 30% on both draws): **confirmed** (max 2/30).
* **P6** (implication conditional on P3): P3's first clause failed for exactly one trap, so the implication holds for four of five traps and not for `T03` (below).

## What this implies for the trap suite (taxonomy NOT redesigned; ADR-107 D5)

1. **On the clean v2 draw only `T03` is tempting.** Its composite reaches `predictive_association` in 28/30 draws; the composites of `T01`, `T02`, `T04`, `T05` reach it in 0/30 (best-of-15 by dev t; `T04` falls from 19/30 on v1 to 0/30; a plausible but untested reason is that v1's genuine `P06` (Tokyo, short lead, `bank_transfer`) adds real signal in exactly the regions `T04` composites select). For those four traps the contract rejects the composite on power/uncertainty grounds (`G03`/`G04`/`G05`/`G10`/`G12`) before any confounding gate could act, so a "no trap promoted" result carries no information about their confounding logic.
2. **No trap composite can reach `shadow_policy`** under contract 1.3.0 (`G16`), so "trap promoted" for a k >= 2 rule is structurally 0. Promotion safety is testable only through k = 1 rules, and there only `T03` on v1-like data ever got close (1/30). On clean v2 the bare-literal promotion rate is 0/30 for all five (Wilson upper bound 0.11).
3. **What the trap suite can honestly claim after v2 freeze**: the scorer's trap classification and the hard disqualifier `Tp` are exercised with real candidates only via `T03` on the clean draw (its composites reach `predictive_association`, which the v2 recovery contract treats as a hit, so the strict trap exemption and the trap-hit flag are meaningfully tested); `T01`, `T02`, `T04`, `T05` are inert on clean data. That is a property of the existing taxonomy on this data, reported for the founder; it is **not** fixed here.
4. **`FC1` cannot be closed by these numbers alone**: ADR-107 D5 makes C5 mandatory but sets no `tau_t`. On calibration seeds the measured facts are the table above; deciding whether "computed and disclosed" satisfies FC1, or whether `T01`/`T02`/`T04`/`T05` must be strengthened (a taxonomy/safety-research change outside `TASK-107`), is the single remaining founder-level item (spec section 11.3). C5 must be recomputed on the fresh acceptance seeds (Phase 2c) on the final composite generator.

## Limitations (as computed, not tuned)

* "Best composite" is a proxy (top 15 of the eligible literal-plus-confounder rules by development-split Welch t); a rule outside those 15 might do better, so the composite rates are lower bounds on "can reach". The family excludes composites with non-confounder atoms and excludes `booking_month` (not in the engine language).
* 30 calibration seeds (not acceptance seeds); v2-clean has no targets yet, so target-induced coupling with the traps' rows/levers is not represented (FC3 covers that on the composite generator).
* v1 seeds 1009-1012 of the v1-draw batch failed to start the first time (an unintended `ruff format` of the frozen `engine.py` was on disk for a moment, tripping `frozen_version_record()`; the file was restored, sha256 `fefceeaac20e8ff7...` re-verified, `git diff` on `engine.py` empty) and were re-run with the same script and arguments; the affected worker output was never written. No number was selected or discarded.
* The aggregator `rates` was extended after the raw run to also report the bare literal's promotion and evidence levels (raw JSON unchanged); the first aggregation printed the same composite counts.
