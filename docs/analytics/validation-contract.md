# Validation and Evidence Contract v1.2.0

**Owner:** Statistics · **Task:** TASK-018 · **Status:** approved for use by TASK-019 onward

This contract is preregistered: every rule and threshold below was fixed before any candidate
pattern existed. Its executable half is `packages/analytics/src/policy_analytics/validation/`
(`contract.py` = vocabulary and thresholds, `grading.py` = decision functions, `report.py` = output
format). Prose and code must agree; the code is authoritative for grading, this document is
authoritative for intent.

Nothing here estimates anything. Applying these rules to persisted candidates is TASK-019.

**v1.1.0 change note (2026-08-14, ADR-014/ADR-015).** Gate G05's p-value source changed; see §4a.
Nothing else in this contract changed — same gates, same thresholds (including `fdr_alpha = 0.10`),
same evidence-level and readiness rules. The one 2026-08-14 dry run graded under v1.0.0
(`artifacts/validation/task-019-validation-report.json`) keeps that grading; it is not re-graded
here. §2's rule against post-hoc threshold tuning still applies — this is a versioned estimator
fix for a defect proven independent of any candidate's data, not a threshold adjusted because a
result was inconvenient. See §4a for the full account.

**v1.2.0 change note (2026-08-20/21, `ADR-036`/`ADR-042`, `TASK-063`).** Gate G06's adjustment set
generalized from a fixed pair (`manager`, `supplier`) to every eligible `DECISION_TIME` covariate
the development split can jointly support; see §4b. Nothing else in this contract changed — G05
and every other gate, threshold, and evidence/readiness rule are exactly as v1.1.0 left them.
Findings graded under v1.1.0 or earlier keep that grading; they are not re-graded here.

## 1. Purpose and standing assumption

Discovery produces candidate patterns. A candidate is a *search result*, not a finding. The default
assumption is that a candidate is an artifact of leakage, confounding, selection, or the size of
the search, and the candidate must earn its way out of that assumption.

The standing epistemic position of this product: **historical booking data can support at most
`adjusted_observational_association`.** Levels 4 and 5 require a design, not more adjustment, and
are unreachable without an intervention or a natural experiment. Any product surface implying
otherwise is a defect.

## 2. Versioning and preregistration

- Thresholds live in `ValidationThresholds`; the contract version is `CONTRACT_VERSION`.
- Changing any threshold requires a new contract version and re-validation of every finding graded
  under the previous one. Findings carry the version that graded them.
- Validation may only run against candidates already persisted with `status=PERSISTED` and a
  timestamp preceding the validation run. Re-grading the same candidates under new thresholds is a
  new run and a new family, and is disclosed as such.
- Thresholds are never tuned after seeing results. If a threshold turns out to be wrong, it is
  changed deliberately, versioned, and everything is re-graded — not adjusted for one candidate.

## 3. Inputs required before validation can run

| Input | Source | Blocking |
|---|---|---|
| Leakage-safe analytical dataset with a version | TASK-011 (Data Engineer) | yes |
| Feature-timing classification for every column | TASK-008 (Data Engineer) | yes |
| Chronological development / validation / future-holdout splits | TASK-012 (Data Engineer) | yes |
| Versioned outcome definitions and direction | TASK-013 (Statistics) | yes |
| Persisted candidates with conditions, support, and raw effects | TASK-015/016/017 (ML Discovery) | yes |
| Number of hypotheses discovery actually evaluated | discovery run manifest | yes, for gate G05 |
| Declared DAG and minimal adjustment set per candidate | Statistics, before estimation | yes, for level 3 |
| Clustering key (manager, supplier, customer) | analytical dataset | yes, for gate G04 |

A missing input is a `NOT_EVALUATED` gate, which the contract treats exactly like a failure. An
unrun check is never a passed check.

## 4. Estimation rules

**Comparison group.** Every candidate is compared against the complement of its condition within
the same cohort and window, never against a hand-picked baseline.

**Uncertainty.** Cluster bootstrap over the declared clustering key, `bootstrap_resamples = 2000`
replicates, run seed recorded, percentile interval at 95%. Booking-level i.i.d. resampling is
prohibited: bookings share managers, suppliers, and customers, and independence assumptions
manufacture significance. A point estimate without an interval is not reportable.

**p-values (CONTRACT_VERSION >= 1.1.0).** The p-value gate G05 corrects is
`normal_approx_two_sided_p(point_estimate, standard_error)` — a Wald-type p-value using the
cluster-bootstrap standard error (`bootstrap_standard_error` on the same replicates used for the
confidence interval) as the reference scale. See §4a for why this replaced the empirical
`bootstrap_two_sided_p` inversion as G05's source. `bootstrap_two_sided_p` remains available and
correct for small-family or purely diagnostic use; it is simply no longer what G05 corrects.

**Multiple comparisons.** Benjamini–Hochberg control of the false discovery rate at
`fdr_alpha = 0.10` across the family. **The family is the number of hypotheses discovery
evaluated, not the number it reported.** A search over 500 rules that returns its best 15 has a
family of 500; `benjamini_hochberg_adjusted(..., family_size=500)` enforces this. When the
evaluated count is unavailable, no candidate can pass G05 and nothing exceeds level 1.

**Adjustment (CONTRACT_VERSION >= 1.2.0, §4b).** Joint stratification over every eligible
`DECISION_TIME` covariate outside the candidate's own condition set, greedily included in
ascending-cardinality order up to whatever the development split's `confounder_stratum_coverage`
can support — not a single hand-picked minimal set. The selection *rule* (cardinality order,
coverage floor) is fixed before any candidate is evaluated and applies identically to every
candidate; the resulting *set* of columns actually used is per-candidate and recorded in the
report (`adjustment_columns_considered`/`adjustment_columns_used`). Adding covariates after seeing
the estimate is still prohibited — the rule, not a person, chooses the set.

**Unmeasured confounding.** Every adjusted estimate reports an E-value. The E-value must be at
least `min_e_value = 1.5` and must exceed the strongest measured confounder–outcome association;
otherwise a confounder no stronger than one already in the data could explain the whole effect.

## 4a. The G05 p-value defect and its fix (v1.1.0, ADR-014/ADR-015)

### The defect

Contract v1.0.0 computed G05's p-value by inverting the empirical bootstrap distribution
(`bootstrap_two_sided_p`): count what fraction of `B` cluster-bootstrap replicates fall on the
opposite side of zero from the point estimate, and floor the result at `1 / (B + 1)` because a
resampling procedure with `B` replicates cannot report finer resolution than that.

The first real application of this contract — the 2026-08-14 `TASK-019` dry run against 15 frozen
`TASK-015` candidates — found this floor structurally incompatible with the family sizes this
system actually produces. At `B = bootstrap_resamples = 2000`, the floor is `1/2001 ≈ 0.0005`.
Benjamini-Hochberg requires, at minimum, a raw p-value at or below `alpha · rank / family_size`
to survive; the most lenient case (`rank = 1`) requires `p ≤ alpha / family_size`. Setting the
floor equal to that bound and solving for `family_size` gives the crossover:

```
floor > alpha / family_size
family_size > alpha / floor = alpha · (B + 1)
            = 0.10 × 2001 ≈ 200
```

**Once `family_size` exceeds roughly 200, no candidate can pass G05 under contract v1.0.0, no
matter how large its true effect is** — because every candidate whose replicates unanimously
agree in sign (the case for a genuinely strong effect) hits the exact same floor, and the floor
itself is already too coarse. The dry run's `family_size` was 6,945 — about 35× past that
crossover. All 15 candidates landed exactly at the floor and all 15 failed G05, capping every one
at `LEVEL_1_DESCRIPTIVE` regardless of effect size. A diagnostic normal-approximation p-value
computed alongside (same bootstrap standard error) put every candidate below `1e-6` — several
orders of magnitude past what BH would have required — strongly indicating the G05 failures were
an artifact of estimator resolution, not weak evidence. `tests/analytics/test_g05_multiplicity_fix.py`
reproduces this mechanism directly: two synthetic replicate sets, one "modest" and one
astronomically larger, produce the *identical* p-value under the old method, and a floored p-value
tied across 15 synthetic candidates fails BH at `family_size = 6945` exactly as observed.

This defect is a property of the estimator and the family-size regime, not of any candidate's
data. It was found and fixed without opening `hidden_ground_truth.json` or
`synthetic_benchmark.py`, and the fix does not reference or depend on any specific candidate's
pattern.

### The replacement method

**G05's p-value is now `normal_approx_two_sided_p(point_estimate, standard_error)`**
(`packages/analytics/src/policy_analytics/validation/grading.py`): a two-sided Wald test using the
cluster bootstrap's *standard error* (`bootstrap_standard_error`, the sample standard deviation of
the same replicate set) rather than an empirical tail count. Concretely:

```
z = |point_estimate| / standard_error
p = erfc(z / sqrt(2))          # via math.erfc, not 1 - math.erf(...) — see precision note below
```

This is the simplest defensible fix, preferred over the alternatives considered:

- **Increase `bootstrap_resamples` until the floor clears the requirement empirically.** Rejected:
  clearing even the 2026-08-14 dry run's `family_size = 6945` at `rank = 1` needs
  `B > (2001 × alpha⁻¹ × family_size⁻¹)⁻¹`-scale replicate counts — on the order of 50,000+ per
  candidate per split — expensive without deeper optimization, and it does not fix the underlying
  problem for a larger future search; the crossover simply moves.
- **A more sophisticated resampling-based tail estimate** (importance-sampled bootstrap,
  Edgeworth-corrected bootstrap, saddlepoint approximation). Rejected as unnecessary complexity:
  the sample sizes this system operates at (hundreds to thousands of exposed records per
  candidate) are exactly the regime the central limit theorem is built for, so a plain normal
  approximation on the bootstrap's own standard error is already well justified, auditable in a
  few lines, and requires no new dependency.
- **The normal approximation, as implemented.** Chosen: simplest option that is mathematically
  sufficient (next section), keeps the bootstrap itself — clustering, replicate count, seed — as
  the sole source of uncertainty quantification, and only changes how a replicate set becomes a
  p-value.

**Precision note.** The tail probability is computed via `math.erfc(z / sqrt(2))`, not
`1 - math.erf(...)` — this matters. The naive `2·(1 - 0.5·(1+erf(x)))` form suffers catastrophic
cancellation once `erf(x)` rounds to exactly `1.0` in double precision, which happens already
around `z ≈ 8.3`, giving a *false* floor barely better than the defect being fixed.
`math.erfc(x) = 1 - erf(x)`, computed directly without the cancellation, remains accurate down to
underflow at roughly `z ≈ 38` (`p ≈ 1e-315`) — see the resolution proof below and
`tests/analytics/test_g05_multiplicity_fix.py::test_normal_approximation_has_no_resolution_floor`,
which pins that the two formulations diverge exactly where expected.

### Mathematical sufficiency of the resolution

The replacement must resolve p-values well below whatever any realistic future `family_size`
requires. Requiring a comfortable safety margin, take `family_size = 100,000` — roughly 15× the
dry run's search size — as a generous upper bound on how large a discovery search this system
might plausibly run. The most lenient BH threshold (`rank = 1`) at that scale is:

```
p_required = alpha / family_size = 0.10 / 100,000 = 1e-6
```

Solving `erfc(z/√2) = 1e-6` gives `z ≈ 4.89` — under five standard errors, comfortably within
what a several-hundred-to-several-thousand-record cluster bootstrap on a real effect produces (the
dry run's diagnostic p-values corresponded to `z` in the 8–20+ range). `math.erfc` stays accurate
and strictly decreasing out to roughly `z ≈ 38` before underflowing to exactly `0.0` — which is
still the *correct* answer for a pass/fail comparison against any positive threshold, not a wrong
value. That leaves roughly **33 standard errors, and on the order of 300 decades of p-value
resolution, of headroom** beyond what a `family_size = 100,000` search would ever require at
`rank = 1`. `tests/analytics/test_g05_multiplicity_fix.py::test_normal_approximation_resolves_far_below_bh_requirements_at_any_realistic_family_size`
pins this derivation as an executable check, not just prose.

### Migration from v1.0.0

- Findings graded under `CONTRACT_VERSION = "1.0.0"` (the 2026-08-14 dry run) keep that grading.
  They are not, and must not be, retroactively re-graded to v1.1.0; the frozen artifact's own
  `validation_contract_version` field records which version produced it, permanently.
- Any *new* validation run automatically uses v1.1.0 (`CONTRACT_VERSION` is a single source of
  truth in `contract.py`) and must be labeled as such. Comparing a v1.0.0 result to a v1.1.0
  result — e.g. claiming a candidate "now passes" — must say explicitly that the contract version
  changed, not just that the candidate did.
- No other gate, threshold, or evidence/readiness rule changed in this version. A candidate that
  failed a gate other than G05 under v1.0.0 will still fail it under v1.1.0.
- Applying v1.1.0 to the same (still not blind-protocol-compliant, still founder-blocked)
  `TASK-015` candidate artifact is a live capability of the code as of this fix, but doing so does
  not manufacture validated findings: `TASK-017`/ADR-008 compliance and the founder readiness
  block on `TASK-015`/`TASK-016` are unrelated prerequisites this fix does not touch. `TASK-019`
  stays `IN_PROGRESS` until a genuinely compliant `TASK-017` artifact exists.

## 4b. G06 adjustment-set generalization (v1.2.0, `ADR-036`/`ADR-042`, `TASK-063`)

### The defect

Through v1.1.0, G06's adjustment set was a fixed pair, `("manager", "supplier")`, chosen once by
hand from ordinary booking-domain reasoning before any candidate existed (`ADR-007`'s own
discipline — never picked to fit a result). That discipline was sound; the fixed *set* was not
future-proof. A fixed two-variable set structurally cannot see a confounder outside it, no matter
how well the two chosen variables were reasoned about. `ADR-036` found this gap made concrete:
across four `TASK-060` diversity-search iterations, confounding trap `T03` (real travel benchmark)
reached `PASS`/`shadow_policy` twice, because `T03`'s true confounders are not `manager` or
`supplier` — G06 was never looking in the right place, by construction, regardless of how strong
the search's own candidates were.

### The replacement method

G06's adjustment set is now computed **per candidate**, not fixed once for the whole contract:

1. **Pool.** Every manifest-declared adjustment-eligible `DECISION_TIME` feature except the
   candidate's own condition features (adjusting for the treatment itself is circular — unchanged
   from v1.1.0). Date-like or otherwise unsupported decision-time fields are excluded explicitly
   by the versioned analytical manifest, never by a validation-module column-name list.
2. **Binning.** A numeric pool column with more than 6 distinct values in the development split is
   quartile-binned (4 groups, same index-based quantile convention as `percentile_ci` elsewhere in
   this module); a numeric column with 6 or fewer distinct values (`installments`, `party_size`) is
   used as-is, since binning it further would only discard information. Categorical/boolean columns
   are used as-is.
3. **Greedy, coverage-gated joint stratification.** Pool columns are tried in ascending order of
   their own distinct-value count in the development split (ties broken alphabetically) — a
   dataset-level property fixed before any candidate is evaluated, never a per-candidate or
   per-feature-identity choice. Each column is added to the running joint stratification only if
   doing so keeps the resulting `confounder_stratum_coverage` at or above
   `min_confounder_stratum_coverage` (0.50, the same value the `0.5` literal already used in
   v1.1.0, now named); a column that would push coverage below the floor is left out, and the next
   one (in cardinality order) is tried instead. Low-cardinality columns go first because each
   additional column multiplies the number of joint strata by roughly its own cardinality — trying
   cheap ones first lets more columns fit before the development split runs out of usable strata.

**No gate logic anywhere in this method references `T03`, `acquisition_channel`, or any other
specific feature or trap by name.** The selection rule is a function of cardinality and coverage
only — the same rule runs identically whether or not a candidate happens to be trap-shaped, and
would run identically on a dataset that had never heard of the travel benchmark's specific traps.
`tests/analytics/test_validation_apply.py`'s regression tests use deliberately neutral synthetic
column names (`real_confound`, `irrelevant_a`, `irrelevant_b`) for exactly this reason — proving the
*rule* generalizes, not that it was special-cased for one known trap.

**What did not change:** `MIN_STRATUM_CELL = 5` (both exposed and comparison sides of a stratum),
the E-value check, the attenuation ceiling, the same-sign requirement, and travel's reviewed
heterogeneity role. TASK-066 moved that role from code into the analytical manifest without
changing travel's selected column or results.

### Domain-aware gate inputs (TASK-066)

The selected analytical dataset's `manifest.json` owns a typed `validation_roles` v1.0.0 block:
the adjustment-eligible subset, optional G09 heterogeneity column, optional G11 decision-known
calendar column, clustering column (from the existing `clustering` block), and optional robustness
group/alternative outcome. Every referenced field must have a compatible role in `feature_timing`
and must exist in exactly one hash-verified physical partition. Candidate condition fields must
also exist in that same physical/role contract.

G01 permits only `DECISION_TIME`; `UNKNOWN`, `POST_DECISION`, `OUTCOME`, `IDENTIFIER`, and
`METADATA` fail closed. G06 draws only from the manifest allowlist and always removes the
candidate's own condition fields. A missing reviewed G09 or G11 role produces `NOT_EVALUATED`, not
PASS and not a guessed proxy. Missing manifests, unsupported role-contract versions, unknown
roles, incompatible semantic-role assignments, partition hash drift, and unknown candidate fields
are validation errors. Travel's manifest declares its already-reviewed roles, so validation v1.2.0
semantics and thresholds are unchanged; no validation-contract version bump is required.

### Why greedy-and-stop, not full joint stratification of everything

Naively cross-tabulating *every* eligible covariate at once (rather than growing the set only as
far as coverage allows) would combinatorially fragment the development split into mostly-singleton
strata — `coverage` would collapse toward zero for nearly every candidate, and G06 would fail
almost universally, which is a broken gate, not a stricter one. The greedy, coverage-gated process
is the minimal change that satisfies "adjust for every eligible covariate the sample can actually
support" without needing a new estimation method (multivariate regression, propensity scoring):
`_stratified_adjustment`, the underlying cross-tabulation function, is unchanged from v1.1.0 — only
*how many and which* columns get passed to it, per candidate, is new.

### Real-data confirmation (not just synthetic)

Run against `task-060-iteration-20260820-004` (the last `TASK-060` iteration where trap `T03`
reached `PASS`/`shadow_policy` under v1.1.0's fixed adjustment pair): §5's gate-by-gate detail for
the affected candidate, and whether it is now rejected on the new general grounds rather than by
the search stage simply not proposing it, is recorded in `HANDOFF-058`/`ADR-042` rather than
repeated here, since it is evidence about one specific run, not a property of the contract itself.

### Migration from v1.1.0

- Findings graded under `CONTRACT_VERSION = "1.1.0"` or earlier keep that grading — not
  retroactively re-graded. The frozen artifact's own `validation_contract_version` field records
  which version produced it, permanently.
- Any *new* validation run automatically uses v1.2.0 and must be labeled as such.
- No gate other than G06 changed in this version — including G05, still governed by v1.1.0's
  normal-approximation fix (§4a).
- `CONFOUNDER_COLUMNS` no longer exists as a module constant; `adjustment_columns_considered`
  (the eligible pool) and `adjustment_columns_used` (what the greedy process actually selected) are
  now per-candidate diagnostics fields, not a single run-level constant — a candidate's own report
  is the source of truth for what it was actually adjusted for.

## 5. Gate sequence

Gates run in the fixed order below. `PASS` and `WARN` satisfy a gate; `WARN` never changes the
ceiling but always appears in the finding. `FAIL` and `NOT_EVALUATED` do not satisfy it.

| Gate | Detects | Failure action |
|---|---|---|
| G00 Lineage and preregistration | ungraded provenance, post-hoc candidates | reject |
| G01 Target leakage | condition uses post-decision or outcome information | reject |
| G02 Post-treatment controls | adjusting on a descendant of the exposure | cap at level 2 |
| G03 Sample adequacy | analysis too underpowered to see an actionable effect | cap at level 1 |
| G04 Uncertainty | effect indistinguishable from noise under clustering | cap at level 1 |
| G05 Multiple comparisons | survivorship of the search itself | cap at level 1 |
| G06 Confounding | effect explained by prespecified common causes | cap at level 2 |
| G07 Selection and collider | outcome-dependent inclusion or missingness | cap at level 2 |
| G08 Survivorship cohort | cohort filtered on survival or completion | reject |
| G09 Simpson and heterogeneity | pooled estimate contradicts its own strata | cap at level 1 |
| G10 Temporal stability | effect exists only where it was found | cap at level 1 |
| G11 Seasonality | calendar effect labelled as a business pattern | cap at level 2 |
| G12 Robustness | dependence on one cluster, outlier, or cutoff | cap at level 1 |
| G13 Identification design | causal claim without a design | cap at level 3 |
| G14 Randomisation integrity | experimental claim without randomisation | cap at level 4 |
| G15 Economic materiality | effect too small to act on | policy readiness only |

Exact rules and thresholds for each gate are in `GATE_SPECS`; they are quoted there in full so the
code and the review can never drift apart.

### Notes on the gates most likely to be argued about

**G03 sample adequacy is power, not headcount.** An earlier draft of this contract used a flat
floor of 200 exposed records. Measured against the benchmark's outcome variance (contribution
margin, sd ≈ €766 over 10,000 bookings), that rule would have capped six patterns with |t| between
4.5 and 11 at level 1 purely on record count, while admitting larger but noisier subgroups. The
rule is therefore the minimum detectable effect at 80% power versus the materiality threshold, with
record, event, and cluster counts as floors for bootstrap stability only. This calibration used
outcome variance and group sizes alone — no candidate, effect, or p-value — and was fixed before
any candidate existed.

**G01 target leakage.** The condition may reference only `DECISION_TIME` columns. Variables that
are algebraic components of the outcome (a discount rate inside a margin outcome) are a
*definitional dependency*, not evidence: they are recorded as `WARN` with the mechanical
relationship stated, and the finding must not be presented as a discovery about behaviour.

**G07 selection.** Outcome-dependent missingness is the failure mode this dataset is most exposed
to — repeat-purchase observability that depends on cancellation is exactly the trap encoded in the
synthetic benchmark. When missingness depends on the outcome, the reported effect is the worst-case
bound, never the complete-case estimate.

**G09 Simpson.** A sign reversal in strata covering at least 20% of exposure means the pooled
number is not merely uncertain, it is wrong. The candidate is re-specified at the stratum level and
re-validated as a new candidate; it is not reported with a caveat.

**G10 temporal stability.** Genuinely period-limited effects (a supplier that degraded in 2025) are
legitimate, but they are *different patterns*: they are re-scoped to an explicit validity window
and re-validated, never presented as a standing rule.

## 6. Evidence levels

Cumulative and monotone: a level requires everything all lower levels require. `LEVEL_REQUIREMENTS`
in code is the authority.

| Level | Requires | Means |
|---|---|---|
| 1 `descriptive_observation` | G00, G01, G08 | These records differ, in this window, in this dataset. |
| 2 `predictive_association` | + G03, G04, G05, G10, G12 | Statistically distinguishable, survives the search, holds out of period. |
| 3 `adjusted_observational_association` | + G02, G06, G07, G09, G11 | Survives prespecified adjustment; unmeasured confounding still possible. |
| 4 `quasi_causal_evidence` | + G13 and a quasi-experimental design | Causal under stated, testable design assumptions. |
| 5 `experimental_evidence` | + G14 and prospective randomisation | Measured causal effect. |

The identification design imposes an independent ceiling: `OBSERVATIONAL` can never exceed level 3,
`QUASI_EXPERIMENTAL` never exceeds level 4. Level 5 cannot be assigned retrospectively.

**Language.** `LANGUAGE_RULES` fixes the strongest permitted wording per level and the forbidden
verbs. At levels 1–3 the causal verbs (*causes, drives, leads to, reduces, increases*) are
forbidden in API responses, UI text, reports, and investor material alike. Product and Fundraising
inherit this constraint; they cannot upgrade it.

## 7. Policy readiness

Evidence answers "is it real". Readiness answers "what may the business do about it". They are
separate, and readiness never exceeds what evidence supports.

| Readiness | Condition | Permitted action |
|---|---|---|
| `NOT_READY` | rejected, or immaterial (G15 fails) | none |
| `EXPERIMENT_ONLY` | level ≤ 2 and material; or level 3 without operational feasibility | design a controlled experiment |
| `SHADOW_POLICY` | level 3, material, operationally feasible; or level 4–5 without a positive backtest | log would-be decisions without enforcing |
| `HIGH_CONFIDENCE` | level 4–5, material, feasible, backtest net-positive with an interval excluding zero | propose an enforced rule for human approval |

`backtest_net_positive` is `None` until a policy backtest exists (TASK-032). Until then nothing in
this system can reach `HIGH_CONFIDENCE`, by construction.

## 8. Economic impact

Impact is deterministic code (ADR-004), computed only for candidates that survive to level 2 or
above, and always carrying the bootstrap interval that produced the effect:

1. affected records in the observed window;
2. per-record effect on the versioned outcome, with interval;
3. historical impact over the observed window = affected × effect, interval propagated from the
   same bootstrap replicates;
4. annualisation **only** with at least 12 months of coverage and a stable exposure rate; otherwise
   the observed-window figure is the only figure published;
5. materiality when the interval's lower bound is above zero and the impact clears either
   `min_material_annual_impact` or `min_material_outcome_share`.

Impact is never summed across findings without an overlap analysis: candidates share records, and
adding their impacts double-counts. The aggregate figure a customer sees is a deduplicated
union-of-affected-records estimate or it is not published.

At levels 1–3, impact is stated as *exposure* — value at stake in these records — not as savings.
Only levels 4–5 with a positive backtest may be described as recoverable.

## 9. Policy backtesting methodology

A backtest (TASK-032) replays a policy candidate against history. Its methodological rules:

- **Decision-time only.** The rule may fire only on information available at the decision
  timestamp; a backtest that uses outcomes to decide is circular.
- **Both sides always.** Report avoided bad outcomes *and* suppressed good outcomes. A rule that
  blocks harmful bookings also blocks profitable ones; a one-sided backtest is a sales artifact.
- **No behavioural extrapolation.** Historical replay assumes everything else unchanged. Customers,
  managers, and suppliers respond to policies. The backtest is an upper bound on mechanical effect,
  labelled as such, and is not a forecast.
- **Out-of-period first.** The headline backtest number comes from the future holdout, not from the
  window in which the pattern was discovered.
- **Uncertainty.** The same cluster bootstrap; a net effect whose interval includes zero is
  reported as "no measurable net effect", never as a positive.
- **Operational cost.** Review effort, exception handling, and customer friction are included as
  costs. A rule that saves €30k and requires 400 manual reviews is not a saving.

TASK-033 validates this machinery against synthetic policy ground truth before any backtest number
is shown to a customer.

## 10. Acceptance test for this contract

The contract is not judged by whether it produces findings. It is judged by whether it rejects
things that deserve rejection. Against the synthetic benchmark (TASK-003), a correct application
must:

- reject or downgrade the confounding traps T01–T05 (manager and supplier effects that are
  artifacts of assignment, paid-search and payment-method effects that are artifacts of customer
  and lead-time composition, and the manual-exception main effect);
- bound rather than estimate any effect on repeat purchase, whose missingness depends on
  cancellation;
- scope the drift pattern P07 to a validity window instead of reporting it as standing;
- report the heterogeneous pattern P09 by customer segment rather than pooled;
- assign no finding above `adjusted_observational_association`.

A run that recovers true patterns but also promotes a trap has failed. TASK-022 and TASK-028 score
this explicitly, and a false-positive trap is weighted more heavily than a missed pattern.

## 11. Known limitations

- Observational identification caps this product at level 3. The honest ceiling on customer-facing
  language is "survives adjustment", and the path to anything stronger runs through experiments the
  customer must agree to run.
- E-values quantify sensitivity to unmeasured confounding; they do not exclude it.
- Cluster bootstrap intervals are approximate with few clusters. Below `min_clusters = 5` the
  contract refuses inference rather than reporting an unreliable interval; this rules out
  clustering on supplier (4 levels) or manager (8 levels) alone. The delivered analytical dataset
  (`travel-bookings-analytical-v1.0.0`, resolving `HANDOFF-010` item 2) adds a `customer_id`
  identifier and designates it the clustering key, which is the correct choice regardless: repeat
  purchase and cancellation dependence is naturally at the customer level, not the manager or
  supplier level.
- Rare patterns are structurally invisible. At benchmark scale a subgroup of ~20 records cannot
  clear the power gate against a €766 outcome standard deviation, whatever its true effect. Such
  patterns are false negatives by construction, not analytical failures, and TASK-029 must report
  them as the known cost of this evidence standard.
- Thresholds are pilot defaults calibrated to a 10k-booking, 24-month benchmark. The materiality
  thresholds in particular are placeholders until a real customer's economics are known, and
  re-setting them is a versioned change, not a per-finding adjustment.
- **G06's generalized adjustment set (v1.2.0, §4b) is still not exhaustive**, by disclosed
  construction, not oversight: it excludes calendar-date columns, it only adjusts jointly for as
  many covariates as the development split's sample size can support before coverage collapses
  (a candidate with a small exposed group will get a *narrower* adjustment set than one with a
  large exposed group, purely from sample size, not from any judgment about which confounders
  matter more), and it captures each covariate's own main effect, not interactions between
  adjustment covariates beyond what the joint strata already are. A confounder requiring more
  covariates than a given candidate's sample can jointly support remains invisible to G06, the
  same class of limitation the fixed pair had, at a wider but still finite boundary. `ADR-043`
  checked, empirically, whether replacing joint stratification with additive multivariate
  regression would close this gap — it would not: a confound that only appears once covariates are
  *jointly* stratified (an interaction) is invisible to an additive (main-effects-only) regression
  by construction, regardless of how many covariates it includes. This is a genuine ceiling of
  simple, closed-form adjustment methods at finite sample sizes, not a defect specific to this
  contract's implementation.
