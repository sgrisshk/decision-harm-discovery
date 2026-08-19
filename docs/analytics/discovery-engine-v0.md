# Discovery Engine v0 methodology

**Owner:** ML Discovery · **Task:** TASK-015, TASK-058, TASK-060 · **Methodology version:**
`discovery-engine-v0.3.0`

## Scope and evidence boundary

This engine generates interpretable candidate associations for Statistics validation. It does not
estimate adjusted effects, classify evidence, demonstrate causality, or recommend deployment.
Every candidate must be described as “associated with lower contribution margin and awaiting
statistical validation.”

The run is pinned to analytical dataset `travel-bookings-analytical-v1.0.0`, identity
`dd7889f7d14264a7ae19e2fc11d95dcdb9da8ad4df3645b4adf7f8bab79cd423` (re-pinned twice 2026-08-18, per
ADR-030 then ADR-031; originally `98ad4e7e08e63ee9e31f9317ca408f2895da8bece49324482915e24df0aee04c`
— the underlying data is unchanged, see those entries), and Statistics-owned outcome contract
v1.0.0. The primary outcome is `contribution_margin_eur`; a decrease is harmful.

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

**Validated (2026-08-17, Statistics/Architect, `ADR-025`):** `TASK-019`/`TASK-028` ran against the
resulting official run (`task-058-remediation-20260817-001`); governing economic impact estimation
error dropped 204%→37.5% median (FAILED→PROMISING band), Top-K precision/leakage/direction accuracy
held or improved. `docs/benchmark/decision-gate.md`'s overall verdict moved FAILED→PROMISING.
`TASK-058` is `DONE`.

## Diversity-aware selection (v0.3.0, `TASK-060`)

**Problem diagnosed (2026-08-18, live-verified against
`artifacts/evaluation/task-028-task-058-remediation-001.json`):** the precision term fixed how
*well* any single rule scores; it did nothing about which *set* of rules fills the top-K. Of
`task-058-remediation-20260817-001`'s 15 persisted candidates, only **2 unique patterns** (`P01`,
`P06`) were represented — the other 13 were near-duplicate rescalings of `P01` (different numeric
thresholds on the same underlying features). Economic-weighted recall (45.2%) had not moved since
before `TASK-058`, because tightening a rule's population doesn't help discover a *different* rule
if the beam search never surfaces one. Mechanism: score-sorted single-pass selection plus a hard
`max_candidate_jaccard = 0.85` ceiling lets many pairwise-under-85%-overlap rescalings of one
dominant mechanism all individually pass — 80% overlap, for instance, clears the ceiling every
time — while collectively crowding out a genuinely distinct, lower-scoring pattern that never gets
a turn.

**Fix:** top-K selection (`_greedy_diverse_select`) is now a two-phase (interactions, then
singletons — preserving the pre-existing preference) greedy loop scored by marginal gain, not raw
score. Each round, every remaining rule's own `_development_score` is discounted by its current
maximum development-split exposure overlap with everything already selected:

```text
marginal = score × (1 − diversity_discount_weight × max_overlap_with_selected)
```

The discount is updated incrementally against only the most recently selected rule each round, not
recomputed from scratch. `DiscoveryConfig.diversity_discount_weight` defaults to `1.0` (full
discount); `0.0` disables it, which reproduces `v0.2.0`'s exact selection sequence
(regression-tested — the hard `max_candidate_jaccard` ceiling is independent of the weight and
still applies at either setting, so a rule over it is always skipped outright, never merely
deprioritized). This is a discovery-method decision, not a per-run tuning knob, chosen from generic
reasoning (score discounted by its own overlap fraction, the simplest form of marginal-gain
selection) — like the precision term, without opening `hidden_ground_truth.json` or
`synthetic_benchmark.py`. Full design rationale: `TASK-060` in `TASKS.md`, `ADR-035`.

**Explicitly not in scope:** `_development_score` itself (`TASK-058`, `ADR-023`) — this is about
which set of already-scored rules survives to the top-K, not how any single rule is scored.

**New official blind run issued (2026-08-18, ML Discovery):** `task-060-remediation-20260818-001`,
`status=PERSISTED`, 15 candidates, committed via signed receipt before any evaluation opened
`hidden_ground_truth.json`. Public, no-ground-truth comparison against
`task-058-remediation-20260817-001`: distinct categorical `(feature, value)` pairs used across the
15 candidates rose from 3 to 5 — `destination == Zanzibar` is new (matching the disclosed pattern
name "P02 Zanzibar family summer"), alongside the already-known `supplier == BlueWing` and
`destination == Tokyo`. Mean support fell a further ~33% (0.1787→0.1202) and total reported
exposure a further ~36% (3.56M→2.28M) on top of `TASK-058`'s reduction. **Caution flagged for
Statistics:** `CAND-012` uses `acquisition_channel == paid_search`, a feature the validation
contract's own trap taxonomy associates with a confounding-composition trap (T02) — diversity
surfacing a previously-never-selected feature is exactly the intended effect, but this specific
one needs G06/trap-rejection scrutiny, not an assumption it is a genuine pattern. `TASK-019`/
`TASK-028` against this run are requested in `HANDOFF-052`; not yet scored as of this writing.

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
