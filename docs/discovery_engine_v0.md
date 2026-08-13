# Discovery Engine v0 methodology

**Owner:** ML Discovery · **Task:** TASK-015 · **Methodology version:**
`discovery-engine-v0.1.0`

## Scope and evidence boundary

This engine generates interpretable candidate associations for Statistics validation. It does not
estimate adjusted effects, classify evidence, demonstrate causality, or recommend deployment.
Every candidate must be described as “associated with lower contribution margin and awaiting
statistical validation.”

The run is pinned to analytical dataset `travel-bookings-analytical-v1.0.0`, identity
`98ad4e7e08e63ee9e31f9317ca408f2895da8bece49324482915e24df0aee04c`, and Statistics-owned outcome
contract v1.0.0. The primary outcome is `contribution_margin_eur`; a decrease is harmful.

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
observed window, not savings. Preliminary order is development historical exposure with a mild
complexity penalty. Full multi-factor ranking is TASK-016.

Temporal direction consistency is the share of available later chronological splits whose raw
difference remains harmful. Actionability is a coarse discovery label: conditions involving a
directly controllable commercial field are `HIGH`; all others require business review. Neither
label substitutes for Statistics or Product review.

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
