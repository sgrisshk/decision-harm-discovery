# Policy Backtest Screen — UX Specification

**Owner:** PRODUCT
**Task:** TASK-034 ("Policy backtest UI")
**Depends on (implementation):** `TASK-032` (Policy backtest engine v0, Statistics) — **now `DONE`** (`docs/analytics/policy-backtest-contract.md`, `ADR-028`). `TASK-031` (Policy candidate generator, Architect) and `TASK-030` (this product's own domain model, `READY`, pending Architect's persistence-shape half of `HANDOFF-049`) are still not `DONE` — there is no real, persisted Policy Candidate yet for this screen to attach to in production, even though the underlying computation it displays already exists and is tested.
**Status:** UX specification only, revised (2026-08-18) against the real, frozen `BacktestResult` contract — not a proposal anymore.

## Why this document exists, and why it changed today

Written first against `docs/analytics/validation-contract.md` §9's methodology alone, before `TASK-032` existed. It has since been rewritten field-for-field against the real `BacktestResult` (`packages/analytics/src/policy_analytics/backtest/`, `docs/analytics/policy-backtest-contract.md`) once Statistics built and froze it the same day — the same discipline `docs/product/finding-product-contract.md` followed when `HANDOFF-046` corrected an assumption after the real economic-impact code landed. Every field name below is copied from that contract, not renamed or reworded.

`TASK-034`'s own stated dependency is only `TASK-032`, which is now `DONE` — so this screen's content is unblocked even though the practical end-to-end flow (create a candidate → run a backtest on it) still needs `TASK-031`/`TASK-030` to produce a real candidate to attach the "Run historical backtest" button to. Both facts are true at once: the spec is ready, and there is nothing real to point it at yet.

## Relationship to other authoritative documents

- `docs/analytics/policy-backtest-contract.md` (Statistics, `ADR-028`) — the authoritative, executable shape of everything this screen renders. Supersedes this document's earlier, conceptual framing of the same fields.
- `docs/analytics/validation-contract.md` §9 — the methodology the contract above implements; still the source of the five (now six, with operational cost) rules.
- `docs/product/policy-candidate-domain-model.md` §7 — reserves `backtest_result` on every Policy Candidate; now fillable field-for-field by the real `BacktestResult`.
- `docs/product/finding-product-contract.md` — the evidence-pill vocabulary this screen reuses verbatim.
- `memory/HANDOFFS.md#HANDOFF-050` — Statistics' confirmation that this screen's original design instincts (three distinct populations, both-sides enforcement, un-netted cost) were correct, plus two additions folded in below.

## 0. What this screen is not

Not a re-run of the Finding detail screen. The Finding answers "does this pattern exist in history." This screen answers "what did decisions matching this rule actually look like, in a window never used to find or grade the pattern" — `docs/analytics/policy-backtest-contract.md` §1's own framing, quoted rather than paraphrased: a backtest is **a mechanical replay**, not a causal estimate of intervention effect, not a second piece of evidence, and not an experiment. Showing the Finding's own `historical_impact` here as if it were the backtest result is exactly the mistake `docs/product/policy-candidate-domain-model.md` §4/§9 already warns against.

## 1. Eligibility — when this screen has anything to show

Two independent gates, both required:

1. **Candidate status.** Only a Policy Candidate already at `APPROVED_SHADOW` or later (`docs/product/policy-candidate-domain-model.md` §8) — backtesting a still-`DRAFT`/`UNDER_REVIEW` candidate would replay a rule nobody has reviewed or committed to trying.
2. **Outcome support.** `docs/analytics/policy-backtest-contract.md` §3: the bad/good outcome split is defined **only for `contribution_margin_eur`** in v1.0.0 (`BAD_OUTCOME_SUPPORTED_OUTCOME_ID`) — `run_backtest()` raises rather than guessing a threshold for any other outcome. Since `contribution_margin_eur` is this product's only primary outcome (`docs/analytics/outcome-contract.md`), this is not a live restriction for any real Finding today, but it is a real, disclosed scope limit, not an oversight: if a future Finding is ever built on a secondary/mechanism outcome instead, this screen must show "Backtesting isn't available for this outcome yet" rather than attempt a silent or incorrect computation.

## 2. Triggering a run

A backtest run is a **job**, reusing the existing `AnalysisRun`-style `ResourceStatus` pattern (`pending`/`running`/`completed`/`failed`) — Architect's own question in `HANDOFF-050` (point 1) about this remains open, but Product's position is unchanged: this is a deterministic, versioned, reproducible computation over a fixed input, the same shape as every other job in this system, and does not need a new status vocabulary invented for it.

- **Action: "Run historical backtest."** Visible on any eligible (§1) candidate with no `completed` run yet, or whose most recent run used an older `BACKTEST_CONTRACT_VERSION` than the live one.
- **Optional input at trigger time: cost per review (EUR).** Per `docs/analytics/policy-backtest-contract.md` §5, `operational_cost_per_review_eur` is a caller-supplied constant, never invented by the engine — this screen is the caller, so it must expose this as an actual optional numeric field on the trigger action, not assume the engine fills it in. Leaving it blank is a fully valid, expected choice (see §4's `net_effect_is_cost_exclusive` handling), not a degraded state.
- Once triggered: `pending → running → completed/failed`, using the existing `LoadingState`/`ErrorState` primitives (`apps/web/components/states/`) — no new loading/error pattern.
- A `failed` run (e.g. a missing-value guard tripped, §6) shows `ErrorState` with the reported reason; no silent retry, no partial numbers.
- Re-running always creates a new, separate run record — never overwrites a prior one, matching `CandidatePattern`/`ValidationReport`'s immutability convention. Prior runs stay visible in a collapsed list, not deleted.

## 3. Page structure (once a `completed` run exists)

```
┌──────────────────────────────────────────────────────────────────┐
│ ← Back to policy candidate                                        │
│                                                                     │
│  H1  Historical backtest: <policy candidate title>                │
│      [Evidence pill]  Backtested against the future-holdout window│
│                                                                     │
├──────────────────────────────────────────────────────────────────┤
│ 1. THE RULE                                                       │
│    <trigger conditions, plain language, reused from the policy    │
│    candidate's own trigger — never re-derived here>               │
│    Action: <action_detail — human-authored>                       │
│                                                                     │
│ 2. WHAT IT WOULD HAVE TOUCHED                                     │
│    affected_decisions bookings in the future-holdout window would │
│    have matched the rule — a different count from the Finding's   │
│    own affected_records/exposed_records; never presented as the   │
│    same number                                                    │
│                                                                     │
│ 3. UPSIDE AND DOWNSIDE — BOTH, ALWAYS                             │
│    Avoided bad outcomes:      avoided_bad_outcomes bookings        │
│      ("bad" = <bad_outcome_definition>, stated plainly)            │
│    Suppressed good outcomes:  suppressed_good_outcomes bookings    │
│    Neither side is ever shown without the other — they always sum │
│    to affected_decisions                                          │
│                                                                     │
│ 4. BENEFIT                                                         │
│    <benefit.value ± interval>                                     │
│    "Raw, unadjusted — an upper bound, not a confounder-controlled  │
│    estimate." (shown because benefit_is_adjusted is always false) │
│                                                                     │
│ 5. OPERATIONAL COST                                                │
│    If supplied: <operational_cost.value>, "assumed at              │
│    €<operational_cost_per_review_eur>/review, not estimated from   │
│    data"                                                            │
│    If not supplied: "No cost assumption entered — net effect below│
│    is benefit only, not cost-netted." (net_effect_is_cost_exclusive)│
│                                                                     │
│ 6. NET EFFECT                                                      │
│    <net_effect.value ± interval>, or "No measurable net effect"    │
│    verbatim when no_measurable_net_effect is true — read this      │
│    field directly, never re-derive the zero-crossing client-side  │
│    <methodology_disclosure string, rendered verbatim from the      │
│    engine — not authored by this screen>                          │
│                                                                     │
│ 7. EVIDENCE (reused, not recomputed)                                │
│    <Evidence pill from the source Finding's evidence_snapshot>    │
│    "This backtest does not change the finding's evidence level."  │
│                                                                     │
│ 8. WHAT YOU CAN DO NEXT                                            │
│    Gated by no_measurable_net_effect / net_effect sign — see §7    │
└──────────────────────────────────────────────────────────────────┘
```

## 4. Field-to-copy mapping

Exact field names from `BacktestResult` (`docs/analytics/policy-backtest-contract.md`):

| Field | Meaning | Copy rule |
|---|---|---|
| `window` | Hard-constant `"future_holdout"` — never a caller choice | Always named explicitly on screen ("future-holdout window"), never omitted or implied |
| `affected_decisions` | Count matching the trigger in `future_holdout` | **A third, distinct population** from the Finding's `exposed_records` (development-only) and `affected_records` (full combined window) — confirmed real and intended by Statistics (`HANDOFF-050`). Its own explicit label, never reused from the Finding screen's population field |
| `avoided_bad_outcomes` / `suppressed_good_outcomes` | Both sides, always sum to `affected_decisions` (enforced in code, not just convention) | Always shown together — a `BacktestResult` populating only one cannot even be constructed, so the UI never needs a defensive check, only a rendering rule |
| `bad_outcome_definition` | What "bad" means for this outcome (`contribution_margin_eur < 0`, i.e. a booking that lost money outright) | Rendered plainly next to "avoided bad outcomes" so the count isn't opaque — this field exists specifically so the UI doesn't have to hardcode or guess the threshold's meaning |
| `benefit` (value + interval) | Raw, **unadjusted** future-holdout mean difference × `affected_decisions` | Always with `benefit_is_adjusted` |
| `benefit_is_adjusted` | Always `false` in v1.0.0 | Must be shown as a caveat next to `benefit` — "raw, not confounder-adjusted" — never silently dropped, since its absence would let the number read as more rigorous than it is |
| `operational_cost` (nullable) | `null` unless a `cost_per_review_eur` was supplied at trigger time (§2) | When `null`: no cost line implying "zero cost," instead an explicit "no cost assumption entered" statement |
| `operational_cost_per_review_eur` | The caller-supplied constant, echoed back | Shown alongside `operational_cost` so the assumption behind the number is visible, not hidden inside a computed total |
| `net_effect` (value + interval) | `benefit` minus `operational_cost` when supplied, else `benefit` alone | Always paired with `net_effect_is_cost_exclusive` |
| `net_effect_is_cost_exclusive` | Distinguishes a benefit-only figure from a cost-netted one | Must change the screen's own wording ("before operational cost" vs. a netted figure) — never leave the reader to infer which case applies from whether a cost line happens to be present |
| `no_measurable_net_effect` | Precomputed zero-crossing check | Read directly for the "no measurable net effect" display rule — never re-derive from the interval client-side, per Statistics' own explicit note in `HANDOFF-050` |
| `methodology_disclosure` | A fixed disclosure string from the engine itself | **Rendered verbatim** — this screen does not author its own "upper bound, not a forecast" sentence; the engine already provides the sanctioned wording, the same pattern as `permitted_language` on a Finding |
| Evidence pill | Source Finding's evidence level, from the candidate's frozen `evidence_snapshot` | Identical pill/wording to `docs/product/finding-detail-screen.md` |

## 5. Never shown without qualification

- `no_measurable_net_effect = true` shown as a positive number anywhere — forbidden; must read "no measurable net effect."
- `avoided_bad_outcomes` without `suppressed_good_outcomes` alongside — cannot actually occur (enforced in `BacktestResult.__post_init__`), but the UI must still never split them across different views/tabs that could be seen independently.
- `benefit` without its `benefit_is_adjusted = false` caveat visible in the same view.
- `net_effect` without stating whether it's `net_effect_is_cost_exclusive` — a reader must never be left to assume cost was netted in when it wasn't, or vice versa.
- `operational_cost` present without `operational_cost_per_review_eur` shown alongside it — the assumption behind the number must always be visible, not just its product.
- Any backtest number presented as though it upgrades the source Finding's `evidence_level` — a backtest changes candidate status (§7), never the Finding's own evidence grade.
- `window` mislabeled as, or silently defaulting to, the discovery window.
- The Finding's own pre-backtest exposure figure (`docs/product/policy-candidate-domain-model.md` §4) shown next to the real `net_effect` without clearly distinguishing which is which.

## 6. Edge cases

- **No run exists yet** (true for every real candidate today, since none exist). Not an error — see §8.
- **Outcome not supported** (§1.2). Distinct message from a generic error — "Backtesting isn't available for this outcome yet," not `ErrorState`'s failure framing, since nothing actually failed.
- **Run `failed`** — including the contract's own disclosed hard-failure cases: a missing value found among `future_holdout`'s affected records despite the outcome's `COMPLETE` missingness policy (§3 of the contract — treated as "dataset no longer matches its pinned identity," not silently skipped). `ErrorState`, no partial numbers, re-run always available.
- **`no_measurable_net_effect = true`.** A legitimate, expected outcome — the candidate does not advance (§7) but this is not styled as a failure state.
- **A stale run** (older `BACKTEST_CONTRACT_VERSION`). Same "graded under an earlier standard" treatment as a stale Finding.
- **Source Finding becomes `SUPERSEDED`/`WITHDRAWN` after a backtest already ran.** Per `docs/product/policy-candidate-domain-model.md` §6, the candidate is affected — this screen must surface that rather than keep presenting an orphaned result as current.
- **Multiple runs exist**, possibly with different `operational_cost_per_review_eur` assumptions. The most recent non-stale `completed` run is the headline; prior runs (with their own cost assumption, if any) stay in a collapsed list, never silently discarded or averaged together.
- **No cost assumption ever entered across any run.** Expected and valid — `net_effect_is_cost_exclusive = true` is not a degraded or incomplete state, just a different, equally legitimate one (benefit-only).

## 7. What you can do next — gated by `no_measurable_net_effect` and `net_effect`'s sign

| Result | Available actions |
|---|---|
| `no_measurable_net_effect = true` | "Keep in shadow" only — candidate stays `APPROVED_SHADOW`. |
| `no_measurable_net_effect = false`, `net_effect` negative | "Retire this candidate" — a rule that backtests net-negative should not be quietly left in shadow; retiring requires a reason (`docs/product/policy-candidate-domain-model.md` §8). |
| `no_measurable_net_effect = false`, `net_effect` positive | + "Propose for customer decision" — advances toward `APPROVED_FOR_CUSTOMER_DECISION`. Still only a proposal document for the customer's own decision — this screen never offers an "enforce" action, matching the domain model's absolute boundary. |

## 8. Loading, empty, and error states

Reuse `apps/web/components/states/` — no new primitives:

- **Loading (run in progress):** `LoadingState`, `label="Running historical backtest…"`.
- **Error (run failed, or API failure):** `ErrorState`, standard `title`/`message`/`requestId`/`retryHref` pattern.
- **Empty — no run exists yet.** `EmptyState` with the "Run historical backtest" action (§2) and copy that doesn't overclaim: **"No backtest has been run yet. This candidate's benefit is currently based on historical exposure only, not a forward-looking test."**
- **Outcome not supported (§6):** its own distinct `EmptyState` variant, not styled as an error.

## 9. Non-goals for this screen

- Does not implement backtest statistical methodology — displays what Statistics computes (`agents/PRODUCT.md`: "not owned: statistical confidence").
- Does not offer an "enforce this policy" action, at any result — this system never enforces (`docs/product/policy-candidate-domain-model.md` §5/§9, `PROJECT_CONTEXT.md` non-goals).
- Does not aggregate backtest results across multiple policy candidates into a portfolio view.
- Does not implement `TASK-033`'s synthetic-ground-truth validation — Statistics' internal check of the engine itself, never customer-facing.
- Does not compute or suggest a `cost_per_review_eur` value — that number, when entered, is always the user's own input, never a system default or estimate (`docs/analytics/policy-backtest-contract.md` §5; `ADR-004`).

## 10. Handoff to Architect — still deferred, largely de-risked

`HANDOFF-050` in `memory/HANDOFFS.md` already carries Statistics' confirmation that this screen's design assumptions match the real contract exactly. What remains open there is purely Architect's own job-status modeling question (point 1) — not a new handoff, an update to the existing one. `TASK-034` implementation stays correctly `BLOCKED`: the computation exists and is confirmed, but there is still no real, persisted Policy Candidate (`TASK-031`/`TASK-030`) to attach this screen to.
