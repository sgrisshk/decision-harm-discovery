# Finding Feedback Contract v0

**Owner:** PRODUCT
**Task:** TASK-035 ("Finding feedback model"), preparing `TASK-036` ("Customer review workflow")
**Depends on (implementation):** `TASK-027` (finding detail screen — reserves the UI slot this feeds) and `TASK-035` itself, both `BLOCKED`. `TASK-036` additionally depends on `TASK-035`.
**Status of this document:** Semantic/field contract only. No persistence, no UI, no statistical method is implemented or proposed here.

## No customer feedback has been captured, and none can be yet

Per `docs/customer/findings-review-protocol.md`'s own preconditions, this protocol — and therefore this feedback model — cannot run until a real customer has agreed to a pilot, `TASK-037`–`TASK-041` are `DONE`, and at least one candidate carries a real evidence level. None of that exists (`TASK-057` is still `TODO`; see `memory/CURRENT_STATE.md`). This document defines the contract *in advance*, the same way `docs/product/finding-product-contract.md` and `docs/product/finding-detail-screen.md` were written ahead of their backends, so `TASK-036` can execute immediately once preconditions are met instead of inventing structure under time pressure.

## Relationship to other documents

- `agents/PRODUCT.md` — mission and "not owned" boundary (statistical confidence, implementation architecture, willingness to pay) this document respects throughout.
- `docs/product/finding-product-contract.md` — the Finding's own field contract (evidence, impact, lifecycle). Feedback attaches to a Finding by `finding_id` but never writes back into it.
- `docs/product/findings-list-screen.md` / `docs/product/finding-detail-screen.md` — the detail screen already reserves a "quick reaction capture" UI slot for exactly the six values formalized here (`docs/product/finding-detail-screen.md`, "What you can do next" section); this document is that reservation's content contract.
- `docs/customer/findings-review-protocol.md` — the session methodology (one finding at a time, ask novelty before showing the number, distinguish stated commitment from stated intention, log weak evidence as weak). This document's fields are built to be filled *by* that protocol, not to replace it.
- `agents/CUSTOMER_DISCOVERY.md` and `agents/README.md`'s independence rule ("Customer Discovery cannot convert polite interest into validated demand," "Product cannot assign evidence strength") — the hard boundary behind §7 below.

---

## 1. Why a single enum is not enough

The six requested values do not sit on one axis. Collapsing them into one single-select enum forces two failures: contradictory-but-real customer reactions become inexpressible (a customer can simultaneously say "we knew this" *and* "we could act on it" — `KNOWN_ALREADY` and `ACTIONABLE` are not mutually exclusive), and an arbitrary precedence rule would have to silently decide which value "wins" when a customer's actual reaction touches more than one, destroying information the review session captured.

Reading the six values against what they actually measure:

- `KNOWN_ALREADY` / `NEW` answer **novelty** — did the customer already know this pattern.
- `ACTIONABLE` / `NOT_ACTIONABLE` answer **actionability** — can they name a concrete change.
- `WRONG` answers neither — it's the customer disputing the finding's **factual accuracy**, independent of whether it's novel or actionable (you can dispute something new or something known; you can dispute something you'd otherwise act on).
- `INTERESTING` answers neither — per `docs/customer/findings-review-protocol.md`, it is explicitly **weak, generic-enthusiasm** engagement, not a judgment on novelty, actionability, or correctness.

**Answer to "should novelty and actionability be separate dimensions": yes**, and the split goes one step further than a 2-axis model — `WRONG` and `INTERESTING` are not axis values at all. They are independent qualifier tags that can attach to any novelty/actionability answer (or to neither, if that's all the session captured).

## 2. Structure

Three independent parts, built only from the six requested literal values — no new value names introduced:

### 2.1 Novelty (single-select, nullable)

| Value | Meaning |
|---|---|
| `KNOWN_ALREADY` | The customer states they knew this pattern existed, **described before being shown the number** (`docs/customer/findings-review-protocol.md`'s explicit capture method — ask what they knew first, not after). |
| `NEW` | The customer states they did not know this pattern existed. |

Nullable, not a forced choice: a session may capture a `WRONG` or `INTERESTING` reaction before novelty is even discussed. But the protocol's session structure already asks this for every finding, so in practice it should be present on a completed review.

### 2.2 Actionability (single-select, nullable)

| Value | Meaning |
|---|---|
| `ACTIONABLE` | The customer names a concrete change they could make, **unprompted**. |
| `NOT_ACTIONABLE` | The customer cannot name one unprompted — recorded as not actionable **regardless of interest expressed** (verbatim rule from `docs/customer/findings-review-protocol.md`; a customer being enthusiastic does not upgrade this). |

### 2.3 Qualifier tags (multi-select set, default empty)

| Tag | Meaning |
|---|---|
| `WRONG` | The customer disputes the finding's factual accuracy against their own domain knowledge — e.g. "we don't have that policy," "that manager left months ago," "this destination is mislabeled." This is a **domain-fact** dispute, not a statistical one. A customer's statistical objection (sample size, confounding, causal story) is captured as a trust objection and routed to Statistics per the review protocol — it does not set this tag. |
| `INTERESTING` | Polite or positive engagement without a named commitment — "interesting," "nice," "keep me updated," generic enthusiasm. Present **only** as a soft signal; see §7. |

Both tags may apply, one may apply, or neither. They are additive annotations on top of whatever novelty/actionability answer (if any) was captured, not alternatives to it.

## 3. Valid combinations

All combinations of {novelty ∈ {`KNOWN_ALREADY`, `NEW`, null}} × {actionability ∈ {`ACTIONABLE`, `NOT_ACTIONABLE`, null}} × {tags ⊆ {`WRONG`, `INTERESTING`}} are **structurally storable**. Nothing here rejects a genuine, if messy, human reaction. Two rules apply on top:

1. **`WRONG` requires a comment.** If `WRONG` is in the tag set, `customer_comment` (§4) is not optional — a dispute with no explanation is unusable and must not be stored as a bare flag. This is the one place a free-text field becomes structurally required rather than optional.
2. **`WRONG` + `ACTIONABLE` is flagged for reviewer double-check, not rejected.** A customer disputing a finding while also naming an action on it is an apparent contradiction worth a second look in-session, but real interviews are inconsistent and the tool must not silently coerce or discard the customer's actual words to force consistency.

No other combination is special-cased. In particular, `KNOWN_ALREADY` + `NOT_ACTIONABLE` + no tags — the lowest-signal, most common-looking combination — is valid and expected; see §6 for what it feeds.

## 4. Additional fields

| Field | Type | Required? | Meaning |
|---|---|---|---|
| `finding_id` | reference | Required | The Finding this reaction is about. Never writes back to it (§7). |
| `review_session` | reference (company + session date; see note) | Required | Which review session this came from. A formal `review_session` persistence object doesn't exist yet — Customer Discovery's session records currently live as markdown log rows (`docs/customer/pipeline.md`). This document does not invent that schema; it only requires the link to exist once one is built (see §9). |
| `captured_at` | timestamp | Required | When this reaction was recorded (during or immediately after the session — see §5 on not editing after the fact). |
| `novelty` | `KNOWN_ALREADY` \| `NEW` \| null | Optional (see §2.1) | — |
| `actionability` | `ACTIONABLE` \| `NOT_ACTIONABLE` \| null | Optional (see §2.2) | — |
| `tags` | subset of `{WRONG, INTERESTING}` | Optional, default empty | — |
| `customer_comment` | free text, verbatim | Required if `WRONG` ∈ `tags`, else optional | The customer's own words, not a paraphrase or generative model summary. Recorded, not resolved or argued in-session (review protocol). |
| `customer_certainty` | `LOW` \| `MEDIUM` \| `HIGH`, nullable | Optional | The customer's **own, self-reported** sense of how sure they are about *their reaction* (e.g. how sure they are this was already known, or that it's wrong) — a subjective business signal, not a statistical one. **Never named "confidence"** in code or copy, and never combined, averaged, or displayed alongside any `EffectEstimate.confidence_level` or CI from `docs/product/finding-product-contract.md` — that would misrepresent a customer's gut feeling as statistical evidence. Useful only for triage (e.g. a `HIGH`-certainty `WRONG` deserves faster follow-up than a shrugged one). |
| `intended_action` | free text, nullable | Optional | What the customer says they would do, in their words. |
| `commitment_strength` | `STATED_COMMITMENT` \| `STATED_INTENTION` \| `NONE`, nullable | Optional | Formalizes the review protocol's existing distinction ("will change a specific rule" vs. "will look into it") into a queryable field — not a new semantic, a named version of a rule the protocol already states. |
| `customer_owner` | free text (name/role), nullable | Optional | The person on the customer side who can actually approve acting on this finding — reuses `agents/CUSTOMER_DISCOVERY.md`'s existing "decision owner" concept, scoped per finding in case it differs from the session's general decision owner. |
| `internal_follow_up_owner` | free text (role), nullable | Optional | Which of our roles is responsible for chasing this specific reaction. Not requested explicitly but cheap and useful to distinguish from `customer_owner`, which is a different person entirely. |
| `follow_up_date` | date, nullable | Optional, only meaningful when `commitment_strength ≠ NONE` or `actionability = ACTIONABLE` | When to check back. Nothing to follow up on if the finding was `NOT_ACTIONABLE` with no expressed commitment — leave null rather than inventing a date. |

## 5. Record lifecycle — append-only

Matches this repository's existing immutability posture (`CandidatePattern`/`ValidationReport` are immutable snapshots; `FindingLifecycleStatus` transitions are forward-only, `docs/product/finding-product-contract.md` §12). Feedback records are **append-only**: if a customer's view changes in a later session — "actually, now that we've discussed it more, this is actionable" — that is a **new** feedback record for the same `finding_id` under a new `review_session`, not an edit to the old one. The interview history (what was said, and when) is itself evidence; overwriting it would delete the record of a changed mind, which is exactly the kind of signal §6 needs.

Natural key: `(finding_id, review_session)`, not `finding_id` alone — the same customer may review the same finding across multiple sessions (repeat pilots, `TASK-043`/`TASK-044`), and different customers entirely may review the same synthetic-benchmark-derived finding once real pilots multiply.

## 6. How this feeds product learning

- **New-finding rate** (`novelty = NEW` share) and **actionability rate** (`actionability = ACTIONABLE` share) across a customer's reviewed findings are the concrete inputs to `MILESTONE-M3`'s success criterion ("new + economically material + actionable") and `TASK-045`'s repeatability assessment across customers.
- **`WRONG` rate** is a signal to route, not to silently absorb — a `WRONG` tag on a finding is a handoff trigger to Data Engineer (if the dispute is about data/canonicalization) or Statistics (if it's really a disguised statistical objection the customer voiced in factual language). It is evidence that something upstream may need review, never something this feedback layer resolves itself.
- **`KNOWN_ALREADY` + `NOT_ACTIONABLE` + no tags, repeated across most findings shown to a customer**, is a direct, literal instance of this project's own documented kill signal (`memory/CURRENT_STATE.md`: "the system repeatedly produces only obvious, unstable, economically immaterial, or non-actionable relationships"). This feedback model is the mechanism that would actually detect that condition from real reactions rather than assumption.
- **`INTERESTING`-heavy, commitment-free patterns** (many tags, no `STATED_COMMITMENT`, no follow-through) are the operational definition of "polite interest," which `agents/README.md`'s independence rule already says Customer Discovery must not convert into validated demand on its own. Tracking the *rate* of interest-without-commitment across sessions is how Founder Strategy would notice this happening in aggregate rather than per-anecdote.
- All of the above are **counts and rates over human-reported categorical/text fields** — arithmetic on stored labels, not a new statistical method. Any real analysis beyond counting (e.g. "is the actionability rate significantly different between two customer segments") is a `agents/STATISTICS.md` question if it's ever asked, not something this document authorizes Product to compute.

## 7. What must never be interpreted as validation

- **Feedback never changes a Finding's `evidence_level` or `policy_readiness`.** This document's fields have no write path to `ValidationMetadataPersistence`, `EvidenceLevel`, or `PolicyReadiness` (`docs/product/finding-product-contract.md`). If a `WRONG` dispute reveals a genuine methodological problem, the fix is a new validation run through Statistics under the normal, versioned contract process (`ADR-007` re-grading) — never a direct mutation triggered by a feedback row. Evidence strength stays exclusively Statistics-owned; Product does not assign it (`agents/README.md` independence rule).
- **`ACTIONABLE` does not mean the pattern is causal**, and does not mean a policy built on it will work. It means the customer could name an action. The finding's evidence level is unchanged by this tag either direction.
- **`NEW` does not mean the pattern is real or correct.** Novelty and correctness are orthogonal — a finding can be both `NEW` and `WRONG` at once.
- **`INTERESTING` is never strong evidence and must never be counted toward validated demand**, pricing signal, or product-market fit — per `docs/customer/findings-review-protocol.md`'s own explicit classification of it as weak, generic enthusiasm.
- **One customer's feedback is not repeatability evidence.** A single pilot's reactions — however positive — must not be treated as proof the product works generally; that requires the independent multi-customer comparison `TASK-045` already exists to perform.
- **A stated `intended_action` or `commitment_strength = STATED_COMMITMENT` is not validated willingness to pay.** `TASK-046` ("ask a customer to pay; stated willingness alone is not validation") and `TASK-047` (pricing test) are the only things that validate payment willingness — this feedback model must not be read as having already done that.
- **A `WRONG` tag on one finding is not a verdict on the dataset or the whole pipeline**, and a clean `NEW`/`ACTIONABLE` reaction on one finding does not certify data quality either. Each feedback record is scoped to exactly one finding.
- **Feedback never feeds back automatically into ML Discovery ranking or Statistics' validation thresholds.** Any methodological change motivated by patterns seen in customer feedback goes through a deliberate, `DECISIONS.md`-recorded change by the owning specialist — never an automated loop from this data into the discovery/validation code.

## 8. Explicitly out of scope for this document

- Persistence model, database schema, migrations — Architect's call, handed off in §9, not designed here.
- UI implementation of the capture form — reserved as a slot in `docs/product/finding-detail-screen.md`, not laid out here.
- Any statistical treatment of feedback data (significance testing across segments, weighting, aggregation formulas beyond plain counts/rates) — not proposed; would require `agents/STATISTICS.md` if ever needed.
- The customer/session/interview persistence model itself (`review_session`) — referenced, not defined; currently a markdown log (`docs/customer/pipeline.md`), formalizing it (if ever needed) is a separate Customer Discovery/Architect decision.
- `TASK-036`'s actual review-workflow UI (batch vs. one-by-one screen mechanics beyond what `docs/customer/findings-review-protocol.md` already specifies) — this document only fixes what a feedback record contains, not how the reviewer's screen is laid out.

## 9. Handoff to Architect — future persistence, not current implementation

Recorded as `HANDOFF-031` in `memory/HANDOFFS.md`. Implementation is explicitly **not** requested now — it stays `BLOCKED` behind `TASK-027` (which reserves the UI slot this feeds) and `TASK-035` itself, both currently `BLOCKED`. The handoff exists so the eventual persistence design has this contract available ahead of time, the same way `docs/product/finding-product-contract.md` was available before `docs/architecture/finding-persistence-contract.md` was written.
