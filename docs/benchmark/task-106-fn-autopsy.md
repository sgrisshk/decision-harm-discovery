# TASK-106 - FN autopsy of P01-P07 (travel benchmark) at the frozen engine

**Owner:** STATISTICS (lead), ML_DISCOVERY and ARCHITECT (support). **Recorded:** 2026-09-24 (task released by `ADR-105`).
**Forensic only.** Nothing in `engine.py`, any gate, threshold, `apply.py`, `contract.py`, the generator, the catalogue or the recall
denominator was changed. Raw `2/7` is left as recorded. No benchmark-v2 design (that is `TASK-107`) and no engine fix is proposed here.

## 0. Frozen version, confirmed and recorded

`scripts/diagnose_task106_fn_autopsy.py` refuses to run unless all of these hold, and records them in every raw file
(`frozen_version`): `DISCOVERY_METHOD_VERSION = discovery-engine-v0.6.2`; `engine.py` sha256
`fefceeaac20e8ff7...` (full value in the raw JSON); validation contract `1.3.0`; no `G17` in `GateId`;
`DiscoveryConfig()` defaults as in `TASK-103` section 1. Base commit `c2647e4`.

"P01-P07" here means the seven scoreable patterns `{P01, P02, P03, P04, P06, P08, P09}` (`decision-gate.md` "Fixed denominators";
`P05`/`P07` are excluded). The "two TPs" are `P01` and `P06`; the "five FNs" are `P02, P03, P04, P08, P09` (the `2/7` partition).

## 1. Method and two definitions that had to be pinned

**Matching.** `TASK-028` counts a candidate as recovering a pattern when its exposed-set recall of the pattern's affected records is
>= 0.5 (*lenient*). A broad rule can satisfy this for many patterns at once. This document therefore reports, everywhere, both:

* **lenient** = recall >= 0.5 (TASK-028, unchanged), and
* **specific** = Jaccard(candidate exposed set, pattern affected set) >= 0.5 (declared before any Jaccard was computed;
  sensitivity at 0.3 is in the raw files and never changes a conclusion below).

Fidelity check: my per-candidate lenient matches, evidence levels and readiness reproduce `TASK-103` run 1's `evaluation.json` exactly (15/15).
The real `discover_candidates()` at the frozen version also reproduces `TASK-103`'s 15 candidates condition-for-condition (36,791 hypotheses).

**Oracle detectability** is measured two ways, both through the real, unmodified validation contract and both against a fixed
multiplicity family of 36,791 (`TASK-103`'s evaluated-hypotheses count; 26,213 as a sensitivity):

* **projection oracle** - the tightest rule the engine's vocabulary can express (`TASK-069`'s construction), validated with `run_validation`.
  Detectable = reaches `predictive_association` (`TASK-028`'s recovery bar). This is what an engine could ever output.
* **exact-rule oracle** - the pattern's exact ground-truth membership (including calendar conjuncts the vocabulary lacks) as one
  idealised Boolean atom, validated by the same contract. It tests statistical detectability at the standard N only; it is not representable.

**Sampling error.** Ground-truth affected counts are random draws. The unchanged generator was re-run with 60 additional seeds
(101-160) plus the committed seed (61 realisations, the analytical builder unchanged; the committed seed reproduces the committed
dataset identity `b6128eb3...`). Rates carry Wilson 95% intervals. The real engine was additionally run end-to-end on the committed
draw and on 6 further draws (7 total, seeds 101-106 + committed).

## 2. Summary table

Committed draw unless stated. "Rate" = fraction of the 61 generator realisations (P08: of the 27 in which it is scoreable, n>=50).

| Pattern | Detectable (oracle, predictive) | Search-eligible (v0.6.2) | Discovered: lenient / specific | Validated | Safety-eligible | Promoted | First failure | Class | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| **P01** (TP) | projection 61/61 [94-100%]; exact 61/61 | yes; pool rank 162/25,338, clears floor | lenient yes (13 predictive candidates); **specific no** (best J 0.26) | lenient candidates yes; precise rule yes (oracle) | G06 pass; G16 fails (k=3) | no | lenient: none before the universal G16/G13/G14 cap; **specific: selection loss** | TP (lenient); would be A under the specific standard | 5.1, 5.2 |
| **P06** (TP) | projection 34/61 [43-67%] (39/61 at family 26,213); exact 53/61 [76-93%]; **committed draw: projection fails G05 at family 36,791 (adj. p 0.108 vs 0.10, knife-edge)** | yes; rank 489/25,338, clears floor | lenient yes (3 predictive); **specific no** (best J 0.06) | lenient candidates yes; precise rule no on the committed draw (G05) | G06 pass; G16 fails | no | lenient: none; **specific: selection loss, and oracle G05 marginal** | TP (lenient) | 5.1, 5.2 |
| **P02** | projection 21/61 [24-47%]; exact 60/61 [91-100%] | precise projection generated but **discarded as exposure-identical to its depth-2 parent** | lenient yes (1 predictive, broad CAND-012); specific no (best J 0.014) | best pool rule (J 0.45, rank 2352) fails G05+G12 | n/a | no | **representability** (no `booking_month` atom; `party_size>=5` off-grid): representable rule 3.34x broader, fails G05 | **A** (representability subtype) | 5.3 |
| **P03** | projection 25/61 [30-54%] (G12 fails 35/61); exact 57/61 [84-97%] | yes; rank 1,773, clears floor | lenient yes (4 predictive); specific no (best J 0.04) | oracle yes on the committed draw | G06 pass; G16 fails | no | selection (S5); and TP status itself is contradictory under the scorer (its exact rule contains T03's `apparent_feature`) | **D** | 5.4 |
| **P04** | projection 0/61 [0-6%]; exact 0/61 (G05 fails 59, G03 53) | not generated (no eligible ancestor chain, missing `trip_duration_days>=14` atom) | lenient yes (2 predictive, broad); specific no | no | n/a | no | **oracle detectability** (p=2.0e-3 vs BH 3.8e-6, 514x short at n_dev=58) | **B** | 5.5 |
| **P08** | scoreable in 27/61 draws only; projection 0/27; exact 0/27 | exact rule n_dev=33 < min_n=40; projection not generated | lenient yes (1 predictive, broad); specific no | no | n/a | no | **oracle detectability / support floor** (MDE 368 EUR vs effect 80 EUR) | **B** | 5.5 |
| **P09** | projection 0/61; exact 0/61 (G03 43, G05 61, G10 61) | yes but rank 9,270 (2-condition projection); above floor | lenient yes (2 predictive, broad); specific no | no | n/a | no | **oracle detectability** (p=0.013 vs 3.8e-6, 3,450x short) | **B** | 5.5 |

Universal facts at the frozen version (committed draw): all 15 candidates are `experiment_only` (0 promoted); `G13`/`G14` fail for
all 15 (observational design ceiling); `G16` fails for all 15 (every candidate has k>=2). "Promoted" therefore fails at the same
frozen contract point for every pattern and cannot be the first failure of any FN.

### Class counts among the five FNs

| Class | Count | Patterns |
|---|---:|---|
| A engine-actionable | **1** | P02 (representability subtype; lowest-confidence assignment, see 5.3) |
| B benchmark-actionable | **3** | P04, P08, P09 |
| C correctly rejected | **0** | none (see 5.4 for why P03 is not C) |
| D specification ambiguity | **1** | P03 |

Reading rule of `ADR-105` Decision 5: 3 of 5 FNs are oracle-undetectable at the standard N (60%); 1 is detectable but not
expressible by the engine's vocabulary; 1 cannot be decided until the scorer's trap-literal rule is specified. This is neither the
"2 TP + 4 undetectable + 1 safety-rejected" case nor the "4 detectable-and-safe patterns lost by search" case. No FN is
"detectable, safe, and simply lost by search/selection" (the engine-loss story) except, on a stricter standard, the TPs themselves
(section 4).

### The two TPs' robustness (P01, P06)

* **Under TASK-028's lenient statistic they are robust**: lenient-recovered at predictive level in 7/7 engine runs. But so is *every*
  scoreable pattern (P02, P03, P04, P08, P09 too: 7/7 draws, or 4/4 for P08) - the statistic is saturated at `v0.6.2`, so it does not
  discriminate. The committed `v0.6.2` run scores 7/7 recovered (economic-weighted recall 100%) under it.
* **Under a specific-rule standard they are not**: no specific (J>=0.5) P01 or P06 candidate exists in the committed run. Across the
  7 engine draws a specific rule reaches predictive level for P01 in 3/7 (Wilson 16-75%) and for P06 in 1/7 (any level 2/7).
* **Oracle-side**: P01's precise branch is detectable in 61/61 draws (robust). P06's is detectable in 34/61 (56%; interval 43-67%): the
  committed draw is one where it fails G05 at the `v0.6.2` family size although it passed at 26,213 (`TASK-070`).

## 3. Discrepancies with the existing evidence (stated plainly)

| # | Old statement | Re-verified at the frozen version | Reading |
|---|---|---|---|
| D1 | `ADR-103`/`ADR-105`: raw recall `2/7` | True for `v0.2.0`-`v0.5.0` (`TASK-028` files) and `v0.6.0` (45.2%). At **`v0.6.2` (`TASK-103` run)** the same `TASK-028` statistic scores **7/7 recovered**, economic-weighted 100%; `TASK-103`'s "P01 and P06" is the frozen-bar's chosen pair, not the metric's output. | Not a contradiction of `2/7` as history; it means `2/7` is not the frozen engine's score under its own metric. Raw `2/7` is kept as instructed. |
| D2 | `TASK-103`: "P01 and P06 reached predictive_association" | Reproduced exactly - but only via broad rules. No candidate has J>=0.5 for either. Earlier engines did have one (`v0.2.0`-`v0.5.0`: J 0.50 / 0.70, `task-106-version-comparison-raw.json`). | The precise P01/P06 discoveries present through `v0.5.0` are absent in the committed `v0.6.2` run (candidate median exposure 3,921 vs 1,397 in `v0.5.0`; 5/15 candidates lenient-match >=3 patterns vs 0). |
| D3 | `TASK-070`/`ADR-065`: evidence-achievable set `{P01,P03,P06}` under contract 1.3.0 | Reproduced exactly on the same frozen run (`task-106-rerun-task070-validation-power-raw.json`, family 26,213). Re-measured on the `v0.6.2` family (36,791) with the same committed data: **P06's precise branch fails G05**; over 61 draws the achievable rates are P01 100%, P06 56%, P03 41%, P02 34%. | The "3/7 achievable" is a single-draw statement; expected engine-representable achievable count over draws is about 2.3, not 3. |
| D4 | `TASK-069` oracle decomposition (dev n, harm, MDE, optimistic p, broadening, projection rules) | Reproduced exactly for all seven (e.g. P04 p=1.96e-3, P08 n=33, P09 p=0.0132; broadening 1.06/3.34/1.00/8.90/1.42/1.05/3.58). The script itself cannot run its own fidelity gate at `v0.6.2` (it asserts the `v0.5.0` run's 26,213 hypotheses; log in `task-106-rerun-logs.txt`), so my script re-derives the quantities with the same functions. | Consistent. |
| D5 | `TASK-069` pool ranks P01 69, P03 835, P06 204, P09 5,894 of 17,381 | Now 162, 1,773, 489, 9,270 of 25,338 | Not like-for-like (dataset `v1.0.0` -> `v1.1.0` adds `travel_month`; `TASK-101` widened eligibility). Direction: precise branches sit lower in a larger pool. |
| D6 | `TASK-078`: `T03`/`T04` **SURVIVED** with oracle adjustment sets (`shadow_policy`) | Re-run at contract 1.3.0: both capped at `predictive_association`/`experiment_only`, gate of death `G16`. `T01`/`T02`/`T05` unchanged (G03). (`task-106-rerun-task078-raw.json`) | `TASK-078` predates `G16`. No gate distinguishes a P03-like from a T03-like rule at k>=2; `G16` caps both. |
| D7 | `ADR-065`: P03 "reachable but not safe to chase" (C-like) | P03's own exact rule passes `G06` (oracle projection: failures are only G13/G14/G16). The safety objection is the scorer's trap-literal rule, not a gate. | Re-classified D, section 5.4. |

## 4. First-failure structure, and what the "TP" status rests on

Two standards produce different pictures at the frozen version:

* **Lenient (TASK-028, as scored):** first failure of every scoreable pattern is *none* until the universal promotion cap
  (`G16`/`G13`/`G14`); no pattern is an FN.
* **Specific rule:** P01 (100% oracle-detectable) and P06 (56%) are lost at greedy-diverse selection (both above the relevance floor);
  P03 likewise (41%). These are the only detectable-and-lost cases and are engine-side. Under this standard the `v0.6.2` engine has
  0 specific discoveries in the committed run, where `v0.5.0` had 2.

This document does not decide which standard the benchmark *should* use (that is a specification decision, see class D and `TASK-107`).

## 5. Per-pattern chains

Stage vocabulary: ground truth -> oracle detectability -> search eligibility -> discovery -> validation -> safety -> promotion.
Raw values: `docs/benchmark/task-106-raw/seed-20260813.json` (chain, trace, candidates), `task-106-raw-exact/seed-20260813.json`,
`task-106-poolbest-rules.json`; rates `task-106-oracle-rates.json`, `task-106-engine-seed-summary.json`.

### 5.1 P01 (TP) - `supplier=BlueWing AND discount_rate>=0.12 AND booking_lead_days<21`
Ground truth 142 records (75 development), realized -998 EUR. Exact rule: n_dev=75, +987 EUR, MDE 245, p=1.6e-29: detectable in 61/61
draws (exact and projection). Projection `booking_lead_days lt 23 AND discount_rate ge 0.12 AND supplier eq BlueWing` (J 0.95): generated,
eligible, pool rank 162/25,338, effective score 9,628 vs floor 1,565, **not selected**. Search selects 15 broad rules; 13 predictive
ones lenient-match P01 (9 match only P01), best J = 0.26 (`CAND-005`, `lead<23 AND discount>=0.12`, 545 exposed vs 142 affected).
Validation of the precise rule: predictive, G12 passes; G11 fails (seasonality, level cap), G16 fails. Not promoted (universal).

### 5.2 P06 (TP) - `destination=Tokyo AND booking_lead_days<10 AND payment_method=bank_transfer`
134 records (59 development). Exact rule p=1.2e-31, MDE 276 vs +1,153. Projection J 0.71 (`lead<23`, broadening 1.42): eligible, rank 489,
clears the floor, not selected; 3 broad predictive candidates lenient-match it, best J 0.06. **The precise projection fails G05 on the
committed draw at family 36,791** (bootstrap-SE p 8.8e-6, BH-adjusted 0.108 vs alpha 0.10: a knife-edge miss; it passes at family 26,213 on this draw and passed in `TASK-070`); exact rule fails G10
on this draw. Detectable in 56% of draws (projection). Note the exact rule contains `payment_method=bank_transfer`, the literal
`T04` apparent feature (section 5.4).

### 5.3 P02 - `destination=Zanzibar AND customer_segment=family AND party_size>=5 AND booking_month IN [6,7,8]` (class A, representability)
137 records (69 dev). Exact rule: +880 EUR, p=4.6e-22: detectable in 60/61 draws as an idealised rule. The engine cannot express it:
no `booking_month` atom (dataset has `travel_month`, derived from `travel_date`, a different field), `party_size` grid stops at 4,
and the rule has 4 conditions (max 3). The tightest representable rule is 3.34x broader (J 0.30); on the committed draw it is discarded as
exposure-identical to its depth-2 parent (correct behaviour of the redundancy skip) and is detectable in only 21/61 draws (G05 39, G12 20).
The closest pool rule (`destination=Zanzibar AND party_size>=4 AND travel_month>=8`, J 0.45, rank 2,352, above floor) fails G05 and G12.
**Why A and how confident:** exact-rule detectability (60/61) means the target is reachable under the contract; the loss is vocabulary
representability, not search or selection. Lowest-confidence assignment: if a reviewer holds that a missing booking-date calendar
feature in the analytical dataset is a benchmark-construction property rather than an engine property, this becomes B-adjacent; the
exact-rule evidence (not B by the definition, since an oracle passes) is why it is A here. Evidence that would flip it: a
generic calendar atom would have to be shown to leave the representable rule passing G05 - not tested here (no engine change permitted).

### 5.4 P03 - `installments>=3 AND customer_type=new AND acquisition_channel=paid_search` (class D)
333 records (152 dev), exactly representable (broadening 1.00). Exact rule 57/61 detectable; representable rule 25/61 (G12 threshold
perturbation of `installments>=3` fails 35/61 draws, sensitive to draw). Committed draw: rule generated, eligible, rank 1,773/25,338, clears
floor, **not selected**; oracle validation predictive, `G06` passes, `G16` fails (k=3). Lenient-recovered by 4 broad predictive candidates
(none contains `paid_search`).
**Why D, not A and not C.** `evaluate_benchmark.py` sets `is_true_pattern = matched and not matched_traps`, where a trap is matched if the
trap's `apparent_feature` literal is among the candidate's conditions. P03's own exact rule contains `acquisition_channel=paid_search` =
`T03`'s apparent feature, so a candidate that reproduces P03 is scored as a **trap**, not a true pattern, and is excluded from recovery
(`... and not s.is_trap`). The benchmark thus lists P03 as a positive target whose exact rule its scorer classifies as a trap: TP
status cannot be decided until the specification says how a genuine interaction containing a trap's apparent feature is scored
(the ground truth itself says for `P05`/`T05`: "P05 is a genuine interaction; the main effect is a trap"). Not C: `ADR-065`'s C-like
reading (unsafe to chase) rests on `T03` surviving `G06`; at contract 1.3.0 `G16` caps `T03` and `P03` alike, `G06` passes P03's own rule,
and promotion is blocked for all k>=2 candidates, TPs included, so promotion cannot be what makes P03 an FN. Not A: without the
scorer conflict it would be A (selection loss on a draw-dependent 41%); that conditional is stated, not assumed.
The same literal-containment issue applies to P04 (`supplier=Atlas` = `T02`) and P06 (`payment_method=bank_transfer` = `T04`).

### 5.5 P04, P08, P09 (class B)
* **P04** `supplier=Atlas AND trip_duration_days>=14 AND booking_month IN [1,2,12]`: 101 records (58 dev), +307 EUR; exact rule p=2.0e-3
  vs BH rank-1 bound 3.8e-6 (514x short); exact-rule oracle 0/61 (G05 fails 59/61). Cannot pass with an oracle handed the exact rule.
  Engine-side it is also unreachable (chain needs an absent `trip_duration_days>=14` atom; `supplier=Atlas` alone is -50 EUR).
* **P08** `product_category=luxury AND party_size=1 AND booking_lead_days>=90`: 60 records (33 dev), +80 EUR against MDE 368 EUR; exact rule
  n_dev=33 < `min_n` 40 (engine-ineligible) and fails G03/G04/G05; scoreable at all in only 27/61 draws; 0/27 detectable.
* **P09** `supplier=DeltaSun AND booking_month IN [9,10,11] AND party_size>=4`: 124 records (60 dev), +242 EUR vs MDE 274; exact p=0.0132
  (3,450x short); 0/61 detectable (G03 43/61, G05 61/61, G10 61/61).
All three are undetectable by the frozen contract at the standard N with the true rule; the family-size sensitivity (26,213 vs 36,791)
changes nothing for them. Effect sizes and prevalence (n_dev 33-60 of 4,999) are set by the generator, hence class B. Uncertainty: the
binding G05 depends on the multiplicity family set by search breadth, and P08 fails G03 (sample adequacy) independently of the family; P09 fails G03 in 43/61 draws and G10 in 61/61.

## 6. Neutral implications by class (no recommendation)

* **A (P02):** implies a representability question (feature/atom vocabulary) that is separate from search and selection; the frozen contract does not forbid it.
* **B (P04, P08, P09):** implies these three cannot become true positives at the standard N under this contract regardless of engine behaviour; only the data/generator or the statistical contract could change that (the latter carries FP risk, `ADR-103`).
* **C (none):** no FN is detectable-but-correctly-rejected as distinct from the universal `G16` cap.
* **D (P03):** implies the benchmark specification (scorer trap-literal rule) must be settled before P03 can be called a TP or FN; P04/P06 share the exposure.
* **TP robustness:** the lenient `TASK-028` statistic no longer discriminates at `v0.6.2` (7/7); the precise-rule loss for P01/P06 is an engine-side, selection-stage finding independent of the FN classes.

## 7. Reproduction

```sh
uv run python scripts/diagnose_task106_fn_autopsy.py seed --seed 20260813 --engine --trace --out docs/benchmark/task-106-raw/seed-20260813.json   # ~10 min
uv run python scripts/diagnose_task106_fn_autopsy.py seed --seed S --out docs/benchmark/task-106-raw/seed-S.json          # oracle only, ~10 s (add --engine: +~6 min)
uv run python scripts/diagnose_task106_fn_autopsy.py exact --seed S --out docs/benchmark/task-106-raw-exact/seed-S.json    # exact-rule oracle
uv run python scripts/diagnose_task106_fn_autopsy.py seed|exact --family-size 26213 ...                                     # sensitivity dirs *-f26213
uv run python scripts/diagnose_task106_fn_autopsy.py rates --dirs docs/benchmark/task-106-raw docs/benchmark/task-106-raw-exact docs/benchmark/task-106-raw-f26213 docs/benchmark/task-106-raw-exact-f26213 --out docs/benchmark/task-106-oracle-rates.json
uv run python scripts/diagnose_task106_fn_autopsy.py poolrules --committed-json docs/benchmark/task-106-raw/seed-20260813.json --out docs/benchmark/task-106-poolbest-rules.json
uv run python scripts/diagnose_task106_fn_autopsy.py engine-summary --in docs/benchmark/task-106-raw --out docs/benchmark/task-106-engine-seed-summary.json
uv run python scripts/diagnose_task106_version_comparison.py --blind-root <checkout>/artifacts/blind --evaluation-root <checkout>/artifacts/evaluation --out docs/benchmark/task-106-version-comparison-raw.json
uv run python scripts/diagnose_validation_power.py --blind-root ... --validation-report ... --robustness-semantics one_bin_relative_v2 --raw-output docs/benchmark/task-106-rerun-task070-validation-power-raw.json
uv run python scripts/diagnose_task078_oracle_adjustment_sufficiency.py --raw-output docs/benchmark/task-106-rerun-task078-raw.json
```

Seeds 101-160 are the generator-seed sample (chosen before any result; no seed excluded). Seeds 101-106 also carry engine runs. Caveats:
(1) engine runs on other seeds evaluate 34.8k-37.7k hypotheses, but every oracle validation uses one fixed family (36,791);
(2) the exact-rule oracle is a k=1 idealisation (it also reaches `shadow_policy` for P03 because `G16` does not apply to k=1);
(3) raw files for seeds 101-160 written before a cosmetic edit of the script differ only in the recorded `discovery_config_defaults` field;
(4) the `TASK-069` diagnostics that need `artifacts/blind/task-064-*` were run against the main checkout's `artifacts/`.
Lint: `ruff check` and `pyright` clean on `scripts/diagnose_task106_fn_autopsy.py` and `scripts/diagnose_task106_version_comparison.py`.
