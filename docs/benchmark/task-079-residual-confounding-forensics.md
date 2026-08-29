# TASK-079 — Second forensic layer: residual confounding beyond `G06` adjustment-set selection (`ADR-072`)

**Status: POST-HOC DIAGNOSTIC throughout, diagnosis only, exactly like `TASK-069`/`070`/`075`/`078`
before it.** Every number below is produced by the real, unmodified
`policy_analytics.validation.apply` and `policy_analytics.discovery.engine` modules. The only
interventions are process-local, `finally`-restored monkeypatches of module attributes (never a
source-code edit) — the same discipline `TASK-078`'s script established:
`apply_module.ADJUSTMENT_QUANTILE_BINS` and `apply_module._select_adjustment_columns` are
temporarily overridden for the duration of single calls in Branch 1; Branch 2 calls
`discovery.engine`'s real `_metric`/`_development_score`/`_atoms`/`_eligible` read-only, exactly as
`discover_candidates` itself would; Branch 3 calls `apply.py`'s real `_binned_adjustment_frame`/
`_stratified_adjustment` read-only. **No code, gate, threshold, estimator, or `discovery.engine`
change of any kind is proposed, scoped, or implemented anywhere in this document.** Raw computed
output: `docs/benchmark/task-079-residual-confounding-forensics-raw.json`, produced by
`scripts/diagnose_task079_residual_confounding_forensics.py`.

## 0. The three questions, kept separate per `ADR-072`

1. **Branch 1 (`T04`, estimator sufficiency).** Oracle set held fixed (`booking_lead_days`,
   `destination`, never re-chosen) — why does `_stratified_adjustment`'s mean-differencing leave a
   `shadow_policy`-reaching residual, and is this a general estimator-insufficiency property?
2. **Branch 2 (`T03`, candidate-condition/confounder entanglement).** Can `discovery.engine`'s
   search produce an apparent pattern that becomes statistically irremovable downstream
   specifically because conditioning already folded a true confounder into the rule's own
   condition set — as a systematic property, not an isolated occurrence?
3. **Branch 3 (`T05`, overlap ceiling).** How should validation treat a trap whose complete,
   correct confounder set cannot jointly clear the coverage floor on this data — and should a
   future selector know this in advance?

**Preregistered separation, checked explicitly in §5 below, not violated anywhere in this
document.**

## 1. Fidelity

Dataset identity re-verified fresh against `TASK-075`/`TASK-078`'s own recorded value
(`b6128eb3c1bdb36515c90570aa4ccabfc3dff8d1026d9002f1c832774b60a683`) before anything below was
computed. `CAND-014`'s and `CAND-015`'s real conditions are parsed generically from the
already-committed `task-075-t03-forensic-trace-raw.json`, never retyped by hand. `T04`'s oracle set
(`booking_lead_days`, `destination`) is the identical achievable set `TASK-078` already established
and reused verbatim here, not re-derived or re-chosen. `artifacts/blind/task-073-official-*` is
still not present in this worktree (same disclosed, gitignored-artifacts limitation `TASK-075`'s and
`TASK-078`'s own `CODE_REVIEWER` reviews already recorded); this script's baseline 4-bin
reproduction of `TASK-078`'s own recorded `CAND-015` oracle result (adjusted harm `154.1` EUR,
attenuation `0.07`, E-value `1.70`) reproduces it exactly, which is the substitute fidelity anchor
used throughout, consistent with both prior tasks' own disclosed practice.

## 2. Branch 1 — `T04`: estimator sufficiency

### 2.1 Baseline reproduction

`CAND-015` (`discount_rate ge 0.05 AND payment_method eq bank_transfer`), oracle-adjusted for its
fixed, complete 2-variable confounder set at the estimator's shipped 4-bin granularity: raw harm
`166.5` EUR → adjusted `154.1` EUR, attenuation `0.07`, coverage `1.00`, E-value `1.70` (floor
`1.5`). Matches `TASK-078` exactly.

### 2.2 Binning-granularity sweep (oracle set fixed; only `ADJUSTMENT_QUANTILE_BINS` varied)

| Bins | Adjusted harm (EUR) | Attenuation | E-value | Coverage | Gate `PASS`? |
|---:|---:|---:|---:|---:|---|
| 2 | 162.3 | 0.02 | 1.73 | 1.00 | yes |
| 3 | 157.8 | 0.05 | 1.72 | 1.00 | yes |
| 4 (shipped) | 154.1 | 0.07 | 1.70 | 1.00 | yes |
| 5 | 150.2 | 0.10 | 1.69 | 1.00 | yes |
| 6 | 147.0 | 0.12 | 1.68 | 1.00 | yes |
| 8 | 147.2 | 0.12 | 1.68 | 1.00 | yes |
| 10 | 147.4 | 0.11 | 1.68 | 1.00 | yes |
| 12 | 145.3 | 0.13 | 1.67 | 1.00 | yes |

Attenuation drifts monotonically upward with finer binning (`0.02` → `0.13`), i.e. binning
granularity is not inert — finer resolution on `booking_lead_days` does capture a little more
structure. **But the drift is small, bounded, and never approaches either threshold**: attenuation
never gets within 4x of the `0.50` ceiling, and E-value never gets within 0.17 of the `1.5` floor,
across a 6x range of bin counts (2 to 12). Coverage stays at `1.00` (never the binding constraint)
at every granularity tested.

### 2.3 A different, standard estimator: additive OLS regression adjustment (oracle set fixed)

Standard alternative to stratified mean-differencing: `outcome ~ treatment + destination (4 dummies)
+ booking_lead_days (raw continuous, unbinned)`, fit by ordinary least squares (from-scratch,
pure-Python normal-equations solve; `n=4999` development rows). Treatment coefficient (regression-
adjusted harm): **`156.0` EUR, attenuation `0.06`, E-value `1.71`** — indistinguishable from the
stratified baseline (`154.1`/`0.07`/`1.70`).

**Prior context, not re-litigated here:** `ADR-043` (2026-08-21, `HANDOFF-058`) already evaluated
additive multivariate regression against full joint stratification, on an earlier run's
`CAND-015`-labeled candidate, over its **full 8-covariate adjustment-eligible pool** (not the
2-variable oracle set held fixed in this task): additive regression showed near-zero attenuation
(`157.2`→`158.9` EUR), while an unrestricted, coverage-floor-ignoring 8-covariate joint
stratification drove the effect down to `~47.7` EUR — attributed there to interaction structure
additive regression cannot capture. This task's regression test uses the fixed 2-variable oracle
set (never re-chosen, per this task's own constraint) and finds the same qualitative pattern:
regression and stratification agree with each other, both leaving the residual essentially intact,
when restricted to the same 2 covariates.

**Conclusion so far: neither binning granularity nor estimator family (stratification vs.
regression) is the driver of `T04`'s survival.** Both estimator variants, tested independently, land
within noise of the shipped result. This directly weighs against, not for, "the estimator's own
mechanics are insufficient" as the primary explanation — the estimator computes, consistently and
correctly across two different standard forms, what limited signal the fixed 2-variable oracle set
actually carries.

### 2.4 What actually explains the residual: a P06-overlap decomposition

`CAND-015`'s own hidden-ground-truth trap (`T04`) has `direct_effect: 0` — `payment_method=
bank_transfer` has **no genuine causal effect on its own**; its entire apparent effect is,
by the benchmark's own construction, attributable to confounding by `destination`/
`booking_lead_days`. But a genuine causal pattern also exists in this data — `P06` ("Tokyo urgent
bank transfers", `rule: destination=Tokyo AND booking_lead_days<10 AND payment_method=bank_transfer`,
configured effect ≈300 EUR/booking) — and `CAND-015`'s exposed population partially overlaps it.

Decomposing `CAND-015`'s raw `166.5` EUR development-split effect by whether each exposed record
also satisfies `P06`'s true rule:

| Subset | n | Weighted contribution to raw effect (EUR) |
|---|---:|---:|
| Overlaps `P06` (genuine causal signal) | 42 | 51.0 |
| Does not overlap `P06` (pure confounding per `direct_effect=0`) | 964 | 115.4 |
| **Total** | 1006 | **166.4** (≈ matches raw `166.5`) |

**If the oracle adjustment worked perfectly**, it should remove the entire "does not overlap"
contribution (`115.4` EUR, which by the trap's own construction is 100% attributable to
`destination`/`booking_lead_days` confounding) and leave only the genuine `P06` signal (`51.0`
EUR) — an ideal adjusted effect near `~51` EUR. **The observed oracle-adjusted effect is `154.1`
EUR — a reduction of only `12.4` EUR, roughly 11% of the theoretically-removable confounding
component.** Even the correct, complete, fully-achievable 2-variable oracle set removes only a
small fraction of the bias it should, by the trap's own synthetic construction, be able to remove
in full.

This is independently corroborated by `ADR-043`'s own historical number: its unrestricted
8-covariate joint stratification landed at `~47.7` EUR — close to this decomposition's independently
computed `51.0` EUR "genuine signal only" estimate, via a completely different method (raw-subset
decomposition here vs. full-interaction stratification there). Two independent methods converge on
approximately the same "what a truly complete adjustment would show" figure, well below the
`154`–`159` EUR every 2-variable-oracle-set estimator variant in §2.2/§2.3 actually produces.

### 2.5 Isolating what the 2-variable oracle set is missing: a pure-`T04` counterfactual

If `CAND-015`'s own second condition (`discount_rate>=0.05`) were *not* compounded on — i.e. testing
the trap's bare `apparent_feature` (`payment_method==bank_transfer` alone) under the identical
oracle set — does it survive?

**No.** Raw effect `66.9` EUR (much smaller than `CAND-015`'s `166.5` — compounding with
`discount_rate` is what concentrates the effect), oracle-adjusted `51.2` EUR, **E-value `1.32`**
— already below the `1.5` floor on `G06`'s own terms, before `G05` (multiple comparisons) also
independently rejects it. `policy_readiness=experiment_only`, not `shadow_policy`. **The pure trap,
without `CAND-015`'s own second condition, does not reach a disqualifying state at all, even
without needing G05 to stop it.**

### 2.6 The missing ingredient, isolated directly: a `discount_rate` hypothetical

`discount_rate` — `CAND-015`'s own second condition feature — is structurally excluded from its real
adjustment set by `G02`'s circularity guard, and is not part of `T04`'s own documented
`confounded_by` list (that list characterizes only the trap's single `apparent_feature`,
`payment_method=bank_transfer`, not the compound candidate `CAND-015` search actually produced).
**Diagnostic only, mirroring `TASK-075` §2's own precedent for exactly this kind of counterfactual
(never a proposal to bypass `G02` for real):** adjusting jointly for `booking_lead_days`,
`destination`, **and** `discount_rate` —

| Set | Coverage | Adjusted harm (EUR) | Attenuation | E-value | Gate `PASS`? |
|---|---:|---:|---:|---:|---|
| Oracle only (`booking_lead_days`, `destination`) | 1.00 | 154.1 | 0.07 | 1.70 | yes |
| Oracle + `discount_rate` | 0.98 | **79.1** | **0.52** | **1.43** | **no** |

Adding `discount_rate` alone flips **both** the attenuation gate (`0.52 > 0.50` ceiling) and the
E-value gate (`1.43 < 1.5` floor) to `FAIL`. The resulting adjusted effect (`79.1` EUR) also lands
close to the `51.0`–`47.7` EUR "genuine signal only" range independently triangulated in §2.4.

### 2.7 Branch 1 conclusion — architectural attribution

**`T04`'s survival is not primarily an estimator-mechanics defect.** Two independent lines of
evidence rule that out: (a) binning granularity moves the result only slightly, never near either
threshold (§2.2); (b) a completely different, standard estimator family (additive regression)
reproduces the stratified result almost exactly on the same fixed inputs (§2.3). The estimator
faithfully and consistently computes what limited adjustment power a 2-variable set carries.

**What actually drives the survival is that `CAND-015`'s own second condition feature
(`discount_rate`) is itself strongly associated with the outcome, and is structurally invisible to
any adjustment set — not because of the cardinality cliff (`TASK-075`), not because `G06`'s
selection logic failed, but because it is literally part of the candidate's own condition
(`G02`'s circularity guard, correct and untouched) and, separately, is not part of `T04`'s own
documented trap confounders at all (the trap's ground truth characterizes `payment_method=
bank_transfer` in isolation, not the compound rule search actually produced).** §2.5 shows the pure
trap does not survive without this compounding; §2.6 shows that if this one variable could be
adjusted for, the candidate would fail on both remaining gates.

**This is the same general mechanism Branch 2 formally characterizes for `T03` (§3), discovered
independently via Branch 1's own estimator-focused investigation.** The architectural level a future
fix would need to address, for `T04` specifically, is **not** the estimator's own computational form,
and evidence here does not support recalibrating thresholds (§2.2's sweep shows the current E-value
floor and attenuation ceiling correctly separate the "oracle-set-only" and "oracle-set-plus-the-
missing-variable" cases with a wide margin, not a knife-edge one) — it is the same **candidate-
generation semantics / structural-exclusion** level Branch 2 attributes `T03`'s survival to.

## 3. Branch 2 — `T03`: candidate-condition/confounder entanglement

### 3.1 Method

For each trap's single-condition `apparent_feature`, this task computes `discovery.engine`'s real,
unmodified `_development_score` for the bare singleton, then — for every `DECISION_TIME`
adjustment-eligible pool feature — the score of compounding that feature's own best-scoring real
atom (from `engine._atoms`, the same atom-generation code `discover_candidates` itself calls) onto
the singleton as a 2-condition rule. No `discovery.engine` code is modified or called with altered
logic; every call is exactly what `discover_candidates` itself would compute.

**Base-eligibility constraint, consistent with prior findings, not a limitation of this method:**
only `T03`'s and `T04`'s bare `apparent_feature` singletons are eligible under `_eligible` (raw
`harm_per_booking > 0`, `discover_candidates`'s own sign convention) — `T01`, `T02`, `T05`'s
singletons all show the *opposite* raw sign in the development split and are therefore never
eligible base rules at all. This matches `TASK-075`'s own independent finding that `T01`/`T02`/`T05`
have never appeared as a real persisted candidate in this project's official history — confirmed
here from a completely different angle (raw score eligibility, not adjustment-set selection).

### 3.2 Per-trap compounding sweep

**`T03`** (base singleton `acquisition_channel=paid_search`, score `3966.9`): `2/15` pool features
increase the score when compounded on. The single largest booster is `discount_rate ge 0.08`+
(`+1508.6`, the actual real `CAND-014` condition — see §3.3); `booking_lead_days lt 23.0` is the
only other booster (`+429.9`). Of `T03`'s own 3 ground-truth confounders (`customer_type`,
`discount_rate`, `installments`), only `discount_rate` increases score — `installments` (`-102.3`)
and `customer_type` (`-1115.7`) both *decrease* it.

**`T04`** (base singleton `payment_method=bank_transfer`, score `2585.0`): `5/15` pool features
increase the score. Ranked: `discount_rate ge 0.12` (`+2664.0`, the largest booster by a wide
margin — and this is `CAND-015`'s own real second condition), `booking_lead_days lt 23.0`
(`+1518.7`, a true `T04` confounder), `destination eq Tokyo` (`+396.1`, the other true `T04`
confounder), `acquisition_channel eq paid_search` (`+202.2`), `installments ge 3.0` (`+88.9`).
Both of `T04`'s ground-truth confounders increase score; so do 3 non-confounder features,
`discount_rate` chief among them.

### 3.3 `CAND-014` direct trace

The real, historical `CAND-014` (`acquisition_channel==paid_search AND discount_rate>=0.08`) is
exactly the top-scoring compound rule the sweep above found: singleton score `3966.9` → compound
score `4807.1` (delta `+840.2`, ≈21% higher), despite `n_exposed` shrinking from `1335` to `645`
and the `0.15`-per-condition complexity penalty. `harm_per_booking` nearly doubles
(`108.6`→`217.7` EUR) — that increase, driven by `discount_rate ge 0.08` concentrating a
higher-harm subgroup, more than compensates for the smaller population and the complexity penalty
in `_development_score`'s formula. **This is not a coincidence of hindsight — the sweep above shows
it is the highest-scoring available compounding move among all 15 pool features, found by the same
generic sweep applied identically to every trap.**

### 3.4 Aggregate: is being a confounder associated with being score-increasing?

Across all `5+15=20` compounding trials from `T03` and `T04` combined (`T01`/`T02`/`T05` excluded,
§3.1): **confounder trials increase score `60%` of the time (`3` of `5`); non-confounder trials
increase score `16%` of the time (`4` of `25`)** — confounders are roughly `3.75x` more likely to be
score-increasing than non-confounders, in this (small, `n=5` vs `n=25`, disclosed limitation) sample.

**But the relationship is not deterministic in either direction**, and this matters for the answer
below: `T03`'s `customer_type` and `installments` (both real confounders) *decrease* score;
`T04`'s `discount_rate` and `T03`'s `booking_lead_days` (both *not* that trap's own documented
confounder) *increase* score. `booking_lead_days` is instructive on its own: it is a true confounder
for `T01`/`T04`/`T05` but not `T03`, and it still boosts `T03`'s score — showing the mechanism is
not "the search detects `T03`'s specific confounders," it is that **any feature with a strong
enough raw (unadjusted) association with the outcome in the development split will boost score when
compounded on, and true confounders are simply more likely than an average feature to have that
property, because "correlated with the outcome" is the shared defining property of both "good
candidate signal" and "confounder" — the score cannot distinguish the two by construction.**

### 3.5 Formal characterization and the direct answer

**The general class:** a true confounder `C` for a base condition `X` becomes structurally
irremovable for a candidate rule `X AND C` (rather than `X` alone) whenever (a) `C`'s raw,
unadjusted association with the outcome is strong enough that adding it as a second condition
increases `_development_score` (§3.2–3.4 show this occurs for roughly 1-in-5-to-1-in-3 available
features per trap, confounders somewhat more often than non-confounders but not exclusively), and
(b) the resulting compound rule survives `discover_candidates`'s beam/diversity/relevance-floor
selection into the final reported set (not tested exhaustively here, but `CAND-014` and `CAND-015`
are both real, historical instances of exactly this outcome). Once both hold, `G02`'s circularity
guard — correct and general, never in question here — permanently and structurally excludes `C`
from that candidate's own adjustment set, regardless of estimator quality, oracle-set completeness,
or `G06` selection logic, because `C` is not merely unselected, it is definitionally part of the
thing being tested.

**Direct answer: yes.** Search can and, in this project's own official-run history, twice has
(`CAND-014`/`T03`, `CAND-015`/`T04` — the only two traps whose apparent features were ever eligible
to become real candidates at all, §3.1) produced an apparent pattern that becomes statistically
irremovable downstream specifically because ordinary, unmodified greedy score-maximization folded a
strongly outcome-associated variable into the rule's own condition set. **This is a systematic
property of how `_development_score` composes candidate conditions — a raw, un-adjusted function of
subgroup mean-difference and population size that cannot distinguish a genuinely narrower causal
subgroup from a subgroup narrowed by conditioning on a confounding-correlated variable — not an
isolated `T03`-specific occurrence.** It is also not a guarantee: most pool features in this sweep
(`31/35` non-`CAND-014`/`CAND-015` trials) *decrease* score when compounded on, so the majority of
possible search paths do not exhibit it; the two traps that ever produced a real candidate both did.

### 3.6 Branch 2 conclusion — architectural attribution

The mechanism operates entirely inside `_development_score`'s own well-documented, unadjusted
scoring formula (`docs/analytics/discovery-engine-v0.md`, engine.py's own docstrings: "It performs
no inference and makes no causal claim") — nothing here is a defect in that formula relative to its
stated purpose (ranking raw, descriptive candidate strength on development data only); it is a
structural consequence of composing multi-condition rules from a raw, unadjusted score with no
knowledge of confounding, combined with `G02`'s (separately correct) circularity guard downstream.
**The architectural level a future fix would need to address is candidate-generation semantics —
specifically, how `discover_candidates` composes multi-condition rules blind to whether an added
condition is itself an outcome-correlated (and therefore potentially confounding) variable — not
`G06`'s selection algorithm** (which, per `TASK-075`, never even sees `discount_rate` for either
`CAND-014` or `CAND-015` — it is excluded before selection ordering runs at all), and not the
estimator (Branch 1, §2.7, shows it computes correctly on whatever adjustment set it is given).

## 4. Branch 3 — `T05`: overlap ceiling

### 4.1 Where the coverage collapse actually happens

`T05`'s counterfactual (`manual_exception==true`, `n_exposed=338` development-split) against every
non-empty subset of its complete, correct 4-variable oracle set
(`booking_lead_days`, `destination`, `party_size`, `trip_duration_days`):

| Size | Best subset(s) | Coverage | Usable/total joint cells |
|---:|---|---:|---|
| 1 | any single variable | 1.000 | 3–5 / 3–5 |
| 2 | any pair except `(booking_lead_days, destination)` | 1.000 | 12–20 / 12–20 |
| 2 | `booking_lead_days, destination` | 0.988 | 19/20 |
| 3 | `destination, party_size, trip_duration_days` (best) | 0.849 | 32/60 |
| 3 | `booking_lead_days, destination, party_size` | 0.828 | 30/60 |
| 3 | `booking_lead_days, party_size, trip_duration_days` | 0.825 | 28/48 |
| 3 | `booking_lead_days, destination, trip_duration_days` (worst) | 0.675 | 33/80 |
| **4** | **all four (the complete oracle set)** | **0.178** | **10/240** |

Every 2-variable subset clears the `0.50` floor comfortably (`≥0.988`); every 3-variable subset
still clears it (`0.675`–`0.849`); the full 4-variable set collapses to `0.178` — a sharp, one-step
cliff, not a gradual decline. This confirms `TASK-078`'s finding as a genuine data-support property,
not an artifact of which 3-or-4 variables happen to be chosen: **no 4-variable combination of these
oracle confounders could jointly clear the floor on this sample**, only some 3-variable subsets can,
and only barely.

### 4.2 Why: joint cells vastly outgrow the exposed population

`n_exposed=338`; `MIN_STRATUM_CELL=5` per side means, even under perfectly even allocation across
cells (the best case any real allocation could ever achieve), at most `338 // 5 = 67` joint cells
could have any usable occupancy at all. The full 4-variable joint space has `240` cells — **more
than 3x the theoretical maximum this population could ever fill**, even before accounting for real,
uneven allocation (which makes the effective ceiling lower still: the actual run has only `10`
usable cells against that `67`-cell theoretical bound). This is a hard arithmetic ceiling of
population size versus joint cardinality, not a defect in the greedy selection order or the
estimator's own logic — `TASK-078`'s finding, reproduced here at the level of the underlying cell
arithmetic rather than only the top-line coverage number.

### 4.3 Recommendation: a named identifiability-ceiling treatment, distinct from ordinary FAIL

**This class of case is not the same as an ordinary `G06` `FAIL`.** An ordinary confounding-gate
failure (attenuation, sign-flip, or E-value below floor) means: *an adjustment was computed, and it
did not support the candidate.* `T05`'s case means something categorically different: *no adjustment
for its known, correct, complete confounder set could be computed with any statistical reliability
at all, on this data, regardless of how it is chosen or estimated.* Both currently collapse into the
identical `not_ready`/`G03_SAMPLE_ADEQUACY`-or-`G06`-`FAIL` outcome (`TASK-078` §4), which is safe
(the trap is correctly rejected either way) but loses information a downstream reader — a human
reviewing why a finding was rejected, or a future selector deciding whether to keep trying — would
benefit from having distinguished. Grounding this in the contract's own existing taxonomy
(`PolicyReadiness`: `not_ready`/`experiment_only`/`shadow_policy`/`high_confidence`; `EvidenceLevel`:
`descriptive`/`predictive`/`adjusted_observational`/`quasi_causal`/`experimental`) — neither
enumeration currently has a slot for "the confounders are known but jointly inestimable on this
sample," a genuinely distinct status from every existing level and readiness value, which all
describe *what was found*, not *why adjustment was structurally impossible to attempt reliably*.

**A named "identifiability ceiling" outcome, distinct from `not_ready`, is a coherent addition to
this taxonomy** — it would let a reviewer distinguish "this pattern's raw effect was real but weak"
(`G03`) or "this pattern's confounders were checked and found genuinely inadequate to explain the
effect" (ordinary `G06` `FAIL`) from "this pattern's confounders could not be jointly checked at
all, at this population size" (the ceiling). This is a validation-methodology characterization, not
a scoped design — whether and how to add it is left to whatever follow-on task takes it up (§7).
**This is explicitly not a recommendation to lower the `0.50` coverage floor** — the floor is doing
exactly its job here (correctly refusing to trust a `10`-of-`338`-usable-record adjustment); the
recommendation is about how the *rejection* is labeled and surfaced, never about relaxing the
*rejection itself*.

### 4.4 Should a future selector know this in advance?

**Yes, in principle, and cheaply.** `confounder_stratum_coverage` is a fast, closed-form function of
the frame and a candidate confounder set — computing it for a proposed set costs the same whether
computed before or during selection; nothing about it requires the estimator's slower paths
(bootstrap, E-value, etc.). §4.1's subset sweep demonstrates directly that the *achievable coverage
ceiling for a given population size and set of marginal cardinalities* is itself a computable,
inspectable property, independent of which specific covariates end up chosen — the sharp 3-to-4
variable cliff here is a property of `n_exposed=338` and these variables' cardinalities, not of
which variable is added seventh or eighth (the cardinality-cliff mechanism `TASK-075` diagnosed).
**A future selector could, in principle, check an achievable-coverage ceiling for the sample's own
scale before or during selection, so a small-`n_exposed` candidate is recognized as unable to
support deep joint adjustment before effort is spent trying** — named here as a property worth
knowing, not designed, scoped, or authorized as a change by this task.

### 4.5 Branch 3 conclusion

`T05`'s `0.18` joint coverage at the full oracle set is confirmed, at the underlying cell-arithmetic
level, as a genuine identifiability ceiling of this dataset at this candidate's population size —
not a selection-algorithm artifact (§4.1's per-subset sweep rules out order-dependence: no
4-variable combination could pass, only some 3-variable ones can). The recommended treatment is a
named, distinct evidence/readiness outcome for this class of case (§4.3) and, separately, advance
awareness of the achievable-coverage ceiling as a property a future selector could reasonably use
(§4.4) — neither is a fix, and neither touches the `0.50` floor itself.

## 5. Preregistered cross-branch separation — checked explicitly

- **`T04`'s failure is not treated as proof threshold calibration is the defect.** §2.2/§2.6 show
  the opposite: the E-value floor and attenuation ceiling correctly and with a wide margin separate
  the "2-variable oracle only" case (comfortably passing) from the "2-variable oracle plus the
  missing variable" case (failing both thresholds cleanly, not marginally) — evidence *for* the
  thresholds working as intended, not against them.
- **`T03`'s finding does not lead to a recommendation to ban confounder-like features from
  conditions.** §3.4/§3.5 explicitly report the relationship is probabilistic, not deterministic
  (some real confounders decrease score; some non-confounders increase it) — the finding is a
  mechanism characterization, and §3.6 attributes it to candidate-generation semantics generally,
  not to any specific feature-exclusion rule.
- **`T05`'s ceiling does not lead to a recommendation to lower the coverage floor.** §4.3 states this
  explicitly: the floor is doing its job; the recommendation is entirely about labeling/surfacing
  the rejection, never about relaxing it.
- **Mechanism first, design second, honored throughout:** every branch's §2.7/§3.6/§4.5 conclusion
  states an architectural attribution or named treatment, not a specific fix, gate change, or code
  edit.

## 6. Completion criterion applied exactly

- **`T03`:** first sufficient survival mechanism established (§3.5) — a true confounder's own strong
  raw outcome-association can cause it to be selected by ordinary greedy score-maximization as an
  additional rule condition, at which point `G02`'s (correct) circularity guard permanently excludes
  it from adjustment. Architectural level: **candidate-generation semantics** (`discovery.engine`'s
  condition composition), not `G06`, not the estimator (§3.6).
- **`T04`:** first sufficient survival mechanism established (§2.7) — the same general mechanism as
  `T03`, discovered independently via the estimator-focused branch: `CAND-015`'s own second
  condition (`discount_rate`) is both outcome-associated and structurally inadjustable, and is not
  even part of the trap's own documented confounder list (a scope gap between "confounders of a
  trap's single apparent feature" and "confounders relevant to whatever compound candidate search
  actually produces"). Architectural level: **candidate-generation semantics**, not the estimator
  (ruled out directly by two independent estimator-variant tests, §2.2/§2.3), not primarily
  threshold calibration (§2.2/§2.6 show thresholds separating the two cases cleanly, not marginally).
- **`T05`:** named validation-treatment recommendation delivered (§4.3: a distinct
  "identifiability-ceiling" outcome, not a fix; §4.4: advance overlap-awareness named as a property a
  future selector could use, not designed).

**Success is the correct, evidenced architectural attribution per branch — achieved above — not a
change in any trap's pass/fail outcome.** No trap's verdict changed: `T03` and `T04` still reach
`shadow_policy` under their oracle sets exactly as `TASK-078` found; `T05` still fails coverage
exactly as `TASK-078` found. Nothing in this document alters that.

## 7. What a future follow-on (`ADR-071` step 3 `G06` fix-design, or any other) would need to cover — named, not designed

Per this task's own hard rule, nothing below is a proposal, a scoped fix, or an authorized change:

- **For `T03`/`T04` (candidate-generation semantics level):** whether and how `discovery.engine`'s
  condition-composition step should account for a candidate condition's own potential confounding
  role — this reaches into `discovery.engine`'s scoring/composition design (`_development_score`,
  `_atoms`, the beam/diversity selection chain) and is explicitly the kind of change `ADR-072`
  blocks until this task is reviewed. Any such design must be validated against the same negative/
  positive-control discipline `TASK-075` §5 and `ADR-071`'s acceptance matrix already require (all 5
  traps, the 6 real historical `PASS` candidates, `T02`'s separate vocabulary gap) — not just
  `T03`/`T04`'s specific identities, matching every prior task in this chain.
- **For `T04` specifically:** the scope gap between a trap's documented `confounded_by` (defined for
  a single `apparent_feature`) and the actual confounding-relevant variable set for whatever
  multi-condition candidate search actually produces — worth this follow-on's own explicit
  consideration, since a future selector or scoring change aimed at `T03`'s mechanism should be
  checked against this same shape of gap, not just `T03`'s own case.
- **For `T05` (validation-methodology level):** whether to add a named identifiability-ceiling
  evidence-level/readiness outcome distinct from `not_ready` (§4.3), and whether/how a future
  selector should compute or consult an achievable-coverage ceiling in advance (§4.4) — both are
  validation-contract and/or selector-design questions, not `discovery.engine` questions, and
  neither is scoped here beyond what §4.3/§4.4 name.
- **Positive-control preservation** (the six real historical `PASS` candidates) remains out of scope
  for this task, exactly as `TASK-078` §9 already stated for the layer before it — carried forward
  unchanged to whichever design task eventually opens.

## 8. What this task did not do

No threshold in `ValidationThresholds` was read as wrong and none is recommended for change; `G02`
was read about extensively but never bypassed except in two explicitly disclosed, clearly-labeled
diagnostic-only hypotheticals (§2.6) that mirror `TASK-075` §2's own established precedent for this
exact kind of counterfactual, and neither hypothetical is proposed as a real adjustment-set change.
No replacement selection rule, estimator change, scoring-function change, or `discovery.engine`
change is proposed, sketched, or implied anywhere above beyond the diagnostic naming in §7. `G06`,
`apply.py`, `discovery.engine`, and `validation-contract.md` are untouched on disk. No trap's
pass/fail verdict was recomputed or changed. No follow-on `TASKS.md` entry is opened by this task —
§7 names scope for the orchestrating session/founder to open, per this task's own hard rule.
