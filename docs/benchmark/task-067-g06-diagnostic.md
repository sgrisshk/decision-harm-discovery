# TASK-067 deep per-candidate G06 diagnostic — `task-065-b2b-comparable-20260822-001`

**Status: POST-HOC DIAGNOSTIC throughout.** Every number in this document is produced by
`scripts/diagnose_g06_task065_b2b.py`, run for real on 2026-08-22 against already-frozen,
already-public artifacts. Nothing here is a new official `TASK-019`/`TASK-028` run, changes any
frozen artifact, threshold, gate, or the recorded `ADR-053` FAILED verdict, or touches
`apply.py`/`contract.py`/any production module. Raw computed output:
`docs/benchmark/task-067-g06-diagnostic-raw.json`.

**Relationship to the existing record:** `TASKS.md` TASK-067 is `DONE` at a coarse, run-level of
detail (`ADR-055` Statistics attribution, `ADR-056` ML_DISCOVERY concurrence:
`CONCUR_GENERAL_FIXABLE`). This document is the deeper, per-candidate diagnostic that record's own
text pointed to but that had not actually been executed. It **does not reopen or flip** the
`ADR-053` FAILED verdict or `TASK-065`'s `DONE` status. It **does** materially refine — and on one
specific mechanism-level claim, contradict — `ADR-055`/`ADR-056`'s characterization of *why* G06
fails. See §7.

## 0. Custody and scope declaration

This diagnostic reads only: the frozen candidate file
(`artifacts/blind/task-065-b2b-comparable-20260822-001.candidates.json`, SHA-256
`ec3b1c17c9826724dfaa6adec1a1db431768bad772b228d33cf906be6ab49bcc`, re-verified by the script
before it runs anything else), the frozen `TASK-019` report
(`artifacts/validation/task-019-task-065-b2b-comparable-20260822-001.json`), the frozen `TASK-028`
report (`artifacts/evaluation/task-028-task-065-b2b-comparable-20260822-001.json` — already
legitimately opened once, after commitment, by the `TASK-065` independent evaluator; this document
reads its already-public `matched_patterns`/`is_trap` fields, it does not open
`hidden_ground_truth.json` itself), the public b2b analytical dataset/manifest, and `apply.py`'s
real, unmodified, read-only-called functions. `synthetic_data_domains/b2b_sales/comparable/
evaluation/hidden_ground_truth.json` was not opened to produce this document, directly or
indirectly. No other domain's hidden ground truth was opened, referenced, or touched. No new blind
or official run was issued. No new domain was selected or prepared.

## 1. Script review and fix

`scripts/diagnose_g06_task065_b2b.py` imports and calls `apply.py`'s real private functions
verbatim (`_adjustment_pool`, `_binned_adjustment_frame`, `_select_adjustment_columns`,
`_stratified_adjustment`) rather than reimplementing G06's logic — verified by reading `apply.py`
lines 302–438 and 513–601 (`_validate_one`'s own G06 block) and confirming the script's call
sequence (`_adjustment_pool` → `_binned_adjustment_frame` → greedy trace mirroring
`_select_adjustment_columns` exactly → `_stratified_adjustment` on the selected set) is
call-for-call identical to production. Re-running the script reproduces the frozen `TASK-019`
report's `confounder_stratum_coverage`, `adjusted_harm_per_booking`, and `adjustment_columns_used`
**exactly** (bit-for-bit, spot-checked across all 15 candidates) — direct evidence the script is
not silently diverging from the gate it is tracing.

**Bug found and fixed (execution, not logic):** on first real run, `_eta_squared` and
`_fwl_additive_coefficient` both called `polars.Series.to_numpy()`, which panicked with
`ModuleNotFoundError: No module named 'numpy'` — this project's actual `.venv` has no numpy
installed, and numpy is not a declared dependency anywhere in `pyproject.toml`. This is consistent
with the codebase's own disclosed discipline: `ADR-042`'s alternatives-considered text says
outright "no `numpy`/`scipy` dependency currently exists to lean on," and a repo-wide
`git grep -l -E "to_numpy|import numpy"` before the fix returned only this one file. **Fix:**
rewrote both functions to do the identical arithmetic (grand-mean/between-group sum-of-squares for
η²; iterative alternating group-demeaning for the Frisch–Waugh–Lovell partialling-out) over plain
Python lists/dicts instead of numpy arrays — same numerics, same result, no new dependency. No
other logic changed. Full fix note lives in the script's own module docstring
(`scripts/diagnose_g06_task065_b2b.py`, "Fix history"). After the fix: clean run, exit 0, no
warnings; `ruff`/`pyright` show the same (pre-existing, untouched-by-this-fix) findings as before —
`pyright` in fact drops from 58 file-scoped errors to 5 because the numpy-typed-unknown chain is
gone; no new `ruff`/`pyright` findings were introduced by the fix (verified with `git stash`
before/after diffing both tools' output).

## 2. Per-candidate table

Thresholds (`packages/analytics/src/policy_analytics/validation/contract.py`,
`DEFAULT_THRESHOLDS`, unchanged): `max_adjusted_attenuation = 0.50`, `min_e_value = 1.50`,
`min_confounder_stratum_coverage = 0.50`. Attenuation below uses the **exact production formula**
(`apply.py` line 583: `1 - adjusted_harm / raw_harm`, signed, not `1 - |adjusted|/|raw|`) — this
matches the gate's own printed detail text exactly (e.g. `CAND-004`: gate text "attenuation 1.02",
this table: 1.0185). Note this is marginally different from, and more precise than, the informal
`1 − |adjusted|/|raw|` formula `docs/benchmark/task-065-b2b-portability-postmortem.md` §2.9 used
for its own summary table — that document's reported max attenuation (0.997) undercounts the three
sign-flipped candidates; the real production figure for those reaches as high as 1.0185
(`CAND-004`). This does not change any verdict (those three candidates independently fail the
`same_sign` sub-condition regardless of which attenuation formula is quoted) — noted here as an
honest, minor precision correction to the earlier document, not a discrepancy in the frozen
artifact or the gate's own behavior.

"Effective sample size" = `total_exposed_usable` (exposed records inside strata that clear
`MIN_STRATUM_CELL = 5` on both sides — the population the adjusted estimate is actually computed
over). "Joint strata" = `n_groups` (all joint cells formed by the selected covariates) /
`n_usable` (cells clearing the floor). "Covered sample share" = `coverage` =
`total_exposed_usable / total_exposed_all`.

| Candidate | Conditions | Raw effect (USD) | Adjusted effect (USD) | Attenuation | Selected covariates (n/pool) | Strata (usable/total) | Coverage | Eff. n | E-value | Temporal (dev/val/holdout same-sign, retention) | G06 exact failing sub-condition(s) |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---|---|
| CAND-001 | `deal_size_usd<21811.14 & product_line=Platform` | 22,370.9 | −58.1 | **1.0026** | competitor_involved, decision_maker_engaged, **company_size_band**, lead_score (4/9) | 16/64 | 0.565 | 970 | 1.042 | ✓/✓/✓, 0.98 | same_sign, attenuation, e_value |
| CAND-002 | `deal_size_usd<21811.14 & discount_requested_pct≥5.48` | 21,073.0 | 876.4 | 0.9584 | competitor_involved, decision_maker_engaged, product_line, **company_size_band**, lead_score, sales_region (6/9) | 39/623 | 0.561 | 916 | 1.184 | ✓/✓/✓, 0.97 | attenuation, e_value |
| CAND-003 | `deal_size_usd<21811.14 & lead_score<76.0` | 20,923.8 | 1,389.2 | 0.9336 | competitor_involved, decision_maker_engaged, product_line, **company_size_band**, discount_requested_pct (5/9) | 40/183 | 0.501 | 793 | 1.242 | ✓/✓/✓, 0.98 | attenuation, e_value |
| CAND-004 | `deal_size_usd<21811.14 & discount_requested_pct<18.91` | 20,387.3 | −376.3 | **1.0185** | competitor_involved, decision_maker_engaged, product_line, **company_size_band**, lead_score, sales_region (6/9) | 38/623 | 0.588 | 943 | 1.114 | ✓/✓/✓, 0.99 | same_sign, attenuation, e_value |
| CAND-005 | `deal_size_usd<21811.14 & lead_score≥42.0` | 20,458.8 | −124.4 | **1.0061** | competitor_involved, decision_maker_engaged, product_line, **company_size_band**, discount_requested_pct (5/9) | 42/183 | 0.939 | 1,509 | 1.062 | ✓/✓/✓, 0.98 | same_sign, attenuation, e_value |
| CAND-006 | `competitor_involved=True & deal_size_usd<28597.49` | 15,720.5 | 1,167.7 | 0.9257 | decision_maker_engaged, product_line, **company_size_band**, discount_requested_pct, lead_score (5/9) | 83/333 | 0.901 | 1,033 | 1.215 | ✓/✓/✓, 0.99 | attenuation, e_value |
| CAND-007 | `company_size_band=small & discount_requested_pct≥5.48` | 20,874.4 | 1,871.8 | 0.9103 | competitor_involved, decision_maker_engaged, product_line, **deal_size_usd**, lead_score, sales_region (6/9) | 45/621 | 0.585 | 786 | 1.291 | ✓/✓/✓, 0.96 | attenuation, e_value |
| CAND-008 | `deal_size_usd<28597.49 & lead_score<54.0` | 16,306.3 | 1,146.8 | 0.9297 | competitor_involved, decision_maker_engaged, product_line, **company_size_band**, discount_requested_pct, sales_region (6/9) | 68/661 | 0.562 | 665 | 1.213 | ✓/✓/✓, 0.95 | attenuation, e_value |
| CAND-009 | `company_size_band=small & lead_score<76.0` | 20,621.3 | 2,223.4 | 0.8922 | competitor_involved, decision_maker_engaged, product_line, **deal_size_usd**, discount_requested_pct (5/9) | 24/179 | 0.572 | 751 | 1.324 | ✓/✓/✓, 0.98 | attenuation, e_value |
| CAND-010 | `deal_size_usd<28597.49 & sales_region=East` | 15,098.1 | 451.1 | 0.9701 | competitor_involved, decision_maker_engaged, product_line, **company_size_band**, discount_requested_pct, lead_score (6/9) | 79/610 | 0.692 | 799 | 1.124 | ✓/✓/✓, 0.96 | attenuation, e_value |
| CAND-011 | `company_size_band=small & lead_score≥42.0` | 20,295.2 | 520.2 | 0.9744 | competitor_involved, decision_maker_engaged, product_line, **deal_size_usd**, discount_requested_pct (5/9) | 32/179 | 0.973 | 1,294 | 1.136 | ✓/✓/✓, 0.98 | attenuation, e_value |
| CAND-012 | `company_size_band=small & discount_requested_pct<18.91` | 20,277.8 | 1,235.0 | 0.9391 | competitor_involved, decision_maker_engaged, product_line, **deal_size_usd**, lead_score, sales_region (6/9) | 43/621 | 0.559 | 735 | 1.225 | ✓/✓/✓, 0.99 | attenuation, e_value |
| CAND-013 | `deal_size_usd<8413.08 & product_line=Platform` | 19,214.0 | 1,123.1 | 0.9415 | competitor_involved, decision_maker_engaged, **company_size_band**, discount_requested_pct, lead_score (5/9) | 51/246 | 0.957 | 931 | 1.211 | ✓/✓/✓, 0.97 | attenuation, e_value |
| CAND-014 | `company_size_band=small & competitor_involved=False` | 18,644.4 | 256.1 | 0.9863 | decision_maker_engaged, product_line, **deal_size_usd**, discount_requested_pct, lead_score (5/9) | 46/332 | 0.921 | 939 | 1.091 | ✓/✓/✓, 0.97 | attenuation, e_value |
| CAND-015 | `deal_size_usd<28597.49 & lead_source=referral` | 14,590.1 | 449.3 | 0.9692 | competitor_involved, decision_maker_engaged, product_line, **company_size_band**, discount_requested_pct, lead_score (6/9) | 53/610 | 0.582 | 555 | 1.124 | ✓/✓/✓, 0.96 | attenuation, e_value |

**Excluded-from-pool covariates and why, uniform across all 15:** the candidate's own two literal
condition columns (circularity rule, unchanged since `ADR-042`); `deal_created_date` (DECISION_TIME
but not `adjustment_eligible` in the manifest — the one disclosed date-like exclusion, §4b/§11).
Pool size is therefore always `11 − 2 = 9`.

**Skipped-for-coverage covariates (tried, rejected):** every candidate's skip list is drawn from
`{industry, lead_source, sales_rep}` plus, for the five candidates with only a 5-covariate selected
set, also `sales_region`. All skips are for the identical stated reason — the trial coverage if
added would drop below `min_confounder_stratum_coverage = 0.50` (e.g. `CAND-001`: adding
`sales_rep` would drop coverage to 0.0064) — never because a covariate "isn't relevant." No
candidate was ever blocked by an *insufficient pool* (9 eligible covariates is the same order of
magnitude as travel's disclosed 8-covariate residual case, `ADR-043`) — the pool is not thin,
what happens *inside* the coverage-gated selection is the story (§4).

**G06 exact failing sub-condition, aggregated:** all 15/15 fail **attenuation** (0.892–1.018 vs.
ceiling 0.50) and **E-value** (1.042–1.324 vs. floor 1.50) simultaneously; 3/15
(`CAND-001`, `CAND-004`, `CAND-005`) additionally fail **same_sign** (adjustment flips the point
estimate's sign). **Zero of 15 fail on coverage** — coverage clears the 0.50 floor for every single
candidate (min 0.501, `CAND-003`, essentially at the floor; mean 0.70). No candidate fails on
"insufficient eligible covariates" or is blocked from a larger selected set by pool exhaustion —
the pool always has 9 candidates and 4–6 are always selected. G09/G13/G14 are the only other
non-passing gates and are identical, uninformative, and unrelated to this diagnosis for every
candidate (§2.7 of the postmortem; re-confirmed here: exactly one distinct 16-gate outcome pattern
across all 15 candidates, computed directly from `task-019-...json`).

## 3. The dataset-level fact this diagnosis turns on

`η²(deal_size_usd | company_size_band)` on the development split (public data, dataset-level, not
per-candidate) = **0.9593** — `company_size_band` explains 95.9% of `deal_size_usd`'s variance.
These are, for practical purposes, the same variable at two different levels of coarseness (raw
value vs. its own 4-band discretization: small/medium/large/enterprise, non-overlapping USD
ranges). Every one of the 15 committed candidates conditions on **one** of this pair (`deal_size_usd`
or `company_size_band`, public fact, `pattern_definition`, already noted in the postmortem §2.9)
— and `_adjustment_pool`'s circularity rule (`ADR-042`, unchanged) excludes only the candidate's
own literal condition columns, so the **other** member of the pair is never excluded and is, in
every one of the 15 candidates, selected into the adjustment set (`size_proxy_in_selected_set` is
non-null for all 15, per the raw JSON).

**Ablation, computed directly by the script (`attenuation_without_size_proxy`):** dropping only
the size-proxy covariate from each candidate's already-selected set (keeping every other selected
covariate) collapses attenuation from a mean of **0.957** (range 0.892–1.018) down to a mean of
**0.075** (range 0.004–0.173) — a roughly 13x reduction — while coverage *rises* (mean 0.930, range
0.798–1.000, since dropping a covariate only relaxes the joint-stratification constraint). This is
not a coverage-floor artifact; it is direct evidence that **one covariate, not the joint effect of
the selected set, explains essentially all of the measured attenuation** for every one of the 15
candidates, without exception.

## 4. Mechanism checklist — confirmed / ruled out, with cited numbers

1. **Covariate cardinality — contributing, not causal.** The greedy order (ascending distinct-value
   count, ties alphabetical, `ADR-042`) is real and unchanged; `company_size_band` (4 categories) is
   tried early in every candidate where it isn't the condition. But cardinality only decides *order*
   — `discount_requested_pct` (also 4 categories) is *skipped* for several candidates on coverage
   grounds (e.g. `CAND-001`: 0.2721 trial coverage), so low cardinality alone does not guarantee
   selection. What differs about the size-proxy is its correlation with the outcome, not its
   cardinality. **Contributing** (determines when the proxy is *tried*), **not the driver of
   magnitude** (§3's ablation is the driver).
2. **Joint-stratification sparsity — real, but not binding.** The *unrestricted* full-9-covariate
   cross-tabulation collapses to **exactly 0.0000 coverage for all 15 candidates** (`cells.n_usable`
   is a small fraction of `n_groups` throughout, e.g. `CAND-008`: 68/661) — sparsity at the
   full-pool level is total, more severe than travel's one disclosed residual case (`ADR-043`:
   0.21, thin but nonzero). But the *selected*, coverage-gated set (4–6 covariates) never fails the
   coverage sub-condition (§2) — sparsity is real at the unused, unrestricted extreme but is not
   what fails any of the 15 candidates.
3. **The coverage floor itself — ruled out as a cause of FAIL.** 0/15 candidates fail on coverage;
   min is 0.501 (`CAND-003`), comfortably above 0.50 for the other 14. The floor *does* limit the
   selected set to 4–6 of 9 pool covariates, but §3's ablation shows the covariates it excludes are
   not the ones driving attenuation anyway.
4. **Greedy covariate-selection order effects — confirmed, a real general property.** Because the
   ordering signal is cardinality alone (no correlation-with-condition awareness), a low-cardinality
   near-duplicate of a condition feature is *systematically* tried early and is never disqualified
   by the circularity rule (which checks literal column identity, not information content). This is
   general in principle — any domain shipping a raw quantity and its own low-cardinality band as
   two separate `adjustment_eligible` columns would trigger the same behavior — not b2b-specific by
   construction of the rule.
5. **Condition-feature exclusion from the pool — confirmed as the precise mechanical gap.**
   `_adjustment_pool` (`apply.py`, unchanged since `ADR-042`) excludes exactly
   `condition_features` — a `frozenset[str]` of literal column names. It has no mechanism to also
   exclude a column that is merely a near-perfect proxy of a condition feature under a different
   name. This is the exact rule whose scope this diagnosis shows is too narrow.
6. **Covariate correlation/collinearity — confirmed as the dominant driver.** §3: η² = 0.9593
   (dataset-level, public); ablation collapses mean attenuation 0.957 → 0.075 by removing one
   covariate. This is the single most consistent (15/15, no exceptions) finding in this diagnostic.
7. **Interaction-driven confounding — ruled out as the shape of this residual, in direct contrast
   to `ADR-043`'s travel case.** `ADR-043`'s signature: additive FWL ≈ 0% attenuation
   (157.2→158.9 EUR) vs. joint stratification ≈70% (157.2→47.7 EUR) — confound invisible to main
   effects alone. Here: mean additive FWL attenuation is **0.914** (range 0.794–1.157,
   `additive_fwl_attenuation` in the raw JSON) — essentially the *same order of magnitude* as the
   actual selected-set attenuation (mean 0.957) for every one of the 15 candidates. A main-effects-
   only regression over the same 9-covariate pool reproduces almost the whole effect. This is the
   opposite signature from the one `ADR-055`/`ADR-056` characterized this failure as sharing. The
   `ADR-043`-style "unrestricted joint" comparison point is itself degenerate here (§4.2 above,
   coverage 0 for all 15) — the diagnostic technique `ADR-055` cited as evidence of a shared shape
   does not actually produce a usable comparison number on this run.
8. **Outcome scale — ruled out.** Same `net_deal_contribution_usd` (`harm_multiplier=-1`) throughout
   development/validation/future_holdout; G03/G04 pass cleanly for all 15 with wide-margin
   confidence intervals (`docs/benchmark/task-065-b2b-portability-postmortem.md` §2.8, re-confirmed
   here via the identical gate-outcome pattern in §2). No scale artifact indicated.
9. **Heterogeneous effects — indeterminate, not evaluable from available inputs.** G09 is
   `NOT_EVALUATED` for all 15 (`validation_roles.heterogeneity_column = null` in the b2b manifest,
   confirmed directly from `manifest.json`). This diagnosis cannot confirm or rule this out; it is a
   disclosed, independent gap (domain-contract category), not something this script's inputs can
   speak to.
10. **Lack of overlap/positivity — present as texture, not the proximate failure.** Fine-grained
    joint cells are frequently one-sided (e.g. `CAND-008`: 661 cells, 402 comparison-only, 22
    exposed-only, 169 both-below-floor, only 68 usable) — real, imperfect overlap at the
    full-joint-cell level. But `confounder_stratum_coverage`'s whole purpose is to already discount
    for exactly this by construction, and it clears the floor for all 15 (§2). Not the binding
    constraint.
11. **Adjustment-method/data-type mismatch — ruled out.** `_binned_adjustment_frame` correctly
    quartile-bins high-cardinality numerics and leaves categorical/boolean/low-cardinality numerics
    as-is (confirmed by inspecting `adjustment_selected` values in the raw trace — categorical
    strings, boolean-like flags, and untouched low-cardinality numerics all appear as expected, no
    sign of an unbinned high-cardinality numeric column entering a stratification key). No mismatch
    found.

## 5. Comparison to `ADR-042`/`ADR-043`'s diagnosed shape

`ADR-042`/`ADR-043` (travel, `CAND-015`/`task-060-iteration-20260820-004`): coverage-starved at the
margin (0.51, near the floor), 7 covariates selected of 8 eligible, and — critically — the residual
gap was *invisible to additive adjustment* (near-zero attenuation) and only visible once covariates
were stratified *jointly* (interaction). That is a genuinely different statistical signature from
what §2–§4 show here: b2b's coverage is comfortably clear of the floor for 14/15 candidates, the
pool is not exhausted, and the confound is visible to a *purely additive* method almost as strongly
as to the actual joint method. **This is not the same known gap.** It is a distinct, previously
undiagnosed general mechanism: a circularity-exclusion rule that is blind to near-duplicate/
highly-collinear covariates of a candidate's own condition, landing here on a domain whose
manifest happens to expose exactly such a pair (`deal_size_usd`/`company_size_band`) as two
separate `adjustment_eligible` columns.

## 6. Classification

**A — GENERAL_FIXABLE_METHOD_DEFECT, but a materially different specific defect than the one
`ADR-055`/`ADR-056` recorded, compounded by a domain-contract characteristic (flavor of B).**

- **Confirms** the coarse-level bucket `ADR-055`/`ADR-056` already landed on: this is not
  `b2b_sales`-specific pattern/trap tuning, not a validation-code bug, and not simply "correct
  conservative rejection with nothing more to say" (§4.6 shows a specific, general, fixable
  mechanical gap: `_adjustment_pool`'s circularity check operates on literal column identity, not
  correlation). The failure is general in the sense that any domain exposing a raw quantity and its
  own coarse band as two separate `adjustment_eligible` columns would trigger the identical
  behavior, independent of `b2b_sales`'s specific patterns or traps.
- **Contradicts** `ADR-055`/`ADR-056`'s specific mechanism-level claim — that this is "the same
  qualitative shape `ADR-043` already characterized... a confound that is at least partly
  interaction-driven, which closed-form joint stratification can only partially resolve." §4.7/§5
  show the opposite signature: additive (main-effects-only) adjustment reproduces almost the whole
  effect here, unlike travel's case. This is a genuine, evidenced discrepancy, not a rounding
  difference, and it is being stated plainly rather than smoothed into the existing record.
- **Compounding domain-contract element (why this bites b2b and not, so far, travel):** b2b's
  manifest declares both `deal_size_usd` and `company_size_band` — described in
  `docs/benchmark/task-065-b2b-portability-postmortem.md` §2.9 itself as "a banded version of the
  same quantity" — as two separate `adjustment_eligible` `DECISION_TIME` columns, with no
  deduplication or correlation review; travel's `TASK-013`-reviewed, `ATTACHED`-status contract has
  no disclosed analogue in the postmortem's own domain-comparison table (§3). This is consistent
  with, and sharpens, `ADR-055`'s already-recorded category 7 (domain contract — implicated) finding
  with a specific, named mechanism rather than a general "thinner contract" observation.
- **Explicitly not C:** this is not simply "correct conservative rejection of a genuinely
  unrecoverable confound" in the strong sense — the ablation in §3 shows most of the reported
  confounding is attributable to a *single* covariate that is itself nearly a restatement of the
  candidate's own condition, which is a real, nameable, and in-principle-fixable gap in the
  adjustment-pool construction rule, not an irreducible property of the domain's confounding
  structure. This diagnosis cannot certify from public artifacts alone whether the *residual*
  ~7.5%-mean attenuation (after removing the size-proxy) reflects genuine remaining confounding or
  further crowding by a *different* correlated covariate — that would require checking correlation
  among the other 8 pool covariates, which this diagnosis did not do (see §8, falsifiable
  observation 2).
- **Explicitly not D:** the evidence is direct, computed from real per-candidate output, consistent
  across all 15 candidates without exception, and points at a specific mechanical gap with a
  specific proposed fix shape (extend `_adjustment_pool`'s circularity rule from literal-identity
  exclusion to a correlation-aware exclusion). This is not an evidentiary dead end.

## 7. Flag for whoever reviews `TASK-068` next (Code Reviewer, `HANDOFF-070`) — observation only, no
authority claimed to change `TASK-068`/`ADR-057`

`TASK-068`'s implementation (`ADR-057`) was scoped against `ADR-055`/`ADR-056`'s coarse-level
attribution: G06's own limitation is "the same general adjustment-richness/interaction-effect
limitation already disclosed," and the *separate*, upstream problem worth fixing is anchor-feature
identity crowding at final candidate selection (category 3). This diagnosis's evidence suggests
that framing understates how entangled the two are for this domain, and raises a real question
about how much recall `TASK-068`'s mechanism can actually recover here even if its own structural
check passes:

- `TASK-068`'s cap operates on which **feature identity anchors a candidate's own condition** in
  the final Top-K. It does not touch, and cannot touch (by its own explicit scope, `ADR-056`/
  `ADR-057`), **which covariates land in a candidate's G06 adjustment pool.**
- Per §3, *any* b2b candidate — regardless of which feature anchors its condition — that does not
  itself condition on both `deal_size_usd` and `company_size_band` will still have whichever one it
  doesn't condition on sitting in its adjustment pool, low-cardinality, tried early, and (per the
  ablation) capable of explaining away most of a real effect on its own. A more feature-identity-
  diverse Top-K (`TASK-068`'s stated goal) does not by itself change this for any *individual*
  surviving candidate that still touches either member of this specific collinear pair.
- This is **not** a claim that `TASK-068` is wrong to build or that its structural check will fail
  — the structural check (distinct anchor-feature count) is a different, valid, orthogonal question
  from whether G06 passes more candidates. It **is** a claim that a passing `TASK-068` structural
  check on a future domain, by itself, does not predict whether G06's own collinearity-blind-spot
  (§4.5/§6) will or won't also depress that domain's economic-weighted recall — that depends on
  whether the *new* domain's manifest happens to expose a similarly collinear covariate pair, an
  independent question `TASK-068`'s preregistered success/kill criteria do not currently ask.
- No code, status, or ADR is changed by this observation. It is handed forward for whoever reviews
  `TASK-068` next to weigh, consistent with `HANDOFF-070`'s standing review responsibility.

## 8. Falsifiable observations that could overturn this diagnosis

1. **Direct, already-computable recheck:** anyone with repo access can rerun
   `scripts/diagnose_g06_task065_b2b.py` (deterministic, pure functions over frozen inputs) and
   confirm or refute that `additive_fwl_attenuation` tracks the selected-set `attenuation` as
   closely as claimed in §4.7/§5, and that `attenuation_without_size_proxy` collapses as claimed in
   §3, for all 15 candidates. If either fails to reproduce, §5's classification is wrong.
2. **Unchecked correlation among the remaining 8 pool covariates:** this diagnosis did not compute
   pairwise correlation/η² among the other pool covariates (only `deal_size_usd`/
   `company_size_band`, the pair the postmortem itself already flagged as related). If a second,
   similarly collinear pair exists among the remaining covariates (e.g. `lead_score` and some
   combination of `decision_maker_engaged`/`competitor_involved`), the residual ~7.5%-mean
   attenuation after removing the size proxy (§3) may itself be partly a second instance of the same
   mechanism rather than genuine remaining confounding — this would strengthen, not weaken, §6's
   classification, but is not confirmed here and should not be assumed.
3. **E-value was not recomputed for the size-proxy-removed counterfactual.** §3's ablation only
   recomputes attenuation and coverage, not the E-value (which needs `pooled_sd`, not re-derived
   here). It is a testable, not-yet-confirmed prediction that removing the size proxy would also
   clear the E-value floor for a material fraction of the 15 — this diagnosis stops short of that
   specific claim.
4. **Hidden-ground-truth check, out of this diagnosis's scope by design:** if `B03`'s true
   generative mechanism (already legitimately viewable by an actor with existing custody, e.g. a
   future `TASK-028`-scoped session) turns out to have no relationship to deal size or company size
   at all, that would suggest the near-total attenuation observed here is a coincidental collinearity
   artifact rather than a meaningful adjustment result — weakening confidence that this is "true"
   confounding recognized/misrecognized correctly, though it would not change §6's mechanical
   finding about the adjustment-pool rule itself.
5. **Travel comparison, already public and re-derivable without opening any hidden ground truth:**
   if travel's own adjustment-eligible pool (16 columns, `docs/benchmark/task-065-b2b-portability-
   postmortem.md` §3) is checked and found to contain a similarly collinear (η² > ~0.9) pair that
   has simply never been selected together with a matching condition feature by chance, that would
   support this being a fully general, recurrence-prone method gap rather than one this domain's
   contract happens to expose; if no such pair exists anywhere in travel's pool, that would support
   the "compounded by domain contract" half of §6's classification more strongly than the "purely
   general" half.
6. **A future domain (if and when `TASK-068` or any successor authorizes one) reproducing or not
   reproducing this shape:** if a subsequent domain's G06 failures (should any occur) show the
   interaction-driven `ADR-043` signature instead of this collinearity signature, that would confirm
   both mechanisms are real and distinct, each recurring under different domain conditions — neither
   confirming nor contradicting this diagnosis, but sharpening the general taxonomy.

## 9. What this diagnosis does not establish

Consistent with its own scope boundary (§0): this document does not open or characterize
`hidden_ground_truth.json`'s contents beyond the already-public `matched_patterns`/`is_trap` fields
`TASK-028`'s evaluator already froze; it does not confirm or rule out whether `B03`'s true
generative mechanism is or is not genuinely mediated by deal size; it proposes no code change to
`apply.py`, no new contract version, and no change to any threshold — a correlation-aware extension
to `_adjustment_pool`'s circularity rule is named as the natural fix shape in §6 but is not
designed, scoped, or authorized here, and no new task is created by this document. It does not
authorize, scope, or touch `TASK-068`, `ADR-057`, or `HANDOFF-070` in any way beyond the observation
recorded in §7 for a future reviewer to weigh.
