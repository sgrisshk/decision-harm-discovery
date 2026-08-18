# Policy Candidate Domain Model v0

**Owner:** PRODUCT
**Task:** TASK-030 ("Policy candidate domain model"), preparing `TASK-031` ("Policy candidate generator")
**Depends on (implementation):** none anymore — `TASK-030` is `DONE` (`ADR-029`, 2026-08-18). `TASK-031` (the generator, `READY`) is the only thing still not built; `TASK-032`/`TASK-033` (backtest engine) shipped independently (`ADR-028`, operating directly on a Finding's `pattern.conditions`, not on this persistence layer).
**Status:** Domain model **and real, tested persistence** (`apps/api/app/policies/`, migration `20260818_0007`). §1–§9 below are annotated with the concrete implementation where it now exists; nothing in the original content was wrong, §12 (added same day) turned out to match the real code closely enough that Architect implemented straight from it.

## Why this document exists now

`MILESTONE-M1` is `DONE` for its synthetic scope (`memory/CURRENT_STATE.md`, 2026-08-17): a real, persisted, UI-visible Finding now exists — 15 real `Finding` rows (`GET /api/v1/findings`), 6 of them at `adjusted_observational_association`/`shadow_policy`. `TASK-030` is unblocked to `READY` on exactly that basis. This document is Product's response: what a Policy Candidate — the *next* step in the product's own stated flow (`agents/PRODUCT.md`: Finding → Evidence → Economic impact → **Intervention** → Validation → Policy candidate) — actually is, in terms an Architect can implement and a Statistics reviewer can check, before `TASK-031` starts generating them from real Findings.

## Relationship to other authoritative documents

- `agents/PRODUCT.md` — mission and "not owned" boundary (statistical confidence, implementation architecture, willingness to pay), respected throughout.
- `docs/product/finding-product-contract.md` — the source Finding's field contract. A Policy Candidate is *derived from* one Finding; this document does not restate or recompute anything that document already fixes (evidence level, impact, readiness).
- `docs/analytics/validation-contract.md` §7–§9 — the only source of the readiness matrix, the economic-impact/exposure-vs-savings framing, and the (not-yet-implemented) backtest methodology. Quoted, never re-derived.
- `apps/api/app/db/models.py` (`PolicyCandidateModel`) and `apps/api/app/api/schemas.py` (`FindingRead` and its nested reads) — the current, real, live code this document extends. `PolicyCandidateModel` today is a minimal skeleton (`id`, `finding_id`, `title`, `rationale`, `rule_definition: JSONB`, `status: str`) — exactly the "intentionally minimal" state `FindingModel` was in before `docs/product/finding-product-contract.md`.
- `PROJECT_CONTEXT.md` non-goals — **no autonomous policy enforcement** is explicit and binding on every design choice below.

No statistical threshold or new metric is invented in this document. Every number a Policy Candidate displays is a Finding field already defined by Statistics, carried forward — never recomputed by Product.

## 0. What a Policy Candidate is, and isn't

A Policy Candidate is a **human-reviewable proposal** to change a specific future decision rule, generated deterministically from exactly one eligible Finding. It is not:

- a new statistical estimate (all numbers are the source Finding's, snapshotted — see §4);
- an executable rule (this system never enforces anything — see §2 "Action");
- guaranteed money (see §4 — pre-backtest, it is the same non-committal "exposure" framing the Finding already uses, not a promise);
- a second, independent piece of evidence — one Finding, one underlying pattern, however many candidates are drafted from it (see §6).

## 1. Eligibility — when a Finding may produce a Policy Candidate

Gated entirely by the Finding's own `policy_readiness` (`docs/analytics/validation-contract.md` §7 — "readiness answers 'what may the business do about it'"), matching `docs/product/finding-product-contract.md` §9's action matrix exactly:

| Source Finding `policy_readiness` | May a Policy Candidate be generated? |
|---|---|
| `NOT_READY` | No. |
| `EXPERIMENT_ONLY` | No — the next step at this readiness is designing a controlled experiment, not a policy candidate. |
| `SHADOW_POLICY` | Yes, in `SHADOW` mode only (§3). |
| `HIGH_CONFIDENCE` | Yes — but this readiness is currently unreachable system-wide (no backtest exists yet, `docs/product/finding-product-contract.md` §3), so this row is inert today, not a live path. |

On today's real data, this means: of the 15 real Findings, only the 6 at `adjusted_observational_association`/`shadow_policy` are eligible at all, and every eligible candidate starts in `SHADOW` mode — there is no code path today that can produce an enforcement proposal, by construction, not by an omitted feature.

**Implemented (`ADR-029`):** `app.policies.service.create_draft_policy_candidate` enforces this table exactly (`_ELIGIBLE_READINESS`), plus one gate this section didn't literally spell out but §0's "a Finding a policy candidate attaches to" already implies: the source Finding's `lifecycle_status` must be `ACTIVE`. Ratified here, not just accepted silently — generating a candidate from a `SUPERSEDED`/`WITHDRAWN` Finding would create a row §6 would immediately have to block anyway, so rejecting it at creation is the correct reading of this document's own intent, not an Architect addition beyond it. `mode` is enforced as contract-locked to `SHADOW` by a Pydantic validator, not merely undocumented as a path nothing takes.

## 2. Trigger

The **trigger** is the condition that would have fired on a historical decision — inherited verbatim from the source Finding, never re-derived or narrowed by the candidate itself:

- `trigger_conditions`: an immutable copy of the Finding's `pattern.conditions` (`FindingPatternRead.conditions`) at candidate-generation time — same feature/operator/value shape, same guarantee that every condition is `DECISION_TIME` (inherited from the validation contract's gate `G01`, not re-checked here).
- **The generator (`TASK-031`) may not edit, loosen, or tighten this condition set.** A different trigger is a different statistical claim, requiring its own Finding through the normal discovery→validation path — not a manual edit inside policy-candidate review. This mirrors the repository-wide rule that re-specifying a condition creates a new candidate/finding, never an edit to an existing one (`docs/architecture/finding-persistence-contract.md`).
- Because the trigger is a decision-time rule, it is inherently prospective-compatible: the same condition that was evaluated retrospectively on historical bookings can be evaluated on a new booking at the moment of decision. No new capability is required to make it "fireable" going forward — that property was already established by the validation contract's `G01`/`G02` gates before the Finding existed.

## 3. Scope

**Scope** is where and when the trigger applies going forward — distinct from the trigger condition itself:

- `effective_population`: defaults to "every future decision matching the trigger, within the source Finding's eligible cohort definition" (`docs/analytics/outcome-contract.md` §6) — i.e., no narrower than what the Finding was actually validated against.
- `mode`: `SHADOW` or `ENFORCEMENT_PROPOSAL` (§1's eligibility table — `SHADOW` is the only reachable value today).
- `effective_from`: a date, required, defaulting to "candidate creation date" — this is inherently forward-looking in a way the Finding itself is not (the Finding describes a closed historical window; a policy has no historical window, only a start date).
- **Guardrail — scope must never be narrowed by a variable the source Finding's validation flagged as a confounder or trap risk.** If `potential_confounders` (`FindingEvidenceRead.potential_confounders`) contains a variable, that variable cannot be used to further restrict scope (e.g. "only apply to manager X") — doing so would reintroduce exactly the confound the validation contract's gates exist to rule out, using the operational scope field as a back door around statistical review. This is a hard validation rule for `TASK-031`, not a suggestion.
- Manual scope narrowing beyond the trigger (e.g. "only new bookings from Tuesday's rollout onward," a pure timing/rollout choice unrelated to the statistical condition) is allowed and does not require new validation — it doesn't change what pattern is being acted on, only when/how broadly.

**Implemented (`ADR-029`):** `effective_population` stays free text exactly as written above. The guardrail needed something mechanically checkable, which this section didn't literally define — closed by a new `scope_narrowing_features: tuple[str, ...]` field (empty by default): `app.policies.contracts.PolicyCandidateCreate` accepts it, and `create_draft_policy_candidate` rejects any value intersecting the source Finding's `potential_confounders` before a row is ever written, raising `PolicyCandidateError` rather than silently dropping the offending feature. `TASK-031`'s generator does not need to (and must not try to) reimplement this check — it only needs to populate `scope_narrowing_features` correctly and let the persistence layer enforce it.

## 4. Expected benefit

**Reused from the source Finding, never recomputed.** A Policy Candidate carries a frozen `expected_benefit_snapshot` copied from `FindingImpactRead` at generation time (`outcome_name`, `outcome_unit`, `affected_records`, `per_record_effect`, `historical_impact`, `annualized_impact`, `annualization_justified`, `materiality_pass`) — the exact same fields, same framing rules, as the Finding itself:

- **Before a backtest exists** (`TASK-032`/`TASK-033`, not built), "expected benefit" is not a forward-looking promise — it is the Finding's own historical `historical_impact`, in **exposure** framing ("value at stake in these records," never "savings" — `docs/analytics/validation-contract.md` §8). A Policy Candidate in `SHADOW` mode (the only mode reachable today) must display this with the identical qualifier the Finding already carries; it gains no additional certainty by being wrapped in a candidate.
- **`annualization_justified` is currently hard-gated `False` for every real Finding** (`memory/CURRENT_STATE.md`, 2026-08-17 — pending a stability check not yet implemented). No Policy Candidate may show an annualized expected-benefit figure today; this is a system-wide fact, not a per-candidate judgment.
- **After a backtest exists**, a *second*, separate field applies — `backtest_result` (§7) — which is the actual forward-looking, both-sides, operational-cost-netted number per `docs/analytics/validation-contract.md` §9. Until then, `backtest_result` is `null` and the UI must not synthesize one from the exposure figure.
- Never sum `expected_benefit_snapshot.historical_impact` across multiple Policy Candidates — same deduplication rule as Findings (`docs/product/finding-product-contract.md` §3); two candidates can share affected records.

## 5. Action

**What the candidate proposes doing when the trigger fires** — and the sharpest boundary in this document, because "what pattern is harmful" (Statistics' output) and "what operational intervention to take about it" (a business/domain decision) are different kinds of knowledge:

- **The generator (`TASK-031`) may only ever propose the one safe default action**: `"Flag matching bookings for human review before proceeding"` — a non-blocking, log/flag action, matching `SHADOW` mode's own definition ("log would-be decisions without enforcing," `docs/analytics/validation-contract.md` §7). It never proposes blocking, auto-rejecting, or auto-modifying a booking. This default requires no domain knowledge beyond the statistical pattern itself and cannot make a decision worse than doing nothing.
- **Any more specific operational action** (e.g. "require a second approval," "cap the discount at X," "route to a senior manager") **is not something this system invents.** It requires the customer's own operational/domain judgment — out of scope for Product, ML Discovery, or Statistics to supply, per `agents/PRODUCT.md`'s "not owned: willingness to pay" boundary's underlying principle (this system doesn't know the customer's operational levers any more than it knows their willingness to pay). `action_detail` is a free-text field, **required to be human-authored** before a candidate can leave `DRAFT` status (§8) — never populated by a generative model inventing plausible-sounding intervention text, and never left as a placeholder that reads as if the system recommended it.
- **This system never enforces anything, at any readiness level, ever.** `ENFORCEMENT_PROPOSAL` mode (§1, currently unreachable) still only produces a *document* — "propose an enforced rule for human approval" (`docs/product/finding-product-contract.md` §9). Whether and how a real rule is actually enforced happens entirely in the customer's own operational tooling, outside this system's ownership (`PROJECT_CONTEXT.md`: no autonomous policy enforcement, no policy-management platform). The domain model has no field representing "currently enforcing" — only "proposed for the customer's own decision" (§8's terminal state).

## 6. Evidence

A Policy Candidate does not carry independent evidence — it carries a **frozen snapshot** of its source Finding's evidence state at generation time, for the same audit reason the Finding's own `title`/`summary` are snapshotted rather than live-derived (`docs/product/finding-product-contract.md` §12.2):

- `source_finding_id` (FK, `RESTRICT` — matches the existing `PolicyCandidateModel`).
- `evidence_snapshot`: `evidence_level`, `policy_readiness`, `validation_contract_version`, `finding_generated_at` — copied, not re-joined live.
- **If the source Finding later becomes `SUPERSEDED` or `WITHDRAWN`** (`FindingLifecycleStatus`, `docs/product/finding-product-contract.md` §12.1), every Policy Candidate referencing it is affected: any candidate still in `DRAFT` or `UNDER_REVIEW` is blocked from advancing further until a human reviews the change; any already `APPROVED_SHADOW` **or `APPROVED_FOR_CUSTOMER_DECISION`** is auto-transitioned to `RETIRED` with the reason "source finding no longer active" (§8). A policy candidate must never keep quietly running against a finding the system itself no longer stands behind. (The `APPROVED_FOR_CUSTOMER_DECISION` half is an extension beyond this section's original literal wording, which only named `APPROVED_SHADOW` — ratified here as correct: the stated rationale, "must never keep quietly running against a finding the system no longer stands behind," applies equally to both approved states, and leaving `APPROVED_FOR_CUSTOMER_DECISION` un-cascaded would have been an oversight, not a deliberate narrower scope.)
- One Finding may produce more than one Policy Candidate (e.g. a reviewer proposes an alternative `effective_from` date or a narrower non-confounded scope, §3) — but every one of them shares the same `evidence_snapshot`, because they share the same underlying statistical claim. Multiple candidates from one Finding are not multiple pieces of evidence; `TASK-031`'s default behavior is to generate exactly one candidate per eligible Finding, and additional candidates only arise from explicit human review action, never automatic proliferation.

**Implemented (`ADR-029`):** `app.policies.service.create_draft_policy_candidate` derives `trigger_conditions`/`evidence_snapshot` from the Finding directly — never accepted from a caller, operationalizing §2's ban on caller-supplied conditions. `validation_contract_version` comes from the linked `ValidationReportModel` row (not present on the Finding's own snapshot) rather than omitted. One-per-Finding defaults on; `force=True` creates an explicit additional one, raising `PolicyCandidateError` otherwise (never a silent no-op). `cascade_finding_lifecycle_change` implements the bullet above as a service-layer function, not a database trigger — consistent with every other lifecycle rule in this codebase being enforced in Python (`FindingLifecycleStatus` transitions, `TASK-035`'s `WRONG ⇒ comment` rule). **Disclosed gap, not fixed here:** nothing in this codebase yet transitions a Finding's `lifecycle_status` away from `ACTIVE` — no supersede/withdraw endpoint exists — so this function is built and tested directly but not called from anywhere in production today.

## 7. Backtest result

`TASK-032`/`TASK-033` shipped the same day this document was written (`ADR-028`), ahead of `TASK-031` — the engine operates directly on a Finding's `pattern.conditions` and does not need this persistence layer to exist. This section's original reservation held field-for-field:

- `backtest_result`: nullable, `null` for every Policy Candidate today (no `TASK-031` generator has run yet — the table is confirmed empty). Once populated, holds the Statistics-owned result: affected decisions, avoided bad outcomes **and** suppressed good outcomes (both sides always, per `docs/analytics/validation-contract.md` §9), benefit, operational cost, net effect with interval, computed only against the future holdout split, never the window the pattern was discovered in.
- A net effect whose interval includes zero must be shown as "no measurable net effect" — never as a positive (existing rule, reused, not reinvented here).
- Until this field is non-null, no Policy Candidate may claim a validated forward-looking benefit — §4's exposure framing is the ceiling.

**Implemented (`ADR-029`):** `app.policies.contracts.PolicyCandidateBacktestSnapshot` validates the real `BacktestResult.to_dict()` shape exactly (`docs/analytics/policy-backtest-contract.md`) — `affected_decisions`, `avoided_bad_outcomes`/`suppressed_good_outcomes` (with a model validator enforcing they sum to `affected_decisions`, the same both-sides guarantee `BacktestResult.__post_init__` already enforces one layer down), `bad_outcome_definition`, `benefit`/`benefit_is_adjusted`, `operational_cost`/`operational_cost_per_review_eur`, `net_effect`/`net_effect_is_cost_exclusive`, `no_measurable_net_effect`, `methodology_disclosure`. Nothing writes to this field yet — reserved per this section, not populated by `TASK-030`'s scope.

## 8. Status

`PolicyCandidateStatus` — distinct from `FindingLifecycleStatus`, and forward-only, matching this repository's established append-only convention for lifecycle enums:

| Value | Meaning | Entry condition |
|---|---|---|
| `DRAFT` | Generated by `TASK-031` from an eligible Finding; `action_detail` not yet human-authored. | Initial state. |
| `UNDER_REVIEW` | A human (Product, Customer Discovery, or the pilot customer) is actively evaluating it; `action_detail` has been supplied. | From `DRAFT`, once `action_detail` is non-empty. |
| `REJECTED` | A human decided not to pursue it. Requires a `rejection_reason` (mirrors `FindingLifecycleStatus.WITHDRAWN`'s required-reason pattern). Terminal. | From `UNDER_REVIEW`. |
| `APPROVED_SHADOW` | Approved to track in shadow/log-only mode. The practical ceiling of what this system can approve until `TASK-032` exists. | From `UNDER_REVIEW`, only if source Finding's `policy_readiness` permitted `SHADOW_POLICY`+ at snapshot time. |
| `APPROVED_FOR_CUSTOMER_DECISION` | A backtested proposal document, handed to the customer for their own enforcement decision — not this system enforcing anything (§5). | From `APPROVED_SHADOW`, only once `backtest_result` is non-null with a net effect excluding zero on the positive side (mirrors `HIGH_CONFIDENCE`'s own condition, `docs/analytics/validation-contract.md` §7). Unreachable today. |
| `RETIRED` | No longer active — either a human withdrew it, or its source Finding became `SUPERSEDED`/`WITHDRAWN` (§6). Requires a reason. Terminal. | From `APPROVED_SHADOW` or `APPROVED_FOR_CUSTOMER_DECISION`. |

No transition ever returns a candidate to `DRAFT` or `UNDER_REVIEW` from a later state. A reconsidered `RETIRED`/`REJECTED` candidate is a new candidate generated fresh from a current (possibly re-validated) Finding, never a revived old row — same principle as `FindingLifecycleStatus` and `CandidatePattern`.

**Implemented (`ADR-029`):** `app.policies.service.transition_policy_candidate` enforces this table as a literal adjacency map (`_TRANSITIONS`), rejects any edge not listed (`PolicyCandidateError`, never a silent coercion), enforces the `action_detail`-before-`UNDER_REVIEW` entry condition, and requires a `reason` for both `REJECTED` (stored as `rejection_reason`) and `RETIRED` (stored as `retirement_reason`) — matching this table's own "Requires a reason" cells for both terminal states, not just the one this document's prose emphasized more. A `blocked_by_source_lifecycle` flag (§6) additionally halts any transition, checked before the adjacency map, so a blocked candidate cannot advance even along an otherwise-legal edge.

## 9. What must never be interpreted as validation

Mirrors `docs/product/finding-feedback-contract.md` §7's boundary, restated for this object:

- **A Policy Candidate existing, or reaching `APPROVED_SHADOW`, is not proof the policy works.** It is a human-reviewable proposal built from one Finding's already-established evidence level — creating or approving a candidate changes nothing about that evidence level.
- **`expected_benefit_snapshot` before a backtest is not a savings estimate.** It is the same historical exposure figure the Finding already shows, wrapped for review, not a new, stronger claim.
- **Shadow-mode logging data accumulating over time is not the same as a `TASK-032` backtest.** The backtest replays *historical* decisions under strict methodology (decision-time only, both sides, out-of-period, uncertainty-bounded, operational-cost-netted). Live shadow logs are a different, prospective evidence source this document does not define and does not authorize conflating with a backtest result.
- **`APPROVED_FOR_CUSTOMER_DECISION` is not enforcement, and never becomes it inside this system.** Whether a customer actually turns a proposal into a live operational rule is a fact this system can, at most, later record as reported by the customer — never something it executes.
- **One Finding producing multiple Policy Candidates is not multiple independent confirmations** of the pattern (§6) — they share one `evidence_snapshot`.

## 10. Explicitly out of scope for this document

- Persistence migration extending `PolicyCandidateModel` — Architect's call, handed off below.
- UI for reviewing/approving candidates — not laid out here.
- The generator's exact deterministic algorithm (`TASK-031` itself) — this document fixes what a candidate *is*, not the procedure that produces one from a Finding.
- Backtest statistical methodology beyond what `docs/analytics/validation-contract.md` §9 already fixes (`TASK-032`/`TASK-033`, Statistics-owned).
- Real customer review workflow specifics for policy candidates (parallel to `docs/customer/findings-review-protocol.md` for Findings) — a natural future document, not written here.

## 11. Handoff to Architect — future persistence, not current implementation

Recorded as `HANDOFF-049` in `memory/HANDOFFS.md`. `TASK-031` (the generator that would produce real rows against this model) stays correctly `BLOCKED` on this document reaching `DONE` status via Architect/Statistics sign-off, exactly as `TASK-035`'s persistence stayed deferred behind `HANDOFF-031` until its own prerequisites landed.

**Status (2026-08-18):** Statistics' half of `HANDOFF-049` is answered (confirmed §3's confounder-scope-narrowing guardrail and §7's `backtest_result` shape match the now-real, frozen `TASK-032` engine — `docs/analytics/policy-backtest-contract.md`). Architect's half — the persistence-shape/trigger-vs-constraint question — remains open. §0–§11 above stay as originally written; §12 below is added now, ahead of that answer, the same way this whole document was written ahead of `TASK-031` existing.

## 12. Generation procedure (for TASK-031)

§0–§11 fix what a Policy Candidate *is*. This section fixes the piece TASK-031's own goal text ("**deterministically** translate validated findings into reviewable interventions") still needs and the rest of this document doesn't cover: how a candidate actually comes into existence.

- **Manually triggered, not automatic.** No candidate is created the instant a Finding reaches an eligible `policy_readiness` — matches this repository's consistent pattern of explicit, reviewable pipeline steps (`scripts/promote_findings.py`, `scripts/run_backtest.py`; nothing cascades automatically anywhere else in this system either). A human/operator runs generation, either against one named Finding or as a batch over every currently-eligible Finding lacking a candidate.
- **Idempotent per Finding, by default.** Running generation again over a Finding that already has at least one Policy Candidate produces **no new row** — matches §6's "`TASK-031`'s default behavior is to generate exactly one candidate per eligible Finding." A second candidate for the same Finding only ever comes from an explicit, separate human review action (e.g. "propose an alternative scope," §3), never from re-running the batch generator.
- **Deterministic per-Finding output.** For one eligible Finding, generation always produces the same `trigger_conditions` (§2, copied verbatim), the same default `mode = SHADOW` (§1 — `ENFORCEMENT_PROPOSAL` is not reachable by this generator; nothing in `TASK-031` needs to special-case a mode it can never legitimately choose), the same `evidence_snapshot`/`expected_benefit_snapshot` (§4/§6, copied at generation time), and status `DRAFT`.
- **`action_detail` starts unset, not pre-filled.** The generator does **not** write the safe default action text (§5) into `action_detail` itself — doing so would make a machine-authored string indistinguishable from a human-reviewed one the moment it exists, undermining §5's "required to be human-authored before a candidate can leave `DRAFT`" rule. Instead, the safe default ("Flag matching bookings for human review before proceeding") is surfaced only as a **suggested placeholder** in the review UI (`docs/product/customer-review-workflow.md`/detail view), which a reviewer must actively accept or edit before the candidate can advance to `UNDER_REVIEW` (§8). The generator's own output has `action_detail = null`.
- **A skipped Finding is disclosed, not silent.** A generation run reports, per Finding it considered: created / skipped-already-has-candidate / skipped-ineligible (with the specific reason — readiness, outcome, or lifecycle status) — the same audit-disclosure discipline `TASK-015`'s run manifest and `scripts/promote_findings.py` already apply to their own batch operations, not a new pattern invented here.
- **No numerical threshold is chosen by the generator.** Every number a generated candidate carries is copied from the source Finding (§4/§6) — matches `TASK-031`'s own goal text ("a generative model may later explain but never invent numerical thresholds") by construction: there is no step in this procedure where a new number could be introduced, generative model or otherwise.
