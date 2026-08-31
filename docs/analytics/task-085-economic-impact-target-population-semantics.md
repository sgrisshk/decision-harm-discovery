# TASK-085 — Economic-impact target-population semantics: design (`ADR-087`, this document is design-only)

**Status: DESIGN ONLY. No implementation.** Nothing here changes `discovery.engine`,
`policy_analytics.validation.apply`, `economic_impact.py`, any `GateId`/`GateSpec`, any threshold in
`ValidationThresholds`, or `decision-gate.md`'s metric bands. Where this document names a field, a
function, or a metric, it is describing the *existing* codebase (read, not modified) or specifying
what a later, distinct implementation task would need to build, exactly as `TASK-080`'s design
document does for `G16`. `CODE_REVIEWER` reviews this document before any implementation task opens.

**Depends on / builds on:** `TASK-084` (`APPROVED`, `ADR-086`) — the estimator is arithmetically
correct against the current contract; the error is an estimand mismatch, not a computation bug.
`TASK-080`/`ADR-077` (`APPROVED`, `ADR-078`) — an independently reviewed, closely analogous
non-identifiability result this document extends rather than re-derives (§4).

**Review status: `CODE_REVIEWER` `APPROVED WITH REVISION NEEDED` (`ADR-089`), corrected in place,
2026-08-31 — no further independent review round required.** The central `O1`/`O2`/`O3`
non-conflation architecture (`ADR-089`'s own approval standard) was independently re-derived and
held. One real, code-confirmed defect was found in tier 2's original population specification (§5.2)
— fixed normatively here, not merely disclosed, per the founder's own instruction; see §5.2's inline
correction note for the full record. An additional `O1`≠`O3` divergence (time horizon, via
`active_booking_months`) was independently found and is folded into §8.1. Neither finding disturbs
`O1`/`O2`/`O3`'s non-conflation, so `ADR-089`'s own approval standard already holds without a new
review round, per its own explicit fork for documentation/specification-level findings.

---

## 0. The three objects, restated once, used consistently throughout

Per `ADR-087`, kept genuinely distinct everywhere below — never merged into one name or one number:

1. **Observed candidate exposure** (`O1`). The economic quantity for the whole population the
   candidate rule's condition actually selects. Fully observable in production. Matches the current
   estimand exactly.
2. **Attributable harmful impact** (`O2`). The portion of `O1` justifiably linkable to the actual
   discovered harmful mechanism, as opposed to co-selected records the rule admits for unrelated or
   confounding reasons.
3. **Latent affected-population impact** (`O3`). The true injected pattern's own economic impact.
   Known only via `hidden_ground_truth.json` in the synthetic benchmark; unknown in production.
   Ground truth is used in this document only to describe `O3` and to reason about the benchmark's own
   comparison (§8) — never as a production narrowing procedure, per the binding prohibition carried
   forward from `TASK-084`/`ADR-086`.

## 1. What the code actually computes today, read directly (not paraphrased)

`packages/analytics/src/policy_analytics/validation/apply.py`, lines ~857–898, and
`economic_impact.py`'s `build_economic_impact_result`:

```
full_mask         = rule_expr(conditions) applied to the whole frame       # the candidate's own condition, nothing else
combined_mask     = full_mask                                              # development + validation + future_holdout combined
combined_stats    = split_stats(frame, combined_mask, outcome, "combined") # a plain group-mean computation (summarize_group/raw_difference/harm_score)
exposed_total     = combined_stats.n_exposed
per_record_value  = combined_stats.harm_per_booking      # RAW, unadjusted mean difference — not adjusted_effect
historical_value  = per_record_value * exposed_total
```

Three facts, each independently confirmed by `TASK-084`'s Branch 3 and the `CODE_REVIEWER`
verification's Check 3, load-bearing for everything below:

- **The population is `full_mask` — the candidate's own condition, period.** No narrowing, no
  ground truth, no attribution step anywhere in this computation. This is `O1` by construction, not
  an approximation of `O2` or `O3` that happens to be imprecise.
- **The per-record effect is the raw group-mean difference (`harm_per_booking`), not `adjusted_effect`**
  (the confounder-adjusted quantity `G06` already computes for gating). This is a disclosed,
  deliberate choice (`economic_impact.py`'s own docstring: "must not be extended to narrow exposure to
  a ground-truth-matched subpopulation"), not an oversight — but it means the impact figure and the
  evidence-level figure can, and structurally do, use different per-record effects for the same
  candidate.
- **`validation-contract.md` §8's own text already specifies the correct *customer-facing* framing**:
  "At levels 1–3, impact is stated as *exposure* — value at stake in these records — not as savings."
  `docs/product/finding-product-contract.md` (§ impact framing label, line 63/117) already implements
  this: the exposure/savings framing is "computed once, applied everywhere," never customer-authored,
  and "savings"/"recoverable" language is forbidden below level 4–5-with-backtest. **The customer-facing
  wording layer is not the site of the defect `TASK-084` found.** The defect is (a) an internal/
  benchmark vocabulary layer — `historical_impact`, `EconomicImpactResult`, and
  `decision-gate.md`'s own metric name "economic impact estimation error" all use impact/causal-flavored
  language even though the contract's own §8 already calls the *same computation* "exposure" — and
  (b) the benchmark's own comparison methodology (§8 below), which is internal to `TASK-028`/`evaluate_
  benchmark.py`, not customer-facing at all. This distinction matters directly for §5's evaluation of
  semantics (a).

## 2. The central design question, fixed by `ADR-087`

What economic quantity can be honestly reported to a user for a discovered surrogate rule, when the
system observes `O1` but does not identify `O2` (and, in a benchmark, is compared against `O3`)?

## 3. Semantics (a) — rename, don't recompute

**What it is.** Keep the current computation exactly as-is; change only the language used to describe
it, everywhere it appears — not just in customer-facing product copy (already correct, §1), but in the
internal/engineering/benchmark vocabulary that currently uses impact language inconsistently with the
contract's own §8.

**What it actually requires, concretely, once the customer-facing layer is confirmed already correct
(§1):**

1. Field/type naming inside the estimator and its persistence contract:
   `EconomicImpactResult.historical_impact` → a name that states the population honestly (e.g.
   `candidate_exposure` or `candidate_value_at_stake`); `historical_value`/`historical_impact` locals in
   `apply.py` similarly renamed. This is a rename of Python identifiers and persisted JSON keys — a
   real implementation cost (every consumer of the current field name, `apps/api/app/findings/
   contracts.py` included per `HANDOFF-025`, would need updating and versioning under
   `ECONOMIC_IMPACT_CONTRACT_VERSION`), but a mechanically bounded one.
2. `decision-gate.md`'s own metric name ("economic impact estimation error") and its narrative prose
   throughout the "Post-benchmark comparison" entries, which consistently call the reported figure
   "impact" and compare it against a "realized ground-truth effect" — language that, read literally,
   already asserts the two are the same estimand. This is exactly the premise `TASK-084` disproved.
3. Every forensic document in this chain (`task-058`–`task-084`, this document's own dependencies)
   that uses "impact" for `O1`'s quantity — not rewritten retroactively (§9's `ADR-015` precedent
   applies to grading, and rewriting frozen forensic prose is out of this task's scope regardless), but
   any *new* prose from this point forward should use `O1`'s name consistently.

**Does this alone solve the honesty problem?** No, and the reason is precise, not a hand-wave: renaming
changes what a number is *called*, not what population or mechanism it targets. A customer (or a
benchmark) reading "candidate exposure: €X" is told exactly and only what `O1` is — which is true and
useful — but nothing about the rename itself tells anyone how much of `O1` is `O2`. `TASK-084`'s own
finding was never that the number was mislabeled in a way that made it wrong; it was that the *product
question* "how much of this is really the mechanism's fault" (`O2`) has no answer in the current
pipeline at all, under any name. A rename cannot manufacture identification.

**What it costs.** Genuinely small at the customer-facing layer (already done); real but bounded at
the internal/persistence/benchmark-vocabulary layer (a field/metric-name migration, versioned per
`ECONOMIC_IMPACT_CONTRACT_VERSION`, following this project's own `ADR-015`/`ADR-064` precedent for
versioning a corrected semantic without silently re-grading old artifacts). It does **not** weaken the
product's value proposition in any way that survives scrutiny: the product was already required, by
its own §8, to say "exposure," not "savings," at every level this system actually reaches (1–3) — a
rename that makes the *engineering* vocabulary match the *product* vocabulary the contract already
mandates is a consistency fix, not a value-proposition change. "Exposure" is the right word for `O1`
specifically because it is a scope claim ("this much of the business is touched by this rule"), not a
mechanism claim — exactly what `O1` is and only what `O1` is.

**Verdict on (a) alone: necessary, insufficient.** Every other semantics below assumes (a) as a
precondition — nothing downstream can be honest if the vocabulary itself keeps asserting `O1 = O2`.

## 4. Semantics (b) — partial-identification bound for `O2`

This is the question requiring the most genuine investigation, and the one this document treats most
carefully. The conclusion is negative — stated plainly, per `ADR-087`'s own instruction that this is a
legitimate outcome.

### 4.1 The formal non-identification result, stated first

Partition the candidate's own exposed population `E` (size `N_E`, known) into an unobservable
mechanism-affected part `A ∩ E` (size `π · N_E`, `π` unknown) and an unobservable non-mechanism part
`E \ A` (size `(1-π) · N_E`). Let `δ_A` be the true per-record effect specific to `A ∩ E`, and `δ_C`
the average per-record effect specific to `E \ A` — which may itself be non-zero, and per `TASK-084`
Branch 4's positive control (§4.2 there: whole-rule error grows with dilution precisely when, and only
when, the diluting population carries its own outcome association, `r≈0.998`) generically *is*
non-zero for a search-composed surrogate rule, because `discover_candidates`'s own eligibility filter
(`_eligible` requiring `harm_per_booking > 0` over the whole exposed set) structurally selects for
rules whose full population already shows same-signed harm — selecting for exactly this kind of
confounding by construction, not by accident.

The one quantity this system can estimate without new assumptions, `δ_E` (the observed, already-
correctly-bootstrapped raw effect over `E`), decomposes by simple linearity of expectation as:

```
δ_E = π · δ_A + (1 - π) · δ_C
```

`O2`, the attributable impact, is `π · N_E · δ_A`. One equation, two unknowns (`π`, `δ_A`, given `δ_C`
is also unknown) — **not identified from `δ_E` alone, under any estimator.** This is not a defect of
this particular estimator; it is a property of the information the candidate's own condition and the
development-split frame contain. Recovering `π`, `δ_A`, or `δ_C` individually requires either (i)
external information the system does not have (ground truth, `O3`), or (ii) a new assumption fixing
one of the three unknowns — exactly the "new, unverifiable assumption" `ADR-087` asks this document to
avoid introducing.

### 4.2 Does the candidate's own condition structure help? — direct extension of `TASK-080`/`ADR-077`

`ADR-087` names this as a concrete avenue to investigate: "the candidate's own condition structure."
This is not a new question — it is, formally, the *same* question `TASK-080` already investigated to
an independently reviewed conclusion (`CODE_REVIEWER`, `ADR-078`), for a structurally identical
decomposition problem.

`G16`'s leave-one-out mechanism (`TASK-080` §4/§8.1) asks, for a compound rule `R = (C1...Ck)` and each
atom `Ci`: does `base_i`'s own effect (the rule with `Ci` removed), examined within `Ci`'s two levels,
attenuate (confound-like) or concentrate without attenuating (interaction-like)? This is exactly a
special case of the `π`/`δ_A`/`δ_C` decomposition in §4.1 — `Ci` is playing the role of the (candidate,
not ground-truth) variable that would split `E` into a more- and less-affected part, and the question
"is `Ci`'s apparent contribution real or a co-traveling confound" is the *same inferential act* as "is
`O1`'s own excess over `O2` real dilution-confounding or a genuine, concentrated mechanism effect."

`ADR-077`'s own, independently `CODE_REVIEWER`-approved conclusion (`ADR-078`) for that identical
inferential act, using the identical information source ("a frozen candidate's condition tuple + frame
alone"), is:

> "No observational estimand computable from a frozen candidate's condition tuple + frame alone can
> provide positive evidence for genuine interaction without also turning residual proxy confounding
> into `interaction_like`, at realistic prevalence/measurement-error/nonlinearity combinations."

Concretely, `ADR-077`'s adversarial identifiability suite (`docs/benchmark/task-080-identifiability-
suite-raw.json`) showed a 100%-confounded, zero-true-effect DGP produces the *same* classifier output
as a genuine-interaction DGP at realistic sample sizes and skewed confounder prevalence — not a rare
edge case, a `plateau at 1.000` false-positive rate by `n=2,400`. **This result transfers directly to
§4.1's decomposition problem**, because the underlying obstruction is identical: any statistic
computed from `E`'s own internal structure (stratifying by an atom, by a threshold position, by a
nested subrule) that tries to separate "explained by a proxy/confound" from "a genuine, concentrated
effect" is a functional of the same low-dimensional cell-mean summary that both a stratum-varying
confounding bias and a genuine effect can produce indistinguishably. `TASK-080`'s own estimand audit
(§14/§15 of that document) checked every candidate signal this project's own machinery offers for this
purpose — attenuation-under-adjustment, stratum-contrast heterogeneity, threshold-perturbation
stability, an OLS/nested-model interaction test — and found each one reducible to the same statistic,
none independent of it.

**Conclusion for this avenue: a partial-identification bound for `O2` built purely from the candidate's
own condition structure is not achievable**, for the same reason, already independently reviewed and
approved, that positive `interaction_like` evidence is not achievable in `G16`. This document does not
re-run `TASK-080`'s suite (out of scope: that would be touching `TASK-080`'s own closed design); it
applies that already-established, already-reviewed result to a structurally identical question.

### 4.3 Does overlap with other candidates help?

Named in `ADR-087` as a second avenue. Unlike §4.2, this is not covered by `ADR-077`'s proof (which was
scoped to "a frozen candidate's condition tuple + frame alone") — so it is evaluated fresh, not
assumed to inherit the same impossibility result.

**The idea.** If search separately discovers a narrower, nested candidate `R' ⊂ R` (a strict refinement
of the same rule) that independently reaches a higher evidence level, `R'`'s own exposed population
could, in principle, serve as a tighter (though still not ground-truth-verified) proxy for `A`, and its
own impact estimate could substitute for `R`'s `O2`.

**Why this does not clear the bar as a general mechanism, on inspection:**

1. **No guarantee such a candidate exists.** `TASK-084`'s own Branch 2/3 finding (`recall_of_true_
   pattern` ranging 69.4%–100% across the 9 matched candidates, §3.3 there) shows the discovered rule
   is sometimes *narrower* than the true pattern (partial coverage) and sometimes broader (dilution) —
   there is no structural reason search would ever discover both a broad surrogate and a properly nested
   narrower refinement of the *same* rule for the *same* mechanism. In this project's own official
   runs, it never has (every matched candidate is exactly one persisted rule per pattern, not a nested
   family).
2. **Even where a nested candidate exists, its own exposed population is still just another `O1`,
   subject to the identical, unresolved identification problem — one level down.** Substituting `R'`
   for `R` does not identify `O2`; it only produces a *different* `O1`, for a narrower, differently-
   diluted rule, with its own unknown mix of `π'`/`δ_A'`/`δ_C'`. Nothing in the substitution removes the
   `π`/`δ_A`/`δ_C` non-identification from §4.1 — it relocates it, exactly the failure pattern `ADR-071`
   already named for a superficially similar `G06` reordering fix, and `TASK-080` §3 flagged for
   candidate-generation-side fixes generally.
3. **It is not reliably buildable as a production mechanism.** Even granting (1)/(2), a design that
   only produces a bound "when we happen to also find a nested refinement" cannot be a general answer
   to `ADR-087`'s central question — it would need its own fallback for the (typical) case where no
   such candidate exists, which collapses back to the unresolved general problem.

**Conclusion: not a proven mathematical impossibility, unlike §4.2, but not a reliable, general-purpose
identification source either** — disclosed as a practical, not formal, negative finding. A future
direction naming it explicitly (an ensemble-of-candidates cross-check, run only opportunistically when
a genuine nested refinement exists) is named in §10, not built here.

### 4.4 Does within-candidate heterogeneity (a `G09`-style stratum split) help?

Third avenue named in `ADR-087`. This reduces to §4.1/§4.2 directly: splitting `E` by any covariate
not already in the candidate's own condition and comparing stratum effects is exactly `G06`'s/`G09`'s
own existing adjustment/heterogeneity machinery, already subject to this product's own disclosed
ceiling (`validation-contract.md` §11: "E-values quantify sensitivity to unmeasured confounding; they
do not exclude it"; "a confounder requiring more covariates than a given candidate's sample can jointly
support remains invisible"). A high-effect substratum is exactly as consistent with a co-traveling,
unmeasured confounder specific to that substratum as with a genuinely concentrated mechanism effect —
the identical ambiguity §4.2 already resolved against, one level down in granularity. No new
identification power over §4.2.

### 4.5 A generic (Manski-style) support-restriction bound — checked, not assumed unavailable

For completeness: the classical partial-identification move when a quantity is a mixture of two
unobserved subgroup means (Manski 1990, 2003) is to bound the unknown-mixture mean using the outcome's
own natural support `[y_min, y_max]`, without needing to separately identify the mixture weight. Applied
here: even granting the outcome (contribution margin per booking) has a known bound, the *quantity this
design needs* is not `E[Y | A ∩ E]` alone (which a support bound could constrain) but `π · N_E ·
(δ_A - baseline)` — the bound would still need either `π` itself bounded (unknown, and no candidate-
internal or overlap-based source for it survives §4.2–§4.4) or a domain-supplied floor on `π` (a genuine
new, unverifiable assumption — precisely what `ADR-087` asks this document not to introduce). A support-
restriction bound formally exists but degenerates to requiring exactly the assumption this document is
required to avoid; it is not a free lunch here, and is not adopted.

### 4.6 Verdict on (b)

**Not achievable without introducing a new, unverifiable assumption — a real, checked, negative
conclusion, not a failure to look.** The strongest available avenue (§4.2, candidate-internal
structure) inherits an already-independently-reviewed impossibility result (`ADR-077`/`ADR-078`)
directly, not by analogy alone but by formal structural identity of the two decomposition problems. The
two remaining avenues named in `ADR-087` (§4.3 overlap, §4.4 heterogeneity) do not clear the bar either,
for reasons specific to each. A classical support-restriction bound (§4.5) formally exists but requires
exactly the assumption this document is instructed to avoid introducing. **`O2` is not
partial-identification-boundable from what a production system actually observes, today, without
external information.** §6 revisits what "external information" would have to mean for this to change.

## 5. Semantics (c) — evidence-dependent reporting

### 5.1 What already exists in this project's own machinery that this semantics can reuse

Two pieces of information this system already computes, currently discarded or unsurfaced at the
impact-reporting layer, are directly relevant to an evidence-dependent design — nothing new needs to be
invented to use them:

1. **`adjusted_effect`** — `G06`'s own confounder-adjusted per-record effect, with its own E-value,
   already computed for every candidate that reaches gate `G06`, but (§1) explicitly *not* used for the
   impact computation, which uses raw `harm_per_booking` instead.
2. **`G16`'s per-atom composition-safety classification** (`confound_like` / `indeterminate`, per
   `TASK-080`/`ADR-077`'s two-state design) — already computed for every `k ≥ 2` promoted candidate,
   naming specifically which condition atoms show positive evidence of confounding and which are
   merely unresolved.

Both are computed on `O1`'s own population (`E`) — using either does **not** identify `O2` (§4
established that no candidate-internal computation can), but both make the *per-record effect term*
progressively more defensible as more identifying work has actually been done on the candidate, which
is exactly the ladder-shaped claim `ADR-087` asks this semantics to design.

### 5.2 The design — three tiers, keyed to the existing evidence ladder, no new gate

| Tier | Evidence level required | What is computed | Population | Name | Claim permitted |
|---|---|---|---|---|---|
| 1 | `descriptive_observation`+ (1+) | `per_record_value` = raw `harm_per_booking`, `historical_value` = `per_record_value × exposed_total` — **unchanged computation from today** | `E` (`O1`) | **Candidate exposure** | "Value at stake in these records" (§8's own existing wording) — never "impact," never "savings" |
| 2 | `adjusted_observational_association`+ (3+) | `per_record_value` = `adjusted_effect` (already computed by `G06`), aggregated **only over the population `adjusted_effect` was actually estimated on** — the development split — never transported to a wider window | `E_dev = E ∩ {development split}` (`O1`'s own definition, restricted, **strictly narrower than tier 1's `E`**) | **Adjustment-consistent candidate exposure (development-split scope)** | Same "exposure" framing, scoped explicitly to the development-split population in its own name and figure — **explicitly not upgraded to "attributable" or "impact" language**, and explicitly not presented as a figure for the same population as tier 1 |
| 3 | `quasi_causal_evidence`/`experimental_evidence` (4–5), i.e. `G13`/`G14` satisfied | The candidate's own exposed population is now, by identification-design construction (not by search happenstance), the mechanism's population — `O1` and `O2` coincide by design, not by estimation | `A` (design-identified, ≈ `O2`) | **Attributable harmful impact** | Causal language becomes permitted per the existing `LANGUAGE_RULES` for levels 4–5; "recoverable"/"savings" only with a positive backtest, per §8's existing final sentence |

**Correction (2026-08-31, founder, following the independent `CODE_REVIEWER` review's Check 3,
`ADR-089`).** The original version of this table's tier-2 row stated the population stayed "over `E`,
not a narrower population." Independent code tracing (`apply.py`) found this false as originally
specified: `adjusted_effect` is fit by `_stratified_adjustment` on the development split alone, but
the draft's own computation multiplied it by `exposed_total` — the *combined* development +
validation + future_holdout count — a silent cross-split transport of a development-only-fit effect
onto a wider population it was never estimated on. This did not cause `O1`/`O2` conflation (both
tier 1 and tier 2 remained `O1`-family, candidate-exposure quantities, never claimed as `O2`), so it
did not breach `ADR-089`'s own approval standard — but it was a real, code-confirmed defect in tier
2's own specification and is fixed here normatively, not merely disclosed: **tier 2's population is
now `E_dev`, explicitly narrower than tier 1's `E`, matching exactly the population `adjusted_effect`
was actually estimated on. No transport assumption is introduced.** If a future implementation
task finds `E_dev`-scoped reporting insufficiently useful on its own terms (e.g. too small a sample,
or confusing next to tier 1's wider figure), the correct response is to leave tier 2 **unavailable**
until a genuine cross-split methodology (e.g. refitting `adjusted_effect` over the combined
population, itself a new statistical-machinery question this design document does not authorize) is
separately designed and reviewed — never to silently re-widen the population tier 2 reports over.

Tier 3 is not new machinery — it is the observation that `ADR-087`'s central question already has an
answer in the existing evidence ladder, once stated precisely: **`O2` becomes reportable exactly when,
and only when, a genuine identification design (`G13`) or randomization (`G14`) makes the candidate's
own exposed population coincide with the mechanism's population by construction — never by adjusting or
narrowing an observational surrogate rule after the fact.** This is the same ceiling `validation-
contract.md` §1 already states in general ("historical booking data can support at most `adjusted_
observational_association`... levels 4 and 5 require a design, not more adjustment"), applied here
specifically to the impact quantity rather than only to the evidence-level claim.

**A disclosed, load-bearing consequence, stated plainly rather than hidden:** because this project has
never had a candidate reach level 4–5 (`§1`'s own standing position: observational data caps this
product at level 3), **tier 3 is, in practice, currently an always-empty slot.** This is not a design
failure — it is an honest consequence of what this product's current data regime can support, named
here exactly as `validation-contract.md` §11 already names comparable ceilings ("rare patterns are
structurally invisible... false negatives by construction"). A tier that is honestly empty today is
better than a tier that is silently filled with an unidentified number.

### 5.3 What is shown to a user when attribution is not possible (tiers 1–2, i.e. every real candidate today)

- **Always:** "Candidate exposure" (or its adjustment-consistent refinement at tier 2), with its
  existing bootstrap interval, in `O1`'s own language — never "impact," never a claim about the
  mechanism specifically.
- **When `k ≥ 2` and `G16` has run:** a disclosed qualifier surfacing `G16`'s own per-atom
  classification verbatim — e.g. "N of K conditions in this rule show no evidence against a confounding
  explanation" (`confound_like` atoms) or "this rule's own condition structure could not rule out
  confounding for N of K conditions" (`indeterminate` atoms) — **never a numeric adjustment to the
  reported exposure figure**, only a disclosed, qualitative caveat alongside it, exactly analogous to
  how `G16`'s cap already travels with the candidate's evidence level without being folded into any
  point estimate.
- **Always, explicitly:** a statement that the portion of this exposure specifically attributable to
  the discovered mechanism (as opposed to co-selected records) cannot currently be estimated from this
  data — not "is small" or "is being refined," a plain disclosure of non-identifiability, matching this
  project's own established disclosure culture (§11's own "Known limitations" precedent).

### 5.4 Behavior under a broad surrogate/partial-coverage rule

- `O1` (all tiers): grows or shrinks directly and honestly with the rule's own breadth — by
  construction, since it is defined as exactly what the rule selects. No distortion, because no claim
  beyond "this rule's own population" is being made.
- Tier 2's adjustment-consistent refinement: partially mitigates confounding *within* the per-record
  term (to whatever extent `G06`'s adjustment ceiling allows — itself disclosed as incomplete,
  `validation-contract.md` §11), but does **not** address dilution/breadth at all, since tier 2's own
  population (`E_dev`, per the correction above) is itself just as much a raw candidate-defined
  surrogate population as tier 1's `E` — narrower in *window*, not narrower in the sense of excluding
  non-mechanism records. This must never be presented as solving the breadth problem `TASK-084`
  diagnosed as dominant (Branch 4's `r≈0.998` positive control).
- Under partial coverage (`recall_of_true_pattern < 1`, `TASK-084` §3.3), `O1` may in fact be *smaller*
  than the true mechanism's own full population for that same rule shape — the honest exposure figure
  can understate `O3` just as often as it overstates it via dilution. Nothing in this design corrects
  for that either; it is disclosed as a further reason `O2` is not derivable from `O1` by any fixed
  multiplier.

### 5.5 Verdict on (c)

**Adopted, as this document's actual recommendation** — see §6 for the full statement and the
synthesis with (a).

## 6. Recommendation

**Recommended design: (a) + (c), combined — not (a) alone, and not (b), which §4 established is not
achievable without a new unverifiable assumption.**

1. **(a) is a necessary precondition, not a standalone answer.** Every quantity named in §5.2's table
   must use `O1`-honest language (exposure/value-at-stake) at every layer — customer-facing (already
   correct, §1), internal field/persistence naming, and benchmark/decision-gate vocabulary (§8). This
   requires a real, bounded, versioned rename at the internal layers, not merely a restatement of the
   already-correct product-facing rule.
2. **(c) is the substantive mechanism.** It gives a name, a target population, a formal estimand, and a
   permitted claim to each of `O1`'s two tiers and to `O2`'s (currently empty) tier, reusing only
   already-computed quantities (`adjusted_effect`, `G16`'s per-atom classification) and the existing
   evidence ladder — no new gate, no new statistical machinery, no new tunable threshold.
3. **(b) is not adopted, on a checked, disclosed negative finding**, not by default or by not looking:
   the strongest candidate-internal avenue for a partial-identification bound on `O2` inherits an
   already-independently-reviewed non-identifiability result (`ADR-077`/`ADR-078`) by direct structural
   correspondence (§4.2); the two other avenues `ADR-087` names do not clear the bar either (§4.3,
   §4.4); a classical support-restriction bound formally exists but requires exactly the kind of
   external assumption this document is instructed to avoid manufacturing (§4.5).

This synthesis directly answers §2's central question: **the only economic quantity that can be
honestly reported to a user for a discovered surrogate rule, absent a genuine identification design, is
`O1` — the candidate's own exposure — named as such, with its per-record term's own defensibility (raw
vs. adjustment-consistent) disclosed by tier, and with an explicit, standing statement that the
mechanism-attributable share of that exposure is not currently estimable.** `O2` remains a legitimate,
named, currently-unfilled slot in the product's own vocabulary — reachable only through a real
identification design (tier 3), never through a cleverer computation on the same observational surrogate
rule.

## 7. Formal estimands, stated with the rigor this project's other estimands use

**`O1` — Candidate exposure (tiers 1–2 of §5.2). Two distinct population scopes, corrected 2026-08-31
per `ADR-089` Check 3 — tier 2 is no longer stated as sharing tier 1's population.**

- **Tier 1 target population:** `E = {records where rule_expr(candidate.conditions) holds}` over the
  combined (development + validation + future_holdout) observed window.
- **Tier 1 estimand:** `Σ_{i ∈ E} (Y_i − μ_{E^c})`, equivalently `|E| · (μ_E − μ_{E^c})`, where `μ_E`,
  `μ_{E^c}` are the outcome's mean over `E` and its complement within the same cohort/window
  (`apply.py`'s `split_stats`/`raw_difference`) — the unadjusted `μ_E − μ_{E^c}`.
- **Tier 2 target population:** `E_dev = E ∩ {development split}` — strictly narrower than `E`,
  matching exactly the population `G06`'s `_stratified_adjustment` fits `adjusted_effect` on. **Not**
  the combined window — that would silently transport a development-only-fit effect onto records it
  was never estimated on, the defect this correction fixes.
- **Tier 2 estimand:** `|E_dev| · adjusted_effect`, where `adjusted_effect` is `G06`'s own
  confounder-adjusted difference, computed via the existing greedy, coverage-gated joint
  stratification (`validation-contract.md` §4b), unchanged — evaluated and aggregated over `E_dev`
  only.
- Uncertainty: cluster bootstrap over `customer_id`, `DIAGNOSTIC_BOOTSTRAP_REPS` replicates, percentile
  interval — unchanged from today's computation.
- Evidence claim permitted: mirrors `LANGUAGE_RULES` at the candidate's own evidence level for the
  *association* claim (unchanged); for the *exposure figure itself*, always "value at stake in these
  records," never a savings/impact/causal verb, regardless of evidence level, through level 3 — matching
  §8's own existing final paragraph exactly.

**`O2` — Attributable harmful impact (tier 3 of §5.2, currently unfilled in practice).**

- Target population: `A`, the mechanism's own affected population, as delimited by a genuine
  identification design (`G13` quasi-experimental design or `G14` randomization) — not a subset of `E`
  selected by any observational computation.
- Estimand: identical form to `O1`'s, evaluated over `A` instead of `E`, using the design-appropriate
  effect estimator (already specified by `validation-contract.md` §9's backtest methodology and §6's
  level-4/5 requirements — no new estimator is proposed here).
- Evidence claim permitted: `LANGUAGE_RULES` levels 4–5 (causal verbs permitted); "recoverable"/
  "savings" only with a positive backtest, per §8's existing rule, unchanged.
- **Not estimable at levels 1–3 by any construction identified in this document (§4).** This is stated
  as part of the estimand's own specification, not as a caveat bolted on afterward: the estimand is
  defined only conditional on a design that makes `A` observable in the first place.

**`O3` — Latent affected-population impact (benchmark-only, never a production estimand).**

- Target population: `hidden_ground_truth.json`'s own `affected_booking_ids` for the matched pattern(s).
- Estimand: `patterns_by_id[pid]["true_effect"]["realized_economic_impact"]`, summed over matched
  patterns — exactly `evaluate_benchmark.py`'s existing `truth_impact` computation, unchanged.
- Role: benchmark-side comparison target only (§8). Never surfaced to a production user; never a
  narrowing procedure for `O1`/`O2`, per the binding prohibition this document does not touch.

## 8. The benchmark comparison, and metric 6's fate — a consequence, not a starting assumption

### 8.1 What metric 6 actually compares today, read directly

`scripts/evaluate_benchmark.py` lines ~536–556: `reported_point` is the midpoint of `historical_
impact`'s CI — `O1`'s own quantity, exactly as §1/§7 specify. `truth_impact` is the sum of matched
patterns' `realized_economic_impact` — `O3`, exactly as §7 specifies. **Metric 6, as currently defined,
computes `|O1 − O3| / O3`: a genuinely different-estimand comparison, precisely what `TASK-084`
diagnosed and `ADR-087` asked this document to resolve.** Under §6's recommended semantics, no claim the
product would ever make asserts `O1 ≈ O3` — that equivalence was never true, is not the target this
design recommends reporting, and no version of (a)/(b)/(c) makes it true. A metric built to check it is
therefore checking a property the corrected system does not claim to have.

**Additional, independently confirmed divergence (2026-08-31, `CODE_REVIEWER`, `ADR-089` Check 1) —
`O1` and `O3` differ on time horizon too, not only population definition.** `O1`'s window is `E`'s
combined development+validation+future_holdout observed window, unconditionally. `O3`'s window is
`hidden_ground_truth.json`'s own `active_booking_months` for the matched pattern, which for several
patterns restricts `O3` to a narrower window than `O1`'s combined window ever uses. This is a further,
independently-found confirmation that `O1 ≠ O3` — the two sides of metric 6 disagree on population
*and* time horizon, strengthening (not merely restating) the case for prospective retirement in §8.4.

### 8.2 Is metric 6 semantically valid as a product-quality gate, given §6's conclusion? — the consequence, reached from the reasoning above

**No, not as currently defined — a direct consequence of §6/§7, not an assumption made going in.**
`decision-gate.md`'s own criterion for what should be graded is itself an accurate business proxy only
if the number it grades is the number the product actually claims. Once `O1`'s honest claim is "value
at stake in the records this rule selects" (§7), there is no production-relevant sense in which that
number should equal `O3` — comparing them was never measuring product quality; it was measuring the
size of a category error this document now names precisely.

### 8.3 What a like-with-like comparison would have to check instead — sketched, not specified, and explicitly not the prohibited path

The binding prohibition rules out "fix metric 6 to compare the candidate's overlap with ground truth" —
i.e., narrowing `O1`'s population using `O3`'s own membership information before comparing. **Nothing
proposed here does that.** A like-with-like check, if a future task builds one, would instead compare
`O1` against **the realized value of that same estimand, for that same candidate-defined population `E`
— not against a differently-defined population at all.** Concretely, two distinct, ground-truth-free
questions this reframing separates out, previously conflated by metric 6's single number:

1. **Is the reported `O1` estimator well-calibrated for its own stated target?** — e.g., does a
   development+validation-fit exposure figure's interval cover the same population's realized value in
   the future_holdout window (an out-of-sample stability check for the *impact* quantity specifically,
   analogous in spirit to `G10`'s existing temporal-stability check for the *association* claim, but not
   currently computed for impact). This uses only the candidate's own defined population `E` and the
   dataset's realized outcomes — no ground-truth pattern membership anywhere in it.
2. **Once `O2` becomes reachable at tier 3 (§5.2), does the design-identified `O2` accurately predict
   `O3`?** — this is the comparison that is actually meaningful against ground truth, because at tier 3
   `O2`'s own population is, by construction, meant to approximate `A`. This comparison has never been
   possible to run in this project's history, because no candidate has ever reached level 4–5 (§5.2's
   disclosed "always-empty slot" today).

Question 1 is, largely, already answered by `TASK-084`'s own finding: the estimator is arithmetically
correct for `O1`'s own population (`CODE_REVIEWER` Check 3, `ADR-086`) — so a metric built around
question 1 would mostly be re-confirming a property already established, which is better owned by a
regression/form test (this project's own `G05`/`G12` precedent: `test_g05_multiplicity_fix.py`,
`test_g12_robustness_fix.py`, neutral synthetic form tests, not a benchmark decision-gate metric) than
by a founder-level go/no-go gate. Question 2 has no live population to grade against today and would
only become meaningful once a level 4–5 candidate exists.

**This document does not specify a replacement metric** — doing so would be a gate/threshold-adjacent
design decision, and `TASK-085`'s own scope excludes "any gate/threshold change of any kind." §8.4
states the recommended disposition instead.

### 8.4 Recommended disposition of metric 6

**Retire metric 6, as currently defined, from the decision gate — prospectively only, and by
consequence of §6–§8.3's reasoning, not as a starting assumption.** Concretely:

- `TASK-073`'s and `TASK-083`'s own historical **FAILED** verdicts are **not rewritten**. Each stands
  exactly as recorded, under the estimand definition that governed it at the time — matching `ADR-015`'s
  own versioning precedent (a contract-semantics change is never retroactive) and this document's own
  explicit instruction.
- Any future run's decision-gate grading should **not** compute metric 6 against `O3` at all, because
  under the corrected semantics no production claim asserts `O1 ≈ O3` — grading a claim the product does
  not make is not a stricter gate, it is a miscalibrated one, in either direction.
- What (if anything) replaces metric 6's numbered slot in `decision-gate.md` — a form-test regression
  suite for `O1`'s own calibration (§8.3 question 1, likely the right home), a currently-inactive
  "attributable-impact accuracy" slot that only activates once a level 4–5 candidate exists (§8.3
  question 2), or simply five graded metrics instead of six — is a **gate-definition decision**, and
  `TASK-085`'s own scope bars this document from making it (`decision-gate.md`, `docs/analytics/
  validation-contract.md` thresholds, and `GATE_SPECS` are all explicitly out of scope for this design
  task). This is named as the concrete next question for a distinct, later task, opened only after this
  document's own `CODE_REVIEWER` review — matching this project's decide/implement separation
  (`TASK-076`/`077`'s own precedent).
- Until that follow-on task resolves this, `decision-gate.md` itself is **not edited by this document**
  (the same reason: gate-definition changes are out of this task's scope) — the disposition above is
  this document's *recommendation*, to be acted on by whichever task is authorized to touch
  `decision-gate.md`.

## 9. What additional data source could unlock a stronger claim in the future

Named as future directions, not built here, per `ADR-087`'s own acceptance item:

1. **A genuine identification design or natural experiment** (tier 3, §5.2) — already the existing
   ladder's own answer; nothing new. The realistic path is `TASK-032`'s policy-backtest machinery,
   applied to an actual enforced or randomized rollout of a candidate rule, which is the only currently
   planned mechanism by which this product's own exposed population could ever coincide with a
   mechanism population by construction.
2. **A small, independently verified audit sample.** If a real customer (post-`TASK-057`) can provide
   manual case-review or compliance-audit labels — true mechanism membership, verified by a domain
   expert — for even a modest random subsample of a candidate's exposed population, that sample could
   support a genuine correction via a double-sampling/measurement-error-correction design: the audited
   subsample directly estimates `π` and `δ_A`/`δ_C` separately (§4.1's previously unidentified unknowns),
   and that estimate can then correct the full-population `O1` figure into a defensible `O2` estimate,
   with its own uncertainty propagated from the audit sample's own size. This is a real statistical
   technique (double sampling for validation of a noisy classifier/proxy, e.g. as used for
   measurement-error correction generally) that this document does not build, because the audited data
   source does not exist yet — named here exactly as `ADR-087` asks, as a future direction, not a
   current capability.
3. **An ensemble-of-candidates cross-check** (§4.3), run opportunistically when a genuinely nested
   refinement is independently discovered by search for the same rule — disclosed as unreliable as a
   general mechanism (§4.3), but worth recording as a supplementary signal a future design could surface
   alongside `O1`, never as a substitute for it.

None of these exist today. Naming them is not a promise they will be built; it is the honest answer to
"what would have to be true for `O2` to become reportable beyond tier 3's design-based path," per
`ADR-087`'s own acceptance requirement.

## 10. Acceptance-criteria checklist (mirrors `TASK-080`'s own matrix discipline)

| Acceptance item (`TASK-085`/`ADR-087`) | Addressed |
|---|---|
| Name of each quantity | §0, §7 — `O1` candidate exposure (tier 1, over `E`) + adjustment-consistent candidate exposure (tier 2, over `E_dev`, corrected 2026-08-31), `O2` attributable harmful impact, `O3` latent affected-population impact |
| Target population | §7, per quantity |
| Formal estimand | §7, stated with the same rigor as this project's other estimands |
| Evidence claim permitted | §7, per quantity, tied to `LANGUAGE_RULES` |
| Behavior under a broad surrogate/partial-coverage rule | §5.4 |
| What is shown to a user when attribution is not possible | §5.3 |
| How the benchmark metric should compare like-with-like | §8.3 (sketched; not specified, out of this task's scope to fully build) |
| What additional data source could unlock a stronger claim | §9 |
| Three candidate semantics genuinely investigated, none preselected | §3 (a), §4 (b), §5 (c) |
| Partial-identification achievability investigated, not assumed | §4, negative conclusion, checked against `ADR-077`'s already-reviewed result plus two further avenues |
| Prohibited easy path avoided | §8.3 states explicitly what is and is not proposed; no ground-truth-overlap comparison is recommended anywhere in this document |
| Tier 2 has no implicit cross-split transport (`ADR-089` Check 3, corrected 2026-08-31) | §5.2's inline correction, §7's `O1` estimand — tier 2 scoped to `E_dev`, never the combined window |
| `O1`/`O3` divergence independently reconfirmed on a second axis (`ADR-089` Check 1) | §8.1 — time horizon (`active_booking_months`), in addition to population |
| Historical custody preserved (`ADR-089` Check 6) | §8.4 — `TASK-073`/`TASK-083` unchanged, retirement prospective only |
| Metric 6's fate reached as a consequence, not an assumption | §8.1–§8.4 |
| `TASK-073`/`TASK-083` historical verdicts not rewritten | §8.4, explicit |
| A real, disclosed recommendation given | §6 |
| Design-only; no estimator/engine/gate change | Banner, throughout; §8.4 explicitly declines to edit `decision-gate.md` itself |

## 11. What this document does not do

- Does not change `apply.py`, `economic_impact.py`, `discovery.engine`, any `GateId`/`GateSpec`, any
  `ValidationThresholds` value, or `decision-gate.md`'s text or bands.
- Does not reopen or re-litigate `TASK-080`/`ADR-077`'s own identifiability result — applies it (§4.2)
  under its own stated scope.
- Does not touch `TASK-069`–`084` or any existing `ADR`.
- Does not specify a replacement metric 6, a new `GateId`, or any new tunable threshold — §8.4 names the
  next task explicitly, deliberately not performed here, matching this project's decide/implement
  separation.
