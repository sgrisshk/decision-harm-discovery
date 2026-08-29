# Real-Data Decision Gate — Pre-Registered

**Owner:** FOUNDER_STRATEGY
**Support:** ARCHITECT
**Recorded:** 2026-08-29, against commit `eb7fc6f` (`TASK-069`: record founder-proposed research
plan and anti-overfitting hard rule — the most recent commit on `main` at the time this document
was written)
**Task:** `TASK-074` (opened by `ADR-066`'s named, not-opened, follow-on gap)
**Status:** PRE-REGISTERED. No real (non-synthetic) customer dataset has been ingested as of this
commit — `TASK-057` is `BLOCKED` (`ADR-063`), `TASK-037` is `BLOCKED` on `TASK-057`, `TASK-038` is
`BLOCKED` on `TASK-037`. This document must not be edited after a first real run produces a
result — only appended to, under "Post-run review log," matching
`docs/benchmark/decision-gate.md`'s own append-only discipline.

## Why this exists, and why now

`docs/benchmark/decision-gate.md` fixed, before `TASK-028` ever ran, what a *good* and a *bad*
result would look like against the synthetic benchmark's hidden ground truth. That document works
because a hidden ground truth exists: `TASK-028` can compute recall against known patterns, count
leakage violations mechanically, and check effect direction against a known counterfactual. None of
that machinery survives contact with a real customer dataset. There is no `hidden_ground_truth.json`
for a real business — no injected patterns, no known traps, no counterfactual outcome to score a
candidate's effect direction against. `ADR-066` named this gap explicitly when it declined to open
real-data ingestion: "a real run's own results have no pre-registered bar to be judged against once
obtained." `TASK-072`'s determination corroborated the same point independently: a real run
"answers a different question (does the mechanism produce plausible, defensible, correctly-signed
findings a human domain expert would trust) than the one the cited synthetic numbers measure."

This document is that pre-registered bar, written the same way `decision-gate.md` was: before
anyone — including this agent — has seen a single real candidate. `ADR-007`/`ADR-012`'s standing
discipline against premature precision applies here with, if anything, more force than it did to
the synthetic gate: defining "good result" *after* seeing a real run's output would not merely risk
overfitting a threshold to one result, it would let whoever is writing the criteria unconsciously
grade toward whatever the pipeline happened to produce, on the one class of result this project has
no mechanical check against. Writing this now, with zero real candidates in hand, is the whole
point.

**What this document is not.** It does not open, scope, or authorize the first real-data ingestion
itself — that remains `TASK-057`/`TASK-037`/`TASK-038`'s to gate, on their own existing terms, all
of which stay untouched and unaffected by this document. It does not touch `TASK-057`'s pause, and
recording it must not be read, cited, or later mistaken as progress toward `ADR-063`'s reopening
condition for that task. It changes no code, mechanism, gate, or threshold in
`packages/analytics/src/policy_analytics/validation/` or `docs/analytics/validation-contract.md`.
It is a founder-level judgment about what evidence, once produced, would be defensible to act on or
show a stakeholder — the same kind of call `decision-gate.md` made, applied to a setting where the
usual metrics cannot be computed at all.

## Why this document cannot have `decision-gate.md`'s "Fixed denominators" section

`decision-gate.md` fixed exact counts before scoring — 9 patterns, 7 scoreable, 5 traps, K=10 — read
once, in restricted form, from a file whose contents were counts only, not directions or effect
sizes, so the pre-registration could not be reverse-shaped to the answer. **No equivalent file
exists, or can exist, for a real customer dataset**, because there is no injected ground truth to
count. That absence is not an oversight this document works around — it is the entire reason a
different kind of gate is needed. In place of numeric denominators, this document fixes four things
that do not require a hidden answer key to apply: a review *process* (§1), a *bar* stated in this
project's own evidence vocabulary plus real-data-specific checks (§2), *language* discipline for
whatever evidence grade is actually reached (§3), and an explicit *kill* definition and response
(§4). Where `decision-gate.md` asks "did the mechanism recover the pattern we hid," this document
asks "would a person who actually knows this business, shown this candidate and everything the
gates could and could not check, say it holds up" — a falsifiability-by-domain-knowledge standard,
not a confirmation standard, in the same spirit as `docs/analytics/validation-contract.md` §10's own
acceptance test: "judged by whether it rejects things that deserve rejection," not by whether it
produces findings.

## Scope

Applies to the first completed real (non-synthetic) customer dataset discovery run, whenever
`TASK-057`/`TASK-037`/`TASK-038` eventually permit one, and to every real-data run after it until
this document is revised by a later, dated `FOUNDER_STRATEGY` append. It governs what may be
presented to any stakeholder outside the reviewing loop defined in §1 — a customer contact, an
investor, or company leadership acting on the result — and separately governs what counts as
internal-only diagnostic output. It does not govern synthetic-benchmark runs, which stay under
`docs/benchmark/decision-gate.md` unchanged.

---

## 1. Plausibility-review protocol

No mechanical check in this project — not `TASK-028`'s recall scoring, not any validation gate —
can confirm a real candidate is a true finding, because none can compare it against a known answer.
The substitute is a two-reviewer human protocol, both reviewers required, before any candidate
reaches a stakeholder outside the reviewing loop.

**Reviewer 1 — Statistics (internal, methodology reviewer).** Same role that owns evidence grading
today (`agents/STATISTICS.md`). Checks, specifically:

- the evidence level and readiness the gates actually assigned, and whether every gate that ran had
  enough real data to run meaningfully (a `G06` adjustment set that collapsed to zero covariates for
  lack of joint sample support is a materially weaker check than the same gate running with a full
  set — the gate still "passed," but what it verified shrank; this must be stated, not left implicit
  in a pass/fail flag);
- the actually-available sample size and cluster count in the real data, not any manifest-declared
  or synthetic-inherited figure — see §2 for the floor this feeds;
- whether `docs/analytics/validation-contract.md` §11's disclosed limitations (rare-pattern
  invisibility, `G06`'s non-exhaustive adjustment set, pilot-calibrated materiality thresholds) apply
  with more or less force on this dataset's actual shape than they did on the synthetic benchmark's;
- whether the candidate's robustness (`G12`) and stability profile is the kind that would survive a
  second independent slice of the same real data, to the extent one exists to check against.

**Reviewer 2 — a named domain reviewer with real, current operational knowledge of the specific
business the dataset came from.** This project has no internal role that substitutes for this — it
is deliberately not `STATISTICS`, `ML_DISCOVERY`, or `FOUNDER_STRATEGY` wearing a second hat, because
none of those roles have ever operated the business being analyzed. In practice this will typically
be a contact on the customer/data-provider side, secured through whatever approved engagement
produced the dataset — a process this document does not scope, open, or authorize (that is
`TASK-037`/`TASK-038`/`TASK-057`'s to govern). This document does not require the reviewer hold any
particular title; it requires they know how the business actually runs well enough to recognize an
operationally mundane effect, a known process quirk, or an obviously wrong number for that business.
**If no such reviewer is available at the point a finding would otherwise go to a stakeholder, the
finding is held internal-only until one is secured — never shown externally without this step.**

The domain reviewer checks, concretely, on every candidate presented to them:

1. **Effect direction plausibility.** Does the direction match what someone who runs this business
   would expect? If it is surprising, is there a known, nameable operational reason (a recent
   process change, a known problem supplier, a specific known-bad channel) a domain expert — but not
   the algorithm — would recognize? A surprising-but-explainable direction is not automatically
   disqualifying; a surprising-and-unexplainable one is a reason to hold, not surface.
2. **Population/exposure size defensibility.** Does the affected population size make business
   sense for this data — a plausible real segment of their operation — or does it look like a data
   artifact (a near-duplicate export, a test-account cluster, a migration boundary) that a person who
   knows the data's provenance would recognize on sight but no statistical gate is positioned to
   catch?
3. **Known confounding pattern for this data shape.** Is there a business-process reason two
   variables move together that `G06`'s automatically-selected adjustment set would not know to
   include — the real-data analog of `T01`–`T05`? The synthetic benchmark's trap catalog existed
   because the generator's confounding was knowable by construction; no equivalent enumerated catalog
   exists for an unfamiliar real schema, and the domain reviewer is the only check positioned to spot
   a trap shape nobody pre-registered. Ask directly: "does your team assign, route, or select on
   anything close to this candidate's condition, for a reason unrelated to the outcome we're
   measuring?"
4. **Data-quality artifact plausibility.** Could this be a duplicate-record, unit-mismatch,
   encoding, or schema-migration artifact rather than a real behavioral pattern? Synthetic data
   structurally cannot produce this failure mode — every synthetic domain ships a clean,
   already-reviewed manifest (`ADR-066`, reasoning §1) — so this check has no precedent run anywhere
   else in this project and must not be assumed already covered by the statistical gates.

**Standard applied.** Not "prove this is true" — impossible without ground truth, and not the
standard `decision-gate.md` itself applied even where ground truth existed (that document also
graded whether the mechanism *rejected what deserved rejection*, not merely whether it found
patterns). The standard here is: given the finding, its direction, its size, and the adjustment set
actually applied, does a person who knows this business fail to immediately recognize it as wrong,
mundane, or artifactual? This is a falsifiability check, not a confirmation exercise, and it can
only lower confidence in a candidate, never raise it above what the statistical gates themselves
support — domain plausibility review is a filter, not a substitute source of evidence, and never
promotes a finding to a higher evidence level than `packages/analytics/src/policy_analytics/
validation/` assigned it.

**Sign-off.** Both reviewers must sign off in writing, dated, against the specific candidate, in
the run's own written record, before `FOUNDER_STRATEGY` may show it to any stakeholder outside the
reviewing loop. `FOUNDER_STRATEGY` remains the final approver for any external presentation
regardless of sign-off — mirroring `decision-gate.md`'s own ownership of the go/no-go call. A
candidate with one sign-off and one refusal, disagreement, or non-response does not meet the bar
(§2) and must be held internal-only, recorded explicitly as "reviewed, not cleared" rather than
silently dropped or silently resubmitted for a different answer.

---

## 2. Minimum bar: defensible finding worth surfacing vs. suppress / hold internal-only

Expressed in this project's own evidence-level vocabulary
(`packages/analytics/src/policy_analytics/validation/contract.py`,
`docs/analytics/validation-contract.md` §6), plus the real-data-specific checks synthetic grading
had no need for because every synthetic domain ships a clean manifest with a known confounding
structure by construction.

**A candidate is worth surfacing to a stakeholder only if all of the following hold:**

1. **Evidence level ≥ 3, `adjusted_observational_association`.** This is already this product's own
   disclosed ceiling for historical, non-experimental data (`validation-contract.md` §1: "historical
   booking data can support at most `adjusted_observational_association`"). A level 1
   (`descriptive_observation`) or level 2 (`predictive_association`) candidate is discovery signal
   only — useful for `STATISTICS`/`ML_DISCOVERY` to iterate on, never a standalone stakeholder-facing
   finding on a first real run, where there is no ground truth to catch an unadjusted confound that a
   human reviewer also missed.
2. **Actually-available sample size and power, computed fresh against this dataset's own realized
   outcome variance — not inherited from the synthetic benchmark's calibration.**
   `validation-contract.md` §11 already discloses that its numeric thresholds are "pilot defaults
   calibrated to a 10k-booking, 24-month benchmark... placeholders until a real customer's economics
   are known." A first real run must not silently reuse those placeholders as if they were validated
   for this dataset. `G03`'s underlying method (minimum detectable effect at 80% power against the
   materiality threshold, not a flat headcount) must be re-run against the real data's own outcome
   variance before any candidate from it is treated as adequately powered. This is `STATISTICS`'
   implementation call, not fixed numerically here — what is fixed here is that skipping this
   re-derivation and reusing synthetic-calibrated floors unchanged disqualifies a finding from being
   surfaced.
3. **Both plausibility reviewers (§1) have signed off, in writing, on this specific candidate.** A
   single sign-off, a disagreement, or a non-response does not meet the bar. Minimum consensus is
   both, not one — there is no majority-of-one on a two-reviewer panel.
4. **Every confounder `G06` could not rule out is disclosed by name, not glossed.** Every finding
   shown to a stakeholder must carry an explicit, plain-language statement of exactly which
   variables `G06` adjusted for on this candidate (`adjustment_columns_used`), plus an explicit
   acknowledgment that no enumerated trap catalog equivalent to `T01`–`T05` exists for this
   unfamiliar real schema, so residual confounding beyond the stated adjustment set cannot be ruled
   out. This disclosure is mandatory precisely because the synthetic benchmark's trap catalog gave a
   false sense that "5/5 traps rejected" generalizes to unknown data — it does not, by
   `ADR-066`'s own reasoning (confounding on real data is "genuinely unmeasured... as opposed to a
   synthetic generator's, which is knowable by construction").
5. **Economic materiality (`validation-contract.md` §8) computed against the real dataset's own
   outcome variance**, not synthetic-calibrated `min_material_annual_impact` /
   `min_material_outcome_share` values inherited unchanged, for the same reason as item 2.
6. **No trap-shaped resemblance flagged and unresolved.** If the domain reviewer identifies a
   candidate as resembling a known operational routing/assignment/selection process (§1 item 3) and
   that resemblance is not resolved — either shown not to explain the effect, or the candidate
   re-specified to exclude it — the candidate does not meet the bar regardless of what the
   statistical gates alone concluded.

**Anything failing any one of these six is suppressed or held internal-only** — recorded in the
run's own written record for `STATISTICS`/`ML_DISCOVERY`/`ARCHITECT` diagnostic use, never shown to
a stakeholder outside the reviewing loop. Internal-only is not the same as killed (§4) — a held
finding can still inform engineering diagnosis; it is simply not presented externally until it
clears the bar above or the bar's judgment is revisited by a later dated `FOUNDER_STRATEGY` append.

---

## 3. Claim-capping language

`docs/analytics/validation-contract.md` §6's `LANGUAGE_RULES` already fix the strongest permitted
wording per evidence level and forbid causal verbs at levels 1–3 in "API responses, UI text,
reports, and investor material alike." That discipline is not weakened here — it is extended with
one additional, real-data-specific requirement: **every stakeholder-facing statement of a first
real-run finding must also disclose that the finding was not, and cannot be, benchmarked against a
known ground truth**, because none exists for real data. Quoting the synthetic benchmark's own
numbers (90% Top-10 precision, 45.2% economic-weighted recall, 5/5 trap rejection, or any other
number from `docs/benchmark/decision-gate.md`'s post-benchmark comparison log) as if they describe
this real finding's own reliability is explicitly forbidden — those numbers describe the synthetic
benchmark and only the synthetic benchmark.

**Example language, by evidence level actually reached** (the contract's own `permitted_claim`
strings, extended with the required real-data disclosure clause):

- **Level 2, `predictive_association`:**
  > "In your historical data, [X] is associated with [outcome Y], and this holds when tested on a
  > held-out later period. We have not adjusted for other factors that might explain it, and we have
  > not been able to check this against a known correct answer, because none exists for your data.
  > This is a candidate worth your team's attention to investigate, not a proven cause."
  (Per §2, a level-2 finding does not meet the "worth surfacing" bar on its own for a first real run
  — this wording is provided for the internal record and for the narrow case where `FOUNDER_STRATEGY`
  explicitly decides, in writing, to disclose a sub-bar finding as an explicitly-labeled diagnostic
  observation rather than a finding, per §4's near-empty-result framing.)
- **Level 3, `adjusted_observational_association` (the minimum level eligible to be surfaced):**
  > "In your historical data, [X] remains associated with [outcome Y] even after adjusting for
  > [name the variables `G06` actually adjusted for]. Two people who know your business — one from
  > our team, one from yours — reviewed this finding and did not find an obvious alternative
  > explanation, but we have not run an experiment, and confounding from something we did not measure
  > or adjust for is still possible. Unlike our benchmark testing, we have no way to mechanically
  > confirm this isn't an artifact of a pattern specific to your business that our adjustment didn't
  > include — this is our best available check, not a guarantee. This is a defensible finding worth
  > your team's attention, not a proven cause-and-effect claim."
- **Any level, forbidden framing (never used regardless of level reached):** "our system found," "we
  validated," or "proven" used without the qualifying clause above; any citation of a synthetic
  benchmark metric as evidence for this finding's reliability; any causal verb (*causes, drives,
  leads to, reduces, increases*) below level 4, exactly as the contract already forbids.

No claim to a stakeholder may exceed, in strength or in confidence framing, the evidence level and
readiness tier the gates actually assigned — this document adds disclosure obligations on top of
that ceiling, it never raises it.

---

## 4. Kill result — explicit, not just the success path

A "kill" result is one the company must not act on or present to a stakeholder as a finding, stated
in two distinct shapes, because they call for different responses.

### Kill-type A — near-empty or empty defensible result

**What it looks like:** zero, or fewer than some small number, of candidates clear the full §2 bar
on this real dataset. This is a *legitimate, disclosable outcome*, not a failure to hide.
`ADR-066`'s determination on `TASK-072` already named this as the honestly-expected result for any
non-travel first dataset, given the disclosed non-travel track record (`b2b_sales` and `ecommerce`
both at 0.0% economic-weighted recall across all four tested synthetic arms) — this document commits
in advance to treating that outcome, if it recurs on real data, exactly the way this project's
culture treats every other disclosed negative result: as real information, reported plainly, not
minimized and not treated as an embarrassment requiring spin.

**What happens next, named explicitly, in order:**

1. **Diagnose before responding.** `STATISTICS`/`ML_DISCOVERY` determine whether the near-empty
   result traces to a demonstrable, fixable real-data-pipeline defect — a `DECISION_TIME`
   classification error that wrongly excluded a real predictive column, a `G06` adjustment set that
   collapsed to near-nothing from low real sample size, outcome variance far outside what the
   synthetic-calibrated materiality thresholds assumed — or whether the mechanism ran correctly and
   this business's real data simply does not contain a pattern large and clean enough to clear the
   bar. This mirrors `decision-gate.md`'s own FAILED-action discipline: diagnose the specific cause
   before deciding how to respond, and a single run does not by itself justify concluding the
   discovery mechanism doesn't work on real data.
2. **If a fixable defect is found:** fix it and rerun once against the same dataset — the same
   single-remediation discipline `decision-gate.md` applies to a FAILED synthetic run.
3. **If no fixable defect is found — a genuine, diagnosed absence of a clearable pattern in this
   business's real data:** this is reported to `FOUNDER_STRATEGY` as a legitimate, disclosed
   outcome, written up honestly (never framed to a stakeholder as "your data is clean" or any other
   euphemism that obscures a null result). What happens after that — try a second real dataset, pause
   real-data work and return to synthetic iteration, or something else — is **not pre-committed by
   this document**, because the right choice depends on facts not yet knowable (which dataset, which
   vertical, how the diagnosis reads against the existing travel/non-travel evidence pattern) and
   must be a new, dated `FOUNDER_STRATEGY` decision made at that time, citing this document and the
   specific diagnosis. What **is** pre-committed here: a near-empty result on one real dataset will
   not, on its own, be treated as proof the discovery mechanism doesn't work — the same two-strikes-
   before-concluding discipline `decision-gate.md` applies to changing the core discovery approach
   applies here too, and it will not be silently used as an argument for or against `TASK-057`'s
   reopening, which stays governed on `ADR-063`'s own separate terms regardless of this document.

### Kill-type B — plausibility-review or process breakdown

**What it looks like:** either (a) the domain reviewer (§1) flags findings as implausible or
artifact-shaped across the board — a systematic pattern, not an isolated disagreement on one
candidate — or (b) a candidate the domain reviewer explicitly flagged as resembling a known
confound or data artifact is shown to a stakeholder anyway, meaning the review protocol itself was
bypassed, overridden, or failed to run before external presentation. This is not a result about the
business's data at all — it is evidence this document's own process broke down, and it is treated
with the same weight `decision-gate.md` gives a hard disqualifier: it overrides whatever any
individual candidate's own gate outcomes said.

**What happens next, named explicitly:**

1. Any pending or scheduled stakeholder presentation of real-run findings is halted immediately.
2. A mandatory joint review convenes — `FOUNDER_STRATEGY`, `ARCHITECT`, `STATISTICS` — before any
   further real-data work of any kind continues, mirroring `decision-gate.md`'s own "mandatory
   review... before any further synthetic iteration or real-customer work proceeds" convocation.
3. The outcome is recorded as a new `DECISIONS.md` entry regardless of what it concludes, and this
   document is appended-to (never rewritten) with whatever correction the review determines is
   needed to the protocol in §1 or the bar in §2.
4. This is a **process fix**, explicitly not a dataset-swap or a return-to-synthetic response — the
   named "something else" response the scope in `TASK-074` asked this document to consider. Trying a
   different real dataset without first fixing what let an unreviewed or reviewer-flagged candidate
   reach presentation would repeat the same failure on the next dataset.

---

## Post-run review log

*(Append-only. Nothing recorded here until a first real dataset run actually completes and is
reviewed under §§1–2. This section exists in advance, empty, exactly as `decision-gate.md`'s
"Post-benchmark comparison" section did before `TASK-028` ever ran.)*
