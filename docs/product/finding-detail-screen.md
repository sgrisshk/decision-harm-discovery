# Finding Detail Screen — UX Specification

**Owner:** PRODUCT
**Task:** TASK-027 ("Finding detail screen" in `TASKS.md`; see naming-conflict note below)
**Depends on (implementation):** TASK-025 (Findings API completion) → TASK-024 (full finding persistence model)
**Status of this document:** UX specification only. Not implemented. Backend data required to render this screen does not exist yet (see "Data requirements" below).
**Companion document:** `docs/product/finding-product-contract.md` is the field-and-wording contract this screen renders — required/optional/qualified-only field lists, the exact permitted-language ladder, the finalized action matrix (§9), and the Finding lifecycle/title contract (§12). Where the two differ, the contract is authoritative. See also `docs/product/findings-list-screen.md` (`TASK-026`), the triage view that links into this one.

**No validated Finding has been produced yet** — `TASK-015` discovery is `DONE` (15 candidates persisted), but Statistics validation (`HANDOFF-016`) is still `Pending`, so `TASK-019`–`TASK-025` remain `BLOCKED`. This document, like `docs/product/finding-product-contract.md`, is written against the concrete persistence contract (`docs/architecture/finding-persistence-contract.md`, `apps/api/app/findings/contracts.py`) and never against `synthetic_data/evaluation/hidden_ground_truth.json` or any other hidden-truth artifact.

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
- **Readiness pill**: separate from evidence level, driven by `policy_readiness` (`NOT_READY` / `EXPERIMENT_ONLY` / `SHADOW_POLICY` / `HIGH_CONFIDENCE`). `OQ-003` is now resolved (`docs/analytics/validation-contract.md` §7) — this pill is no longer provisional. `HIGH_CONFIDENCE` is currently unreachable system-wide (no policy backtest exists) and must not be treated as an imminent state.
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

**Finalized in `docs/product/finding-product-contract.md` §9** (`OQ-003` is resolved). Actions are gated by `policy_readiness`, not evidence level directly — `policy_readiness` already encodes "what may the business do about it" (`docs/analytics/validation-contract.md` §7), so gating on evidence level separately, as this section originally proposed, was redundant. See the contract for the current table and the `NOT_READY`-must-distinguish-rejected-from-immaterial rule.

- A lightweight reaction capture (`Known already / New to us / Doesn't look right / Not actionable / Interesting / Actionable`) is teased on this screen as the entry point for TASK-035/TASK-036, which are downstream Product tasks blocked on this screen shipping. This spec does not fully design the feedback workflow — only reserves the UI slot — to keep TASK-027 scoped. The full semantic contract for what each reaction actually captures (dimensions, valid combinations, additional fields, what it must never be read as) is now formalized in `docs/product/finding-feedback-contract.md`.

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

## Lifecycle-status gating (supersedes the old `ResourceStatus`-based section)

Resolved by `docs/product/finding-product-contract.md` §12.1 (`HANDOFF-024`). A promoted Finding is never partial — `FindingPromotion` only creates one after validation has a non-null evidence level and impact is computed — so the old `pending`/`running`/`failed` gating this section previously described **cannot occur** on a real Finding row and has been removed. The job-oriented `ResourceStatus` enum still exists for `AnalysisRun`/`Dataset`, but a Finding's own status is `FindingLifecycleStatus`:

- `ACTIVE` → full detail screen as specified above.
- `SUPERSEDED` → the normal content is replaced by a prominent banner: "This finding has been superseded by a newer analysis," linking to `superseded_by_finding_id` when set. Reachable only by direct link (never listed, per `docs/product/findings-list-screen.md`).
- `WITHDRAWN` → same banner treatment, showing the required `withdrawal_reason` instead of a replacement link.
- Stale (graded under an older `validation_contract_version` than the live one) is not a status — it's computed at read time. When stale, show a small "graded under an earlier validation standard" note alongside the normal content; never hide it, never auto-upgrade the evidence level.

## Field-to-copy mapping

Consolidates the pill/wording rules already stated inline above into one table. Source fields are `ValidationMetadataPersistence`/`EconomicImpactPersistence`/the persisted `Finding` (`apps/api/app/findings/contracts.py`, `docs/architecture/finding-persistence-contract.md`).

| Field | Detail-screen element | Copy rule |
|---|---|---|
| `title` | H1 | Verbatim deterministic snapshot (`docs/product/finding-product-contract.md` §12.2) |
| `summary` | "What we found" paragraph | Verbatim deterministic snapshot, same template family as `title` |
| `pattern_definition` / `CandidatePattern.conditions` | Collapsed "view technical rule definition" | Raw, only behind disclosure |
| `validation.evidence_level` | Evidence pill | 5-way mapping: `descriptive_observation`→"Observed pattern", `predictive_association`→"Predicts outcome", `adjusted_observational_association`→"Holds after adjustment", `quasi_causal_evidence`→"Quasi-causal", `experimental_evidence`→"Experimentally confirmed" |
| `validation.permitted_language` | Evidence section subtext | Render this stored sentence **verbatim** — it is now a persisted field (server-selected from `LANGUAGE_RULES`), not something the client re-derives from the evidence level |
| `validation.policy_readiness` | Readiness pill | 4-way mapping, see `docs/product/finding-product-contract.md` §9 |
| `validation.raw_effect` | "Raw effect" | Value with "descriptive, unadjusted, no interval — not a validated estimate" directly beside it |
| `validation.adjusted_effect` | "Adjusted effect" | Value + `ci_low`/`ci_high`/`confidence_level`/`method`, always all four together; absent below `adjusted_observational_association` — show "not yet adjusted," not a blank |
| `validation.controlled_variables` + `validation.potential_confounders` | "Alternative explanations checked" list | Two source lists, one narrative: "adjusted for" vs. "considered and still possible" |
| `validation.temporal_stability` | Stability breakdown | Rendered as the summary string it is; not decomposed further in v0 (full per-segment table is Optional later, `docs/product/finding-product-contract.md` §2) |
| `validation.warnings` | Warnings & limitations | Verbatim list; "No caveats flagged" when empty |
| `validation.failure_modes` + `validation.recommended_validation` | "What could change" | Shown together, sourced directly, never invented |
| `impact.historical_impact` | "Money at stake" headline | Range; "exposure" label (see List spec's same rule) |
| `impact.annualized_impact` | Annualized line | Shown only when non-null (structurally tied to `annualization_justified=true` by the schema's own validator); otherwise "Not enough history to project forward" |
| `impact.outcome_name` / `impact.outcome_unit` | Outcome label | Rendered from data, never hardcoded |
| `status` (`FindingLifecycleStatus`) | Header banner (non-`ACTIVE` only) | See lifecycle-status gating above |
| lineage fields (`dataset_version`, `analysis_run_id`, `contract_version`, `generated_at`) | Provenance strip | Collapsed by default |

## Edge cases

- **Directly linking a `SUPERSEDED`/`WITHDRAWN` finding** — banner replaces content (see lifecycle-status gating).
- **Stale contract version** — informational note, content still renders in full.
- **Finding ID that doesn't exist / was never promoted** — standard 404 handling via `ErrorState` (see states below), not a blank page.
- **`adjusted_effect` absent** (evidence below `adjusted_observational_association`) — "not yet adjusted," never a missing/blank field.
- **`impact.annualized_impact` null** — "Not enough history to project forward," never a silently omitted line.
- **Impact interval crosses zero** — "no measurable economic effect," never a number with a footnote (`docs/product/finding-product-contract.md` §3).
- **`warnings` empty** — explicit "No caveats flagged," not an omitted section.
- **`controlled_variables`/`potential_confounders` both empty** (e.g. a `descriptive_observation`-level finding, pre-adjustment) — explicit "Not yet tested against alternative explanations," never an omitted section (existing rule, retained).
- **Very small `impact.affected_records`** near the `G03` power floor — visible qualifier regardless of evidence level.
- **Many `pattern_definition` conditions** — same truncation contract as the title template; the technical disclosure always shows the full untruncated list even when the title/summary truncate.

## Loading, empty, and error states

Reuse `apps/web/components/states/` — no new primitives:

- **Loading:** `LoadingState` with `label="Loading finding…"`. Implemented at `apps/web/app/(app)/findings/detail/` (`HANDOFF-029`) — moved from a `[id]` dynamic route to a `?id=` query param per ADR-032, when the app was converted to a GitHub Pages static export (no server, so an unbounded set of finding IDs can't be pre-rendered via `generateStaticParams`).
- **Error (finding not found, or API failure):** `ErrorState` with `title="Could not load this finding"`, `message`/`requestId` from `toErrorDisplay(error)`, `retryHref` pointing back to the same finding URL. A 404 (finding never existed or ID is wrong) and a genuine API/network failure both go through the same `ApiError`-based path already established in `apps/web/lib/api/errors.ts` — no special-cased "not found" page distinct from the standard error state, consistent with how `/datasets` and `/findings` already handle errors.
- **Empty:** not applicable to a single-item detail page — a detail screen either resolves to content (including the `SUPERSEDED`/`WITHDRAWN` banner variants, which are not "empty," just non-default) or resolves to the error state above. There is no zero-items case for a single ID lookup.

## Data requirements this spec implies for TASK-024 — status

Originally an open list handed to Architect (`HANDOFF-008`). Now substantially resolved:

- Plain-language pattern summary → resolved, `docs/product/finding-product-contract.md` §12.2 (`title`/`summary`, stored/versioned).
- Raw/adjusted effect with uncertainty → resolved, `ValidationMetadataPersistence.raw_effect`/`adjusted_effect`.
- Confounders/alternatives checked → resolved, `controlled_variables`/`potential_confounders`.
- Stability → resolved as a summary string (`temporal_stability`); full per-segment breakdown remains Optional later.
- Impact as a range + annualization-justified flag → resolved, `EconomicImpactPersistence`.
- Outcome name/unit as data → resolved, `EconomicImpactPersistence.outcome_name`/`outcome_unit`.
- Finding-lifecycle status → resolved, `docs/product/finding-product-contract.md` §12.1 (`HANDOFF-024`).

Remaining, non-blocking: feature `display_label` for readable titles (`HANDOFF-028`). The route itself (`HANDOFF-029`) is built, at `/findings/detail?id=` rather than `/findings/[id]` — see ADR-032.
