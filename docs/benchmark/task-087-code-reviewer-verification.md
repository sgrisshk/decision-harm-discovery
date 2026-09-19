# TASK-087 — `CODE_REVIEWER` independent adversarial review of the like-with-like calibration metric design (`ADR-090`)

**Verdict: APPROVED WITH REVISION NEEDED.** The core like-with-like property — identical population
masks (mandate 1), calibration error kept genuinely separate from candidate-localization quality
(mandate 4), and the adversarial Case C/D property (mandate 5) — is independently confirmed clean.
The coupling check (design built against `TASK-085`'s own `O1`/`O2` estimand, never against
`TASK-086`'s serialization/field-naming choices) is also confirmed clean. Two findings require the
design document to be revised before any implementation task
(`tests/analytics/test_o1_temporal_calibration.py`) opens:

1. **Mandate 3 (defined behavior under population/candidate-membership drift) is not fully met.**
   The design's own Check 5 claims "defined behavior under population drift," tested only by its own
   Case E (a smooth 30% shrink, rate stable). This review constructs the boundary case Case E never
   reaches — a candidate whose `future_holdout` exposure is genuinely zero, a plausible, not
   contrived, outcome given `discover_candidates` selects candidates using only development-split
   eligibility — and finds the design's own literal computation (as specified in §1 and implemented
   in its own diagnostic script) raises an **uncaught `AssertionError`** rather than returning any
   verdict. `apply.py`'s own existing `G10` temporal-stability gate, using the identical underlying
   `split_stats` inputs, already handles this exact scenario defensively. The design does not
   inherit that discipline. **Required revision:** the design document must explicitly specify
   graceful degradation at this boundary (mirroring `G10`'s own pattern) before implementation.

2. **Mandate 2 (no leakage from `future_holdout`) — the design's own disclosed Check 4 caveat is
   confirmed real and demonstrably live, not merely theoretical.** The design document's own
   "empirically null" finding (one dataset, one seed, byte-identical top-15) is independently
   reproduced on a second, genuinely different dataset (also byte-identical) — but a constructed
   engineered case proves, using the real unmodified engine code, that `stability_credit_weight`'s
   channel **does** flip real top-K candidate selection whenever two candidates' raw development
   scores are close enough for the stability credit margin to matter. This does not contradict the
   design document's own CONDITIONAL characterization of Check 4 (§4.4 already names this exact
   hypothetical) — it independently confirms that hypothetical is realizable, not merely plausible.
   This finding does not by itself block approval, because the design's own recommended scope (a
   form-test/regression-suite check, never a `decision-gate.md` metric, with a binding requirement to
   re-run the leakage diagnostic after any relevant discovery-selection config change) already
   accounts for a live, not-fully-eliminated leakage risk. But the review record must state plainly
   that this caveat carries real, demonstrated weight, not a remote theoretical one.

No other defect was found. Every check below uses the real, unmodified `policy_analytics` code;
independent verification scripts (new datasets, new constructions, new adversarial cases — never
merely re-running the implementer's own scripts and trusting their output) are committed alongside
their raw JSON output.

**Scripts and raw output committed by this review:**
- `scripts/review_task087_check1_null_divergence_probe.py` →
  `docs/benchmark/task-087-review-check1-null-divergence-raw.json`
- `scripts/review_task087_check2_leakage_cross_dataset_and_engineered.py` →
  `docs/benchmark/task-087-review-check2-leakage-cross-dataset-raw.json`
- `scripts/review_task087_check3_population_edge_cases.py` →
  `docs/benchmark/task-087-review-check3-population-edge-cases-raw.json`
- `scripts/review_task087_check5_independent_clustered_adversarial.py` →
  `docs/benchmark/task-087-review-check5-independent-clustered-adversarial-raw.json`

---

## Mandate 1 — Identical population and time support on both sides, independently re-verified

**Verdict: PASSES, cleanly.**

Direct code trace, not merely re-reading the design document's own Sec 2 (`apply.py`'s
`_validate_one`, lines ~514–523; `discovery/engine.py`'s `_metric`, lines 277–301): both compute one
`full_mask = frame.select(rule_expr(conditions)...)` (respectively `_rule_expr`) over the WHOLE
frame, then slice it per split via `full_mask.filter(split_frame_mask)` — the predicted side
(development+validation) and realized side (future_holdout) genuinely share one mask-generating
rule, differing only in which rows of the *same* boolean series each side keeps. Confirmed directly,
matching the design document's own claim exactly.

**A divergence channel the design document's own trace does not itself address, independently
probed and ruled out for the real dataset:** Polars' three-valued boolean logic makes a rule's mask
value `null` (not `False`) when a condition's own feature is null for a row, and `frame.filter(mask)`
silently drops null-mask rows from BOTH `mask` and `~mask`. If a `DECISION_TIME` feature's null rate
differed between development+validation and future_holdout, the *effective* eligible population for
a rule could diverge across the two windows despite an identical mask-generating rule. Direct
inspection (`scripts/review_task087_check1_null_divergence_probe.py`) found **zero nulls in any
`DECISION_TIME` feature, in any split**, for the real `travel-bookings-analytical-v1.1.0` dataset.
This channel does not materialize today — a clean, independently-confirmed pass, disclosed as
dataset-contingent rather than an architectural guarantee (a future dataset version with nulls in a
`DECISION_TIME` feature would need this check re-run).

Also independently confirmed: the temporal split boundaries are genuinely chronological
(`temporal_splits.py`: `future_holdout_start = "2025-07-01"`, strictly after `validation_end =
"2025-06-30"`), so the realized side is genuinely later in time than the predicted side, not merely
disjoint by label.

## Mandate 2 — No leakage from `future_holdout` into discovery, fitting, or the calibration target

**Verdict: the design document's own CONDITIONAL verdict (predicted-side computation clean;
candidate-selection channel real, disclosed, and — per this review's own independent construction —
demonstrably capable of mattering, not merely theoretically present) is confirmed, and this review's
own findings argue the caveat should be weighted as a live, not merely theoretical, risk.**

**Predicted-side computation.** Independently re-confirmed clean by direct trace: `split_stats` is
called on frames filtered to `development`/`validation` only (`apply.py` `_validate_one`); the
tier-2 `_stratified_adjustment` fits on `dev_frame = frame.filter(split_label == "development")`
alone (line ~616, confirmed by direct read) — no row used to form either the tier-1 or tier-2
prediction is drawn from `future_holdout`.

**The selection-stage channel, re-derived independently, not accepted by citation.** Direct read of
`discovery/engine.py` confirms the design document's own trace exactly:
`_temporal_consistency(frame, rule, outcome)` (lines 410–427) computes `_metric(..., "future_holdout")`
for every pool candidate, and its output (a `consistency` fraction in `{0.0, 0.5, 1.0}`, i.e. the
share of available later splits whose harm sign agrees with development) feeds
`_apply_stability_credit(raw_score, consistency, weight)` = `raw_score * (1 + weight * consistency)`
(line 430). This `effective_score`, not the raw development score, is what `_greedy_diverse_select`
ranks and thresholds candidates on. `DiscoveryConfig.stability_credit_weight` defaults to `0.5`
(confirmed unconditional: `scripts/run_discovery.py` does not override it), and `DiscoveryConfig.seed`
is confirmed **unused anywhere inside `discover_candidates`** (no `random` import in `engine.py` at
all — the whole search is deterministic given the frame), so varying `seed=` alone, as one might
first try, is a no-op; a genuinely different dataset is the only lever available to test breadth.

**Two independent tests beyond the design document's own single dataset/seed run
(`scripts/review_task087_check2_leakage_cross_dataset_and_engineered.py`):**

1. **Cross-dataset comparison on `travel-bookings-analytical-v1.0.0`** (a domain instance the design
   document's own diagnostic never touched): `stability_credit_weight=0.5` vs. `0.0` produces
   **byte-identical top-15 sets**, reproducing the design document's own finding on a second,
   independent dataset. This strengthens the null finding's generality.
2. **Synthetic engineered tie-break case (the decisive test).** Two candidate rules constructed so
   R2's raw development-split score is ~10% HIGHER than R1's, but R1's cross-split sign is stable
   (`consistency=1.0`) while R2's flips negative in validation/future_holdout (`consistency=0.0`),
   with `top_k=1` forcing one decisive pick. Result, using the real unmodified
   `discover_candidates`/`_temporal_consistency`/`_apply_stability_credit`/`_greedy_diverse_select`
   code: under `weight=0.0`, R2 correctly wins on raw score alone; under `weight=0.5` — the real
   shipped default — **the winner flips to R1**, because R1's 1.5× stability credit overturns R2's
   raw-score lead.

**What this means, stated plainly.** The design document's own §4.4 already names the exact
hypothetical this construction realizes ("a candidate pool with more genuinely mixed-sign later-split
behavior near the `relevance_floor_percentile` cutoff could see this channel actually reorder or
exclude a candidate"). This review's own independent construction confirms that hypothetical is
**realizable under the real, unmodified engine code**, not merely a remote theoretical possibility —
the mechanism requires only a modest (~10%) raw-score gap between two candidates with divergent
cross-split stability, a condition with no reason to be rare in a real candidate pool. This does not
overturn the design document's own CONDITIONAL characterization of Check 4 — it independently
substantiates it, and argues the caveat should be read as carrying real, demonstrated weight. This is
consistent with, and reinforces, the design document's own recommendation (§8.1: form-test/regression
suite only, never a `decision-gate.md` graded metric) and its own binding recommendation (§4, "any
future change to `stability_credit_weight`... must re-run [the leakage diagnostic]... before this
calibration design continues to be trusted"). That binding recommendation should be treated as
load-bearing, not a minor footnote, given this review's findings.

## Mandate 3 — Defined behavior when candidate membership changes between development and holdout

**Verdict: FAILS as currently specified — the design document's Check 5 "defined behavior under
population drift" claim is not fully accurate; a concrete, plausible boundary case crashes rather
than resolving.**

The design document's own Case E tests only a smooth population shrink (30% of reference, rate
stable) — a case that remains computable throughout. This review constructs three cases the design
document's own evidence does not cover (`scripts/review_task087_check3_population_edge_cases.py`):

- **Case F1 — population vanishes to zero in `future_holdout`.** A candidate with substantial
  predict-window exposure (n=600) but ZERO matching rows in `future_holdout`. `split_stats` returns
  `None` whenever either the exposed or comparison group is empty in a window (`apply.py`'s own
  early return). This is not contrived: `discover_candidates`'s own eligibility is decided entirely
  from the `development` split, with no requirement that a selected rule have any exposure at all in
  the much shorter (6-month vs. 18-month) `future_holdout` window, especially for a narrow-support
  rule. **Result: the design's own proposed computation — literally as specified in §1 and
  implemented in its own diagnostic script's `_calibration_check` (`assert predict_stats is not None
  and realize_stats is not None`) — raises an uncaught `AssertionError`.** `apply.py`'s own existing
  `G10` temporal-stability gate (lines ~741–757), consuming the identical `split_stats` outputs,
  already guards against exactly this scenario (`retention = ... if holdout and dev.harm_per_booking
  else 0.0`, `same_sign` requires all three splits present) and degrades to a defined FAILED verdict.
  The proposed design does not inherit that discipline.
- **Case F2 — population explodes 40× with a moderate rate shift** and **Case F3 — population
  shrinks to a handful of records (n=5) with a genuinely different rate**: both remain correctly
  computable and resolve sensibly (`calibration_ok=False` in both, correctly detecting genuine
  drift/miscalibration even at extreme size ratios). These controls confirm the defect is specific
  to the unguarded zero-population boundary, not the population-drift design generally, and confirm
  the coverage test still does genuine statistical work away from that boundary.

**Required revision, concrete and narrow:** before `tests/analytics/test_o1_temporal_calibration.py`
is built, the design document must explicitly specify behavior when either side's `split_stats`
returns `None` — the natural, minimal fix is to mirror `G10`'s own established pattern (report
"not computable" / a structural absence, never crash), which requires no new statistical machinery,
only a defined branch the design's own prose does not currently commit to.

## Mandate 4 — Calibration error genuinely kept separate from candidate-localization quality

**Verdict: PASSES, cleanly, independently confirmed by direct trace.**

`_calibration_check` (the design's own proposed computation, per its diagnostic script and this
review's independent reproductions) reads only `sel` (the rule mask), `window`
(predict/realize), the outcome column, and `customer_id` (the clustering column) — confirmed by
direct reading of the function signature and body, not by trusting the design document's own
assertion. Direct grep of `apply.py`, `scripts/diagnose_task087_check4_future_holdout_leakage.py`,
and `scripts/diagnose_task087_check5_7_calibration_adversarial.py` for `hidden_ground_truth`,
`affected_booking_ids`, or `patterns_by_id` finds **zero matches** in any code path the calibration
computation itself touches — `apply.py` even carries its own standing comment (line 21) that it must
never be edited to read `hidden_ground_truth.json`. The `true_mechanism_member` column used in the
implementer's Case C/D construction is confirmed, by direct reading, to be used only for case
construction/interpretation in the surrounding script — never read by `_calibration_check` itself.
There is no code path by which the verdict could depend, even indirectly, on ground-truth overlap.

## Mandate 5 — The adversarial Case C/D constructions are genuinely independent evidence

**Verdict: PASSES — independently confirmed with a materially different construction, not a re-run
of the implementer's script.**

**A real gap found in the implementer's own evidence, and filled here.** The implementer's own
`case_c_well_calibrated_zero_overlap`/`case_d_poorly_calibrated_high_overlap`
(`scripts/diagnose_task087_check5_7_calibration_adversarial.py`) assign a UNIQUE `customer_id` per
synthetic record, so every `cluster_cells` entry has exactly one record — their adversarial evidence
never actually exercised the CLUSTERING `cluster_bootstrap_replicates` exists for (accounting for
within-customer correlation from repeat bookings). Direct inspection of the real dataset
(`identifiers.csv`) confirms this matters for real data: 3200 unique customers across 10000 rows,
most contributing 3–4 rows each.

`scripts/review_task087_check5_independent_clustered_adversarial.py` rebuilds a well-calibrated/
zero-overlap case and a poorly-calibrated/high-overlap case with GENUINE multi-row customer clusters
(2–4 rows/customer, correlated within-cluster noise), using the real, unmodified
`split_stats`/`cluster_cells`/`cluster_bootstrap_replicates`/`percentile_ci`. Both cases resolve
exactly as required: the zero-overlap case reads `calibration_ok=True` (predicted 239.3 EUR, CI
`[228.4, 249.7]`, realized 236.4 EUR); the 90%-overlap regime-shift case reads `calibration_ok=False`
(predicted 695.1 EUR, CI `[688.6, 701.9]`, realized 2.3 EUR). This independently confirms, under a
materially different and more realistic cluster structure, that the proposed metric's verdict tracks
calibration quality, not ground-truth overlap.

## Coupling check — `TASK-087`'s design against `TASK-085`'s estimand, not `TASK-086`'s implementation

**Verdict: PASSES, cleanly.**

Direct grep of `docs/analytics/task-087-economic-impact-calibration-metric-design.md` for
`CandidateExposureResult`, `TASK-086`, `contracts.py`, `schemas.py`, and `Pydantic` finds zero
matches. The document's one reference to tier-2 population scoping (`E_dev`, §1's "tier-2 variant")
cites `TASK-085` §7's own formally-defined estimand naming directly, not any `TASK-086`
serialization/field-naming artifact. The design's reasoning throughout (§1–§9) is expressed entirely
in terms of `rule_expr(candidate.conditions)`, `split_stats`, `harm_per_booking`, and the `E`/`E_dev`
population definitions `TASK-085` §7 establishes — never in terms of any `TASK-086`-specific type,
field name, or persistence shape. No coupling defect found.

## Summary

| Mandate | Verdict |
|---|---|
| 1. Identical population/time support | PASSES (code trace + independent null-divergence probe: zero nulls found) |
| 2. No `future_holdout` leakage | Design's own CONDITIONAL verdict confirmed; independently shown to be a real, demonstrated risk (engineered tie-break flips real top-K selection), not merely theoretical — does not block approval given the design's own scope recommendation and binding re-run requirement |
| 3. Defined behavior under candidate-membership/population drift | **FAILS as specified** — Case F1 (zero future_holdout exposure) crashes rather than resolving; concrete, narrow revision required before implementation |
| 4. Calibration kept separate from localization | PASSES, cleanly, by direct trace |
| 5. Independent Case C/D construction | PASSES, with a real gap in the implementer's own evidence (degenerate n=1 clusters) found and independently filled |
| Coupling check (`TASK-085` estimand, not `TASK-086` implementation) | PASSES, cleanly |

**Overall: APPROVED WITH REVISION NEEDED.** The like-with-like property that is this review's central
mandate holds. One concrete, narrow revision is required (mandate 3 — define behavior at the
zero-population boundary, mirroring `G10`'s own established pattern) before
`tests/analytics/test_o1_temporal_calibration.py` (the design document's own proposed name) is
built. The
mandate-2 finding should be carried forward as a confirmed, live caveat — not a reason to withhold
approval, given the design's own already-correct scope recommendation (form-test suite, never a
`decision-gate.md` metric, with a binding re-run requirement on any relevant config change), but real
weight that record should not understate. `NO VALID REPLACEMENT YET` is explicitly **not** invoked —
the core design is sound and the required revision is narrow, disclosed, and does not touch the
design's own statistical approach.
