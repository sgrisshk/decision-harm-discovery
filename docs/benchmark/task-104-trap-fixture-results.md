# TASK-104 — Controlled-fixture results for trap types T01, T02, T05

**Status:** results only; no engine, gate, threshold, contract, `apply.py`, `TASK-102` or `ADR-097`/`098`
text was changed. Tests: `tests/analytics/test_task104_trap_fixtures.py` (25 tests, ~55 s). Every result
below comes from the real, unmodified `policy_analytics.validation.apply.run_validation` (G00-G16,
`assign_policy_readiness`, `ValidationReport.warnings`). Nothing re-implements a gate.

## 1. Result table

"Capped" = `policy_readiness` below `SHADOW_POLICY` (`NOT_READY`/`EXPERIMENT_ONLY`), evidence level at most
`predictive_association`, the named confounding-type gate FAILED, and its caveat text is in
`report.warnings` (the same shape `decision-gate.md`'s 2026-08-30 entry records for `T03`/`T04`, where
`G16` supplied the cap and caveat).

| Trap | Designated mechanism (from code) | Reaches it? | Capped, trap as catalogued (equal confounder weights) | Capped when confounding runs through what the mechanism can see | Adversarial flip |
|---|---|---|---|---|---|
| **T01** `manager=Manager 2` | G06; G16 vacuous (k=1) | yes | **NO** by G06 (6/6 seeds reach `SHADOW_POLICY`, attenuation 0.31-0.38). As shipped it is below `SHADOW_POLICY` only because of a G12 artifact (section 4a), which is not a confounding caveat and not confounding-dependent | yes, by G06, when at least about 50% of the confounding is on `party_size` (the one catalogued confounder G06 retains) | confirmed on the adjustable control: G06 off gives `SHADOW_POLICY`; restored gives capped |
| **T02** `supplier=Atlas` | G06 cannot see `booking_month`; G11 (seasonality via `booking_date`) can; G16 vacuous | yes, G11 only | **NOT robustly.** 4/6 seeds capped by G11, 2/6 reach `SHADOW_POLICY` (G11 ratio 1.45-1.59 against ceiling 1.5) | yes, by G11 (ratio 1.95), G06 uninvolved | confirmed for G11 (off gives `SHADOW_POLICY`); G06-off changes nothing (G06 was never the stopper) |
| **T05** `manual_exception=true` | G06; G16 vacuous (k=1) | yes | **NO** (6/6 seeds reach `SHADOW_POLICY` at `adjusted_observational_association`, attenuation 0.31-0.37) | yes, by G06, when at least about 50% of the confounding is on `party_size` | confirmed on the adjustable control: G06 off gives `SHADOW_POLICY`; restored gives capped |

Supplementary (not part of the catalogued single-atom trap): a compound (k>=2) form of each trap
(`apparent_feature AND destination=Tokyo`) is capped by `G16` (`composition_risk_indeterminate`) and reaches
`SHADOW_POLICY` for T01/T05 when G16 is disabled (T02 stays capped by G11). So compound forms are already
protected; pure single-atom forms are outside G16's domain by design.

**Reading against `ADR-098`'s pre-committed rule** (fixture-demonstrated capping counts toward D2 Part B):
none of the three is cleanly demonstrated capped as catalogued. T02 is capped conditionally (it depends on
how much confounding runs through booking month, and is knife-edge at equal weights). T01/T05 as catalogued
are promoted to `SHADOW_POLICY` by the real gates. Part B therefore stays at 2/5 on the strict reading; this
document does not re-grade it, and recommends no gate change (out of scope).

## 2. How each mechanism was determined (from code)

- A trap candidate is a single condition `apparent_feature` (`synthetic_benchmark.py` trap catalogue;
  counterfactual conditions in `task-075-t03-forensic-trace-raw.json`). k=1, so `G16`
  (`composition_safety.classify_composition_safety`) returns `satisfied=True`, reason
  `not_applicable_single_atom`. Only single-atom-relevant mechanisms can act.
- G06 (`apply._validate_one`): greedy coverage-gated adjustment set (`_select_adjustment_columns`), then
  fails if coverage < 0.50, sign flips, attenuation > 0.50 or E-value < 1.5. Failure caps at
  `predictive_association`.
- G11: max monthly exposure/cohort concentration on `seasonality_column = booking_date` (from the manifest)
  must be <= 1.5; failure caps at `predictive_association`.
- G09 (Simpson, within `customer_segment`) and G12 (robustness, leave-one-out over `manager`) are also
  relevant and interact (sections 3, 4).

## 3. Fixture (test-side only)

The delivered `travel-bookings-analytical-v1.1.0` is copied to a temp directory and two things are rewritten,
with the copied manifest's partition hashes refreshed so the real input contract accepts it:

1. the trap's `X` column, drawn with probability `0.03 + 0.62 * s`, where `s` is a weighted 0/1
   confounder score over the trap's catalogued `confounded_by` columns (indicator = value >= the column's
   own second-quartile breakpoint, aligned with G06's quartile bins; `destination in {Tokyo, Reykjavik}`;
   `booking_month in {4,5,6,10,11,12}`, chosen to appear in all three temporal splits);
2. `contribution_margin_eur = 400 - A*s + N(0, 250)` (and `gross_profit_eur` shifted identically), `A`
   calibrated so raw exposed-vs-rest harm is about 400 EUR. `X` never enters the outcome (zero direct effect).

Why not the real data: `X` is essentially uncorrelated with its catalogued confounders there (indicator-rate
gaps at most 0.09), so a single-atom trap candidate is stopped by G03/G04/G05 for having no effect. Real-data
counterfactual run for context: T01/T02/T05 apparent-feature candidates give `descriptive_observation`,
harm -29/-50/-30 EUR (wrong-signed, non-significant). That says nothing about confounding safety.

**Honest limitations.** (a) The catalogue gives the confounder names, not their weights; "equal weights" is my
assumption and the outcome depends on it (section 5). (b) `X` is rewritten, so exposure geometry, and hence
G06's coverage-gated selection, differs from any real trap candidate. (c) Outcome noise is synthetic and
small, to keep thin-cell stratified estimates from blurring the gate under test. (d) The alignment of the 0/1
indicator with G06's bin edges was fixed after seeing that a misaligned split left within-bin residual
confounding; the catalogue-weight results were not tuned.

## 4. Per-trap findings

### 4a. T01
- As shipped, every `manager=...` candidate has one G12 leave-one-group-out refit (group column `manager`)
  with zero exposed rows, so sign agreement is at most 8/9 = 89% < 90% and **G12 fails deterministically
  regardless of any confounding** (caps at `descriptive_observation`). T01 is therefore below `SHADOW_POLICY`
  as shipped, but by a structural artifact, with a G12 caveat and not a confounding caveat. The same artifact
  would cap a genuine manager effect.
- With the G12 group column moved off `manager` in the fixture manifest (`acquisition_channel`), G12 is
  neutral and G06 alone decides: catalogue weights are **not capped** (attenuation 0.31-0.38, 6/6 seeds).
- Of T01's four catalogued confounders only `party_size` survives G06's coverage floor here (the retained set also includes proxy columns such as `customer_segment`, `customer_type`, `product_category`, `payment_method`, and varies by seed — on one review seed `booking_lead_days` was also retained); `destination`,
  `booking_lead_days`, `trip_duration_days` are dropped (matches `task-075`).

### 4b. T05
- No G12 artifact. Catalogue weights: **not capped**, `SHADOW_POLICY` at `adjusted_observational_association`,
  attenuation 0.31-0.37 (6/6 seeds). This has the same shape as the outcome `decision-gate.md` treats as a hard disqualifier
  (a confounding trap reaching `SHADOW_POLICY`); it is an analogy only — a synthetic fixture, not an official run, and not itself a hard-disqualifier event.

### 4c. Sensitivity of T01/T05 to how much confounding is on the adjustable column (seed 104)
Share of confounding on `party_size` (rest even): 0 -> attenuation 0.11, 0.25 -> 0.33 (both `SHADOW_POLICY`);
0.5 -> 0.78, 0.6 -> 0.89, 0.7 -> 0.98 (capped by G06 alone; G06-off gives `SHADOW_POLICY`); 0.8-1.0 ->
1.06-1.08 (G06 caps, but G09 also fails and still caps with G06 off, because `party_size` proxies the
declared heterogeneity column `customer_segment`). The control used in tests is 0.6.

### 4d. T02
- `booking_month` is not a column and is not in `adjustment_eligible`; `booking_date` and `travel_month`
  are also excluded. G06 can never adjust for it. G11 (via `booking_date`) is the only mechanism that
  observes booking month.
- Month-only confounding: G11 ratio 1.95 (> 1.5), capped at `predictive_association`; G11 disabled gives
  `SHADOW_POLICY`; G06 disabled changes nothing.
- Duration-only confounding (`trip_duration_days`, coverage-dropped by G06 as in `task-075`): **not capped**.
- Equal weights on duration and booking month: G11 ratio 1.52, 1.59, 1.50, 1.53, 1.45, 1.51 for seeds
  101-106 (103 sits exactly at 1.50 and passes; 105 passes) so **4/6 capped, 2/6 promoted**.

## 5. Adversarial regression evidence (inside the tests only)

`g06_disabled()` wraps `apply._stratified_adjustment` so it always stratifies on no columns (adjusted =
raw, detail shows `attenuation 0.00`); `g11_disabled()` replaces `apply.DEFAULT_THRESHOLDS` with
`seasonal_concentration_index=1e9`; `g16_disabled()` flips the real `classify_composition_safety` result to
`satisfied=True`. All are context managers restoring the original object (asserted). Each flip test asserts,
in order: capped (gate FAIL, caveat in warnings, below `SHADOW_POLICY`); protection off -> gate PASS, caveat
absent, `SHADOW_POLICY` reached; restored -> capped again.
`TestFixtureReachesRealGates` spies on the real `_stratified_adjustment` and `classify_composition_safety`
and asserts they are called with the report's own `adjustment_columns_used` set and k=1.

## 6. Testability / definition findings for the safety contract

1. **T02 is only partly routable.** Its catalogued confounder `booking_month` has no column and no G06
   path; the only protection is G11, which is a concentration heuristic (exposure share by month), not
   an adjustment, and sits at its threshold when the confounding is shared with a duration effect.
2. **Trap identity vs. gate scope.** The catalogue defines each trap as a single condition, the one form G16
   cannot act on; G16's protection (`TASK-083`) covers only compound forms.
3. **T01 is capped by an unrelated mechanism** (G12 leave-one-manager-out on the apparent-feature column
   itself). A Part B count that credits this would credit a non-confounding cap.
4. **Trap weights are undefined.** The catalogue lists `confounded_by` without effect sizes, so "capped"
   is not a property of the trap alone but of how much of its confounding lies in G06's retained set.
5. No fix is proposed here (out of scope).

## 6a. Post-review notes (2026-09-24, applied after independent review `APPROVED`; documentation only, no result changed)

1. **Catalogued is not generated.** The independent reviewer found that the benchmark generator
   (`synthetic_benchmark.py`, ~lines 274-318) does not implement several catalogued confounders:
   `T01` (`manager`) is driven only by `destination in {Tokyo, Zanzibar}` or `booking_lead_days<14` (`party_size` and
   `trip_duration_days` never enter); `T02` (`supplier`) is driven only by `trip_duration_days>=14` (`booking_month` is
   not in the supplier logic); `T05` uses equal weights on four binary indicators
   (`dest in {Tokyo,Zanzibar}`, `lead<14`, `party>=5`, `dur>=14`). Against the real generator `T02` is the duration-only
   case (tested here as not capped) and `T01` has no `party_size` share.
2. **Fixture vs generator, and a generator-faithful cross-check.** This fixture uses `destination in {Tokyo, Reykjavik}`
   and median splits instead of the generator's indicators, exposure probability `0.03+0.62s`, and Gaussian outcome
   noise. The reviewer re-ran with the generator's own indicators: `T05` (equal weights) reached `SHADOW_POLICY` in 7/7
   runs across raw harm 150/400/1000; `T01` with the generator's true confounders (`destination`+`booking_lead_days`,
   `party_size` weight 0) and `G12`'s group column moved off `manager` reached `SHADOW_POLICY` 3/3; `T01` as shipped
   stayed below `SHADOW_POLICY` via `G12`. The negative result is therefore independent of the median-alignment choice.
3. **The one post-hoc fixture adjustment** (aligning the 0/1 confounder cut to G06's quartile edge) makes a retained
   confounder more adjustable, favouring capping — it works against the negative finding.

## 7. Reproduce

`uv run pytest tests/analytics/test_task104_trap_fixtures.py` (dataset `synthetic_data/analytical/
travel-bookings-analytical-v1.1.0` required; tests skip if absent). Seeds 101-106, fixed.
