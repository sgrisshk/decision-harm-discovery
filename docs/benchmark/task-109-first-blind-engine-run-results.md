# TASK-109 results — first blind frozen-engine run on frozen benchmark v2

**Owner:** STATISTICS (lead), ARCHITECT (support). **Status:** measurement complete, written up
for `CODE_REVIEWER`'s independent re-derivation (`TASK-109`'s own "done when" clause). This
document reports numbers plainly; it does not characterize them as good or bad beyond the
pre-registered interpretation in section 6.

**Binding on this write-up:** `ADR-110`, `TASKS.md` `TASK-109`,
`docs/benchmark/task-109-preregistration.md` (committed before any run), the `TASK-107` freeze
manifest (`docs/benchmark/task-107-freeze-manifest.md`).

---

## 1. Frozen-state verification

### Before the first run (step 1)

| File | sha256 | Matches freeze manifest |
|---|---|---|
| `packages/analytics/src/policy_analytics/discovery/engine.py` | `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549` | YES |
| `packages/analytics/src/policy_analytics/validation/contract.py` | `a55fdc94c7e520cc4e287c6627d345e5a2335bfc1bd684db584218790b7403cd` | YES |
| `packages/analytics/src/policy_analytics/benchmark_v2_scoring.py` | `0878811a737ad3608f2ee14568f10a67fc92fd052d866c261d44c9650a8ada1b` | YES |
| `packages/analytics/src/policy_analytics/synthetic_benchmark_v2.py` | `2d6231001ec5ba4e526263e2ad7e67b84d651408be2183fcc024b927fc1627da` | YES |
| `packages/analytics/src/policy_analytics/synthetic_benchmark_v2_targets.py` | `4a9e75a8d27284dbaa20ba0467d43871d0df20db6e16268ca01af208eb9d2059` | YES |

Engine identity confirmed: `discovery-engine-v0.6.2`, validation contract `1.3.0`, no `G17`
(re-derived and asserted programmatically by `verify_frozen_state()` in
`docs/benchmark/task-109-evidence/run_blind_engine.py`, run before every single seed).

### After all 30 seeds (step 7)

Re-hashed the same five files after the full run: **identical hashes, byte for byte, to the table
above.** `git diff --name-only e9896a9 HEAD` (the commit at which `ADR-110`/`TASK-109` were
opened, through the final evidence commit) touches **only**:

* `docs/benchmark/task-109-preregistration.md` (new)
* `docs/benchmark/task-109-evidence/run_blind_engine.py` (new)
* `docs/benchmark/task-109-evidence/engine-raw/seed-4001.json` ... `seed-4030.json` (new, 30 files)
* `docs/benchmark/task-109-evidence/engine-aggregate-rates.json` (new)
* `docs/benchmark/task-109-first-blind-engine-run-results.md` (this file)
* the `TASK-109` `TASKS.md` status entry (appended)

Nothing in `discovery/`, `validation/`, the v2 generator/scorer/targets files, or any v1 file was
touched. `ruff format` was never run over `packages/`.

## 2. What actually ran

Per seed (`4001`-`4030`, all 30, no retries that discarded earlier output, no sequential
extension): the real, unmodified `discover_candidates()` against the composite v2 draw (all 20
`TargetDesign` records dosed together, `v2_common.build_draw`), `DiscoveryConfig()` at every
frozen default except `seed` (unused by the search itself — confirmed, `grep '\.seed\b' engine.py`
returns no hits — carried only for run provenance); then the real, unmodified `run_validation()`
(contract 1.3.0), using the multiplicity family size the engine's own search actually reported for
that seed (`evaluated_hypotheses`, ranging **35,079-36,581** across the 30 seeds, mean 36,183 —
not the fixed 60,000 oracle placeholder, which was explicitly "independent of any engine output"
and never applicable to a real engine run; see pre-registration section 1); then the real,
unmodified `benchmark_v2_scoring.score()` against the 11 final Core targets (`assessed=True`), the
3 permanently-excluded Core-FAIL targets (`C01, C10, C13`, `assessed=False` — never credited,
never exempt a trap, `ADR-108` Decision 3's existing mechanism), `D01` (`assessed=True`,
`stratum="declared_overlap"`), and traps `T01-T05`.

Every seed produced exactly **15 generated candidates** (`DiscoveryConfig.top_k=15`, unchanged).
Raw per-seed output (engine candidates, validation reports, full `score()` output) is committed
under `docs/benchmark/task-109-evidence/engine-raw/seed-<seed>.json`.

**Disclosure on run order:** seeds `4001-4009` were produced first, while this task was still
calibrating a safe per-batch size against the Bash tool's timeout before committing to a fixed
batch size for the remaining seeds. They used the **identical** script, parameters, and
frozen-state verification as every later seed — nothing about them differs methodologically — and
are kept as genuine results rather than discarded and rerun, per `TASK-109`'s own "no retries that
discard earlier output" instruction.

## 3. Headline numbers

**Core denominator = 11** (`C02, C04, C06, C07, C08, C09, C11, C12, C14, C15, H01`). **`D01`
reported separately below, never mixed into this denominator.**

| Metric | Core (any of 30 seeds) |
|---|---|
| **Coverage Recall** | **11/11** |
| **Specific Recall (headline)** | **6/11** (`C07, C09, C11, C12, C14, C15`) |
| **Exact Recall** | **4/11** (`C07, C11, C12, C15`) |

**[Correction, 2026-10-05, after independent review — read with equal prominence to the row above,
not as a footnote.]** The "≥1 of 30 seeds" headline is deliberately the weaker of two readings
(see section 5). Applying this project's own established reliability standard — the same one-sided
95% Clopper-Pearson lower bound ≥ 0.90 on a `k`/30 count that `TASK-107` itself required to
oracle-qualify these 11 targets as Core in the first place — to the engine's own `k`/30 discovery
rates instead:

| Aggregation | Specific Recall | Exact Recall |
|---|---|---|
| Headline ("≥1 of 30 seeds") | 6/11 | 4/11 |
| Majority (≥16/30 seeds) | 3/11 (`C07, C11, C14`) | 2/11 (`C07, C11`) |
| **CP-LB ≥ 0.90 ("reliable", `TASK-107`'s own standard)** | **1/11** (`C07` only, `k=30/30`, CP-LB 0.9050) | **0/11** (`C07`'s own `k=29/30` Exact rate gives CP-LB 0.8514, below 0.90) |

Under the identical reliability bar this project already uses to decide whether a target counts as
oracle-detectable at all, Specific Recall is **1/11**, not 6/11, and Exact Recall is **0/11**, not
4/11. The headline and the "ever discovered" framing in section 5 are not withdrawn — the measurement
itself is unchanged and the choice was disclosed before this correction — but a reader must not take
"6/11" as implying anything close to majority or reliable capability; per the project's own standard,
only one Core target (`C07`) clears a 90%-reliable bar for Specific recovery, and none does for Exact.

### Per-target rate across the 30 seeds (`k`/30), Core

| Target | Coverage k/30 | Specific k/30 (θ_J=0.50) | Exact k/30 |
|---|---|---|---|
| C02 | 25/30 | 0/30 | 0/30 |
| C04 | 30/30 | 0/30 | 0/30 |
| C06 | 30/30 | 0/30 | 0/30 |
| C07 | 30/30 | **30/30** | 29/30 |
| C08 | 30/30 | 0/30 | 0/30 |
| C09 | 30/30 | 1/30 | 0/30 |
| C11 | 30/30 | 26/30 | 26/30 |
| C12 | 30/30 | 8/30 | 7/30 |
| C14 | 30/30 | 21/30 | 0/30 |
| C15 | 30/30 | 1/30 | 1/30 |
| H01 | 30/30 | 0/30 | 0/30 |

Five of the 11 (`C02, C04, C06, C08, H01`) never reached Specific on any of the 30 seeds despite
Coverage on nearly every seed (C02 on 25/30, the rest on 30/30) — i.e. the engine consistently
finds *a* candidate overlapping these targets' affected rows, but never one meeting the
exposure-Jaccard/precision bar. `C09` and `C15` reached Specific on exactly 1 of 30 seeds each —
right at the edge, not a stable capability for those two.

### D01 (`DECLARED_OVERLAP`, oracle_qualified) — reported separately, never Core

| Metric | D01 (any of 30 seeds) |
|---|---|
| Coverage | 1/1 (30/30 individual seeds) |
| **Specific** | **0/1** (0/30 seeds) |
| Exact | 0/1 (0/30 seeds) |

The engine found a candidate covering `D01`'s affected rows on every one of the 30 seeds, but
never one meeting the Specific bar, and never an exact bijection.

## 4. Funnel

Per seed: **15 generated candidates** → validated (reaches `predictive_association` or above):
mean **14.43/15** (range 13-15 across the 30 seeds) → **Coverage** (recall≥0.5 against a given
Core target): 11/11 targets reached on at least one of the 15 candidates, on nearly every seed →
**Specific** (exposure-Jaccard≥0.50 AND effective-condition precision=1.00 AND credited AND
validated): 6/11 targets, with widely varying per-target stability (`C07` essentially every seed;
`C09`/`C15` only once each) → **Exact** (raw bijection before vacuity relaxation): 4/11, a strict
subset of the Specific set (`C09` and `C14` reach Specific but never Exact).

The validation step is **not** the bottleneck: on average only 0.57 of the 15 candidates per seed
fail to reach `predictive_association`. The bottleneck for the 5 never-Specific Core targets is
entirely at the Specific geometric/structural match (exposure-Jaccard / effective-condition
precision), consistent with the engine reliably *finding* a region overlapping these targets
(Coverage) but not reconstructing one that is specific enough.

**Finer decomposition already supported by the scorer, checked and disclosed as empty:**

* `exact_after_vacuity` (a candidate that only bijects with the target after its own vacuous
  conditions are dropped — relaxed, never counted as Exact): **zero occurrences across all 30
  seeds**, for any Core or D01 target.
* `specific_metric_also_holds_for` (a candidate whose Specific metric match also holds against a
  target other than the one it was credited to, i.e. credit ambiguity): **zero occurrences**
  across all 30 seeds.
* Safety/trap suite (`T01-T05`): **no trap literal appeared in any candidate's conditions, on any
  of the 30 seeds** (`trap_appeared` false for every trap, every seed); consequently
  `any_trap_promoted` is `false` on every seed and there are zero exempted candidates and zero
  "no exemption, not a confirmed trap" entries to report.
* "Broad" candidates (covering ≥3 targets by the lenient recall≥0.5 test): present on all 30
  seeds — expected, given the dense 20-target composite.

## 5. Aggregation method — methodological choice, disclosed

`TASK-109` does not fully specify how to turn 30 per-seed, per-target outcomes into one
project-level number, and explicitly requires disclosing the choice rather than silently picking
the most favorable framing. **This implementer's choice:** the headline aggregate reported above
("`X`/11 Core targets reached [metric] on at least 1 of the 30 seeds") is an **"ever discovered
across 30 independent composite draws"** bar — i.e. a target counts toward the aggregate numerator
if the real engine, run once per seed with no retries, reached that metric on *any* one of the 30
seeds.

This is deliberately **not** the same kind of bar as `TASK-107`'s own oracle-qualification
standard (one-sided 95% Clopper-Pearson lower bound ≥ 0.90 on a 30/30 count, i.e. the *true rule*,
evaluated directly by the real validation contract, must be detectable on essentially every seed).
That standard answers "is the signal statistically real and detectable at all." This task's
aggregate instead answers "did the real discovery search, which must find its own rule from
scratch on each independent draw with no guarantee of selecting the same candidate twice, ever
land on something specific enough" — a materially easier bar to clear in the "ever" direction
(one hit out of 30 independent attempts is enough), which is exactly why the full per-target `k`/30
table in section 3 is reported alongside it and not replaced by it: `C09` and `C15` clear the
"ever" bar on the strength of a single seed each, which is a very different, much weaker claim
than `C07`'s 30/30. Both the `k`/30 table and the "any of 30" aggregate are reported together, as
`TASK-109` requires; neither is presented without the other, and the reviewer should weigh the
aggregate's "6/11" headline in light of the fact that two of those six targets reached Specific
only once in 30 independent draws.

A second, narrower scope choice (also disclosed, not a scorer default): Challenge-only designs
(`C03, C05, H02, H03`) and the non-qualifying `D02` were not constructed as `Target` objects at
all for this run (`docs/benchmark/task-109-preregistration.md` section 3) — confirmed before the
run that none of their trap literals bear on the 11 Core + `D01` set, so this changes no number
reported here.

## 6. Pre-registered interpretation (`ADR-110`), applied verbatim

Quoted directly from `ADR-110`, not paraphrased:

> Low Specific Recall is evidence of a discovery limitation **under benchmark v2's composite
> regime specifically** — it can no longer be attributed to v1's known oracle-undetectable-positive
> problem, because every one of these 11 targets already cleared oracle qualification.
>
> High Coverage with low Specific means the engine finds the signal's *region* but localizes the
> rule's structure poorly.
>
> High Specific with low Exact is a narrower canonical-reconstruction problem, not a general
> discovery failure.
>
> A high Specific Recall proves discovery capability up to `predictive_association` only — it does
> **not** prove production readiness, safety, or economic value, and does **not** alter `D2 = 2/5`
> or any other `TASK-102` evidence-bar item.
>
> The reviewer's own caveat is carried forward explicitly: the result characterizes performance
> against the frozen *dense 20-target composite* generator, not isolated causal effects in the real
> world.

Applied to this result:

* **Coverage Recall is 11/11** (every Core target, on nearly every seed) while **Specific Recall is
  6/11 (and, per the per-target table, only `C07` reaches it reliably; `C09`/`C15` reach it once
  each)** — by the interpretation above, this is evidence of a discovery limitation **specific to
  v2's dense composite regime**, not a re-litigation of oracle-undetectability (all 11 already
  cleared oracle qualification in `TASK-107`). The 5 targets that never reach Specific (`C02, C04,
  C06, C08, H01`) are a case of the engine finding the *region* (Coverage) without localizing the
  rule's structure (Specific) — exactly the "high Coverage / low Specific" pattern the ADR names.
* **Exact (4/11) is a strict subset of Specific (6/11):** `C09` and `C14` reach Specific but never
  Exact — the "high Specific / low Exact" pattern, a narrower canonical-reconstruction problem for
  those two, not a general discovery failure, per the ADR's own reading.
* This Specific Recall result (6/11, or 4/11 on the stricter, more defensible "reliable" reading of
  only `C07/C11/C12/C15`) proves discovery capability up to `predictive_association` only. It does
  **not** prove production readiness, safety, or economic value, and does **not** alter `D2 = 2/5`
  or any `TASK-102` evidence-bar item — restated here exactly as the ADR requires, not as this
  implementer's own gloss.
* This result characterizes the engine's performance against the frozen dense 20-target composite
  generator specifically. It says nothing about isolated real-world causal effects.
* `D01`'s own result (Coverage 1/1, Specific 0/1, Exact 0/1) is reported in its own stratum and is
  not combined with, or compared against, the 11-target Core aggregate at any point in this
  document.

## 7. Defect check (step 6)

No scorer or runtime defect was found during this task that would invalidate the measurement.
Specifically checked and found clean: zero trap literals appeared in any of the 450 generated
candidates (15 × 30 seeds); zero credit-ambiguity cases (`specific_metric_also_holds_for` empty on
every seed); zero vacuity-relaxation-only matches (`exact_after_vacuity` empty on every seed);
every seed's engine-reported `evaluated_hypotheses` matched the family size `run_validation`
actually used (checked programmatically, `run_blind_engine.py`'s own `SystemExit` guard, never
triggered); the scorer's own internal invariant checks (`_check_invariants`,
`InvariantViolation`) raised nothing on any of the 30 seeds. The result in sections 3-4 (6/11
Specific, with most of that driven by one target) is a **plain, poor-looking result on its own
terms** — it is reported as such, with no attempt to explain it away, and is not treated as a
defect.

## 8. Files

* Pre-registration: `docs/benchmark/task-109-preregistration.md`
* Run script (reused unmodified engine/contract/scorer/generator; I/O and aggregation only):
  `docs/benchmark/task-109-evidence/run_blind_engine.py`
* Raw per-seed evidence (30 files): `docs/benchmark/task-109-evidence/engine-raw/seed-4001.json`
  through `seed-4030.json`
* Aggregate rates: `docs/benchmark/task-109-evidence/engine-aggregate-rates.json`
* This document: `docs/benchmark/task-109-first-blind-engine-run-results.md`
