# Discovery Engine v0 methodology

**Owner:** ML Discovery · **Task:** TASK-015, TASK-058, TASK-060, TASK-064 · **Methodology version:**
`discovery-engine-v0.5.0`

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

`ADR-047` subsequently publishes analytical input `travel-bookings-analytical-v1.1.0` for a
future, separate discovery iteration. It adds generic decision-time `travel_month`; it does not
retroactively alter this document's frozen v0.5.0 run or its dataset identity. Raw date thresholds
remain excluded from atoms.

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
  direction. The score-core beam width is 80; v0.5.0 additionally retains up to two best eligible
  rules per feature/operator structural signature before expansion. Seed is 1729 (the search is
  deterministic; the seed is recorded for forward compatibility).
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
contract's own trap taxonomy associates with a confounding-composition trap (originally
mislabeled `T02` here — corrected below to `T03`) — diversity surfacing a previously-never-selected
feature is exactly the intended effect, but this specific one needs G06/trap-rejection scrutiny,
not an assumption it is a genuine pattern.

**Verdict (2026-08-20, Statistics, `ADR-036`, `HANDOFF-052`): done condition NOT met, on all three
parts.** `TASK-019`/`TASK-028` ran for real against `task-060-remediation-20260818-001`. (1) Unique
true patterns recovered: still 2 (recall unchanged at 45.2%). (2) Top-10 precision: **90% → 40%**.
(3) Trap rejection: **`T03` promoted** — `CAND-012` reached `PASS`/`shadow_policy`, a hard
decision-gate disqualifier (the correction above: `T02` is `supplier == Atlas`, `T03` is
`acquisition_channel == paid_search`). Root cause: `CAND-012` clears gate G06 cleanly because G06's
fixed adjustment set (`manager`, `supplier`) doesn't cover `T03`'s actual confounders
(`customer_type`, `discount_rate`, `installments`) — a previously-latent gate limitation, first
triggered now that diversity explores more of the feature space, not a new defect and explicitly
*not* patched in response (would tune validation methodology to a result seen only after opening
`hidden_ground_truth.json`, exactly what `ADR-007` forbids). Does not affect the standing PROMISING
decision-gate verdict, anchored to `task-058-remediation-20260817-001` and untouched. `TASK-060`
stays `IN_PROGRESS`.

## Diversity iteration v0.3.1 (`TASK-060`, 2026-08-20)

The verdict above traces to a real property of `_greedy_diverse_select` itself, separate from the
G06 gap Statistics declined to patch: nothing in pure overlap-based marginal gain requires a
low-overlap pick to be any *good* — a statistically thin, disjoint rule can out-rank a reasonable
near-duplicate purely by being untouched by anything else, once the strongest low-overlap
candidates are exhausted. This is the standard failure mode diversity/maximal-marginal-relevance
methods hit without a relevance floor, and it is addressed generically here — no reference to
`T03`, `acquisition_channel`, or any other specific feature enters the fix, matching the same
discipline `ADR-036` held validation to.

Two changes, both in `DiscoveryConfig`:

- **`diversity_discount_weight` default lowered `1.0` → `0.5`.** At full strength, a rule with
  near-zero overlap keeps ~all of its own raw score regardless of how weak that score is; `0.5`
  still rewards genuine diversity without letting overlap alone override raw quality completely.
- **`min_diversity_relevance_ratio` (new, default `0.5`).** A rule must reach this fraction of the
  strongest score in its own selection phase (interactions or singletons, scored independently)
  before the greedy-diverse loop will consider it at all — computed once per phase, not
  re-evaluated as selection proceeds. `0.0` disables the floor (the original, too-permissive
  `v0.3.0` behavior).

`tests/analytics/test_discovery_engine.py` proves both properties on fully generic fixtures (a
"strong distinct pattern" that the default still correctly prefers over a near-duplicate, and a
"weak disjoint noise" rule the floor now excludes that the original full-strength configuration
would have admitted) and that `diversity_discount_weight=1.0`/`min_diversity_relevance_ratio=0.0`
reproduces `v0.3.0`'s exact original behavior, for regression comparison.
`DISCOVERY_METHOD_VERSION` bumps `"discovery-engine-v0.3.0"` → `"discovery-engine-v0.3.1"`.

**New official blind run (2026-08-20, ML Discovery):** issued/verified/launched/frozen/committed
under the same `ADR-008` protocol, before any evaluation opened `hidden_ground_truth.json` — see
`TASKS.md` `TASK-060` for the run ID and public comparison; `TASK-019`/`TASK-028` against it are
requested in a new handoff, not yet scored as of this writing.

**Verdict (2026-08-20, Statistics, `HANDOFF-054`):** safety held (90% Top-10 precision, 100%
direction accuracy, no trap promoted, `T03` specifically no longer reaching `PASS`), but unique
matched patterns stayed at 2 — unchanged across every run to date, including before `TASK-058`.
Handed back one diagnostic question: is the ceiling a selection-stage artifact, or upstream in the
beam search?

## Diagnostic: the ceiling is selection-stage (`ADR-038`, `HANDOFF-055`)

`scripts/diagnose_candidate_pool_recall.py` (new, committed, not part of the official pipeline)
locally reproduced `task-060-iteration-20260820-002`'s exact search — byte-faithful,
`evaluated_hypotheses` matched exactly — but stopped before `_greedy_diverse_select` ever ran. The
full **5,197-candidate eligible pool** (vs. 15 persisted) contains a partial-or-better match for
every one of the 6 missing patterns, several with 15–84 independently redundant full matches — not
one lucky rule. Opening `hidden_ground_truth.json` here is the same established
post-hoc-analysis-of-an-already-committed-run discipline `TASK-028` uses (`ADR-025`).

Two findings narrowed *where* the fix should point, not just the headline answer: every hit sits at
0.106–0.328 of its phase's best score — well under `min_diversity_relevance_ratio=0.5` — confirming
the floor built to stop the `T03` regression is also excluding genuine weak signal. Separately,
`P03`'s best-matching rule shares `T03`'s exact apparent feature
(`acquisition_channel = paid_search`, confirmed programmatically) — structurally unsafe to chase by
loosening selection at any ranking, since it would very likely re-trigger the same `G06` gap
`ADR-036` declined to patch reactively; `P04` has zero full-match candidates anywhere in the pool, a
beam-search question, not a selection one. Recommendation: scope the next iteration to `P02`/`P08`/
`P09` specifically (real, redundant, trap-free signal), not a uniform floor change.

## Stability-credited effective score, v0.4.0 (`TASK-060`, `ADR-039`)

**Constraint carried over from the diagnostic:** do not raise or lower
`min_diversity_relevance_ratio` globally — `ADR-038` already showed that reaching `P02`/`P08`/`P09`
this way would also reopen the `T03` risk `v0.3.1` fixed, since a single global ratio cannot tell
"weak because it's genuinely thin" apart from "weak because it's a rescaling nobody has looked at
yet." The floor itself, and `diversity_discount_weight`, are unchanged by this iteration.

**Fix: change what gets compared against that same, unmoved floor.** Every rule's raw
`_development_score` is now credited by its own cross-split stability
(`_temporal_consistency` — the same later-split direction-agreement fraction already reported as
`Candidate.temporal_direction_consistency`, just computed earlier so selection can use it too, not
only the final report):

```text
effective_score = development_score × (1 + stability_credit_weight × temporal_consistency)
```

`stability_credit_weight` defaults to `0.5`; `0.0` reproduces `v0.3.1` exactly (regression-tested —
`effective_score == development_score` for any consistency value at weight `0.0`). A rule with no
later-split exposure gets `0.0` consistency, never treated as stable — the same conservative
convention `TASK-016`'s ranking module already uses for missing stability. This `effective_score`,
not the raw score, is what both the relevance floor and the marginal-gain formula compare from this
version on.

**Alternatives considered (chose one, not both, per this iteration's own scope):**

- **Pattern-shape-aware relaxation** (a lower floor specifically for candidates whose condition
  features don't overlap features previously seen in trap-suspicious candidates) — considered,
  rejected. Any workable version of this either (a) tracks which features were flagged by past
  runs' actual trap findings — which is exactly the reactive, ground-truth-informed tuning
  `ADR-007`/`ADR-036` forbid, since it would encode `T03`'s already-known identity into future
  behavior even if phrased as "feature shape" rather than "acquisition_channel" by name — or (b)
  requires inventing a new a-priori "assignment-type vs. commercial-term" feature taxonomy with no
  existing basis in this codebase, whose boundary would need its own separate justification and
  carries a real risk of being retrofitted to match a split (`customer_segment`/`party_size` vs.
  `acquisition_channel`) this session already knows from the `ADR-038` diagnostic — a much harder
  discipline to hold cleanly than a feature-identity-agnostic formula.
- **Stability-weighted marginal gain (chosen).** References no feature, trap, or pattern identity;
  the identical formula applies to every rule regardless of which columns its conditions touch.
  Reuses an already-established, already-computed statistic rather than inventing a new signal, and
  is well-motivated independent of this benchmark: a weak effect that repeats across independent
  time periods is standard evidence of a genuine mechanism rather than a development-split
  artifact — the same logic the validation contract's own temporal-stability gate (G10) applies
  downstream, pulled one stage earlier into search.

**Honest limitation, not hidden:** stability credit cannot promise to exclude `P03`/`T03` specifically
if that trap's association is itself stable across splits — plausible, since `ADR-036` described it
as a structural composition effect, not sampling noise. This iteration does not depend on that
exclusion happening by construction: `T03` promotion is independently re-checked by `TASK-028`
against `hidden_ground_truth.json` regardless of what this formula does, exactly as it was for
`v0.3.0` and `v0.3.1`. If a `P03`/`T03`-shaped candidate reaches the top-15 again and gets promoted,
this iteration's own done condition (no trap promoted) fails and it is reported as such — not
declared safe by assumption.

**New official blind run, and an honest null result (`ADR-039`, `HANDOFF-056`):**
`task-060-iteration-20260820-003` was issued/verified/launched/frozen/committed under the same
`ADR-008` protocol, before any evaluation opened `hidden_ground_truth.json` — and is **byte-
identical, condition-for-condition, to `task-060-iteration-20260820-002`** (verified by direct
diff). `TASK-019`/`TASK-028` were not re-requested — identical candidates imply an identical
already-known outcome. Root cause, checked directly against the analytical dataset (not
`hidden_ground_truth.json`): the dominant pattern's rescalings and `customer_segment == family`
(`P02`/`P09`'s best pool candidate) are *both* fully stable (`consistency = 1.0`) — a uniform
credit cannot differentiate two equally stable candidates, so ranking doesn't move. `party_size <
2.0` (`P08`'s best candidate) is only partially stable (`0.5`), *less* stable than the dominant
pattern, so uniform credit would if anything worsen its position. The mechanism's premise — weak
true patterns are differentially more stable than the dominant rescaling family — does not hold on
this data: the dominant pattern is itself genuinely stable, not a fragile artifact. `TASK-060`
remains `IN_PROGRESS`; the next iteration needs a mechanism beyond the two `ADR-038` scoped
between (see `ADR-039`'s closing note on a possible floor-reference-point change, not itself
authorized or implemented here).

## Floor reference point, v0.4.1 (`TASK-060`, `ADR-040`)

**Diagnosis:** the relevance floor's reference point — what `min_diversity_relevance_ratio` is a
fraction *of* — was always the phase's single maximum `effective_score`. `ADR-038`'s diagnostic
showed that maximum is always the dominant rescaling family (largest population × effect, by
construction of `_development_score`), so the floor was measured against one outlier rather than
the pool's typical quality — systematically excluding weaker genuine patterns (`P02`/`P08`/`P09`
sat at 0.11–0.33 of that maximum) with no regard for whether they were noise or signal. Neither
`v0.4.0`'s stability credit nor `ADR-038`'s rejected uniform-floor-lowering addressed this specific
property; this iteration does.

**Fix:** the reference the floor is measured against is now `relevance_floor_percentile`-th
percentile of the phase's own `effective_score` distribution (`_percentile`, linear
interpolation), not its maximum. Default `0.75` — a standard robust-statistics choice: a rule must
be in its phase's upper quartile, which is far less sensitive to a single extreme outlier than the
maximum, while still requiring genuinely above-average quality, unlike the median (`0.5`), which
would let roughly half the eligible pool through regardless of what the diversity/overlap
mechanism then does. `relevance_floor_percentile=1.0` reproduces the maximum exactly — `v0.4.0`'s
behavior — and combined with `stability_credit_weight=0.0` reproduces `v0.3.1` exactly
(regression-tested). `min_diversity_relevance_ratio` itself is unchanged, per `ADR-038`'s own
constraint; only what it multiplies changed. References no specific feature, trap, or pattern — a
property of the pool's own score distribution shape only.

**New official blind run:** issued/verified/launched/frozen/committed under the same `ADR-008`
protocol, before any evaluation opened `hidden_ground_truth.json` — see `TASKS.md` `TASK-060` for
the run ID, public comparison, and `TASK-019`/`TASK-028` outcome.

## Structure-covered expansion beam, v0.5.0 (`TASK-064`, `ADR-045`/`ADR-046`)

`TASK-064` changes the search stage, not `TASK-060`'s closed top-K selection stage. The required
pre-code trace found that all 25 eligible depth-1 rules already fit inside the old width-80 beam,
but depth 2 contained 1,201 eligible rules. Relevant, already-disclosed feature pairs were scored
at ranks 319, 606, and 908–1047: valid rules with adequate support, but unable to produce a third
condition because a global score-only top 80 owned every expansion right. Changing their
generation order would not change their score and therefore could not fix this.

The v0.5.0 expansion beam is the union of:

1. the previous global top `beam_width=80` score core; and
2. up to `beam_rules_per_structure=2` best rules for every structural signature, where a signature
   is only the sorted tuple of `(feature, operator)` pairs and deliberately excludes values.

The combined beam is sorted by the unchanged development score and hard-capped at
`max_expansion_beam_size=512`. On the public travel analytical frame the depth-2 expansion beam is
418 rules and the evaluated hypothesis family grows from 6,557 to 26,213; a truth-free local run
completed in about 2m19s on the development machine. The cap prevents datasets with many
feature/operator structures from making the reserve unbounded. Setting
`beam_rules_per_structure=0` reproduces v0.4.1's score-only beam exactly.

No eligibility threshold, support floor, score formula, maximum interaction depth, final
selection knob, feature timing class, or candidate schema changes. No feature/pattern/trap name is
present in the beam logic or its synthetic tests. The method only changes whether an already
eligible rule may form a deeper conjunction.

The same trace established a separate hard limitation: seasonal P04 is not representable because
raw dates are excluded and the analytical contract supplies no decision-time month/season feature.
This method does not pretend beam coverage can recover a missing atom. Adding a generic temporal
feature, if desired, is separate Data Engineering/architecture work and a new input contract.

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
