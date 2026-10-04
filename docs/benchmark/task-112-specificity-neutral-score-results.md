# TASK-112 -- Specificity-neutral development score: results

**Status:** draft, being filled in as each step's real evidence completes. See
`docs/benchmark/task-112-evidence/` for all raw data and scripts; this document narrates and cites
them, it does not replace them.

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

_[filled in once docs/benchmark/task-112-evidence/step4-analysis-summary.json is complete]_

## Step 5 -- paired evaluation (4101-4130, the untouched evaluation reserve)

_[filled in once docs/benchmark/task-112-evidence/step6-verdict.json is complete]_

## Step 6 -- two-sided go/no-go verdict

_[filled in]_
