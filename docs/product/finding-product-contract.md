# Finding Product Contract v0

**Owner:** PRODUCT
**Status:** v0.2 — content/field contract, not yet implemented. Amended: the persistence schema this contract targets moved from conceptual (`ValidationReport`) to concrete (`docs/architecture/finding-persistence-contract.md`, `apps/api/app/findings/contracts.py`); §12 added to resolve `HANDOFF-024`.
**Scope:** What information one persisted, validated Finding must carry so a business user can understand it. This is not a dashboard, not a policy candidate (TASK-030), and not a UI layout — it is the field-and-wording contract that `docs/product/finding-detail-screen.md` and `docs/product/findings-list-screen.md` (screen layouts) and `TASK-024` (persistence model) must all satisfy.

**No validated Finding has been produced yet.** `TASK-015` (discovery) is `DONE` — 15 candidates are persisted in `artifacts/discovery/task-015-candidates.json` — but Statistics validation of those candidates (`HANDOFF-016`) is still `Pending`, so `TASK-019`/`TASK-020`/`TASK-021`/`TASK-023`/`TASK-024`/`TASK-025` remain `BLOCKED`. Nothing in this document is, or is derived from, a real Finding row, and nothing here is, or is derived from, `synthetic_data/evaluation/hidden_ground_truth.json` or any other hidden-ground-truth artifact — this contract is built only from the discovery-candidate contract, the validation contract, and the persistence-preparation schemas, exactly the way a real Finding will be built.

## Relationship to other authoritative documents

This contract does not restate or invent statistical rules. It consumes them:

- `docs/analytics/validation-contract.md` (Statistics, `ADR-007`) — the only source of evidence-level requirements, gate definitions, permitted wording (`LANGUAGE_RULES`), and the policy-readiness matrix. Quoted here verbatim where needed; never re-derived.
- `docs/analytics/outcome-contract.md` (Statistics, `ADR-009`/`ADR-011`) — the only source of outcome meaning, direction, and unit for the synthetic benchmark.
- `docs/architecture/finding-persistence-contract.md` and `apps/api/app/findings/contracts.py` (Architect, `TASK-024` preparation) — the current authoritative, concrete shape: `CandidatePatternPersistence`, `ValidationMetadataPersistence`, `EconomicImpactPersistence`, `FindingPromotion`. Supersedes the looser `ValidationReport`-only framing this contract originally used; field names below are kept in sync with this code.
- `packages/analytics/src/policy_analytics/validation/contract.py` (`LANGUAGE_RULES`, `GateId`, `PolicyReadiness`) — same role as above, one layer down.
- `docs/product/finding-detail-screen.md` (Product, `TASK-027`) and `docs/product/findings-list-screen.md` (Product, `TASK-026`) — the two screen layouts that render these fields.
- `memory/HANDOFFS.md#HANDOFF-013` (Statistics → Product) — this document is Product's response to its first half (finalize the action matrix, §9). Its second half (real materiality threshold) is addressed in §11.
- `memory/HANDOFFS.md#HANDOFF-012` and `#HANDOFF-024` (Statistics/Architect → Product) — §12 is Product's answer to `HANDOFF-024`.

No statistical threshold in this document is invented. Every number that appears is either a fixed enum/gate identifier from the code above, or explicitly marked as Statistics-owned and not reproduced.

## 0. What "validated Finding" means in v0

One persisted, graded pattern: the output of applying `docs/analytics/validation-contract.md` (`TASK-019`/`TASK-020`/`TASK-021`) and the economic impact engine (`TASK-023`) to one `TASK-015` candidate. Not a raw discovery candidate (pre-validation), not a policy candidate (`TASK-030`, post-Finding), not a row in a ranked list (`TASK-026`). This contract covers exactly one Finding in isolation.

---

## 1. Required for MVP

A Finding cannot be shown to a business user without these. Grouped by the question each answers (`agents/PRODUCT.md` mission order).

### What happened / where

| Field | Meaning | Source |
|---|---|---|
| `finding_id`, `candidate_id`, `analysis_run_id` | Identity and traceability | `TASK-024` / `ValidationReport` |
| `dataset_version`, `outcome_definition_version`, `contract_version` | Which data, outcome contract, and validation contract graded this | `ValidationReport` |
| `generated_at` | When this grading ran | `TASK-024` |
| Plain-language pattern summary | One sentence, business language, deterministically templated from `pattern_definition` — never freeform generative model prose standing in as the fact (`ADR-004`) | New — templating logic owned jointly by Product (wording) and Architect (implementation) |
| `pattern_definition` | The technical rule (conditions/thresholds) | `ValidationReport`; shown collapsed, not the default reading path |

### Who this applies to

| Field | Meaning | Source |
|---|---|---|
| `exposed_records`, `comparison_records` | Absolute counts — a percentage is never shown without its count | `ValidationReport` |
| Eligible cohort window | The time window/eligibility rule the outcome contract defines | `docs/analytics/outcome-contract.md` §6, per outcome |
| `clustering_key` | Exists in the data model for audit purposes; not a headline UI element (e.g. "customer-level") | `ValidationReport` |

### Money at stake

Impact fields do not exist in code yet (`TASK-023` is `BLOCKED`). Listed here as required so `TASK-023`/`TASK-024` are scoped against real UI need, per `docs/analytics/validation-contract.md` §8:

| Field | Meaning | Display rule |
|---|---|---|
| `affected_records` (window) | Same population as `exposed_records`, restated for the impact section | — |
| `per_record_effect` (value + interval, in outcome's own unit) | Same shape as `EffectEstimate` | Always interval, never bare |
| `historical_impact` (value + interval) | `affected × effect`, interval propagated from the same bootstrap | Always interval, never bare |
| `outcome_name`, `outcome_unit` | Rendered from data (`docs/analytics/outcome-contract.md`), never hardcoded as "gross margin" or any fixed string — `OQ-002` (real-customer outcome) is still open | — |
| `materiality_pass` (bool, from gate `G15`) | Whether the impact clears Statistics' materiality threshold | Show the pass/fail; never show or imply the threshold *value* — that number is a placeholder (`min_material_annual_impact`, `OQ-004`) and is Statistics/Customer-Discovery owned |
| `annualization_justified` (bool) | Whether ≥12 months of stable-exposure coverage exists | Gates whether an annualized figure may appear at all — see §3 |
| Impact framing label (`exposure` vs `savings`) | Deterministic from evidence level + backtest existence, per `docs/analytics/validation-contract.md` §8 | Never authored per-finding; computed once, applied everywhere |

### How strong is the evidence

| Field | Meaning | Source |
|---|---|---|
| `evidence_level` | One of the five `EvidenceLevel` values | `ValidationReport` |
| `identification_design` | `OBSERVATIONAL` / `QUASI_EXPERIMENTAL` / `EXPERIMENTAL` — explains the ceiling on this finding | `ValidationReport` |
| `raw_effect` (`EffectEstimate`-shaped, but see §3 — no interval in practice at this stage) | The unadjusted, descriptive difference | `ValidationReport` |
| `adjusted_effect` (`EffectEstimate`: value, ci_low, ci_high, confidence_level, method, unit) | Required whenever `evidence_level` ≥ `adjusted_observational_association` — `ValidationReport` itself refuses construction without one at that level, so the UI can rely on this invariant | `ValidationReport` |
| `controlled_variables` | What was adjusted for | `ValidationReport` |
| `potential_confounders` | What remains a possible alternative explanation | `ValidationReport` |
| `robustness_tests` | What stability/sensitivity checks were run | `ValidationReport` |
| `temporal_stability` | Summary string of whether the effect holds over time | `ValidationReport` |
| Gate warnings (`WARN`-outcome `gate_results` details) | Caveats that didn't change the evidence ceiling but must be surfaced | `ValidationReport.warnings` |
| `failure_modes` | Why the finding was capped, if it was | `ValidationReport` |
| `recommended_validation` | What would be needed to raise the evidence level — this is the direct answer to "what could change?" | `ValidationReport` |

`controlled_variables` + `potential_confounders` + `robustness_tests` together are the answer to "which alternatives were checked" — see §1 note below on whether to merge or keep separate (flagged to Statistics, §10).

### What happens next

| Field | Meaning | Source |
|---|---|---|
| `policy_readiness` | `NOT_READY` / `EXPERIMENT_ONLY` / `SHADOW_POLICY` / `HIGH_CONFIDENCE` | `ValidationReport` |
| Next-step action | Deterministic from `policy_readiness` alone — see §9 | New, finalized here |
| Finding lifecycle status | Candidate-under-review / validated / rejected / superseded — **not** the existing job-oriented `ResourceStatus` (`pending/running/completed/failed/draft`), which describes run state, not finding lifecycle. Still open — see `HANDOFF-008`/`HANDOFF-012`, re-flagged in §10, not re-litigated here | Open — `TASK-024` |

---

## 2. Optional later

Present a real MVP without these; add once the core narrative is proven:

- `adjusted_p_value`, `family_size` — statistical significance internals; whether these are ever customer-facing is a Statistics/Architect call, not Product's (Product does not own statistical confidence, `agents/PRODUCT.md`). Reserve the slot, don't decide the exposure.
- E-value (unmeasured-confounding sensitivity) — analyst/audit detail.
- Full 16-gate detail table (every `GateId` with its `PASS`/`WARN`/`FAIL`/`NOT_EVALUATED` outcome and detail string) — an expandable technical/audit panel beyond the warnings summary.
- Segment/time-period stability as a full breakdown table or chart, beyond the `temporal_stability` summary sentence.
- Secondary/mechanism outcome decomposition (`cancellation`, `refund_amount_eur`, `support_cost_eur`, `additional_cost_eur`) shown as supplementary explanation of the primary-outcome effect — never summed into it (`docs/analytics/outcome-contract.md` §3).
- Ranking/comparison context relative to other findings — belongs to `docs/product/findings-list-screen.md` (`TASK-026`, spec complete, implementation not started).
- Feedback capture (`TASK-035` values: `KNOWN_ALREADY`/`NEW`/`WRONG`/`NOT_ACTIONABLE`/`INTERESTING`/`ACTIONABLE`) — reserve a UI slot only, don't design the workflow here.
- Policy backtest result, once `TASK-032` exists — the only path to `HIGH_CONFIDENCE` readiness and "savings" language.

---

## 3. Never shown without qualification

Each of these must always carry its stated qualifier. Showing the bare form is a defect, not a simplification.

| Item | Required qualifier |
|---|---|
| Any verb describing the pattern | Must be one of `LANGUAGE_RULES[evidence_level].permitted_verbs`, taken verbatim — never authored ad hoc. See §4; note that at `descriptive_observation` even "is associated with" and "predicts" are forbidden, reserved for level 2+. |
| `raw_effect` | Must display "descriptive, unadjusted, no interval — not a validated estimate" directly beside the number. It structurally has no interval (per `docs/analytics/outcome-contract.md`'s worked example); it must never be styled to look like a validated figure. |
| `adjusted_effect` value | Never without `ci_low`, `ci_high`, `confidence_level`, and `method` in the same view — these four always travel together (`EffectEstimate` enforces this in code; the UI must not un-bundle them). |
| "Savings" / "recoverable" language | Forbidden at levels 1–3, and at 4–5 without a positive backtest. Must read "exposure" / "value at stake" instead (`docs/analytics/validation-contract.md` §8). |
| Annualized impact figure | Forbidden unless `annualization_justified` is true; otherwise state plainly that there isn't enough history to project forward. |
| Economic impact whose interval does not exclude zero on the low side | Not material — must render as "no measurable economic effect," never as a number with a footnote. |
| Impact summed across findings | Never add two findings' `historical_impact` — requires an explicit deduplicated union-of-affected-records computation first, or it is not shown at all. |
| A mechanism/secondary-outcome figure | Always labeled "component of `<primary outcome>`," never added to the primary-outcome impact. |
| A `G01` "definitional dependency" warning (e.g. a discount rate embedded in a margin formula) | Must carry "this is a mechanical relationship, not a discovered behavior" — never presented as a plain behavioral pattern. |
| A `G09`-failed (Simpson) finding | Never shown as a pooled number with a caveat. If Statistics re-specifies it at the stratum level, the original is superseded, not caveated. |
| A `G10`-scoped (temporally limited) effect | Must carry its explicit validity window; never phrased as a standing rule. |
| `repeat_purchase_180d` or any `MNAR_BOUNDED` outcome | Never converted to a EUR figure, never combined with margin-based impact — shown only as its own rate with MNAR bounds attached (`docs/analytics/outcome-contract.md` §5). |
| `HIGH_CONFIDENCE` readiness | Currently unreachable system-wide (no backtest exists yet) — this is a fact about the system, not a per-finding judgment; do not build a UI path that expects it soon. |
| Any number | Must have deterministic-code provenance (`ADR-004`) — a generative model may phrase the sentence around a number, never originate the number. |
| A finding near the `G03` power floor | Carries a visible "small sample" qualifier even when it technically passes — rare patterns are structurally exposed to false negatives/instability at this benchmark's scale (`docs/analytics/validation-contract.md` §11). |

---

## 4. Wording ladder — association vs. stronger evidence

Quoted directly from `LANGUAGE_RULES` in `packages/analytics/src/policy_analytics/validation/contract.py`. This table is generated from that code; if the code changes, regenerate this table — never hand-edit it to diverge.

| Evidence level | Permitted claim | Permitted verbs | Forbidden |
|---|---|---|---|
| `descriptive_observation` | "In this dataset and window, these records differ on this outcome." | *is observed with, differs from, coincides with* | causal verbs; **also** "predicts", "is associated with" (reserved for higher levels) |
| `predictive_association` | "This combination is associated with a worse outcome and holds out of period." | *is associated with, predicts, identifies* | causal verbs; "after accounting for" (implies adjustment not yet done) |
| `adjusted_observational_association` | "The association survives adjustment for the listed variables; unmeasured confounding remains possible." | *remains associated with, persists after adjusting for* | causal verbs (*causes, leads to, drives, results in, reduces, increases*) |
| `quasi_causal_evidence` | "Under the stated design assumptions, the estimated effect is causal." | *is estimated to cause, under \<design\> assumptions, reduces* | "proves", "guarantees", "will save" |
| `experimental_evidence` | "Randomised assignment measured this effect." | *causes, reduces, increases* | "proves", "guarantees" |

**Standing fact for this product:** historical booking data caps evidence at `adjusted_observational_association` (`docs/analytics/validation-contract.md` §1). In practice, until an experimental or quasi-experimental design exists, no finding this system produces uses causal verbs at all.

---

## 5. Uncertainty display

- Never a bare point estimate once past `descriptive_observation`. `adjusted_effect` always shows value + interval + confidence level + method together.
- `raw_effect` (descriptive-level number) is visually de-emphasized relative to `adjusted_effect` when both exist — it is a search result, not a conclusion.
- Interval width and confidence level (95%, per contract) are Statistics' methodology, not Product's to justify; Product's obligation is only that the four `EffectEstimate` components never separate in the UI.
- If the impact interval does not exclude zero: no number is shown as an effect — see §3.

## 6. Warnings display

- Every `WARN`-outcome gate detail is rendered, regardless of whether it changed the evidence ceiling — a `WARN` still means "read this before trusting the number."
- Explicit "No caveats flagged" state when the warnings list is empty — absence must read as deliberate, not as an omission.
- `failure_modes` and `recommended_validation` are always shown together as the answer to "what could change?" — sourced directly from the validation report, never invented by Product or a generative model.

## 7. Large economic effect, weak evidence

Applies when `evidence_level` is `descriptive_observation` or `predictive_association` and the raw/exposure number is large enough to draw the eye (no absolute threshold is defined here — that would be inventing a number; this is a *display rule*, not a value):

- The evidence-level qualifier gets equal or greater visual weight than the money figure. A large unqualified number next to a small caveat invites the reader to anchor on the money.
- The framing sentence ("descriptive, unadjusted — may not hold up under adjustment") sits directly adjacent to the number, not in a collapsed section.
- No policy-candidate action is offered — the action matrix (§9) already enforces this via `policy_readiness`, since nothing below `adjusted_observational_association` reaches `SHADOW_POLICY`. This section exists to state the *visual* rule explicitly, not just the action-gating rule.

## 8. Strong evidence, small economic effect

Applies when a finding clears `adjusted_observational_association` (the practical ceiling on this dataset) but fails gate `G15` (economic materiality):

- `G15` is `readiness_only` (per `docs/analytics/validation-contract.md` §5 gate table) — it caps `policy_readiness` at `NOT_READY`, it does **not** lower `evidence_level`. The UI must never imply the evidence is weak because materiality failed; these are independent signals and must be visually distinct (evidence badge stays at its earned strength; readiness pill separately says "not material").
- Copy should say something to the effect of "this is real, but too small to act on" — never "this needs more validation," which would misattribute an economic-size problem to a statistical-rigor problem.
- Since this dataset's evidence ceiling is level 3, "strong evidence" in practice means "survives adjustment," not "proven causal" — the wording ladder (§4) already prevents overstatement here.

---

## 9. Next-step action matrix (finalized)

This finalizes the provisional table in `docs/product/finding-detail-screen.md` §7, now that `OQ-003` is resolved (`docs/analytics/validation-contract.md` §7). Driven by `policy_readiness` alone — that field already encodes "what may the business do about it," so a separate evidence-level gate is redundant and was the provisional version's simplification.

| `policy_readiness` | Available actions |
|---|---|
| `NOT_READY` | "Flag for review" only. Covers two different situations — rejected (not a real pattern) and immaterial (real but too small, §8) — the UI must distinguish these using `evidence_level`/`failure_modes`, never collapse them into one unexplained "not ready" state. |
| `EXPERIMENT_ONLY` | + "Design a controlled experiment." No policy-candidate action offered. |
| `SHADOW_POLICY` | + "Create policy candidate (shadow/log-only)," explicitly labeled as not enforced. |
| `HIGH_CONFIDENCE` | + "Propose enforced policy candidate for approval." Currently unreachable system-wide (§3) — implement the code path, but it will not fire until `TASK-032` exists. |

`docs/product/finding-detail-screen.md` §7 should be updated to point here as the authoritative table rather than keep its own provisional copy — tracked as a follow-up edit alongside this contract.

## 10. Questions for Statistics (handoff, not decided here)

Per instruction, no statistical threshold is invented above. These specific open questions are routed to Statistics via `HANDOFF-020` (see below) rather than guessed:

1. Standardized display wording when an impact interval crosses zero — is there a preferred phrase (parallel to the backtest section's "no measurable net effect," `docs/analytics/validation-contract.md` §9), and should the same phrase apply outside backtests?
2. Should `adjusted_p_value` / `family_size` ever be customer-facing, or stay in an analyst/audit-only view? Product defers to Statistics + Architect.
3. Display treatment for `NOT_EVALUATED` gates (graded identically to `FAIL`, per `GateOutcome`): should the UI say "not yet evaluated" (reads as pending) or "failed" (reads as checked-and-rejected)? These give a business user different impressions of the same programmatic outcome, and the choice should be Statistics-approved so it doesn't misrepresent rigor either direction.
4. §1 above merges `controlled_variables` and `potential_confounders` conceptually into "what was checked" for the business narrative, while keeping them as two separate lists in the data. Confirm this framing doesn't misrepresent the methodology — one list is "adjusted for," the other is "considered and still possible."
5. ~~The finding-lifecycle status vocabulary~~ — **resolved in §12** below (`HANDOFF-024`), superseding this item.

## 11. Response to HANDOFF-013

`HANDOFF-013` (Statistics → Product) asked for two things. Status of each:

1. **Finalize the next-step action matrix** now that `OQ-003` is resolved — done, §9 above.
2. **Supply the customer economics behind the materiality threshold** (`OQ-004`) — still open. Product cannot produce a real threshold from synthetic data; `OQ-004`'s resolution condition requires a real pilot customer's actual P&L, which does not exist until `TASK-057` delivers one. `agents/PRODUCT.md` also does not own customer willingness/economics (`agents/CUSTOMER_DISCOVERY.md` does). This half of `HANDOFF-013` is redirected, not answered — see `HANDOFF-021` below. The current placeholder (`min_material_annual_impact = 25000`, `min_material_outcome_share = 0.005`) remains Statistics-owned and usable for synthetic work only, per `OQ-004`'s existing text.

## 12. Finding lifecycle status and title/summary contract (resolves HANDOFF-024)

`HANDOFF-024` (Architect → Product) asked two questions to unblock locking `TASK-024`'s schema. Answered here, grounded in `docs/architecture/finding-persistence-contract.md` and `apps/api/app/findings/contracts.py`.

### 12.1 Lifecycle enum

`FindingLifecycleStatus` — distinct from the job-oriented `ResourceStatus` and from customer feedback (`TASK-035`, which does not exist yet and requires per-viewer state this product has no auth to support):

| Value | Meaning | Display |
|---|---|---|
| `ACTIVE` | The current, valid version of this finding | Default and only status shown in the findings list and full detail view |
| `SUPERSEDED` | Replaced by a newer Finding promoted from a re-specified or re-validated candidate covering the same underlying pattern (e.g. the `G09` Simpson re-specification rule, `docs/analytics/validation-contract.md` §5/§10; or a contract-version re-grade) | Never in the default list. Retrievable by direct link for audit, always with a prominent "superseded" banner replacing the normal content, linking to the replacement via `superseded_by_finding_id` when set |
| `WITHDRAWN` | Pulled for a reason other than re-specification (e.g. a data-quality defect discovered after promotion) | Same treatment as `SUPERSEDED`, showing the required `withdrawal_reason` instead of a replacement link |

**Transitions are forward-only**, matching the append-only philosophy already used for `CandidatePattern`/`ValidationReport`: `ACTIVE → SUPERSEDED`, `ACTIVE → WITHDRAWN`. Nothing transitions back to `ACTIVE` — a pattern found valid again after withdrawal is promoted as a *new* Finding from a new/re-validated candidate, never a status flip on the old row (mirrors "re-specifying a candidate creates a new candidate; it never updates the existing row").

**Deliberately excluded:**

- Any "reviewed"/"seen" state — that is per-viewer interaction state, and no multi-user auth exists (`TASK-053` is `BLOCKED` on "real external users"). A single global "reviewed" flag would misrepresent per-person state. Belongs to `TASK-035`/`TASK-036` once auth exists, not to Finding lifecycle.
- Any "awaiting validation"/"in progress" state — structurally impossible for a `findings` row: `FindingPromotion` only creates one after `validation.evidence_level` is non-null and impact is computed. A pattern still being validated is a `CandidatePattern`/`ValidationReport`, never exposed on a customer-facing Findings screen at all (`docs/architecture/finding-persistence-contract.md`: "candidate and validation audit endpoints ... are separate and non-customer-facing"). This also **retires the old `ResourceStatus`-based "Run-status gating" section** in `docs/product/finding-detail-screen.md` (`pending`/`running`/`failed` cannot occur on a promoted Finding) — updated there accordingly.
- **Staleness is computed, not stored.** A Finding graded under an older `validation_contract_version` than the currently active `CONTRACT_VERSION` is detected by comparison at read time, the same way `ADR-007` already requires re-grading on a contract bump. Storing it would need a background job to flip every old Finding the moment a threshold changes; comparing at read time can't drift out of sync. Display rule: if stale, show "graded under an earlier validation standard" — never hide it, never auto-upgrade its evidence level.

### 12.2 Title / summary contract

**Stored, versioned, deterministic snapshot — computed once at promotion time, never derived live on every read, never generative model-authored at render time (`ADR-004`).** Two fields, sharing one `title_template_version`:

- `title` — short, list-row-length business sentence (target ≤ ~80 characters).
- `summary` — one-paragraph version for the detail screen's "What we found" section.

**Why stored, not derived on read:** `CandidatePattern` and `ValidationReport` are already immutable snapshots; the rendered title should be equally reproducible. If template logic changes later, a customer who saw a finding worded one way must not have it silently reword itself underneath them with no record — an audit/traceability concern, not just a caching optimization. `title_template_version` scopes any future wording defect to exactly the findings produced under that version, without needing to touch the underlying data.

**Mechanical v0 template** (`title_template_version = "v0-mechanical"`), a pure function of `CandidatePattern.conditions` plus the outcome contract's harm-direction phrase:

```
"<outcome harm-direction phrase> when " + join(" and ", condition_phrase(c) for c in conditions)
```

- Per-condition phrasing by `operator`: `ge` → "is at least", `le` → "is at most", `gt` → "is more than", `lt` → "is less than"; `eq` on a boolean → drop the verb and state the flag (negate for `eq: false`); `eq` otherwise → "is".
- Feature names are formatted mechanically (`snake_case` → "Title Case") for v0 — an explicit, disclosed simplification, **not** a curated business label. No column in the schema carries a human-authored display label today (`DatasetColumn` has only `name`/`data_type`/`timing`) — flagged to Data Engineer below, not solved here; v0 ships "Discount Rate" (mechanical), not "the discount given to the customer" (curated).
- The outcome harm-direction phrase is sourced from the outcome contract (`docs/analytics/outcome-contract.md`), not authored per finding — e.g. for `contribution_margin_eur` (decrease = harm): "Contribution margin drops". This is data, not freehand template text.
- Truncation for many conditions (readability limit) is an Architect implementation detail, bounded by one rule fixed here: the title must stay one sentence and must never silently drop a condition without saying so (e.g. "and 2 more conditions").

This resolves `HANDOFF-024`.
