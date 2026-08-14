# Findings List Screen — UX Specification

**Owner:** PRODUCT
**Task:** TASK-026 ("Findings list screen")
**Depends on (implementation):** TASK-025 (Findings API completion) → TASK-024 (full finding persistence model)
**Status of this document:** UX specification only. Not implemented. `docs/product/finding-detail-screen.md` (`TASK-027`) existed first; this document fills the gap `TASKS.md` flagged: "`TASK-026` still needs an approved Product list-screen spec."
**Companion document:** `docs/product/finding-product-contract.md` is the field-and-wording contract both screens render. Where the two differ, the contract is authoritative.

## No validated Finding exists yet — and none of this is built from synthetic ground truth

`TASK-015` (discovery) is `DONE`: 15 candidates are persisted in `artifacts/discovery/task-015-candidates.json`. Statistics validation of those candidates (`HANDOFF-016`) is still `Pending`, so `TASK-019`–`TASK-025` remain `BLOCKED` and no row exists in a `findings` table anywhere. This document is written against the concrete persistence contract Architect has already prepared (`docs/architecture/finding-persistence-contract.md`, `apps/api/app/findings/contracts.py`: `CandidatePatternPersistence`, `ValidationMetadataPersistence`, `EconomicImpactPersistence`, `FindingPromotion`) and `docs/product/finding-product-contract.md` — never against `synthetic_data/evaluation/hidden_ground_truth.json` or any other hidden-truth artifact, and never against invented statistics. Every field named below already exists in that code; none is proposed here for the first time except pure UI/copy structure.

## Product framing

Per `agents/PRODUCT.md`, the product's core flow is Finding → Evidence → Economic impact → Intervention → Validation → Policy candidate. The list screen is the **triage/prioritization** step of that flow — it exists to help a business user decide *which* finding to open next, not to explain any one of them fully (that's the detail screen). It must never become a generic BI dashboard (`PROJECT_CONTEXT.md` market boundary): no charts, no vanity metric tiles, no aggregate numbers computed by summing across findings.

**Scope boundary vs. the detail screen:** the list shows only what's needed to triage — title, evidence, readiness, headline exposure, population, warning presence. Everything else (raw/adjusted effect breakdown, alternative explanations checked, full warnings text, provenance) lives only on the detail screen. Do not grow list rows into mini detail cards.

## Which findings appear at all

Only `FindingLifecycleStatus.ACTIVE` findings appear in the default list (`docs/product/finding-product-contract.md` §12.1). `SUPERSEDED` and `WITHDRAWN` findings are excluded — they are audit artifacts, reachable only by a direct link someone already has, never something a user browses to. A rejected candidate (`validation.evidence_level IS NULL`) is never a Finding at all (`FindingPromotion`'s own invariant) and therefore never a list-omission question — there is nothing to filter out.

**Materiality does not gate visibility.** A Finding whose `policy_readiness` is `NOT_READY` because it's immaterial (gate `G15`) is real, validated, and must still appear — hiding it would contradict `docs/product/finding-product-contract.md` §8 ("this is real, but too small to act on" must be sayable, not silently dropped). Only lifecycle status gates default visibility.

## Page structure

```
┌──────────────────────────────────────────────────────────────────┐
│  H1  Findings                                                     │
│      <n> validated findings                                       │
│                                                                    │
│  [ Sort: Exposure ▾ ]  [ Filter: Readiness ▾ ]  [ Filter: Evidence ▾ ] │
├──────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ <title, one line, business language>                       │  │
│  │ [Evidence pill]  [Readiness pill]        [⚠ N caveats]      │  │
│  │ <exposure range, framed>  ·  <n> bookings affected          │  │
│  │ Generated <date>                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ ... next row ...                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

No summary tiles above the list (no "Total exposure: €X" — forbidden by `docs/product/finding-product-contract.md` §3's ban on summing impact across findings without a deduplicated union-of-affected-records computation, which does not exist; a top-of-page KPI tile is exactly the mistake that rule exists to prevent). No chart, sparkline, or trend graphic — this is a ranked list, not a dashboard.

## Row information hierarchy (highest to lowest priority)

1. **Title** — the deterministic `title` snapshot (`docs/product/finding-product-contract.md` §12.2), one line, plain business language. Never the raw condition dict.
2. **Evidence pill** — identical mapping to the detail screen's header pill (`docs/product/finding-detail-screen.md`, same five-way `EvidenceLevel` → label table). Reusing the exact same pill/wording across both screens is required — a user must not learn two different vocabularies for the same concept.
3. **Readiness pill** — identical mapping to the detail screen (`policy_readiness` → `NOT_READY`/`EXPERIMENT_ONLY`/`SHADOW_POLICY`/`HIGH_CONFIDENCE`).
4. **Exposure figure** — `impact.historical_impact` as a range (`ci_low`–`ci_high`), with the same "exposure" vs. "savings" framing rule as the detail screen (in practice always "exposure" today, since nothing exceeds `adjusted_observational_association` on this dataset and no backtest exists). Must carry equal-or-greater visual weight given to the evidence/readiness pills next to it, per `docs/product/finding-product-contract.md` §7 — a large number must never outrank its qualifiers in a scanning list, if anything more important here than on the detail screen since a list is skimmed, not read.
5. **Population** — `impact.affected_records`, an absolute count ("N bookings"), never a bare percentage.
6. **Warning indicator** — a badge showing the count of `validation.warnings`, shown only when count > 0. Unlike the detail screen (which explicitly states "No caveats flagged" when empty, because it's a single-item deep read), the list omits the badge entirely when there are none — stating "0 caveats" on every row is noise at list density, whereas omission on a single detail page reads as unintentional.
7. **Small-sample qualifier** — a visible marker when the finding sits near the `G03` power floor (same rule as `docs/product/finding-product-contract.md` §3's last row), shown even though it technically passed.
8. **Generated/updated date** — lowest priority, small text, for recency/trust only.

Clicking/tapping anywhere on a row opens the detail screen (`/findings/{id}`, not yet implemented — see `HANDOFF-029`).

## Sorting and filtering

- **Default sort: descending by `impact.historical_impact.ci_low`** (the conservative lower bound of the validated impact interval, not the point estimate). This is a legitimate ranking because, unlike a raw discovery candidate, a promoted Finding's impact has already passed validation and materiality (`G15`) — sorting on it is not the "large effect, weak evidence" problem `docs/product/finding-product-contract.md` §7 warns about, which concerns unvalidated candidates, not Findings. Using the lower bound rather than the point value means a finding with a wide, uncertain interval doesn't jump ahead of a tighter, more certain one purely on a lucky midpoint — no new statistic, just an existing field used conservatively.
- **Alternate sorts (user-selectable):** `policy_readiness` (business users scanning for "what can I act on now"), evidence level, most recently generated.
- **Filters:** `policy_readiness`, `evidence_level`, warnings present/absent. Dataset filter only if/when multiple datasets exist — today there is exactly one, so this is deferred, not built speculatively (matches the repo's "do not overbuild before demand" posture).
- **Never:** a sort or filter that requires computing a new metric not already in `EconomicImpactPersistence`/`ValidationMetadataPersistence`. If a future sort idea needs a number that doesn't exist in the persisted schema, that is a handoff to Statistics/Architect, not something Product or Architect invents at the UI layer.

## Field-to-copy mapping

| Field (`FindingPromotion` / persisted `Finding`) | List element | Copy rule |
|---|---|---|
| `title` | Row heading | Verbatim; CSS ellipsis only at very narrow widths, never server-side truncation beyond the template's own limit (`docs/product/finding-product-contract.md` §12.2) |
| `validation.evidence_level` | Evidence pill | Same 5-way mapping as `docs/product/finding-detail-screen.md` header |
| `validation.policy_readiness` | Readiness pill | Same 4-way mapping as the detail screen |
| `impact.historical_impact` (`value`/`ci_low`/`ci_high`) | Exposure figure | Range, never a bare point; "exposure" label unless `evidence_level` ∈ {`quasi_causal_evidence`, `experimental_evidence`} **and** a positive backtest exists (currently never — `TASK-032` doesn't exist) |
| `impact.affected_records` | Population count | "`<n>` bookings" (unit name from the outcome contract's cohort, not hardcoded) |
| `validation.warnings` (length) | Warning badge | "`<N>` caveats", shown only if `N > 0` |
| `impact.materiality_pass` | (implicit via readiness pill) | Never shown as a separate bare boolean — always via the readiness pill, which already encodes it |
| `status` (lifecycle) | (gates default visibility only) | Not rendered as a field on `ACTIVE` rows — a status label would only ever read "Active," which is redundant when it's the only thing ever listed |
| `created_at` / `generated_at` | Meta text | "Generated `<date>`", low visual priority |

## Edge cases

- **Zero active findings.** Not an error — see Empty state below.
- **All findings are `NOT_READY` (immaterial).** Still listed in full (see "Which findings appear at all" above); do not filter them out by default just because none are currently actionable.
- **A finding's impact interval does not exclude zero.** Per `docs/product/finding-product-contract.md` §3, no number is shown as an effect in this case — the row's exposure figure reads "no measurable economic effect" instead of a range. Sort placement for such rows (since they have no usable `ci_low` to sort by) is an Architect implementation detail; the only fixed requirement is they must still appear, never be silently dropped from the list.
- **Small-sample finding.** Visible qualifier badge (see hierarchy item 7), still fully listed.
- **Many findings (pagination).** Not designed in detail here — page size and cursor-vs-offset are Architect's call (`HANDOFF-029`). Fixed requirement: sort order must stay stable across pages; a newly promoted Finding appearing mid-session must not reshuffle a page the user is already scrolled into.
- **A finding reached via a stale link while `SUPERSEDED`/`WITHDRAWN`.** Not a list concern — handled entirely on the detail screen (banner + replacement link), since these never appear in the list itself.
- **Very long title from a many-condition pattern.** The title template itself truncates with an explicit "and N more conditions" (`docs/product/finding-product-contract.md` §12.2) — the list never re-truncates a title that already fits the template's contract; if it still overflows a narrow viewport, CSS ellipsis only, not a second truncation with different rules.
- **Multiple datasets.** Deferred; default view spans all datasets until a second real dataset exists (matches `TASK-057`'s current `TODO` status — there is nothing to filter yet).

## Loading, empty, and error states

Reuse the existing real primitives in `apps/web/components/states/` — do not invent new ones:

- **Loading:** `LoadingState` with `label="Loading findings…"` — already implemented in `apps/web/app/(app)/findings/loading.tsx`; no change needed.
- **Error:** `ErrorState` with `title="Could not load findings"`, `message`/`requestId` from `toErrorDisplay(error)`, `retryHref="/findings"` — already implemented in `apps/web/app/(app)/findings/page.tsx`'s catch branch; no change needed to the error-handling *mechanism*, only to what's rendered once real data flows (this spec's row hierarchy above).
- **Empty (zero `ACTIVE` findings, request succeeded):** `EmptyState`. Update the existing copy from the current placeholder ("Validated findings will appear here once discovery and statistical validation have run on a dataset.") to reflect the real current pipeline stage without technical jargon: **"No validated findings yet. Discovered patterns are still going through statistical validation before they're shown here."** Distinct from the error state per `EmptyState`'s own contract — nothing failed, there is just nothing to show yet.

## Non-goals for this screen

- Not a generic BI/metrics dashboard — no charts, no top-of-page KPI tiles, no cross-finding aggregates.
- Does not implement search (not requested; add only against a demonstrated need, matching the repo's deferred-features posture).
- Does not implement the policy-candidate or backtest views (`TASK-030`–`TASK-034`, separate work).
- Does not implement customer feedback capture (`TASK-035`/`TASK-036`) — that lives on the detail screen's reserved slot, not the list.

## Data requirements — already satisfied

Unlike when the detail screen's spec was first written against a conceptual schema, essentially every field this list needs already exists in `docs/architecture/finding-persistence-contract.md`/`apps/api/app/findings/contracts.py`. The only genuinely new gaps this document surfaces:

1. Feature `display_label` for readable titles — `HANDOFF-028` (Data Engineer), non-blocking.
2. Pagination mechanism and zero-interval sort placement — `HANDOFF-029` (Architect), implementation detail, not a Product decision.

Implementation is handed off in `HANDOFF-029`.
