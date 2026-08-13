# Finding Detail Screen — UX Specification

**Owner:** PRODUCT
**Task:** TASK-027 ("Finding detail screen" in `TASKS.md`; see naming-conflict note below)
**Depends on (implementation):** TASK-025 (Findings API completion) → TASK-024 (full finding persistence model)
**Status of this document:** UX specification only. Not implemented. Backend data required to render this screen does not exist yet (see "Data requirements" below).
**Companion document:** `FINDING_PRODUCT_CONTRACT.md` is the field-and-wording contract this screen renders — required/optional/qualified-only field lists, the exact permitted-language ladder, and the finalized action matrix (§9, superseding this document's §7). Where the two differ, the contract is authoritative.

## Naming conflict with the request

The task that asked for this work referred to it as "TASK-026 — Finding Detail Screen." In `TASKS.md`, TASK-026 is **"Findings list screen"** and TASK-027 is **"Finding detail screen."** This specification covers the finding *detail* screen (single finding, full evidence view), so it is written against **TASK-027**. Reported here rather than silently resolved, per `engineering rules` conflict-reporting rule. If TASK-026 (the list screen) was actually intended, that is separate, smaller-scope work and should be requested explicitly.

## Why this document exists despite BLOCKED status

TASK-027 is `BLOCKED` on TASK-025, which is `BLOCKED` on TASK-024, which is `BLOCKED` on TASK-020/TASK-023. None of those exist yet — the current `Finding` API (`apps/api/app/api/schemas.py: FindingRead`) only exposes `title`, `pattern_definition`, `sample_size`, `evidence_level`, `status`, `warnings`. It has no raw/adjusted effect, uncertainty, impact, stability, or confounder-check fields.

Product's job here is UX specification, not implementation (`agents/PRODUCT.md`). Writing the spec now, ahead of the backend, lets Architect build TASK-024's data model against real UI requirements instead of guessing, and lets this screen ship as soon as TASK-025 unblocks instead of waiting for a second design pass. Nothing here should be built against fake/mock data as if it were real.

## Product framing

Per `agents/PRODUCT.md`, every finding must answer, in this order, in business language:

1. What happened?
2. Why care?
3. How much money may be involved?
4. How strong is the evidence?
5. Which alternatives were checked?
6. What could change?
7. What happens next?

The screen must never say "AI says this is true," never hide uncertainty, and never present association as causation (`ADR-005`). Evidence-level language in the UI must never exceed the assigned `EvidenceLevel`.

## Page structure

```
┌──────────────────────────────────────────────────────────────────┐
│ ← Back to findings                                                │
│                                                                    │
│  H1  <plain-language finding title>                               │
│      [Evidence pill]  [Readiness pill]  [⚠ N warnings]            │
│                                                                    │
├──────────────────────────────────────────────────────────────────┤
│ 1. WHAT WE FOUND                                                  │
│    <one-paragraph plain-language pattern description>             │
│    "When <condition>, <outcome> is <direction> than otherwise."   │
│    [ View technical rule definition ▸ ]  (collapsed by default)   │
│                                                                    │
│ 2. WHO THIS APPLIES TO                                            │
│    <N> of <total> bookings (X%)  ·  <date range covered>          │
│    Segment/scope description                                     │
│                                                                    │
│ 3. MONEY AT STAKE                                                 │
│    Historical impact:  <range, not point estimate>  (<outcome     │
│    metric name>, historical period only)                          │
│    Annualized estimate: <range> — shown only if the backend        │
│    marks annualization as justified; otherwise explicit note      │
│    "Not enough history to project forward."                       │
│    "This reflects observed history, not a guaranteed future       │
│    saving."                                                       │
│                                                                    │
│ 4. HOW STRONG IS THE EVIDENCE                                     │
│    Evidence ladder (5 steps, current step highlighted):           │
│    Descriptive → Predictive → Adjusted observational →            │
│    Quasi-causal → Experimental                                    │
│    Raw effect: <value>        Adjusted effect: <value ± range>    │
│    "Adjusted for: <confounders controlled for>"                   │
│    Stability: <holds across time / segments> with a visual        │
│    breakdown, not just a single word                              │
│                                                                    │
│ 5. ALTERNATIVE EXPLANATIONS CHECKED                                │
│    List of confounders/hypotheses tested → outcome per item       │
│    (ruled out / partially explains / inconclusive)                │
│    If none tested yet: explicit "Not yet tested against            │
│    alternative explanations" — never omit the section              │
│                                                                    │
│ 6. WARNINGS & LIMITATIONS                                         │
│    Verbatim backend warnings, unedited, unsoftened                │
│    "No caveats flagged" shown explicitly when the list is empty   │
│                                                                    │
│ 7. WHAT YOU CAN DO NEXT                                           │
│    Action set gated by evidence level (see matrix below)          │
│    Quick reaction capture (see TASK-035 note below)                │
│                                                                    │
├──────────────────────────────────────────────────────────────────┤
│ Provenance (collapsed strip): dataset id/version · analysis run   │
│ id · code version · generated <timestamp>                         │
└──────────────────────────────────────────────────────────────────┘
```

## Section-by-section rules

### Header

- Title is a plain-language sentence generated from the pattern, never a raw rule dump (e.g. "Bookings modified after payment lose margin more than others," not `payment_status == 'modified' AND ...`).
- **Evidence pill**: plain-language label mapped 1:1 from `EvidenceLevel`, never invented wording:
  - `descriptive_observation` → "Observed pattern"
  - `predictive_association` → "Predicts outcome"
  - `adjusted_observational_association` → "Holds after adjustment"
  - `quasi_causal_evidence` → "Quasi-causal"
  - `experimental_evidence` → "Experimentally confirmed"
- **Readiness pill**: separate from evidence level, driven by `policy_readiness` (`NOT_READY` / `EXPERIMENT_ONLY` / `SHADOW_POLICY` / `HIGH_CONFIDENCE`). `OQ-003` is now resolved (`docs/validation_contract.md` §7) — this pill is no longer provisional. `HIGH_CONFIDENCE` is currently unreachable system-wide (no policy backtest exists) and must not be treated as an imminent state.
- Warning count badge is always visible in the header if `warnings` is non-empty — never buried behind a click.

### 1. What we found

- One paragraph, plain business language, generated deterministically from `pattern_definition` (not generative model free text at render time beyond agreed templated phrasing — numeric truth stays in code per `ADR-004`).
- Raw `pattern_definition` (conditions/thresholds) available behind a collapsed "view technical rule definition" disclosure, for analysts/auditors, not the default reading path.

### 2. Who this applies to

- Absolute count **and** percentage of the analyzed population — never percentage alone (small-sample percentages are misleading).
- Time window the finding was computed over.
- If `sample_size` is small in absolute terms, this section carries a visible low-confidence marker regardless of evidence level — a below-threshold sample should never read as visually equivalent to a large one.

### 3. Money at stake

- Always a **range**, never a bare point estimate, whenever uncertainty exists.
- Outcome metric name is rendered from data, not hardcoded as "gross margin" — `OQ-002` (canonical economic outcome) is still open, and the screen must not assume its resolution.
- Annualized/projected figures are shown only if the backend explicitly marks the annualization as statistically justified (TASK-023 scope); otherwise the screen states plainly that projection isn't supported yet. No UI-side extrapolation.
- A standing disclaimer that historical impact is not a guaranteed future outcome sits directly under the number, not in fine print elsewhere.

### 4. How strong is the evidence

- Evidence ladder shows all 5 levels so the user understands where this finding sits relative to the strongest possible evidence — showing only the achieved level, in isolation, invites over-trust.
- Raw effect and adjusted effect are shown side by side so the user sees whether/how adjustment changed the picture, with a one-line explanation of which confounders were controlled for.
- Stability is shown as a breakdown (e.g., per time period / per segment), not a single "stable/unstable" word — a pattern that holds in aggregate but flips in one large segment is a materially different finding.
- Language here is hard-capped by `evidence_level`: no "causes," "proves," or "guarantees" below `experimental_evidence`.

### 5. Alternative explanations checked

- This directly answers "which alternatives were checked" and must never be skipped, collapsed away, or merged into "warnings." Confounders are Statistics' domain (TASK-021/TASK-022); Product's job is guaranteeing this evidence is always surfaced, legibly, per finding.
- Each checked alternative shows what was checked and the outcome: ruled out / partially explains the effect / inconclusive.
- If discovery/validation hasn't run confounder checks yet on this candidate, the section says so explicitly rather than disappearing — an empty section reads as "nothing to worry about," which is false.

### 6. Warnings & limitations

- Rendered verbatim from the backend `warnings` list. Product does not rewrite or soften these strings.
- Explicit "No caveats flagged" state when empty, so absence is a visible, deliberate statement rather than an accidental gap.

### 7. What you can do next — action matrix

**Finalized in `FINDING_PRODUCT_CONTRACT.md` §9** (`OQ-003` is resolved). Actions are gated by `policy_readiness`, not evidence level directly — `policy_readiness` already encodes "what may the business do about it" (`docs/validation_contract.md` §7), so gating on evidence level separately, as this section originally proposed, was redundant. See the contract for the current table and the `NOT_READY`-must-distinguish-rejected-from-immaterial rule.

- A lightweight reaction capture (`Known already / New to us / Doesn't look right / Not actionable / Interesting / Actionable`) is teased on this screen as the entry point for TASK-035/TASK-036, which are downstream Product tasks blocked on this screen shipping. This spec does not fully design the feedback workflow — only reserves the UI slot — to keep TASK-027 scoped.

### Provenance strip

- Collapsed by default, always available: dataset id/version, analysis run id, code/model version, generated timestamp. Answers "can this be traced and reproduced" (`ARCHITECTURE.md` traceability requirement) without cluttering the primary business narrative.

## Non-negotiable copy rules

- Never use "caused," "proves," or "guarantees" below `experimental_evidence`.
- Never show a percentage without its underlying count.
- Never show a point estimate where the backend provides a range — show the range.
- Never hide a non-empty `warnings` list behind extra navigation.
- Never omit the "alternative explanations checked" section, even when the answer is "not yet checked."

## Non-goals for this screen

- Not a generic BI/metrics dashboard (`PROJECT_CONTEXT.md` market boundary).
- Does not compute or restate statistical confidence — it displays what Statistics already produced (`agents/PRODUCT.md` "Not owned").
- Does not implement policy backtesting UI (TASK-034, separate task).
- Does not fully design the feedback workflow (TASK-035/036, separate tasks) — only reserves a UI slot.

## Run-status gating (uses existing `ResourceStatus`)

The current `ResourceStatus` enum (`pending/running/completed/failed/draft`) describes the underlying run/generation state, not the finding's evidence lifecycle — these are two different concepts and must not be conflated in the UI:

- `completed` → full detail screen as specified above.
- `pending` / `running` → "Still being analyzed" state, no partial numbers rendered.
- `failed` → explicit error state, no finding content rendered.
- `draft` → not shown to business users; internal-only state if it reaches the UI at all.

## Data requirements this spec implies for TASK-024 (handed off, not decided here)

To render this screen, the finding persistence model needs, beyond the current `FindingRead` skeleton:

- plain-language pattern summary (templated, not raw condition dict) or enough structure for the frontend to template it deterministically;
- raw effect and adjusted effect as separate values with uncertainty ranges;
- list of confounders/alternatives checked, each with an outcome label (ruled out / partially explains / inconclusive);
- stability broken down by segment/time period, not a single flag;
- estimated impact as a range, plus an explicit boolean/flag for whether annualization is statistically justified;
- outcome metric name/unit as data, not an assumed constant;
- a finding-lifecycle status distinct from `ResourceStatus` (candidate awaiting review / validated / rejected / superseded) is implied by "what happens next" but does not yet exist anywhere in the schema — flagged to Architect/Statistics rather than assumed here.

This list is the basis for `HANDOFF-008` in `memory/HANDOFFS.md`.
