# TASK-078 — Oracle-adjustment-set sufficiency experiment (`ADR-071` step 2)

**Status: POST-HOC DIAGNOSTIC EXPERIMENT throughout.** Every number here is produced by the real,
unmodified `policy_analytics.validation.apply.run_validation` (and, for the one intervention this
task authorizes, a process-local monkeypatch of the module attribute `_select_adjustment_columns`
— never a change to the function's source). Nothing here is a new official run, changes any frozen
artifact, or touches `discovery.engine`, `apply.py`, `G02`, or `validation-contract.md` on disk.
**This task does not propose, scope, or design any fix** — see §8/§9 for exactly what is, and is
not, being handed to the next task. Raw computed output:
`docs/benchmark/task-078-oracle-adjustment-sufficiency-raw.json`, produced by
`scripts/diagnose_task078_oracle_adjustment_sufficiency.py`.

## 0. The single question

If `G06` receives each trap's true confounder set directly — bypassing its own cardinality-cliff
selection logic (`TASK-075`) entirely — is the *rest* of the validation mechanism (estimator,
remaining `G00`–`G14` gates, thresholds) sufficient to reject the five confounding traps
(`T01`–`T05`)?

## 1. Method

**Single controlled intervention, per `TASK-078`'s scope item 1.** Same dataset
(`travel-bookings-analytical-v1.1.0`, identity `b6128eb3c1…60a683`, matching `TASK-075`'s own
record), same candidate definitions (`CAND-014`/`T03`, `CAND-015`/`T04`, and `T01`/`T02`/`T05`'s
single-condition `apparent_feature` counterfactuals — all parsed generically, none retyped by
hand, from `docs/benchmark/task-075-t03-forensic-trace-raw.json` and
`synthetic_data/evaluation/hidden_ground_truth.json`), same estimator
(`_stratified_adjustment`, cluster bootstrap, E-value), same `G00`–`G15` gates and thresholds
throughout. **The one intervention:** for the duration of one `run_validation()` call per trap,
the module attribute `policy_analytics.validation.apply._select_adjustment_columns` is replaced
with a wrapper that ignores its own greedy coverage-gated search entirely and returns a fixed,
precomputed oracle adjustment set instead — `G06`'s own selection *algorithm* is never edited on
disk; only its *output*, for this one substitution, is overridden. Every other gate, and
`classify_evidence_level`/`assign_policy_readiness`, run unmodified on the real outputs. The
monkeypatch is removed (restoring the real function) immediately after each `run_validation()`
call, in a `finally` block.

**Oracle sets are read once from `hidden_ground_truth.json`'s `confounded_by` field, fixed before
any candidate is scored, never revised after a result (`TASK-078` scope item 2).** The achievable
oracle set for a trap is every `confounded_by` variable that is (a) in the manifest's
`adjustment_eligible` pool and (b) not one of that trap's own candidate's condition features
(`G02`'s circularity guard, untouched — never bypassed by this experiment). Where a ground-truth
confounder fails either test, it is excluded and the reason is disclosed, generically, the same
rule applied to every trap identically (§3).

**Same `G00`–`G15` estimator and thresholds, not a shrunk multiplicity family.** Each run passes
exactly one candidate to `run_validation()`. `G05`'s Benjamini–Hochberg family_size is still the
real, already-documented `33085` from `task-073-official-20260829-001` (`TASK-075`'s own recorded
value, reused verbatim, not re-derived) — but with only one candidate in the call, that candidate's
BH rank is always 1, which is the *most conservative* (largest) adjusted p-value obtainable at
that family_size, strictly harder to pass than its true historical rank. This can only make `G05`
spuriously *reject* a trap that should otherwise pass, never help a trap survive — every raw
p-value observed in this experiment is far enough below `alpha=0.1` that this makes no difference
to any verdict here (see raw JSON, `documented_official_family_size_reused`).

## 2. Fidelity

`artifacts/blind/task-073-official-20260829-001.*` are not present in this worktree (`artifacts/`
is gitignored; this is a fresh worktree with no prior official-run output in it — the identical
disclosed limitation the `CODE_REVIEWER`'s independent `TASK-075` review already recorded). This
task cannot re-verify the frozen `candidates.json`'s SHA-256 against `hashes.json`, nor byte-match
a fresh `run_validation()` against the committed `TASK-019` artifact directly. Two substitute
checks were run instead, and both passed before anything below was reported:

1. **Dataset identity**, recomputed fresh from the manifest, matches the identity `TASK-075`
   recorded exactly: `b6128eb3c1bdb36515c90570aa4ccabfc3dff8d1026d9002f1c832774b60a683`.
2. **A fresh, override-free `run_validation()` call** — real `_select_adjustment_columns`, no
   monkeypatch — on `CAND-014`/`CAND-015`'s exact real conditions (recovered programmatically from
   the already-committed `task-075-t03-forensic-trace-raw.json`, never retyped) and on
   `T01`/`T02`/`T05`'s counterfactual conditions, reproduces `TASK-075`'s own already-recorded
   `adjustment_columns_used` **exactly**, for all five traps. Script output:
   `[fidelity 2/2] real (non-overridden) G06 selection reproduces TASK-075's own recorded
   adjustment_columns_used exactly, for all 5 traps' conditions`.

This bears on custody/fidelity re-verification only, not on the mechanism this task measures —
once oracle overrides are applied, they are applied on top of a harness independently shown to
reproduce the real, unmodified pipeline's own already-confirmed selections.

## 3. Oracle sets, read once, per trap

| Trap | Candidate tested | `confounded_by` (ground truth) | Achievable oracle set | Excluded, and why |
|---|---|---|---|---|
| T01 | counterfactual `manager==Manager 2` | destination, booking_lead_days, party_size, trip_duration_days | all 4 | none |
| T02(a) | counterfactual `supplier==Atlas` | trip_duration_days, booking_month | trip_duration_days | `booking_month`: vocabulary gap — not in the manifest's `adjustment_eligible` pool at all |
| T02(b) | counterfactual `supplier==Atlas` | trip_duration_days, booking_month | trip_duration_days, booking_month | none — `booking_month` derived (§5) |
| T03 | `CAND-014` (real, `acquisition_channel==paid_search AND discount_rate>=0.08`) | customer_type, discount_rate, installments | customer_type, installments | `discount_rate`: structurally excluded — it is `CAND-014`'s own second condition feature (`G02`, untouched) |
| T04 | `CAND-015` (real, `discount_rate>=0.05 AND payment_method==bank_transfer`) | booking_lead_days, destination | both | none |
| T05 | counterfactual `manual_exception==true` | destination, party_size, trip_duration_days, booking_lead_days | all 4 | none |

`T03` is the one trap whose fully-representable ground truth is not fully achievable under the
untouched mechanism — not a vocabulary gap like `T02`'s, but a structural one: `discount_rate` is
literally one of `CAND-014`'s own two defining conditions, so `G02`'s circularity guard (adjusting
for the treatment's own defining variable is circular — correct in general, untouched here)
excludes it regardless of any selection-order fix. This is disclosed, not glossed over: the `T03`
result below is against its best *achievable* oracle set (2 of 3 ground-truth confounders), not
the full 3.

## 4. Per-trap oracle-adjustment results

| Trap | Oracle set applied | Coverage | Raw effect (EUR) | Adjusted effect (EUR) | Attenuation | E-value (floor 1.5) | `G06` | Gate-of-death (excl. `G13`/`G14`) | Evidence level | Policy readiness | Verdict |
|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| T01 | destination, booking_lead_days, party_size, trip_duration_days | 0.78 | −29.1 | −69.0 | −1.37 | 1.39 | FAIL | `G03_SAMPLE_ADEQUACY` | descriptive_observation | **not_ready** | REJECTED |
| T02(a) | trip_duration_days | 1.00 | −50.4 | −47.5 | 0.06 | 1.31 | FAIL | `G03_SAMPLE_ADEQUACY` | descriptive_observation | **not_ready** | REJECTED |
| T02(b) | trip_duration_days, booking_month | 1.00 | −50.4 | −47.9 | 0.05 | 1.31 | FAIL | `G03_SAMPLE_ADEQUACY` | descriptive_observation | **not_ready** | REJECTED |
| **T03** | customer_type, installments | 1.00 | 217.7 | 220.0 | −0.01 | **1.94** | **PASS** | none | adjusted_observational_association | **shadow_policy** | **SURVIVED** |
| **T04** | booking_lead_days, destination | 1.00 | 166.5 | 154.1 | 0.07 | **1.70** | **PASS** | none | adjusted_observational_association | **shadow_policy** | **SURVIVED** |
| T05 | destination, party_size, trip_duration_days, booking_lead_days | 0.18 | −29.6 | −143.6 | −3.85 | 1.67 | FAIL | `G03_SAMPLE_ADEQUACY` | descriptive_observation | **not_ready** | REJECTED |

`T03` and `T04` clear every gate at full statistical power (`G00`–`G12`, `G15` all PASS; `G13`/`G14`
FAIL as expected for observational data, the contract's own disclosed level-3 ceiling) — identical
to their real, non-overridden gate traces on `G00`–`G05` and `G07`–`G15` (only `G06`'s own numbers
differ, since that is the one substituted input). Full gate-by-gate detail for every run:
`docs/benchmark/task-078-oracle-adjustment-sufficiency-raw.json`.

**`T01`, `T02`(a and b), `T05` are rejected on two independent grounds, not one.** All four fail
`G03_SAMPLE_ADEQUACY` — their raw, unadjusted development-split effect is too small relative to the
minimum detectable effect to clear sample adequacy at all (consistent with `hidden_ground_truth`'s
own `direct_effect: 0` for every trap: these three never produced a real candidate in this
project's history, per `TASK-075` §4, precisely because their raw apparent correlation was never
strong enough for the search to select them). Their oracle-adjusted `G06` also independently fails
— on attenuation (`T01`, `T05`: the adjusted effect moves *further* from zero and reverses in
relative magnitude, `attenuation < -1`) or on E-value (`T02`: adjusted effect's standardized
magnitude does not clear `1.5` even though attenuation and coverage are both fine). **`T05`'s
oracle set — even the complete, correct 4-variable ground truth — cannot reach the `0.50` joint
coverage floor** (`0.18`): unlike `T03`/`T04`'s 2-variable oracle sets, which achieve coverage
`1.00`, a 4-way joint stratification on `T05`'s true confounders is themselves too fine relative to
its `n_exposed=338` — a genuine data-support ceiling, not a selection-algorithm artifact, and a
fact worth carrying into any future selector design's own overlap/coverage trade-off (`ADR-071`
step 3).

## 5. `T02`'s two counterfactuals, kept separate (scope item 3)

**(a) Schema-feasible oracle** (`trip_duration_days` only, `booking_month` excluded): rejected,
`not_ready`, gate-of-death `G03_SAMPLE_ADEQUACY` (also independently `G06`-failing on E-value).
Tests `G06` sufficiency under the *current* vocabulary.

**(b) Full-ground-truth oracle** (`trip_duration_days` **and** `booking_month`): `booking_month`
was reconstructable without changing the benchmark's own meaning — derived as
`booking_month := month(booking_date)`, the exact same generic `<x>_month := month(<x>_date)`
derivation `scripts/diagnose_oracle_decomposition.py` already established as this project's own
precedent for this exact situation (a true condition names a calendar decomposition of a date
column the frame already carries). Computed as a one-off column for this experiment's `run_id`
only — never written to the dataset on disk, the manifest's `adjustment_eligible` pool, or
`discovery.engine`'s vocabulary. Result: also rejected, `not_ready`, same gate-of-death
(`G03_SAMPLE_ADEQUACY`, also independently `G06`-failing on E-value, `1.31` either way). **(a) and
(b) reach the identical verdict here** — adding `booking_month` barely moves the adjusted effect
(`−47.5` vs. `−47.9` EUR) because `trip_duration_days` alone already achieves full coverage and
`G03`'s upstream rejection does not depend on the adjustment set at all. This equality is itself
informative: for `T02` specifically, the vocabulary gap `TASK-075` flagged as a second, independent
defect turns out **not to be load-bearing for this trap's own rejection** — `T02` was never going
to reach `shadow_policy` either way, because its raw apparent effect is too weak to pass `G03` in
the first place. This does not reopen or soften `TASK-075`'s own finding that `booking_month`'s
absence is a real, independent gap (§4b/§11 disclosed limitation) — it only means this specific
trap's rejection does not depend on closing it.

## 6. Why `T03` and `T04` survive — mechanistic, not just observational

**`T04`/`CAND-015` is the cleaner case: no representability caveat at all.** Both of `T04`'s true
confounders (`booking_lead_days`, `destination`) are fully achievable — neither is `CAND-015`'s own
condition feature, neither is a vocabulary gap. Handed directly to the estimator, bypassing `G06`'s
selection entirely, the joint stratification reaches full coverage (`1.00`) and a plausible,
modest attenuation (`0.07`, harm `166.5 → 154.1` EUR) — and still clears every threshold, including
the `E-value` floor (`1.70 ≥ 1.5`), reaching `shadow_policy`. **This directly answers `TASK-078`'s
question in the negative for `T04`: even a perfect adjustment-set selector would not have stopped
this specific promotion.** The defect is downstream of adjustment-set construction — in the
estimator's own power to separate the true confounding-driven association from the two true
confounders' actual effect, or in what counts as sufficient adjustment at all for this kind of
composition-driven trap (`payment_method==bank_transfer` correlates with `destination`/
`booking_lead_days`, which correlate with the outcome, but stratified mean-differencing over those
two covariates does not fully remove the association).

**`T03`/`CAND-014` survives too, but with the `G02` caveat from §3 attached.** Its achievable
oracle set (`customer_type`, `installments`) reaches full coverage (`1.00`) and the adjusted effect
does not attenuate at all — it moves in the *opposite* direction of attenuation (`217.7 → 220.0`
EUR, `attenuation −0.01`), i.e. adjusting for the two available true confounders explains
essentially none of the raw association. `TASK-075` §2 already established, by a separate
counterfactual trace, that `discount_rate` (the excluded third confounder) would *also* fail the
old coverage floor if it were eligible — so this is not simply "the selector would have picked
`discount_rate` under a smarter rule and everything would be fine." The more precise reading:
`CAND-014`'s own condition set folds a real, ground-truth confounder (`discount_rate`) directly
into its exposure definition, which makes that confounder categorically inadjustable for this
candidate under `G02`'s (correct, general) circularity rule — a **specification** problem in how
the search composed this particular rule, not a **selection-among-eligible-covariates** problem
`G06` could ever solve by reordering. Whether adjusting for `discount_rate` (were it not
self-referential) would have rescued this candidate is not established either way by this
experiment — what is established is that the two confounders that *are* adjustable do not.

**Both survivals share one property TASK-075's own diagnosis did not test:** in `TASK-075`'s
account, traps failed because `G06`'s selection *never reached* the true confounders. Here, `G06`
*is* handed the true confounders (or the best achievable subset), at full coverage, and the
candidate still clears every gate. The cardinality cliff explains why `G06` didn't try; it does not
explain why trying would have been enough.

## 7. Acceptance criterion applied, exactly as fixed in advance

Per-trap, not an aggregate that could average away one survivor (`TASK-078` item 4): every
fully-representable trap given its complete known confounder set must stop reaching `shadow_policy`
or above.

- `T01`: rejected. ✓
- `T02(a)`: rejected. ✓ (schema-feasible oracle)
- `T02(b)`: rejected. ✓ (full-ground-truth oracle, reported separately, never merged with (a))
- `T03`: **survives** at `shadow_policy`, under its best achievable oracle set (2 of 3
  ground-truth confounders — the third is structurally inadjustable for this candidate, §3/§6). ✗
- `T04`: **survives** at `shadow_policy`, under its complete, fully-achievable oracle set. ✗
- `T05`: rejected. ✓

**Two of five traps survive their oracle-adjustment set. The preregistered criterion is not met.**

## 8. The fork this task exists to resolve

**Survivor found — the cardinality cliff (`TASK-075`) remains a proven, real defect, but is *not
sufficient* to explain the safety failure by itself.** `T04` demonstrates this cleanly and without
qualification: its oracle set carries no representability caveat, reaches full joint coverage, and
`CAND-015` still reaches `shadow_policy`. `T03` demonstrates it too, with the disclosed caveat that
its oracle set is incomplete for a structural (not vocabulary, not selection-order) reason.

Per `TASK-078`'s own pre-fixed instruction: **opening a "fix `G06`'s selector" task now would be
premature.** A second forensic layer — examining the estimator/specification/downstream decision
semantics, not just which covariates `G06` picks — is required first, as its own task, before any
`G06` fix-design work begins.

## 9. What the next task (the second forensic layer) would need to cover — named, not designed

Per this task's own hard rule, nothing below is a proposal, a scoped fix, or an authorized change.
It names what the next task, opened separately by the orchestrating session, would need to
investigate — generically, not keyed to `T03`/`T04`/`CAND-014`/`CAND-015`'s identities:

- **Why does full-coverage adjustment for the complete, correct confounder set (`T04`) still leave
  a `shadow_policy`-reaching adjusted effect?** Candidates worth investigating, none decided here:
  whether `_stratified_adjustment`'s exposure-weighted mean-differencing is itself too weak an
  adjustment for continuous/moderate-cardinality confounders like `booking_lead_days`/`destination`
  (residual within-stratum confounding after quartile-binning); whether the E-value floor (`1.5`)
  and attenuation ceiling (`0.50`) are calibrated for a level of residual bias this specific
  confound structure does not produce even when genuinely present; or something the estimator
  itself cannot see at all.
- **Whether a candidate's own condition set folding in a ground-truth confounder (`T03`/
  `CAND-014`'s `discount_rate`) is a systematic failure mode of the search/candidate-generation
  step**, not just this one instance — if the search can propose rules that compound a true
  confounder into their own exposure definition, no adjustment-set fix downstream of candidate
  generation can ever recover from it for that candidate, regardless of how good `G06` becomes.
  This is a question about `discovery.engine`'s candidate-composition behavior, explicitly outside
  this task's (and `TASK-075`'s) own scope, and outside `G06` entirely.
- **`T05`'s oracle-set coverage ceiling (`0.18` even at the complete, correct 4-variable oracle
  set)** is a genuine data-support fact this project's synthetic travel dataset produces, not a
  selection-algorithm defect — worth carrying forward into whatever coverage/overlap constraint any
  future selector design (`ADR-071` step 3) settles on, since a selector that *could* correctly
  identify all 4 true confounders still could not jointly adjust for them here.
- **Positive-control preservation** (the six real `PASS` candidates) is explicitly out of scope for
  both this task and the next forensic layer — `ADR-071`'s own fix-design/implementation phase,
  unchanged by this task's finding.

## 10. What this task did not do

No threshold in `ValidationThresholds` was read as wrong, no gate's rule was called a defect, `G02`
was never bypassed, and no replacement selection rule, estimator change, or gate change is
proposed, sketched, or implied anywhere above beyond the diagnostic naming in §9. `G06`,
`apply.py`, `discovery.engine`, and `validation-contract.md` are untouched on disk — the only
override was a process-local, `finally`-restored monkeypatch of one module attribute for the
duration of six `run_validation()` calls. The six existing real `PASS` candidates were not
touched, re-scored, or evaluated by this experiment. Neither follow-on task (the `G06` fix-design
this fork does *not* authorize, nor the second forensic layer it names) is opened by this task —
both are for the orchestrating session/founder to open, per `TASK-078`'s own instruction.
