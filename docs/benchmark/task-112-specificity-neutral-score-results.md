# TASK-112 -- Specificity-neutral development score: results

**Status: COMPLETE. Verdict: NOT SUCCESS (hard stop) -- the modification is a severe, two-sided
regression, not merely "insufficient improvement."** See `docs/benchmark/task-112-evidence/` for
all raw data and scripts; this document narrates and cites them, it does not replace them.

`engine.py` sha256 before any change (= Step 1 commit `be7e829`):
`fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549` (`discovery-engine-v0.6.2`,
matches `TASK-107`'s freeze manifest).

## Step 1 -- parameter-free form found; pre-registered counterfactual

See `docs/benchmark/task-112-evidence/step1_formula_derivation.md` (full reasoning) and
`step1-prereg-counterfactual-results.json` (raw numbers). Summary: a genuinely parameter-free form
exists -- remove `_development_score`'s volume term entirely (`n_exposed**population_score_exponent`
-> its own `exponent -> 0` degenerate case, i.e. deletion, not a new coefficient). Mechanically
recomputed from already-committed `TASK-111` evidence (no new engine run): all 7/7 `H111`-positive
FNs show the predicted `Δscore` decrease; `C11` (control) also decreases but is not expected to
resolve; `C07`'s guard margin strengthens, not weakens.

## Step 2 -- the one modification

```
OLD: score = harm_per_booking * n_exposed**population_score_exponent / (1 + 0.15*(k-1))
NEW: score = harm_per_booking                                        / (1 + 0.15*(k-1))
```

`DISCOVERY_METHOD_VERSION` bumped `v0.6.2 -> v0.6.3`. Diff touches only
`packages/analytics/src/policy_analytics/discovery/engine.py` (module docstring, version constant,
`population_score_exponent`'s field docstring note, `_development_score`'s body/docstring) --
confirmed via `git diff fc9ca9b --stat -- packages/` showing exactly one file changed. `ruff
check`/`pyright` clean on this file.

## Step 3 -- Mechanism PASS (development seeds 4001-4030)

See `docs/benchmark/task-112-evidence/step3-analysis-summary.json`.

| target | old median Δscore | new median Δscore | decreased as predicted |
|---|---|---|---|
| C04 | 8843.8 | -55.9 | YES |
| C06 | 10324.5 | -148.7 | YES |
| C09 | 8530.7 | -71.5 | YES |
| C12 | 4976.6 | -274.4 | YES |
| C14 | 4624.4 | 90.0 | YES |
| C15 | 6099.7 | -135.0 | YES |
| H01 | 9410.2 | -174.3 | YES |

**7/7 of the 7 H111-positive FNs decreased in the predicted direction, no large reversal for any.**
Exceeds the `>=5/7` Mechanism PASS bar. **STEP 3 VERDICT: PASS.**

C07 guard: median Δscore 1064.3 -> -572.2 (strengthens in specific's favor).
C11 control: median Δscore 2242.3 -> -500.2 (decreases mechanically, as expected; not used as
pass/fail evidence per ADR-113 Decision 4).

## Step 4 -- regression/kill tests (development evidence, 4001-4030)

Full `discover_candidates` -> `run_validation` -> `benchmark_v2_scoring.score()` pipeline run
through the real modified engine on 5 development seeds (4001, 4002, 4004, 4006, 4008), compared
against `TASK-109`'s already-committed OLD-engine numbers on the same seed range
(`docs/benchmark/task-109-evidence/engine-raw/seed-4001.json`,
`docs/benchmark/task-109-evidence/engine-aggregate-rates.json`).

**Critical finding: Coverage collapses.** `coverage_targets` (any candidate reaching
`recall >= coverage_recall` against a Core target) is **empty on 4/5 seeds** (4001, 4004, 4006,
4008 -- 0/11 Core targets) and only `{C07}` on the 5th (4002), against an OLD-engine baseline of
11/11 on seed 4001 (including a `best_j=1.0` exact match). The batch was intentionally stopped
after 5/5 consistent seeds (not all 30) to redirect compute to the authoritative Step 5/6
evaluation, which is what actually gates the final verdict -- development seeds cannot be used to
confirm or deny it either way, per `ADR-113`.

**Mechanistic explanation.** `benchmark_v2_scoring`'s Coverage requires *recall*
(`inter / n_a`, i.e. finding most of a target's TRUE affected population) -- an inherently broad
property. The OLD volume term, in addition to carrying `H111`'s bias, was functionally necessary
for the search to ever rank a broad, high-recall candidate competitively against a narrow,
high-rate one. Removing it leaves nothing to reward finding more of a target's true population;
combined with the unchanged `min_n=40` eligibility floor (which still lets small-sample rate
estimates through), the new rate-only score is dominated by small, high-variance,
high-per-booking-rate pockets that recall almost none of any target's true affected rows.

See `docs/benchmark/task-112-evidence/step4-dev-regression/*.json` and `step4_analyze.py`.

## Step 5 -- paired evaluation (4101-4130, the untouched evaluation reserve)

Both the frozen baseline engine (`discovery-engine-v0.6.2`, sha256
`fefceeaac20e8ff7...`, obtained via a read-only scratch copy with `engine.py` swapped back to the
exact pre-`TASK-112` content -- see `README-baseline-setup.md`; this repo's own working tree was
never reverted) and the modified engine (`discovery-engine-v0.6.3`) ran the full
`discover_candidates` -> `run_validation` -> `benchmark_v2_scoring.score()` pipeline on all 30 seeds
of the freshly-authorized `4101-4130` reserve, identically to `TASK-109`'s own methodology. 60/60
runs completed cleanly; each run's own frozen-state verification passed every time.

**Per-target absolute numbers, baseline vs modified, 30 seeds each:**

| target | baseline Coverage k/30 | modified Coverage k/30 | baseline Specific k/30 | modified Specific k/30 | baseline CP-LB | modified CP-LB | baseline reliable (>=0.90) | modified reliable | baseline Exact k/30 | modified Exact k/30 |
|---|---|---|---|---|---|---|---|---|---|---|
| C02 | 27 | 0 | 0 | 0 | 0.000 | 0.000 | NO | NO | 0 | 0 |
| C04 | 30 | 0 | 0 | 0 | 0.000 | 0.000 | NO | NO | 0 | 0 |
| C06 | 30 | 0 | 0 | 0 | 0.000 | 0.000 | NO | NO | 0 | 0 |
| C07 | 30 | 15 | 30 | 13 | 0.905 | 0.279 | **YES** | NO | 30 | 13 |
| C08 | 30 | 0 | 0 | 0 | 0.000 | 0.000 | NO | NO | 0 | 0 |
| C09 | 30 | 0 | 6 | 0 | 0.091 | 0.000 | NO | NO | 0 | 0 |
| C11 | 30 | 2 | 18 | 0 | 0.434 | 0.000 | NO | NO | 18 | 0 |
| C12 | 30 | 1 | 17 | 1 | 0.402 | 0.002 | NO | NO | 17 | 1 |
| C14 | 30 | 0 | 17 | 0 | 0.402 | 0.000 | NO | NO | 0 | 0 |
| C15 | 30 | 0 | 1 | 0 | 0.002 | 0.000 | NO | NO | 1 | 0 |
| H01 | 30 | 0 | 0 | 0 | 0.000 | 0.000 | NO | NO | 0 | 0 |

**Aggregate, absolute, both engines:**

| metric | baseline | modified |
|---|---|---|
| Reliable Specific Recall (CP-LB>=0.90 Core targets) | **1/11** (C07) | **0/11** |
| Total Specific-hit count (11x30 target-seed pairs) | **89** | **14** |
| Coverage Recall (ever-recovered, any_of_30) | **11/11** | **3/11** |
| Exact Recall (ever-recovered, any_of_30) | **4/11** | **2/11** |
| Total Exact-hit count (11x30) | 66 | 14 |
| Seeds with any trap promoted (safety) | 0/30 | 0/30 |

Raw data: `docs/benchmark/task-112-evidence/step5-paired-4101-4130/*.json` (60 files). Aggregation:
`step6_verdict.py` -> `step6-verdict.json`.

## Step 6 -- two-sided go/no-go verdict (`ADR-113` Decision 7, evaluated exactly as stated)

| # | condition | result |
|---|---|---|
| 1 | Step 3 Mechanism PASS held | **TRUE** |
| 2 | modified has MORE reliably-recovered Core targets than baseline | **FALSE** (0 vs 1) |
| 3 | total Specific-hit count across 11x30 increases | **FALSE** (14 vs 89) |
| 4 | Coverage loses no Core target at headline level, no material systematic hit-rate drop | **FALSE** (8/11 targets lose coverage entirely; all 11/11 show a >=20% hit-rate drop) |
| 5 | Exact Recall does not worsen | **FALSE** (2/11 vs 4/11 ever-recovered; 14 vs 66 raw hits) |
| 6 | precision/safety regression suite does not worsen | **TRUE** (0/30 trap-promoted seeds, both engines; full `tests/analytics` suite: no regression beyond the exact mechanism changed, see Step 2 commits) |

**VERDICT: NOT SUCCESS.** Conditions 2, 3, 4, and 5 all fail -- this is not a borderline miss on
one axis, it is a severe, consistent regression across every secondary endpoint and the primary
endpoint simultaneously. Even `C07`, the one target `TASK-111` found did not depend on winning the
broad-vs-specific score race, loses reliability (CP-LB 0.905 -> 0.279) -- the local, pairwise
Mechanism-PASS prediction (Step 3) was itself correct (`C07`'s own margin over its named
competitor did strengthen, exactly as predicted), but a *global* effect outside that pairwise
comparison dominates: removing the volume term uniformly also makes many small, high-variance,
unrelated candidates newly competitive for every one of the ~15 final top-K slots across the whole
search, crowding out genuine broad recoveries search-wide, not just in the one pairwise comparison
Step 1/3 checked. `H111` correctly explained a real score bias; removing it the way `ADR-113`'s one
permitted parameter-free form specifies is **not** a viable fix -- the volume term, however biased
in H111's narrow sense, was carrying real, load-bearing weight for the search's ability to find and
retain broad, high-recall candidates at all.

**Hard stop rule applies.** Per `ADR-113` Decision 8 / the task's own hard-stop rule: no second
tweak is attempted inside `TASK-112`. This is reported as the complete, substantive result. Any
further autopsy (e.g. a different, still-parameter-free normalization, or accepting that no
parameter-free fix exists and this axis needs a different remediation entirely) is explicitly a
new, separately-opened task.
