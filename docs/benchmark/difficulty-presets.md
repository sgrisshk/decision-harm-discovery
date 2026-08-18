# TASK-004 benchmark difficulty presets

**Scope:** `TASK-004`. Adds `EASY`/`MEDIUM`/`HARD`/`BRUTAL` presets to the `TASK-003` synthetic
generator (`packages/analytics/src/policy_analytics/synthetic_benchmark.py`), varying noise,
effect size, missingness, confounding, rarity, and temporal instability.

## The one non-negotiable constraint

`MEDIUM` must reproduce the already-frozen benchmark byte-for-byte. Every already-completed
discovery/validation/blind run — including `task-015-official-20260816-015`, its `TASK-019`/
`TASK-028`/`TASK-029` scoring, and the `TASK-029` decision-gate `FAILED` verdict currently under
review (`HANDOFF-043`) — was built against `hidden_ground_truth.json` with SHA-256
`5c41aab8ad6765332b708fd8b91567b63839b84add2dd8aa206d87c159cab506`. Changing that file for the
default configuration would silently invalidate all of it.

This is enforced two ways, not just by care during implementation:

1. Every new `BenchmarkConfig` field defaults to the identity value for its own mechanism (`1.0` =
   unscaled). `Difficulty.MEDIUM` is exactly those defaults — `difficulty_config(Difficulty.MEDIUM)
   == BenchmarkConfig()`.
2. Not one of the six knobs adds, removes, or reorders a single `rng.*()` call versus the
   pre-`TASK-004` generator — every one multiplies or nudges an already-existing magnitude or
   threshold value in place, so the *sequence* of random draws for every row is untouched. A
   scaled-by-1.0 uniform call (`scaled_uniform`) is verified to consume the exact same single
   `rng.random()` draw as the original bare `rng.uniform(...)` call; `scale_effect_leaves` returns
   its input completely untouched (not `value * 1.0`) at scale `1.0`, so an int magnitude like
   `410` never silently becomes the float `410.0` in the frozen ground truth.

`tests/analytics/test_difficulty_presets.py::test_default_config_still_reproduces_the_frozen_hidden_ground_truth`
asserts the exact SHA-256 above directly — not a value to update if it ever fails.

## The six knobs

| Knob | Mechanism | Applied to |
|---|---|---|
| `effect_scale` | Multiplies every configured pattern effect magnitude (`loss`/`cancel_logit`/`support_lambda` deltas in `_generate_row`, and the matching `configured_effect` reported in `hidden_ground_truth.json` via `scale_effect_leaves`) | All 9 patterns |
| `noise_scale` | Multiplies the width/stddev of the outcome-generation noise sources (`customer_price`'s gaussian, `additional_cost`'s gaussian, and the `support_cost`/`base_cost_ratio`/`refund_ratio` uniform ranges via `scaled_uniform`) | Outcome variance, not decision-time feature generation |
| `confounding_scale` | Multiplies the non-random manager/supplier assignment weight boosts that create the benchmark's observed confounding traps | Manager 2, Atlas, Tokyo-supplier weighting |
| `missingness_scale` | Multiplies the `repeat_purchase_180d` outcome-dependent missingness probability (clamped to a valid `[0, 1]` probability) | The MNAR selection-bias trap |
| `rarity_scale` | Tightens (or loosens) each pattern's own numeric trigger threshold via `_tightened_min`/direct multiplication — capped so a threshold can never be pushed past its field's real achievable range | 7 of 9 patterns (P07's trigger is purely categorical/temporal, not tightened) |
| `drift_scale` | An additional multiplier on top of `effect_scale`, applied only to P07 — the one pattern whose own trigger condition is temporal (`drift_period == "late"`) | P07 only |

## Presets

Verified on the full 10,000-row benchmark (`difficulty_config(difficulty)`, default seed):

| Difficulty | effect | noise | confounding | missingness | rarity | drift | Total exposed rows | Total \|impact\| (EUR) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| EASY | 1.6 | 0.7 | 0.5 | 0.5 | 1.3 | 0.5 | 1,433 (14.3%) | 1,287,180 |
| MEDIUM | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1,163 (11.6%) | 668,522 |
| HARD | 0.6 | 1.5 | 1.6 | 1.6 | 0.7 | 1.6 | 561 (5.6%) | 244,114 |
| BRUTAL | 0.35 | 2.2 | 2.4 | 2.2 | 0.65 | 2.4 | 525 (5.3%) | 152,182 |

Total exposed rows and total absolute economic impact are summed across all 9 patterns — both
move monotonically EASY > MEDIUM > HARD > BRUTAL, the actual point of a difficulty ladder.
Individual `configured_effect`/`realized_effect` values, per-pattern support, and the specific
trigger conditions remain private (same restriction as the `TASK-003` benchmark itself — the
generator is withheld from ML Discovery because it encodes the mechanisms).

**BRUTAL's `rarity_scale` is 0.65, not more aggressive**, despite BRUTAL otherwise being the most
extreme preset on every other knob. This was chosen empirically, not arbitrarily: below roughly
`0.6`, two patterns (`P04`, `P08`) lose all support outright on the full 10,000-row benchmark —
each requires reaching the tail of its own capped-gaussian feature (`trip_duration_days`,
`booking_lead_days`) on top of two other conditions, so tightening their threshold further doesn't
make the pattern *rare*, it makes it *absent*, which is a different (and less useful) failure mode
for a discovery benchmark than "hard to find." `0.65` was verified to keep all 9 patterns at
nonzero support across every preset.

## Internal-consistency guarantee, at every difficulty

The same paired factual-minus-counterfactual arithmetic Statistics independently verified for the
frozen `MEDIUM` artifact (`HANDOFF-030`: `realized_economic_impact == |realized_effect| ×
affected_n` to the cent) is asserted directly, at every difficulty, by
`tests/analytics/test_difficulty_presets.py::test_every_preset_generates_and_stays_internally_consistent`.
Difficulty-scaling changes *how large or common* a pattern's effect is; it never changes the
generator's own replay methodology.

## How to generate a preset run

```sh
make benchmark-difficulty difficulty=hard
# or directly:
uv run python scripts/generate_synthetic_benchmark.py --difficulty hard
```

Writes to `synthetic_data_presets/<difficulty>/` (gitignored — generated, reproducible from a
seed, never the frozen benchmark) — never to `synthetic_data/`, which only the plain `make
benchmark` / no-flags CLI invocation touches, unchanged from before this task. `--seed` and
`--row-count` are also available; `--output` overrides the destination directory explicitly.

## Explicitly out of scope for this delivery

- **No wiring into the blind-discovery/validation pipeline.** `TASK-015`–`TASK-029` continue to
  run against `synthetic_data/` (`MEDIUM`) only. Using a harder preset to stress-test discovery is
  a real, valuable follow-up, but it is a new benchmark run with its own issuance/freeze/scoring
  cycle (`ADR-008`) — not implied by this task existing.
- **No public/blind-export path for preset runs.** `scripts/prepare_blind_workspace.py` and the
  blind-benchmark protocol are unchanged; they still operate on `synthetic_data/`. Exporting a
  preset run through that same pipeline is straightforward (same generator, same artifact shapes)
  but not built or tested here.
- **No re-tuning of the baseline (non-pattern) data-generating process.** `noise_scale` only
  touches outcome-generation noise, not the decision-time feature distributions (destination,
  segment, channel weights, etc.) — keeping those fixed means a harder preset is a harder version
  of *the same population*, not a different population.
