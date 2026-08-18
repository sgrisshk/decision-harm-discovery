# Customer Review Workflow — UX Specification

**Owner:** PRODUCT
**Task:** TASK-036 ("Customer review workflow")
**Depends on (implementation):** `TASK-035` (finding feedback model, `READY`, semantic contract frozen — `docs/product/finding-feedback-contract.md`) and, separately, `TASK-053` (basic authentication, `READY`, not `DONE`) for attributing *who* captured each reaction.
**Status:** UX specification only. Not implemented. Remains correctly `BLOCKED` on `TASK-035` per `TASKS.md`; written now so it's ready the moment that gate clears, the same pattern used throughout this product's screens.

## What this document is, and what already exists

Two documents already answer adjacent questions and are not repeated here:

- `docs/customer/findings-review-protocol.md` (Customer Discovery) — the **interview methodology**: how a human reviewer structures the conversation with a real customer, what to ask, how to classify strong vs. weak evidence, what's out of scope for the session.
- `docs/product/finding-feedback-contract.md` (Product, frozen v0) — **what gets stored** per finding: the novelty/actionability axes, the `WRONG`/`INTERESTING` qualifier tags, and every additional field (comment, certainty, intended action, commitment strength, owners, follow-up date).

This document is the missing third piece: the **actual product screen flow** that lets whoever is running a session — sitting with the customer, or filling it in immediately after — walk through Findings one at a time and turn the interview protocol's questions into the feedback contract's stored fields. `TASK-027`'s detail screen already reserves the UI slot this fills: a currently-disabled `FeedbackSlot` component (`apps/web/app/(app)/findings/[id]/page.tsx`, `findingDetail-feedback` class) showing static, non-interactive reaction chips ("Feedback capture coming soon").

## 1. Entry point and queue

- A review session starts from the findings list (`docs/product/findings-list-screen.md`) via a "Start review session" action, or resumes an in-progress one.
- **Queue contents:** only `FindingLifecycleStatus.ACTIVE` findings — same rule as the list screen's own default visibility (`docs/product/findings-list-screen.md` "Which findings appear at all"). A `SUPERSEDED`/`WITHDRAWN` finding is never queued for a fresh review.
- **Default order:** the same default sort the findings list already uses — descending by `impact.historical_impact.ci_low` (`docs/product/findings-list-screen.md` "Sorting and filtering") — so the highest-confidence, largest-exposure findings are reviewed first. Reusing the existing sort avoids inventing a second ranking concept for the same data.
- **Session identity:** each session needs a `review_session` reference (company, date, interviewer) to key feedback records against, per `docs/product/finding-feedback-contract.md` §4/§5. A formal `review_session` persistence object does not exist yet — flagged as open in `HANDOFF-031` and re-flagged in the implementation handoff below (§9), not invented here.

## 2. One finding at a time

Per finding in the queue, the screen shows two halves:

**Top half — the finding itself**, reusing the detail screen's core content, not a re-summarized version of it: plain-language title/summary, evidence pill, money at stake, alternative explanations checked. The review protocol's own session structure ("walk the customer through: what was found → the affected population → the raw effect → what current policy says") maps directly onto sections already defined in `docs/product/finding-detail-screen.md` — this screen does not redefine that content, only re-renders it inline instead of requiring a separate page visit.

**Bottom half — the capture form**, replacing the current disabled `FeedbackSlot` placeholder with a real form matching `docs/product/finding-feedback-contract.md` exactly:

| Contract field | Form element |
|---|---|
| `novelty` | Two-option single-select: "Known already" / "New to them" |
| `actionability` | Two-option single-select: "Actionable" / "Not actionable" |
| `tags` | Two independent toggles: "Doesn't look right" (`WRONG`), "Interesting" (`INTERESTING`) — not mutually exclusive with each other or with novelty/actionability, per the contract's §2 structure |
| `customer_comment` | Free text. Becomes **required**, with inline validation, the moment "Doesn't look right" is toggled on — matches the contract's §3 rule 1 exactly; the form must not allow advancing past a `WRONG` tag with an empty comment. |
| `customer_certainty` | Optional three-way selector (Low/Medium/High), labeled in the UI as the customer's own gut sense — **never** placed near, or styled like, any statistical confidence/interval element elsewhere on the page, per the contract's explicit "never named confidence" rule |
| `intended_action` | Optional free text |
| `commitment_strength` | Optional single-select: "Said they'd change a specific rule" / "Said they'd look into it" / not set — mirrors the review protocol's own "distinguish a stated commitment from a stated intention" language, not a UI-invented rewording |
| `customer_owner`, `internal_follow_up_owner` | Optional free text, two separate fields, not merged |
| `follow_up_date` | Optional date picker, only surfaced (not hidden, just visually secondary) when `commitment_strength` is set or `actionability = ACTIONABLE` — matches the contract's "only meaningful when there's a next step" rule |

No field on this form is required except the comment-on-`WRONG` rule above — matching the contract's own nullability (§2.1/§2.2: novelty and actionability are themselves optional).

## 3. Advancing through the queue

- **"Save and next"** — commits a feedback record (even a partial one, per §2's nullability) and advances. A record is only created if **at least one field was actually set** — advancing past a finding with the entire form untouched does not create an empty, meaningless row.
- **"Skip"** — explicitly distinct from the above: advances without creating any feedback record at all. The distinction matters for later interpretation: "no record" (skipped) must never be conflated with "reviewed, nothing to add" (a record exists but every field is at its default) — the UI enforces this by only ever writing a record when there's real content.
- **Back** — returns to the previous finding in the queue; per `docs/product/finding-feedback-contract.md` §5 (append-only), going back and changing an answer does **not** edit the record just created — it creates an additional new record for the same `(finding_id, review_session)` pair. The interview history is itself evidence; the UI must not present "back" as silently correcting the prior answer.
- **Progress indicator:** "Finding 3 of 6," scoped to this session's queue, not a global count.

## 4. Session completion

A minimal completion screen — counts only, no interpretation layered on top:

- Findings reviewed vs. skipped (session-scoped counts).
- Per the contract's own §6 product-learning use, session-level novelty/actionability rates *may* be computed later for `MILESTONE-M3`/`TASK-045` purposes, but **not on this screen** — this session-completion view shows raw counts of what was captured, not a rate, a verdict, or any language implying the session validated anything. That interpretation belongs to Founder Strategy/Customer Discovery reviewing across sessions, never to the workflow tool itself in the moment.
- No "results" framing, no congratulatory copy implying a good outcome — matches `docs/customer/findings-review-protocol.md`'s explicit caution against letting a session "become a sales pitch that overrides the recorded objections."

## 5. What must never be interpreted as validation

Restates `docs/product/finding-feedback-contract.md` §7 in this workflow's specific terms — this screen is the point of capture, and is exactly where the temptation to over-read a reaction is highest:

- Completing a review session is not evidence the product works — it's evidence a conversation happened and was recorded.
- A high `ACTIONABLE`/`NEW` count in one session is not repeatability evidence (`TASK-045` exists precisely because one session cannot answer that).
- `INTERESTING` toggled on, alone, must never be visually or numerically treated as equivalent to a `commitment_strength = STATED_COMMITMENT` answer — they are different fields captured by different form elements for exactly this reason.
- This workflow never writes to `evidence_level` or `policy_readiness` on any Finding — there is no code path from this form to those fields, by construction (same boundary as the underlying contract).

## 6. Edge cases

- **Empty queue** (no `ACTIVE` findings, or all already reviewed this session). `EmptyState`, not an error — "No findings left to review in this session."
- **A finding becomes `SUPERSEDED`/`WITHDRAWN` mid-session** (another process promotes a replacement while a review is in progress). The queue should not silently keep offering it; skip it with a visible note ("This finding was superseded during the session") rather than showing a stale row as if current.
- **Reviewer identity unknown** — see §9; until `TASK-053` exists, `captured_by` cannot be attributed. The workflow must not fabricate an identity or silently attribute to a shared/anonymous account; this is a hard implementation blocker, not a UI detail to work around.
- **Session interrupted (browser closed mid-queue).** Records already saved via "Save and next" persist (they're independent append-only rows, §3); resuming should return to the first not-yet-reviewed-or-skipped finding in the same queue order, not restart from the top.
- **A finding with no `WRONG`/`INTERESTING` tags and both axes null, saved anyway** — cannot happen per §3's "at least one field set" rule; the save action itself is disabled/no-ops on a fully empty form rather than producing a meaningless record.

## 7. Loading, empty, and error states

Reuse `apps/web/components/states/` — no new primitives, consistent with every other screen in this product:

- **Loading (queue fetching):** `LoadingState`, `label="Loading review session…"`.
- **Error (API failure saving a record or loading the queue):** `ErrorState`, standard `title`/`message`/`requestId`/`retryHref` pattern. A save failure must not silently advance to the next finding — the reviewer stays on the current one with the error shown and their entered-but-unsaved form content preserved, not discarded.
- **Empty (queue has nothing left):** `EmptyState`, per §6.

## 8. Non-goals

- Does not implement the `review_session` persistence object itself — referenced, not designed here (same deferral as `docs/product/finding-feedback-contract.md`).
- Does not implement cross-session analytics/rate dashboards (§4) — a Founder Strategy/Customer Discovery concern over time, not this screen.
- Does not replace or duplicate `docs/customer/findings-review-protocol.md`'s human conversation guidance — that protocol still governs how the reviewer talks to the customer; this document only governs what happens on screen while they do.
- Does not attempt to solve reviewer identity/auth — that is `TASK-053`, a separate security-sensitive design task.

## 9. Handoff to Architect — future implementation, not current

Recorded as a new handoff in `memory/HANDOFFS.md`. Two independent blockers, both must clear before real implementation: `TASK-035` itself (currently `READY`, not `DONE`) and `TASK-053` (basic auth, `READY`, not `DONE` — without it, `captured_by` cannot be attributed and this workflow degrades to an anonymous form, which `docs/product/finding-feedback-contract.md` §4 does not account for). Neither is unblocked by this document.
