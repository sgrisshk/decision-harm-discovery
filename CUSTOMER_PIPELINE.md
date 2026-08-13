# Customer / Data-Partner Pipeline Log

**Owner:** CUSTOMER_DISCOVERY
**Relates to:** `TASK-057`, `CUSTOMER_DATA_ACQUISITION_PLAN.md`
**Last updated:** 2026-08-13
**Status: 0 of 3 required serious conversations obtained. 0 real prospects contacted.**

## Rule for this file

Only log a row here after a real exchange with a real person at a real company actually happened.
No row may be created, and no field filled in, from an assumed or typical answer. If a prospect
has been messaged but has not replied, they get a row with `Status: CONTACTED, no reply yet` and
every other field left as `—` — not a guess. This file is evidence, not a forecast; see
`agents/CUSTOMER_DISCOVERY.md` on treating polite interest as validation.

## Approved outreach offer (verbatim, use for all first-touch contact)

> "We are testing a system that analyzes historical business decisions and downstream outcomes to
> find non-obvious patterns associated with economic loss. For an early pilot we need anonymized
> historical transactional data and will return a confidential findings report."

Do not describe a finished platform. Do not say "proves," "causes," or "guarantees." At most:
candidate patterns, at most adjusted observational association — see `DECISIONS.md` evidence-level
ADR. This matches the constraint already fixed in `CUSTOMER_DATA_ACQUISITION_PLAN.md` §0.

## Per-prospect record template

Copy this block per prospect once a real conversation happens; do not pre-fill.

```md
### P-<number> — <company name> (<vertical>)

- **Source:** <warm intro / cold email / LinkedIn / other, and who/what>
- **First contact date:** YYYY-MM-DD
- **Status:** CONTACTED, no reply yet | CALL SCHEDULED | CALL DONE | SAMPLE PROVIDED | SCHEMA SHOWN | DECLINED | GHOSTED
- **Transaction volume:** <rows/month or /year, as stated by prospect — not estimated by us>
- **Months of history available:** <as stated>
- **Available decision-time fields:** <what they described, e.g. agent/manager, discount, channel, terms>
- **Available outcome fields:** <e.g. cancellation, refund, margin, default, churn>
- **Ability to anonymize:** <yes/no/unsure, and what they said about how>
- **Person who controls the data:** <name/role, and whether this is the person we're talking to>
- **Willingness to provide a sample:** <yes/no/conditional, and the condition>
- **Security objections raised:** <verbatim or close paraphrase, not resolved/argued in the log>
- **Timeframe:** <when they said they could realistically act>
- **Notes:** <anything that doesn't fit above; do not editorialize interest level — record what was said, not what it seemed to mean>
```

## Log

_No entries yet. Zero real prospects have been contacted as of 2026-08-13._

## Funnel status against `CUSTOMER_DATA_ACQUISITION_PLAN.md` §10 target

| Stage | Target | Actual |
|---|---|---|
| Prospect targets identified (named) | 20 | 0 |
| Discovery calls booked | 12–14 | 0 |
| Serious conversations (this task's bar) | ≥3 | 0 |
| Verbal yes to sample/export | 5–7 | 0 |
| Datasets received | 3–5 | 0 |

## Why this is still at zero

Customer Discovery, running as an AI agent in this repository, has no outbound communication
channel available in this session — no connected email or calling tool, and no named contact list
of real companies has been supplied or researched yet. Getting real replies also inherently takes
real-world days regardless of tooling; a single agent turn cannot produce a completed multi-day
back-and-forth. This is recorded as `HANDOFF-023` to Founder Strategy rather than papered over with
invented conversations.
