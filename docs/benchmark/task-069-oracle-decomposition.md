# TASK-069 oracle decomposition benchmark — travel, `task-064-beam-20260822-001`

**Status: POST-HOC DIAGNOSTIC throughout.** Every number in this document is produced by
`scripts/diagnose_oracle_decomposition.py`, run for real on 2026-08-28 against already-frozen,
already-committed artifacts. Nothing here is a new official `TASK-015`/`TASK-019`/`TASK-028` run,
changes any frozen artifact, threshold, gate, or recorded verdict, or touches
`discovery/engine.py` or any other production module. Raw computed output:
`docs/benchmark/task-069-oracle-decomposition-raw.json`.

**What this closes.** `TASK-069`'s research plan, item 7. It is the diagnostic step that plan names
as "the recommended starting point, before touching the search algorithm itself" — it turns
"unique-pattern recall = 2/7" into a per-pattern, per-stage, diagnosable metric. **It is not design
work and starts none.**

**Binding constraint, restated.** `TASK-069`'s hard rule forbids any new search objective, scoring
term, or expansion policy being designed, scoped, or justified by reference to travel's specific
pattern identities or feature values, while explicitly permitting this benchmark to read those
identities *to explain failures*. This document therefore reports where each pattern dies and what
class of mechanism could in principle address it. **No per-pattern fact in this document may be
carried into a replacement mechanism's actual scoring or expansion logic.** A mechanism that
reaches 7/7 by fitting these specifics would be a worse outcome than the honest 2/7.

## 0. Custody and scope declaration

This diagnostic reads: the frozen candidate file
`artifacts/blind/task-064-beam-20260822-001.candidates.json` (SHA-256
`9f55dddc17e22a6064af42a89fd0c3951b4ee09a5f43595c6a3a4cc618fa6d09`, re-verified by the script
against its frozen `hashes.json` before anything else runs), its sibling `discovery_metrics.json`,
the frozen `TASK-019` report `artifacts/validation/task-019-official-20260822-task-064-beam-001.json`,
the frozen `TASK-028` report `artifacts/evaluation/task-028-task-064-beam-001.json`, the public
travel analytical dataset/manifest, `discovery/engine.py`'s real unmodified functions, and
`synthetic_data/evaluation/hidden_ground_truth.json`.

Opening travel's hidden ground truth here is the established discipline, not an exception: it has
been legitimately open since `TASK-028`'s first evaluation
(`docs/benchmark/task-029-benchmark-report-v1.md` §1), the traced run was frozen and committed via
signed receipt before any evaluation opened it, and this is the same
"already frozen, now graded" precedent set by `scripts/evaluate_benchmark.py` (`TASK-028`,
`ADR-025`), `scripts/diagnose_candidate_pool_recall.py` (`ADR-038`/`HANDOFF-055`) and
`scripts/diagnose_g06_task065_b2b.py` (`TASK-067`). No blind run was issued; no new domain was
touched; no other domain's ground truth was opened.

**`artifacts/` is gitignored and per-checkout.** The script takes `--blind-root`; reproducing this
document requires a checkout holding the frozen run's outputs.

## 1. Fidelity — the trace is the committed run, asserted not assumed

`scripts/diagnose_oracle_decomposition.py` calls `discovery.engine`'s own
`_atoms` / `_metric` / `_eligible` / `_development_score` / `_select_expansion_beam` /
`_temporal_consistency` / `_apply_stability_credit` / `_greedy_diverse_select` /
`_apply_feature_identity_cap` verbatim; only the recording is new. It refuses to print anything
unless both of the following hold, and both did:

1. reproduced `evaluated_hypotheses = 26,213`, exactly the committed run's own figure; and
2. the reproduced final selection is **condition-for-condition identical to all 15 committed
   candidates**.

The committed run declares `discovery-engine-v0.5.0`; the installed engine is `v0.6.0`. `v0.6.0`'s
only addition is the feature-identity cap, inert at its default `max_feature_identity_fraction=1.0`
— assertion 2 is the direct evidence that the difference is unobservable here, rather than an
assumption.

### Search shape

| Depth | Generated | Eligible | Skipped as exposure-identical to a parent | Expansion beam |
|---|---:|---:|---:|---:|
| 1 | 88 | 25 | 0 | 25 |
| 2 | 1,754 | 1,201 | 61 | 418 |
| 3 | 24,371 | 16,155 | 1,078 | — (terminal) |

16 `DECISION_TIME` feature columns, 88 atoms, **17,381-rule eligible pool** before selection.
Interaction-phase relevance floor: `1,453.36`.

## 2. Method: the "oracle projection"

Stage 1 needs a decision about *which* rule counts as "the pattern" inside a vocabulary that cannot
express the pattern exactly. The script projects each true conjunct onto **the tightest atom that
still covers it** — the largest `ge` threshold at or below a lower bound, the smallest `lt`
threshold at or above an upper bound, the exact `eq` atom for a categorical level. Covering, never
narrowing, is the point: a covering projection exposes every booking the pattern affected, so its
recall against that pattern is 1.0 by construction and `scripts/evaluate_benchmark.py`'s own
`recall ≥ 0.5` matching statistic is satisfied whenever the projection is eligible at all.
Whatever a covering projection cannot do, no rule in this vocabulary can do.

Two mechanical consequences are recorded rather than silently absorbed: a covering atom satisfied by
every development row is dropped (support 1.0 can never be eligible), and where a numeric equality
needs two bounds on one feature, only the more selective survives — the engine's expansion never
adds a second condition on a feature a rule already uses.

The script hardcodes **no** pattern id, feature name, threshold, or rule; every true rule is parsed
generically out of `hidden_ground_truth.json`'s own `rule` string at runtime.

## 3. Headline results — per-pattern stage of death

Two verdicts are reported per pattern and neither substitutes for the other. **"Recovered"** is
`TASK-028`'s own frozen metric (matched by a candidate reaching at least `predictive_association`),
read from the frozen evaluation rather than re-derived. **"Oracle branch dies at"** is where the
*pattern's own tightest representable rule* first fails. They differ because the benchmark's
matching statistic is recall-only, so a much broader rule can recover a pattern whose own precise
branch never survives.

| Pattern | Impact (€) | Recovered | Oracle branch dies at | Tightest representable rule | Broadening | Pool rank | Clears floor |
|---|---:|---|---|---|---:|---:|---|
| P01 | 141,765 | **yes** | S5_SELECTED | `booking_lead_days lt 23.0 AND discount_rate ge 0.12 AND supplier eq BlueWing` | 1.06× | 69 / 17,381 | yes |
| P02 | 115,315 | no | S3_SURVIVES_EXPANSION | `customer_segment eq family AND destination eq Zanzibar AND party_size ge 4.0` | 3.34× | — | — |
| P03 | 126,133 | no | S5_SELECTED | `acquisition_channel eq paid_search AND customer_type eq new AND installments ge 3.0` | 1.00× | 835 / 17,381 | yes |
| P04 | 39,150 | no | S2_GENERATED | `supplier eq Atlas AND trip_duration_days ge 10.0` | 8.90× | — | — |
| P06 | 135,891 | **yes** | — (reaches validation) | `booking_lead_days lt 23.0 AND destination eq Tokyo AND payment_method eq bank_transfer` | 1.42× | 204 / 17,381 | yes |
| P08 | 28,387 | no | S2_GENERATED | `booking_lead_days ge 88.0 AND party_size lt 2.0 AND product_category eq luxury` | 1.05× | — | — |
| P09 | 28,054 | no | S5_SELECTED | `party_size ge 4.0 AND supplier eq DeltaSun` | 3.58× | 5,894 / 17,381 | yes |

"Broadening" = the projection's full-cohort exposure divided by the pattern's affected record count
— how much specificity the vocabulary costs before search even starts.

### Stage 1 in detail — representability

| Pattern | Conditions representable | Exact | What is missing |
|---|---|---|---|
| P01 | 3 / 3 | 2 | `booking_lead_days<21` → nearest covering `lt 23.0` |
| P02 | 3 / 4 | 2 | `booking_month IN [6,7,8]` has no atom; `party_size>=5` → `ge 4.0` (grid stops at 4); rule needs 4 conditions vs `max_conditions=3` |
| P03 | 3 / 3 | **3** | nothing — **exactly representable** |
| P04 | 2 / 3 | 1 | `booking_month IN [1,2,12]` has no atom; `trip_duration_days>=14` → `ge 10.0` (grid stops at 10) |
| P06 | 3 / 3 | 2 | `booking_lead_days<10` → nearest covering `lt 23.0` |
| P08 | 3 / 3 | 2 | `booking_lead_days>=90` → `ge 88.0`; `party_size=1` needs two bounds on one feature, only `lt 2.0` survives (exact here) |
| P09 | 2 / 3 | 2 | `booking_month IN [9,10,11]` has no atom |

Three of seven patterns are blocked on a **calendar atom that does not exist**. Two of those three
are *also* blocked by the numeric quantile grid: `_atoms` places thresholds only at the 0.2/0.4/0.6/0.8
development quantiles, so `trip_duration_days` tops out at `ge 10.0` against a true bound of 14, and
`party_size` at `ge 4.0` against a true bound of 5. This is the same limitation `ADR-045` recorded
for P04's month condition, now measured on a second axis it did not cover.

### Stage 2/3 in detail — the distinction this benchmark exists to draw

`diagnose_candidate_pool_recall.py` could not tell "pruned before it could exist" from "present but
low-ranked". The per-depth trace does:

- **P02 — S3, exposure-identical to a parent.** Generated at depth 3, eligible, and then *discarded*:
  `_metric` finds it exposes exactly the same rows as its depth-2 parent
  `destination eq Zanzibar AND party_size ge 4.0`, because on this dataset `customer_segment=family`
  and `party_size ≥ 4` coincide. The redundancy skip is doing exactly what it was built to do. The
  practical consequence is mild and should not be overstated: **the surviving parent is itself a
  full recall-1.0 match at pool rank 1,532/17,381, clears the relevance floor, and then loses
  selection.** P02's real terminal stage is therefore S5, one exposure-identical rule removed.
- **P04 — S2, and not because of the beam.** Neither depth-1 ancestor ever entered the scored pool:
  `supplier eq Atlas` measures `harm_per_booking = −50.39` and `trip_duration_days ge 10.0` measures
  `−24.85`, both failing `_eligible`'s `harm > 0`. `discover_candidates` only expands rules already
  in `scored`, so the depth-2 rule was never enumerated — and it would have been ineligible anyway
  (`−41.55`). **Not a beam-width problem, not a scoring problem, and not fixable by any expansion
  policy.**
- **P08 — S2, and here the beam genuinely binds.** Its depth-2 ancestor
  `booking_lead_days ge 88.0 AND party_size lt 2.0` *was* eligible and scored, at **rank 1,047 of
  1,201** against a 418-rule expansion beam — pruned before it could form a third condition. (This
  reproduces `ADR-045`'s own pre-code trace figure of "908–1047" exactly, from an independent code
  path.) But the depth-3 rule would then have been ineligible regardless: `n_exposed = 35 < min_n =
  40`. **P08 is doubly blocked — beam first, support floor immediately behind it.**

### Stage 4/5 in detail — three patterns die purely in selection

P01, P03 and P09's oracle branches are generated, eligible, scored, pooled, and **clear the
relevance floor** — then lose every greedy-diverse selection round. The `v0.4.1` floor that
`HANDOFF-055` identified as the binding constraint is **no longer binding for these three** under
`v0.5.0`/`v0.6.0`'s configuration: all three sit above `1,453.36`. What excludes them now is
marginal-gain competition against the dominant `discount_rate`-anchored family, not the floor.

P03 is the sharpest case in the whole benchmark: **exactly representable, exact recall 1.0, exact
population (broadening 1.00×), pool rank 835 of 17,381, above the floor — and not selected.**

### Stage 6 — validation, and the counterfactual

P06's oracle projection *is* committed candidate `CAND-007`; it reached `predictive_association`.
That is the only pattern whose own precise branch survives the entire pipeline.

For every pattern whose oracle branch was never selected, the script asked the real, unmodified
validation contract what it *would* have said. This is explicitly **counterfactual** — no artifact
is written under `artifacts/validation/`, and the Benjamini–Hochberg adjustment runs over a
different reported-p-value set than the official run's (family size held at the committed run's own
26,213).

| Pattern | Counterfactual verdict | Counterfactual evidence level | Failed gates |
|---|---|---|---|
| P01 | DOWNGRADE | `descriptive_observation` | G11, G12, G13, G14 |
| P02 | DOWNGRADE | `descriptive_observation` | G05, G11, G12, G13, G14 |
| P03 | DOWNGRADE | `descriptive_observation` | G12, G13, G14 |
| P04 | DOWNGRADE | `descriptive_observation` | G03, G04, G05, G06, G10, G12, G13, G14, G15 |
| P08 | DOWNGRADE | `descriptive_observation` | G03, G04, G05, G11, G12, G13, G14, G15 |
| P09 | DOWNGRADE | `descriptive_observation` | G03, G05, G06, G12, G13, G14 |

**Correction, 2026-08-28 (`TASK-069` item 1, `docs/benchmark/task-069-validation-power-autopsy.md`
§2).** P09's row above originally omitted `G03_SAMPLE_ADEQUACY`, which
`task-069-oracle-decomposition-raw.json` records and which is P09's *binding* level-2 gate. The
raw output was and is correct; only this table's transcription was wrong. No computed number
changed.

**This materially qualifies the whole exercise, and is the most uncomfortable finding here.** Even a
selection policy that admitted all six oracle branches would move `TASK-028`'s unique-pattern recall
by **zero**, because that metric counts patterns matched by a candidate reaching at least
`predictive_association`, and none of these six reach it. G12/G13/G14 fail for every observational
candidate by construction, so the discriminating gates are G03/G04/G05/G11. Anyone reading
"selection is the bottleneck for P01/P03/P09" as "fix selection and recall rises" would be wrong.
A search-side fix is necessary for those three; on this evidence it is not sufficient.

## 4. Could any expansion order reach these patterns at all?

A first-failing-stage ladder cannot answer the question that actually decides which research
direction matters: **is the pattern reachable by *any* beam, score, or lookahead?**
`discover_candidates` only ever expands a rule already in `scored`, and `_eligible` requires
`harm_per_booking > 0`. So a rule is reachable only if some chain of nested sub-conjunctions, from a
single condition up to the whole rule, is eligible at *every* step.

The script therefore measures every sub-conjunction of the **exact** true rule — including
conditions the vocabulary cannot express, using a disclosed diagnostic-only derivation
(`booking_month := month(booking_date)`) that never becomes an atom and never enters the traced
search.

| Pattern | Exact true rule eligible? | dev `n` | dev harm/booking | Eligible ancestor chain exists? |
|---|---|---:|---:|---|
| P01 | yes | 75 | +987.05 | **yes** (every one of its 7 sub-conjunctions is eligible) |
| P02 | yes | 69 | +880.29 | **yes** (all 15 sub-conjunctions eligible) |
| P03 | yes | 152 | +396.06 | **yes** (`installments>=3` → … → full) |
| P04 | yes | 58 | +307.45 | **yes**, but only via one path |
| P06 | yes | 59 | +1,153.06 | **yes** (all 7 eligible) |
| P08 | **no** | **33** | +79.55 | **NO** |
| P09 | yes | 60 | +242.13 | **yes**, but only via one path |

### P04 — vocabulary is the whole story, on two axes

P04's only viable chain is `trip_duration_days>=14` (+32.34) → `supplier=Atlas AND
trip_duration_days>=14` (+95.49) → full rule (+307.45). Every other route is blocked:
`supplier=Atlas` alone is **−50.39** and `supplier=Atlas AND booking_month IN [1,2,12]` is **−34.41**.

The chain's required first step, `trip_duration_days>=14`, **is not an available atom** — the
quantile grid stops at 10.0, and the relaxed `ge 10.0` flips harm negative (−24.85 vs +32.34 for the
true bound). So P04 is blocked by the vocabulary twice over: a missing calendar atom *and* a
threshold grid too coarse to place the one bound that makes its ancestor harmful.

**Implication:** an eligible chain does exist once the atoms exist, so a lookahead or Pareto
expansion policy would work for P04 — but only *after* the vocabulary is fixed. Neither helps on its
own. Note also that `supplier=Atlas` is confounding trap `T02`'s exact `apparent_feature`, so P04 is
not a safe target to chase by loosening eligibility (verified directly against the ground truth's
`confounding_traps` block, not asserted from memory).

### P08 — the eligibility gate itself is the blocker

P08 has **no eligible ancestor chain at any depth, under any vocabulary**:

| Sub-conjunction | dev `n` | harm/booking | Eligible |
|---|---:|---:|---|
| `product_category=luxury` | 546 | **−142.24** | no |
| `party_size=1` | 1,202 | +59.84 | yes |
| `booking_lead_days>=90` | 929 | **−68.94** | no |
| `product_category=luxury AND party_size=1` | 130 | **−59.88** | no |
| `product_category=luxury AND booking_lead_days>=90` | 117 | **−197.03** | no |
| `party_size=1 AND booking_lead_days>=90` | 210 | +21.72 | yes |
| **full rule** | **33** | **+79.55** | **no — `n_exposed=33 < min_n=40`** |

The single chain that stays harmful (`party_size=1` → `party_size=1 AND booking_lead_days>=90` →
full) terminates on the support floor: the exact true rule affects 60 records in a 10,000-row
cohort, 33 of them in development, below `min_n = 40` and `min_support = 0.01`.

**This is the finding that changes the shape of the research plan.** P08 is unreachable by *every*
search-side direction in `TASK-069`'s list — not by a different beam, not by lookahead, not by a
Pareto frontier, not by interaction-first pair screening, not by a richer vocabulary. Its effect is
interaction-only-positive (two of its three conditions are individually *protective* in the raw
contrast) and its true population is below the engine's own eligibility floor. Recovering P08
requires reconsidering `_eligible` itself — the `harm_per_booking > 0` monotonicity assumption and
the `min_n`/`min_support` floors — which is a different kind of change from anything directions 1–6
currently scope. Its counterfactual validation (G03/G04 sample-adequacy and uncertainty failures)
independently says the same thing from the other end: at n=33 there may be nothing here a
disciplined pipeline *should* promote.

The two non-scoreable patterns corroborate the mechanism rather than contradicting it: P05 (23
affected records; 9 in development) and P07 (drift pattern, 0 development exposure) both have no
eligible chain, for the same structural reasons.

## 5. Continuity with `HANDOFF-055`

`HANDOFF-055` scanned the *final* v0.3.1 pool (5,197 rules) and found every missing pattern had a
partially-or-better matching candidate. That result holds and strengthens under v0.5.0's larger
17,381-rule pool, re-derived here with exact bitmask row algebra cross-checked against polars:

| Pattern | Best recall in pool | Rank (of 17,381) | Full-match (≥0.5) rules in pool |
|---|---|---:|---:|
| P01 | 1.000 (`discount_rate ge 0.12`) | 1 | 687 |
| P02 | 1.000 (`destination eq Zanzibar AND party_size ge 4.0`) | 1,532 | 392 |
| P03 | 1.000 (`acquisition_channel eq paid_search`) | 674 | 373 |
| P04 | **0.337** (`booking_lead_days lt 45.0`) | 743 | **0** |
| P06 | 1.000 (`booking_lead_days lt 23.0`) | 102 | 526 |
| P08 | 1.000 (`party_size lt 2.0`) | 4,005 | 126 |
| P09 | 1.000 (`party_size ge 4.0`) | 3,327 | 335 |

P04 remains the only scoreable pattern with **zero** full-match rules anywhere in the pool, exactly
as `HANDOFF-055` found. What is new is *why*: not merely that its best rule is weak, but that its
representable projection is not harmful in the data at all.

One qualification `HANDOFF-055` recorded still stands and is re-verified here directly against the
ground truth's `confounding_traps` block: **P03's own exactly-representable rule contains
`acquisition_channel eq paid_search`, which is trap `T03`'s exact `apparent_feature`.** P03 is the
cleanest selection-stage target in the benchmark and simultaneously the least safe one to chase,
until `G06`'s adjustment set is generalized on its own generically-motivated schedule (`ADR-036`).

## 6. What this implies for `TASK-069`'s other six directions

Stated as which *class* of mechanism could address which pattern. This is a mapping of failure modes
to research directions — **not a design, not a recommendation to fit any of these patterns, and not
input to any mechanism's logic.**

| Pattern | Binding constraint | Direction that could matter |
|---|---|---|
| P01 | already recovered; its precise branch loses selection | 1 / 2 (selection-stage), low value — already counted |
| P02 | exposure-identical parent, then selection; needs depth ≥ 4 and a calendar atom for full specificity | 6 (vocabulary), then 1 / 2 |
| P03 | **selection only** — exactly representable, exact recall, above floor, rank 835 | **1 / 2** — but trap-`T03`-unsafe until G06 is generalized |
| P04 | **vocabulary, twice** — missing calendar atom *and* too-coarse numeric grid | **6 first**; 3 (lookahead) only becomes useful afterwards |
| P06 | none — reaches `predictive_association` | — |
| P08 | **eligibility gate** — no eligible ancestor chain exists at any depth; true rule below `min_n` | **none of 1–6** as currently scoped |
| P09 | missing calendar atom; 2-condition projection then loses selection | 6, then 1 / 2 |

Three conclusions, in order of how much they should change the plan:

1. **Direction 6 (separate vocabulary-generation stage with lineage) is upstream of directions 1–3
   for three of the six missing patterns**, and for P04 it is strictly prerequisite: an eligible
   ancestor chain exists only once the atoms do. The plan's own recommended sequencing —
   "(a) replace only the expansion policy; (b) separately, rerun the baseline after adding a
   calendar atom" — has the two experiments in an order this diagnostic suggests is backwards for
   P02/P04/P09. Running (a) first on the current vocabulary can only move P03 (unsafe) and P09
   (partially).
2. **The vocabulary gap is wider than `ADR-045` recorded.** `ADR-045` identified the missing
   calendar atom. The quantile-grid coarseness is a second, independent axis: two patterns' true
   numeric bounds fall outside the 0.2/0.4/0.6/0.8 grid entirely, and for P04 the relaxation
   *flips the sign of the measured effect*.
3. **`_eligible`'s `harm_per_booking > 0` requirement is a monotonicity assumption the plan does not
   currently name.** It is what kills P04's promising branches and, combined with `min_n`, what puts
   P08 out of reach of every listed direction. Whether that gate should admit interaction-only-
   positive effects is a real design question — and one this document deliberately does not answer,
   because answering it here would be designing a mechanism against known pattern identities, which
   `TASK-069`'s hard rule forbids.

**Counterweight, stated plainly so it is not lost:** §3's counterfactual validation shows that none
of the six missing patterns' oracle branches reach `predictive_association` even if handed straight
to validation. Search-side work on any of them is necessary but demonstrably not sufficient for the
metric `TASK-069` exists to move. Whether the binding constraint is ultimately search, vocabulary,
eligibility, or the validation contract's own statistical power at these effect sizes and sample
sizes is a question this benchmark newly makes askable — and does not settle.

## 7. Reproduction

```sh
uv run python scripts/diagnose_oracle_decomposition.py
uv run python scripts/diagnose_oracle_decomposition.py --skip-counterfactual-validation  # faster
```

Requires a checkout holding `artifacts/blind/task-064-beam-20260822-001.*` (gitignored,
reproducible); override with `--blind-root`. Runtime is dominated by the depth-3 search
(~4 min) and the counterfactual cluster bootstrap.
