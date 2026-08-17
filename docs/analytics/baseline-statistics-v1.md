# Baseline Business Statistics v1 (TASK-014)

**Owner:** Statistics · **Depends on:** `TASK-013` (outcome contract, `DONE`) · **Script:**
`scripts/baseline_statistics.py` · **Artifact:** `artifacts/baseline/task-014-baseline-statistics.json`

## Purpose and scope

TASK-014's goal, verbatim: "Sanity-check overall distributions, time/segment/supplier/manager
trends, and outcome prevalence before discovery." This is a data-understanding pass, not discovery
and not validation. It exists to catch a broken dataset, an unexpected missingness pattern, or an
implausible distribution *before* trusting anything discovery or validation later reports on it —
the same posture `TASK-013` already took toward the primary outcome's own missingness (0%,
verified, not assumed), extended here to every outcome and every decision-time feature.

**What this is not:**

- **Not a discovery run.** It reports one column at a time (or one column against
  `contribution_margin_eur`), never a conjunction of conditions. Finding "interesting"
  combinations of conditions is `TASK-015`'s job, under its own contract
  (`docs/analytics/discovery-engine-v0.md`) and its own evidence-language restrictions
  (`DISCOVERY_CONTRACT.causal_language_note`).
- **Not a validated finding.** No number here carries an uncertainty interval, a p-value, or a
  multiple-comparison correction — those are gates `TASK-018`/`TASK-019` apply to *candidates*,
  not to a raw univariate breakdown. Every number in this report is `descriptive_observation`, the
  lowest evidence level (`docs/analytics/validation-contract.md` `LANGUAGE_RULES`), and must never
  be described with causal or comparative-strength language ("worse", "drives", "because of").
- **Does not open `hidden_ground_truth.json`.** There is no legitimate reason for a baseline
  profiling pass to ever need it, and the script does not import or reference it.

**Timing note.** This task was `READY` (P1, correctly not displacing the P0 chain) from
`2026-08-17` and, per its own status note, was never picked up before `TASK-015`'s blind discovery
run (`task-015-official-20260816-015`) already completed. Running it now is a genuine, independent
first pass over the analytical dataset — it does not rerun or replace anything upstream, and its
role going forward is as a standing reference (e.g. for sanity-checking whether a future dataset
version looks similar) rather than a precondition later stages already passed without it.

## What the report contains

Six sections, each a thin, deterministic wrapper around already-tested primitives
(`policy_analytics.outcomes.aggregation.summarize_group`/`mnar_bounds`,
`policy_analytics.validation.apply.load_analytical_frame`) — this script adds no new
outcome-handling logic, only grouping/summary glue:

1. **`cohort`** — total row count, overall booking-date range, and per-split (`development`/
   `validation`/`future_holdout`) row counts and date ranges. Sanity-checks `TASK-012`'s temporal
   split contract directly: confirms `development` = calendar 2024, `validation` = H1 2025,
   `future_holdout` = H2 2025, with no gap or overlap.
2. **`overall_distributions`** — every `DECISION_TIME` feature (`DECISION_TIME_FEATURES`,
   `validation.apply`), never an `OUTCOME`/`POST_DECISION` column, matching the same
   explanatory-variable boundary discovery and validation already enforce
   (`EXCLUDED_EXPLANATORY_CLASSIFICATIONS`). Categorical columns get a value-count/share table;
   numeric columns get a five-number summary (min/p25/median/p75/max) plus mean/std;
   `booking_date`/`travel_date` get a min/max range rather than a value-count table (365+ distinct
   values would make that table useless).
3. **`outcome_prevalence`** — every outcome in `OUTCOME_DEFINITIONS` (primary and all six
   secondary/decomposition outcomes; `contribution_margin_rate` excluded as a computed ratio, not
   a stored column), via `summarize_group`: N, missingness, mean, std. `repeat_purchase_180d`
   additionally gets `mnar_bounds()` (observed-only mean plus pessimistic/optimistic bounds),
   consistent with its `MNAR_BOUNDED` policy — this report never states a bare complete-case mean
   for it.
4. **`time_trend`** — primary-outcome mean and N by split, and by calendar year-month across the
   full 24-month window (`by_year_month`). Purely descriptive: no seasonality test, no trend
   significance — just numbers, for a human to eyeball for anything implausible.
5. **`segment_trend` / `supplier_trend` / `manager_trend`** — primary-outcome mean, N, and missing
   rate broken out by `customer_segment`, `customer_type`, `supplier`, and `manager` respectively.

**Scope choice: every trend breakdown (3–5) is reported against `contribution_margin_eur` only**,
not against every secondary outcome. This is a deliberate call, not an oversight: a full
per-outcome trend table for all seven outcomes across four dimensions would multiply this report
sevenfold for little sanity-check value, and `outcome_prevalence` (§3) already covers every
outcome once, in full, on its own. If a future need arises to sanity-check a secondary outcome's
trend specifically, that is a scoped addition to this script, not a reason to withhold this pass.

## How to read it

Every number is a plain group mean or count — read it as "what the data looks like," never as
"what causes what" or "which segment underperforms." A large gap between two suppliers' means in
`supplier_trend`, for instance, is exactly the kind of raw association `TASK-015`'s discovery
search is built to propose as a *candidate* and `TASK-018`/`TASK-019` to grade — this report is
upstream of both and makes no claim about whether any such gap survives confounding, multiple-
comparison correction, or temporal stability. Do not cite a number from this artifact as evidence
for or against a specific candidate; cite the candidate's own frozen validation report instead.

## Regenerating

```
uv run python scripts/baseline_statistics.py
```

Refuses to overwrite an existing frozen output without `--force`, matching every other frozen-
artifact script in this repository (`validate_candidates.py`, `evaluate_benchmark.py`). A future
dataset version (a new `dataset_identity_sha256`) should get its own baseline artifact, not a
silent overwrite of this one — the frozen `dataset_identity_sha256` field in the output payload is
how a reader confirms which dataset version a given baseline report describes.
