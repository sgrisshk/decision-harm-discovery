# Outcome Definition Contract v1.0.0 — First Blind Benchmark

**Owner:** Statistics · **Task:** TASK-013 (scoped to the synthetic benchmark) · **Closes:** the
outcome-contract half of `HANDOFF-003`

This contract fixes what "harm" means for `TASK-015`/`TASK-016`/`TASK-017` on the delivered
analytical dataset `travel-bookings-analytical-v1.0.0`
(`synthetic_data/analytical/travel-bookings-analytical-v1.0.0/`, dataset identity
`490c65655aff645ec8da845cff257f23edfccea4abe609553b576b5b800f91e8`, resolving `HANDOFF-002`). It is
preregistered the same way the validation contract is (`docs/validation_contract.md`, ADR-007):
fixed before any candidate exists, versioned, and not renegotiable per finding. Its executable form
is `packages/analytics/src/policy_analytics/outcomes/` (`contract.py` = definitions,
`aggregation.py` = pure group-summary arithmetic).

Decision-time features live in `features.csv`, identifiers (including the `customer_id`
clustering key) in `identifiers.csv`, split/timing metadata in `metadata.csv`, and every outcome
column this contract defines lives in the physically separate `outcomes.csv` — ML Discovery reads
the first three; `outcomes.csv` is opened only through this contract.

**ML Discovery must treat this document and its code as authoritative.** Discovery selects and
ranks *conditions*; it does not choose, redefine, or reweight outcomes. If a discovery method
needs an outcome this contract does not define, that is a new outcome proposal routed back to
Statistics, not a local decision.

## 1. Scope and what this contract is not

This is the benchmark-scoped answer, not the general-purpose one. `OQ-002` — which outcome a real
customer actually optimizes for — stays open. Two things will differ when a real customer dataset
arrives:

- **Right-censoring.** This benchmark is a closed 24-month window where every downstream cost
  (refunds, support, additional cost) has already fully realized by the time the CSV was
  generated. A live dataset will have recent bookings whose refund/support/cancellation history is
  still accruing. `contribution_margin_eur`'s "no expected missingness" property is a property of
  *this closed benchmark*, not a property of the outcome in general — a real-data outcome contract
  must define an explicit maturation window (e.g., "outcome computed only for bookings whose
  travel date is at least 60 days in the past") or accept right-censoring as reported uncertainty.
- **Customer economic objective.** Whether contribution margin (vs. gross margin, vs. some
  customer-specific P&L line) is the right optimization target is a business fact this repository
  does not yet have (`OQ-002`, `HANDOFF-013` to Product).

## 2. Primary outcome

**`contribution_margin_eur`** — realized contribution margin per booking: net revenue minus base
cost, refunds, additional realized cost, support cost, and payment fees.

| Property | Value |
|---|---|
| Unit | EUR per booking, nominal (single currency in this benchmark; no inflation/FX adjustment) |
| Harm direction | **decrease** relative to the comparison group (higher is better) |
| Missing-data policy | `COMPLETE` — 0% missingness verified against `outcomes.csv` (`missingness.json.overall.contribution_margin_eur = 0.0`); any missingness found at analysis time is a data-quality defect, not something to silently drop |
| Eligible cohort | every booking with `booking_date` in `[2024-01-01, 2025-12-31]`; no filter on cancellation, refund, support activity, or `repeat_purchase_180d` (gate G08) |
| Comparison group | complement of the candidate condition within the eligible cohort (never a different window, never a hand-picked baseline) |
| Clustering key | `customer_id` (`identifiers.csv`), per `manifest.json.clustering` — well above the validation contract's `min_clusters = 5` floor |

### Why this outcome and not another

`contribution_margin_eur` is the only outcome in the schema that nets out *every* downstream cost
component present in the data (refund, support, additional cost, payment fee) rather than a
partial view of them. `gross_profit_eur` stops before support/additional cost/payment fees;
`cancellation`, `refund_amount_eur`, and `support_cost_eur` are each one mechanism, not the
economic total. Choosing the fullest realized measure means a discovery run optimizing this one
number cannot be gamed by a pattern that looks harmful on one component while being neutral or
positive overall.

It is also the only outcome with **zero missingness**, verified empirically against the generated
benchmark (10,000/10,000 present), which removes an entire bias family — selection on outcome
missingness — from the primary-outcome analysis before validation even starts. Every candidate
against `repeat_purchase_180d` inherits gate G07's bounding requirement; every candidate against
`contribution_margin_eur` does not need it.

## 3. Secondary outcomes

Ranked by how they may be used. None of these may be the sole basis for a candidate's rank; they
explain or decompose the primary outcome, or are exploratory only.

| Outcome | Unit | Direction | Missing-data policy | Role |
|---|---|---|---|---|
| `gross_profit_eur` | EUR/booking | decrease = harm | `COMPLETE` | decomposition — separates priced-in harm from downstream-operational harm |
| `contribution_margin_rate` (derived: margin ÷ price) | ratio | decrease = harm | `COMPLETE` | decomposition — compares harm across price tiers without magnitude bias |
| `cancellation` | rate [0,1] | increase = harm | `COMPLETE` | mechanism — explains a margin finding, not independent evidence for it |
| `refund_amount_eur` | EUR/booking | increase = harm | `COMPLETE` | mechanism — component of margin |
| `support_cost_eur` | EUR/booking | increase = harm | `COMPLETE` | mechanism — component of margin |
| `additional_cost_eur` | EUR/booking | increase = harm | `COMPLETE` | mechanism — component of margin |
| `repeat_purchase_180d` | rate [0,1] | decrease = harm | `MNAR_BOUNDED` | exploratory only — see §5 |

A finding built on a mechanism outcome (cancellation, refund, support, additional cost) and a
finding built on the primary outcome for the *same condition* are not independent evidence: the
mechanism outcome is a component of the primary one. Report the relationship; never sum their
impacts as if they were separate harms.

## 4. Sign convention for ranking

Outcomes point in different natural directions (higher-is-better for margin, higher-is-worse for
cancellation). `TASK-016` needs one comparable "harm score" to rank across outcomes without
guessing signs per outcome:

```
raw_difference = mean(exposed group) − mean(comparison group)          # in the outcome's own units
harm_score     = raw_difference × harm_multiplier                       # positive always means harm
harm_multiplier = +1 if higher_is_worse else −1
```

`harm_score` is exposed as `OutcomeDefinition.harm_multiplier` and
`aggregation.harm_score(...)`. Deterministic historical exposure for a candidate — the number the
`TASK-015` candidate contract asks for — is:

```
historical_exposure_eur = harm_score × n_exposed_present
```

exposed as `aggregation.historical_exposure(...)`. This is **raw, unadjusted, un-annualized**
exposure over the observed window only — descriptive, not a validated estimate. Confidence
intervals, adjustment for confounding, and annualization belong to `TASK-021`/`TASK-023`
(Statistics), applied only after a candidate survives the validation gates in
`docs/validation_contract.md`.

### Worked example, from the actual benchmark

For the candidate `supplier=BlueWing AND discount_rate>=0.12 AND booking_lead_days<21`
(n=142, ground-truth pattern P01), measured against `contribution_margin_eur`:

- `raw_difference` = −992 EUR (exposed group's margin is €992 lower on average)
- `harm_multiplier` = −1 (margin is a higher-is-better outcome)
- `harm_score` = (−992) × (−1) = **+992 EUR** (positive, correctly signed as harmful)
- `historical_exposure_eur` = 992 × 142 ≈ **€140,900** over the observed window

This number is descriptive only — it carries no interval and has not been adjusted for anything.
It is what discovery reports; it is not a finding.

## 5. Missing-data handling

Two policies, both defined in `MissingDataPolicy`:

- **`COMPLETE`** — the outcome is expected to have no missingness. This is an empirical claim
  verified against the generated CSV (`tests/analytics/test_outcome_contract.py`), not an
  assumption. If a future benchmark regeneration introduces missingness in one of these columns,
  the test fails and this contract must be revisited before discovery runs again.
- **`MNAR_BOUNDED`** — missingness is expected to depend on the outcome or a close proxy of it. The
  only outcome with this policy is `repeat_purchase_180d`: overall missingness is 9.7%, but 45.7%
  among cancelled bookings versus 7.2% otherwise (measured on the benchmark). This is missing-not-
  at-random by construction — the generator's selection-bias mechanism — and gate G07 in the
  validation contract requires worst-case bounds (`aggregation.mnar_bounds`), never a naive
  complete-case mean.

**`repeat_purchase_180d` is exploratory only and may never be the primary outcome or be converted
into a EUR figure.** No customer-lifetime-value model exists in this repository to translate a
repeat-purchase probability into money; doing so without one would be an invented number, which
ADR-004 forbids. If a repeat-purchase finding is pursued, it is reported in its own unit
(percentage points of repeat-purchase rate) with the MNAR bounds attached, never combined with
margin-based impact.

## 6. Eligibility and cohort rule

The eligible cohort is every decision in the benchmark window, full stop:

```
booking_date within [2024-01-01, 2025-12-31]
```

No filter may reference `cancellation`, `refund_date`, `booking_changes`, `support_cases`,
`support_cost_eur`, `additional_cost_eur`, or `repeat_purchase_180d` when *defining the cohort* —
that is validation gate G08 (survivorship), restated here so Discovery does not have to infer it
from the gate list. Conditions may of course use decision-time features to *define a candidate
subgroup*; the rule is about which decisions enter the analysis at all, not which subgroup a
pattern targets.

## 7. Interpretation limits

- **Direct/variable cost only.** `contribution_margin_eur` nets out refunds, support cost,
  additional realized cost, and payment fees — not fixed overhead, staff time not captured in
  `support_cost_eur`, opportunity cost, or manager compensation. "Harm" in this contract means
  harm to this specific, partial P&L line, not full business impact.
- **Single 24-month window, single currency.** No inflation, FX, or macro adjustment is applied or
  needed at this scale; this stops being true for a longer or multi-currency real dataset.
- **No customer-lifetime-value model.** `repeat_purchase_180d` is the only forward-looking outcome
  and it is a binary 180-day flag with severe MNAR missingness — it is not, and must not be
  presented as, a measure of customer lifetime damage.
- **The "value at stake" framing, not "savings."** Per the validation contract's language rules,
  nothing above `adjusted_observational_association` is reachable on this benchmark's design, so
  economic figures built on this outcome contract are exposure — value at stake in these records —
  never claimed savings, until a design or backtest (`TASK-032`) earns that language.
- **This is a synthetic benchmark, not a business fact.** The choice of `contribution_margin_eur`
  as primary is defensible *for this dataset and this exercise* — it is the fullest, cleanest
  measure available. It is not evidence that a real customer's decision objective is contribution
  margin; that is `OQ-002`, unresolved, and requires Product/Customer Discovery input before any
  real-data outcome contract is written.
- **No right-censoring in this benchmark, unlike production.** See §1 — this simplification does
  not carry over to real data without an explicit maturation-window decision.

## 8. Versioning

`OUTCOME_CONTRACT_VERSION = "1.0.0"`, tied to `DATASET_VERSION = "synthetic-travel-benchmark-1.0.0"`
in `contract.py`. A new benchmark generation (e.g., the `TASK-004` difficulty presets, or the
`HANDOFF-010` regeneration adding per-pattern true effects and a customer ID) is a new dataset
version; whether the outcome contract itself needs to change depends on whether new columns or new
missingness mechanisms are introduced. `ValidationReport.outcome_definition_version` records which
version graded a given finding.
