# TASK-070 — the G12 fix, measured: multi-domain non-regression and the re-measured evidence ceiling

**Status: POST-HOC DIAGNOSTIC throughout.** Every number here is produced by running the real,
unmodified production validation path (`policy_analytics.validation.apply.run_validation`) on
2026-08-28. Nothing here is a new official `TASK-015`/`TASK-019`/`TASK-028` run, changes any frozen
artifact, or grades any candidate for the record. Raw computed output:
`docs/benchmark/task-070-validation-power-remeasurement-raw.json`.

**Sequencing, and why it matters.** Everything in this document was measured **after** the fix was
designed, implemented, versioned, and passing both required regression families on entirely
invented data. `TASK-070`'s hard rule forbids any perturbation step, refit-outcome rule, or
admissibility criterion being designed, scoped, or tuned by reference to travel's specific pattern
identities or feature values. The design is frozen in `ADR-064` and
`docs/analytics/validation-contract.md` §4c; the regression evidence is
`tests/analytics/test_g12_robustness_fix.py`, which reads no dataset, no candidate artifact, no
ground truth, and no real outcome definition. **This document is measurement of an already-fixed
gate. Nothing in it fed back into the fix.**

## 1. What changed, in one line

Validation contract **v1.2.0 → v1.3.0** (`ADR-064`). G12's numeric-threshold perturbation is now
the one-bin step relative to each candidate's own threshold that the contract's preregistered
wording always specified, with named states for coarse/discrete columns; and a `decomposition_of`
outcome is no longer admissible as a magnitude-parity refit, though it is still estimated and
reported as a disclosed diagnostic. No threshold changed. No gate other than G12 changed.

## 2. Multi-domain non-regression (scope item 5)

The same 60 already-frozen candidates, across **three domains and four runs**, graded twice — once
under the superseded semantics, once under v1.3.0 — with every gate result and every gate
diagnostic compared candidate for candidate.

| Run | Domain | Candidates | Gates whose outcome moved | Final verdicts changed |
|---|---|---:|---|---:|
| `task-015-candidates` | travel | 15 | **G12 only** | 8 / 15 |
| `task-065-b2b-comparable-20260822-001` | b2b_sales | 15 | **none** | 0 / 15 |
| `task-068-ecommerce-baseline-20260827-001` | ecommerce | 15 | **G12 only** | 0 / 15 |
| `task-068-ecommerce-cap-20260827-001` | ecommerce | 15 | **G12 only** | 0 / 15 |

For all 60 candidates, `adjustment_columns_used`, `e_value`, `confounder_stratum_coverage` (G06),
`p_value_normal_approx_bootstrap_se` (G05), `holdout_retention` (G10),
`segment_reversal_exposure_share` (G09) and `seasonal_concentration_index` (G11) are **identical
under both semantics**. G12 is the only gate this change touches, on real data, in three domains.

Two results worth reading carefully:

- **`b2b_sales` moves not at all.** Its 15 candidates passed G12 under both semantics, and its
  manifest declares no alternative outcome. A change that were merely a relaxation would still have
  shown up as looser deviations; it shows up as nothing, because there was nothing there to relax.
- **Both `ecommerce` runs change G12's outcome for 8–9 candidates and change *zero* final
  verdicts** — those candidates are held at their existing level by other gates entirely. That is
  an independent demonstration that G12, and only G12, moved.

**The named states fire on real data, not only in tests.** Across the four runs the v1.3.0
threshold family produced 182 `estimated` refits, 4 `degenerate_no_contrast` (two in each
`ecommerce` run), 0 `vacuous_identical_rule`, and 0 `unrepresentable_step`. Every affected
candidate still had at least one estimated refit, so none reached the `NOT_EVALUATED` state; the
degenerate refits were recorded and excluded rather than silently counted as disagreement, which is
exactly the accounting the pre-fix battery got wrong.

**The gate is not toothless afterwards.** Over all 60 candidates graded under v1.3.0, the max
magnitude deviation runs **min 0.003, median 0.113, p90 0.389, max 0.495 against a 0.50 ceiling** —
the worst real candidate clears the ceiling by half a percentage point. The ceiling is still doing
work; it is simply no longer doing it as a function of threshold position.

## 3. The re-measured oracle evidence ceiling for all 7 travel patterns

`scripts/diagnose_validation_power.py --robustness-semantics one_bin_relative_v2`, against the same
committed run (`task-064-beam-20260822-001`), the same oracle projections (re-derived and asserted
equal to `TASK-069` item 7's committed rules condition-for-condition), and the same Benjamini-
Hochberg family (26,213). The only thing that differs from item 1's autopsy is the contract version.

### 3.1 Level-2 blocking gates, before and after

| Pattern | Blocking gates under v1.2.0 | Blocking gates under v1.3.0 | Change |
|---|---|---|---|
| **P01** | `G12` | **none** | reaches `predictive_association` |
| **P02** | `G05`, `G12` | `G05` | still capped, now by data alone |
| **P03** | `G12` | **none** | reaches `predictive_association` |
| **P04** | `G03`, `G04`, `G05`, `G10`, `G12` | `G03`, `G04`, `G05`, `G10`, `G12` | unchanged |
| **P06** *(control)* | none | none | unchanged |
| **P08** | `G03`, `G04`, `G05`, `G12` | `G03`, `G04`, `G05`, `G12` | unchanged |
| **P09** | `G03`, `G05`, `G12` | `G03`, `G05`, `G12` | unchanged |

### 3.2 The answer

**The re-measured achievable evidence ceiling is 3 of 7 scoreable patterns — `P01`, `P03`, and
`P06` — reaching at least `predictive_association`, up from 1 of 7 under v1.2.0.** `P03` reaches
`adjusted_observational_association` (level 3); `P01` reaches level 2 and is held below level 3 by
`G11` seasonality; `P06`, the control, is unchanged at level 2.

**This is the same number `TASK-069` item 1 named as an upper bound, now realised rather than
inferred.** Item 1's "at most 3 of 7" rested on `P01` and `P03` being achievable *if* `G12`'s cap
was not a genuine property of their effects. Item 2 showed the cap was not a genuine property of
*any* effect at those threshold positions. This re-measurement settles it as an actual result:
under the corrected gate, `P01` and `P03` clear `G12` on their own merits (max deviation 39% and
35% against a 50% ceiling, sign agreement 100%), and the three-pattern denominator is what the
dataset plus the corrected contract actually support. The four patterns that do not reach level 2
are blocked by `G03`/`G04`/`G05` sample-adequacy and multiplicity limits that a robustness fix
cannot and should not touch.

Per `TASK-069` item 2's own requirement, **the denominator names its contract version**: it is
`3 / 7 under validation contract v1.3.0`, and it is a joint property of the dataset and the
robustness gate's form, never of the dataset alone. Under v1.2.0 the same dataset gave 1 / 7.

### 3.3 G12 numbers per pattern, and the four patterns it still fails

| Pattern | max deviation v1.2.0 | max deviation v1.3.0 | sign v1.2.0 | sign v1.3.0 | binding refit under v1.3.0 |
|---|---:|---:|---:|---:|---|
| P01 | 66.2% *(fail)* | **39.3% *(pass)*** | 100% | 100% | threshold perturbation, `discount_rate ge 0.12` → 0.08 |
| P02 | 89.0% *(fail)* | **43.2% *(pass)*** | 91.7% | 100% | threshold perturbation, `party_size ge 4` → 5 |
| P03 | 71.3% *(fail)* | **35.0% *(pass)*** | 100% | 100% | threshold perturbation, `installments ge 3` → 2 |
| P04 | 138.4% *(fail)* | 91.3% *(fail)* | 91.7% | 90.9% | **leave-one-cluster-out**, `manager=Manager 2` |
| P06 | 31.8% *(pass)* | 29.6% *(pass)* | 100% | 100% | threshold perturbation, `booking_lead_days lt 23` → 16 |
| P08 | 88.3% *(fail)* | 55.6% *(fail)* | 71.4% | 91.7% | **leave-one-cluster-out**, `manager=Manager 3` |
| P09 | 93.2% *(fail)* | **93.7% *(fail)*** | 91.7% | 100% | **threshold perturbation**, `party_size ge 4` → 3 |

Three of these rows are the strongest available evidence that this was a fix rather than a
relaxation, and none of them was arranged:

- **`P09` still fails, on the threshold perturbation itself, and by slightly *more* than before**
  (93.7% vs 93.2%). Its atom sits at percentile 0.789 — the same region as `P03`'s — and under a
  step measured from its own threshold, moving `party_size ge 4` to `ge 3` still collapses the
  estimate to 6% of its original magnitude. `P09`'s threshold sensitivity is real. Item 2 predicted
  exactly this from its own diagnostic sweep, before any fix existed, and independently established
  `P09` as data-limited regardless (its exact true rule misses BH's most lenient bar by ~3,450×).
- **`P04` and `P08` now fail on leave-one-cluster-out**, the check family this change deliberately
  did not touch. Dropping a single manager collapses `P04`'s estimate to 9% of its magnitude and
  flips its sign, and halves `P08`'s. That is genuine single-cluster dependence — precisely what
  G12 exists to catch — surfacing once the two malfunctioning sub-checks stopped drowning it out.
- **`P02` moves from `G05 + G12` to `G05` alone**: its cap is now attributable to a single, honest
  cause (the size of the search it survived), not split across one real limit and one artifact.

### 3.4 Non-scoreable patterns, recorded because the result is not uniformly favourable

`P05` and `P07` are not scoreable and are reported only for completeness. **`P05`'s G12 deviation
rises under the fix, 81.6% → 143.6%**, and **`P07`'s sign agreement falls from 90.0% to 88.9%,
crossing below the floor.** `TASK-069` item 2 flagged the `P05` direction in advance as a property
of a relative step on that rule. Both are recorded as-is: the corrected gate is *stricter* on these
two, which is the opposite of what a relaxation would produce, and neither outcome was adjusted.

## 4. What this does not say

It does not say any candidate "became stronger" — the contract version changed, and every
comparison above states both versions. It does not promote any finding: these are counterfactual
gradings of oracle projections that were never selected by any blind run, and the frozen
`artifacts/validation/` reports keep their own recorded `validation_contract_version` and are not
re-graded (`docs/analytics/validation-contract.md` §4c migration). It does not settle any
benchmark-semantics question beyond supplying the number `TASK-069`'s step 1 needs, with its
contract version attached. And it opens no follow-on work: whatever a `3 / 7 under v1.3.0`
denominator implies for `TASK-069` is `TASK-069`'s decision to make, not this document's.

## 5. Reproduction

```sh
# The re-measurement above (needs a checkout holding the frozen blind artifacts).
uv run python scripts/diagnose_validation_power.py \
  --blind-root /path/to/checkout/artifacts/blind \
  --robustness-semantics one_bin_relative_v2 \
  --raw-output docs/benchmark/task-070-validation-power-remeasurement-raw.json

# Item 1's original autopsy, unchanged: the default semantics are the pre-fix ones, so a plain
# re-run still reproduces docs/benchmark/task-069-validation-power-autopsy-raw.json.
uv run python scripts/diagnose_validation_power.py --blind-root /path/to/checkout/artifacts/blind

# Item 2's form investigation, pinned to the gate it measured, byte-reproducible as committed.
uv run python scripts/diagnose_g12_perturbation_form.py --blind-root /path/to/checkout/artifacts/blind

# The fix's own regression families — no artifacts, no dataset, no ground truth required.
uv run pytest tests/analytics/test_g12_robustness_fix.py
```
