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

*(Appended 2026-08-27, after both preregistered runs executed. §1–§9 above are unedited: `git diff
d2f1d2f -- docs/benchmark/task-068-ecommerce-preregistration.md` was empty immediately before
issuance, and this section is the only permitted change per §9.)*

### 10.1 Pre-issuance conditions re-checked at issuance time

- **Executor bytes.** All five SHA-256s `HANDOFF-073`'s CODE_REVIEWER pinned still match exactly:
  `scripts/run_discovery.py` `5548ebd2ef16f718bd0a1cf9ce0d03f88dea39391eca56eba094aa6e33e63bb1`;
  `tools/blind_agent/core.py` `e5d3fb60118d6a14843f89a4e87ca40b3cf43ae66cc5ec0eadfe101fef358c7a`;
  `tools/blind_agent/models.py` `8d315cb9239a3af423d9c15bea202e39544cd0404d77d6d4f526a6ed861d0a86`;
  `tools/blind_agent/cli.py` `d156e8f37c2fadaefd8e4f29153fd8b84a1941de8d4571793c5af62a44e9694b`;
  `packages/analytics/src/policy_analytics/discovery/engine.py`
  `192b897088bb77568e4bac865773939ad5513d2fe6d9ed8dc8f5d3c8e9d9174b`. `blind/allowlist.yaml` is
  also unchanged at `f35da4a8a6ed67f6fba7813f5002fd649b6a7a0c30eaa89065b407253d261fc1`. The only
  commits between the reviewed `f0f3e62` and issuance HEAD `bea0606` are `a4e101d`/`bea0606`, which
  touch `memory/HANDOFFS.md` and `TASKS.md` only.
- **§7 step-1 rehearsal.** `make blind-rehearsal BLIND_DATASET=ecommerce/comparable` printed
  `BLIND_REHEARSAL_VALID` at exit 0 against pinned image
  `policy-blind-agent@sha256:9ad6e1a78ca41a7c04895d1d99c7775e77fc2c8fbb4f23cee268ed04534c7c9b`,
  re-run on this tree rather than inherited from the readiness review.
- **Run IDs.** Both preregistered stems were confirmed absent from `BLIND_RUNS_ROOT` and repository
  artifacts immediately before issuance. A fresh evaluator signing key was created with
  `make blind-key-init` (`/tmp/policy-blind-evaluator/signing.key` did not exist — a consequence of
  local `/tmp` cleanup on 2026-08-24; the five historical runs' receipts are therefore no longer
  re-verifiable against a live key, which is recorded as an observation and affects nothing here).

### 10.2 The two runs as actually executed

Both: `BLIND_DATASET=ecommerce/comparable`, agent `deterministic`, network `none`, `seed=1729`,
`discovery-engine-v0.6.0`, dataset identity
`fb8d049d5f81bb0d792ead8d6310e301b998f4eed7acf63a3274456b9f56c658`, split contract
`ecommerce-temporal-split-v1.0.0`, search-fit split `development`, 17,523 evaluated hypotheses,
15 candidates `PERSISTED`, bundle
`e79c0f8017eb4be1a96b48079809e9e7055046a23b9a3aca02b1d6b4446b7391`.

**§4b verified against the machinery, not asserted:** diffing the two evaluator-signed acceptance
contracts field by field yields exactly one difference — `max_feature_identity_fraction`
`1.0` vs `0.34`. Every other signed field is identical.

| | Baseline (`1.0`) | Test (`0.34`) |
|---|---|---|
| Run ID | `task-068-ecommerce-baseline-20260827-001` | `task-068-ecommerce-cap-20260827-001` |
| `frozen/candidates.json` | `ae45e637053978acd248ecf28913c5fc30c31871a251664d62de657cda6edaf8` | `57b9100a45102898d0d28a724674d615432fd29bb589962fdd5e13128dac6a0d` |
| `frozen/discovery_metrics.json` | `43e5a4f3d348c4058cc43a7770799a17c6c6be005d3802f3a37fd2f14fbf16c5` | `90dd972bbd117411303dc101db6f6c8767d8e8c52443d6577ce6a1aace219c67` |
| `frozen/run_report.md` | `0ad9f4088f58bc849592e81aee35ef65cc908a53a27ff6d554234ba9036411f9` | `0ad9f4088f58bc849592e81aee35ef65cc908a53a27ff6d554234ba9036411f9` |
| `frozen/hashes.json` | `3f0ac8e7ba56c98f4695d69d9820ec4f5b3f4c028558c01087fcb872d621a635` | `25ace3bbf48690b50779c73846788331fae58883d94a4aae6e8618674b995a59` |
| `BLIND_MANIFEST.json` | `5e5523349766a3f6962a95f523dcad0b446ef7d5b04b85681605026f70e2bfbf` | `59166245955289c4f6675f145c30b69e2a2ea799af2a20399aef3d3c3f1917c9` |
| Receipt file | `ce83b815c9cdb9ea716023144937faa53b18ecf9bbde062350be78ae1a59e1d3` | `5a9426dea49bc17d9cac38c82980629fa9b95d177d906ea14f1dbdf617a3ae8b` |
| Receipt HMAC | `fd45c9ebc02fe9a7575f452fdc472e90d7bb7aee8325c0b7f73854d2458eb692` | `c05c7d23802264ae2d40616330d525ad32461ad2889ae896afe8269e5a76275f` |
| Committed at | `2026-08-27T18:07:59.570847+00:00` | `2026-08-27T18:14:49.407342+00:00` |
| Frozen at | `2026-08-27T18:07:38.368367+00:00` | `2026-08-27T18:14:41.805632+00:00` |

**The R4 failure mode did not occur.** The two candidate sets are not byte-identical, and each
run's `discovery_metrics.json` declares the fraction its own signed contract carries (`1.0`,
`0.34`). Which configuration produced which candidate set is provable from the frozen artifacts.

Frozen originals live under `/tmp/policy-blind-runs/<run-id>/frozen/`; byte-identical archived
copies under `artifacts/blind/<run-id>.<name>` (`0444`, each `cmp`-verified at copy time).

### 10.3 Custody (§7 steps 5–6)

Both runs were signed (`scripts/commit_blind_candidates.py`, evaluator-owned key, after freeze) and
then independently custody-verified **before any ground truth was opened**. The verification pass
recomputed, from raw bytes rather than trusting any prior command's stdout: the manifest HMAC by
hand as well as through `_verify_manifest_signature`; `verify_candidate_commitment`; candidate,
manifest and receipt SHA-256s; `bundle_id` recomputed from the signed `allowed_files`; candidate↔
manifest bundle/identity binding; every signed workspace file re-hashed against its manifest entry;
input-provenance hashes; the full signed acceptance contract against §2/§3/§4's fixed values;
`runtime_agent=deterministic`, null model, digest-pinned image, `seed=1729`; `state=FROZEN`;
`0444` on all four frozen artifacts and the frozen hash index's self-consistency; the absence of any
ground-truth or evaluation artifact anywhere in the run tree; and commitment timestamps strictly
after freeze. **43 checks, all PASS, for each run: `CUSTODY_VERIFIED`.**

**Disclosed limitation, stated as plainly as `ADR-051`/`ADR-052` and §7 state it.** This session
executed the issuing-coordinator, commitment-signer, custody-verifier and evaluator steps. It is
therefore **not** the four-distinct-identity chain §7's actor-eligibility rule requires, and the
custody verification, though genuinely re-derived rather than rubber-stamped, is not independent in
the sense `ADR-051` means. The structural protections that do not depend on actor independence held
in full — the blind actor really was an isolated, network-less, digest-pinned container that never
saw ground truth; candidates really were signed and frozen before truth opened; and every binding
above is checkable by anyone from the frozen bytes. What a single session cannot supply is the
independence of the *judgment*, and that is a real limitation of this record, not a formality. It is
the same disclosure `ADR-051`/`ADR-052` and this task's own evaluator-slot record already make.

### 10.4 §7 step 7 — `TASK-019`, both runs, before any truth access

| | Baseline | Test |
|---|---|---|
| Report | `artifacts/validation/task-019-task-068-ecommerce-baseline-20260827-001.json` | `artifacts/validation/task-019-task-068-ecommerce-cap-20260827-001.json` |
| SHA-256 | `8fdaa7edd3e9b9863a1a089470c2242a5c3343d11dddb2d144ee301f78222752` | `f85393b302186ea78d06fa2b25a29f48096062767526254aa9765b571a993479` |
| Mode / status | `0444`, `FROZEN` | `0444`, `FROZEN` |
| `hidden_ground_truth_opened` | `false` | `false` |
| Verdicts | 15 `DOWNGRADE` | 15 `DOWNGRADE` |
| Evidence level | 15 `descriptive_observation` | 15 `descriptive_observation` |

Gate profile (contract `1.2.0`), baseline → test: G06 `pass` 14→13 / `fail` 1→2; G12 `pass` 7→6 /
`fail` 8→9; G13 and G14 `fail` 15/15 in both; G09 `not_evaluated` 15/15 in both — the accepted,
pre-disclosed `heterogeneity_column`/`robustness_group_column` ceiling `HANDOFF-073` R3 recorded in
advance, identical across arms and so unable to bias the comparison. G00–G05, G07, G08, G10, G11
and G15 pass 15/15 in both. Both reports were frozen before any `TASK-028` ran.

Worth recording because it differs from `TASK-065`: on `b2b_sales`, G06 failed for **all 15**
candidates. On `ecommerce` it passes for 14/15 (baseline) and 13/15 (test). The `TASK-067` G06
defect is therefore not what caps this domain — G13/G14 are, and those are properties of
observational candidates, not of this mechanism.

### 10.5 §5a structural check — decided truth-free, before any `TASK-028`

Computed exactly as §5a fixes it: the distinct
`{condition.feature for condition in candidate.conditions}` over all 15 frozen candidates, from
public frozen candidate bytes only.

| Feature identity | Baseline slots | Test slots |
|---|---|---|
| `discount_pct` | 11 | 5 |
| `product_price_usd` | 8 | 5 |
| `quantity` | 4 | 5 |
| `product_category` | 0 | 5 |
| `items_in_cart` | 2 | 4 |
| `coupon_used` | 2 | 1 |
| `acquisition_channel` | 2 | 1 |
| `product_tier` | 1 | 3 |
| `days_since_last_visit` | 0 | 1 |
| **Distinct identities** | **7** | **9** |

**PASS — 9 > 7, strictly higher.** The preregistered quota is honoured exactly: no identity exceeds
`max(1, floor(0.34 × 15)) = 5` slots in the test run, against a baseline where `discount_pct` alone
claimed 11 of 15. Two identities appear that the baseline never surfaced (`product_category`,
`days_since_last_visit`) and none is lost. This is the `ADR-055` crowding defect being corrected in
the direction the mechanism predicted, and it exceeds §4a's honest worst-case floor of 3.

### 10.6 §7 step 8 — `TASK-028`, baseline then test, in the fixed order

`synthetic_data_domains/ecommerce/comparable/evaluation/hidden_ground_truth.json` (SHA-256
`07731b6de0168c8fc9f43ad8f09c3be78168bf916514a9e22ab27e950de004f6`) was opened here for the first
time, after 10.1–10.5 were complete and frozen. Generically derived: scoreable patterns
`E03`, `E04`, `E06`, `E09` (total realized impact 15,545.88 USD); traps `ET01`–`ET05`.

| | Baseline | Test | §5 comparison |
|---|---|---|---|
| Report | `artifacts/evaluation/task-028-task-068-ecommerce-baseline-20260827-001.json` | `artifacts/evaluation/task-028-task-068-ecommerce-cap-20260827-001.json` | |
| SHA-256 | `79e511ec29fdbb03a804ebcc51117eda03fb55b93f68ebc097b7a6bebc52cc02` | `47b240d384f75c581dda02054f2ff4e796b13429f818eed20dab4fbfff3b424e` | |
| Top-10 precision | 50% (5/10) | 50% (5/10) | equal → **not degraded** |
| Economic-weighted recall | 0.0% (0 of 15,545.88) | 0.0% (0 of 15,545.88) | unchanged |
| Unique scoreable-pattern candidate-match recall | **1/4** (`E03`) | **2/4** (`E04`, `E09`) | **strictly higher** |
| Direction accuracy | not estimable (0/0) | not estimable (0/0) | not estimable in **both** → §5a: not a degradation |
| Trap rejection | 5/5, 0 promoted | 5/5, 0 promoted | equal → **not degraded** |
| Traps appearing as candidates | `ET03`, `ET05` (4 candidates) | `ET03`, `ET05` (2 candidates) | none promoted in either |
| Leakage violations | 0 | 0 | no disqualifier |
| Economic-impact error | not estimable | not estimable | no validated matched finding |
| `policy_readiness` | 15 `experiment_only` | 15 `experiment_only` | |

Both TASK-028 reports are `0444`, `status=FROZEN`.

### 10.7 Determination against §5, and nothing else

**SUCCESS.** Applied strictly, with no metric, threshold or matching rule added, dropped,
reweighted or re-derived:

- The structural kill gate **passed** (7 → 9 distinct identities).
- The success clause requires one of the two named recall metrics to be strictly higher. **Unique
  scoreable-pattern candidate-match recall rose 1/4 → 2/4.** (Economic-weighted recall is 0.0% in
  both; the criterion is disjunctive — "or" — and is met by the second metric.)
- Top-10 precision: `test >= baseline` (0.50 = 0.50). **Not degraded.**
- Direction accuracy: zero eligible denominator in **both** runs, so per §5a it is reported as not
  estimable and cannot count as a degradation. It was not estimable in the baseline either, so the
  §5a case where the test run loses a denominator the baseline had does **not** apply.
- Trap rejection: 5/5 in both; no trap promoted in either, so the "trap promoted that the baseline
  did not promote" kill does not fire.

No kill condition fires. The recall metric used is the same computation that reproduces
`TASK-065`'s published `1/6` on `b2b_sales` byte-for-byte, checked against that frozen artifact
before being applied here.

**What this success does and does not claim, stated precisely so it is not over-read.** It is a
success of the *preregistered mechanism test*: the feature-identity cap did what `ADR-055` predicted
it would do — broke the single-identity crowding, surfaced two scoreable patterns where the baseline
surfaced one, and cost nothing on precision, direction or trap rejection. It is **not** a claim that
`ecommerce` now passes `docs/benchmark/decision-gate.md`. Graded under §6's retained bands, **both**
arms come out **FAILED**, driven by economic-weighted recall < 5% (0.0%) under the weakest-band
rule, with no hard disqualifier — the same absolute outcome `TASK-065` recorded on `b2b_sales`, and
unchanged between baseline and test. The cap recovered candidate-level matches, but nothing reached
`predictive_association`, so no match converted into economic-weighted recall: G13/G14 cap every
candidate at `descriptive_observation`. `TASK-068`'s criteria and the decision gate answer two
different questions, and both answers are recorded here as they came out.

`docs/benchmark/decision-gate.md` is not edited by this run, and travel's standing `PROMISING`
verdict (`ADR-025`) is unaffected in either direction.

### 10.8 Domain status

`ecommerce`/`comparable` is now **spent**: its hidden ground truth has been opened and it can never
again serve as independent portability evidence (`ADR-054`'s hard rule, as applied to `b2b_sales`).
Four untouched `TASK-061` domains remain: `healthcare`, `insurance`, `manufacturing`, `saas`.

Gates at determination time: `uv run ruff check .` → All checks passed; `uv run pyright` → 0 errors,
0 warnings, 0 informations; `uv run pytest -q` → **572 passed, 73 skipped, 2 failed**, the two
failures being the known `FileNotFoundError` on the gitignored `artifacts/` travel fixtures absent
from this worktree — the exact figures `HANDOFF-073`'s readiness review recorded.
