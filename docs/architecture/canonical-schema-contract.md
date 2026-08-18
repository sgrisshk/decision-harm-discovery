# Travel-booking canonical schema contract

**Scope:** `TASK-010`. Fixes the typed target shape a raw ingested dataset (`TASK-005`–`TASK-009`)
must be mapped onto before it can enter `policy_analytics.analytical_dataset.build_analytical_dataset`
or a future real-customer equivalent of it.

## What already existed, and what this closes

`analytical_dataset.py` has labeled its output `travel-booking-canonical-v1.0.0` since `TASK-011`,
but that was a version string attached to the synthetic benchmark's own already-canonically-named
columns — not a defined, checkable contract, and not a mapping from an arbitrary raw schema onto
it. `TASK-011`'s own evidence says so explicitly: "production customer-input canonicalization
under `TASK-010` remains blocked and is not implied." This closes that gap: the schema is now a
real typed contract (`policy_analytics.cleaning.canonical_schema`), and a raw dataset with
*different* column names can be reproducibly mapped onto it (`policy_analytics.cleaning.mapping`/
`normalize`), not just one that already happens to match.

The version does not bump. Nothing about the target shape changed — `analytical_dataset.py` now
imports `CANONICAL_SCHEMA_VERSION` from this module instead of defining its own copy of the same
string.

## The 32-field schema

Every field is either read directly off the synthetic benchmark's own public, disclosed schema
(`synthetic_data/metadata/feature_timing.json`/`schema_profile.json` — the only concrete
travel-booking schema this repository has ever seen) or cross-referenced against a real structural
dependency elsewhere in the codebase. See `CANONICAL_SCHEMA`'s module docstring for the exact list;
in short:

- `role` reuses `FeatureTiming` (`IDENTIFIER`/`DECISION_TIME`/`POST_DECISION`/`OUTCOME`/
  `METADATA`) — the same vocabulary `TASK-008` already classifies raw columns into.
- `dtype` is one of `string`/`integer`/`float`/`boolean`/`date`.
- `required` is **not editorial**. It is exactly: `booking_id`/`customer_id` (identity/clustering,
  enforced by `analytical_dataset.py`), `booking_date` (the temporal-split column, read by literal
  name), `currency` (read by literal name), `customer_price_eur` (documented in the `TASK-013`
  outcome contract as expected-complete, used as a ratio denominator), and every outcome column
  whose `MissingDataPolicy` is `COMPLETE` (`contribution_margin_eur`, `gross_profit_eur`,
  `cancellation`, `refund_amount_eur`, `support_cost_eur`, `additional_cost_eur`).
  `repeat_purchase_180d` is deliberately **not** required — its `MNAR_BOUNDED` policy means
  missingness is expected and itself meaningful. `tests/analytics/test_canonical_schema.py`
  regenerates this set from the outcome contract directly rather than hand-copying it, so it stays
  a real cross-check.
- `unit` is set for every currency/rate/count field (`EUR`, `ratio_0_1`, `count`, `days`).

## Why the mapping is never automatic for real data

Which raw column supplies `quoted_cost_eur` versus `support_cost_eur` versus nothing at all is a
question about the customer's business, not something a name-matching heuristic can answer safely
— guessing wrong here silently corrupts the outcome/feature layer everything downstream depends
on. Consistent with `ADR-004` and this repository's repeated rule that semantic meaning is never
inferred silently:

- `suggest_mapping(profiles)` proposes a candidate `ColumnMapping` from **exact name matches only**
  (case-insensitive) plus a small, disclosed alias list sourced from the one other real schema
  variant this repository has ever seen (`tests/fixtures/synthetic_travel_bookings.csv`). It is
  explicitly advisory — nothing treats its output as confirmed.
- `validate_mapping(mapping, classifications)` is the actual gate. It checks, independent of how
  the mapping was constructed: every mapped canonical field is real; no source column is mapped
  twice; every mapped source column has a `TASK-008` feature-timing classification; **a source
  column not classified `DECISION_TIME` may never be mapped onto a canonical `DECISION_TIME`
  field** (the one safety-critical cross-check — refuses to launder a column `TASK-008` flagged as
  risky into a safe-looking canonical feature, however the mapping was built); and every
  `required` canonical field has a source.
- `canonicalize(frame, mapping, classifications)` applies a validated mapping: casts each mapped
  source column to its canonical field's declared type (booleans via an explicit
  true/false-token allowlist, not `bool(str)`), fails closed with `CanonicalizationError` on any
  validation problem or type-coercion failure (never partial output), and records every unmapped
  source column in `dropped_columns` rather than silently discarding it.

## Verified against real, not synthetic-only, cases

- The benchmark's clean reference CSV (`synthetic_data/reference/travel_bookings_clean.csv`,
  already canonically named) maps and canonicalizes end to end: all 32 fields, correct types,
  zero dropped columns.
- The benchmark's deliberately dirty raw CSV (`synthetic_data/raw/travel_bookings_dirty.csv`)
  **correctly fails closed** on `booking_date`'s real corrupted values — the same 127 values
  `TASK-007`'s profiler already flagged suspicious. Canonicalization must not paper over data it
  already knows is wrong.
- `tests/fixtures/synthetic_travel_bookings.csv` — a genuinely different raw schema (different
  column names, several canonical fields entirely absent) — proves the mechanism on non-identical
  input: `suggest_mapping` correctly resolves aliased names (`customer_price` → `customer_price_eur`,
  `gross_margin` → `gross_profit_eur`, ...), correctly leaves genuinely-absent fields unmapped
  (`customer_id`, `currency`), and `validate_mapping`/`canonicalize` correctly refuse to proceed
  given the missing required fields (`customer_id`, `currency`, `support_cost_eur`,
  `contribution_margin_eur`) rather than silently canonicalizing a partial, unsafe dataset.

## Explicitly out of scope for this delivery

- **No automatic wiring into the upload endpoint.** `TASK-006`–`TASK-009` run automatically at
  upload time because they require no external input. Canonicalization requires a *confirmed*
  mapping — something that cannot exist automatically for a dataset nobody has looked at yet. This
  stays a deliberate, explicit, separately-invoked step (library-level today; a CLI/API surface is
  premature before a second real raw schema exists to justify one — `TASKS.md`'s "do not overbuild
  before demand").
- **No persistence layer.** No DB table/column stores a `ColumnMapping` or a canonicalization run
  yet — there is no real customer dataset to canonicalize. Adding one now would be speculative
  infrastructure ahead of `TASK-038`.
- **No currency/unit conversion.** `unit` is recorded per field (informational) but no FX or unit
  conversion is implemented — real customer data in a non-EUR currency is out of scope until a
  concrete need exists.
