# TASK-068 — `ecommerce` domain-selection preregistration

**Owner:** STATISTICS (preregistration/evaluation authority), with ML_DISCOVERY as issuing coordinator
**Recorded:** 2026-08-23
**Status:** PRE-REGISTERED. No `ecommerce` run has been issued; no `ecommerce`
`hidden_ground_truth.json` has been opened by any recorded session. This document must not be edited
after either preregistered run is issued — only appended to, under "Post-run record".

This is the separate domain-selection preregistration that `ADR-055` step 3, `ADR-056`, `ADR-057`,
and `ADR-059` each explicitly declined to perform, and that `TASK-068`'s own preregistered-test
step 4 requires before any official run begins. `ADR-059` approved only the implementation
contract; it selected no domain and authorized no run. This document selects the domain and fixes
every parameter and criterion. It does **not** by itself authorize issuance — see
"§8 Readiness: unmet preconditions", which records five concrete blockers found while verifying
readiness, three of which are owned by other roles.

---

## 1. Pre-registration condition, verified before writing this document

Checked directly, not taken from any narrative:

- **`ecommerce`'s hidden ground truth has never been opened.** `grep` across the entire working
  tree for any co-occurrence of `ecommerce` with `hidden_ground_truth` returns zero matches;
  `DECISIONS.md` carries no `ADR-048`-equivalent disclosure for this or any domain other than
  `b2b_sales`; `ADR-055`'s own eligibility statement (`ecommerce`/`saas`/`insurance`/
  `manufacturing`/`healthcare` "remain genuinely unopened and eligible") is consistent with that
  check. No file in this change opens it either.
- **The mechanism under test exists and is Code-Reviewer-approved.** Read directly in
  `packages/analytics/src/policy_analytics/discovery/engine.py`:
  `DiscoveryConfig.max_feature_identity_fraction` (default `1.0`), `_apply_feature_identity_cap`
  (a post-filter over `_greedy_diverse_select`'s unmodified output),
  `DISCOVERY_METHOD_VERSION = "discovery-engine-v0.6.0"`, `_IDENTITY_CAP_OVERSELECT_MULTIPLIER = 5`.
  Approval: `ADR-059`/`HANDOFF-070`.
- **There is no non-`1.0` default.** The implementation ships the cap disabled, so the enabled-mode
  fraction is a genuine preregistration decision and is fixed in §4 below, on domain-neutral
  grounds only.
- **No `TASK-068` run of any kind exists.** `/tmp/policy-blind-runs` contains only the five
  `TASK-060`/`TASK-064`/`TASK-065`-era runs; `artifacts/blind/` carries no `task-068-*` artifact.

### 1a. Disclosed pre-existing exposure of `ecommerce` *design* content (not ground truth)

Stated plainly rather than discovered later. `ecommerce`'s pattern/trap **identities and several of
their generative mechanisms** are already recorded in shared, version-controlled repository files —
`memory/HANDOFFS.md` (`HANDOFF-053`, including a per-trap raw-marginal table and pattern `E06`'s
literal condition set), `TASKS.md`'s `TASK-061` progress bullets, and
`docs/benchmark/multi-domain-benchmarks.md`. This is **not** hidden-ground-truth access: none of it
comes from `synthetic_data_domains/ecommerce/comparable/evaluation/hidden_ground_truth.json`, it
predates this task by three days, it is the same kind of partial public disclosure travel's own
`P01`–`P09` already carry in `docs/benchmark/task-029-benchmark-report-v1.md`, and much of it is
now stale (the traps were rewired when `HANDOFF-053` was resolved, so the tabulated mechanisms no
longer describe the shipped generator).

Consequences fixed here rather than judged later:

1. It does **not** disqualify `ecommerce` under `ADR-055`'s selection rule, and the rule is not
   changed to avoid it — deviating from a preregistered lexicographic rule because of what a
   session happens to have read would itself be the post-hoc selection this discipline forbids.
2. It does **not** reach the blind actor: the isolated workspace contains only the six public
   analytical partitions plus allowlisted discovery code (`blind/allowlist.yaml`,
   `tools/blind_agent/core.py:DATASET_FILES`), never `memory/`, `docs/`, `TASKS.md`, or any
   dataset-local generator/evaluation path.
3. Every parameter in §3–§4 below is fixed **in this document, in advance**, and none is derived
   from any `ecommerce` (or `b2b_sales`) pattern, trap, feature name, or effect size.

---

## 2. Domain lock

| Item | Value |
|---|---|
| Domain | `ecommerce` |
| Variant | `comparable` (every pattern and trap active, unscaled) |
| Blind dataset selector (to be registered) | `ecommerce/comparable` |
| Analytical root | `synthetic_data_domains/ecommerce/analytical/ecommerce-analytical-v1.0.0` |
| Hidden ground truth (opened only in Phase C) | `synthetic_data_domains/ecommerce/comparable/evaluation/hidden_ground_truth.json` |

**Selection rule (unchanged, not re-derived):** lexicographically first `domain_id` among the
still-unopened `TASK-061` domains — the same rule `TASK-065` used to pick `b2b_sales`, restated in
`ADR-055`. `ecommerce` < `healthcare` < `insurance` < `manufacturing` < `saas`. The `comparable`
variant is fixed for the same reason `TASK-065` fixed it: it is the single richest per-domain
source and the only variant with a built analytical dataset, matching travel's canonical run.

**This spends one of five remaining untouched domains** (`ADR-054`), and it may be spent exactly
once. If either preregistered run below fails for infrastructure reasons before candidates are
frozen, the domain is **not** re-spent by silently reissuing: a failed run ID is permanently closed
(`blind/README.md`), and re-issuance under the same preregistration is permitted only while no
`ecommerce` ground truth has been opened by any actor.

---

## 3. Baseline run (fixed)

| Item | Value |
|---|---|
| Purpose | Same-domain reference for every comparison in §5 |
| Method | `discovery-engine-v0.6.0` with `max_feature_identity_fraction = 1.0` (cap **disabled**) |
| Run ID stem | `task-068-ecommerce-baseline-<YYYYMMDD>-001` |
| Issuance | `make blind-issue RUN=<id> BLIND_DATASET=ecommerce/comparable` (agent `deterministic`, network `none`, seed `1729`) |

**Why "v0.6.0 with the cap disabled" and not literally `v0.5.0` code.** `TASK-068`'s own text and
`ADR-055` both name a "same-domain `discovery-engine-v0.5.0` baseline". Executing that literally is
impossible from the current checkout without a code revert: `scripts/run_discovery.py` refuses to
run unless the signed `discovery_method_version` equals the implementation's own
`DISCOVERY_METHOD_VERSION`, which is now `v0.6.0`. The substitution is exact, not approximate, and
is not a weakening of the baseline:

- Structurally, `max_feature_identity_fraction = 1.0` makes `max_per_feature == top_k`, which no
  feature's tally can reach before the final list already holds `top_k` entries — the cap is
  unreachable by construction, and `_apply_feature_identity_cap` is not even called
  (`identity_cap_active` is false), so `_greedy_diverse_select` receives its ordinary `top_k`.
- `ADR-059` independently re-verified this three ways (implicit default, explicit `1.0`, and a
  direct unmodified `_greedy_diverse_select` call bypassing all `TASK-068` code), plus a real
  regression run.

Recorded here as a preregistered substitution so it is a fixed decision, not a later
rationalization. A reviewer who rejects the substitution must say so **before** issuance; after
issuance this document is closed to edits.

---

## 4. Test run (fixed)

| Item | Value |
|---|---|
| Purpose | The single falsifiable test of `TASK-068`'s mechanism |
| Method | `discovery-engine-v0.6.0` with `max_feature_identity_fraction = 0.34` (cap **enabled**) |
| Effective constraint | `max_per_feature = max(1, floor(0.34 × 15)) = 5` of 15 committed slots per feature identity |
| Run ID stem | `task-068-ecommerce-cap-<YYYYMMDD>-001` |
| Issuance | identical to §3 except for the cap parameter |

### 4a. Why `0.34`, on domain-neutral grounds only

The implementation ships no enabled default, so this value is chosen here. The reasoning uses no
`ecommerce` and no `b2b_sales` content of any kind:

1. **It is not a new number.** `0.34` is the exact constant already fixed, truth-free and before any
   domain existed, in the falsification fixture `ADR-056` required and `ADR-057`/`ADR-059`
   approved (`tests/analytics/test_discovery_engine.py`, where at that fixture's `top_k = 6` it
   yields `floor(0.34 × 6) = 2`). Reusing a constant that was fixed under review, in a
   domain-free setting, is strictly more defensible than inventing a fresh one now that a domain
   has been named.
2. **"One third" is the natural statement of the failure mode.** The defect being tested is a
   single feature identity claiming the entire committed set. One third is the coarsest bound that
   still forces genuine plurality; at `top_k = 15` the float arithmetic lands on `5.1`, so
   `floor` gives exactly 5 — one third of the set, with no dependence on rounding luck.
   (`0.3333` would give 4 via `int(4.9995)`; `0.34` is chosen partly because it is numerically
   unambiguous, which matters for a preregistered value.)
3. **Its structural guarantee is stated in advance, not overclaimed.** Every rule contributes at
   least one feature to the tally and no feature may be used more than 5 times, so a full
   15-candidate set must represent **at least 3 distinct feature identities** in the absolute worst
   case (all singletons), and more whenever rules carry 2–3 conditions, which is the normal case
   at `max_conditions = 3`. That worst-case floor of 3 is the honest guarantee; anything above it
   is an empirical result, not a promise.

**Alternatives considered and rejected, before seeing any result:**

- `0.5` → `max_per_feature = 7`: a single identity could still hold nearly half the committed set.
  Too weak to falsify anything — a null result would be uninformative about the mechanism.
- `0.25` → `max_per_feature = 3`: with the fixed `5×` overselect (`_IDENTITY_CAP_OVERSELECT_MULTIPLIER`),
  a pool whose eligible rules concentrate on few features could fail to fill `top_k` and land under
  10 candidates, which `scripts/run_discovery.py` emits as `status=INSUFFICIENT_CANDIDATES`. That
  converts a methodology test into an infrastructure failure and wastes the domain.

### 4b. Everything else is held fixed

Both runs use identical inputs and identical values for every other knob — the committed defaults,
none touched by `TASK-068` (`ADR-059` grep-verified all ten `TASK-060`/`TASK-064` knobs at zero
hits):

`seed=1729`, `min_support=0.01`, `max_support=0.4`, `min_n=40`, `max_conditions=3`,
`beam_width=80`, `beam_rules_per_structure=2`, `max_expansion_beam_size=512`, `top_k=15`,
`numeric_quantiles=(0.2, 0.4, 0.6, 0.8)`, `max_categorical_levels=12`,
`max_candidate_jaccard=0.85`, `max_candidates_per_atom=5`, `population_score_exponent=0.5`,
`diversity_discount_weight=0.5`, `min_diversity_relevance_ratio=0.5`, `stability_credit_weight=0.5`,
`relevance_floor_percentile=0.75`.

**`max_feature_identity_fraction` is the only difference between the two runs.** If any other input
differs, both runs are void and the comparison is not made.

---

## 5. Success and kill criteria — verbatim from `TASK-068`

Reproduced exactly as written in `TASKS.md`'s `TASK-068` entry, not paraphrased:

> - **Success:** economic-weighted recall (or unique scoreable-pattern candidate-match recall) is
>   strictly higher than the same-domain baseline, with Top-10 precision, direction accuracy, and
>   trap rejection not degraded relative to that baseline.
> - **Kill:** any of — the structural check fails; a trap is promoted that the baseline did not
>   promote; Top-10 precision or direction accuracy degrades relative to the baseline; or the
>   structural check passes but both recall metrics are unchanged or worse than the baseline. On any
>   kill outcome, this mechanism is not iterated a second time on the same lever (the same
>   two-strikes discipline `ADR-041`/`ADR-049` already apply elsewhere) — record the honest negative
>   result; a genuinely new mechanism is required for any further attempt.

And the hard gate that runs first, also verbatim:

> 2. **Structural check, decided truth-free:** the new mechanism must increase the count of
>    distinct anchor-feature identities in the committed Top-K relative to the same-domain
>    `discovery-engine-v0.5.0` baseline. Failing this is itself a kill — the remaining criteria are
>    not evaluated.

### 5a. How each term is computed (fixed now, so it cannot be chosen later)

- **Structural check** — for each run, take the frozen `candidates.json`, collect
  `{condition.feature for condition in candidate.conditions}` over all 15 candidates, and count the
  distinct feature identities. The test run's count must be **strictly greater** than the
  baseline's. Computed from public frozen candidate bytes only; **no ground truth is opened to
  decide it**, and it is decided before either `TASK-028` runs. If it fails, this is a kill and
  §5's remaining criteria are not evaluated — but `TASK-019`/`TASK-028` are still run and reported
  for both runs, because leaving a spent domain unscored would waste it.
- **Top-10 precision, economic-weighted recall, unique scoreable-pattern candidate-match recall,
  direction accuracy, trap rejection, leakage violations, economic-impact error** — exactly as
  `scripts/evaluate_benchmark.py` computes them today, with its domain-generic
  trap-identity/scoreable-pattern derivation (`HANDOFF-065`, verified to reproduce travel's
  historical values byte-for-byte). **No metric definition, threshold, or matching rule may be
  changed between this document and the determination.**
- **"Not degraded"** — strictly: `test >= baseline` on Top-10 precision, on direction accuracy, and
  on trap rejection count. Any decrease is a degradation, however small; there is no tolerance band.
- **"Not estimable"** — if direction accuracy has a zero eligible denominator in **both** runs (the
  `TASK-065` outcome), it is reported as not estimable and cannot count as a degradation. If it is
  estimable in the baseline and not in the test run, that **is** a degradation, since the test run
  lost the eligible denominator the baseline had.

---

## 6. Decision-gate bands: retained unmodified

`docs/benchmark/decision-gate.md`'s three hard disqualifiers and its graded bands are retained
**exactly as written, unmodified**, and are not restated with different numbers here:

1. any leakage violation → FAILED;
2. any confounding trap promoted to `SHADOW_POLICY`/`HIGH_CONFIDENCE` → FAILED;
3. any validated finding above the materiality threshold with the wrong effect direction → FAILED.

Graded bands (Top-K precision; economic-weighted recall; trap rejection; leakage; direction
accuracy; impact error) apply as written, with the overall verdict the weakest graded band unless a
disqualifier fires.

**The one thing that is domain-substituted, and nothing else:** that document's "Fixed
denominators" section names travel's `P01`–`P09`/`T01`–`T05` and travel's excluded `P05`/`P07`.
For `ecommerce`, the scoreable-pattern set and trap set are whatever
`scripts/evaluate_benchmark.py` derives generically from the loaded ground truth at run time —
the same substitution `TASK-065` made, no per-domain hand-picking, and `K = 10` is unchanged. The
bands, the thresholds, and the disqualifiers are untouched.

`docs/benchmark/decision-gate.md` itself is **not edited** by this task. Its standing travel
`PROMISING` verdict (`ADR-025`) is anchored to a different run and is unaffected by any `ecommerce`
result, in either direction.

---

## 7. Custody protocol (`ADR-051`-shaped, as `ADR-055` step 3 requires)

The only authorized order, per run, with no step reordered or merged:

1. **Readiness** — every item in §8 resolved and recorded; `make blind-rehearsal
   BLIND_DATASET=ecommerce/comparable` prints `BLIND_REHEARSAL_VALID` against the pinned image
   digest; an `ADR-052`-style evaluator slot for this task is approved **before** issuance.
2. **Issue / verify** — `make blind-issue` then `make blind-verify`, both with
   `BLIND_DATASET=ecommerce/comparable`. The preregistered run ID must not already exist in
   `BLIND_RUNS_ROOT` or `artifacts/blind/`.
3. **Launch** — `make blind-shell`, deterministic actor, network `none`, fresh container, no
   evaluator key and no provider credential passed.
4. **Freeze** — `make blind-freeze`; verify frozen hashes, read-only artifacts, `state=FROZEN`.
5. **Commit** — `scripts/commit_blind_candidates.py` produces the signed receipt, created by the
   trusted evaluation coordinator (ARCHITECT) using the evaluator-owned key.
6. **Independent custody verification** — an uncontaminated CODE_REVIEWER verifies receipt
   signature, candidate SHA-256, bundle/manifest binding, and freeze status, and records the
   verdict **before** any ground truth is disclosed to anyone.
7. **Validation** — a separately instantiated STATISTICS/evaluator actor, bound to the approved
   slot only after step 5, runs `TASK-019`; the report is frozen `0444`, hashed, and confirmed
   `hidden_ground_truth_opened=false`.
8. **Evaluation** — only then does the same evaluator run `TASK-028` against exactly the
   preregistered `ecommerce/comparable` ground truth.
9. **Determination** — §5's criteria applied to the two frozen artifact pairs, recorded in
   `TASK-068`'s `TASKS.md` entry with both runs' frozen paths and SHA-256s.

**Sequencing between the two runs — fixed here, and deliberately stronger than a plain
run-then-run order.** Both runs complete steps 2–6 (issued, launched, frozen, signed, custody-
verified) **before any `TASK-028` opens `ecommerce` ground truth**. Order:

> baseline issue→freeze→sign→verify → test issue→freeze→sign→verify → `TASK-019`(baseline) →
> `TASK-019`(test) → both reports frozen → `TASK-028`(baseline) → `TASK-028`(test)

`TASK-019` opens no ground truth (`hidden_ground_truth_opened=false`), so it may precede truth
access. Committing **both** candidate sets before any truth opens removes the possibility that a
baseline score influences the test run's configuration — the exact post-hoc adjustment
`ADR-007`/`ADR-012` exist to forbid, which a naive "score the baseline, then run the test" order
would leave open.

**Actor eligibility (binding).** No single actor may hold more than one of: (a) issuing
coordinator, (b) commitment signer, (c) custody verifier, (d) validation/evaluation evaluator. In
particular, the actor that fixed this document's parameters is, by `ADR-051`'s ineligibility rule
(5) ("any Statistics/evaluator actor that participated in ... pre-commitment tuning for this run"),
**not eligible to be the evaluator in steps 7–8**. That is a deliberate self-exclusion, recorded
here so a later session cannot read this document as authorizing its author to score the result.

---

## 8. Readiness: unmet preconditions found while verifying, not assumed

Each of the following was verified by execution or direct file inspection. **None is a
methodological objection to the test; all are missing infrastructure.** Until every one is
resolved and recorded, no `ecommerce` run may be issued.

### R1 — No registered blind dataset selector for `ecommerce` (owner: ARCHITECT)

`blind/allowlist.yaml`'s `datasets` map contains only `travel` and `b2b_sales/comparable`.
Executed check:

```
travel               -> OK   synthetic_data/analytical/travel-bookings-analytical-v1.1.0
b2b_sales/comparable -> OK   synthetic_data_domains/b2b_sales/analytical/b2b_sales-analytical-v1.0.0
ecommerce/comparable -> FAIL ValueError: unknown blind dataset selector: ecommerce/comparable
ecommerce            -> FAIL ValueError: unknown blind dataset selector: ecommerce
```

`HANDOFF-063` established that this key must be **reviewed**, not merely added, and that issuance
signs the selected root together with dataset identity and acceptance fields. Same shape of work
`HANDOFF-063` did for `b2b_sales`, plus a truth-free pinned-image rehearsal returning
`BLIND_REHEARSAL_VALID`.

### R2 — `ecommerce`'s analytical dataset is missing both mandatory split partitions (owner: DATA_ENGINEER)

`tools/blind_agent/core.py:DATASET_FILES` requires six public partitions. The committed
`ecommerce-analytical-v1.0.0` directory has `features.csv`, `outcomes.csv`, `identifiers.csv`, and
`metadata.csv` but **no `split_manifest.json` and no `split_membership.csv`**, so issuance fails
closed on a missing allowlisted source. The manifest carries an internal `temporal_splits` block
(development 4,981 / validation 2,431 / future_holdout 2,588 rows) but that is not the public,
identity-pinned split contract the runner verifies.

This is exactly what `HANDOFF-064` delivered for `b2b_sales` (`b2b-sales-temporal-split-v1.0.0`,
pinned to that dataset's identity). The tooling already generalizes:
`scripts/build_domain_temporal_splits.py` plus
`domain_benchmarks.analytical_bridge.temporal_split_config` would produce
`ecommerce-temporal-split-v1.0.0`. It has simply never been run and committed for this domain.

### R3 — `ecommerce`'s manifest has no `validation_roles` block, so `TASK-019` cannot run (owners: DATA_ENGINEER + STATISTICS review)

`ADR-050` made validation inputs manifest-owned and fail-closed.
`packages/analytics/src/policy_analytics/validation/input_contract.py` raises
`ValueError("manifest lacks supported validation_roles version 1.0.0")` when the block is absent.
`b2b_sales`'s manifest has it; `ecommerce`'s does not — its analytical dataset was built under
`TASK-062` (2026-08-20) and never regenerated after `ADR-050` landed.

`analytical_dataset.build_analytical_dataset` now emits the block generically, so regeneration is
the mechanical fix, but two things must be handled deliberately rather than as a side effect:
(a) the emitted `heterogeneity_column`/`robustness_group_column`/`alternative_outcome_id` come from
`analytical_bridge.analytical_dataset_config`, which sets all three to `None`, so G09/G11 will be
`NOT_EVALUATED` for every candidate — the same second ceiling `TASK-065` hit, and it must be
recorded as an accepted, disclosed condition rather than discovered afterwards; (b) regeneration
may move `dataset_identity_sha256`, which is exactly the pinned-hash regression class `ADR-030` and
`TASK-062`'s own `_config_summary()` fix already caught twice — it must be checked byte-for-byte,
not assumed.

### R4 — The blind executor cannot express the cap, so the test run is currently *unexecutable as specified* (owners: ML_DISCOVERY implementation, ARCHITECT signing surface, CODE_REVIEWER approval)

**This is the most consequential finding.** `scripts/run_discovery.py:90` builds the discovery
configuration as:

```python
config = DiscoveryConfig(seed=int(manifest["random_seed"]))
```

Every other knob is left at its default, and `max_feature_identity_fraction` has **no path from the
signed manifest into the executor**. Issued today, the "cap-enabled" test run would silently run
with the cap **disabled** while being labelled `discovery-engine-v0.6.0` — producing a candidate set
byte-identical to the baseline and a determination that looks like a legitimate null result but is
actually a configuration bug. That is the same failure `task-060-iteration-20260820-003` already
produced once (`ADR-039`: a new official run byte-identical to its predecessor), except here it
would be mistaken for the test's answer instead of caught by diff.

Two things are required, and the second is not optional:

1. the executor must accept the parameter, and
2. the parameter must be carried in the **evaluator-signed** acceptance contract
   (`tools/blind_agent/core.py:_acceptance_contract`), the same way `discovery_method_version` and
   `random_seed` already are — otherwise the run's own signed record cannot prove which
   configuration produced the candidates, and the baseline/test distinction is unverifiable after
   the fact.

Until this exists, **`make blind-issue` for the test run must not be attempted**: a run ID is
consumed permanently on issuance and a failed or mis-configured run cannot be retried under the
same ID.

### R5 — The `ADR-051` custody chain has no eligible actors instantiated for this task (owners: ARCHITECT, CODE_REVIEWER, FOUNDER_STRATEGY as needed)

§7 requires four distinct identities. Today none is bound for `ecommerce`, and there is no
`ADR-052`-style approved evaluator slot for `TASK-068` (the existing approval,
`EVALUATOR_SLOT_APPROVED: TASK-065-INDEPENDENT-EVALUATOR` in `HANDOFF-067`, is scoped to
`TASK-065`/`b2b_sales` by its own text and cannot be reused). `ADR-052` makes slot approval a
mandatory **pre-issuance** condition, so this must be created before step 2 of §7, not during it.

---

## 9. What may not change after this document

Fixed and closed to edit once either run is issued: the domain and variant; both run IDs; both
runs' complete `DiscoveryConfig`; the success/kill criteria in §5; the computation rules in §5a;
the decision-gate disqualifiers and bands in §6; the custody order and actor-eligibility rule in
§7. A change to any of them voids both runs and requires a new preregistration and a new domain —
of which four would then remain.

Explicitly permitted after issuance: appending the post-run record below; recording honest
infrastructure failures; and recording a kill. **A kill is a complete, valid, expected outcome**
(`ADR-058` reopening condition 1 treats success and kill identically) and must be recorded as such
rather than re-examined against a metric not named in §5.

---

## 10. Post-run record

*(Empty. To be appended only after the runs described above actually execute. Nothing has been
issued as of 2026-08-23.)*
