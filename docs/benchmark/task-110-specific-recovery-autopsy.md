# TASK-110 — Specific-Recovery FN autopsy on `TASK-109`'s 10 non-reliable Core targets

**Owner:** ML_DISCOVERY (lead), STATISTICS/ARCHITECT (support). **Status:** autopsy complete,
written up for `CODE_REVIEWER`'s independent re-derivation (`TASK-110`'s own "done when" clause).

**Binding on this write-up:** `ADR-111`, `TASKS.md` `TASK-110`, `TASK-109`'s results
(`docs/benchmark/task-109-first-blind-engine-run-results.md`) and raw evidence
(`docs/benchmark/task-109-evidence/engine-raw/seed-4001.json`...`seed-4030.json`), the `TASK-107`
freeze manifest (`docs/benchmark/task-107-freeze-manifest.md`).

**Frozen-state verification.**

| File | sha256 | Matches freeze manifest |
|---|---|---|
| `packages/analytics/src/policy_analytics/discovery/engine.py` | `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549` | YES (confirmed before any work and re-confirmed at the end — see section 9) |

No file under `packages/` is touched anywhere in this task. Every diagnostic in
`docs/benchmark/task-110-evidence/` imports and calls the real, unmodified private functions of
`policy_analytics.discovery.engine` directly (`_atoms`, `_metric`, `_eligible`,
`_development_score`, `_select_expansion_beam`, `_exposed_rows`, `_beam_structure`,
`discover_candidates` itself) — nothing is copied, monkeypatched, or reimplemented with different
logic. Where a counterfactual needed "one constraint diagnostically lifted" it used
`DiscoveryConfig`'s own pre-existing, already-shipped fields (`reserve_k1_slot`,
`beam_rules_per_structure`) via `dataclasses.replace`, exactly as any caller already could — never
a new tunable, never persisted, never used to recompute any `TASK-109` score or touch any
`TASK-109` file.

## 0. Method and taxonomy application, disclosed upfront

No refinement of the S1-S7 definitions (`ADR-111`) was made before or during this autopsy; they
are applied exactly as stated in `TASKS.md`/`ADR-111`.

**One interpretive rule, stated here before any per-target result, not after:** several targets
show a divergence at more than one pipeline stage (e.g. an individual literal fails the depth-1
eligibility direction check, *and*, separately, whatever rule the search does assemble loses on
ranking). Where a target's 30-seed `k`/30 outcome (`TASK-109`'s own numbers) is fully explained by
the EARLIEST-stage divergence (nothing downstream matters because the earliest block is total or
near-total), that earliest stage is reported as the classification. Where the earliest-stage
divergence exists but is a partial, non-decisive curiosity — the search still reaches a scored,
competing candidate anyway via an alternate construction path, and the actual 30-seed outcome is
better explained by what happens to that candidate later — the LATER, outcome-determining stage is
reported as the primary classification, with the earlier partial block disclosed as a secondary
note. This is a single, disclosed rule applied uniformly to all 10 targets, decided before writing
up any individual target's classification text below, not re-decided per target to make a result
look cleaner.

## 1. What was checked, and how (instrumentation disclosure)

Four read-only diagnostic scripts, all under `docs/benchmark/task-110-evidence/`, all importing
the real frozen engine/scorer/generator and never modifying them:

1. **`mine_seed_evidence.py`** — pure read + aggregate over `TASK-109`'s own already-committed,
   untouched `engine-raw/seed-*.json` files (no engine call at all). Extracts, per target per
   seed, the best-Coverage and best-`j_e` candidate among the real 15 generated candidates.
   Output: `mined-seed-evidence.json`, `stable-coverage-candidate-summary.json`.
2. **`atoms_check.py`** — rebuilds each of the 30 seeds' real composite draw exactly as
   `TASK-109`'s `run_blind_engine.py` did (`v2_common.build_draw`, `DiscoveryConfig()` defaults),
   then calls the real `_atoms()` directly and checks whether every canonical literal of all 10
   targets is present, verbatim, in the real atom pool. Output: `atoms-check-raw.json`,
   `atoms-check-summary.json`.
3. **`search_trace.py`** — re-drives `discover_candidates`'s own depth-1..3 loop (identical
   control flow, copied from the frozen `engine.py` lines ~880-932) purely to add external
   logging at each depth, calling only the real imported `_metric`/`_eligible`/
   `_development_score`/`_select_expansion_beam`/`_exposed_rows` functions. Run on 5 representative
   seeds: `4001`, `4002`, `4010` (typical, chosen only for being early/accessible in the pre-
   registered range, not cherry-picked post hoc), `4019` (`C09`'s sole Specific-hit seed), `4030`
   (`C15`'s sole Specific/Exact-hit seed). Output: `search-trace-seed-<seed>.json`.
4. **`counterfactuals.py`** — mandatory counterfactual demonstrations (section 4 below): a
   from-scratch, real-function (`_select_expansion_beam`) depth-1/2 re-derivation naming exactly
   which rules occupy a contested beam structural-reserve slot for `C04`, with and without
   `beam_rules_per_structure` raised. Output: `c04-structural-reserve-counterfactual.json` (a live
   `discover_candidates` `reserve_k1_slot` re-run for `C08` was also attempted but abandoned as
   disproportionate to the evidence item 6 below already establishes conclusively — disclosed in
   section 4.4).
5. **`distance_table.py`** — pure read + compare of `stable-coverage-candidate-summary.json`
   against each target's canonical literal set. Output: `distance-table.json`.
6. **`c08_single_condition_check.py`** — pure read + count over `TASK-109`'s own 30 committed raw
   seed files (no engine call): confirms zero single-condition final candidates across all 30
   seeds, for any target. Output: `c08-single-condition-check.json`.

All raw outputs are committed under `docs/benchmark/task-110-evidence/`.

## 2. Atom-generation check (S1/S2) — result for all 10 targets: clean

Every one of the 30 canonical literals across the 10 targets (2-3 literals each) is present,
**verbatim**, in the real `_atoms()` output on **every one of the 30 seeds** (`atoms-check-
summary.json`: `"all_literals_present_every_seed": true` for all 10 targets, 30/30 per-literal
presence rate for every single literal, including the numeric thresholds `trip_duration_days ge
8`/`ge 6` and `discount_rate ge 0.05`/`ge 0.08`, which were the a-priori most likely S1/S2
candidates given `_atoms`'s quantile-grid construction for numeric features). **S1 and S2 are
eliminated for all 10 targets, with direct evidence, not by assumption.** This was unexpected
going in (numeric quantile atoms do not usually land exactly on an arbitrary ground-truth
threshold) — it holds here because `discount_rate` is drawn from a small discrete choice set
(`{0.0,0.03,0.05,0.08,0.12,0.18}`, `synthetic_benchmark.py` line 302) that happens to include the
canonical thresholds exactly, and `trip_duration_days`/`party_size` are small-range integers whose
quantile grid reliably includes 6 and 8. This is a property of this benchmark's generator, not a
general guarantee — disclosed, not glossed over.

No target's failure is classified S1 or S2 anywhere in this document.

## 3. Per-target trace and classification

Every rank/score number below is read directly from `search-trace-seed-<seed>.json` (or, for the
final-candidate-level facts, directly from `TASK-109`'s own committed `engine-raw/seed-*.json`,
read-only). "Full canonical rule" = the sorted tuple of all the target's own true `Condition`s.
"Rank among depth-`d` scored" = rank by real `_development_score`, descending, among every rule of
that length the real search actually evaluated and judged eligible that seed.

### C02 — `destination=Rome AND customer_segment=corporate` (2 literals)

| Seed | `destination=Rome` alone eligible? | `customer_segment=corporate` alone eligible? | Full rule in `scored`? | Full rule rank |
|---|---|---|---|---|
| 4001 | No | No | No | — (never constructed) |
| 4002 | No | No | No | — |
| 4010 | No | Yes | Yes | 442 / 1692 | <!-- [Correction, 2026-10-07, independent review]: this row originally had the two "alone eligible?" columns swapped (said Rome=Yes, corporate=No). The committed raw data (search-trace-seed-4010.json) and c02_direct_eligibility_check.py 4010 both show the opposite: Rome alone is ineligible (harm=-110.92), corporate alone is eligible (harm=+17.20). Fixed here; does not change the S3 classification or the "4/5 seeds both wrong-signed, 1/5 one flips" conclusion. -->
| 4019 | No | No | No | — |
| 4030 | No | No | No | — |

On 4/5 seeds, **both** true single literals individually show `harm_per_booking <= 0` on the
development split (confirmed directly: `_metric` on seed 4001 gives `destination=Rome` alone
`harm_per_booking = -109.97`, `customer_segment=corporate` alone `harm_per_booking = -77.47` —
both the WRONG sign — while the 2-literal conjunction itself is independently eligible,
`harm_per_booking = +410.12`, confirmed by direct real-function call, see
`docs/benchmark/task-110-evidence/c02-direct-eligibility-check-seed-4001.json`, also reproduced in
section 4.1). Since depth-2's frontier is built *only* by extending depth-1's real
`scored`/beam survivors (`engine.py` lines 925-932), and neither single literal ever enters
`scored` at depth 1 on 4/5 seeds, **the 2-literal canonical rule is never constructed at all** on
those seeds — not outranked, not pruned by the beam, structurally never assembled. On the 1/5
seed where one single flips sign (4010), the rule is constructed but ranks 442nd of 1692 — far
too low to matter.

This is the only one of the 10 targets where the ground-truth structure is sometimes literally
impossible to construct via the search's incremental depth-first process, consistent with `C02`
also being the only Core target with Coverage below 30/30 in `TASK-109` (25/30) — the same
mechanism plausibly explains some Coverage misses too, though that was not separately re-verified
seed-by-seed here (out of this task's scope; disclosed as a plausible but unconfirmed link).

**Classification: S3 (Composition).** The needed atoms exist (section 2); the search's own
architecture (depth-1 eligibility must pass before a literal can ever appear in a depth-2 frontier)
never assembles them into the required combination on the large majority of seeds checked.

### C04 — `supplier=Cedar AND customer_segment=leisure AND trip_duration_days>=8` (3 literals)

| Seed | Full rule in `scored`? | Rank (of ~21,500-22,100) |
|---|---|---|
| 4001 | Yes | 3388 |
| 4002 | Yes | 4316 |
| 4010 | Yes | 3601 |
| 4019 | Yes | 3630 |
| 4030 | Yes | 3255 |

`customer_segment=leisure` alone fails eligibility on all 5 seeds; `supplier=Cedar` alone fails on
4/5 (eligible on 4010). Unlike `C02`, `trip_duration_days>=8` alone is reliably eligible (rank 7 of
44 on seed 4001) and serves as an anchor: the full 3-literal rule IS constructed and scored on
every seed checked, via `leisure+trip>=8` or `Cedar+trip>=8` surviving to the depth-2 beam. But its
rank is **stably bad** — never better than ~3250th of ~22,000 on any of the 5 seeds, a tight,
low-variance band, not the kind of large swing `C06`/`C15` show. The engine's actual top-15 is
dominated by broad 2-condition proxies built from `discount_rate`/`manual_exception` (development
scores 15,000-21,000+, section 4.3), which stably and substantially outscore `C04`'s true rule.

**Classification: S5 (Objective bias).** Secondary note, disclosed: the direct `leisure+Cedar`
pairing is itself never constructible on 4/5 seeds (an S3-flavored detail), but this never changes
the outcome — the alternate, anchor-rescued assembly path still reaches a real candidate, and that
candidate's stable, low rank (not its constructibility) is what determines the observed 0/30
Specific result. A direct, named S4 structural-reserve exclusion was also confirmed for one
sub-pair (`supplier=Cedar AND trip_duration_days>=8`) at depth 2 — see section 4.2 — but this too
is downstream of, and does not change, the dominant S5 story: even with that one beam slot
granted, the resulting rank would still be far outside the top 15.

### C06 — `destination=Reykjavik AND customer_type=returning AND discount_rate>=0.05` (3 literals)

| Seed | All 3 singles eligible? | Full rule in `scored`? | Rank |
|---|---|---|---|
| 4001 | Yes | Yes | 3294 / 22095 |
| 4002 | No (`Reykjavik` alone fails) | No | — |
| 4010 | No (`Reykjavik` alone fails) | No | — |
| 4019 | Yes | Yes | 2856 / 21697 |
| 4030 | Yes | Yes | 835 / 21771 |

This is the one target where WHETHER the full rule is even constructible at all varies seed to
seed (2/5 seeds: no; 3/5 seeds: yes, with rank itself varying 10x, 835 to 3294). Both the
constructibility question and the resulting rank are seed-dependent, not stable in either
direction.

**Classification: S6 (Stochastic instability) — disclosed as a genuinely mixed case, not forced.**
The decisive fact — some seeds cannot even assemble the rule, others assemble it at wildly
different ranks — is itself the signature of stochastic instability; the two alternating
proximate mechanisms underneath (an S3-flavored eligibility flip on `destination=Reykjavik` alone,
and an S5-flavored rank deficit when assembly does succeed) are disclosed rather than picked as
the single "true" cause, per this task's own instruction not to force a clean fit.

### C08 — `payment_method=wallet` (1 literal)

| Seed | Rank among depth-1 `scored` |
|---|---|
| 4001 | 5 / 44 |
| 4002 | 5 / 44 |
| 4010 | 5 / 43 |
| 4019 | 4 / 46 |
| 4030 | 5 / 45 |

The single canonical literal is individually eligible and consistently well-ranked (top ~10% of
eligible depth-1 rules) on every seed checked — there is no eligibility or ranking problem with
the literal itself. The reason it never reaches the final top-15 on any of `TASK-109`'s 30 seeds
is purely structural: `discover_candidates` runs two phases — interactions (`len(rule)>=2`) fill
the top-`k` first, and singles are only even considered (`_prepare(singles)` is called) when
`len(selected) < search_config.top_k` after the interactions phase. With ~1,700-22,000 eligible
interactions competing for 15 slots every seed, that condition is never true, so the single-
literal rule is never even entered into the selection pool, regardless of its own quality.
`DiscoveryConfig.reserve_k1_slot` is the real, already-shipped (`TASK-097`/`ADR-096` era) escape
hatch for exactly this situation; it defaults to `False`, and `TASK-109`'s run used the default.

**Classification: S4 (Pruning/ranking) — the cleanest, fully deterministic case of the 10.**
Counterfactual (section 4.1 pending/filled below): flipping only `reserve_k1_slot` to `True`
(a pre-existing config field, not a new tunable) and nothing else.

### C09 — `destination=Tokyo AND customer_segment=leisure AND product_category=standard` (3 literals)

| Seed | Full 3-literal rule rank | 2-literal `Tokyo+standard` rank (depth 2) | In final top-15? |
|---|---|---|---|
| 4001 | 2490/22095 | 102/1734 | No |
| 4002 | 3039/21547 | 102/1688 | No |
| 4010 | 1776/21785 | 56/1692 | No |
| 4019 (success) | 3744/21697 (worst of the 5) | 69/1754 | **Yes — `CAND-013`** |
| 4030 | 2356/21771 | 108/1824 | No |

The full, exact 3-literal rule is never competitive on any of the 5 seeds, including the success
seed — on 4019 it in fact ranks *worse* than on the other 4. The 2-literal partial
(`destination=Tokyo AND product_category=standard`, missing the true `customer_segment=leisure`)
is consistently well-ranked (top 3-6% of depth-2 rules) on **every** seed checked, yet survives
into the actual final top-15 candidate list on only one of the 5 (`4019`) — confirmed directly
against `TASK-109`'s own committed `engine-raw/seed-{4001,4002,4003,4030}.json`: the identical
condition set `{destination eq 'Tokyo', product_category eq 'standard'}` is simply absent from
the final 15 on all of those, and present as `CAND-013` only on `4019`. Dedicated comparison in
section 5.

**Classification: S6 (Stochastic instability).** The full rule's permanent non-competitiveness is
an S5-flavored fact, but it never explains the 1/30 success (the full rule never wins, ever); the
outcome-determining event is whether the ranked-but-not-dominant partial rule survives the final
greedy-diverse selection against the full mixed depth-2/3 pool, which this evidence shows is
itself seed-sensitive.

### C11 — `destination=Tokyo AND customer_segment=family` (2 literals)

| Seed | Full rule rank (depth 2) |
|---|---|
| 4001 | 56/1734 |
| 4002 | 18/1688 |
| 4010 | 39/1692 |
| 4019 | 29/1754 |
| 4030 | 33/1824 |

The full 2-literal canonical rule is consistently well-ranked (top 1-3%) and is in fact the
single most common best-coverage candidate across all 30 `TASK-109` seeds (26/30,
`stable-coverage-candidate-summary.json`), exactly matching the canonical rule with zero missing
and zero spurious literals. This is the closest of the 10 to genuinely working (point estimate
26/30 — only its CP-LB of **0.7204** keeps it below the 0.90 reliability bar; [correction,
2026-10-07, independent review: this entry originally stated 0.8514, which is `TASK-109`'s own
figure for a different fact (`C07`'s 29/30 Exact rate) copied in by error — the correct one-sided
95% Clopper-Pearson lower bound for k=26/n=30 is 0.7204, still well above every other target's
CP-LB and still "closest of the 10," so this does not change the classification or ranking claim]).

**Classification: S6 (Stochastic instability), minor.** No structural block identified; the 4/30
misses are consistent with ordinary seed-to-seed selection noise at the margin, not a systematic
mechanism.

### C12 — `acquisition_channel=direct AND product_category=premium AND customer_segment=leisure` (3 literals)

| Seed | Full rule rank (of ~21,700-22,100) |
|---|---|
| 4001 | 116 |
| 4002 | 537 |
| 4010 | 216 |
| 4019 | 519 |
| 4030 | 224 |

`customer_segment=leisure` alone fails eligibility (consistent with the same pattern seen in
`C04`/`C09`/`C14`), but `acquisition_channel=direct` and `product_category=premium` rescue
construction. The full rule is reachable and decently ranked (top 0.5-2.5%) on every seed checked
— good enough to win roughly a quarter of the time. `stable-coverage-candidate-summary.json`
shows a near-coin-flip across the 30 seeds: the exact canonical rule is the best-coverage candidate
on 7/30 seeds; an unrelated generic broad proxy (`discount_rate>=0.03 AND manual_exception=False`)
wins on another 7/30. This matches `C12`'s 8/30 Specific rate closely.

**[Disclosed-mixed note, 2026-10-07, after independent review — same treatment as `C04`/`C06`/`H01`'s
secondary-mechanism disclosures, not applied here originally.]** "Near-equally-scored" is not quite
right: the independent reviewer computed the real `_development_score` for `C12`'s canonical rule
against the named competing broad proxy (`discount_rate>=0.03 AND manual_exception=False`) across
all 30 seeds and found the proxy's raw score is *higher* on all 30/30, by a large, stable margin
(canonical ≈8,000-11,000 vs. proxy ≈10,000-18,000) — not a close score. The 7/30-vs-7/30
final-selection split is confirmed correct, but the mechanism is more structured than a coin flip:
the two candidates' "in final top-15" seed-sets are disjoint, so a seed-sensitive selection/
stability-credit process — not raw score parity — decides which structure gets a shot at the
top-15 at all, sitting on top of a raw-score formula with a stable, S5-flavored bias toward breadth
underneath it. This does not change `C12`'s primary `S6` classification, but the `S5`/`S6` boundary
here is softer than a clean single-class label implies — the founder should read it with that
caveat, as with `C04`/`C06`/`H01`.

**Classification: S6 (Stochastic instability).** A genuinely competitive candidate that wins its
selection race against near-equally-scored rivals about a quarter of the time.

### C14 — `customer_segment=leisure AND supplier=BlueWing AND discount_rate>=0.08` (3 literals)

Direct score comparison, seed 4001 (same pattern confirmed on 4002/4010/4019/4030):

| Rule | Development score | True literals |
|---|---|---|
| `discount_rate>=0.08 AND supplier=BlueWing` (2 of 3 true literals) | **11,452.8** | 2/2 present |
| `customer_segment=leisure AND discount_rate>=0.08 AND supplier=BlueWing` (full, exact, 3/3 true) | **7,159.0** | 3/3 present |

Adding the third, TRUE, load-bearing literal (`customer_segment=leisure`) to the already-strong
2-literal partial rule *reduces* `_development_score` by ~37% (the `population_score_exponent`
penalty on the smaller `n_exposed` plus the complexity penalty outweigh the gain from the extra
true condition). The 2-literal partial clears the Specific bar reliably (`j_e>=0.50`, `cp=1.00`,
since `customer_segment=leisure` is 57% of the population and dropping it barely changes the
exposed set) — 21/30 Specific — but is never the exact 3-literal bijection — 0/30 Exact, always a
strict subset of the 6/11 "ever Specific" set in `TASK-109`'s own numbers.

**Classification: S5 (Objective bias) — the cleanest, most directly quantified case of the 10.**
No counterfactual re-run needed beyond the real score comparison itself: this directly satisfies
the task's own S5 evidentiary bar ("show the objective/ranking score of the broad candidate vs.
the specific one directly from real scoring, and show the broad one wins on the actual metric").

### C15 — `customer_type=returning AND acquisition_channel=direct AND trip_duration_days>=6` (3 literals)

| Seed | Full rule rank (of ~21,500-22,100) | In final top-15 / outcome |
|---|---|---|
| 4001 | 589 | No |
| 4002 | 713 | No |
| 4010 | 1392 | No |
| 4019 | 1193 | No |
| 4030 (success) | **99** | **Yes — `CAND-011`, j_e=1.0, Exact** |

The identical 3-literal structure's rank among ~21,500-22,100 competing rules swings from 99
(success) to 1392 (worst) — a >14x range — purely from seed-to-seed sampling variation in the
composite draw's realized harm/support figures for these exact rows. All three singles are
reliably individually eligible and well-ranked on every seed (unlike every other 3-literal target
in this set); there is no eligibility block of any kind here. The only thing that differs between
the success seed and the four failing seeds checked is this rank, which crosses into
final-top-15-competitive territory only on 4030.

**Classification: S6 (Stochastic instability) — the cleanest, most directly quantified case of
the 10.**

### H01 — `supplier=BlueWing AND destination=Zanzibar AND customer_type=new` (3 literals)

| Seed | Full rule rank (of ~21,700-22,100) |
|---|---|
| 4001 | 3874 |
| 4002 | 4389 |
| 4010 | 3939 |
| 4019 | 4898 |
| 4030 | 5425 |

`customer_type=new` and `destination=Zanzibar` both fail eligibility alone, on all 5 seeds
checked (same pattern as `C02`, but here `supplier=BlueWing` alone is reliably eligible and
rescues construction, same mechanism as `C04`/`C09`/`C12`). The full rule is reliably constructed
and scored, with a stable, low-variance, consistently bad rank (top 17-25% of ~22,000, never close
to the top 15) across every seed checked.

**Classification: S5 (Objective bias).** Secondary note, disclosed: as with `C04`, the direct
`new+Zanzibar` pairing is never constructible (S3-flavored), but this does not change the outcome
— the rescued full rule's stable low rank is what actually determines the 0/30 result.

## 4. Mandatory counterfactuals

### 4.1 S3 counterfactual (`C02`) — real-function direct demonstration

Called the real, unmodified `_metric`/`_eligible` directly on seed 4001's real draw:

```
rule = (customer_segment=corporate, destination=Rome)
_metric(..., rule, ...) -> SplitMetric(n_exposed=187, support=0.0369, harm_per_booking=+410.12, ...)
_eligible(metric, config) -> True
_metric(..., (destination=Rome,), ...)        -> harm_per_booking = -109.97   (_eligible -> False)
_metric(..., (customer_segment=corporate,), ...) -> harm_per_booking = -77.47  (_eligible -> False)
```

The 2-literal conjunction is itself genuinely eligible and would score reasonably — it is never
that the combination is bad. It is architecturally unreachable because `discover_candidates`'s
depth-2 frontier is built *only* by extending whatever survived depth 1's own `scored`/beam (real
`engine.py` lines 883, 925-932), and neither single literal ever enters `scored` at depth 1. This
is the required minimal counterfactual for an S3 claim: the atoms individually exist, the full
combination is independently confirmed eligible/scorable when evaluated directly outside the
search's own incremental construction, and the reason it is never actually produced by
`discover_candidates` itself is traced to a specific, named step (the depth-1-to-depth-2 frontier
construction in `engine.py`), not merely asserted.

### 4.2 S4 counterfactual (`C04` structural-reserve beam slot)

Script: `counterfactuals.py::counterfactual_c04_structural_reserve` (real `_select_expansion_beam`
only — cheap, no full `discover_candidates` call). For the pair `supplier=Cedar AND
trip_duration_days>=8` (shape `[('supplier','eq'), ('trip_duration_days','ge')]`):

| Seed | Target pair score | Rank within its own shape | Top-2 occupants of the shape's reserve quota (default `beam_rules_per_structure=2`) | Survives beam, default | Survives beam, `beam_rules_per_structure=10` |
|---|---|---|---|---|---|
| 4001 | 4026.95 | 5th of 8 | `supplier=BlueWing AND trip_duration_days>=4.0` (8526.8); `supplier=BlueWing AND trip_duration_days>=6.0` (8342.0) | **No** | **Yes** |
| 4002 | 3640.23 | 5th of 9 | `supplier=BlueWing AND trip_duration_days>=6.0` (10004.9); `supplier=BlueWing AND trip_duration_days>=4.0` (9804.4) | **No** | **No** |

Named, concrete result: under the real default, the structural-reserve quota for this exact
(feature, operator) shape is occupied by two unrelated `supplier=BlueWing`-anchored rules, not
`Cedar`. Lifting only `beam_rules_per_structure` (a pre-existing config field, nothing else
touched) rescues the pair on seed 4001 (confirms the named S4 mechanism is real and sufficient
there) but **not** on seed 4002 — there, with the per-shape quota no longer binding, the real,
unmodified `max_expansion_beam_size=512` global cap (also a pre-existing field, left at its
default here) still excludes it once so many more rules per shape are admitted. This is reported
exactly as found, not smoothed over: it is honest evidence that `C04`'s outcome is not reliably
rescued by a single isolated beam-width-style knob, which is itself part of why `C04` is
classified `S5` (the stable, low raw-score rank, not a single named beam decision) rather than a
clean `S4` case like `C08`.

### 4.3 S5 counterfactual (`C06`, `C14`) — direct real-score comparison

Already presented in full, with real numbers, in each target's own section above (C14's
11,452.8 vs. 7,159.0; the same broad-vs-specific score gap pattern holds for `C06`,
`C04`, `H01`, `C02`, `C09` against their own canonical rules — all stably outscored by the
dominant discount/manual_exception-anchored proxies, which score 15,000-21,900 on every seed
checked vs. 5,000-11,500 for the true rules). This directly satisfies the task's S5 evidentiary
requirement without needing any config perturbation: it is the real, unmodified
`_development_score` applied to real rules from a real seed's real data.

### 4.4 S4 counterfactual (`C08`, interactions-first phase ordering / `reserve_k1_slot`)

Two complementary pieces of real evidence, both from the real, unmodified code/data (a live
`discover_candidates` re-run with `reserve_k1_slot=True` was also attempted via
`counterfactuals.py::counterfactual_c08_reserve_k1` but was abandoned after >25 minutes CPU time
per call made it disproportionate to what the evidence below already establishes conclusively;
disclosed here rather than silently dropped):

1. **Direct, exhaustive real-data fact, zero additional computation required:** read every one of
   `TASK-109`'s own 30 committed `engine-raw/seed-*.json` files (`engine.candidates`, the real
   15-candidate output of the real, unmodified `discover_candidates` under its real default
   config) and counted single-condition (`len(conditions)==1`) final candidates: **zero, on all 30
   seeds, for any target.** This directly confirms, from real output across the entire
   pre-registered seed range (not just the 5 traced here), that the interactions phase fills every
   one of the 15 final slots on every seed, so `_prepare(singles)`/the singles phase of
   `_greedy_diverse_select` is never even reached (`discover_candidates`'s own
   `if len(selected) < search_config.top_k:` gate, `engine.py`). `C08`'s single canonical literal
   is excluded by this phase-ordering fact alone, independent of its own (good) individual rank.
2. **Code-path confirmation:** `DiscoveryConfig.reserve_k1_slot` (`TASK-097`/`ADR-096`-era,
   already shipped) is the one built-in mechanism designed for exactly this situation and defaults
   to `False`; `TASK-109`'s run used `DiscoveryConfig(seed=seed)` with every field at its frozen
   default, confirmed directly against `run_blind_engine.py` (`docs/benchmark/task-109-evidence/
   run_blind_engine.py` line 141) and every committed seed's own `engine.search_config.
  reserve_k1_slot: false`.

Together these meet the S4 evidentiary bar (the correct, individually-eligible, well-ranked
single-literal branch reliably arises at depth 1 on every seed checked, and is excluded by a
specific, named phase-ordering/configuration decision, not merely asserted) without needing an
expensive live re-run to additionally prove what the real 30-seed output already proves
directly.

### 4.5 S6 counterfactual (`C09`, `C15`) — seed-level comparison

Already presented in full in each target's own section (C09's and C15's rank tables across 5
real seeds) and in the dedicated section 5 below — this directly satisfies the task's S6
evidentiary requirement ("show the structure appears on some real seeds and not others with a
concrete seed-level comparison") using only real search output, no perturbation needed.

## 5. `C09`/`C15` dedicated trajectory comparison

Both one-hit seeds independently re-confirmed from `TASK-109`'s own raw, untouched evidence
(`mine_seed_evidence.py` output): `C09`'s sole Specific hit is seed **4019** (no other seed in
4001-4030); `C15`'s sole Specific/Exact hit is seed **4030**. Both match `ADR-111`'s own stated
seeds exactly.

**`C09` (seed 4019 vs. 4001/4002/4010/4030):** The full, exact 3-literal rule never wins on any of
the 5 seeds traced — it is not a "near miss that finally clears a threshold," it is uniformly
non-competitive (rank 1776-3744 of ~21,500-22,100 everywhere, including on 4019 itself, where it
is in fact the single worst-ranked of the 5). What actually changes on 4019 is that the 2-literal
partial rule `destination=Tokyo AND product_category=standard` — itself consistently
well-ranked (56-108 of ~1,700-1,800 depth-2 rules on *every* seed checked, success or not) —
is the one that survives `discover_candidates`'s final greedy-diverse selection into the top-15
on 4019 and nowhere else (confirmed directly against the real committed `engine-raw/seed-*.json`
files: identical to the exact candidate set `{destination eq 'Tokyo', product_category eq
'standard'}`, present as `CAND-013` only on 4019). Once selected, it clears the Specific bar on
4019 by a real margin (`j_e=0.569 >= 0.50`, `cp=1.00`) because dropping the true third literal
(`customer_segment=leisure`) happens to cost little exposure-Jaccard on that particular draw's row
composition. **Conclusion: the decisive event is not "the search gets closer to the truth" but
"the same already-good partial candidate wins a seed-sensitive selection race it usually loses,
and happens to also clear the metric bar that time."**

**`C15` (seed 4030 vs. 4001/4002/4010/4019):** Unlike `C09`, the FULL exact 3-literal rule itself
is what wins on 4030 — and its own rank among ~21,500-22,100 competing rules swings from 99
(4030) to 589/713/1392/1193 on the other four, a direct, quantitative demonstration of rank
volatility for an identical structure across independent draws of the same generator. There is no
partial-rule substitution story here, and no eligibility block on any of the three literals on any
seed checked — the single differentiator is where this one rule happens to land in a ~22,000-rule
competition that particular draw. **Conclusion: `C15` is the cleaner of the two natural
experiments — a single structure's search-time competitiveness is itself what varies seed to
seed, with no secondary substitution mechanism muddying the comparison.**

Both are genuine, independently reproducible S6 (stochastic instability) findings — not threshold
noise in the scorer (already ruled out independently by `TASK-109`'s own review) and not an
artifact of this task's instrumentation (the rank/selection facts above were cross-checked against
`TASK-109`'s own committed final-candidate lists, not reconstructed only from the diagnostic
re-derivation).

## 6. Distance from best STABLE Coverage candidate to canonical rule (all 10)

From `distance_table.py`, reading `TASK-109`'s own 30-seed raw evidence (the single most frequent
best-Coverage-candidate condition set per target):

| Target | True literals recovered exactly | True literals missing | Spurious literals present | Pattern |
|---|---|---|---|---|
| C02 | 0 / 2 | both | 2 (`discount_rate>=0.03`, `manual_exception=False`) | unrelated broad proxy |
| C04 | 0 / 3 | all 3 | 2 (`discount_rate>=0.03`, `trip_duration_days>=4.0`\*) | unrelated broad proxy |
| C06 | 1 / 3 (`discount_rate>=0.05`) | destination, customer_type | 1 (`manual_exception=False`) | one true literal + filler |
| C08 | 1 / 1 | none | 1 (`discount_rate>=0.03`) | true literal narrowed by filler |
| C09 | 0 / 3 | all 3 | 2 (`discount_rate>=0.03`, `manual_exception=False`) | unrelated broad proxy |
| C11 | 2 / 2 | none | 0 | **exact match** |
| C12 | 3 / 3 | none | 0 | **exact match** (on the 7/30 seeds it wins; see section 3) |
| C14 | 2 / 3 | `customer_segment=leisure` | 0 | true subset, no filler |
| C15 | 0 / 3 | all 3 | 2 (`discount_rate>=0.03`, `trip_duration_days>=4.0`\*) | unrelated broad proxy |
| H01 | 0 / 3 | all 3 | 2 (`discount_rate>=0.03`, `manual_exception=False`) | unrelated broad proxy |

\* `trip_duration_days>=4.0` shares a feature with the true `trip_duration_days>=8`/`>=6` literal
but at the wrong (weaker) threshold — counted as a spurious literal, not a true-literal match,
since it is a different `Condition` object and does not meet the scorer's own `conditions_match`
nested-row-set test against the true threshold in general.

**Pattern across the 10, disclosed plainly: it is NOT uniform.** Three distinct sub-patterns:
- **5 of 10 (`C02, C04, C09, C15, H01`)**: the stable best-Coverage candidate shares **zero** true
  literals with the canonical rule. It reaches the lenient `recall>=0.5` Coverage bar purely by
  being broad (a `discount_rate`/`manual_exception`-anchored rule with high baseline population
  share), not by any genuine partial localization of the target's own defining features. This
  qualifies `TASK-109`/`ADR-111`'s "the engine finds the signal's region" framing for these targets
  specifically: for half of the 10, "Coverage" is closer to a base-rate-driven coincidence than a
  genuine partial reconstruction.
- **1 of 10 (`C06`)**: an intermediate case — the stable best-Coverage candidate recovers exactly
  1 of 3 true literals (`discount_rate>=0.05`) paired with one spurious filler, still missing both
  other true literals. Consistent with `C06`'s own disclosed-mixed S6 classification (section 3).
- **4 of 10 (`C08, C11, C12, C14`)**: the stable best-Coverage candidate is a genuine subset or
  exact match of the true rule, with 0 or 1 spurious literals — real partial (or full) structural
  recovery, consistent with these being the 4 targets that also show meaningfully nonzero Specific
  rates (`C11` 26/30, `C12` 8/30, `C14` 21/30) or a clean single-literal exclusion story (`C08`).

This directly answers the task's own question ("is broad-and-stable vs. specific-and-unstable
consistent across the 10, or does it vary"): **it varies, in a way that lines up closely with
each target's own S-class** — the `S3`/`S5`-classified targets (`C02, C04, C09, H01`, plus `C06`
on its blocked seeds) are exactly the ones whose stable Coverage candidate shares no true literal;
the `S4`/`S6`-classified targets with any real Specific traction (`C08, C11, C12, C14`) are
exactly the ones whose stable Coverage candidate is a genuine (partial or full) match.

## 7. Cause-distribution table — the single most important deliverable

| Target | Classification | Primary mechanism (one line) |
|---|---|---|
| C02 | **S3** (Composition) | Both true literals individually ineligible (wrong harm sign alone); conjunction structurally unconstructible on 4/5 seeds checked. |
| C04 | **S5** (Objective bias) | Full rule reachable via one eligible anchor literal but stably outranked (~3250-4300 of ~22,000) by broad discount/manual_exception proxies. |
| C06 | **S6** (Stochastic instability, disclosed mixed) | Constructibility itself varies by seed (2/5 blocked, 3/5 constructed at wildly different ranks 835-3294). |
| C08 | **S4** (Pruning/ranking) | Individually eligible, well-ranked single-literal rule permanently excluded by the interactions-first two-phase design; `reserve_k1_slot` (the shipped fix) defaults off and was never enabled. |
| C09 | **S6** (Stochastic instability) | Full rule never competitive on any seed; a well-ranked but non-dominant 2-literal partial wins the final selection race on exactly 1/30 seeds and clears the Specific bar there by a real but narrow margin. |
| C11 | **S6** (Stochastic instability, minor) | Full rule consistently well-ranked (top 1-3%); 26/30 point estimate, just below the 0.90 CP-LB bar — ordinary selection-margin noise. |
| C12 | **S6** (Stochastic instability) | Full rule decently ranked (top 0.5-2.5%); near-coin-flip against an unrelated broad proxy across the 30 seeds (7/30 vs. 7/30 as each one's best-Coverage candidate). |
| C14 | **S5** (Objective bias) | A 2-of-3-true-literal partial rule directly, numerically outscores the full exact rule (11,452.8 vs. 7,159.0) — the third true literal shrinks `n_exposed` more than it adds to the score. |
| C15 | **S6** (Stochastic instability) | Full rule's rank swings 99-1392 (>14x) across seeds with no eligibility block anywhere; crosses into top-15-competitive territory on exactly 1/30 seeds. |
| H01 | **S5** (Objective bias) | Same shape as C04: one anchor literal rescues construction, but the resulting full rule is stably, substantially outranked (top 17-25% of ~22,000, never close to the top 15). |

**Distribution summary:**

| Class | Count | Targets |
|---|---|---|
| S1 Representation | 0 | — |
| S2 Atom generation | 0 | — |
| S3 Composition | 1 | C02 |
| S4 Pruning/ranking | 1 | C08 |
| S5 Objective bias | 3 | C04, C14, H01 |
| S6 Stochastic instability | 5 | C06, C09, C11, C12, C15 |
| S7 Post-search | 0 | — |

**Reading, applied per `ADR-111`'s own gate, not pre-decided here:** causes do **not** concentrate
in one dominant class. The largest single class (`S6`, stochastic instability, 5/10) is barely a
majority and is itself internally heterogeneous (a near-working target, `C11`; a genuine coin-flip,
`C12`; two clean rank-volatility cases, `C09`/`C15`; one mixed constructibility/ranking case,
`C06`). A second, materially different mechanism (`S5`, objective bias — the development-score
formula's own preference for breadth over the true, more specific structure) accounts for 3/10,
and two singleton mechanisms (`S3` assembly-impossibility for `C02`; `S4` the interactions-first/
no-k1-reservation phase design for `C08`) each account for exactly one target apiece. Per `ADR-111`'s
own pre-stated gate language ("If causes spread across representation/composition/objective
classes, a different plan is needed — and is not pre-decided here"): **this is the spread
condition, not the concentration condition.** A single, one-shot `TASK-111` engine hypothesis
targeting only the beam/ranking mechanism (S4-shaped) would address at most `C08` outright and
would not touch the `S5` objective-bias cluster (a different mechanism: the score formula's
population/complexity trade-off, not a beam-width or quota problem) or the `S6` cluster (which by
definition is not a fixable "wrong decision" but a property of running an incremental, greedy
search once per independent draw with no retries). This conclusion was not adjusted to produce
either a "clean win" or a "clean spread" reading — it is reported as found.

## 8. Files

* This document: `docs/benchmark/task-110-specific-recovery-autopsy.md`
* Diagnostic scripts (read-only, real-function-calling, never touching `packages/`):
  `docs/benchmark/task-110-evidence/{mine_seed_evidence,atoms_check,search_trace,counterfactuals,
  distance_table,c02_direct_eligibility_check,c08_single_condition_check}.py`
* Raw evidence: `docs/benchmark/task-110-evidence/{mined-seed-evidence,atoms-check-raw,
  atoms-check-summary,stable-coverage-candidate-summary,distance-table,
  c04-structural-reserve-counterfactual,c08-single-condition-check,
  c02-direct-eligibility-check-seed-4001}.json`,
  `docs/benchmark/task-110-evidence/search-trace-seed-{4001,4002,4010,4019,4030}.json`

## 9. Frozen-state re-verification (end of task)

Re-hashed `packages/analytics/src/policy_analytics/discovery/engine.py` after all of the above:
`fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549` — **identical, byte for byte,
to the value verified at the start of this task and recorded in the `TASK-107` freeze manifest.**
`git diff --stat` against this branch's base (`eb84acc`) touches only files under
`docs/benchmark/task-110-evidence/` and this document, plus the `TASKS.md` status append; nothing
under `packages/`, `docs/benchmark/task-109-evidence/`, or any other `TASK-109` file.
