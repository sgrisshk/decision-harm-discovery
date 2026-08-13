# Customer Findings Review Protocol

**Owner:** CUSTOMER_DISCOVERY
**Supports:** TASK-042 (Customer findings review)
**Status:** Prepared in advance. Not yet executable — see "Preconditions" below.

## Purpose

A repeatable instrument for reviewing validated findings with a real pilot customer, so the
review can start immediately once findings exist, without inventing structure under time
pressure or interpreting politeness as validation.

## Preconditions (all must be true before this protocol is used)

1. A real customer has agreed to a pilot (no agreement is currently recorded in `DECISIONS.md`).
2. `TASK-037` through `TASK-041` are `DONE`: security review, real-dataset ingestion, data-quality
   review, blind discovery run, and Statistics validation of top candidates.
3. At least one candidate carries an explicit evidence level and passed conservative validation —
   this protocol reviews validated findings, not raw discovery candidates.

Until all three hold, `TASK-042` stays `BLOCKED` and this protocol must not be run against
synthetic output, a demo, or an unvalidated candidate list.

## Session structure

Review findings **one at a time**, not as a batch summary. For each finding, walk the customer
through: what was found → the affected population → the raw effect → what current policy says →
then ask the questions below before moving to the next finding.

### Per-finding capture

- **Known already vs. new** — did the customer already know this pattern existed? Ask them to
  describe what they knew *before* being shown the number, not after.
- **Actionable** — can they name a concrete change they could make? If they can't name one
  unprompted, treat it as not actionable regardless of interest expressed.
- **Economically material** — does the customer independently estimate this matters in money or
  time, using their own numbers, not the ones just shown to them?
- **Trust objections** — what do they doubt: the data, the method, the causal story, the sample
  size, confounding they suspect? Record objections verbatim; do not resolve or argue them in the
  session — route unresolved statistical objections to Statistics via a handoff.
- **Policy change willingness** — will they say they would change a specific rule, or only that
  they'd "look into it"? Distinguish a stated commitment from a stated intention.
- **Continuation/payment willingness** — do they ask about pricing, request another analysis on
  more data, request deployment, or offer to allocate staff time? These count; enthusiasm alone
  does not.

### Per-interview fields (from `agents/CUSTOMER_DISCOVERY.md`)

Company, role of interviewee, current workflow, last concrete incident, economic cost of that
incident, how the problem was discovered internally, data currently available, current tools,
decision owner (who can actually approve a policy change), pain level, pilot willingness, payment
willingness, and agreed follow-up.

## Evidence classification (apply after the session, not during)

**Strong evidence:** providing real data through an approved secure channel, allocating employee
time, requesting another analysis, changing a policy, requesting deployment, asking about
security/pricing, or paying.

**Weak evidence:** "interesting," "nice idea," "keep me updated," generic AI enthusiasm, or polite
agreement without a named next action. Weak evidence must be logged as weak, not upgraded because
the meeting felt positive.

## Explicitly out of scope for this review

- Judging statistical validity of the finding itself (Statistics already assigned the evidence
  level before this session; if the customer's objection is statistical, capture it and hand off).
- Architecture or deployment feasibility (hand off to Architect if asked).
- Do not let the session become a sales pitch that overrides the recorded objections.

## Output

One structured record per finding, filed as durable evidence per `memory/README.md` conventions:
a `FINDINGS.md` entry only if a claim becomes durable and decision-changing, an `EXPERIMENTS.md`
entry if the review itself was run as a predeclared pilot experiment, and any unresolved
statistical/technical objection as a `memory/HANDOFFS.md` entry to the owning specialist. Update
`memory/CURRENT_STATE.md` only if the review materially changes the project's active-customer
status or kill/continue signal.
