# Economic Impact Result Contract v1.0.0

**Owner:** Statistics · **Task:** TASK-023 · **Resolves:** `HANDOFF-025` · **Consumed by:** TASK-024 (Architect)

This is the versioned, executable semantics behind `EconomicImpactPersistence`
(`apps/api/app/findings/contracts.py`) — Architect's storage envelope, which was deliberately left
without computation logic pending this resolution. Its executable form is
`packages/analytics/src/policy_analytics/validation/economic_impact.py`
(`EconomicImpactResult`, `build_economic_impact_result`), wired into gate G15 inside
`packages/analytics/src/policy_analytics/validation/apply.py`. TASK-024 persists this object; it
does not recompute or reinterpret any of it.

Every quantity here was already being computed by gate G15 before this resolution — nothing new
was estimated to close `HANDOFF-025`. What changed: gate G15's point estimate now comes from the
real (unresampled) combined-cohort sample, not the bootstrap replicate mean (a minor, non-methodology-changing correction — see §5), and a per-record confidence interval is now exposed
separately from the total-exposure interval, because the persistence envelope needs both and G15
previously only kept the total.

## 1. Field-by-field semantics

| Field | Source | Notes |
|---|---|---|
| `impact_contract_version` | `ECONOMIC_IMPACT_CONTRACT_VERSION = "1.0.0"` | Independent of `validation_contract_version` and `outcome_contract_version` — versions this specific result shape. |
| `outcome_name` | `primary_outcome().outcome_id` | Currently always `contribution_margin_eur`. |
| `outcome_unit` | `primary_outcome().unit` | `"EUR per booking (nominal; single currency; no inflation or FX adjustment)"`. |
| `affected_records` | See §2 | **Not** the same population as `ValidationMetadataPersistence.exposed_records`. |
| `per_record_effect` | See §3 | Value + CI + method + unit, harm-signed (§4). |
| `historical_impact` | See §3 | `per_record_effect.value × affected_records`, same CI family. |
| `annualized_impact` | Always `null` in v1.0.0 | See §6. |
| `annualization_justified` | Always `false` in v1.0.0 | See §6. |
| `materiality_pass` | Gate G15's own pass/fail | See §7. |

## 2. `affected_records` — a different population than `exposed_records`, on purpose

**This is the correction this resolution sends back to Product.**
`docs/product/finding-product-contract.md` (§ impact fields) assumed `affected_records` is "same
population as `exposed_records`, restated for the impact section." That assumption predates this
resolution and does not match what gate G15 actually computes, in this version or any earlier one:

- `ValidationMetadataPersistence.exposed_records` = the candidate's exposed count on the
  **development split only** — the population evidence grading was fit and tested against.
- `EconomicImpactResult.affected_records` = the candidate's exposed count over the **full observed
  window** (development + validation + future_holdout combined) — every historical booking the
  pattern actually touches.

These answer different questions ("how many rows graded this finding" vs. "how many bookings does
this pattern touch, historically") and are not generally equal — on the closing `TASK-019` run,
development-only `exposed_records` for `CAND-004` is 1,283 while combined-window
`affected_records` is 2,239. Displaying one without noting it differs from the other is a
foreseeable source of confusion. A follow-up handoff to Product (`HANDOFF-044`) requests updating
`finding-product-contract.md`'s table and, if the UI shows only one "exposed" number today,
deciding which one belongs on a customer-facing Finding (Statistics recommends `affected_records`
for that surface — it answers the business question — with `exposed_records` reserved for an
audit/validation view).

## 3. Point estimate and interval — two different bootstraps, on purpose

`per_record_effect` and `historical_impact` share a common cluster bootstrap (`customer_id`,
`DIAGNOSTIC_BOOTSTRAP_REPS = 1000` replicates) computed over the **combined** window — a
*different* bootstrap run than `ValidationMetadataPersistence.raw_effect`, which is
development-split-only at `DEV_BOOTSTRAP_REPS = 2000` replicates and exists to grade evidence
(gates G03–G05), not to size impact. Do not average or otherwise combine the two — they answer
different questions over different populations.

- `per_record_effect.value` = the real (unresampled) sample mean-difference over the combined
  window, harm-signed. Not a bootstrap-replicate average — a point estimate computed directly from
  data, per ADR-004.
- `per_record_effect.ci_low/ci_high` = a 95% percentile interval from the combined-window
  cluster bootstrap, widened if necessary to contain the point estimate (bootstrap percentile
  intervals are not guaranteed by construction to bracket the unresampled point — see
  `build_economic_impact_result`'s docstring).
- `historical_impact` = `per_record_effect` scaled by `affected_records`, from the *same* replicate
  set, so the two intervals are internally consistent with each other (a candidate's impact CI
  width, relative to its value, tracks its per-record CI width exactly).

## 4. Sign convention

Positive means realized harm, matching `OutcomeDefinition.harm_multiplier`
(`packages/analytics/src/policy_analytics/outcomes/contract.py`) and the ground-truth
`economic_impact_sign_convention` independently verified during `HANDOFF-030`'s TASK-003
acceptance. **A candidate more profitable than its comparison group produces a negative
`historical_impact`** — this contract does not clip that to zero or hide it (`test_economic_impact.py`
pins this explicitly). Product's display rules already handle a non-material or zero-crossing
interval (`finding-product-contract.md`: "no measurable economic effect"); a clearly negative,
material impact is a distinct, legitimate case that display logic should account for, not a
data-quality symptom.

## 5. What changed from G15's original (undocumented) behavior

Before this resolution, G15 used the bootstrap replicates' own mean as its point estimate, with no
separately exposed per-record CI — sufficient for a pass/fail materiality gate, not for a
persistence-ready contract. This resolution replaces the point estimate with the real sample
statistic (`split_stats` over the combined-window mask, the same function every other split-level
statistic in `apply.py` already uses) and adds the per-record CI. On the closing `TASK-019` run the
numeric difference is small (e.g. `CAND-004`: historical impact €680,981 → €681,883, a 0.13%
change) — a precision correction, not a re-estimation, and it does not change any gate outcome,
evidence level, or verdict already frozen in `artifacts/validation/task-019-official-20260816-015.json`,
which is untouched by this change (only future runs use the corrected computation).

## 6. Annualization is not implemented in v1.0.0

`annualized_impact` is always `null`; `annualization_justified` is always `false` —
`EconomicImpactResult.__post_init__` raises if either is violated. `docs/analytics/validation-contract.md`
§8 requires at least `min_annualization_months` of coverage *and* a stable exposure rate before
annualizing; this version does not implement the stability check, so it never claims
annualization is justified, regardless of window length. This is a disclosed, scoped gap in
TASK-023 v0 (the task's own name), not an oversight — implementing it is future TASK-023 work, out
of scope for this resolution.

## 7. Materiality

`materiality_pass` is gate G15's pass/fail exactly: the impact CI's lower bound is positive **and**
clears either `min_material_annual_impact` or `min_material_outcome_share`
(`ValidationThresholds` — both placeholders pending real customer economics, `OQ-004`). This
contract does not expose the threshold values, matching Product's existing display rule (show
pass/fail, never the number). `outcome_share` itself remains available as a Statistics-internal
diagnostic (`diagnostics["historical_exposure_outcome_share"]` in the frozen validation report) for
audit purposes; it is deliberately not added to the persistence envelope, since `materiality_pass`
already answers the only yes/no question the UI needs and an unused extra field is not worth the
added surface.

## 8. Explicitly out of scope for this resolution

This contract reports impact over each candidate's **own, whole-rule** exposed population — it
does not attempt to narrow that population to whatever subset overlaps a specific known
ground-truth pattern. `docs/benchmark/task-029-benchmark-report-v1.md` §3.6 found this whole-rule
reporting responsible for a 2–4.8× overestimate of true impact when a rule is much broader than
the pattern it partially recovers, and proposed a future narrowed-attribution range as a
remediation. That remediation is `HANDOFF-043`'s subject, pending ML_DISCOVERY's concurrence on
whether it's the right fix — it is **not** implemented here, and this contract's v1.0.0 semantics
must not be read as already addressing it.
