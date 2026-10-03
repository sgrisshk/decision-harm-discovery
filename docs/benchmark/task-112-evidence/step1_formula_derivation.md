# TASK-112 Step 1 — parameter-free form + pre-registered counterfactual

**Status:** written BEFORE any code change. `engine.py` sha256 at this point:
`fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549` (matches `TASK-107`'s freeze
manifest / `discovery-engine-v0.6.2`, verified unchanged through `TASK-111`).

## 1. The real formula, read directly from `engine.py` (not assumed)

```python
# packages/analytics/src/policy_analytics/discovery/engine.py, _development_score (lines 433-448)
population_component = metric.n_exposed**config.population_score_exponent
magnitude = metric.harm_per_booking * population_component
return magnitude / (1.0 + 0.15 * (condition_count - 1))
```

i.e. `score = harm_per_booking * n_exposed**population_score_exponent / (1 + 0.15*(k-1))`, with
`population_score_exponent` defaulting to `0.5` (`DiscoveryConfig.population_score_exponent`,
validated to `(0.0, 1.0]` in `__post_init__`). This is exactly the formula `TASK-111` decomposed
and confirmed, byte for byte, as the real, unmodified function (sha256 verified before/after).

Three multiplicative components: `harm_per_booking` (a per-exposed *rate* — the exposed-minus-
comparison mean difference times `outcome.harm_multiplier`, already per-unit, not a total), a
*volume* term `n_exposed**population_score_exponent`, and a complexity penalty
`1/(1+0.15*(k-1))`.

## 2. Is there a parameter-free, per-exposed/rate-normalized equivalent of the volume term?

The volume term is the only component that is not already a rate: `harm_per_booking` is per-unit by
construction, and the complexity penalty is a fixed, hand-set constant (`0.15`) that is explicitly
out of scope (ADR-113 only authorizes touching the volume/support component). The volume term's
*current* form already carries one free, experimentally-chosen coefficient:
`population_score_exponent = 0.5`, picked in `TASK-058`/`ADR-023` as "a geometric-mean-style
balance," not derived from anything parameter-free.

Candidate replacements considered:

1. **Keep an exponent, just pick a different number** (e.g. `0.3`, `0.25`, "whatever best separates
   the FNs on 4001-4030"). Rejected outright — this is exactly the forbidden move named in
   `ADR-113` Decision 1 ("any newly-introduced free coefficient chosen by experimentation"). Any
   value in `(0, 1)` other than the existing `0.5` is just a different hand-picked prior; there is
   no principled way to derive e.g. `0.3` from the formula itself.
2. **Add a `+ specificity_bonus * k` or `- broadness_penalty * support` term.** Explicitly forbidden
   by name in `ADR-113` Decision 1 for the same reason — a new hand-tuned prior pointing the other
   way is not a neutral fix, it is a different bias.
3. **Replace `n_exposed**0.5` with `log(n_exposed)`, `log1p(n_exposed)`, or similar.** Still a
   volume-rewarding, monotonically-increasing-in-`n_exposed` function with no natural choice of
   base/offset that isn't itself an arbitrary pick — not qualitatively different from (1), just a
   different curve shape chosen without justification. Rejected for the same reason as (1).
4. **Remove the volume term's exponent entirely — i.e. the term's own natural `exponent -> 0`
   degenerate case, `n_exposed**0 = 1`.** This is not "pick a new constant" — `0` is not a free
   choice among many candidate values selected for performance, it is the unique exponent at which
   the volume term stops being a function of volume at all, i.e. the term is *removed*, not
   retuned. The resulting score, `harm_per_booking / (1 + 0.15*(k-1))`, is purely rate-based: two
   candidates with identical per-exposed evidence quality (`harm_per_booking`) and identical
   condition count score identically, regardless of how many rows either one covers. This is
   genuinely parameter-free: no new numeric literal appears anywhere in the formula that was not
   already there (`0.15` is untouched and out of scope; the only change is deletion of a term, not
   insertion of a value).

**Conclusion: option 4 exists and is parameter-free.** `TASK-112` does NOT stop at Step 1 — it
proceeds to the pre-registered counterfactual below, then the code change in Step 2.

One structural safeguard already in the engine, confirmed by reading `_eligible()`
(lines ~405-430), makes option 4 safe from the "reward tiny, noisy rules" failure mode a naive
rate-only score risks: `metric.n_exposed >= config.min_n` (default `40`) is already a hard
*eligibility* gate applied before any rule is scored at all, and is untouched by this change. A
rate-only score cannot promote a rule with too little exposure to be scored in the first place —
reliability is enforced by eligibility, not by the score shape.

```
NEW _development_score:
    magnitude = metric.harm_per_booking
    return magnitude / (1.0 + 0.15 * (condition_count - 1))
```

`DiscoveryConfig.population_score_exponent` itself is left defined, at its existing default
(`0.5`), unchanged by this task (ADR-113 Decision 1: "every other component, weight ... untouched")
— it simply stops being read inside `_development_score`. See Step 2's own note on why the field is
kept rather than deleted.

## 3. Pre-registered counterfactual (mechanical, from already-committed `TASK-111` evidence; NO new
engine run, NO code change yet)

Method: `docs/benchmark/task-111-evidence/h111-decomposition-raw.json` already records, for every
target's canonical/specific rule and its `TASK-110`-named broad competitor, on every one of
`TASK-109`'s 30 seeds (`4001-4030`), the real `harm_per_booking`, `n_exposed`, `k`, and the
already-computed OLD `development_score`. `step1_prereg_counterfactual.py` recomputes
`new_score(harm_per_booking, k) = harm_per_booking / (1 + 0.15*(k-1))` directly from those same
recorded fields — this is a hand recomputation of a fixed, already-stated formula over already-
committed numbers, not a new data collection and not fit to any seed. A cross-check
(`old_score` recomputed from the same raw fields against the already-committed `development_score`
value) confirms max relative error `0.0` — this script is reading the real recorded numbers
correctly, not transcribed ones.

**Mechanical reasoning (formula-level, applies uniformly, not target-by-target fitting):** the old
formula's volume term `n_exposed**0.5` multiplies a candidate's score by its own exposed count's
square root. Every broad competitor used in `TASK-111` (`discount_rate>=0.03/0.05 AND
manual_exception=False`, or each target's own named 2-literal competitor) by construction covers
far more rows than the corresponding 2-3 literal canonical/specific rule — removing the term removes
a multiplier that was always larger for the broad side than the specific side. Since `sqrt(x)` is
concave, shrinking a larger multiplier toward `1` removes more absolute score than shrinking a
smaller one, so `Δscore_new = score_new(broad) - score_new(specific)` is mechanically predicted to
be smaller than the already-committed `Δscore_old`, for every target where the broad side's
`n_exposed` exceeds the specific side's — predicted direction: **decrease**, for all 7 `H111`-
positive FNs (`C04, C06, C09, C12, C14, C15, H01`). This reasoning is a direct consequence of the
term's own concavity and the broad-vs-specific exposure asymmetry visible in `TASK-110`'s original
candidate selection (every named competitor is a low-specificity, high-support filter by design),
not a conclusion fitted after seeing the Step 1 script's output.

**Per-target reality check (ran after stating the above reasoning, to confirm the predicted
direction materializes, not to derive it) — `median_n_exposed_ratio` is the competitor's
`n_exposed` divided by the specific rule's `n_exposed`, median across the 30 seeds:**

| target | median Δscore (OLD) | median Δscore (NEW) | median n_exposed ratio (competitor/specific) | decreased as predicted |
|---|---|---|---|---|
| C04 | 8843.8 | -55.9 | 10.56x | YES |
| C06 | 10324.5 | -148.7 | 17.39x | YES |
| C09 | 8530.7 | -71.5 | 10.35x | YES |
| C12 | 4976.6 | -274.4 | 12.14x | YES |
| C14 | 4624.4 | 90.0 | 1.77x | YES |
| C15 | 6099.7 | -135.0 | 7.48x | YES |
| H01 | 9410.2 | -174.3 | 22.95x | YES |

All 7/7 `H111`-positive FNs show the predicted decrease (exceeding the Step 3 bar of `>=5/7`, which
is expected and is not itself the Step 3 verdict — Step 3 re-runs this after the actual code change,
through the real `_development_score`, not this hand recomputation). No large reversal in the
opposite direction occurs for any of the 7. Note `C14`'s much smaller `n_exposed` ratio (1.77x,
versus 7-23x for the other six) — `C14`'s named competitor is its own 2-of-3-literal subset
(`discount_rate>=0.08 AND supplier=BlueWing`), not the universal low-specificity proxy, so the
volume asymmetry is structurally smaller there; the predicted decrease still holds (4624.4 -> 90.0)
but the new median is not pushed negative, consistent with a smaller exposure-ratio mechanism
producing a smaller effect, not a different mechanism.

**`C11` — pre-registered negative/mechanistic control.** Median Δscore also decreases under the new
formula (2242.3 -> -500.2, by the same mechanical volume-term argument — `C11`'s broad competitor
also has far larger `n_exposed`, 12.88x median). **This is not expected to resolve `C11`**: `TASK-
111`'s own finding was that `C11`'s score-bias pattern (present on 26/30 seeds under the OLD
formula) does not causally track `C11`'s actual 4 miss seeds (`4011, 4013, 4027, 4028`) —
independently confirmed by `CODE_REVIEWER`. Moving the score further in the same direction does not
change that the miss mechanism there is downstream selection variance, not this score term. `C11`'s
outcome in Step 3/Step 5 is reported but is never used as evidence for or against this task's
pre-registered predictions, per `ADR-113` Decision 4.

**`C07` — guard.** Median Δscore (broad minus specific) swings from +1064.3 (OLD, broad slightly
ahead) to -572.2 (NEW, specific now ahead) — if anything this strengthens `C07`'s position relative
to its broad competitor on raw score. Per `TASK-111`'s own finding, `C07`'s reliable 29/30 final-
top-15 recovery was never dependent on winning this raw-score race in the first place (final
selection is diversity-based top-15, not a strict pairwise score gate) — so `C07`'s reliable
Specific recovery is pre-registered as expected to persist into Step 4's regression check, and if
anything has a larger safety margin under the new formula, not a smaller one.

## 4. Mechanism PASS bar, restated for Step 3 (not evaluated here — development evidence, after the
code change)

`>=5 of 7` `H111`-positive FNs must show median `Δscore` decreasing in the predicted direction
(already true above, pre-code-change, for all 7/7, computed by hand from committed raw fields), with
no large reversal in the opposite direction for any of them, **recomputed through the real, modified
`_development_score` function** in Step 3 — this document's numbers are the pre-registered
prediction, not a substitute for that re-run.
