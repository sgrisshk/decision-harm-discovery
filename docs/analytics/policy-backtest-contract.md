# Policy Backtest Contract v1.0.0 (TASK-032)

**Owner:** Statistics · **Implements:** `docs/analytics/validation-contract.md` §9 ·
**Fills:** `docs/product/policy-candidate-domain-model.md` §7's reserved `backtest_result` ·
**Module:** `packages/analytics/src/policy_analytics/backtest/` · **CLI:**
`scripts/run_backtest.py` · **Validated by:** `TASK-033` (`scripts/validate_backtest_synthetic.py`,
run only after this document was frozen — see its own section below)

## 1. What a backtest is, and is not

A backtest is a **mechanical replay**: given a trigger condition (a Finding's own
`pattern.conditions`, verbatim — never re-derived, per
`docs/product/policy-candidate-domain-model.md` §2), it asks "what did the decisions this
condition would have flagged actually look like, in a window never used to find or grade this
condition." It is not:

- **A causal estimate of intervention effect.** It does not simulate a human reviewer's actual
  decisions, an actual policy rollout, or how customers/managers/suppliers would respond to the
  policy existing. `docs/analytics/validation-contract.md` §9: "an upper bound on mechanical
  effect... not a forecast."
- **A second, independent piece of evidence.** It never changes a Finding's `evidence_level` — a
  backtest is a downstream application of an already-graded Finding, not a new statistical test of
  the underlying pattern.
- **An experiment.** `EXPERIMENT_ONLY` readiness means designing an actual controlled experiment;
  a backtest is not a substitute for one, and reaching a positive backtest does not retroactively
  make the underlying evidence experimental (`docs/analytics/validation-contract.md` §7's design
  ceiling on evidence level is untouched by this module).

## 2. The five methodological rules, and how this implementation satisfies each

`docs/analytics/validation-contract.md` §9, restated against the actual code:

| Rule | Implementation |
|---|---|
| Decision-time only | The trigger condition is always a Finding's already-`G01`/`G02`-cleared `DECISION_TIME` conditions — the backtest evaluates the same condition, never reintroduces a post-decision field. |
| Both sides always | `avoided_bad_outcomes` and `suppressed_good_outcomes` are both always present in `BacktestResult` and always sum to `affected_decisions` — enforced in `__post_init__`, not just by convention. |
| No behavioural extrapolation | `benefit` is the raw (unadjusted) future_holdout mean difference — see §4 — and every result carries a fixed `methodology_disclosure` string stating the mechanical-upper-bound framing verbatim. |
| Out-of-period first | `window` is hard-constant `"future_holdout"` (`BACKTEST_WINDOW_SPLIT`) — not a caller-supplied parameter. A result computed against any other split is rejected by `BacktestResult.__post_init__`. |
| Uncertainty | The same cluster bootstrap (`customer_id`, `cluster_cells`/`cluster_bootstrap_replicates`/`percentile_ci` from `validation.apply`) already used everywhere else in this repository, restricted to `future_holdout`. A `net_effect` whose interval includes zero sets `no_measurable_net_effect = True`. |

Operational cost is §9's sixth rule, big enough to warrant its own section (§5 below).

## 3. `affected_decisions`, `avoided_bad_outcomes`, `suppressed_good_outcomes`

All three are counts over `future_holdout` records matching the trigger condition:

- `affected_decisions` = N matching the trigger in `future_holdout` (both groups combined is the
  comparison; this is the exposed count only).
- `avoided_bad_outcomes` = N of those with `contribution_margin_eur < 0` — using the outcome
  contract's own already-documented absolute threshold ("a negative value... is a booking that
  lost money outright, not merely an underperforming one," `policy_analytics.outcomes.contract`),
  not a new invented cutoff.
- `suppressed_good_outcomes` = N of those with `contribution_margin_eur >= 0` — the flip side:
  decisions that would be flagged for review despite not losing money outright. This is the
  "friction" §9 requires be shown, not hidden.

**v1.0.0 scope limit, disclosed, not silent:** the bad/good split is only defined for
`contribution_margin_eur` (`BAD_OUTCOME_SUPPORTED_OUTCOME_ID`). `run_backtest()` raises rather than
guessing a threshold for any other outcome — extending this to a secondary outcome needs its own
disclosed threshold decision, not an improvised one at call time.

**Missingness is never silently excluded.** `contribution_margin_eur` has
`MissingDataPolicy.COMPLETE` (0% missingness, verified — `TASK-013`/`TASK-014`). If a missing
value is nonetheless found among `future_holdout`'s affected records, `run_backtest()` raises —
the same "dataset no longer matches its pinned identity, treat as suspect" posture
`DISCOVERY_CONTRACT.primary_outcome_missing_handling` already takes.

## 4. `benefit` — raw, not adjusted, and why

`benefit.value = harm_per_booking(future_holdout raw difference) × affected_decisions` — the
**unadjusted** exposed-minus-comparison difference within `future_holdout`, harm-signed the same
way as everywhere else (`OutcomeDefinition.harm_multiplier`). `benefit_is_adjusted` is always
`False` in v1.0.0, a checkable field rather than an assumption a caller has to remember.

This is a deliberate, motivated choice, not a shortcut: `docs/analytics/validation-contract.md` §9
asks for "an upper bound on mechanical effect." The validation contract's own `adjusted_effect`
(stratified manager × supplier) is *more conservative* — using it here would understate the
disclosed upper bound while implying more rigor than a mechanical replay actually has. The raw
difference, clearly labeled as raw, is the more honest number for what this contract is actually
claiming.

Uncertainty: the same cluster-bootstrap replicate set (`customer_id`, 1000 replicates,
`BACKTEST_BOOTSTRAP_REPS`), harm-signed and scaled by `affected_decisions` — the identical pattern
`economic_impact.py` already uses for `historical_impact`, just restricted to `future_holdout`
instead of the combined window, and unadjusted instead of the validation contract's stratified
figure.

## 5. Operational cost — never invented

§9: "Review effort, exception handling, and customer friction are included as costs. A rule that
saves €30k and requires 400 manual reviews is not a saving." This module never invents a
cost-per-review figure — the same disclosed-placeholder discipline
`ValidationThresholds.min_material_annual_impact` already takes pending real customer economics
(`OQ-004`):

- `operational_cost_per_review_eur` is an optional, explicit, caller-supplied input
  (`--cost-per-review-eur` on the CLI). When omitted, it is `None`, `operational_cost` is `None`,
  and `net_effect_is_cost_exclusive` is `True` — a distinct, checkable field name so a reader
  cannot mistake a benefit-only figure for a cost-netted one by only looking at `net_effect`.
- When supplied, `operational_cost.value = cost_per_review_eur × affected_decisions` (no sampling
  interval of its own — it is an assumed constant, not something estimated from data;
  `method = "assumed_input_no_interval"` says so explicitly), and `net_effect = benefit -
  operational_cost`, with `net_effect`'s interval shifted by the same constant.

Physical review volume (`affected_decisions`) is always reported regardless of whether a EUR cost
assumption is supplied — a reader can always see "N reviews required" even with no cost figure.

## 6. `no_measurable_net_effect`

Mirrors the identical rule already used for `EconomicImpactResult`/gate G15: `net_effect`'s
interval excluding zero (`ci_low > 0` or `ci_high < 0`) is required for a positive claim.
`no_measurable_net_effect = True` whenever the interval crosses zero — the UI-facing rule
(`docs/product/policy-candidate-domain-model.md` §7: "must be shown as 'no measurable net effect'
— never as a positive") reads this field directly rather than re-deriving it from the interval.

## 7. What this contract fills, and what remains blocked

Fills `docs/product/policy-candidate-domain-model.md` §7's reserved, `null` `backtest_result`
field — field-for-field: `affected_decisions`, `avoided_bad_outcomes`,
`suppressed_good_outcomes` (Product's "suppressed good outcomes," same concept, `both sides
always`), `benefit`, `operational_cost`, `net_effect` with interval. `PolicyCandidateStatus`
cannot reach `APPROVED_FOR_CUSTOMER_DECISION` until a `TASK-031`-generated Policy Candidate
actually exists and this module's result is wired into it — `TASK-031` (the generator) is a
separate, `TASK-030`-gated task this module does not depend on and does not implement. This module
operates directly on a Finding's frozen `pattern.conditions`, which already exist independent of
`TASK-031`'s persistence layer — see `TASKS.md`'s `TASK-032` entry for why the pure engine could be
built and tested ahead of the generator.

## 8. TASK-033 — synthetic validation against known ground truth

Run only after this document and the engine's own code were frozen — the same sequencing
discipline as `TASK-018`→`TASK-028` (methodology fixed before ground truth is opened for grading,
never for tuning). Full method and results: `docs/benchmark/task-033-backtest-validation-v1.md`.

**What ground truth can and cannot check.** `hidden_ground_truth.json`'s per-pattern
`realized_counterfactual_effects` is a *whole-population* paired-counterfactual mean effect (every
outcome, computed via `synthetic_benchmark.py`'s `disabled_pattern_id` replay) — it has no
`future_holdout`-only breakdown. `TASK-033` therefore validates this engine's `benefit` figure
against **`mean_effect × |pattern.affected_booking_ids ∩ future_holdout booking IDs|`** — an
explicit, disclosed approximation that assumes the pattern's per-booking effect is homogeneous
across time, not a re-run of the counterfactual generator restricted to `future_holdout`. This is
the same category of assumption already used throughout this benchmark (no per-subgroup
heterogeneity model exists) and is stated as an approximation, not presented as exact ground
truth.
