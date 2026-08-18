# Outcome Definition Contract v1.1.0 — First Blind Benchmark

**Owner:** Statistics · **Task:** TASK-013 (scoped to the synthetic benchmark) · **Closes:** the
outcome-contract half of `HANDOFF-003`

This contract fixes what "harm" means for `TASK-015`/`TASK-016`/`TASK-017` on the delivered
analytical dataset `travel-bookings-analytical-v1.0.0`
(`synthetic_data/analytical/travel-bookings-analytical-v1.0.0/`, dataset identity
`dd7889f7d14264a7ae19e2fc11d95dcdb9da8ad4df3645b4adf7f8bab79cd423` — re-pinned twice 2026-08-18 per
ADR-030 then ADR-031, originally `98ad4e7e08e63ee9e31f9317ca408f2895da8bece49324482915e24df0aee04c`;
every data partition is byte-identical throughout, only metadata fingerprints' computation changed
— resolving `HANDOFF-002`). It is
preregistered the same way the validation contract is (`docs/analytics/validation-contract.md`, ADR-007):
fixed before any candidate exists, versioned, and not renegotiable per finding. Its executable form
is `packages/analytics/src/policy_analytics/outcomes/` (`contract.py` = definitions and the
machine-readable `DISCOVERY_CONTRACT`, `aggregation.py` = pure group-summary arithmetic).

**v1.1.0 change note.** v1.0.0 fixed the primary outcome, direction, unit, and missing-data policy
and is unchanged in substance. v1.1.0 adds, without reopening that decision: an empirically
verified `valid_range` per outcome, an explicit no-winsorization-at-discovery rule, an explicit
aggregation rule per outcome, and §9 below — a consolidated, machine-readable statistical contract
for discovery (search split, support floor, excluded explanatory variables, missing-outcome
handling, causal-language limits). This closes gaps the v1.0.0 text left implicit.

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
| Valid range | **[−5,777.45, 2,519.42] EUR**, the empirically observed range on the pinned dataset (`outcomes.csv`). Used only to flag an out-of-range value as a data-quality defect; never to clip or filter. 11.1% of bookings (1,110/10,000) have a *negative* margin — a genuine loss, not an artifact — so a negative value is in-range and expected, not an anomaly by itself. |
| Winsorization / transformation | **Not allowed at discovery or ranking time.** Discovery ranks on raw values so a reported EUR effect means what it says. Winsorizing the top/bottom 1% is a validation-stage *robustness perturbation* (gate G12) applied afterward to a candidate that already exists — never a preprocessing step before a candidate is proposed or scored. No log/Box-Cox/other transform is applied either, for the same reason: reported effects must stay in native EUR. |
| Aggregation rule | **Unweighted arithmetic mean of present (non-missing) per-booking values within each group** (`aggregation.summarize_group`). No booking is weighted by price, party size, or any other feature; every eligible booking counts once. |

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

### Interpretation

A candidate's raw effect on `contribution_margin_eur` is a difference in average realized,
post-cost value per booking between the exposed subgroup and its complement, in this window, in
this dataset. It is a descriptive association, nothing more, until it survives the validation
contract's gates. Specifically:

- A negative raw difference (exposed group's mean is lower) means the condition is associated with
  *less profitable, or more loss-making*, bookings — not that the condition necessarily *causes*
  the loss (see §9's causal-language rule).
- The unit is real EUR per booking; `historical_exposure_eur` (§4) sums this across exposed
  records in the observed window only — it is not an annualized, risk-adjusted, or causally
  attributed figure.
- Because the range legitimately includes large negative values, a single extreme booking can move
  a small group's mean substantially; this is exactly what the validation contract's robustness
  gate (G12) and sample-adequacy gate (G03) exist to catch — discovery does not correct for it.

## 3. Secondary outcomes

Seven are defined; none may be the sole basis for a candidate's rank — they explain or decompose
the primary outcome, or are exploratory only. Two carry the most independent supporting-evidence
weight (`cancellation`, the clearest single mechanism; `repeat_purchase_180d`, the only
forward-looking signal despite its caveats); the remaining four are cost/margin decompositions of
the same primary outcome and mainly explain *why* a margin finding occurred rather than adding new
evidence that it occurred.

| Outcome | Unit | Valid range | Direction | Missing-data policy | Role |
|---|---|---|---|---|---|
| `cancellation` | rate [0,1] | [0.0, 1.0] | increase = harm | `COMPLETE` | mechanism — explains a margin finding, not independent evidence for it |
| `repeat_purchase_180d` | rate [0,1] | [0.0, 1.0] | decrease = harm | `MNAR_BOUNDED` | exploratory only — see §5 |
| `gross_profit_eur` | EUR/booking | [−5,623.99, 2,709.10] | decrease = harm | `COMPLETE` | decomposition — separates priced-in harm from downstream-operational harm |
| `contribution_margin_rate` (derived: margin ÷ price) | ratio | [−1.3660, 0.3276] | decrease = harm | `COMPLETE` | decomposition — compares harm across price tiers without magnitude bias |
| `refund_amount_eur` | EUR/booking | [0.0, 6,871.55] | increase = harm | `COMPLETE` | mechanism — component of margin |
| `support_cost_eur` | EUR/booking | [0.0, 393.27] | increase = harm | `COMPLETE` | mechanism — component of margin |
| `additional_cost_eur` | EUR/booking | [0.0, 1,523.05] | increase = harm | `COMPLETE` | mechanism — component of margin |

All ranges are empirically observed on the pinned dataset (`outcomes.csv`), for data-quality
sanity-checking only — never for clipping or filtering. Winsorization/transformation is not
allowed at discovery time for any of these, same as the primary outcome (§2). Aggregation is the
unweighted arithmetic mean of present per-booking values for every outcome except
`contribution_margin_rate`, whose rule is the mean of each booking's own ratio — **not**
`sum(margin) / sum(price)`, which would silently reweight toward high-price bookings (see
`contract.py` for the exact, per-outcome `aggregation_rule` string).

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
`docs/analytics/validation-contract.md`.

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

## 9. Statistical contract for discovery

This section is what `TASK-015`/`TASK-016` must obey while *generating and ranking* candidates —
before any validation gate runs. It is machine-readable as `DISCOVERY_CONTRACT` in `contract.py`
(a `DiscoveryStatisticalContract` instance); the numeric floor is imported from, not restated
alongside, the validation contract's own threshold, so the two cannot silently drift apart.

### 9.1 What counts as lower/worse/harmful

Fixed per outcome by `higher_is_worse` (§2, §3): for `contribution_margin_eur` and every
higher-is-better outcome, harmful means a **decrease** relative to the comparison group; for
`cancellation` and every higher-is-worse outcome, harmful means an **increase**. The sign-
normalized `harm_score` (§4) makes "worse" always positive regardless of which direction the raw
outcome points, precisely so discovery never has to hand-code a per-outcome sign.

### 9.2 Minimum support / minimum affected sample size

**These are the same quantity: the count of eligible-cohort records satisfying the candidate
condition (`n_exposed`).** Discovery must not propose or rank a candidate with `n_exposed` below
**50 records** — `DISCOVERY_CONTRACT.min_support_records`, which is *imported directly from* the
validation contract's own gate G03 floor (`ValidationThresholds.min_exposed_records`), not a
second, independently chosen number. The reasoning is the same in both places: a candidate below
this floor cannot be analysed at all, so proposing one only spends multiple-comparison budget
(gate G05) on something that can never survive validation. This is a floor, not a target — most
candidates should sit well above it; see the validation contract's own power-based reasoning
(`docs/analytics/validation-contract.md` §5, gate G03) for why a flat headcount alone is not the real
adequacy criterion once a candidate does reach validation.

### 9.3 Temporal comparison rules

The delivered dataset provides three chronological splits (`metadata.csv.split_label`,
`manifest.json.temporal_splits`): `development` (2024), `validation` (H1 2025), `future_holdout`
(H2 2025).

- **Discovery may select, tune, and rank candidate conditions only on `development`.**
  `DISCOVERY_CONTRACT.search_fit_split = "development"`.
- **`validation` and `future_holdout` are diagnostic-only at discovery time.**
  `DISCOVERY_CONTRACT.diagnostic_only_splits = ("validation", "future_holdout")`. Discovery may
  compute and report the same statistics on these splits for its own stability diagnostics
  (support, raw difference, direction), but must never use them to select, prune, re-tune, or drop
  a condition. Using a later split to shape *which* conditions survive to the candidate list
  invalidates the validation contract's later temporal-stability check (gate G10), which exists
  specifically to test generalization out of the period a pattern was found in — a check that is
  meaningless if that period already leaked into candidate selection.
- Comparison group is always the complement of the condition *within the same split and cohort*
  (§2), never across splits or windows.

### 9.4 Causal-language limits

No candidate — even one that looks strong — has an evidence level until `TASK-018`/`TASK-019`
grade it. Candidate names, descriptions, and warnings must therefore stay at
`descriptive_observation` phrasing: "bookings where X are observed with lower margin," never "X
reduces margin," "X causes," "X drives," or "X leads to." This is the same prohibition
`LANGUAGE_RULES` enforces at every evidence level in the validation contract
(`docs/analytics/validation-contract.md` §6) — restated here because discovery writes candidate language
*before* that contract ever runs, so it cannot inherit the restriction automatically.

### 9.5 Explanatory variables discovery may never use

A candidate condition may reference **only `DECISION_TIME` columns**. Every other classification —
`IDENTIFIER`, `POST_DECISION`, `OUTCOME`, `METADATA`, and any future classification besides
`DECISION_TIME` — is excluded (`EXCLUDED_EXPLANATORY_CLASSIFICATIONS`, built from `FeatureTiming`
so a newly added classification is excluded by default rather than by omission). This is enforced
structurally, not just documented: `features.csv` in the delivered dataset physically contains
only `DECISION_TIME` columns, and `excluded_columns_manifest.json` records every excluded column
with its classification and reason. This is validation gate G01 (target leakage) restated as a
discovery-time input constraint rather than a post-hoc check — the goal is for a leaking condition
to be structurally impossible to construct, not merely caught later.

### 9.6 Missing outcomes — how ML Discovery must treat them

- **Primary outcome (`contribution_margin_eur`, `COMPLETE` policy).** 0% missingness is a verified
  property of the pinned dataset, not an assumption discovery gets to make. If a missing value is
  nonetheless encountered in a candidate's exposed or comparison group, exclude that record from
  the group's support and effect calculation (never impute, never zero-fill), and attach a
  data-quality warning to the candidate — its presence means the running dataset no longer matches
  `DATASET_IDENTITY_SHA256`, and the run should be treated as suspect, not silently patched over.
- **`MNAR_BOUNDED` outcomes (`repeat_purchase_180d`).** Never rank or select candidates for the
  primary leaderboard using this outcome. If discovery explores it at all, report it as a
  separately labeled exploratory list using `mnar_bounds()` — the observed-only mean plus
  pessimistic/optimistic bounds — never a bare complete-case mean, and never merged into the
  primary-outcome ranking.

## 10. Versioning

`OUTCOME_CONTRACT_VERSION = "1.1.0"`, tied to `DATASET_VERSION = "travel-bookings-analytical-v1.0.0"`
and pinned to `DATASET_IDENTITY_SHA256` in `contract.py`. A new benchmark generation (e.g., the
`TASK-004` difficulty presets, or a `HANDOFF-010`-driven regeneration adding per-pattern true
effects) is a new dataset version; whether the outcome contract itself needs to change depends on
whether new columns, new missingness mechanisms, or a materially different observed range are
introduced — the pinned `valid_range` values in particular are empirical claims about *this*
dataset instance and must be re-verified (`tests/analytics/test_outcome_contract.py` does this
automatically against the live artifact) before being trusted against a regenerated one.
`ValidationReport.outcome_definition_version` records which version graded a given finding.
