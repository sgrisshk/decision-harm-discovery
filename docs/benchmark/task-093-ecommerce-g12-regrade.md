# TASK-093 — ecommerce's frozen `TASK-068`/`TASK-019` candidates, re-graded under contract v1.3.0's
corrected `G12` (`ADR-092` follow-on F1)

**Status: POST-HOC DIAGNOSTIC throughout, matching `TASK-070`'s own precedent exactly.** Every
number here is produced by running the real, unmodified production discovery and validation paths
(`policy_analytics.discovery.engine.discover_candidates`,
`policy_analytics.validation.apply.run_validation`) on 2026-09-20. Nothing here is a new official
`TASK-015`/`TASK-019`/`TASK-028` run, changes any frozen artifact, opens hidden ground truth, or
grades any candidate for the record. `ecommerce`'s ground truth was already opened by the original
`TASK-068` custody chain (`task-068-ecommerce-preregistration.md` §10.6/§10.8: "spent" as of
2026-08-27); nothing new is opened by this task. Reproduction script:
`scripts/diagnose_task093_ecommerce_g12_regrade.py`. Raw computed output:
`docs/benchmark/task-093-ecommerce-g12-regrade-raw.json`.

## 0. Why this is a reproduction, not a re-read of the frozen artifacts

The official frozen candidate artifacts
(`artifacts/blind/task-068-ecommerce-{baseline,cap}-20260827-001.candidates.json` and siblings) are
not present in this worktree: `artifacts/` is gitignored and untracked, and a fresh
`git worktree add` checkout does not receive them even though they exist in some other checkouts of
this repository (`ls artifacts/blind/ 2>/dev/null` returns nothing here). Per this task's own
instructions, the candidate set was reproduced instead, by calling the real, unmodified
`discover_candidates()` against the real `ecommerce` analytical dataset
(`synthetic_data_domains/ecommerce/analytical/ecommerce-analytical-v1.0.0`, present and
git-tracked in this worktree, `dataset_identity_sha256`
`fb8d049d5f81bb0d792ead8d6310e301b998f4eed7acf63a3274456b9f56c658` — verified to match the
preregistration's own recorded identity exactly) with the exact documented `TASK-068`
configuration: `DiscoveryConfig(seed=1729, max_feature_identity_fraction=1.0)` for the baseline arm,
`max_feature_identity_fraction=0.34` for the cap arm, every other field left at `DiscoveryConfig`'s
own defaults (confirmed against `docs/benchmark/task-068-ecommerce-preregistration.md` §4b's fixed
list, byte-for-byte identical to the dataclass defaults). Feature columns are every `DECISION_TIME`
column in the registered `ecommerce` `DomainSpec` except the domain's own decision-timestamp column
(`order_date`) — the same rule `scripts/run_discovery.py` applies for travel's `booking_date`/
`travel_date`, derived generically here from `policy_analytics.domain_benchmarks.ecommerce.SPEC`
rather than hardcoded.

### 0.1 Fidelity check (`TASK-075`/`078`/`079` precedent), before trusting the reproduction for anything

| Figure | Official record (`task-068-ecommerce-preregistration.md` §10) | This reproduction | Match |
|---|---|---|---|
| Dataset identity | `fb8d049d5f...` | `fb8d049d5f...` | exact |
| Evaluated hypotheses, baseline | 17,523 | 17,523 | exact |
| Evaluated hypotheses, cap | 17,523 | 17,523 | exact |
| Candidate count, baseline | 15 (`PERSISTED`) | 15 | exact |
| Candidate count, cap | 15 (`PERSISTED`) | 15 | exact |
| Distinct feature identities, baseline (§10.5) | 7 | 7 | exact |
| Distinct feature identities, cap (§10.5) | 9 | 9 | exact |
| Per-feature slot tally, baseline (§10.5) | `discount_pct=11, product_price_usd=8, quantity=4, items_in_cart=2, coupon_used=2, acquisition_channel=2, product_tier=1` | identical | exact |
| Per-feature slot tally, cap (§10.5) | `discount_pct=5, product_price_usd=5, quantity=5, product_category=5, items_in_cart=4, coupon_used=1, acquisition_channel=1, product_tier=3, days_since_last_visit=1` | identical | exact |
| `G12` pass/fail under v1.2.0 semantics, baseline (§10.4) | pass 7 / fail 8 | pass 7 / fail 8 | exact |
| `G12` pass/fail under v1.2.0 semantics, cap (§10.4) | pass 6 / fail 9 | pass 6 / fail 9 | exact |
| `G06` pass/fail, baseline/cap (§10.4) | 14/1, 13/2 | 14/1, 13/2 | exact |
| `G09` outcome, both arms (§10.4) | `not_evaluated` 15/15 | `not_evaluated` 15/15 | exact |
| `G13`/`G14`, both arms (§10.4) | `fail` 15/15 | `fail` 15/15 | exact |
| Evidence level, both arms, v1.2.0 (§10.4) | 15 `descriptive_observation` | 15 `descriptive_observation` | exact |
| Verdict, both arms, v1.2.0 (§10.4) | 15 `DOWNGRADE` | 15 `DOWNGRADE` | exact |

**Every checkable figure matches exactly, including the `G12` pass/fail split re-derived
independently under `RobustnessSemantics.FIXED_QUANTILE_V1` (the "before" figure is not merely
quoted from the preregistration doc — this reproduction re-derives it from scratch and it agrees).**
No individual candidate rule text can be verified against the frozen artifacts (those bytes are
unavailable in this worktree), but the search is deterministic (`seed=1729`, no randomness beyond
the fixed RNG, real production code, real production data) and every aggregate and structural figure
this document can check against real, git-tracked numbers agrees exactly, including a 15-row
per-feature slot table that would not plausibly coincide by chance. Fidelity is treated as
confirmed.

## 1. What was re-graded, and how

Both reproduced 15-candidate sets, graded twice each via
`policy_analytics.validation.apply.run_validation` called directly (`scripts/validate_candidates.py`
does not expose a `--robustness-semantics` CLI flag) — once under
`RobustnessSemantics.FIXED_QUANTILE_V1` (contract v1.2.0's superseded fixed-quantile-step semantics,
the defect `ADR-064`/`TASK-070` proved and fixed for travel) and once under
`RobustnessSemantics.ONE_BIN_RELATIVE_V2` (contract v1.3.0's corrected semantics, the current
default `ROBUSTNESS_SEMANTICS_VERSION`). No gate, threshold, or fix is changed; only the semantics
version passed to the same, unmodified `run_validation` call differs between the two grades of each
arm.

## 2. `G12` before vs. after, both arms

### 2.1 Aggregate

| Arm | `G12` pass, v1.2.0 (before) | `G12` fail, v1.2.0 (before) | `G12` pass, v1.3.0 (after) | `G12` fail, v1.3.0 (after) |
|---|---:|---:|---:|---:|
| baseline (`max_feature_identity_fraction=1.0`) | 7 | 8 | **15** | **0** |
| cap (`max_feature_identity_fraction=0.34`) | 6 | 9 | **15** | **0** |

**`G12` clears completely for every candidate in both arms under the corrected contract.** This
mirrors travel's own experience (`task-070-g12-fix-remeasurement.md` §2: "8/15 final verdicts
changed" there) in the sense that the *gate* moves substantially — but, unlike travel, it moves
*zero* final verdicts for ecommerce, for reasons in §3 below.

**Non-regression, verified directly rather than assumed:** comparing every one of the other 16
gates' outcome for every candidate, before vs. after, the only gate whose outcome moves in either
arm is `G12`. `G06`, `G09`, `G13`, `G14`, and every other gate are byte-identical between the two
semantics — exactly the property `TASK-070` §2 established for travel/b2b_sales/ecommerce
collectively, now independently re-confirmed here for ecommerce alone from a from-scratch
reproduction.

### 2.2 Per-candidate, baseline arm (`max_feature_identity_fraction=1.0`)

| Candidate | Rule | `G12` before (v1.2.0) | `G12` after (v1.3.0) | Before reason (truncated) | After reason (truncated) |
|---|---|---|---|---|---|
| CAND-001 | `discount_pct ge 0.2 AND product_price_usd lt 102.22` | pass | pass | sign 100%, dev 11% | sign 100%, dev 15% |
| CAND-002 | `product_price_usd lt 49.89 AND quantity lt 3.0` | **fail** | **pass** | sign 60% (floor 90%) | sign 100%, dev 3% |
| CAND-003 | `discount_pct ge 0.2 AND quantity lt 3.0` | **fail** | **pass** | sign 60% (floor 90%) | sign 100%, dev 14% |
| CAND-004 | `discount_pct ge 0.05 AND product_price_usd lt 49.89` | pass | pass | sign 100%, dev 7% | sign 100%, dev 7% |
| CAND-005 | `discount_pct ge 0.2 AND product_price_usd ge 34.64` | **fail** | **pass** | sign 80%, dev 84% (ceiling 50%) | sign 100%, dev 42% |
| CAND-006 | `discount_pct ge 0.2 AND items_in_cart ge 2.0` | **fail** | **pass** | sign 100%, dev 94% (ceiling 50%) | sign 100%, dev 34% |
| CAND-007 | `coupon_used eq True AND discount_pct ge 0.1` | pass | pass | sign 100%, dev 35% | sign 100%, dev 18% |
| CAND-008 | `discount_pct ge 0.2 AND items_in_cart lt 4.0` | **fail** | **pass** | sign 40% (floor 90%) | sign 100%, dev 39% |
| CAND-009 | `discount_pct ge 0.15 AND product_price_usd lt 49.89` | pass | pass | sign 100%, dev 15% | sign 100%, dev 10% |
| CAND-010 | `acquisition_channel eq paid_search AND discount_pct ge 0.1` | **fail** | **pass** | sign 100%, dev 52% (ceiling 50%) | sign 100%, dev 24% |
| CAND-011 | `product_price_usd lt 49.89 AND product_tier eq standard` | pass | pass | sign 100%, dev 3% | sign 100%, dev 3% |
| CAND-012 | `discount_pct ge 0.1 AND product_price_usd lt 49.89` | pass | pass | sign 100%, dev 11% | sign 100%, dev 6% |
| CAND-013 | `coupon_used eq True AND quantity lt 2.0` | **fail** | **pass** | sign 33% (floor 90%) | sign 100%, dev 6% |
| CAND-014 | `discount_pct ge 0.05 AND product_price_usd lt 34.64` | pass | pass | sign 100%, dev 8% | sign 100%, dev 8% |
| CAND-015 | `acquisition_channel eq paid_search AND quantity lt 2.0` | **fail** | **pass** | sign 33% (floor 90%) | sign 100%, dev 15% |

Every one of the 8 baseline candidates that failed `G12` under v1.2.0 failed on the sign-agreement
floor (33–80% against a 90% floor, characteristic of the fixed-quantile step landing on an
unrepresentative perturbation) or the magnitude ceiling (52–94% against 50%); all 8 pass cleanly
under v1.3.0's one-bin-relative step.

### 2.3 Per-candidate, cap arm (`max_feature_identity_fraction=0.34`)

| Candidate | Rule | `G12` before (v1.2.0) | `G12` after (v1.3.0) | Before reason (truncated) | After reason (truncated) |
|---|---|---|---|---|---|
| CAND-001 | `discount_pct ge 0.2 AND product_price_usd lt 102.22` | pass | pass | sign 100%, dev 11% | sign 100%, dev 15% |
| CAND-002 | `product_price_usd lt 49.89 AND quantity lt 3.0` | **fail** | **pass** | sign 60% (floor 90%) | sign 100%, dev 3% |
| CAND-003 | `discount_pct ge 0.2 AND quantity lt 3.0` | **fail** | **pass** | sign 60% (floor 90%) | sign 100%, dev 14% |
| CAND-004 | `discount_pct ge 0.05 AND product_price_usd lt 49.89` | pass | pass | sign 100%, dev 7% | sign 100%, dev 7% |
| CAND-005 | `discount_pct ge 0.2 AND product_price_usd ge 34.64` | **fail** | **pass** | sign 80%, dev 84% (ceiling 50%) | sign 100%, dev 42% |
| CAND-006 | `discount_pct ge 0.2 AND items_in_cart ge 2.0` | **fail** | **pass** | sign 100%, dev 94% (ceiling 50%) | sign 100%, dev 34% |
| CAND-007 | `product_price_usd lt 49.89 AND product_tier eq standard` | pass | pass | sign 100%, dev 3% | sign 100%, dev 3% |
| CAND-008 | `coupon_used eq True AND quantity lt 2.0` | **fail** | **pass** | sign 33% (floor 90%) | sign 100%, dev 6% |
| CAND-009 | `acquisition_channel eq paid_search AND quantity lt 2.0` | **fail** | **pass** | sign 33% (floor 90%) | sign 100%, dev 15% |
| CAND-010 | `items_in_cart ge 4.0 AND quantity lt 3.0` | **fail** | **pass** | sign 60%, dev 67% (ceiling 50%) | sign 100%, dev 20% |
| CAND-011 | `product_category eq beauty AND product_tier eq standard` | pass | pass | sign 100%, dev 3% | sign 100%, dev 3% |
| CAND-012 | `product_category eq toys AND product_tier eq standard` | pass | pass | sign 100%, dev 3% | sign 100%, dev 3% |
| CAND-013 | `days_since_last_visit lt 40.0 AND product_category eq beauty` | **fail** | **pass** | sign 67% (floor 90%) | sign 100%, dev 4% |
| CAND-014 | `items_in_cart ge 2.0 AND product_category eq toys` | pass | pass | sign 100%, dev 11% | sign 100%, dev 11% |
| CAND-015 | `items_in_cart lt 3.0 AND product_category eq beauty` | **fail** | **pass** | sign 33% (floor 90%) | sign 100%, dev 7% |

Same pattern: every cap-arm failure under v1.2.0 was a sign-agreement or magnitude-ceiling failure
that the one-bin-relative step resolves cleanly.

### 2.4 The gate is not toothless afterwards

Over all 30 candidate-grades (15 baseline + 15 cap) under v1.3.0: max magnitude deviation **min 3%,
median 10.5%, max 42%**, against the 50% ceiling — every candidate clears with room to spare, but
the worst case (CAND-005/CAND-006 in both arms, ~34–42%) is not close to the ceiling being vacuous.
86 threshold refits were `estimated`, 4 `degenerate_no_contrast` (CAND-013/CAND-015 baseline,
CAND-008/CAND-009 cap — all four already had only 2–3 perturbations available, consistent with
categorical/coarse conditions), 0 `vacuous_identical_rule`, 0 `unrepresentable_step`. No candidate
was capped by a silent `NOT_EVALUATED` masquerading as disagreement — the same accounting property
`TASK-070` §2 verified for travel/b2b_sales.

## 3. Evidence level and `economic_weighted_recall`: unchanged, and why — precisely

**Evidence level does not move for a single candidate in either arm.** All 30 candidate-grades
(15 baseline × 2 semantics, 15 cap × 2 semantics) remain at `descriptive_observation`, verdict
`DOWNGRADE`, identical before and after:

| Arm | Semantics | Evidence level distribution | Verdict distribution |
|---|---|---|---|
| baseline | v1.2.0 (before) | 15 `descriptive_observation` | 15 `DOWNGRADE` |
| baseline | v1.3.0 (after) | 15 `descriptive_observation` | 15 `DOWNGRADE` |
| cap | v1.2.0 (before) | 15 `descriptive_observation` | 15 `DOWNGRADE` |
| cap | v1.3.0 (after) | 15 `descriptive_observation` | 15 `DOWNGRADE` |

**This is not a case of `G12` clearing but some other gate happening to still fail for the same
candidates by coincidence — it is structural, and independent of `G12` entirely.** Checked directly
against `packages/analytics/src/policy_analytics/validation/contract.py`'s own gate-tier
definitions (`_LEVEL_GATES`, `LEVEL_REQUIREMENTS`) and `grading.py`'s `classify_evidence_level`/
`evidence_ceiling`:

- `EvidenceLevel.PREDICTIVE` (`predictive_association`) cumulatively requires `G00`, `G01`, `G08`
  (from `DESCRIPTIVE`) plus `G03`, `G04`, `G05`, `G10`, `G12`. None of these gates other than `G12`
  differ before/after, and all of `G00`, `G01`, `G03`, `G04`, `G05`, `G08`, `G10` already pass 15/15
  in both arms (§2.1's non-regression check, and the fidelity table above). So the 15/15 candidates
  clearing `G12` under v1.3.0 satisfy every gate `PREDICTIVE` requires by name.
- But `G09` (`GateId.SIMPSON`, `G09_SIMPSON_AND_HETEROGENEITY`) is `NOT_EVALUATED` for all 15
  candidates in **both** arms — `ecommerce`'s analytical dataset manifest declares no reviewed
  `heterogeneity_column`/`robustness_group_column` (`analytical_bridge.analytical_dataset_config`
  sets both to `None` for every `TASK-061` domain generically; this is the exact, pre-disclosed
  condition `docs/benchmark/task-068-ecommerce-preregistration.md` §R3 recorded in advance, and
  `ADR-092` Q4's own text names, before this task ran). `GateOutcome.NOT_EVALUATED` is treated
  exactly like `FAIL` (`contract.py`'s own docstring: "an unrun check is not a passed check").
  `G09`'s `GateSpec` has `on_failure=CAP_EVIDENCE, max_level_on_failure=EvidenceLevel.DESCRIPTIVE`
  — **independent of every other gate's outcome, an unsatisfied `G09` caps every candidate's
  evidence ceiling at `DESCRIPTIVE`,** one full tier below `PREDICTIVE`. `evidence_ceiling()`
  computes this ceiling from *every* `GateSpec` with a `CAP_EVIDENCE` failure action, not just the
  ones nominally "required" for the tier being tested, so `G12` clearing cannot lift a candidate
  past a ceiling a different, unrelated gate has already set.

**`G13`/`G14` — which this task's own text and `ADR-092` Q4 both flag as the candidate blocker —
are not, in fact, what is binding here, and it is worth being precise about that rather than
repeating the guess.** `G13` (`IDENTIFICATION_DESIGN`) and `G14` (`RANDOMIZATION_INTEGRITY`) are
required only at `EvidenceLevel.QUASI_CAUSAL` and `EvidenceLevel.EXPERIMENTAL` respectively — two
and three tiers above `PREDICTIVE`, and one and two tiers above `ADJUSTED_OBSERVATIONAL` (the
highest tier `IdentificationDesign.OBSERVATIONAL` can ever reach per `DESIGN_CEILING`, regardless of
any gate outcome). Every candidate here is `IdentificationDesign.OBSERVATIONAL` by construction, so
`G13`/`G14` failing 15/15 is a definitional property of every observational candidate this pipeline
has ever produced (travel's included — nothing ecommerce-specific), not a separate finding about
this domain, and it plays no role in capping these candidates below `predictive_association`. The
gate actually doing that work is `G09`, an entirely different, `G12`-unrelated ceiling that was
already disclosed in `TASK-068`'s own preregistration before any run occurred.

**Consequence for `economic_weighted_recall` and the rest of `TASK-028`'s benchmark metrics: no
re-run was performed, because none is needed.** `scripts/evaluate_benchmark.py`'s
`economic_weighted_recall` only counts a matched pattern if the matching candidate's
`evidence_level` is in `VALIDATED_LEVELS` (`predictive_association` or above). Since no candidate's
evidence level moves in either arm, the set of candidates eligible to contribute to
`economic_weighted_recall` is byte-identical before and after, and so is every other evidence-level-
gated quantity (`policy_readiness`, `PROMOTED_READINESS` trap-promotion checks). The frozen `TASK-028`
figures already on record for both arms
(`docs/benchmark/task-068-ecommerce-preregistration.md` §10.6: **0.0% economic-weighted recall in
both arms**, Top-10 precision 50%/50%, unique scoreable-pattern candidate-match recall 1/4 → 2/4,
trap rejection 5/5 in both, 0 leakage violations, direction accuracy not estimable in both) remain
the accurate figures for what `G12`'s fix does to this domain's benchmark grade: nothing. This is
not an assumption carried over from the preregistration doc — it follows deductively from the gate
mechanics just traced, and is corroborated by this reproduction's own `run_validation` output
showing zero evidence-level movement across all 30 grades.

## 4. Determination — precise, per `ADR-092` Q4's own instruction not to overreach

**`G12` clears substantially for ecommerce under the corrected contract — from 7/15 and 6/15 passing
under the superseded v1.2.0 semantics to 15/15 in both arms under v1.3.0 — confirming ecommerce's
`G12` failures under the frozen official runs were indeed instances of the same proven, since-fixed
`ADR-064` defect, not a genuine robustness problem with these candidates.** That much of `ADR-092`
Q4's open question is answered cleanly: ecommerce's pre-fix `G12` numbers were not informative about
any real property of these candidates' stability.

**But `G12` clearing does not, and structurally cannot, move ecommerce's evidence-level distribution
or its `economic_weighted_recall`, because a second, entirely unrelated gate — `G09`
(`SIMPSON_AND_HETEROGENEITY`, `NOT_EVALUATED` for every candidate in both arms because this domain's
manifest declares no reviewed heterogeneity column) — independently caps every candidate at
`descriptive_observation` regardless of `G12`'s outcome.** This is exactly the outcome this task's
own instructions anticipated as a real possibility ("if `G12` clears but something else ... still
blocks everything, say so plainly") — though the specific blocking gate is `G09`, not `G13`/`G14` as
this task's own draft text and `ADR-092` Q4 guessed; `G13`/`G14` are definitional ceilings for any
observational candidate and were never in a position to bind here. `docs/benchmark/decision-gate.md`'s
overall verdict for both ecommerce arms remains unchanged at whatever it was already recorded as
(FAILED, driven by `economic_weighted_recall < 5%` — `task-068-ecommerce-preregistration.md` §10.7),
unaffected by this task in either direction.

**What this settles about `ADR-092` Q4's actual question — whether ecommerce's 0% economic-weighted
recall was ever informative about the same statistical-power ceiling `P04`/`P08`/`P09` hit on
travel.** The answer is unchanged from `ADR-092`'s own already-careful framing, now with the `G12`
confound formally removed rather than merely suspected: **ecommerce's 0% recall is still not shown
to be the same ceiling as travel's `G03`/`G05` sample-adequacy problem.** `G03`, `G04`, and `G05`
pass 15/15 for ecommerce in both arms, both before and after this re-grade — there was never a
sample-size or multiple-comparisons signature here resembling travel's `P04`/`P08`/`P09`. What now
stands, cleanly, as ecommerce's real and only binding ceiling below `descriptive_observation` is
`G09`'s `NOT_EVALUATED` status — a *manifest/infrastructure* gap (no reviewed heterogeneity column
for this domain), not a statistical-power or sample-size finding, and not the `G12` artifact `ADR-092`
Q4 was checking for either. Neither this task nor `ADR-092` before it authorizes drawing a further
conclusion about whether ecommerce's ceiling generalizes to or differs from travel's — that
comparison would require an evidentiary basis this domain has never reached (nothing here gets past
`descriptive_observation`, so there is no `predictive_association`-or-above ecommerce finding to
compare travel's `P04`/`P08`/`P09` power ceiling against at all). The honest statement is narrower
than either "ecommerce confirms travel's ceiling" or "ecommerce refutes it": **ecommerce's 0% recall
was never actually testing the same mechanism travel's ceiling names, before or after this re-grade,
and this task does not change that.**

## 5. Reproduction

```sh
# Reproduces both candidate sets, verifies fidelity against the preregistration's own recorded
# figures, grades each under both robustness semantics, and writes the raw summary this report is
# drawn from.
uv run python scripts/diagnose_task093_ecommerce_g12_regrade.py
```

Requires only this worktree's already-committed `ecommerce` analytical dataset
(`synthetic_data_domains/ecommerce/analytical/ecommerce-analytical-v1.0.0`); no frozen blind
artifact, no hidden ground truth, and no network access are needed. Intermediate candidate and
validation-report JSON are written under `artifacts/discovery/` and `artifacts/validation/`
(gitignored, regenerable); the raw summary is written to
`docs/benchmark/task-093-ecommerce-g12-regrade-raw.json` (committed, alongside this report).

## 6. What this does not say

It does not modify `G12`, `G09`, any other gate, any threshold, or `ADR-064`'s own fix — every
number here comes from calling existing, unmodified functions with different (reproduced) inputs.
It does not open any new hidden ground truth (ecommerce's was already opened and spent by the
original `TASK-068` run). It does not re-freeze or supersede the official `task-019`/`task-028`
artifacts for `task-068-ecommerce-{baseline,cap}-20260827-001` — those remain the frozen record,
correctly labeled with their own `validation_contract_version` (`docs/analytics/
validation-contract.md` §4c migration: old runs stay reproducible under their own version, not
silently re-graded). It does not draw or assert a conclusion about whether ecommerce's evidence
ceiling "is" or "is not" the same as travel's beyond exactly what `G12`'s re-grade shows: `G12`
was not, and `G09` — a disclosed, unrelated infrastructure gap — is, the operative constraint for
this domain's benchmark grade, at every point this task checked.
