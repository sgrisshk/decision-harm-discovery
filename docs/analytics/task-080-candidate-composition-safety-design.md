# TASK-080 — Candidate-composition safety: design document (`ADR-073`)

**Status: DESIGN ONLY. No implementation.** Nothing in this document changes, or proposes changing,
`discovery.engine`, `apply.py`, `G02`, `G06`, `_development_score`, any threshold value, or
`validation-contract.md` itself. Where this document names a threshold, an enum member, or a gate
mechanism, it is describing the *existing* codebase (read, not modified) or specifying what a later,
distinct implementation task would need to build. `CODE_REVIEWER` reviews this document; no
implementation task opens until that review completes, per this task's own binding instruction.

**Location note.** This document lives in `docs/analytics/`, not `docs/benchmark/`, because it is an
architecture proposal for `discovery.engine`'s and `apply.py`'s design, not a benchmark measurement —
it belongs alongside `discovery-engine-v0.md` and `validation-contract.md`, the two documents whose
seams it reasons across, rather than alongside the `task-0NN-*` forensic reports in `docs/benchmark/`
that measured a fixed, unmodified pipeline. The `task-080-*` filename preserves this project's own
task-provenance naming convention without implying a benchmark-report shape.

**Reading order.** This document assumes familiarity with `docs/benchmark/task-075-t03-forensic-
trace.md`, `task-078-oracle-adjustment-sufficiency.md`, and `task-079-residual-confounding-
forensics.md` (`ADR-071`/`072`/`073`) — it does not re-derive their findings, only cites the
conclusions it builds on.

## 0. Illustrative-example discipline, stated once

Per `TASK-080`'s own binding constraint, every example below that names a specific feature
(`discount_rate`, `paid_search`, `payment_method`, or any travel column) is drawn from `TASK-075`/
`078`/`079`'s own already-published, already-reviewed forensic record, used exactly as those tasks
used it: **to illustrate the general mechanism, never as a target the design below is shaped
around.** No trap ID, pattern ID, or ground-truth `confounded_by` list is used anywhere in the
design reasoning itself (§5–§9) — only in the recap of prior evidence (§1–§2) and in illustrative
asides, each marked "illustrative" at first use in a section. The design's actual mechanism (§8) is
stated entirely in terms of "a base rule," "a candidate atom," and "the development split" — it
would read identically if every travel-specific noun were deleted.

## 1. The central structural problem, stated generically

`discovery.engine` searches conjunctions of decision-time conditions and ranks them by
`_development_score` — a function of a rule's raw, unadjusted per-record outcome difference and its
exposed population size on the development split alone (`engine.py`'s own docstring: "It performs no
inference and makes no causal claim"). `apply.py`'s `G02` gate then excludes every one of a
candidate's own condition features from its adjustment set, because adjusting for the exposure's own
defining variable is circular — a correct, general rule, never in question here.

The structural problem is the interaction of these two correct, individually-justified pieces:

> **Any feature whose raw association with the outcome is strong enough to raise
> `_development_score` when folded into a rule's condition set is, by that same statistical
> property, also exactly the kind of feature that would make a strong confounding control if it
> were available for adjustment instead. Once search folds such a feature into the condition
> (because doing so raised the score), `G02`'s correct exclusion makes it permanently unavailable
> to check whether the very effect that earned the high score is explained by that feature.**

Nothing about this requires a specific feature, dataset, or domain — it is a property of composing
multi-condition rules from a scoring function with no causal-adequacy notion, drawing its features
from the same pool validation later needs for adjustment. `TASK-079` (independently
`CODE_REVIEWER`-confirmed, adversarially, `ADR-073`) established this is not an isolated occurrence:
across the only two traps that have ever produced a real persisted candidate in this project's
official history, the mechanism appeared both times, and a generic sweep across every
adjustment-eligible feature found confounder-labeled features roughly 3.75x more likely than
non-confounder features to be score-increasing when compounded on — a real, aggregate tendency, but
explicitly **not deterministic in either direction** (`TASK-079` §3.4: some true confounders *lower*
score; some non-confounders *raise* it). This last fact is the seed of §6 below: the search score
alone cannot separate "this atom is a confound" from "this atom is a genuine effect modifier,"
because both share the one property the score can see — a strong raw outcome association.

*(Illustrative only, not a design target: `TASK-075`/`079`'s own recovered example is a two-condition
rule whose second condition is strongly outcome-correlated for reasons the trap's ground truth marks
as pure confounding — but the mechanism above is stated, and must remain readable, without reference
to that or any other specific feature identity.)*

## 2. What prior tasks already ruled out, reused here without re-deriving

`TASK-075` ruled out `G06`'s selection ordering as a sufficient explanation (a "sort by relevance"
fix would relocate, not remove, the cardinality cliff — `ADR-071`). `TASK-078` ruled out
"just give `G06` the oracle set" as sufficient — two of five traps still reached `shadow_policy`
under their complete, correctly-covered oracle adjustment sets. `TASK-079` ruled out the estimator's
own computational form (stratification vs. regression, binning granularity — both tested
independently and land within noise of each other) and threshold miscalibration (the E-value floor
and attenuation ceiling separate the "oracle-only" and "oracle-plus-missing-variable" cases with a
wide margin, not marginally) as the primary defect, and attributed survival to **candidate-generation
semantics** — how `discovery.engine` composes multi-condition rules blind to whether an added
condition is itself outcome-correlated. This document is the design response to that attribution,
per `ADR-073`'s own naming of the follow-on task.

One more `TASK-079` finding is load-bearing for §6 below and must not be re-litigated as a G06 defect
here: even a **complete, correctly-covered** oracle adjustment set left a residual effect far larger
than the trap's own construction implies should remain (§2.4 of `task-079`: oracle adjustment removed
only ~11% of the theoretically-removable confounding component, corroborated independently by two
methods). **This project's own estimator has a proven, general ceiling on how much confounding a
simple stratified (or additive-regression) adjustment can remove, even under ideal conditions.** Any
design that relies on "adjust for the atom and see if the effect disappears" inherits this ceiling —
a residual surviving such a check is not proof of a genuine effect, only proof that this specific,
already-limited check did not explain it away. §6 treats this honestly rather than assuming a clean
check is available.

## 3. Solution class 1 — composition-aware scoring/penalty

**The proposal.** An additional atom's contribution to `_development_score` (or a wrapper computed
alongside it) is reduced by a cost term reflecting the adjustability/identifiability it removes from
the resulting rule — e.g., penalizing atoms whose own raw outcome association is strong, on the
theory that such atoms are disproportionately likely to be confounds (§1's 3.75x finding).

**Why this looks attractive.** It intervenes exactly where `TASK-079` measured the symptom
(`_development_score` enrichment), requires no new gate machinery, and is a small, local change to
one already-understood function.

**Why it does not satisfy this task's own criteria, evaluated on the merits.**

1. **The information needed to distinguish a confound from a genuine effect modifier is not present
   at scoring time.** `_development_score` sees only the development split's raw, unadjusted
   per-record outcome difference and population size for the candidate rule itself — exactly the
   same vantage point that makes the underlying problem invisible in the first place. A penalty
   keyed to "this atom's own raw outcome association is strong" cannot distinguish the two cases
   `TASK-079` §3.4 itself already showed are entangled: a true confounder that happens to have a weak
   raw association would escape the penalty, and — the criterion this task names as most important
   and most likely to be silently violated — **a genuine effect-modifying atom has exactly the same
   observable signature** (it also raises the compound rule's score, precisely because the effect it
   modifies really is stronger within its stratum). A scoring penalty built from the same raw
   statistics the score already uses is not a new source of evidence; it is the same evidence,
   double-counted with the sign flipped for a class of atom the penalty cannot actually identify.
2. **A numeric penalty forces a binary trade-off where a three-way distinction is needed.** §6 below
   establishes that a correct treatment of this problem must have three outcomes — confound-like,
   interaction-like, and "cannot tell, on this sample" — with the third case treated as neither
   reject nor promote. A score is a single scalar; it can only push a rule up or down, never say "I
   don't know." Collapsing "cannot tell" into "no penalty" understates the risk exactly where sample
   size is thinnest (early, narrow subrules); collapsing it into "penalty applied" compounds this
   project's already-disclosed problem that rare, genuine patterns are structurally hardest to see
   (`validation-contract.md` §11). Neither collapse is defensible, and a scalar penalty has no third
   option.
3. **Any calibration of the penalty's magnitude is exposed to exactly the overfitting risk this
   project's own discipline forbids.** A penalty large enough to visibly change search's behavior on
   illustrative cases like `TASK-079`'s own recovered examples would, by construction, have been
   tuned by reference to those examples' outcome — the same category of move `TASK-080`'s own
   hard-fixed non-solutions rule out for `G06`/`G12` thresholds, and there is no principled reason a
   new scoring constant is exempt from the same discipline.
4. **Blast radius.** `_development_score` is evaluated for every hypothesis the search evaluates
   (tens of thousands per run, per the `family_size` figures already recorded in this project's
   official runs), not just the handful eventually reported. A change here touches every candidate's
   ranking, not just the compound rules the central problem is actually about, and re-derives the
   exact kind of "relocates rather than removes the problem" risk `ADR-071` already flagged for a
   superficially similar `G06` reordering fix.

**Verdict: rejected as the primary mechanism.** It fails acceptance criterion 2 (interaction
preservation) on the merits, not by assumption, for the same reason `TASK-079` itself concluded the
score "cannot distinguish the two by construction" (§3.4) — that limitation is inherent to what
information the score has access to, and adding a penalty term does not add new information, only a
new way to act incorrectly on the same old information.

## 4. Solution class 2 — counterfactual composition check

**The proposal.** Before a compound rule's second-and-later condition atom is trusted, test directly:
does the base rule's own apparent effect attenuate strongly once the atom's role is changed from
"folded into the condition" to "used as an adjustment covariate for the base rule alone" — the same
kind of stratified, exposure-weighted mean-differencing `_stratified_adjustment` already performs for
`G06`, applied here to a base rule (candidate conditions minus one atom) with a one-variable
adjustment set (that one atom), never to the full compound rule.

**Mechanics, concretely (not proposing new statistical machinery — reusing what already exists).**
For a candidate rule `R = (C1, ..., Ck)`, `k >= 2`, and for each atom `Ci` in `R`:

1. Let `base_i = R` with `Ci` removed (`k-1` conditions). Its raw, unadjusted development-split
   effect (`harm(base_i)`) is already computed by `discovery.engine`'s own `_metric` during search for
   every rule at every depth — no new computation, only a new use of an existing intermediate.
2. Compute the stratified effect of `base_i` adjusted for `Ci` alone (`harm_adjusted(base_i | Ci)`,
   `coverage(base_i | Ci)`) — the identical binning convention (`ADJUSTMENT_QUANTILE_BINS`) and
   exposure-weighted stratification formula `_stratified_adjustment` already implements, just with a
   one-variable adjustment set instead of `G06`'s greedily-grown one.
3. Compare `harm_adjusted(base_i | Ci)` against `harm(base_i)` using the identical attenuation
   notion `G06` already defines (`1 - adjusted/raw`, checked against the existing
   `max_adjusted_attenuation` threshold) — **reusing an already-calibrated, already-audited constant
   rather than introducing a new tunable number**, which matters directly for the anti-overfitting
   discipline: nothing in this check's classification boundary is a new number chosen with this
   project's own traps in view.
4. Compare `harm(R)` (the full compound rule's own already-computed effect) against `harm(base_i)` —
   whether folding `Ci` in concentrated a materially stronger effect than the base rule alone shows.

**Why this can actually distinguish the two cases, to the extent they are distinguishable at all
(full honesty deferred to §6).** Confounding and genuine effect modification produce different
signatures under this specific maneuver: if `Ci` is a common cause of exposure-composition and
outcome (confound-like), stratifying `base_i` by `Ci` should explain most of `base_i`'s own apparent
effect away — strong attenuation. If `Ci` genuinely modifies the effect (interaction-like), `base_i`'s
effect, examined within `Ci`'s own strata, does not get explained away — the *heterogeneity* is real,
not an artifact removed by adjustment, so attenuation stays low even though the compound rule's own
effect (concentrated in `Ci`'s target stratum) is much larger than the base rule's pooled effect.

**Costs and limits, disclosed here, expanded in §6/§10.** The stratification in step 2 can hit
exactly the same coverage-collapse `TASK-079`'s own Branch 3 (`T05`) already demonstrated as a real,
sample-size-driven ceiling, not a selection artifact — this check is not exempt from that ceiling
merely because it operates on a single covariate rather than a joint set; a `base_i` population that
is already narrow before `Ci` is even added can still fail to support a reliable stratified estimate.
This is precisely why §6 requires a third, named "indeterminate" outcome rather than treating this
check as a clean yes/no test.

**This check is deliberately order-independent.** Applying it once per atom, against the rule with
only that atom removed, never against a sequentially-grown or sequentially-ordered subset, avoids the
class of order-dependence defect `ADR-071`'s own adversarial checklist specifically tested `G06`'s
selection for (item 1: "does the retained set change in the direction the mechanism predicts under
reordering"). A leave-one-out check by construction cannot exhibit that failure mode, because no atom
is ever privileged by where it happened to enter the search.

**Verdict: this is a sound, reusable mechanism** — but on its own it only produces a classification
per atom; it does not by itself answer *what to do* with that classification, or *at what stage* to
compute and act on it. §7/§8 resolve that.

## 5. Solution class 3 — dual representation

**The proposal.** A variable that appears in a subgroup's own condition should not, purely by virtue
of appearing there, become invisible to every downstream assessment of its explanatory role — `G02`'s
exclusion (correct: it prevents literally adjusting for the exposure's own defining variable, which
is mathematically circular) should not be the *only* thing validation ever learns about that
variable's relationship to the rule's effect.

**What this is not.** This is not a proposal to weaken or bypass `G02`. Adjusting `X AND C` for `C`
while `C` remains part of the exposure `X AND C` is genuinely circular and stays wrong under this
design, unchanged. What §4's mechanism computes is a *different* quantity that is not circular at
all: the effect of the *base rule* (`X` alone, or `base_i` in the general case) stratified by `C` —
`C` is not part of `base_i`'s own exposure definition in that computation, so no circularity applies.
The "dual representation" is: the subgroup keeps its full condition (`X AND C`) as its own
description, exactly as reported today, while a *separate, disclosed, named* quantity — the leave-
one-out attenuation classification from §4 — travels alongside it, answering a question `G02`'s
exclusion by itself cannot: not "can we adjust the compound rule for its own condition variable"
(no, and that should stay no), but "does removing this variable from the condition and treating it as
a covariate on the rest of the rule change the picture."

**Relationship to §4.** Solution classes 2 and 3 are not independent proposals competing for a slot —
class 2 is the *mechanism* that computes a signal; class 3 is the *representation discipline* that
says the signal must be preserved and disclosed alongside the candidate rather than discarded once a
single pass/fail decision consumes it. §8's recommended design is their combination.

## 6. The interaction-vs-confound distinction — treated in full, not assumed away

This is the hardest and most important question this task poses, and the honest answer has three
parts: what is identifiable in principle, what actually limits identifiability on real, finite
samples, and what the design must therefore do when identification fails.

### 6.1 What is identifiable in principle

Two generative stories produce the same surface symptom (folding an atom into a condition raises the
apparent effect), and they are, in principle, statistically distinguishable by the same maneuver
described in §4:

- **Confounding-as-amplifier.** The candidate atom `Ci` (or something it proxies) is a common cause
  of exposure composition and the outcome. `base_i`'s own effect, examined within `Ci`'s strata,
  mostly disappears — `Ci` "explains away" the association rather than revealing where it is
  strongest.
- **Genuine effect modification (true interaction).** `Ci` marks a subpopulation within which the
  base rule's true causal effect really is larger (or only present at all). `base_i`'s effect,
  examined within `Ci`'s strata, is *not* explained away — it concentrates, without attenuating,
  exactly where `Ci` holds.

These have different statistical signatures (attenuation vs. concentration-without-attenuation), and
§4's check is built specifically to read that difference off the data using an estimator this project
already trusts for an analogous purpose.

### 6.2 What actually limits identifiability on this project's real data — stated as clearly as the
data supports, not more optimistically

Three separate, independently-sufficient reasons this distinction cannot be resolved with full
confidence in every case:

1. **Sample-size/overlap ceiling, identical in kind to `T05`'s.** `TASK-079` Branch 3 proved a sharp,
   arithmetic (not selection-order) ceiling: a modest exposed population simply cannot jointly support
   fine-grained stratification, however chosen. §4's check stratifies an already-narrower population
   (`base_i`, itself a subset of the full candidate) by one more variable — it inherits the identical
   risk, and for deep or already-narrow rules, will hit it *more* often than `G06`'s own joint
   selection does, not less. A "cannot compute reliably" outcome is not an edge case here; it is a
   structurally common one for exactly the compound rules this task is about.
2. **Residual confounding survives even a correct, fully-covered adjustment.** §2 above recapitulates
   `TASK-079`'s own finding: a complete, correctly-covered oracle adjustment removed only a small
   fraction of the confounding it should, by construction, have been able to remove in full. This
   means **a "low attenuation" reading from §4's check is not proof of a genuine interaction** — it
   is equally consistent with a confound whose bias this specific, already-limited stratified
   estimator simply cannot remove. The check can raise confidence in one direction; it cannot certify
   the other.
3. **Confounding-by-proxy is invisible to any observational check, however constructed.** `Ci` may
   itself correlate with a further, unmeasured variable that is the true driver of whatever pattern
   the check reads as "interaction-like." No stratification, adjustment, or estimator variant —
   inside this design or outside it — rules this out. This is the identical, already-disclosed
   ceiling that caps this entire product's evidence at level 3 (`validation-contract.md` §6/§11:
   "unmeasured confounding still possible"; "E-values quantify sensitivity to unmeasured
   confounding; they do not exclude it").

**Direct answer to the question as posed:** this project's own observational evidence can meaningfully
separate the *clear* cases at either end — strong attenuation with adequate coverage is real evidence
of confound-like structure; strong concentration with adequate coverage and low attenuation is real
evidence of interaction-like structure — but **cannot reliably resolve the ambiguous middle**, and
that middle is not a rare corner case given (1) and (2) above. A design that pretends otherwise, by
forcing every atom into "confound" or "interaction," would be wrong exactly as often as this
project's own already-disclosed confounding-adjustment ceiling predicts it would be.

### 6.3 What the design must therefore do — mirroring `T05`'s own treatment, not inventing a new posture

`TASK-079` §4.3 already established a precedent for exactly this situation: a class of case where
validation's available machinery genuinely cannot compute a reliable answer is not the same as an
ordinary gate `FAIL`, and deserves its own **named ceiling** — distinct from reject, distinct from
promote. This task's own instruction requires the identical posture here. §8 specifies three named
outcomes, not two: **confound-like** (evidence ceiling), **interaction-like** (no ceiling from this
mechanism), and **composition-risk indeterminate** (evidence ceiling, distinct reason code from both
`confound-like` and from `T05`'s own overlap-ceiling state, so a reviewer is never left unable to
tell "we think this is a confound," "we cannot tell," and "the confounders are known but jointly
inestimable" apart from each other).

## 7. The stage question — where does the safety invariant belong?

Four candidate stages, evaluated on their own merits per this task's own instruction — not defaulting
to `_development_score` merely because that is where `TASK-079` measured the symptom.

### 7.1 Child generation (blocking certain atom compositions before they are ever scored)

Would require resolving §6's confound-vs-interaction question for every atom pair *before* deciding
whether the combination may even be formed — at the point in the search where the least information
is available (an unscored candidate) and the highest volume of decisions must be made (every
expansion at every depth, not just the handful of candidates eventually reported). A hard block, on
an ambiguous middle case that §6.2 shows is common, must pick a side — and picking "block" fails
criterion 2 (interaction preservation) directly; picking "allow" makes the stage a no-op. This stage
also carries the largest blast radius and the largest philosophical cost: it would require injecting
an inference-flavored judgment into the one layer this project's own code and documentation
repeatedly describe as deliberately inference-free ("It performs no inference and makes no causal
claim," `engine.py`'s own docstring) — for a decision that would then need to be right or fall back to
permissive, which §6 shows it frequently cannot be. **Rejected as the primary invariant location.**

### 7.2 Scoring (`_development_score`)

Addressed in full in §3. **Rejected**, for reasons independent of where `TASK-079` happened to
measure the symptom: the scoring function's own information is the same information that creates the
ambiguity §6 describes, a scalar score structurally cannot represent a three-outcome classification
with a legitimate "cannot tell" state, and any calibration is exposed to the same overfitting risk
this project's own discipline forbids for `G06`/`G12`.

### 7.3 Candidate eligibility (post-scoring, pre-final beam/diversity selection)

Shares §7.1's core defect: an eligibility cutoff is still a binary decision applied before validation
has any chance to see the candidate, at a search-tree scale (every evaluated hypothesis, not the
reported top-K) that makes per-atom stratified checks expensive relative to the benefit, and still
has no way to express "indeterminate" as anything other than "allowed" or "blocked." It additionally
inherits §7.1's blast-radius concern for the beam/diversity/relevance-floor chain specifically named
in this task as off-limits code. **Rejected**, same reasoning as §7.1, one stage later.

### 7.4 Validation/promotion — the recommended location, argued on its own merits

Validation is the only one of the four stages whose native vocabulary already has a representation
for exactly what §6.3 requires: a **named, disclosed evidence ceiling**, distinct from reject and
distinct from promote. `G02` itself already uses this pattern (`FailureAction.CAP_EVIDENCE`,
`max_level_on_failure=EvidenceLevel.PREDICTIVE` — a real, already-shipped instance of "this gate
does not reject outright, it caps how much evidence the finding can claim"). `TASK-079` §4.3
independently arrived at the identical shape for `T05`'s overlap ceiling. A three-outcome
classification (confound-like / interaction-like / indeterminate) maps onto this existing taxonomy
with no new kind of machinery, only a new named state within a pattern this project's gates already
use.

Concretely, this stage has three decisive advantages over §7.1–7.3:

1. **It only ever runs on the small number of candidates that reach promotion, not on the full
   evaluated search.** `apply.py`'s `G06` already recomputes an adjustment set per promoted candidate
   from that candidate's own frozen conditions — the same access pattern this design's check needs
   (§4's mechanism reads only a candidate's own condition tuple plus the frame, exactly like
   `_adjustment_pool` already does). No new field needs to be threaded through `discovery.engine`'s
   output schema at all — the check is entirely reconstructable at validation time from data
   validation already receives.
2. **It leaves search fully permissive, exactly as the founder's own preferred framing states.**
   `discovery.engine`'s scoring, beam, diversity, and feature-identity-cap mechanisms are unchanged in
   every particular — the recommended design touches zero lines of `engine.py`. This directly serves
   this project's own stated differentiation (`PROJECT_CONTEXT.md`: "discovery of previously unknown,
   actionable, policy-worthy interaction patterns") by never risking suppressing a genuine interaction
   at the layer whose entire job is to surface unknown patterns, deferring every judgment about
   *what the pattern means* to the layer whose entire job is exactly that judgment.
3. **Its native vocabulary can actually express "indeterminate" as a first-class outcome**, which
   §6.3 established is not an edge case to special-case away but a structurally common result. A gate
   result with a named reason code is exactly suited to this; a score is not.

### 7.5 The metadata-travels-with-candidate alternative, evaluated on its own merits (not an afterthought)

The founder's preferred framing — "never let the system forget which explanatory variables a subgroup
definition has already absorbed" — is, on inspection, best satisfied *without* discovery.engine ever
needing to carry new metadata at all: because a candidate's own condition tuple already *is* the
record of which variables it absorbed, and §4's check is a pure function of that tuple plus the
frame, "the metadata" is never lost in the first place — it was never anything discovery.engine had
to remember to attach, only something validation had not yet been asked to look at. This is a
stronger, lower-footprint realization of the founder's framing than a literal new schema field would
be: no serialization change, no risk of the metadata silently going stale relative to the candidate it
describes (it is recomputed fresh from the same frozen conditions every time, the same discipline this
project already applies to `_adjustment_pool`), and no new coupling between `discovery.engine`'s output
contract and `apply.py`'s input contract beyond what already exists (the condition tuple itself).

**Conclusion: the safety invariant belongs at validation/promotion.** Not because that is where
`TASK-079` happened to measure the symptom, but because it is the only stage (a) cheap enough to
run the necessary per-atom check against, (b) native to a representation that can express
"indeterminate" without collapsing it into an incorrect binary answer, and (c) capable of enforcing
the invariant without spending any of search's own ability to surface genuine interactions.

## 8. Recommended design

**Combine solution classes 2 and 3, located at validation/promotion (§7.4), computed entirely from a
candidate's own already-frozen condition tuple and the same development-split frame `G06` already
uses — zero changes to `discovery.engine`.**

### 8.1 Mechanism

For a promoted candidate `R = (C1, ..., Ck)`:

- If `k == 1`: no check applies (nothing to leave one atom out of). Candidates unaffected.
- If `k >= 2`: for each `i` in `1..k`, run §4's leave-one-out check (`base_i = R` minus `Ci`,
  stratified adjustment of `base_i` for `Ci` alone), reusing `_stratified_adjustment`'s existing
  binning and estimator logic and `max_adjusted_attenuation`'s existing threshold value — no new
  tunable constant for the attenuation comparison itself.
- Classify each `Ci` against `base_i`:
  - **Confound-like** if `coverage(base_i | Ci)` clears a coverage floor (reusing
    `min_confounder_stratum_coverage`'s existing value and role, the same floor `G06` already applies
    to its own joint stratification, applied here to a strictly simpler one-variable stratification)
    **and** attenuation exceeds `max_adjusted_attenuation`.
  - **Interaction-like** if coverage clears the floor **and** attenuation stays at or below
    `max_adjusted_attenuation` **and** `harm(R)` shows genuine concentration relative to
    `harm(base_i)` (the compounding materially changed the picture, consistent with `Ci` marking a
    real subpopulation rather than being inert).
  - **Composition-risk indeterminate** otherwise — most commonly, `coverage(base_i | Ci)` does not
    clear the floor (§6.2's structurally common case), but also any case whose attenuation reading
    sits ambiguously near the threshold rather than clearly on one side.
- **Rule-level outcome:** if any `Ci` classifies confound-like, the candidate's evidence level is
  capped below `adjusted_observational_association` (mirroring `G02`'s own `CAP_EVIDENCE` /
  `EvidenceLevel.PREDICTIVE` pattern), with a distinct, disclosed reason naming which atom and why.
  Else if any `Ci` classifies indeterminate (and none confound-like), the same cap applies, under a
  **separately named** reason distinct from both the confound-like cap and from `T05`'s own overlap-
  ceiling state — never conflated with either, per this task's own criterion 3. Else (every atom
  interaction-like), no cap from this mechanism; the candidate proceeds through the existing gate
  ladder exactly as it does today.

### 8.2 Why this does not reintroduce §3's objections to a scoring-stage fix

The classification above is computed once per promoted candidate (a handful per run), not once per
evaluated hypothesis (tens of thousands per run) — the cost profile that made a generation/scoring-
stage version of this same check prohibitive does not apply at validation scale. And because the
representation is a named gate-style state, not a scalar, the "indeterminate" outcome is a genuine
third option here, not a forced collapse into one of two numeric directions.

### 8.3 Relationship to existing gates, checked for duplication

Not redundant with `G09` (Simpson's paradox): `G09` checks for sign reversal within strata of the
candidate's own **selected `G06` adjustment covariates** — which, by `G02`'s own exclusion, can never
include a condition feature. This design's check operates specifically on **condition** features,
the exact variable class `G09` structurally cannot reach. The two checks examine disjoint variable
sets and neither substitutes for the other.

## 9. Acceptance-criteria matrix

Applied to the recommended design (§8):

1. **Eliminates or controls the proven advantage.** *Controls, does not eliminate the ranking
   preference itself.* Search still ranks a rule that folds in a strongly outcome-correlated atom
   highly — nothing in this design changes that, and §3/§7.2 argue directly why it should not try to.
   What is controlled is the *consequence* `TASK-080` actually names as the harm: such a rule no
   longer reaches `shadow_policy` (or any level ≥ 3) on the strength of a fold-in whose apparent
   effect is confound-like or indeterminate. The advantage in raw score is preserved (search is
   unconstrained); the advantage in promoted evidence grade is not.
2. **Preserves genuine-interaction detection.** *Satisfied by construction at the search level*
   (zero changes to `_atoms`, `_development_score`, the beam, `_greedy_diverse_select`, or the
   feature-identity cap — every candidate search finds today, it still finds, ranks, and selects
   identically). *At the validation level*, an atom classified interaction-like receives no cap at
   all — the mechanism is designed to leave a genuine effect modifier's evidence grade exactly where
   it would have landed without this check. The honest caveat, stated in §6.2 and not hidden: because
   the interaction-like classification requires clearing a coverage floor and staying under an
   attenuation ceiling, a genuine but weakly-powered interaction can land in "indeterminate" rather
   than "interaction-like" — capped, not rejected, but capped nonetheless. This is the same,
   already-disclosed cost this project's own contract already accepts for rare true patterns
   generally (`validation-contract.md` §11: "rare patterns are structurally invisible... false
   negatives by construction, not analytical failures"), not a new failure mode this design
   introduces.
3. **Defined, `T05`-distinct overlap-ceiling behavior.** *Satisfied.* "Composition-risk
   indeterminate" is a separate named reason code from both "confound-like" and from `T05`'s own
   coverage-ceiling state — a reviewer can always tell which of the three produced a given cap.
4. **Decision-time/leakage compatible.** *Satisfied.* The check uses only `DECISION_TIME` features
   already in the adjustment-eligible pool (the same pool `G06` draws from), computed on the
   development split only, introducing no new information source and no dependency on hidden ground
   truth or any post-decision/outcome field.
5. **Deterministic, reproducible.** *Satisfied.* Every quantity in §8.1 is a closed-form function of
   the frozen candidate's conditions and the frame — the same stratified mean-differencing
   `_stratified_adjustment` already computes deterministically, with no bootstrap or randomness
   required for the classification itself.
6. **Testable against all 5 traps, the 6 historical `PASS` candidates, and multiple domains.**
   *Specified, not run — this is a design-only task.* §10 gives the exact test plan a later
   implementation task must execute.

**For completeness, the same matrix applied to the rejected alternatives:**

| Design | (1) Controls advantage | (2) Preserves interactions | (3) T05-distinct | (4) Decision-time | (5) Deterministic | (6) Testable |
|---|---|---|---|---|---|---|
| §3 Scoring penalty | Partial (same info as problem) | **Fails** — cannot distinguish by construction | N/A (no ceiling concept) | Yes | Yes | Yes, but expensive at full search scale |
| §7.1 Generation blocking | Partial | **Fails** — forced binary on an ambiguous middle | N/A | Yes | Yes | Yes, but largest blast radius |
| §7.3 Eligibility cutoff | Partial | **Fails**, same reason as §7.1 | N/A | Yes | Yes | Yes, same cost concern as §3 |
| §8 Recommended (validation-stage, classes 2+3) | Yes, at the promotion-safety level | Yes, by construction at search; capped-not-rejected at validation for weak cases | Yes | Yes | Yes | Yes, see §10 |

## 10. Test specification for a later implementation task

Not performed here (design-only). A later implementation task must, before travel is examined at
all, per this project's own `TASK-070` synthetic-first precedent:

1. **Synthetic form tests**, neutrally constructed (not travel-specific): a synthetic base rule with
   a known-by-design stable effect, compounded with (a) an atom constructed to be a pure confound
   (outcome-correlated via a shared cause, no true effect-modifying role) and (b) an atom constructed
   to be a genuine effect modifier (the base rule's true effect differs by design across the atom's
   levels) — the mechanism must classify (a) confound-like and (b) interaction-like, at multiple
   population sizes including ones deliberately built to fail the coverage floor (verifying the
   indeterminate path fires correctly, not just the two clear-cut ones).
2. **All 5 traps** (`T01`–`T05`), using their real or counterfactual conditions exactly as `TASK-075`/
   `078`/`079` already reconstruct them (never retyped by hand) — checked for whether the mechanism's
   classification is consistent with each trap's already-published forensic finding, without this
   check being tuned to produce that outcome (the synthetic tests in item 1 must be designed and
   frozen first, exactly as `TASK-070`'s own hard rule required for its own gate fix).
3. **The 6 real historical `PASS` candidates** (`TASK-075`'s own negative-control set) — must not
   receive a confound-like or indeterminate cap that changes their historical evidence level, unless
   a later, independently-justified investigation finds a genuine reason one of them should have.
4. **More than one domain**, matching `TASK-070`'s own precedent — the synthetic domains already
   built under `TASK-061` are the natural reuse, not a travel-only regression suite.
5. **Order-independence check**, mirroring `ADR-071`'s own adversarial standard for `G06`: confirm
   the leave-one-out classification is identical regardless of the order conditions were added to the
   rule during search (a property the design in §8.1 already provides by construction, but which
   should be independently verified against the real implementation, not merely assumed from the
   design).

## 11. Hard-fixed non-solutions — compliance confirmed

- **No confounder-like feature named or class-identified anywhere in the design (§3–§9).** The
  mechanism is stated entirely in terms of "atom `Ci`," "base rule `base_i`," and generic
  DECISION_TIME/adjustment-eligible pool membership. Only §1–§2's recap of already-published prior
  findings and explicitly marked "illustrative" asides reference any specific feature, and none of
  those references shape any part of the actual mechanism in §8.
- **No trap ID or ground-truth identity used as justification for any design choice.** §1–§2's recap
  of `TASK-075`/`078`/`079`'s conclusions is citation of already-reviewed prior evidence, not new use
  of ground truth — this document never opens `hidden_ground_truth.json` and does not need to; every
  number it cites is already published in the reviewed forensic docs.
- **`G06`'s coverage floor (`min_confounder_stratum_coverage`) is read, reused at its existing value,
  and not lowered anywhere.** §8.1 explicitly reuses the existing constant rather than proposing a new
  or relaxed one.
- **No `G06`/`G12` threshold strengthened, and none motivated by `T03`/`T04`'s specific outcomes.**
  This design adds a new, separately-named gate-style outcome; it does not change any existing gate's
  threshold, and the one threshold it reuses (`max_adjusted_attenuation`) is read at its current value,
  not tightened.
- **No penalty for compound-rule depth.** The classification in §8.1 is per-atom (leave-one-out against
  the rest of the rule), not per-depth — a 3-condition rule whose every atom classifies
  interaction-like receives no cap at all, regardless of its depth; a 2-condition rule with one
  confound-like atom is capped exactly as a 4-condition rule with one confound-like atom would be.
  Depth itself never enters the classification.

## 12. What this design does not solve — disclosed, not glossed over

- **Crowding-out of a genuine, weaker interaction by a confound-amplified rescaling of a different,
  false pattern is not addressed by this design.** Because search itself is unchanged, a confound-
  amplified compound rule can still win a `_greedy_diverse_select` top-K slot a true, more modest
  interaction might otherwise have filled — this design prevents the confound-amplified rule from
  reaching a high evidence grade, but does not prevent it from occupying a reported slot. This is not
  a new problem this design introduces; it is the same crowding-out concern `TASK-060`/`TASK-068`
  already partially addressed for other axes (population overlap, feature-identity crowding), left
  unresolved for this specific axis, and explicitly out of this task's own scope (a search-recall
  question, not a promotion-safety question).
- **The classification inherits `TASK-079`'s own proven estimator-adequacy ceiling.** As §6.2 states
  plainly: an "interaction-like" (low-attenuation) reading is evidence for, not proof of, a genuine
  effect, because even a complete, correctly-covered adjustment has been shown to leave meaningful
  residual bias on this project's own data. This design does not — and, given `TASK-079`'s finding,
  cannot — certify a candidate as truly causal; it only prevents the specific, proven promotion
  advantage from operating unchecked, consistent with this product's own disclosed level-3 ceiling.
- **Threshold and floor values used by the recommended design (§8.1) are read from existing,
  already-calibrated constants, but a later implementation task must still confirm those values
  transfer correctly to this new use** (a one-variable adjustment is a strictly simpler stratification
  than `G06`'s own joint one) — via the synthetic-first test plan in §10, before any travel-specific
  number is examined, exactly as `TASK-070`'s own precedent requires.

## 13. Recommendation, stated plainly

**Recommended: the combined solution-class-2/3 design in §8, located at validation/promotion (§7.4),
computed entirely from a candidate's own frozen condition tuple with zero changes to
`discovery.engine`.** This is not an "honest non-recommendation" — the analysis above supports a
specific answer with a specific rationale for why the earlier stages (§7.1–§7.3) and the pure-scoring
alternative (§3) fail acceptance criterion 2 on the merits, and why validation is the only stage whose
existing representational vocabulary (`CAP_EVIDENCE`-style named states) can express the three-outcome
distinction §6 shows is actually necessary.

**What is genuinely open, disclosed rather than assumed:** whether the reused thresholds
(`max_adjusted_attenuation`, `min_confounder_stratum_coverage`) transfer without adjustment to a
one-variable stratification, and exactly how often real (not synthetic) rules land in the
"indeterminate" bucket rather than a clean classification — both are empirical questions the §10 test
plan is built to answer, and neither is decided here, per this task's own design-only scope. A
later, distinct implementation task performs §10's test plan and, if it holds up, implements §8;
`CODE_REVIEWER` reviews this document first, per `ADR-073`'s own instruction, before that
implementation task opens.
