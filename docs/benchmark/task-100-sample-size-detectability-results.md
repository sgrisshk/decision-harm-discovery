# TASK-100 — Results: executing TASK-099's frozen sample-size/detectability pre-registration

**Owner:** STATISTICS
**Recorded:** 2026-09-21
**Executes:** `docs/benchmark/task-099-sample-size-detectability-preregistration.md` (freeze commit
`898a274`, round-2-revision commit `1c1bff5`, both `CLOSED FOR REVIEW — APPROVED`). Nothing in that
document was changed to produce this result; every deviation forced by execution is disclosed below,
not silently absorbed into the design.

**Script:** `scripts/task100_run_experiment.py` (committed alongside this document). `ruff check` and
`uv run pyright` both clean (0 errors/warnings) on the final version. Not part of the official
discovery/validation pipeline — disclosed, non-production forensic/experiment tooling, matching
`scripts/diagnose_*`/`scripts/review_task*` precedent.

**Dataset:** real Kaggle "Brazilian E-Commerce Public Dataset by Olist"
(`kagglehub.dataset_download("olistbr/brazilian-ecommerce")`, version 2, all nine CSVs matching
§2.1's schema dump exactly).

---

## 0. Execution-order record (the thing a reviewer will scrutinize hardest)

Per §6.0's binding requirement, the §4.2 leakage/proxy audit was run and recorded, for all four
patterns at both scales, **before** any Stage 1 (oracle detectability) result was computed or
inspected, and Stage 2 (actual discovery) ran before Stage 1 only to supply Stage 1's own
multiplicity-family-size scalar (§6.1 step 6), never the other direction. This is not asserted from
memory — it is enforced by the script's own phase order (Phase 4 → Phase 5 → Phase 6 → Phase 7, each
a separate function called in that fixed sequence from `main()`, nothing in Phase 6/7 reachable before
Phase 4 returns) and independently checkable from the unbuffered, append-only
`artifacts/task-100/execution_order_log.jsonl` this run produced. Real timestamps from that log,
this run:

| Phase | Event | Unix ts |
|---|---|---|
| Phase 4 (§4.2 leakage audit, all 4 patterns × 2 scales) | start | 1789994741.55 |
| Phase 4 | **done** (8/8 audits recorded, 0 flagged) | **1789994790.48** |
| Phase 5 (Stage 2, `discover_candidates`) | start | 1789994959.61 |
| Phase 5 | done | 1789994961.60 |
| Phase 6 (Stage 1, oracle detectability) | start | **1789994961.61** |
| Phase 6 | done | 1789994961.64 |
| Phase 7 (Stage 3, `run_validation`) | start | 1789995162.31 |
| Phase 7 | done | 1789995870.67 |

The leakage audit's own completion (`1789994790.48`) precedes Stage 1's first result
(`1789994961.61`) by ~171 seconds and precedes it structurally, not just chronologically: Phase 6's
code is not called until Phase 5 returns, and Phase 5 does not read or depend on any Phase 4 result
beyond "which features survived" (already fixed before Phase 4 ran — §4.2 flagged nothing, see §1
below). This session never manually reordered phases, never peeked at Stage 1/Stage 2 output before
Phase 4 returned in any of the runs that produced this document's numbers, and the same ordering held
across every incremental run of the script during development (Phase 5/6/7 code did not exist yet
during the run that first validated Phase 4's leakage-audit logic).

---

## 1. §4.2 leakage/proxy audit — full record, before any Stage 1 result

Run on the development split of each scale, restricted to each pattern's own outcome-eligibility
cohort. Three checks per §4.2: point-biserial correlation (numeric feature) or Cramér's V
(categorical/derived-boolean feature) against the outcome (flag at ≥0.95), and exposed/unexposed
group-purity (flag at ≥99% or ≤1%).

| Pattern | Scale | Check statistic | Exposed rate | Unexposed/comparison rate | Verdict |
|---|---|---|---|---|---|
| OL01 | full | Cramér's V = 0.0533 | 7.39% (n=32,005) | 4.61% (n=16,105) | **PASS** |
| OL01 | matched | Cramér's V = 0.0503 | 7.21% (n=3,219) | 4.62% (n=1,645) | **PASS** |
| OL02 | full | point-biserial r = 0.0099 | 42.74% (n=14,877) | 42.02% (n=34,097) | **PASS** |
| OL02 | matched | point-biserial r = −0.0005 | 42.85% (n=1,482) | 41.66% (n=3,471) | **PASS** |
| OL03 | full | Cramér's V = 0.0080 | 42.82% (n=11,858) | 42.06% (n=37,116) | **PASS** |
| OL03 | matched | Cramér's V = 0.0151 | 42.93% (n=1,153) | 41.74% (n=3,800) | **PASS** |
| OL04 | full | Cramér's V = 0.0542 | 6.32% (n=42,440) | 7.47% (n=4,791) | **PASS** |
| OL04 | matched | Cramér's V = 0.1277 | 6.11% (n=4,285) | 8.18% (n=501) | **PASS** |

**All 8 audits PASS. Zero features excluded.** No check statistic is remotely close to its 0.95/99%
flag threshold — the largest Cramér's V observed (OL04, matched, 0.128) is still roughly 7× below the
flag line. This is a clean, unambiguous result, not a borderline call requiring judgment: none of
today's earlier leakage-mistake shape (a feature arithmetically/definitionally entangled with the
outcome via shared source rows) is present in any of the four pre-registered features, at either
scale. Full statistics: `artifacts/task-100/phase4_leakage.json`.

§4.1's construction-provenance argument (no candidate feature shares a source table with either
outcome) was already verified by inspection in the pre-registration itself; §4.2's empirical audit
above is the mechanical confirmation, now actually run against real rows for the first time.

---

## 2. Real `TASK-008` classification (§3) — confirms the pre-registration's own predictions exactly

`schema_profiler.profile_columns` → `feature_timing.classify_columns`, called directly on a CSV
re-export of the full joined frame `F` (98,665 rows after the §2.2 join; `read_csv(...,
infer_schema_length=0)` fidelity requirement honored). Full output:
`artifacts/task-100/phase3_classify.json`.

| Column | Real classifier output | Matches pre-registration's prediction? |
|---|---|---|
| `seller_customer_cross_state` | `UNKNOWN` | **Yes** — §5.2's own trace predicted exactly this |
| `seller_state`, `customer_state` | `DECISION_TIME` | Yes |
| `max_installments` | `DECISION_TIME` | Yes |
| `modal_payment_type` | `DECISION_TIME` | Yes |
| `product_category_name` | `DECISION_TIME` | Yes |

Per §5.2's own explicit, disclosed exception, `seller_customer_cross_state` is treated as
`DECISION_TIME` for OL01 by this document's own prior declaration, not by the classifier's organic
output (which is `UNKNOWN`, exactly as predicted). Nothing about this required a judgment call this
session made — it was fully specified in advance.

**Two classifier quirks surfaced by running it on genuinely new (non-travel) column names, disclosed
as findings, not silently worked around:**
- `order_status` (a fulfillment-lifecycle field — "delivered"/"shipped"/"canceled"/etc., realized
  well after the decision) classifies `DECISION_TIME` via the generic "low-cardinality categorical
  attribute" rule. It is not, semantically, decision-time information — this is a real, disclosed gap
  in the classifier's coverage (its rules have no lifecycle-status-specific signal), not a leakage
  defect in the sense §4 checks for (it was included in Stage 2's search feature pool as the
  classifier's real, unmodified output required; not hand-corrected, since this task's hard rule
  forbids overriding classifier output).
- `order_approved_at` (a payment-approval **timestamp**) classifies `DECISION_TIME` via the
  `_DECISION_TIME_FLAG_HINTS` name-token rule — its `approved` token collides with the flag-hint
  vocabulary (`{manual, exception, override, approved}`), which was written with a boolean
  "manually-approved" flag in mind, not a timestamp column. Also left uncorrected, for the same
  reason.

Neither quirk affected any of the four pre-registered patterns' own features (none of which are
`order_status`/`order_approved_at`); both are disclosed because they were included in Stage 2's full
search pool (§6.2) and could in principle have produced an unrelated Top-K candidate — checked in §5
below and found not to matter to any of `OL01`–`OL04`'s own results.

---

## 3. Stage 1 — Oracle detectability (real `G03`/`G05` formulas, rule handed directly to the gates)

`minimum_detectable_effect` and `benjamini_hochberg_adjusted`, called unmodified;
`ValidationThresholds` (contract v1.3.0) read directly, not restated. Full statistics:
`artifacts/task-100/phase6_stage1.json`.

| Pattern | Scale | n_exp / n_comp | Raw effect (signed) | MDE₈₀ | Unclustered p | BH-adj p (family=N) | Verdict |
|---|---|---|---|---|---|---|---|
| OL01 | full | 32,005 / 16,105 | **+2.776pp** | 0.665pp | ~0 | ~0.0 (N=271) | **DETECTABLE** |
| OL01 | matched | 3,219 / 1,645 | +2.587pp | 2.068pp | 0.000176 | 0.0398 (N=226) | **DETECTABLE** |
| OL02 | full | 14,877 / 34,097 | +0.720pp | 1.360pp | 0.1385 | 1.0 (N=493) | NOT_DETECTABLE |
| OL02 | matched | 1,482 / 3,471 | +1.188pp | 4.291pp | 0.4386 | 1.0 (N=404) | NOT_DETECTABLE |
| OL03 | full | 11,858 / 37,116 | +0.766pp | 1.460pp | 0.1420 | 1.0 (N=493) | NOT_DETECTABLE |
| OL03 | matched | 1,153 / 3,800 | +1.195pp | 4.649pp | 0.4725 | 1.0 (N=404) | NOT_DETECTABLE |
| OL04 | full | 42,440 / 4,791 | **−1.155pp (wrong sign)** | 1.048pp | 0.00369 | 0.9990 (N=271) | NOT_DETECTABLE |
| OL04 | matched | 4,285 / 501 | **−2.069pp (wrong sign)** | 3.221pp | 0.1055 | 1.0 (N=226) | NOT_DETECTABLE |

**Every pattern's oracle verdict is already fixed at the *matched* (4,999-row) scale and does not
change at the full (49,391-row, ~10×) scale:** OL01 is `DETECTABLE` at both; OL02/OL03/OL04 are
`NOT_DETECTABLE` at both. **No pattern in this pre-registered set actually straddles the
matched→full detectability boundary.** This is itself a material, disclosed finding, not a null
result to skip past: the founder's question — does more data move *additional* patterns across the
detectability line — cannot be answered "yes" or "no" from `OL01`–`OL04` in the way §9's branch 1/2
distinction was designed to test, because none of the four ever crosses that line between these two
specific scales. OL01 was already comfortably detectable at 4,999 rows (its effect is simply large
relative to its own variance); OL02/OL03/OL04's raw effects are too small (0.7–1.2pp on a ~42% base
rate, or wrong-signed) for even a 10× increase to move the multiplicity-adjusted p-value out of
saturation (`bh_adjusted_p` sits at 1.0 or 0.999 in five of six `NOT_DETECTABLE` cells).

**OL04 is a genuine sign-flip at both scales**, per §5.3's own pre-stated falsification criterion:
the hypothesized direction ("orders outside the highest-volume category show a *higher* late rate")
is contradicted by the real data — the highest-volume category (`cama_mesa_banho`) actually has a
*higher* late rate (7.47% full-scale) than the rest of the catalog pooled (6.32%). Recorded here as
real, disclosed evidence against the hypothesis, not softened or dropped.

---

## 4. Stage 2 — Actual discovery (`discover_candidates`, real unmodified engine, real classifier's
feature set)

`DiscoveryConfig()` at every current shipped default (`seed=1729`, `min_support=0.01`,
`max_support=0.40`, `beam_width=80`, `top_k=15`, etc. — no knob touched). `feature_columns` is the
real classifier's `DECISION_TIME` output, plus the one §5.2-declared exception
(`seller_customer_cross_state`), minus two disclosed exclusions (§6 below). Matching reuses
`scripts/evaluate_benchmark.py`'s own `MATCH_RECALL_THRESHOLD=0.5` verbatim. Full output:
`artifacts/task-100/phase5_stage2.json`, `artifacts/task-100/phase5b_matching.json`.

| Pattern | Scale | `discover_candidates` finds a ≥50%-recall match? | Matched candidate (if any) | Recall |
|---|---|---|---|---|
| OL01 | full | **No** | — | — |
| OL01 | matched | **No** | — | — |
| OL02 | full | **Yes** | `CAND-011`: `max_installments≥5 AND total_price≥65.8` | 62.5% |
| OL02 | matched | No | — | — |
| OL03 | full | **Yes** | `CAND-010`: `modal_payment_type=boleto AND total_price≥39.0` | 66.2% |
| OL03 | matched | **Yes** | `CAND-009`: `modal_payment_type=boleto AND total_price≥39.0` | 66.0% |
| OL04 | full | No | — | — |
| OL04 | matched | No | — | — |

**A nuance stated squarely, not glossed over: every "match" above is a narrower, more specific,
multi-condition rule than the literal pre-registered single-condition rule** — never the exact
pre-registered rule itself. The recall-based matching criterion (identical to how this project scores
every other domain's discovered candidates against ground truth) only requires majority row-overlap,
not rule identity. OL02's and OL03's matched candidates both additionally condition on
`total_price`, narrowing and reshaping the exposed population rather than reproducing
`max_installments≥P75` or `modal_payment_type≠mode` as stated. This distinction matters for
interpretation (§7 below): "actual recall found something in this neighborhood" is not the same claim
as "actual recall found the pre-registered pattern."

**OL01 — a mechanistically identified, named search/discovery gap, not a vague ranking failure.**
`seller_customer_cross_state==1`'s own population support is **66.5% (full) / 66.2% (matched)** of
the eligible development population — both comfortably above `DiscoveryConfig.max_support=0.40`.
`discover_candidates`'s own `_eligible()` gate requires `min_support <= support <= max_support`
before a rule may ever be scored as a standalone candidate, so the literal singleton rule is
**structurally ineligible for selection at either scale, independent of its ranking or true effect
size.** The atom does appear inside several interaction candidates (e.g.
`max_installments≥5 AND seller_customer_cross_state≥1`, `CAND-001`/`CAND-002` at full scale) — every
such interaction narrows exposure well below the pattern's own full 32,005-row exposed set (the
largest, `CAND-001`, covers only 7,906 of it — 24.7% recall, short of the 50% bar). This is §9's
second branch, named specifically as the task's own instruction requires: the binding mechanism is
`DiscoveryConfig.max_support`'s eligibility ceiling, not a scoring/beam-width/diversity shortfall,
and not something more data changes (support is a population *proportion*, unaffected by scale).

**OL04's non-discovery is not a contradiction — it is the expected, consistent result of a falsified,
wrong-signed hypothesis:** nothing should match a hypothesis the real data contradicts, and nothing
did, at either scale.

---

## 5. Stage 3 — Validated/promoted discovery (`run_validation`, real gates, real cluster bootstrap)

**Disclosed construction deviation, flagged prominently — read this before the results table.** §6.3
names `validation.apply.run_validation(...)` directly. That function requires an on-disk "analytical
dataset" (`manifest.json` + four partition CSVs, read via `validation_input_from_manifest`) — the
same file layout every `TASK-061` domain's `build_analytical_dataset` produces. That builder itself
could not be used unmodified for Olist: it (a) refuses any input frame containing even one
`UNKNOWN`-classified column anywhere (`F` has many — `product_weight_g`, `review_score`,
`order_purchase_timestamp`, …) and (b) recomputes its own split internally from a single calendar-date
config, which cannot express §2.3's percentile-derived boundaries without re-classifying
`order_purchase_timestamp` as `DECISION_TIME` — something the real classifier does not do (confirmed
`UNKNOWN` in §2 above) and this task's hard rule forbids overriding. Rather than silently declaring
Stage 3 unworkable, this script constructs the on-disk manifest layout by hand
(`build_manifest_and_partitions`), restricted to only the columns Stage 2 actually searched over
(features/outcome/`split_label`/identifiers) — but **every substantive judgment (which classification
each column has, where the split boundaries fall) is read verbatim from Phase 2/3's already-computed,
real `assign_temporal_splits`/`classify_columns` output, never re-decided here.** Nothing in
`validation.apply`/`validation.contract`/`validation.input_contract`/`validation.grading` is modified,
patched, or monkeypatched — the real `run_validation` runs completely unmodified once this scaffolding
exists. This is disclosed as a deviation from a fully literal reading of §6.3's text (which does not
anticipate Olist having no `TASK-061`-style analytical dataset already built for it), not hidden, and
is exactly the class of thing this task's own instructions ask to be flagged for reviewer scrutiny
rather than silently worked around.

All four `run_validation` calls (one per outcome × scale) completed successfully — 15/13/12/13
candidates graded respectively, `status: OK`, no exceptions. Full output:
`artifacts/task-100/phase7_stage3.json`.

**Headline result: zero candidates, across all four runs (53 candidate-gradings total), were promoted
above `descriptive_observation`.** No candidate anywhere reached `predictive_association` or higher,
at either scale, for either outcome — so there is no wrong-direction promotion above materiality to
report (§6.3's safety question), simply because nothing was promoted at all.

| Pattern's matched candidate | Scale | Evidence level | Binding failed gates (of those `predictive_association` requires: G03/G04/G05/G10/G12) |
|---|---|---|---|
| OL02 `CAND-011` | full | `descriptive_observation` | G03 (sample adequacy), G04 (uncertainty), G05 (multiplicity) |
| OL03 `CAND-010` | full | `descriptive_observation` | G03, G05, G10 (temporal stability) |
| OL03 `CAND-009` | matched | `descriptive_observation` | G03, G04, G05, G10 |

These are the same underlying constraint Stage 1 already identified for the *exact* pre-registered
rules (small effect relative to `MDE₈₀`, multiplicity correction over a large evaluated-hypothesis
family) — now confirmed to bind the *narrower, more specific* candidates Stage 2 actually surfaced
too, not just the literal pre-registered rule. **Nothing here contradicts Stage 1; it reinforces it.**

G13 (`IDENTIFICATION_DESIGN`) and G14 (`RANDOMIZATION_INTEGRITY`) failed for every single candidate
across all four runs (0/53) — expected and immaterial to the results above: Olist is purely
observational data with no randomization design declared, so `IdentificationDesign.OBSERVATIONAL`'s
own `DESIGN_CEILING` is `adjusted_observational_association`, and neither G13 nor G14 is actually
required for `predictive_association` (`LEVEL_REQUIREMENTS[PREDICTIVE]` = `{LINEAGE, TARGET_LEAKAGE,
SURVIVORSHIP, SAMPLE, UNCERTAINTY, MULTIPLICITY, TEMPORAL_STABILITY, ROBUSTNESS}` — G13/G14 are not
in that set). Confirmed by checking `contract.py`'s own `_LEVEL_GATES`/`LEVEL_REQUIREMENTS` directly,
not assumed. G12 (robustness) passed for every matched candidate reported above — the thing that
failed was always sample adequacy/multiplicity/uncertainty/temporal-stability, matching Stage 1's own
oracle diagnosis.

---

## 6. Disclosed deviations from a fully literal reading of the frozen document (summary)

Stated once here for a reviewer's convenience; each is also disclosed in place above/in the script's
own comments, and none changes any hypothesis, threshold, rule, or gate:

1. **`split_label` excluded from Stage 2's feature pool.** It is this script's own pipeline-internal
   column (added after the real §2.2 join), and it happens to classify `DECISION_TIME` (a
   low-cardinality string) purely as an artifact of being fed through the classifier at all — not a
   real Olist attribute. Excluded as pipeline plumbing.
2. **`order_delivered_customer_date`/`order_estimated_delivery_date` excluded from Stage 2's feature
   pool for the `OUTCOME_LATE` run only.** Both are `OUTCOME_LATE`'s own literal defining columns
   and both classify `DECISION_TIME` under the real classifier's disclosed rules; leaving them in
   would let Stage 2 condition directly on the outcome's own raw inputs — the same entanglement class
   §4.1 requires excluding for the four named patterns, applied here to Stage 2's full search pool so
   as not to recreate today's earlier leakage mistake inside this task's own execution.
3. **`seller_customer_cross_state` included in Stage 2's actual search feature set**, not only in
   Stage 1's hand-specified oracle rule — read as the more faithful interpretation of §5.2's own text
   ("its membership in OL01's feature set is authorized by this document's explicit declaration"); the
   alternative reading (declared only for Stage 1) would make OL01's own actual-recall question
   structurally vacuous (Stage 2 could never find it by construction), which would contradict the
   reason OL01 was pre-registered as a real search-quality test case.
4. **Stage 3's on-disk analytical-dataset scaffolding built by hand** (§5 above) rather than via
   `build_analytical_dataset`, because that function's real preconditions (zero `UNKNOWN` columns
   anywhere in the source frame; a single calendar-date-only split config) do not fit Olist as
   pre-registered. Every substantive value in the hand-built manifest is read verbatim from Phase 2/3's
   already-computed real function output; no classification or split boundary was decided by this
   step.

None of these four deviations were chosen with knowledge of how any pattern's Stage 1/2/3 result would
come out — (1)/(2)/(4) are structural/mechanical necessities forced by Olist lacking a pre-existing
`TASK-061`-style dataset build, and (3) was decided while writing the code before Phase 5 was ever run
(confirmed by the code's own structure: `DECLARED_DECISION_TIME_OVERRIDES` is a module-level constant,
not something computed from or conditioned on any result).

---

## 7. §9 interpretation, applied per pattern, verbatim branches, no fifth branch

> - Oracle detectability rises **and** actual recall rises at the larger scale → strong evidence...
> - Oracle detectability rises but actual recall does **not** → a genuine search/discovery gap...
> - Oracle detectability does **not** materially rise despite much more data → raw row count is not
>   the operative constraint...
> - Precision or safety deteriorates while recall rises → report this explicitly as a trade-off...

**OL01 (cross-state shipping → late delivery): Branch 2, a genuine, specifically-named
search/discovery gap — but not a scale story.** Oracle detectability does not "rise" between scales
for OL01 because it was already `DETECTABLE` at the matched (4,999-row) scale — this pattern's effect
is simply large enough relative to its own variance to clear the bar at either tested scale. Actual
recall is `False` at both scales, for the same reason at both: `discover_candidates`'s own
`max_support=0.40` eligibility ceiling structurally excludes this rule's 66%+-prevalence singleton
from ever being selected, at either row count. This is real, disclosed, engineering-actionable
evidence of a search-mechanism gap (§9's own second branch), independent of sample size — worth
engineering, per that branch's own text, but the fix is a support-ceiling/near-majority-rule handling
question, not a data-volume one.

**OL02 (installment count → low review): Branch 3 for the pre-registered rule itself.** Oracle
detectability does not materially rise with 10× more development data (`NOT_DETECTABLE` at both
scales; `bh_adjusted_p` stays at 1.0 both times) — raw row count is not the operative constraint here;
the raw effect (0.7–1.2 percentage points on a ~42% base rate) is simply too small relative to the
BH-adjusted multiplicity bar this search family requires. **Disclosed nuance:** Stage 2 does surface a
narrower, related candidate at full scale only (`max_installments≥5 AND total_price≥65.8`), but Stage
3 shows that candidate also fails to clear `predictive_association` (G03/G04/G05), so this nuance does
not change the pattern's overall verdict — it is not evidence that more data helped recover this
specific hypothesis, only that a *different*, narrower relationship in its neighborhood becomes
visible to search at 10× the data, and that relationship is *also* not validated.

**OL03 (non-default payment type → low review): Branch 3, with the same shape as OL02 but even more
scale-invariant.** Oracle: `NOT_DETECTABLE` at both scales, no material change. Stage 2 finds the same
narrower candidate (`modal_payment_type=boleto AND total_price≥39.0`) at **both** scales already —
not a function of scale at all. Stage 3 fails that candidate at both scales for the same reasons Stage
1 already predicts (G03/G05, plus G10 at both). Every stage of this pattern's story is unchanged by a
10× increase in development rows.

**OL04 (non-top product category → late delivery): the hypothesis is falsified, at both scales —
reported plainly, not forced into a branch that assumes the hypothesized direction holds.** The
observed effect has the *opposite* sign from what was pre-registered, at both scales, exactly matching
§5.3's own pre-stated falsification criterion. This is closest in spirit to branch 3 (oracle never
rises to significance; raw row count changes nothing) but is a stronger, more specific finding than
"not yet detectable" — it is actively contradicted by the real data, not merely underpowered. Actual
discovery correctly finds nothing matching the (wrong) hypothesized direction at either scale, which
is the consistent, expected result of a falsified hypothesis, not evidence of anything further.

**No pattern lands in branch 1 or branch 4.** Branch 1 requires oracle detectability to *rise* between
scales with actual recall following — no pattern here has an oracle verdict that differs between the
two tested scales at all (OL01 is already `DETECTABLE` at 4,999 rows; the other three remain
`NOT_DETECTABLE` even at ~49,000). Branch 4 requires recall to rise while precision/safety
deteriorates — nothing here was promoted at any scale (0 of 53 gradings reached
`predictive_association`), so there is no deterioration to report; precision stayed perfect (in the
narrow, disclosed sense §6.3 itself already flags Olist's own labeled-ground-truth-free design can
support) at both scales, for every pattern.

---

## 8. What this experiment actually established, stated plainly

Holding validation/safety standards fixed and increasing Olist's development-side sample size 10×
(4,999 → 49,391 rows) **did not move any of the four independently pre-registered patterns across the
statistical-detectability line, and did not produce a single validated (`predictive_association`+)
finding at either scale.** One pattern (OL01) was already detectable at the smaller scale but is
blocked from actual discovery by a specific, named search-engine mechanism (`max_support`'s
eligibility ceiling) unrelated to sample size. Two patterns (OL02, OL03) have real but small effects
whose statistical significance does not improve with an order of magnitude more data, because the
effect sizes themselves — not row count — are the binding constraint, exactly as §9's third branch
anticipates. One pattern (OL04) is directly falsified by the real data. This is one honest data point,
on one real dataset, with the residual selection-risk caveat §7.1 of the pre-registration itself
already discloses (this document's own hypothesis *selection*, not just its thresholds, cannot be
proven free of generic prior familiarity with a famous public dataset) — it does not, on its own,
settle the travel-benchmark recall-ceiling question `ADR-092` raised, and should not be read as doing
so; it is one additional, real, disclosed data point toward that broader question, exactly the scope
`TASK-099`/`TASK-100` were opened to produce.

---

## 9. Provenance

- Pre-registration document: `docs/benchmark/task-099-sample-size-detectability-preregistration.md`
  (freeze `898a274`, revision `1c1bff5`), unmodified by this task.
- Execution script: `scripts/task100_run_experiment.py`, committed alongside this document.
- Raw artifacts (gitignored, `artifacts/` — not committed, reproducible by re-running the script
  against the same kagglehub cache): `phase1_join.json`, `phase2_split.json`, `phase3_classify.json`,
  `phase3_expectations.json`, `phase4_leakage.json`, `phase4_outcome_p25.json`, `phase5_stage2.json`,
  `phase5b_matching.json`, `phase6_stage1.json`, `phase7_stage3.json`, `phaseN_summary.json`,
  `execution_order_log.jsonl` (the unbuffered per-event log §0 above is drawn from).
- `kagglehub` was not a project dependency before this task; installed ad hoc via
  `uv run --with kagglehub --with polars python3 ...` for this script's own run, not added to
  `pyproject.toml` (this task does not touch project dependency manifests).
