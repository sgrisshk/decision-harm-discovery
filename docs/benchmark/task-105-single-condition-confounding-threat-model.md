# TASK-105 Phase 1 — Single-condition confounding: threat-model specification, catalogue/generator reconciliation, checkpoint

**Status:** Phase 1 only (specification + reconciliation + tests + checkpoint). **No protection mechanism is
designed or implemented.** No change to `engine.py`, any gate, `apply.py`, `contract.py`, frozen `TASK-102`
thresholds, the generator, or the catalogue. Binding decision: `ADR-100` (decisions 1-5), context `ADR-099`.

Artifacts (all new):

| Artifact | Role |
|---|---|
| this document | specification (Part A), reconciliation results (Part B), checkpoint report (Part C) |
| `docs/benchmark/task-105-trap-manifests.json` | machine-checkable per-trap manifests (`T01`-`T05`) |
| `docs/benchmark/task-105-generator-realization-raw.json` | raw measurements (n=400,000 real-generator rows, plus the delivered 10,000) |
| `scripts/measure_task105_generator_realization.py` | measurement code; calls the real `_generate_row` |
| `tests/analytics/test_task105_generator_realization.py` | 51 passing + 12 strict-xfail tests (disagreements surfaced, not hidden) |

---

## Part A — Threat-model specification (`ADR-100` decisions 1-4)

### A1. Semantic definition (decision 1)

Let `C` be a candidate with exactly one condition (`k=1`) defining exposure `X` (a row is exposed iff the
condition holds), `Y` the primary outcome (`contribution_margin_eur` in the benchmark), and `A(C)` the
admissible pre-exposure variables for `C` (A2 below).

> `C` is a **single-condition confounding threat** iff (i) the raw association `X -> Y` satisfies the
> promotion criterion, and (ii) the association can be substantially explained by one or more variables
> `Z ⊆ A(C)`, such that after correct accounting for `Z` the evidence for an independent effect of `X`
> no longer satisfies the promotion criterion.

Consequences stated explicitly:

- The definition is a property of `(X, Y, A(C), data)`. It does **not** mention catalogue names, a generator,
  a trap id, or which column carries the confounding. In particular **no boundary of the form "at least 50%
  of the confounding must sit on `party_size`" (or any share-on-one-column parameter) is encoded**; `TASK-104`
  showed that is a property of `G06`'s coverage-gated selection, not a reasonable threat boundary.
- "The promotion criterion" is the frozen promotion path of the validation contract (readiness
  `SHADOW_POLICY` under the frozen `TASK-102`/`ADR-097`/`ADR-098` thresholds). This specification neither
  restates nor changes any threshold.
- "Correct accounting" names the *target* (the `X`–`Y` association conditional on `Z`), not an estimator.
  Choosing an estimator is mechanism design and is deferred (see C4).

### A2. Admissibility of `Z`: how it is determined from what is already in the repo

`ADR-100` requires `Z` be pre-exposure / causally admissible, excluding mediators, colliders and
target-derived features. What the repository can actually establish, read from the code:

| # | Rule | Source in code | Excludes |
|---|---|---|---|
| R1 | `Z` has `classification == DECISION_TIME` in `synthetic_data/metadata/feature_timing.json` and `discovery_feature_allowed`; only these enter the `features` partition | `analytical_dataset.py` (`feature_columns = columns_by_classification["DECISION_TIME"]`, all must have `discovery_feature_allowed`) | `OUTCOME` (e.g. `cancellation`, `refund_amount_eur`), `POST_DECISION` (`support_cases`, `booking_changes`, `refund_date`, `last_modified_at`), `IDENTIFIER`, `METADATA` -> the **target-derived / post-decision** exclusion |
| R2 | `Z` is named in the dataset manifest's `validation_roles.adjustment_eligible` | `analytical_dataset.py`: every `features` column **except** `decision_timestamp_column` (`booking_date`), `calendar_source_column` (`travel_date`) and `calendar_month_column` (`travel_month`) | date columns (excluded from adjustment by design, handled by `G09`/`G11`) |
| R3 | `Z` is not a condition feature of `C` | `apply._adjustment_pool` (`eligible_features - condition_features`) | the treatment itself and, for a column-level condition, every other level of the same column |
| R4 | (consumed by `G01`) every condition/adjustment feature is `DECISION_TIME` | `apply._validate_one` (`G01`, `G02`) | — |

Delivered v1.1.0 `adjustment_eligible` (verified in the tests): `acquisition_channel, booking_lead_days,
customer_price_eur, customer_segment, customer_type, destination, discount_rate, installments, manager,
manual_exception, party_size, payment_method, product_category, quoted_cost_eur, supplier,
trip_duration_days`.

**R1-R4 are necessary, not sufficient.** The timing classification is a single `DECISION_TIME` bucket: it
says "known before the outcome window", not "causally prior to *this* `X`". It therefore cannot exclude a
decision-time variable that is a *descendant* of the exposure (mediator-shaped) or a collider of `X` and `Y`.
Measured counter-example in this repo: for `T03` (`X = acquisition_channel=paid_search`), `discount_rate` is
`DECISION_TIME` and `adjustment_eligible`, yet the generator makes it a **child** of the exposure (Part B).
Full admissibility is therefore:

> `Z ∈ A(C)` iff R1 ∧ R2 ∧ R3 ∧ (**R5**: a declared causal-order relation states `Z` is not a
> descendant of `X` and not a collider on an `X`–`Y` path).

R5 has **no source in the repository for real data**. For the benchmark, the per-trap manifest field
`causal_role` (`common_cause` / `descendant_of_exposure` / `not_a_cause_of_exposure`) supplies it, verified
against the generator's own data flow. Who declares R5 for non-benchmark data is open (C3, ambiguity A1).

Class-(ii) corollary: a confounder derivable only from an excluded date column (`booking_month` from
`booking_date`) is, by R2, **not available to adjustment** even though the metadata may name it.

### A3. Scope

All `k=1` candidates that reach the promotion path: any single-condition candidate (categorical equality,
numeric threshold, boolean) for which every other gate would permit readiness `>= SHADOW_POLICY`. Not limited
to `T01`-`T05` apparent features and not limited to any trap's confounder list (otherwise benchmark cases would
be fixed instead of the defect class). `k>=2` remains under `G16` and is out of scope of this task.

### A4. Three confounding classes and their obligations (decision 3)

Class is a property of a `(Z, dataset representation)` pair:

| Class | Definition (operational, from the repo) | Obligation |
|---|---|---|
| **(i) observable** | `Z ∈ A(C)` and a column named `Z` is in `adjustment_eligible` | must be checked; a candidate whose confounding by such `Z` is established must not be promoted |
| **(ii) specified-but-unavailable** | metadata declares a confounder exists, but no `adjustment_eligible` column carries it (e.g. `T02`'s `booking_month`) | must move to a conservative state (insufficient-adjustment-coverage or equivalent); must not silently promote |
| **(iii) unknown latent** | an unobserved common cause not named anywhere | outside any provable guarantee; **stated as an explicit limitation**; no obligation to block |

### A5. The frozen acceptance invariant (decision 4, verbatim in substance)

> For any `k=1` candidate reaching the promotion path the system must either **(a)** demonstrate robustness
> of the association after adjustment for **all** available causally-admissible confounders of the declared
> threat model, or **(b)** stop promotion with an explicit insufficient/confounded-evidence reason.

Attribution rule (explicit): **incidental blocking by `G12` (or any gate not aimed at this threat) does not
satisfy the invariant.** `TASK-104` §4a is the worked example: `T01` is below `SHADOW_POLICY` as shipped only
because `G12`'s leave-one-`manager`-out group column is the exposure column itself (sign agreement `<= 8/9`),
a structural artifact that would equally cap a genuine manager effect. A block counts toward the invariant
only if its recorded reason is the confounded/insufficient-adjustment reason for this obligation, and the
same candidate would be promoted if that protection alone were removed (the adversarial standard the later
kill-test must apply). `T01`/`T05` become regression cases; the invariant is not defined through them.

### A6. Internal consistency of the specification

Consistent: decisions 1-4 do not contradict each other; class (iii) is exactly the part of decision 1's
"available to the system" that the invariant's "available" excludes; the scope (A3) and invariant (A5) use the
same candidate set.

Points that are **not** resolved by `ADR-100` and are surfaced for the founder (details in Part C3):
A1 (source of R5), A2 (source of class-(ii) declarations without leaking ground truth), A3 (does
"cannot jointly adjust for all admissible `Z` because of sample coverage" count as branch (b)?), A4 (`T03`
is mediator-shaped as generated), A5 (what "demonstrate robustness" means quantitatively).

---

## Part B — Reconciliation: catalogue vs generator vs observed data

### B1. Method (measured, not asserted)

- **Generator realization.** Rows come from the real `synthetic_benchmark._generate_row`, called exactly as
  `generate_benchmark` calls it (`random.Random(seed)`, `BenchmarkConfig(seed, row_count)`; `confounding_scale=1.0`).
  Verified: default-config regeneration reproduces the delivered `travel_bookings_clean.csv` with **0 mismatching
  rows in 11 columns** (10,000 rows), so the measured generator *is* the one that made the delivered data.
- **Two models per trap** on `n=400,000` generator rows (seed 20260924): `X ~ 1 + pool` and `Y ~ 1 + X + pool`,
  where the pool is every `adjustment_eligible` column except `X`'s own source column, plus 11 `booking_month`
  dummies (the representation does **not** contain them). Numeric threshold indicators used by the generator
  (`lead<14`, `party>=5`, `trip>=14`) join their column's block. Per column block: Wald chi-square (`= df*F`),
  partial `R^2 = W/(W+residual_df)`. "Significant" = Wald `> chi2` critical value at `p=0.001`.
  A confounder is **implemented as a common cause** only if significant on both sides **and** structurally a
  parent of the exposure (below).
- **Structure.** `ast` over `inspect.getsource(_generate_row)`: a variable's parents = names in its RHS plus the
  conditions of every enclosing `if`; direct *column* parents of the exposure are found through non-column
  intermediates (weight lists, `complexity`). This supplies causal *direction*, which correlation cannot.
- Raw numbers: `task-105-generator-realization-raw.json`. Rerun: `PYTHONPATH=packages/analytics/src:packages/schemas/src uv run python scripts/measure_task105_generator_realization.py`.

### B2. Per-trap results (`n=400,000`; Wald chi2 X-side / Y-side; critical values 18.5 for `destination` (df 4) and 13.8 for two-df blocks, 10.8 for one-df)

| Trap | Catalogued `confounded_by` | Generator source says | X-side partial R^2 (Wald chi2) | Y-side Wald chi2 | Realized? | Class (ADR-100) |
|---|---|---|---|---|---|---|
| **T01** `manager=Manager 2` | `destination` | manager weight `+3.5` iff `destination in {Tokyo, Zanzibar}` | 0.0448 (18,755) | 1,084 | **yes** | observable |
| | `booking_lead_days` | ... or `booking_lead_days < 14` | 0.0135 (5,464) | 2,570 | **yes** | observable |
| | `party_size` | never enters manager draw | 0.0000 (0.1) | 961 | **NO** | observable (unused) |
| | `trip_duration_days` | never enters manager draw | 0.0000 (0.2) | 499 | **NO** | observable (unused) |
| **T02** `supplier=Atlas` | `trip_duration_days` | Atlas weight `+4` iff `trip_duration >= 14` | 0.0358 (14,836) | 499 | **yes** | observable |
| | `booking_month` | not in supplier logic | 0.00003 (10.1 < 31.3) | 142 | **NO** | specified-but-unavailable (and unimplemented) |
| | *(uncatalogued)* `destination` | BlueWing weight `+2` iff `destination == Tokyo`, diluting Atlas | 0.0053 (2,140) | 1,141 | **implemented, not catalogued** | observable |
| **T03** `acquisition_channel=paid_search` | `customer_type` | channel drawn independently of everything; customer_type is a *parent of discount* | 0.0000 (0.9) | 12.9 | **NO** | observable (unused) |
| | `discount_rate` | discount weights raised iff `channel==paid_search` or `customer_type==new`: **child of the exposure** | 0.0021 (822)* | 21,278 | **NO as confounder**; descendant | observable column, inadmissible (R5) |
| | `installments` | independent draw | 0.0000 (0.5) | 1,481 | **NO** | observable (unused) |
| **T04** `payment_method=bank_transfer` | `booking_lead_days` | bank weight 0.5 vs 0.28 iff `lead_time < 14` | 0.0234 (9,596) | 2,567 | **yes** | observable |
| | `destination` | never enters payment_method draw | 0.0000 (3.8) | 1,084 | **NO** | observable (unused) |
| **T05** `manual_exception=true` | `destination` | `P(exc) = 0.025 + 0.055*complexity` | 0.0076 (3,048) | 1,084 | **yes** | observable |
| | `party_size` (`>=5`) | same | 0.0030 (1,186) | 961 | **yes** | observable |
| | `trip_duration_days` (`>=14`) | same | 0.0025 (991) | 499 | **yes** | observable |
| | `booking_lead_days` (`<14`) | same | 0.0042 (1,691) | 2,569 | **yes** | observable |

\* `discount_rate` is X-side "significant" only because the exposure causes it; the structural read (`channel ->
discount`, no path `discount -> channel`) labels it a descendant. `booking_month` X-side is insignificant for
every trap (Wald 7-15, critical 31.3).

Exposure-probability arithmetic checked against the generator's own weights (measured vs manifest, n>=200 per
stratum, 60,000-row test fixture; raw file has the 400k values): `T01` 0.126 vs 0.125 (neither driver) and 0.391
vs 0.3913 (either); `T02` non-Tokyo `trip<14` 0.250 vs 0.25, Tokyo `trip<14` 0.166 vs 0.1667, Tokyo `trip>=14`
0.500 vs 0.5, non-Tokyo `trip>=14` **0.614 vs 0.625** (18,204 rows, ~3 SE low at 400k; within the test
tolerance at 60k, noted, unexplained beyond sampling); `T04` `lead<14` 0.503 vs 0.50, else 0.279 vs 0.28;
`T05` by complexity 0..4: 0.025, 0.080, 0.133, 0.189, 0.264 vs 0.025, 0.080, 0.135, 0.190, 0.245 (the last is
26 rows at 60k, 178 at 400k). `T05` therefore confirms **equal weights of 0.055 per indicator**.
`T03`: `P(discount>=0.12 | paid_search)` 0.318 vs 0.3167 and `| not paid_search` 0.266 vs 0.2647;
`P(paid_search)` is 0.272 vs 0.269 by `customer_type` and 0.272 vs 0.270 by `installments` (no dependence).

### B3. Confounding strength in the outcome (context, Y = contribution margin, EUR, X-exposed minus rest; includes genuine pattern effects)

| Trap | raw diff | adjusted for catalogued blocks only (`booking_month` as oracle for T02) | adjusted for whole admissible pool | catalogue-explained part (raw − catalogued-adj) |
|---|---:|---:|---:|---:|
| T01 | −29.5 | +9.8 | +9.6 | −39.3 |
| T02 | +9.4 | +21.3 | +19.0 | −11.9 |
| T03 | −62.2 | −44.8 | −45.1 | −17.4 (adjusts a **mediator**) |
| T04 | −47.6 | −19.9 | −22.3 | −27.7 |
| T05 | −73.7 | −19.4 | −17.3 | −54.3 |

The delivered 10,000 rows have `sd(Y)=766` EUR and raw-difference standard errors of 17-18 EUR (`T05`: 31
EUR, 688 exposed). The confounding-induced shifts above are of the order of, or below, that sampling error, so
on the *delivered* dataset the raw association is dominated by noise (raw diffs −13.9 / +32.8 / −81.6 / −57.1 /
−5.9). Consequently on the delivered data the outcome side of several confounders is not significant
(`T02` `trip_duration_days` Y-side Wald 10.9 < 13.8; `T01` `trip_duration_days` 10.9), while all X-side
dependencies of implemented confounders are (Wald 25-532). Confounding in the generator is real in structure and
measurable at scale, but weak in outcome effect at the delivered size; the `TASK-104` fixtures amplified it
by construction (raw harm calibrated to 400 EUR).

### B4. Where catalogue, generator and observed data disagree (each is a strict-xfail test)

| Trap | Disagreement | Manifest field |
|---|---|---|
| T01 | catalogue lists `party_size`, `trip_duration_days`; generator never uses them | `traps.T01.intended_not_implemented` |
| T02 | catalogue lists `booking_month`; generator never uses it | `traps.T02.intended_not_implemented` |
| T02 | generator uses `destination == Tokyo` (uncatalogued, sign negative) | `traps.T02.implemented_not_catalogued` |
| T03 | `customer_type`, `installments` not implemented; `discount_rate` is a descendant, not a confounder | `traps.T03.intended_not_implemented` |
| T04 | catalogue lists `destination`; generator never uses it | `traps.T04.intended_not_implemented` |
| T05 | **none** — catalogue = generator | — |

`hidden_ground_truth.json` `direct_effect: 0` is true of the trap's *main effect* only: `Atlas` (`P04`),
`manual_exception` (`P05` via `Manager 4`), `paid_search` (`P03`) and `bank_transfer` (`P06`) each also take
part in a genuine pattern, so a `k=1` candidate on those exposures can have a legitimate nonzero marginal effect.

No trap implements a class-(iii) latent common cause (structural test: every non-column input of every
exposure draw is generator plumbing, `rng`/`config`). No trap realizes class (ii): `T02`'s `booking_month` is
specified-but-unavailable in the representation **and** absent from the generator.

---

## The manifests (`task-105-trap-manifests.json`)

Per trap: `apparent_feature`, `exposure`, `intended_confounders` (= committed catalogue, asserted equal),
`implemented_confounders` (realized common causes), `intended_not_implemented`, `implemented_not_catalogued`,
`causal_role` (per confounder), `confounder_class`, `observable_columns` (`null` when unavailable),
`expected_direction` (effect on exposure probability and on outcome, with the indicator definition),
`expected_strength_or_range` (`expected_rates`: arithmetic from the generator's weights, tested against fresh
output; `measured_reference`: the 400k numbers), `applicable_gate` (`primary` / `secondary` / `incidental_not_credited`,
from `TASK-104`/`TASK-075`), `notes`, `outcome_effect_note`. Top level: `latent_confounders_implemented_by_generator: []`.

## Tests (`tests/analytics/test_task105_generator_realization.py`)

`uv run pytest tests/analytics/test_task105_generator_realization.py -rxX` -> **51 passed, 12 xfailed, ~2 s**.
They read the real generator (`_generate_row` output and `inspect.getsource(_generate_row)`), the committed
catalogue, `generate_benchmark` (catalogue regeneration, 200-row config), the delivered manifests and feature
timing. They assert: manifest completeness; manifest `intended_confounders` == committed catalogue == what
`generate_benchmark` emits; generator reproduces the delivered CSV; class assignments vs `adjustment_eligible`
and `DECISION_TIME`; structural parents/roles vs manifest; measured both-sided dependence set vs manifest;
`booking_month` never drives any exposure; expected exposure rates and directions vs fresh output; `T03`
discount downstream of the exposure; no latent parent. The 12 xfails are `strict=True`, each reason names the
manifest field. Correcting the *catalogue* flips the whole-trap and `implemented_not_catalogued` xfails (and the tests pinning manifest `intended_confounders` to the catalogue); the per-confounder `intended_not_implemented` xfails assert against generator measurements, so only a *generator* change flips them.
Not tested: any gate/mechanism behavior (out of scope).

---

## Part C — Checkpoint report

### C1. Per trap: is the catalogue consistent with the generator?

| Trap | Consistent? | Needs correction before any gate can be assessed? |
|---|---|---|
| **T01** | No (2 of 4 catalogued confounders not implemented) | **Catalogue correction** to `{destination, booking_lead_days}` (generator can stay). Note `TASK-104`'s `T01` fixture put weight on `party_size`, which the real generator never does; the real-generator `T01` has no `party_size` share at all. |
| **T02** | No (`booking_month` not implemented; `destination`/Tokyo implemented but uncatalogued) | **Generator fix if `T02` is to exercise class (ii)** (a month effect on the supplier draw); otherwise catalogue correction to `{trip_duration_days, destination}` and `T02` is then a class-(i) case with no class-(ii) content. As-is it cannot test the `booking_month` obligation because the confounding does not exist. |
| **T03** | No, in kind: 2 of 3 not implemented, the third (`discount_rate`) is a *descendant* of the exposure | **Founder decision needed** (A4): as generated there is no common-cause confounding, so `T03` is not a class-(i) case under decision 1 (adjusting for a mediator is exactly what decision 1 forbids). Options for the founder: relabel it as a mediation case outside the threat model, or fix the generator so `customer_type`/`installments`/`discount` are parents of `channel`. |
| **T04** | No (`destination` not implemented) | Catalogue correction to `{booking_lead_days}`. |
| **T05** | **Yes** (equal weights 0.055 x four binary indicators, measured) | None. The only trap that can serve as-is as a class-(i) regression case. |

Cross-cutting: **no benchmark case exists for class (ii) or class (iii)** (no realized specified-but-unavailable
confounding; no latent confounding). Obligations (ii)/(iii) of `ADR-100` cannot currently be tested against the
benchmark at all. `T01`/`T04` (and `T02` after correction) are realized class-(i) cases with 1-2 real confounders.

### C2. Is the specification internally consistent?

Yes, with the caveat that it is *under-determined* at five points (C3). No contradiction between decisions 1-4
was found. The specification as written is a target statement, not yet testable end-to-end because A5 (what
"robustness after adjustment" means) has no quantitative content in `ADR-100`.

### C3. Ambiguities the founder must resolve (not silently resolved here)

- **A1 — source of causal admissibility (R5).** The repo's only timing signal (`DECISION_TIME`) cannot exclude
  descendants or colliders of a given `X` (`T03`/`discount_rate` is the measured counter-example). For real
  datasets nothing declares "`Z` precedes `X`". Which artifact declares it (feature manifest field? per-candidate
  rule? conservative default "`Z` admissible only if declared pre-exposure"?)
- **A2 — declaration source for class (ii).** In the benchmark the confounder lists live in the restricted
  `hidden_ground_truth.json` ("do not expose to ML Discovery"). Something legitimate must tell the system
  a needed confounder is unavailable without leaking ground truth. What is it in the benchmark and in real data?
- **A3 — coverage-limited adjustment.** `G06` drops admissible columns whose joint stratification would leave
  `< 50%` of exposed rows (`TASK-075`). Does "cannot jointly adjust for all available admissible `Z`" count as
  the branch-(b) stop (insufficient adjustment coverage)? Reading the invariant literally, yes; it would then
  apply to most `k=1` candidates with several admissible confounders, so the recall consequence needs a
  founder acknowledgement.
- **A4 — status of `T03`** (above): mediation, not confounding, as generated.
- **A5 — "demonstrate robustness".** No quantitative criterion (attenuation cutoff, sensitivity/E-value,
  interval) is fixed by `ADR-100`; the frozen `TASK-102` thresholds were set for the existing gates.
- **A6 (minor) — timing inside the decision.** `manual_exception` is "recorded during approval" and
  `discount_rate` "approved at booking"; the classification places all of them in one bucket, so ordering
  within the decision is unspecified (same root as A1).

- **A7 (added after independent review) — existential `Z`.** The definition says "there exists `Z ⊆ A(C)`". A large admissible pool
  could explain away almost anything unless a mechanism penalizes the search over subsets; this must be constrained.
- **A8 (added after independent review) — evaluation data.** It is not stated on which data (full data, split, held-out) the
  promotion criterion is evaluated after accounting for `Z`; "substantially explained" is covered only indirectly by A5.
- **A9 (added after independent review) — suppression.** The definition covers explaining-away confounding only; it does not
  address suppression (e.g. `T02`'s adjusted effect moves from +9.4 to +21.3, i.e. adjustment *increases* it).

### C4. Open questions the mechanism design will have to answer (labelled as such; **no algorithm is proposed**)

1. What estimator provides "correct accounting" for `Z` at the sample sizes here (`n_exposed` per split; delivered
   raw-difference SE 17-31 EUR)?
2. How is "all available admissible confounders" made operational when joint stratification is coverage-limited?
3. What is the reported stop reason and evidence level, and how is it distinguished in the report from `G12`/`G16`
   caps so attribution (A5 attribution rule) is testable?
4. Does the class-(ii) trigger read the same metadata as the class-(i) pool?
5. How is the invariant regression-tested when the benchmark only realizes class (i) (C1)?
6. Any safety-semantics change requires a new grading cycle of the changed version (`ADR-100` sequencing).

### C5. Verification status

Measurements are reproducible from the script (seeded). An independent reviewer can re-derive: the generator
reproduces the delivered CSV (0 mismatches); the 12 xfails match the B4 table; `T05` has no disagreement.
Ruff and pyright are clean on the two new Python files. **STOP: Phase 2+ not started.**
