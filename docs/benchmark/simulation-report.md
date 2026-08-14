# TASK-003 Simulation Report

**Generated:** 2026-08-14  
**Benchmark version:** 1.0.0  
**Seed:** 20260813

## Result

The generator produced 10,000 fictional travel bookings spanning 2024-01-01 through 2025-12-31.
The clean reference has 32 columns. The dirty export has 10,037 rows, including 37 intentional
duplicates. No customer data is present.

The realized dataset-level cancellation rate is 6.44%, outcome-dependent repeat-purchase
missingness is 9.72%, and mean realized contribution margin is EUR 274.71. These are deterministic
simulation diagnostics, not customer or causal findings.

## Benchmark construction

The restricted simulation contains nine harmful interaction patterns and five deliberately
confounded main-effect traps. It also contains a late-period effect, seasonal effects, effect
heterogeneity, non-random assignment, selection bias, and missing-not-at-random outcome
observation. Machine-readable pattern definitions, row memberships, and trap definitions are in
`synthetic_data/evaluation/hidden_ground_truth.json` and are intentionally omitted here. Because
the generator implementation encodes those mechanisms, it is restricted from ML Discovery too.
The restricted truth records deterministic paired effects by replaying the same seed with only one
pattern mechanism disabled. Each true pattern also has a machine-readable `true_effect` object
containing its configured mechanism, realized primary-outcome effect, harmful direction, affected
count and support, realized economic impact, valid interval, outcome, and units. Its relevant
outcome and sign convention are taken from outcome contract v1.1.0: contribution margin in EUR per
booking, where a decrease is harm. Direction and impact-error evaluation therefore uses realized
effects, not nominal loss constants. The values and pattern definitions remain private and are not
reported here.

The chronological split is:

| Split | Booking-date range | Rows |
|---|---|---:|
| Development | 2024-01-01–2024-12-31 | 4,999 |
| Validation | 2025-01-01–2025-06-30 | 2,462 |
| Future holdout | 2025-07-01–2025-12-31 | 2,539 |

No split uses random shuffling.

## Dirty-data layer

The corruption manifest records exact source-row lineage for missing suppliers, mixed date
formats, currency symbols embedded in numeric values, case variants, invalid party sizes, invalid
discounts, whitespace variants, and duplicate rows. The dirty layer uses a separate deterministic
seed (`20260814`). Raw input is never rewritten during generation.

## Leakage and access boundary

All 32 fields are classified as `DECISION_TIME`, `POST_DECISION`, `OUTCOME`, `IDENTIFIER`, or
`METADATA`. Only `DECISION_TIME` fields are marked discovery-eligible. Cancellation, refunds,
support activity/cost, realized extra cost, realized profit/margin, repeat purchase, booking
changes, refund date, and last-modified time are barred from explanatory features.

Public directories (`raw`, `reference`, and `metadata`) contain no pattern row memberships or trap
definitions. The analytical dataset and allowlist-only Discovery export likewise contain none of
the private effect fields. ML Discovery is permitted those generated inputs, but not the generator
source or `evaluation/`, until candidate persistence. The evaluator requires an explicit restricted
ground-truth path and rejects candidate files unless an evaluator-owned HMAC receipt commits their
exact SHA-256 and blind bundle ID before truth is opened. Caller-provided status/timestamps are not
treated as proof. Full statistical scoring remains owned by TASK-028; operational steps are in
`docs/benchmark/blind-benchmark-protocol.md`.

The stable synthetic `customer_id` supports customer-level linkage and clustering. TASK-011
publishes it only in the identifier partition, never in discovery features.

## Reproducibility

`make benchmark` regenerates all artifacts from the fixed configuration. SHA-256 hashes for public
artifacts are stored in `synthetic_data/metadata/checksums.json`; the restricted artifact checksum
is kept inside `evaluation/` so its path is not introduced into public metadata. The regenerated
restricted ground-truth SHA-256 is
`5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506`; two consecutive fixed-seed
generations produced the same digest.
Automated tests verify byte-level reproducibility across output directories and repeated generation
into the same directory, temporal coverage, pattern/trap presence, dirty-row counts, feature timing,
the complete private true-effect schema, public-answer separation (including the analytical and
blind-export boundaries), and fail-closed evaluation.

## Limitations and review

This benchmark establishes a reproducible data-engineering testbed; it does not establish causal
validity, statistical identifiability, policy value, or discovery performance. Those decisions
belong to Statistics, Product, and ML Discovery under their assigned tasks. `HANDOFF-006` requests
final Statistics acceptance of the realized-effect representation before TASK-003 can be marked
`DONE`; the implementation review is tracked by `HANDOFF-030`.
