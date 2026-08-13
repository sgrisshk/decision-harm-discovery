# Customer Data Acquisition Plan

**Owner:** CUSTOMER_DISCOVERY
**Date:** 2026-08-13
**Relates to:** `TASK-057` (secure first real pilot customer, travel-agency-scoped), `ADR-010`
**Status:** Draft plan, not yet executed — zero outreach has occurred as of this writing.

## 0. Scope and explicit non-promises

This plan is **not** a sales validation exercise. Its only goal is to get real historical
transactional data from real businesses into research/pilot hands, so the discovery methodology
can be tested against something other than a synthetic benchmark. It does not validate willingness
to pay, does not commit us to build support for any vertical beyond the current travel-agency
pipeline, and does not commit any prospect to anything beyond sharing one historical export.

Every outreach message, call, and follow-up in this plan must hold two lines exactly:

- **No causal proof.** We will describe candidate patterns and, at most, adjusted observational
  associations (the ceiling this product can reach on observational data — see `DECISIONS.md`
  evidence-level ADR). We do not say "causes," "proves," or "guarantees will fix."
- **No production-ready platform.** There is no self-serve upload portal, no hosted dashboard, no
  SLA (`SECURITY.md`: "Upload is intentionally not implemented in this bootstrap"). This is
  positioned as hands-on research work by the founder, not a product demo.

Anyone on this project quoting this plan externally should not round either constraint away.

## 1. Initial ICP shortlist

Screened for: SMB-scale (single reachable decision-maker, not a procurement committee),
transaction-level historical data already sitting in *some* exportable system (CRM/ERP/booking
software, not paper), a human-agent-mediated decision point (someone routinely exercises
discretion — a discount, an exception, a rate, a carrier/supplier choice) whose downstream cost is
plausible but not already fully explained, and a regulatory/PII burden light enough that a
pseudonymized historical extract is a realistic ask.

| Vertical | Fit reasoning | Verdict |
|---|---|---|
| Travel agencies / tour operators | Existing wedge; canonical schema, synthetic benchmark, and outcome contract are already built for this exact structure | **In top 3** — kept as anchor |
| Recruitment / staffing agencies | Consultant-mediated placements, guarantee-period fallout, ATS exports (Bullhorn/JobAdder), owner-led SMBs, low PII sensitivity if candidate names are stripped | **In top 3** |
| B2B wholesale distribution / manufacturer reps | Rep-granted discounts/credit terms, ERP exports (NetSuite/QuickBooks/SAP B1), high transaction volume, owner/CFO-led, minimal PII | **In top 3** |
| Insurance brokerages / MGAs | Very strong structural analogy (agent discretion, loss ratio outcome) but high compliance/PII sensitivity likely slows a first, unpaid data ask | Alternate — revisit in wave 2 |
| Freight / logistics brokerages | Dispatcher/rep rate and carrier decisions, TMS exports, real margin and claims outcomes | Alternate — revisit in wave 2 |
| Real estate brokerages | Agent commission/price-concession behavior is a good analog, but decision-time feature richness is thinner and ownership is fragmented (individual agents, not the brokerage, often hold data) | Alternate |
| SMB lenders / BNPL underwriters | Rich decision data but regulatory and PII burden too high for an unpaid research ask at this stage | Excluded for now |
| Healthcare billing/scheduling | Same reasoning — regulatory burden too high before any pilot credibility exists | Excluded for now |

**This narrowing is a Customer Discovery judgment call, not a Founder-approved decision — see
§10 for the strategic question this raises.**

## 2. Three most suitable verticals

### 2.1 Travel agencies / tour operators

| Field | Detail |
|---|---|
| Transaction unit | Individual booking (one trip/package/reservation line) |
| Economic outcome available | Contribution margin per booking (price − cost − discount − refund/cancellation cost − support cost); cancellation/refund rate; repeat purchase |
| Data volume needed | 12–24 months of history; 2,000–10,000+ bookings gives room for segment-level (manager/supplier/channel) analysis; a few hundred is still usable for descriptive-only findings but not adjusted comparisons |
| Data owner | Owner or operations manager who administers the booking/reservation system |
| Buyer/user | Owner/GM is both the data owner and the decision owner for any policy change; day-to-day report reader is typically the ops or sales manager |

### 2.2 Recruitment / staffing agencies

| Field | Detail |
|---|---|
| Transaction unit | Individual placement (candidate–role–client match) or contract engagement |
| Economic outcome available | Net fee retained (fee minus refund/replacement cost inside the guarantee window); fallout rate within guarantee period; time-to-fill; client repeat business |
| Data volume needed | 12–24 months; 500–3,000+ placements is workable, smaller agencies may only have a few hundred/year — still enough for descriptive findings, not for confident segment comparisons |
| Data owner | Owner/managing director, or whoever runs the ATS/CRM (Bullhorn, JobAdder, Vincere, etc.) |
| Buyer/user | Managing director/owner decides on policy; recruitment ops manager is the likely day-to-day reader |

### 2.3 B2B wholesale distribution / manufacturer reps

| Field | Detail |
|---|---|
| Transaction unit | Individual sales order / invoice line |
| Economic outcome available | Gross/contribution margin per order; late-payment or bad-debt rate; return rate; customer churn |
| Data volume needed | 12–24 months; distributors typically generate thousands to tens of thousands of orders/year, so even a single quarter can carry enough volume — target 3,000–20,000+ rows |
| Data owner | Owner/CFO/controller, or whoever exports from the ERP (NetSuite, QuickBooks, SAP Business One) |
| Buyer/user | Owner/GM or sales director decides; sales ops or finance is the day-to-day reader |

## 3. Outreach message framework

Three variants, same substance, different channel. All variants must include: who we are, what we
want (a one-time historical export, not a live integration), what they get (a free findings
report, no cost, confidential), and the two non-promises from §0. Keep first-touch messages under
120 words — the ask is small on purpose.

### 3.1 Warm intro (preferred first move — see §9, warm intros beat cold outreach on data-sharing asks)

> "[Name] mentioned you run the data side at [Company] and might be a good person to talk to. I'm
> doing independent research into whether historical [booking/placement/order] data hides costly
> patterns a business wouldn't normally notice — things like which combinations of decisions quietly
> lose money. No product, no pitch: I'd look at 12–24 months of your historical data under NDA, for
> free, and hand back a short findings report either way. Worth 20 minutes to see if it's a fit?"

### 3.2 Cold email

> Subject: A free look at what's quietly costing [Company] money
>
> Hi [Name],
>
> I'm researching whether historical [booking/placement/order] records contain decision patterns
> that quietly hurt margin — the kind no one notices because no single case looks wrong. I'm looking
> for a small number of businesses willing to share 12–24 months of historical transaction data
> (anonymized where it matters) for a free, confidential analysis. You'd get a plain-language
> findings report regardless of what we find. This isn't a product pitch — there's no platform to
> buy, and I won't claim to have proven anything, just surfaced patterns worth your own judgment.
>
> Would a short call make sense?

### 3.3 LinkedIn / short DM

> "Doing independent research on hidden margin-losing patterns in [travel booking / placement /
> distribution] data. Looking for a few businesses willing to share a historical export (anonymized,
> NDA, free) in exchange for a findings report. No product pitch — open to a quick call?"

## 4. Discovery call questions

Structured per `agents/CUSTOMER_DISCOVERY.md`'s required capture fields, plus dataset-specific
questions needed before any data changes hands.

**Company and role**
- What's your role, and are you the person who'd approve sharing a historical data export?
- Who else would need to sign off — anyone in legal/compliance/IT?

**Current workflow and pain**
- Walk me through how a typical [booking/placement/order] gets decided end to end.
- What's the last time something like this went wrong in a way that cost real money? What
  happened, and what did it cost, roughly?
- Is that a one-off, or does it feel like a pattern you can't quite pin down?
- How was that cost discovered — did someone notice, or did it surface in a report?

**Data availability**
- What system holds this data today (name the software)? How far back does it go?
- What's roughly in each record — decision-time fields (who handled it, what terms were offered)
  versus what happened afterward (cancelled, refunded, disputed, churned)?
- Roughly how many transactions per month/year?
- Is customer-identifying information (names, emails, phone) in the export, or can it be stripped/
  hashed before sharing?

**Tools and ownership**
- What CRM/ERP/booking software do you use?
- Who actually owns/administers that system?

**Pain level and willingness**
- On a scale of "mildly curious" to "actively costing us sleep," where does this sit?
- Would you be open to sharing a small sample first (a month, anonymized) before a full export?
- If this analysis found something concrete, is there someone who could actually change a policy
  because of it?

**Follow-up**
- Who should get the findings report, and in what format works for them?
- What would make this a clear "yes, keep going" versus "interesting, but not now"?

## 5. Minimal data request

- **Time window:** 12–24 months of historical, transaction-level records (a one-time extract, not
  a live feed or integration).
- **Grain:** one row per transaction (booking/placement/order), not pre-aggregated.
- **Fields:** whatever the business already tracks that splits into decision-time (known when the
  decision was made — who handled it, discount/terms offered, channel, segment) versus outcome
  (what happened after — cancelled, refunded, defaulted, churned, margin realized). We do not
  prescribe an exact schema up front; Data Engineering classifies whatever arrives.
- **Identifiers:** customer/employee names, emails, and phone numbers stripped or hashed before
  transfer wherever possible. A stable pseudonymous ID per customer/agent is useful (needed for
  repeat-purchase/consultant-level analysis) and is compatible with removing real names.
  Deterministic pseudonymization is one option to explain if a prospect wants details.
  Note: the current benchmark schema (`travel-booking-canonical-v1.0.0`) is travel-agency
  specific; recruitment and distribution data will not map onto it without new schema work — see
  §10.
- **Format:** CSV or Excel export, whatever the source system already produces.
- **Volume floor:** enough rows for the vertical's target in §2; below roughly a few hundred
  transactions, only descriptive observations are realistic, and that should be said upfront, not
  discovered after the fact.
- **How it's transferred:** manually, via a mutually agreed encrypted channel (password-protected
  archive, one-time secure link) — not committed to this repository, not emailed in the clear.
  There is no self-serve upload path yet (`SECURITY.md`); say this plainly if asked how the data
  moves.

## 6. Data privacy objections

| Objection | Honest answer |
|---|---|
| "We don't want our data leaving our systems." | Offer alternatives in order of preference: (1) an anonymized/aggregated extract instead of raw rows; (2) a smaller sample first to build trust; (3) a screen-share walkthrough where they run the export and redact fields live before sending. |
| "Is this GDPR/CCPA-compliant?" | This is a manual, one-time research transfer, not a hosted platform processing personal data at scale. We ask them to strip or hash direct identifiers before sending. A short written data-use agreement (not a full DPA) covers scope, retention, and deletion. If they need a formal DPA, that's a signal to loop in Founder Strategy before proceeding — see §9 bad-signal list. |
| "Will you resell or reuse our data, or use it to build a product without our consent?" | Put it in writing: data is used only to produce their findings report, is not shared with any third party, is not used to train or sell anything, and is deleted on request. |
| "How is it stored and secured once you have it?" | Be direct: there is no production-grade encrypted storage or audit trail yet — that's future work (`TASK-005`/`TASK-006`). Today it's held locally, off any shared/public repository, deleted after the engagement unless they ask us to retain it for a follow-up. This is a research-stage engagement, not a SaaS product, and should be described as such. |
| "What happens if you shut down or pivot?" | They keep their own data and the findings report regardless of what happens to this project. We commit to deleting our copy on request at any time. |
| "Can we see what you find before it goes anywhere else?" | Yes — the findings report goes to them first and only them; nothing is published or used as a case study without their explicit, separate consent. |

## 7. What to offer in return

- **Free analysis.** No charge, explicitly framed as research, not a paid pilot — matches the
  current milestone (we are not validating willingness to pay yet).
- **Confidential pilot.** A short written data-use agreement / NDA, an anonymization option, and no
  publicity or case-study use without separate, explicit consent.
- **Findings report.** A plain-language write-up of what was found, delivered whether or not any
  finding turns out to be new or material — including a candid "we didn't find anything worth
  acting on" outcome, since that is itself a possible result. The report states evidence level
  honestly (candidate pattern vs. adjusted observational association) and never claims causation.

## 8. Qualification criteria

A prospect qualifies for outreach effort past the first call when **all** of the following hold:

1. The person we're talking to is the actual data owner or can get a yes/no from that person
   directly (not routed through procurement or a multi-week internal review).
2. At least ~12 months of transaction-level history exists in one exportable system (not
   paper/fragmented spreadsheets).
3. They can describe a concrete, recent pain (a specific incident, not just general interest) with
   a rough cost, even if approximate.
4. They are willing in principle to share a historical (non-live) export under a light NDA/data-use
   agreement, with anonymization as a known, acceptable option.
5. Company size is SMB-scale: small enough that one person can say yes without a security
   questionnaire, large enough to plausibly clear the data-volume floor in §2.

## 9. Signals

### Good pilot candidate
- Has a real export-capable system (CRM/ERP/booking software), not paper or scattered spreadsheets.
- Names a specific recent incident and a rough cost, unprompted.
- The decision-maker is directly reachable (founder/owner), not behind procurement.
- Says something like "we've always wondered why X happens" — an existing, self-recognized itch.
- Replies quickly and is willing to start with a small anonymized sample rather than negotiating
  the full dataset upfront.
- Comfortable stripping/pseudonymizing identifiers without treating it as a dealbreaker.
- No hard regulatory blocker (not health/regulated-finance data) or already has a simple way to
  de-identify.

### Bad pilot candidate
- Needs a multi-week legal/security review before even a small sample can move — wrong shape of
  engagement at this stage.
- Can't name any concrete pain, only generic enthusiasm ("sounds cool," "AI is interesting").
- Data is fragmented across many disconnected systems or under ~6 months of history.
- We're talking to someone with no real authority over data sharing or policy change.
- Asks about pricing, contracts, or a product roadmap before any analysis has happened — signals
  they want a vendor relationship now, which is out of scope (§0).
- Wants publicity or a case study before any finding is even produced.
- Sits in a regulatory environment (health, regulated lending/insurance) that would require a
  formal DPA or security audit before any data can move.

## 10. Pipeline target and funnel

**Goal:** 20 prospect targets across the three verticals, sized to plausibly yield 3–5 received
datasets.

| Stage | Assumption (unvalidated — replace with observed rates after the first 20 attempts) | Count |
|---|---|---|
| Prospect targets identified | — | 20 |
| Discovery calls booked | ~60–70% of targets, weighted toward warm intros | 12–14 |
| Verbal "yes, send a sample/export" | ~40–50% of calls, per §8 qualification | 5–7 |
| Datasets actually received | ~60–70% of verbal yeses convert (follow-through drop-off is real) | 3–5 |

Weighting across verticals: travel agencies get priority for outreach volume (existing wedge,
likely warmer network access); recruitment and distribution are run in parallel as a genuine test
of whether the pain pattern generalizes, not as a fallback. Suggested initial split: 8 travel
agencies, 6 recruitment agencies, 6 distributors — adjustable once real response rates are
observed. These conversion numbers are planning assumptions, not measured facts, and should be
corrected in this document once the first wave of outreach produces real data.

## 11. Open strategic questions for Founder Strategy

Recorded as `HANDOFF-022` in `memory/HANDOFFS.md`. Not blocking outreach from starting, but should
be resolved before real data starts arriving:

1. **Vertical scope vs. `TASK-057`.** `TASK-057` and the entire built pipeline (canonical schema,
   synthetic benchmark, outcome contract) are travel-agency-specific. This plan pursues 3
   verticals for data acquisition. Does non-travel data get run through the existing pipeline
   (requiring new canonical-schema/outcome-contract work per vertical before any real discovery
   run), or is it collected now and analyzed manually/exploratorily outside the productized
   pipeline until one vertical is chosen? This changes what "receiving a dataset" actually unlocks.
2. **Outcome definition per vertical.** `OQ-002`/`OQ-004` are already open for the travel-agency
   outcome and materiality threshold. Multiplying verticals multiplies this open question by three
   distinct outcome definitions (contribution margin vs. net fee retained vs. order margin). Should
   Product predefine an outcome template per vertical before outreach, or should Customer Discovery
   gather data first and resolve outcome definition per prospect afterward?
3. **Positioning framing.** Should outreach explicitly mention a possible future product/pilot
   pricing at all (even softly), or stay strictly "independent research, no product" as drafted in
   §3? This affects both the data-use agreement wording and the company narrative used later for
   `TASK-048`/fundraising materials.
4. **Sequencing priority.** Should travel agencies remain the clear #1 priority (only vertical the
   pipeline actually supports today) with recruitment/distribution treated as secondary
   validation of generality, or should all three be run at genuinely equal priority as drafted in
   §10?
