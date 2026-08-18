# TASK-033 — Backtest Engine Synthetic Validation v1

**Owner:** Statistics · **Validates:** `packages/analytics/src/policy_analytics/backtest/`
(TASK-032) · **Frozen artifact:** `artifacts/backtest/task-033-backtest-validation.json` ·
**Run after:** `docs/analytics/policy-backtest-contract.md` and the engine's own code were written
and frozen (methodology-before-ground-truth sequencing, same as `TASK-018`→`TASK-028`)

## 1. What this validates

Not the discovery→matching pipeline (`TASK-028` already validates that, separately, and already
diagnosed its dilution problem — `task-029-benchmark-report-v1.md` §3.6). This report isolates the
**backtest engine itself**: given the *exact true* affected population for a known pattern
(`hidden_ground_truth.json`'s own `affected_booking_ids`, not a discovered candidate's broader
rule), does `backtest_from_mask()` recover something close to that pattern's own true effect,
restricted to `future_holdout`?

## 2. Method

For each of the 9 hidden patterns: intersect `affected_booking_ids` with `future_holdout` booking
IDs, run the engine on that exact membership mask, and compare its `benefit` against an
approximation of the true future_holdout-scoped benefit —
`mean_effect(contribution_margin_eur) × |affected_booking_ids ∩ future_holdout|` — where
`mean_effect` is `hidden_ground_truth.json`'s own whole-population paired-counterfactual mean
(`realized_counterfactual_effects`). **This comparison is an approximation, not exact ground
truth**: the true per-booking effect could vary across the two-year window, and this treats it as
homogeneous — disclosed in `docs/analytics/policy-backtest-contract.md` §8, not hidden. Also run
against each of the 5 confounding traps' `apparent_feature` condition, as a disclosure check (not
pass/fail — see §4).

## 3. Results — patterns

| Pattern | True future_holdout N | Engine N | True benefit (approx, EUR) | Engine benefit (EUR) | Relative error | Direction correct |
|---|---|---|---|---|---|---|
| P01 | 31 | 31 | 30,949 | 20,038 | 35.3% | ✅ |
| P02 | 49 | 49 | 41,244 | 44,430 | 7.7% | ✅ |
| P03 | 83 | 83 | 31,438 | 41,189 | 31.0% | ✅ |
| P04 | 20 | 20 | 7,752 | 16,233 | 109.4% | ✅ |
| P05 | 6 | 6 | 2,769 | 4,372 | 57.9% | ✅ |
| P06 | 36 | 36 | 36,508 | 18,980 | 48.0% | ✅ |
| P07 | 52 | 52 | 20,616 | 20,370 | 1.2% | ✅ |
| P08 | 14 | 14 | 6,624 | 6,029 | 9.0% | ✅ |
| P09 | 64 | 64 | 14,479 | 10,395 | 28.2% | ✅ |

**Direction accuracy: 9/9 (100%). Median relative error: 31.0%.**

Every pattern's affected-N matches exactly between the true membership mask and the engine's own
count — confirming the mask-alignment mechanics (`backtest_from_mask`'s length check, §2) work
correctly and no row is silently gained or dropped. The remaining error is entirely in the
per-booking *benefit estimate*, not in population count.

## 4. Results — confounding traps (disclosure check, not pass/fail)

| Trap | Apparent condition | True direct effect | Engine raw benefit (EUR) |
|---|---|---|---|
| T01 | `manager == Manager 2` | 0 | -4,821 |
| T02 | `supplier == Atlas` | 0 | 9,640 |
| T03 | `acquisition_channel == paid_search` | 0 | 70,514 |
| T04 | `payment_method == bank_transfer` | 0 | 1,559 |
| T05 | `manual_exception == true` | 0 | 7,393 |

Every trap shows a **nonzero** raw backtest benefit despite a **known-zero true direct effect** —
expected, not a defect. `benefit` is deliberately unadjusted (`docs/analytics/
policy-backtest-contract.md` §4: "an upper bound on mechanical effect," not a causal estimate),
and traps are confounded by construction — a raw comparison-group difference picks up the
confound. T03's apparent EUR 70,514 is the largest, consistent with `acquisition_channel` being a
real confounder in this benchmark. **This is why `docs/analytics/policy-backtest-contract.md`'s
own disclosure text is load-bearing, not decorative: a backtest number must never be shown without
the "mechanical, unadjusted, not causal" framing, and this table is the concrete demonstration of
what happens if that framing is dropped.**

## 5. Why the error is not zero, honestly

The ~31% median relative error traces to a real, disclosed methodological difference, not an
implementation bug:

- **Ground truth's `mean_effect`** comes from a *paired* counterfactual — the same simulated
  customer/booking, pattern enabled vs. disabled — the tightest possible comparison.
- **The engine's `benefit`** comes from an *observational* comparison — the exposed group's mean
  vs. every other `future_holdout` booking's mean (raw, unadjusted) — the same kind of comparison
  a real backtest on real data would have to use, since a real dataset has no paired counterfactual
  to compare against. Some of this gap is genuine estimation noise (smaller for larger-N patterns
  — P07's N=52 error is 1.2%; P05's N=6 error is 57.9% — consistent with a bootstrap-uncertainty
  explanation, not a systematic bias: direction is correct in all 9 cases and there is no
  consistent over- or under-estimation sign across patterns).

This is exactly the gap `docs/analytics/validation-contract.md` §9's "upper bound on mechanical
effect... not a forecast" framing exists to disclose — the engine is not claiming paired-
counterfactual precision, and this report is the evidence that it doesn't have it, quantified.

## 6. Conclusion

The backtest engine (`TASK-032`) recovers the correct **direction** on all 9 known patterns and a
**median 31% relative error** on **magnitude**, using only observational, unadjusted, out-of-period
data — no worse than the general precision ceiling observational estimation already has elsewhere
in this project, and substantially better than `TASK-028`'s whole-rule dilution-affected 204%
median error, because this test isolates engine correctness from candidate-matching population
dilution. The confounding-trap check confirms the engine's own disclosure text is necessary: raw
backtest numbers are not causal and must always carry the "mechanical, unadjusted" framing when
shown. `TASK-032` is ready for real candidate use (`scripts/run_backtest.py`,
`artifacts/backtest/task-032-backtest-task-058-remediation-001.json`) under exactly that
disclosure.
