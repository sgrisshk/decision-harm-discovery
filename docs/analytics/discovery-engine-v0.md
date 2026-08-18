# Discovery Engine v0 methodology

**Owner:** ML Discovery · **Task:** TASK-015, TASK-058 · **Methodology version:**
`discovery-engine-v0.2.0`

## Scope and evidence boundary

This engine generates interpretable candidate associations for Statistics validation. It does not
estimate adjusted effects, classify evidence, demonstrate causality, or recommend deployment.
Every candidate must be described as “associated with lower contribution margin and awaiting
statistical validation.”

The run is pinned to analytical dataset `travel-bookings-analytical-v1.0.0`, identity
`e7aff995359222bfedb6ee7332934a9238ce10b7e889f8812f27a0ff7da1e707` (re-pinned 2026-08-18 per
ADR-030; was `98ad4e7e08e63ee9e31f9317ca408f2895da8bece49324482915e24df0aee04c` — the underlying data
is unchanged, see that entry), and Statistics-owned outcome contract v1.0.0. The primary outcome is
`contribution_margin_eur`; a decrease is harmful.

## Search

- Inputs are only manifest-approved decision-time feature columns, the contracted primary
  outcome, and chronological split labels. Identifiers, metadata, post-decision fields, other
  outcomes, and raw calendar dates are not candidate conditions.
- Atomic numeric conditions use development-split quantiles at 20%, 40%, 60%, and 80%, expressed
  as `< threshold` or `>= threshold`. Categorical conditions use equality for features with no
  more than 12 levels.
- Deterministic beam search evaluates conjunctions of one to three conditions. Conditions in a
  conjunction must reference different features. A conjunction is rejected as tautological if it
  does not strictly reduce the exposed population relative to every immediate parent rule.
- Development eligibility requires `N >= 40`, support between 1% and 40%, and harmful raw outcome
  direction. Beam width is 80 and seed is 1729 (the v0 search is deterministic; the seed is
  recorded for forward compatibility).
- Candidate selection uses development data only. Validation and future-holdout outcomes never
  select or edit a condition; they are reported after conditions are fixed as temporal direction
  diagnostics.
- Identical and near-identical exposure sets are rejected using maximum Jaccard overlap 0.85.
  No atomic condition may occur in more than five reported candidates. These rules prevent a
  single broad association from filling the output with cosmetic variants.

The run manifest records all evaluated hypotheses, including pruned/discarded rules, rather than
only the reported top candidates. Conditions are serialized exactly and must not be edited after
Statistics returns validation results; a changed condition is a new candidate in a new search
family.

## Candidate metrics and preliminary order

For each split, deterministic code reports population N, exposed N, support, exposed/comparison
means, raw difference, sign-normalized harm per booking, and raw historical exposure. Historical
exposure is `harm_per_booking × exposed N`; it is unadjusted, unannualized value at stake over the
observed window, not savings. Preliminary order (which rules survive the beam search and which are
kept in the final top-K, not the same as `TASK-016`'s later multi-factor review ranking) is
development `harm_per_booking × exposed N^population_score_exponent` with a mild complexity
penalty — see "Precision term" below. Full multi-factor ranking (economic impact, support,
stability, actionability, novelty) is implemented separately in
`docs/analytics/candidate-ranking-v0.md` (`TASK-016`) and never edits the search's own output or
which candidates it selected.

Temporal direction consistency is the share of available later chronological splits whose raw
difference remains harmful. Actionability is a coarse discovery label: conditions involving a
directly controllable commercial field are `HIGH`; all others require business review. Neither
label substitutes for Statistics or Product review.

## Precision term (v0.2.0, `TASK-058`, `HANDOFF-043` remediation part 2)

**Problem diagnosed (`HANDOFF-043`, 2026-08-17):** v0.1.0's preliminary order was pure
`historical_exposure = harm_per_booking × exposed N`, linear in population. A rule that grows N
mainly by absorbing bookings with a weaker (but still same-signed) effect always outscored a
smaller, purer rule with the same or larger total exposure — even though the larger one is a worse
estimate of any single underlying mechanism. On the first compliant blind run
(`task-015-official-20260816-015`), matched candidates' exposed populations ran ~15–16× larger than
the true patterns they partially recovered (`docs/benchmark/task-029-benchmark-report-v1.md` §3.6),
diluting per-booking effect while inflating total reported exposure. Direct supporting evidence:
`supplier` and `destination` were both eligible `DECISION_TIME` search features on that run, yet
zero of the 15 reported candidates used any categorical condition — despite disclosed pattern names
("BlueWing", "Tokyo") implying those are exactly the features that would have narrowed a candidate
toward the true population. That is a search-selection artifact, not only a downstream reporting
one: a beam-search step adding a narrowing categorical condition structurally lost to one that
stayed broad, before any candidate was even reported, and no re-ranking of an already-selected
top-K (`TASK-016`) can recover a rule the beam search already discarded.

**Fix:** `_development_score` now raises `n_exposed` to `DiscoveryConfig.population_score_exponent`
(default `0.5`) before multiplying by `harm_per_booking`:

```text
score = harm_per_booking × n_exposed^population_score_exponent / (1 + 0.15·(condition_count − 1))
```

At the default `0.5` this is `harm_per_booking × sqrt(n_exposed)` — a geometric-mean-style balance
between total materiality (`harm_per_booking × n_exposed`) and per-booking purity
(`harm_per_booking` alone), so a rule that grows mainly by dilution no longer automatically beats a
smaller, stronger one, while a genuinely broad, undiluted true effect still wins on its own merits.
`population_score_exponent = 1.0` reproduces v0.1.0's exact linear ranking (regression-tested in
`tests/analytics/test_discovery_engine.py`); values must be in `(0.0, 1.0]`. This is a discovery-
method decision, not a per-run tuning knob, and — like `TASK-016`'s ranking weights — was chosen
from generic reasoning (a symmetric geometric mean, not fit to any specific candidate) without
opening `hidden_ground_truth.json` or `synthetic_benchmark.py`.

**Not yet done:** this fix has not yet been exercised through a new official `ADR-008` blind run;
`TASK-058`'s own done condition requires one, scored against matched true patterns, before it can
be considered validated rather than just implemented and unit-tested.

## Reproduction

```sh
uv run python scripts/run_discovery.py \
  synthetic_data/analytical/travel-bookings-analytical-v1.0.0 \
  artifacts/discovery/task-015-candidates.json
```

The 2026-08-13 run evaluated 6,945 hypotheses and persisted 15 candidates. The JSON artifact is
the numerical source of truth and includes exact config, conditions, metrics, warnings, dataset
identity, and outcome-contract version.

## Blindness limitation

This TASK-015 run did not open hidden-ground-truth artifacts. It is nevertheless not a qualifying
TASK-017 blind run because it executed from the full trusted checkout and the actor context had
access to repository documentation containing benchmark examples. TASK-017 must run as a fresh
actor scoped only to the ADR-008 allowlist workspace and must receive an evaluator-signed candidate
commitment before hidden truth is opened.
