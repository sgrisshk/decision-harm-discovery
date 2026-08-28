# TASK-069 item 2 — is `G12` measuring the right thing? A form investigation

**Status: POST-HOC DIAGNOSTIC throughout.** Every number in this document is produced by
`scripts/diagnose_g12_perturbation_form.py`, run for real on 2026-08-28. Nothing here is a new
official `TASK-015`/`TASK-019`/`TASK-028` run, changes any frozen artifact, threshold, gate, or
recorded verdict, or touches `packages/analytics/src/policy_analytics/validation/` or any other
production module — `validation/apply.py` is imported unmodified and is what computes the real
numbers below. Raw computed output: `docs/benchmark/task-069-g12-form-investigation-raw.json`.

**What this closes.** `TASK-069`'s reformulation, **item 2** — "investigate `G12` as a standalone
statistical question", named there as "the actual next experiment, ahead of any benchmark-semantics
write-up". Item 1 (`docs/benchmark/task-069-validation-power-autopsy.md`) established that `P01` and
`P03` pass every level-2 gate except `G12` by orders of magnitude and that `G12`'s two binding
sub-checks are the numeric-threshold perturbation and the `gross_profit_eur` alternative outcome; its
§6 listed the form questions as "real design questions that this document does not answer and is
forbidden from answering". Item 2 asks the prior question those depend on: **is `G12` measuring
instability of the phenomenon, or instability of a discrete representation of a continuous decision
boundary?** This document answers that and nothing else.

**Binding constraint, restated and honoured.** `TASK-069`'s hard rule explicitly covers `G12`: "the
question is whether the gate's *form* fits threshold-rule hypotheses in general, never whether
`P01`/`P03` specifically should pass it." Accordingly the verdict below is established **entirely on
neutrally-constructed synthetic data** — invented columns, invented distributions, data-generating
processes whose stability is known by construction, and thresholds swept across the whole percentile
range rather than chosen (§2). The measurements on travel's oracle atoms (§3) are reported as
measurement and are *not* the basis of the verdict; **no per-pattern counterfactual `G12` verdict is
computed or claimed anywhere in this document.** No gate, threshold, estimator, or perturbation rule
is proposed, scoped, or designed. §6 states what a follow-on would have to cover without doing any of
it.

## 1. Verdict

**`G12` is form-mismatched for numeric-threshold rules, and in two independent ways.** Not "too
strict" — mismatched: for the sub-checks that bind, the quantity `G12` reports is a deterministic
function of something other than the effect's stability.

| Sub-check | What it is supposed to measure | What it demonstrably measures | Evidence |
|---|---|---|---|
| Numeric-threshold perturbation | "does the effect depend on one arbitrary cutoff?" | **where the atom's threshold sits in its own column**, via the exposure change the fixed grid forces | §2: on an effect that is *maximally stable by construction*, the deviation matches a closed form in the two thresholds' percentiles to a mean absolute residual of **0.0008** over **516** refits, and the gate's verdict flips from pass to fail purely as the threshold is swept |
| `gross_profit_eur` alternative outcome | "does the effect survive a different outcome definition?" | **the share of the pattern's harm that reaches the decomposition component**, an accounting identity | §4: measured deviation equals the ground truth's own primary-vs-alternative effect ratio to within **1.6 points** for every pattern where the alternative effect is non-zero |

Two consequences follow, and they are different in kind:

1. **The perturbation grid is not a "one-bin" perturbation, except at one point.** For an effect that
   is uniform across its own exposed side — the most stable a localised threshold rule can possibly
   be — the production grid passes only when the atom's threshold sits between the **12.5th and
   57.5th percentile** of its own column. That window is solved from the closed form at 0.001
   resolution and is **[0.125, 0.575] for `ge` and `lt` alike**; the simulated sweep's own pass
   window, at its coarser 0.05 spacing, is [0.15, 0.55]. `discovery.engine._atoms` places every
   numeric atom on the
   **0.2 / 0.4 / 0.6 / 0.8** quantile grid. **Two of those four grid points lie outside the window**,
   so half of the engine's own numeric vocabulary cannot pass `G12`'s threshold check no matter how
   stable the underlying effect is.
2. **The mismatch is bidirectional, not conservative.** In the same sweep the production grid
   *passes* a genuinely cutoff-dependent effect — one that exists only in a 2-percentile-point sliver
   and is exactly the "artefact of where you cut" the gate exists to catch — in **16 of 68**
   continuous-column cells, concentrated in the same mid-percentile band where it also passes stable
   effects. A gate whose false-alarm and missed-detection rates are both governed by threshold
   position is not a strict gate; it is measuring the wrong quantity.

**What this does *not* say.** It does not say `P01`/`P03` should pass `G12`, does not say the 50%
ceiling or the 90% sign floor are wrong, and does not say robustness testing should be weakened. The
`G12` *question* — does this effect depend on one cluster, one outlier, or one arbitrary cutoff — is
the right question, and its other two check families behave exactly as designed throughout (§4.1):
winsorisation stays between **0.2% and 15.3%** for every scoreable pattern, and leave-one-cluster-out
passes for every pattern except the two whose exposed groups are degenerate on their own terms (P04
at 91.3%, P08 at 55.6% on 35 exposed records) — in both of which item 1 already identified `G03`
sample adequacy as the binding gate.

## 2. The decisive experiment — neutral synthetic data, no benchmark, no ground truth

### 2.1 Construction

`scripts/diagnose_g12_perturbation_form.py` §A builds a dataset of 40,000 rows with one feature
(`signal_metric`) and one outcome (`value_metric`), both invented, and sweeps:

- **3 column distributions** — `uniform`, `lognormal`, and a coarse integer column (`discrete_small`)
  whose resolution is deliberately too low for a fine percentile step;
- **2 operators** — `ge` and `lt`;
- **17 threshold percentiles** — 0.10 to 0.90 in steps of 0.05, swept rather than chosen;
- **3 data-generating processes**, each defined purely in percentile space *relative to the rule's
  own exposed side*, so the same process means the same thing at every threshold:
  - `step_stable` — the effect applies uniformly across the whole exposed side. **Maximally stable:
    it is the same localised threshold phenomenon at every swept threshold, and moving the cutoff
    cannot make it appear or disappear.**
  - `spike_cutoff_dependent` — the effect exists only within 2 percentile points of the boundary.
    **Genuinely an artefact of exactly where the cut falls; a robustness gate *should* flag it.**
  - `ramp` — the effect grows with distance past the cutoff. Neither knife-edge nor uniform.

For each cell it runs `_robustness_battery`'s threshold-perturbation family (same control flow, same
`rule_expr`/`split_stats`, same `round(..., 8)`) under three grids:

| Grid | Quantiles used | Provenance |
|---|---|---|
| `production_fixed_quantiles` | the column's fixed `PERTURBATION_QUANTILES = (0.15, 0.25)` | production, unmodified |
| `diagnostic_relative_percentile_step` | the atom's own percentile **± 0.05** | the production constant's own half-width |
| `diagnostic_relative_exposure_step` | a **± 25%** change in exposed population | the production constant's own exposure change at its q0.20 anchor |

**The two non-production grids are diagnostic counterfactuals, not proposals.** Their only purpose is
to establish whether the production grid's verdicts are forced by the data or by the grid's
construction. Every constant in them is read off `PERTURBATION_QUANTILES` itself — `(0.15, 0.25)` is
a pair symmetric about q0.20 with half-width 0.05 — never from any observed result. Neither is
recommended, and §5 records that one of them behaves *worse* than production on part of the sweep.

### 2.2 On a maximally stable effect, the deviation is a closed form in threshold position

For a `step_stable` process the perturbed estimate is pure set arithmetic: with the affected region
equal to the true rule's own exposed region, the refit's difference in means is (affected share of
the perturbed exposed group) − (affected share of the perturbed comparison group). Nothing about the
effect's stability enters. The script computes that closed form per refit and records the residual
against the realised numbers.

| | value |
|---|---|
| Refits compared (continuous columns, both operators, all three grids) | **516** |
| Mean absolute residual, observed deviation vs. closed form | **0.000765** |
| Max absolute residual | **0.057** |

The production grid's own numbers on the `uniform` column, `ge` and `lt` giving the same answer:

| Threshold percentile | 0.10 | 0.15 | 0.20 | 0.25 | 0.35 | 0.45 | 0.55 | 0.60 | 0.70 | 0.80 | 0.90 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Deviation (`ge`) | 60% | 40% | 20% | **12%** | 24% | 35% | 47% | 53% | 65% | 76% | 88% |
| Closed form | 60% | 40% | 20% | 12% | 24% | 35% | 47% | 53% | 65% | 77% | 88% |
| `G12` verdict | **fail** | pass | pass | pass | pass | pass | pass | **fail** | **fail** | **fail** | **fail** |

The effect is identical in every column of that table. The measured "instability" is not.

**The minimum sits at the production anchor.** Deviation is minimised at ≈q0.20 — where `(0.15,
0.25)` *is* a ±5-percentile-point step — and grows in both directions from there. The constant
encodes a threshold at the 20th percentile as its design point; the contract's own wording ("one-bin
perturbation of every numeric threshold", `GATE_SPECS[G12].rule`, and the code comment "one bin below
/ above each threshold") describes a step *relative to each threshold*, which the implementation
realises for exactly one atom position. §5 records this as a documented divergence, not a proposal.

### 2.3 The confusion table — flag rates on processes whose stability is known a priori

Continuous columns, 68 cells per process (2 distributions × 2 operators × 17 percentiles). "Flagged"
applies `G12`'s real conjunction — sign agreement ≥ 90% **and** max deviation ≤ 50% — to the
threshold-perturbation family in isolation (an isolation this document discloses everywhere it uses
it, and never presents as the production verdict).

| Grid | `step_stable` flagged *(false alarms)* | `spike_cutoff_dependent` flagged *(true detections)* | `ramp` flagged |
|---|---|---|---|
| `production_fixed_quantiles` | **32 / 68 (47%)** | 52 / 68 (76%) — **16 missed** | 16 / 68 (24%) |
| `diagnostic_relative_percentile_step` | **0 / 68 (0%)** | **68 / 68 (100%)** | 0 / 68 (0%) |
| `diagnostic_relative_exposure_step` | 20 / 68 (29%) | 68 / 68 (100%) | 16 / 68 (24%) |

Read the first row twice. The production grid flags nearly half of a set of maximally stable effects,
and misses a quarter of a set of effects that are *definitionally* cutoff artefacts — and the cells
it misses (`ge`, percentiles 0.25–0.55) are inside the same band where it passes stable ones. Its
verdict tracks threshold position; it does not track stability.

The second row is the alternative hypothesis' test, and it fails: if `P01`/`P03`-shaped verdicts were
forced by the data, no change to the grid's *reference point* — holding its step size and its check
count fixed — could separate stable from fragile processes. One does, cleanly, in 136 of 136 cells.

**Pass window on a maximally stable effect** (realised threshold percentile, continuous columns):

| Grid | passes for thresholds in | cells passing (of 68) |
|---|---|---|
| `production_fixed_quantiles` | **[0.15, 0.55]** | 36 |
| `diagnostic_relative_percentile_step` | [0.10, 0.90] — the whole swept range | 68 |
| `diagnostic_relative_exposure_step` | [0.20, 0.80] | 48 |

Solved from the closed form rather than the sweep, at 0.001 resolution, the production grid's window
is **[0.125, 0.575]** — the same interval for `ge` and for `lt`. The engine's `ge`/`lt` atoms at
q0.60 and q0.80 sit outside it; its atoms at q0.20 and q0.40 sit inside.

### 2.4 The coarse-integer column: every cell fails, for every process

On the `discrete_small` column the production grid flags **24 / 24** cells for each of the three
processes — `step_stable`, `spike_cutoff_dependent` and `ramp` alike. The mechanism is degeneracy,
not instability: the column's 0.15 and 0.25 quantiles both land on its minimum, so `ge <min>` selects
every row and `lt <min>` selects none; `split_stats` returns `None`, and `_robustness_battery`'s
`_record` counts that as a check that ran and did not agree. **All 144 refits across all 72 cells
produce no estimate at all**; sign agreement collapses to zero and the gate fails regardless of what
the data contains.

The relative-percentile counterfactual is not immune, in the mirror-image way: on the same column
**66 of its 144 refits are vacuous** — the perturbed threshold rounds back onto the atom's own value,
so the "check" re-estimates the identical rule — and 24 more are degenerate. **Neither behaviour is
acceptable and neither is fixed here**; both are recorded because a follow-on has to handle coarse
columns explicitly rather than inherit either failure mode.

## 3. The same comparison on the real oracle atoms — measurement, not verdict

Fidelity first: for every pattern the script recomputes the full battery through the real, unmodified
`_robustness_battery` and refuses to report unless its aggregates reproduce item 1's committed raw
output (sign agreement, max deviation, check count). They do, for all nine projections.

Maximum deviation of the **threshold-perturbation family alone**, per grid:

| Pattern | production fixed | relative percentile step | relative exposure step |
|---|---:|---:|---:|
| P01 | **66%** | 39% | 39% |
| P02 | 38% | 43% | 43% |
| P03 | **71%** | 35% | 35% |
| P04 | 21% | 14% | 18% |
| P05 *(non-scoreable)* | 82% | 144% | 310% |
| **P06** *(control)* | 30% | **30%** | 47% |
| P07 | *(no numeric atom)* | — | — |
| P08 | 72% *(+1 degenerate refit)* | 25% *(+1 degenerate)* | 49% *(+3 degenerate)* |
| P09 | 93% | **94%** | 94% |

Three things in that table are worth stating precisely, and none of them is a verdict:

- **P06, the control, is the proof that the production grid *is* the relative grid — at one point.**
  Its only numeric atom sits at percentile 0.200, so the production quantiles (0.15, 0.25) and the
  relative ones (0.14984, 0.24984) are the same grid, and the two columns are identical to the last
  digit. Every other pattern's numeric atom sits somewhere else.
- **P09 is the counter-example that shows the comparison is not a blanket relaxation.** Its atom sits
  at percentile 0.789, like P03's — yet its deviation is 93% under the production grid and **94%**
  under a matched ±5-point step: moving its threshold from 4 to 3 collapses the estimate on its own
  terms. Whatever else is true, P09's threshold sensitivity is not an artefact of the grid's
  reference point. (Item 1 separately established P09 as conclusively data-limited: its exact true
  rule misses BH's most lenient bar by ~3,450×.)
- **The production grid's two refits are sometimes one refit.** For P03's `installments ge 3.0`, the
  column's 0.15 and 0.25 quantiles are *both* 1.0 — the two "independent" perturbations are the same
  rule, evaluated twice, each growing the exposed group 5.45×. The nominal two-sided check is
  one-sided in fact. The relative counterfactual has the mirror problem on the same column: its
  upward step rounds back onto the atom's own value and tests nothing.

Per-refit detail for the two patterns item 1 flagged, recorded because the exposure arithmetic is the
whole story:

| Atom | own percentile | production → | exposed n | growth | deviation |
|---|---:|---|---:|---:|---:|
| `booking_lead_days lt 23.0` (P01) | 0.200 | 16.0 / 29.0 | 59 / 102 | 0.75× / 1.29× | 17% / 17% |
| `discount_rate ge 0.12` (P01) | 0.725 | **0.0** / 0.03 | **320** / 264 | **4.05×** / 3.34× | **66%** / 59% |
| `installments ge 3.0` (P03) | 0.788 | **1.0** / 1.0 | **829** / 829 | **5.45×** / 5.45× | **71%** / 71% |

`discount_rate ge 0.0` and `installments ge 1.0` are conditions every row satisfies. The refit is not
a perturbed version of the candidate; it is the candidate with one of its conditions deleted.

**No counterfactual verdict is drawn from this table.** Whether any particular pattern would or would
not clear `G12` under any particular alternative is a question about a gate design that does not
exist, and answering it from these seven rules is precisely what the hard rule forbids. The verdict
in §1 rests on §2 alone.

## 4. The second, independent form problem — `gross_profit_eur` as an equal-footing refit

Item 1 flagged this separately and asked whether it is a distinct contributor. **It is, it is
independent of the threshold grid, and it is quantifiable exactly.**

`outcomes/contract.py` defines `gross_profit_eur` as `decomposition_of` `contribution_margin_eur` —
net revenue minus base cost and refunds, *before* support cost, additional realized cost and payment
fees. `G12` nonetheless uses it as an equal-footing refit and requires magnitude parity within ±50%
and sign agreement.

**What that check can attain at best.** `hidden_ground_truth.json` records each pattern's realised
counterfactual effect on *both* outcomes. Their ratio is the deviation the check must report if it
estimates both perfectly — an accounting identity with no stability content whatsoever:

| Pattern | measured deviation | attainable deviation *(ground truth)* | ceiling | check alone |
|---|---:|---:|---:|---|
| P01 | 45.3% | **46.9%** | 50% | pass |
| P02 | 89.0% | **100.0%** | 50% | fail |
| P03 | 70.1% | **70.5%** | 50% | fail |
| P04 | 138.4% | 100.0% | 50% | fail |
| **P06** | 31.8% | **31.8%** | 50% | pass |
| P08 | 88.3% | 100.0% | 50% | fail |
| P09 | 75.6% | 100.0% | 50% | fail |

Where the alternative outcome carries a non-zero effect the measured deviation reproduces the
identity to within 1.6 percentage points, and for P06 to three decimal places. **For five of the
seven scoreable patterns the attainable deviation is exactly 100%** — their configured harm runs
entirely through channels gross profit structurally cannot see, so their gross-profit effect is
*zero by construction*. No candidate recovering those five can pass this sub-check at any sample
size, with any estimator, however stable its effect. That is not a robustness result.

**Neutral confirmation, truth-free.** §A.4 of the script builds a synthetic outcome as the sum of two
additive channels and a "decomposition" outcome that omits one of them, with a maximally stable
`step_stable` pattern acting only through the omitted channel. The alternative-outcome refit reports
a **99.9%** magnitude deviation against a 50% ceiling. The construction has no benchmark, no ground
truth and no pattern identity in it; the deviation is forced by the outcome algebra alone.

### 4.1 Which sub-check binds, per pattern

Recomputed by re-running `G12`'s own two rules over each check family alone and over its complement
(the same disclosed isolation as §2.3):

| Pattern | threshold perturbation alone | alt outcome alone | leave-one-out alone | winsorise alone | `G12` fails without perturbation? | without alt outcome? |
|---|---:|---:|---:|---:|---|---|
| P01 | **66.2%** fail | 45.3% pass | 8.4% pass | 4.6% pass | **no** | yes |
| P02 | 38.2% pass | **89.0%** fail *(sign flip)* | 41.6% pass | 10.5% pass | yes | **no** |
| P03 | **71.3%** fail | **70.1%** fail | 10.3% pass | 1.1% pass | **yes** | **yes** |
| P04 | 20.8% pass | **138.4%** fail | 91.3% fail | 0.2% pass | yes | yes |
| **P06** | 29.6% pass | 31.8% pass | 19.6% pass | 12.4% pass | *(passes)* | *(passes)* |
| P08 | 71.7% fail *(sign 25%)* | **88.3%** fail *(sign flip)* | 55.6% fail | 7.3% pass | yes | yes |
| P09 | **93.2%** fail *(sign 50%)* | 75.6% fail | 30.4% pass | 15.3% pass | yes | yes |

**The two form problems are separate and neither subsumes the other.** For `P01` the threshold grid
is the whole story and the alternative outcome passes. For `P03` **both** sub-checks exceed the
ceiling independently — removing either leaves the other binding. For `P02`/`P04`/`P08`/`P09` the
alternative outcome binds regardless, though item 1 already showed those four are capped by
`G03`/`G05` on grounds a perfect `G12` would not touch.

## 5. Was a relative step already considered and rejected?

**No — the opposite.** The preregistered wording *specifies* a relative step and the implementation
does not realise it:

- `docs/analytics/validation-contract.md` §5 and `GATE_SPECS[G12].rule` both state "**one-bin
  perturbation of every numeric threshold**".
- `apply.py`'s own comment on the constant reads "`# one bin below / above each threshold`".
- The implementation replaces the threshold with the column's fixed 0.15 and 0.25 quantiles
  regardless of where the atom sits — a genuine one-bin step only for an atom at ≈q0.20, as P06's
  identical grid columns in §3 show directly.

`PERTURBATION_QUANTILES = (0.15, 0.25)` and `DiscoveryConfig.numeric_quantiles = (0.2, 0.4, 0.6,
0.8)` were introduced in the **same initial commit**; no `ADR` in `DECISIONS.md` and no `TASKS.md`
entry discusses the perturbation grid's form, evaluates a relative alternative, or records a reason
for a fixed one. There is no rejected alternative to defer to. Per `engineering rules` ("if code conflicts
with architecture documentation, do not silently choose one — report the conflict"), **this document
reports the divergence and deliberately does not resolve it**: resolving it is a validation-contract
change, and `TASK-069`'s hard rule forbids this investigation from designing one.

**The counterfactuals are not candidate designs, and this document does not endorse either.** The
relative-percentile variant separates the synthetic processes cleanly (§2.3) but produces vacuous
no-op refits on coarse integer columns (§2.4) and, on one non-scoreable real rule, a *larger*
deviation than production (§3, P05: 82% → 144%). The relative-exposure variant still flags 29% of
maximally stable cells. Both are diagnostics that answer "is the production verdict forced by the
data?"; neither is a specification, and picking between them — or neither — is exactly the design
work this task must not do.

## 6. What this settles for `TASK-069`, and what it authorises

**Settled.** `G12` is **form-mismatched** for numeric-threshold rules, in the specific sense that its
two binding sub-checks report quantities determined by threshold position and by outcome
decomposition respectively, not by the effect's stability. Item 2's first branch — "`G12` is
correctly calibrated and `P01`/`P03` are genuinely fragile" — is **rejected on neutral synthetic
evidence**: a maximally stable, maximally localised threshold effect fails the production check
whenever its threshold sits outside [0.125, 0.575] of its own column, and a genuinely
cutoff-dependent effect passes it inside part of that same band.

**Settled about the achievable denominator, and it cuts the other way from a kill.** Item 1's "at
most 3 of 7" rested on `P01` and `P03` being achievable-if-`G12`'s cap is not a genuine property of
their effects. This investigation shows the cap is not a genuine property of *any* effect at those
threshold positions. So **the "denominator = 3" hope is not killed** — but it is now known to be
**contingent on a validation-contract question, not on the data**, and the contingency is different
for the two patterns:

- Under the **current, unmodified contract**, `P01` and `P03` cap at `descriptive_observation`, and
  that remains the honest recorded outcome until and unless the contract is versioned.
- `P01`'s cap rests on the threshold grid alone. `P03`'s rests on the threshold grid **and**,
  independently, on the decomposition-outcome check — so a change addressing only one of the two
  would leave `P03` capped.
- Therefore reformulation step 1 (record the achievable denominator as a reporting convention)
  **must name the contract version the denominator is computed under**, and must not record
  "denominator = 3" as a property of the dataset. The number is a joint property of the dataset *and*
  the robustness gate's form.

**Explicitly not settled, and not settleable here.** What a threshold perturbation should be defined
relative to; whether it should test both sides of the atom; how degenerate and vacuous refits should
count; how coarse integer columns should be handled; and whether a `decomposition_of` outcome may be
used as a magnitude-parity refit at all. This document deliberately answers none of them.

**What a follow-on task would have to cover** — named, per item 2's own wording ("opens a distinct,
justified follow-on task — fixing robustness semantics without reducing confounder safety, never
framed as 'raise recall'"). **It is not opened here, and nothing below is a design:**

1. **Reconcile the contract text with the implementation.** The preregistered rule says "one-bin
   perturbation of every numeric threshold"; the code implements fixed absolute quantiles. Decide
   which is the intent, generically, and make the two agree.
2. **Define what the perturbation is testing**, including direction (both sides of the atom, or
   only broadening), what "one bin" means when the hypothesis language's own bin width is a
   parameter, and what happens when the column's resolution cannot express the step.
3. **Define the accounting for degenerate and vacuous refits** — a refit that produces no estimate,
   and a refit identical to the candidate, currently reach the gate's two aggregates by different
   and unintended routes.
4. **Decide the role of a `decomposition_of` outcome in robustness** — whether magnitude parity
   against a component of the primary outcome is a coherent requirement at all, or whether the
   comparison belongs on direction/attribution, and whether the manifest's
   `validation_roles.alternative_outcome` should be constrained by outcome role.
5. **Constraints any such work inherits:** it must be specified *before* being measured against any
   benchmark; it must be versioned under validation-contract §2, which requires re-grading every
   finding graded under the previous version; it must not reduce `G06`'s confounder safety or `G12`'s
   other three check families, which behave correctly throughout this investigation; it must be
   validated on more than one domain, since the atom grid and the perturbation constant are
   domain-generic; and per `TASK-069`'s hard rule it must be motivated and justified generically —
   never by reference to travel's seven pattern identities, and never framed as raising recall.
6. **Sequencing note, not a recommendation:** `P03` remains flagged by item 7 as trap-`T03`-unsafe to
   chase until `G06`'s generalisation is evaluated on its own schedule. That flag is unaffected by
   anything here.

**No mechanism, gate, threshold, estimator, perturbation rule, eligibility change, or search change
is proposed, scoped, or authorised by this document, and none has started.**

## 7. Reproduction

```sh
# Section A only — the decisive experiment. Requires no frozen artifacts and reads no benchmark data.
uv run python scripts/diagnose_g12_perturbation_form.py --synthetic-only

# All sections, including the real-atom measurement.
uv run python scripts/diagnose_g12_perturbation_form.py
uv run python scripts/diagnose_g12_perturbation_form.py --blind-root /path/to/checkout/artifacts/blind
```

Sections B and C require a checkout holding `artifacts/blind/task-064-beam-20260822-001.*`
(gitignored and per-checkout, reproducible); Section A does not. Output is byte-reproducible across
runs — the synthetic sweep is seeded and the recording order is fixed.
