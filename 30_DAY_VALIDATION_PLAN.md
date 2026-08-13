# 30-Day Validation Plan

**Owner:** FOUNDER_STRATEGY
**Window:** 2026-08-13 → 2026-09-12
**Status of the thesis at day 0:** Unproven. Repository and agent roles exist; the discovery+validation mechanism has not passed its own blind test even on synthetic data with known ground truth; zero real customer engagement exists (`HANDOFF-014`, resolved 2026-08-13).

## Governing principle

This plan is not sequenced to produce a demo. It is sequenced to kill the two cheapest, most decision-relevant unknowns first:

1. **Does discovery + validation actually recover real, non-obvious, economically material patterns — or only noise and confounding?** This is fully testable right now, at zero customer cost, because the synthetic benchmark has known ground truth (`SIMULATION_REPORT.md`, `docs/validation_contract.md`).
2. **Will any real company give us their data?** This is fully testable right now, at near-zero engineering cost, through direct outreach (`TASK-057`).

Both run in parallel starting day 1. Neither is allowed to block the other. Everything downstream of these two answers — UI polish, policy backtesting, pricing mechanics, fundraising collateral — is explicitly de-prioritized for this window.

Per `agents/FOUNDER_STRATEGY.md`, this plan does not make technical, statistical, or UX decisions. Each track states an owner, an objective, and a measurable output; the owning specialist role decides methodology.

---

## Track 1 — Engineering

Real bottleneck at day 0: `HANDOFF-001` (Architect → Data Engineer, the ingestion contract for `TASK-005`) has been open, unresolved, and unpicked since the repository's first day — while dozens of other cross-role handoffs on the analytics side were resolved in parallel. The product currently has **no working path to accept any uploaded file**, synthetic or real. This track exists to close that gap before it becomes the excuse for why a secured customer (Track 3) has nowhere to send data.

### Week 1 (Aug 13–19)
- **Objectives:** Resolve `HANDOFF-001` (ingestion contract). Deliver `HANDOFF-010` item 1 (per-pattern realized effect sizes in hidden ground truth) so `TASK-003` can close and `TASK-022`/`TASK-028` unblock.
- **Measurable outputs:** `TASK-005` = `DONE`; `TASK-003` = `DONE` (no longer `IN_REVIEW`).
- **Dependencies:** None external — both items are fully owned inside the team (Data Engineer, with Architect/Statistics review).
- **Failure condition:** If `HANDOFF-001` is still `OPEN` at the end of week 1, treat it as an execution-capacity problem, not a sequencing problem — it had no dependency blocking it for the entire prior history of this repository. Escalate directly rather than re-queue it for week 2.

### Week 2 (Aug 20–26)
- **Objectives:** Implement `TASK-006` (upload API), start `TASK-007`–`TASK-009` (profiler, feature-timing classification, data-quality report). Architect resolves `HANDOFF-008` (finding-model field design) so `TASK-024` can be scoped correctly the first time.
- **Measurable outputs:** A CSV can be uploaded through the real API and produce a Data Quality Report end to end on the synthetic fixture.
- **Dependencies:** `TASK-005` (week 1).
- **Failure condition:** If `TASK-006` has not started by day 14 given its sole blocker cleared a week earlier, that repeats the week-1 failure pattern and should trigger the same escalation, not a second grace period.

### Week 3 (Aug 27–Sep 2)
- **Objectives:** Begin `TASK-024`/`TASK-025` (finding persistence model + API) using the evidence classification and economic-impact numbers Track 2 produces this week. If Track 3 has converted a real customer by now, start `TASK-010`/`TASK-011` production canonicalization and prep `TASK-037`.
- **Measurable outputs:** `TASK-024` schema locked; `TASK-025` serves at least one real (non-fixture) validated finding record, even if `evidence_level = descriptive_observation`.
- **Dependencies:** Track 2's `HANDOFF-016` resolution.
- **Failure condition:** If zero candidates survive validation at all (see Track 2), engineering still builds the pipe — but Founder must treat that as the headline result of the month, not a data problem to route around.

### Week 4 (Sep 3–12)
- **Objectives:** If a real dataset exists: run `TASK-038`–`TASK-041` (ingest → data quality → discovery → validation) against it. If not: finish `TASK-026`/`TASK-027` (findings UI) so the synthetic result is presentable.
- **Measurable outputs:** Either a real-data validation report draft, or a working finding-detail screen against the synthetic finding.
- **Dependencies:** Everything upstream; Track 3 conversion status.
- **Failure condition:** Building UI polish in week 4 while `HANDOFF-001`-class items from week 1–2 are still open — that would mean the team optimized for a demo over the actual unknowns this plan targets.

---

## Track 2 — Synthetic validation

This is the cheapest possible test of the core hypothesis: ground truth is known, so a wrong or overconfident finding is caught immediately, with no customer relationship at risk.

### Week 1 (Aug 13–19)
- **Objectives:** Statistics begins `HANDOFF-016` — apply `TASK-019`/`TASK-020`/`TASK-021` to the 15 persisted `TASK-015` candidates (uncertainty, evidence classification, adjusted effects).
- **Measurable outputs:** A provisional evidence-level assignment for all 15 candidates.
- **Dependencies:** `TASK-015` (done), `TASK-018` (done). `TASK-022` (confounding-trap check) specifically also needs `HANDOFF-010` item 1 from Track 1 — if that slips, `TASK-022` slips with it into week 2.
- **Failure condition:** None yet — this is discovery work. The real failure signal arrives once results are in (below).

### Week 2 (Aug 20–26)
- **Objectives:** Complete `HANDOFF-016` (final evidence classification), `TASK-023` (economic impact) for surviving candidates, and run a genuine blind discovery test — `TASK-017` — using the `ADR-008` allowlist-workspace protocol as a separate actor, not the informal full-checkout run `TASK-015` used.
- **Measurable outputs:** `TASK-017` formally satisfied; economic-impact figures for every surviving candidate.
- **Dependencies:** `ADR-008` protocol (already implemented), `HANDOFF-016`.
- **Failure condition (hard):** If the properly blind run under `ADR-008` recovers materially different or fewer candidates than the informal week-1 run, neither run is trustworthy until Statistics/ML Discovery reconcile why — do not carry either into `TASK-028` unresolved.

### Week 3 (Aug 27–Sep 2)
- **Objectives:** `TASK-028` (ground-truth evaluator — precision, recall, Top-K/economic-weighted recall, confounder-rejection rate, direction accuracy, impact error, leakage violations) and `TASK-029` (benchmark report v1) → `MILESTONE-M1`.
- **Measurable outputs:** Benchmark report v1 — the actual, falsifiable answer to "can this system find real planted patterns without cheating, and reject the fake ones."
- **Dependencies:** `TASK-022`/`TASK-023` complete, blind `TASK-017` run complete.
- **Failure condition (hard, thesis-relevant):** Known high-impact planted patterns are not recovered near the top of the ranking, or known confounding traps are not rejected/downgraded, or any leakage violation is found. Any of these is a methodology failure discovered before a single real customer relationship is spent on it — that is the point of this track.

### Week 4 (Sep 3–12)
- **Objectives:** Close out any `MILESTONE-M1` gaps identified in week 3; document the single largest methodological weakness honestly, as `TASK-029` requires — do not soften it for narrative reasons.
- **Measurable outputs:** `MILESTONE-M1` reached, or an explicit, dated statement of why it wasn't and what specifically failed.
- **Dependencies:** Week 3 report.
- **Failure condition:** Same hard failure condition as week 3, now with a remediation attempt behind it — see kill/pivot criteria below.

---

## Track 3 — Customer / data acquisition

Zero engineering dependency. Should start on day 1, in parallel with Track 1/2, not after them.

### Week 1 (Aug 13–19)
- **Objectives:** Execute `TASK-057` (secure first real pilot customer) — founder-led outreach and buyer mapping in the travel-agency wedge.
- **Measurable outputs:** A qualified prospect list, an outreach log, and at least 3–5 discovery conversations booked.
- **Dependencies:** None.
- **Failure condition:** Fewer than 3 conversations booked by end of week 1 — reassess channel and targeting immediately; do not wait for day 30 to notice a dead channel.

### Week 2 (Aug 20–26)
- **Objectives:** Convert week-1 conversations into at least one LOI or equivalent committed pilot with a defined dataset-access plan.
- **Measurable outputs:** `TASK-057` = `DONE`, or a documented, specific reason it is not, with a revised plan.
- **Dependencies:** Week 1 pipeline.
- **Failure condition:** Zero LOIs after roughly two weeks of real outreach volume — this is a hard mid-plan checkpoint, not something to fold silently into the day-30 review. Escalate to a Founder-level ICP/pitch review immediately.

### Week 3 (Aug 27–Sep 2)
- **Objectives:** If `TASK-057` closed: begin `TASK-037` (security review) and prep `TASK-038` (ingestion) for the real dataset. If not: Founder-level decision on whether to continue the current channel, change buyer persona, or widen past a travel-agency-only wedge while staying inside the "historical decisions + downstream outcomes" thesis.
- **Measurable outputs:** Either real-dataset ingestion started, or a dated, explicit pivot decision on acquisition channel/ICP recorded in `DECISIONS.md`.
- **Dependencies:** Week 1–2 pipeline.
- **Failure condition:** Continuing an unproductive channel into week 4 without a documented decision either way.

### Week 4 (Sep 3–12)
- **Objectives:** If a real validated finding exists by now: run `TASK-042` (customer findings review) against `docs/customer_findings_review_protocol.md`. If `TASK-057` never converted: treat that as the headline output of this cycle.
- **Measurable outputs:** Either the first customer response captured (known/new, actionable, trust objections), or a clear, evidence-based statement that first-pilot acquisition did not work in 30 days under the tested approach.
- **Dependencies:** Track 1/2 output, Track 3 weeks 1–3.
- **Failure condition:** `MILESTONE-M3` will very likely not be reached inside 30 days even in the best case — that is expected, not a failure by itself. The failure condition is entering week 5 with no dataset access plan and no documented reason why.

---

## Track 4 — Accelerator / fundraising readiness

Explicitly bounded per `TASKS.md`: "Fundraising must not block product validation." No task in this track may consume time from Tracks 1–3.

### Week 1 (Aug 13–19)
- **Objectives:** Lock `TASK-048` (one-liner, already `READY`) as-is or with minor wording confirmation. First draft of `TASK-049` (founder story).
- **Measurable outputs:** One-liner confirmed; founder-story draft exists.
- **Dependencies:** None.
- **Failure condition:** None material — this is low-cost background work.

### Week 2–3
- **Objectives:** No new fundraising tasks initiated. `TASK-050`/`TASK-051`/`TASK-052` correctly stay `BLOCKED` on real traction and real evidence — do not start them early to have something to show.
- **Measurable outputs:** None expected; absence of premature work is the success condition here.
- **Failure condition:** Any attempt to draft `TASK-050`/`TASK-051` before `MILESTONE-M1` or real customer traction exists — that would be fundraising narrative getting ahead of evidence, which `agents/FOUNDER_STRATEGY.md` and `TASKS.md` both explicitly prohibit.

### Week 4 (Sep 3–12)
- **Objectives:** Day-30 internal retro only — not a YC application, not `TASK-050`. Compile what actually happened: datasets touched, evidence levels reached, customer conversations, LOIs, and the kill/pivot outcome below.
- **Measurable outputs:** An honest internal snapshot feeding the next 30-day cycle.
- **Dependencies:** All other tracks' week-4 output.
- **Failure condition:** The retro overstates synthetic-only results as traction. Synthetic benchmark performance is a methodology signal, not customer evidence, and must not be presented as the latter (see `memory/FINDINGS.md`).

---

## Kill / pivot criteria (day-30 hard gates)

**GO — continue current thesis and build, unchanged** if both hold:
- `MILESTONE-M1` substantively reached: discovery + validation recovers a meaningful share of known planted harmful patterns, correctly rejects/downgrades known confounding traps, and shows no leakage — per Statistics' own preregistered acceptance test (`docs/validation_contract.md` §10). Statistics owns this verdict.
- At least one real customer has committed to a pilot (`TASK-057` done), or a credible near-term pipeline exists (≥2 prospects in late-stage conversation).

**CONTINUE WITH A TARGETED CHANGE** if exactly one holds:
- Mechanism passes, zero customer traction after real effort → this is a GTM/ICP pivot (channel, buyer persona, or widening past travel agencies), not a thesis kill. Engineering and validation continue unchanged; acquisition strategy is what gets re-examined.
- Customer secured, mechanism fails its own blind test → do **not** ingest real customer data (`TASK-038`) until the identified failure mode is fixed and re-tested on synthetic data. Communicate the delay to the prospect rather than running a known-broken engine on their real numbers.

**KILL / PIVOT THE CORE THESIS** if:
- The mechanism fails its blind synthetic test in week 3, and after one dedicated remediation attempt in week 4 it still fails. If discovery + validation cannot reliably separate true planted patterns from noise and confounding when ground truth is fully known and the data is clean, the core technical bet does not work at the current methodology or data richness — independent of any customer question. This is Statistics'/ML Discovery's technical call to confirm; Founder acts on it.

**Not resolvable within this 30-day window, flagged for the next cycle:** the thesis-level kill signal already recorded in `memory/CURRENT_STATE.md` — "across multiple suitable datasets, the system repeatedly produces only obvious, unstable, economically immaterial, or non-actionable relationships" — requires multiple real, validated, customer-reviewed findings. Realistically that evidence does not exist by day 30 even in the best case. This plan's job is to get the inputs to that test moving (Tracks 2 and 3), not to reach the verdict itself.

Example, as requested: if after 3 real datasets the system finds no non-obvious actionable pattern, the thesis is reassessed — that test cannot start until at least one real dataset is ingested, which this plan treats as a stretch goal for week 4, not a guaranteed outcome.

---

## Top 5 assumptions (updated 2026-08-13)

1. Discovery + validation can recover real, non-obvious, economically material patterns above noise and confounding — still unproven even against fully known synthetic ground truth (`MILESTONE-M1` not yet reached; `HANDOFF-016` pending).
2. A real travel-agency (or adjacent) business will grant data access and engagement to a pre-revenue, unproven tool — zero evidence either way; `TASK-057` starts from nothing.
3. A real customer export will contain enough reliable decision-time and outcome fields to support analysis — unvalidated; no real dataset has ever been profiled by this pipeline (`PROJECT_CONTEXT.md`).
4. A validated finding, once shown, will be perceived by the customer as new and actionable rather than "we already knew that" — untested; `MILESTONE-M3` not reached.
5. The customer will change behavior or pay for continued use, beyond stating interest — untested; `TASK-046` not started.

## Top 5 risks (updated 2026-08-13)

1. **Statistical mechanism risk.** The cheapest, fully controllable test of the core hypothesis (blind recovery on synthetic ground truth) has not concluded. Highest priority because it is cheap, internal, and gates whether spending a real customer relationship is responsible at all.
2. **Zero-to-one acquisition risk.** `TASK-057` has no execution history — "founder-led sales" is unstarted work, asking a company to share sensitive financial/booking data with a pre-product startup.
3. **Engineering execution-stall risk.** `HANDOFF-001` sat open, unpicked, for the entire prior history of this repository while the analytics track moved fast in parallel — an observed pattern, not a hypothetical one. If it recurs, the product will have no way to receive a real customer's file even after a customer is secured.
4. **Evidence-language / overclaiming risk.** The differentiation depends entirely on evidence-bounded honesty (`ADR-005`, `ADR-007`). One overclaim to the first, hardest-won customer — causal language below the assigned evidence level, or promised `HIGH_CONFIDENCE` readiness that is structurally unreachable pre-backtest — would break trust the product cannot yet afford to lose. Enforcement at the API edge (`HANDOFF-012`) is still open.
5. **Premature scope-diffusion risk.** Several open handoffs (`HANDOFF-008`, `HANDOFF-009`, `HANDOFF-012`, `HANDOFF-013`) sit in downstream phases — policy backtesting, UI polish, pricing language — while the two upstream questions (does it work, does anyone want it) remain open. Work that reads as progress but doesn't reduce either core uncertainty should wait.

## Next evidence required

1. `TASK-029` Benchmark report v1 — precision, recall, confounder-rejection rate, and leakage results on known synthetic ground truth (Statistics, ML Discovery).
2. Outcome of the first real prospect conversations — interested / not interested, and the specific data-sharing objections raised (Customer Discovery).
3. `HANDOFF-001` resolution — an actual ingestion contract, closing the longest-standing unresolved item in the project (Data Engineer, Architect).
4. At least one LOI or equivalent committed pilot with a named dataset-access plan — the `TASK-057` done condition (Customer Discovery, Founder Strategy).
5. If a real dataset arrives within the window: a customer-specific Data Quality Report (`TASK-039`) — the first real, not synthetic, signal on assumption 3 above (Data Engineer).
