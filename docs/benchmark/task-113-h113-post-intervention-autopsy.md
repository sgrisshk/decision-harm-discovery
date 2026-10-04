# TASK-113 -- Post-intervention autopsy: does the volume term separate signal acquisition from specificity refinement? (`H113`)

**Status: DRAFT IN PROGRESS.** This document is being filled in incrementally as per-target traces
complete; see `docs/benchmark/task-113-evidence/` for the scripts and raw data it cites. Nothing in
this document is authoritative until every section below says COMPLETE.

`engine.py` sha256 verified unchanged throughout this task (frozen `discovery-engine-v0.6.2`):
`fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`.

## Step 1 -- which 8 Core targets lost Coverage (verified, not assumed)

See `docs/benchmark/task-113-evidence/step1_identify_losses_and_candidates.py` ->
`step1-identification-results.json`. Reads ONLY `TASK-112`'s own already-committed raw per-seed
files (`docs/benchmark/task-112-evidence/step5-paired-4101-4130/{baseline,modified}-seed-*.json`),
recomputing "ever-recovered under baseline, never-recovered under modified, across all 30 seeds"
directly from each candidate's own `covers_targets`/`per_target[target]["recall"]` field (cross
-checked against each other, not just trusted singly) -- not from the summary table in
`docs/benchmark/task-112-specificity-neutral-score-results.md`, which this independently reproduces.

**Verified result: C02, C04, C06, C08, C09, C14, C15, H01** (matches `ADR-114`'s narrative exactly;
confirmed independently here, not assumed from it). C07, C11, C12 are excluded: each still has
k>=1/30 Coverage under the modified engine, so Coverage was not lost *entirely* for them.

**Key structural finding from this same step** (see `trace_subjects` in the JSON): across 7 of
these 8 targets (all but C02), the first baseline-covering seed is the *same* seed (4101), and the
baseline candidate credited with Coverage is, in every one of those 7 cases, one of only **three**
distinct two-condition rules, all anchored on `discount_rate`:

| rule | conditions | covers (recall>=0.5) on seed 4101 |
|---|---|---|
| R1 | `discount_rate ge 0.08` AND `manual_exception eq False` | C06, C14 |
| R2 | `discount_rate ge 0.05` AND `trip_duration_days ge 4.0` | C04, C06, C08, C09, C14, C15, H01 |
| R3 | `discount_rate ge 0.08` AND `trip_duration_days ge 6.0` | C14 |

Each has a low `best_j` (0.11-0.16) -- i.e. none of these is "the" canonical/precise rule for any
one target; each is a generically **broad** rule that happens to sweep >=50% recall of several
targets' true populations at once, by breadth alone, not by matching any one target's structure.
C02's Coverage (first seen seed 4102) is credited to two different, also broad, low-`best_j`
candidates (`CAND-009`: `customer_price_eur lt 3785.73` AND `discount_rate ge 0.03`; `CAND-013`:
`discount_rate ge 0.05` AND `manual_exception eq False`).

None of R1/R2/R3 (nor C02's two seed-4102 candidates) appear anywhere in the modified engine's own
real final top-15 for the same seed (`present_in_modified_final_top15_same_seed: false` for every
one, directly from the committed `modified-seed-*.json` files).

## Step 2 -- per-target stage trace (atoms -> composition -> scoring -> beam -> final top-15)

Methodology: `docs/benchmark/task-113-evidence/step2_dual_trace.py`. READ-ONLY. Reimplements
`discover_candidates`'s own control flow using the real frozen engine's own internal functions
(`_atoms`, `_metric`, `_eligible`, `_development_score`, `_select_expansion_beam`, `_exposed_rows`,
`_temporal_consistency`, `_apply_stability_credit`, `_greedy_diverse_select` -- every one called
directly, none copied or edited) for two score variants in parallel at every depth:

- **baseline**: the real `_development_score` (v0.6.2), called as-is.
- **modified**: `harm_per_booking / (1 + 0.15*(k-1))` -- a plain arithmetic recomputation of
  `TASK-112`'s own documented formula (its Step 2), applied to real `SplitMetric` values produced
  by the real, unmodified `_metric()`. This is the same "mechanically recomputed, no new engine
  run" technique `TASK-112`'s own Step 1 used, extended across the full search tree. **The v0.6.3
  code itself is never written, imported, or executed anywhere in this task.**

Fidelity check, every seed: the "baseline" simulation's final top-15 is compared byte-for-byte
(conditions, in order) against the real, already-committed `baseline-seed-<N>.json`; the "modified"
simulation's final top-15 is compared (by rule identity) against the real, already-committed
`modified-seed-<N>.json`. Results below report both checks per seed -- a baseline mismatch would
mean this reimplementation has a bug; a modified mismatch bounds how far the simulation's internal
stages (which the committed data alone cannot show) can be trusted.

<!-- PER-TARGET SECTIONS FILLED IN BELOW AS TRACES COMPLETE -->

## Step 3 -- concentration verdict (`ADR-114`'s pre-stated 6/8 threshold)

<!-- FILLED IN AFTER ALL 8 TARGETS TRACED -->

## Explicitly out of scope (per `TASKS.md` TASK-113 / `ADR-114`)

No scoring or search change of any kind is proposed or implemented here. No two-stage search
architecture is designed or recommended, whether or not `H113` is supported -- that is a possible
future *consequence*, requiring its own separate founder decision and task, never pre-approved by
this one.
