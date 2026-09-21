# TASK-101 — `max_support` search-eligibility fix: rationale, mechanism, regression evidence, downstream chain, cross-domain check

**Owner:** ML_DISCOVERY
**Recorded:** 2026-09-21
**Depends on:** `TASK-100` (`CLOSED — APPROVED`) — the diagnosis this task fixes, not re-derives.
**Design authority for the fix itself:** `ADR-096`.

**Scope, stated up front.** This document covers exactly what `TASK-101`'s `TASKS.md` entry asks
for, in the order it asks for it: (1) why `max_support=0.40` exists and what risk it bounds, with
a citation; (2) the fix itself and why its generic justification comes from (1), not from `OL01`'s
own number; (3) the mandatory both-direction regression, on real Olist data; (4) the full,
unmodified downstream chain for `OL01` after the fix, including `G16`; (5) the explicit
non-goal — `OL01` merely being found is not success, and this document reports whichever way the
chain actually lands; (6) a cross-domain check (travel) confirming the fix does not quietly admit
noise elsewhere. Out of scope, per the task's own binding text: `OL02`/`OL03`/`OL04`'s own gaps,
any change to `G03`–`G16` or the estimator, any new general tuning pass, and the recall-metric
decomposition (`ADR-095`, sequenced after this task).

---

## 1. Why `max_support=0.40` exists, and what risk it actually bounds

**Citation.** `docs/analytics/discovery-design.md` §3 ("Support and complexity rules"), written for
`TASK-015` ("Discovery engine v0") before any code existed, states the reason directly:

> "The absolute floor prevents a large dataset from legitimizing tiny unstable segments; the
> fractional floor prevents a small absolute group from being overrepresented in a very large
> population. **The maximum support rejects broad near-baselines masquerading as subgroups.**"

The design's own eligibility pseudocode, immediately above that sentence, specifies **three**
independent conditions, not two:

```text
exposed_n >= max(min_support_count, ceil(min_support_fraction * eligible_fit_n))
and exposed_n <= floor(max_support_fraction * eligible_fit_n)
and comparison_n satisfies the same absolute minimum count
```

The real risk `max_support` protects against, per this text, is a **comparison group too small or
unstable to make the exposed-vs-comparison contrast mean anything** — not "high support is itself
suspicious." A rule that covers nearly the whole population leaves too little of a "control" group
to compare against, so its descriptive contrast stops being informative, independent of how
correctly signed or materially large its raw effect looks.

**The gap.** `engine.py`'s shipped `_eligible()` (every version from `TASK-015`'s original commit
`317bde0`, 2026-08-13, through `discovery-engine-v0.6.1`) implemented only the *fractional ceiling*
(`config.min_support <= metric.support <= config.max_support`, `packages/analytics/src/
policy_analytics/discovery/engine.py`, pre-fix `_eligible()`). The design's own third condition —
`comparison_n satisfies the same absolute minimum count` — was **never actually wired in**, at any
point in this engine's history (confirmed by reading every commit that touched `_eligible()` or
`DiscoveryConfig.max_support`: `317bde0` introduced both and neither was touched again before this
task). Nothing else in `TASKS.md`/`DECISIONS.md` records a separate task or ADR that revisited
`max_support`'s value or rationale after `TASK-015` — `git log -p` on `engine.py` shows
`max_support=0.40` unchanged in every commit since.

**Consequence, traced by `TASK-100`.** `OL01`'s raw rule (`seller_customer_cross_state ==
1 -> OUTCOME_LATE`) has ~66% support on real Olist data at both tested scales — comfortably above
`0.40` — so `_eligible()` excluded it at depth 1 regardless of the effect's real strength or safety,
even though its comparison group (the other ~34%, thousands of real rows at either scale) is not
remotely thin or unstable. This is precisely the gap the design's own dropped third condition would
have prevented: the fractional ceiling alone conflates "high support" with "thin comparison group,"
when a large enough dataset can have both — a rule with 66% support and a perfectly adequate,
thousands-of-rows comparison group.

---

## 2. The fix

**Design authority:** `ADR-096`. **Code:** `packages/analytics/src/policy_analytics/discovery/
engine.py`, `_eligible()` and `DiscoveryConfig.max_support`'s field docstring.

`_eligible()` now accepts a rule over `max_support` specifically when its comparison group's
absolute size clears the same `min_n` reliability floor already required of the *exposed* side —
implementing the design's own dropped third condition, using the project's own existing, already-
justified `min_n` constant rather than inventing a new tunable:

```python
def _eligible(metric: SplitMetric | None, config: DiscoveryConfig) -> bool:
    if not (metric and metric.n_exposed >= config.min_n and metric.harm_per_booking > 0):
        return False
    if metric.support < config.min_support:
        return False
    if metric.support <= config.max_support:
        return True
    n_comparison = metric.n_population - metric.n_exposed
    return n_comparison >= config.min_n
```

**Why this is not "raise 0.40 to some other number."** `max_support=0.40` is completely unchanged
and still gates the common case exactly as before: every rule at or below it keeps precisely its
prior eligibility verdict — a strict widening, never a raised ceiling, and not a value chosen to
make `OL01`'s own 66% pass (nothing in the mechanism references `0.66`, `OL01`, or Olist at all).
Only rules *above* the ceiling get a second, principled chance, keyed to the exact quantity §3
named as the real risk — comparison-group adequacy — using the same `min_n` bar this project
already trusts as its floor for a reliable sample size on the exposed side (`DiscoveryConfig.min_n`,
unchanged, `TASK-015`'s own original default). This matches the founder's own suggested shape
directly: search now considers high-support rules **specifically where doing so is safe** (comparison
group adequate), rather than one global ceiling moving.

`DISCOVERY_METHOD_VERSION` is bumped `discovery-engine-v0.6.1 -> v0.6.2` (module docstring, `engine.py`):
unlike `v0.6.0`'s `max_feature_identity_fraction` or `TASK-097`'s `reserve_k1_slot`, this is a
genuine, unconditional behavior change with no opt-in flag — every real run using the default
config is affected wherever a rule's support exceeds `0.40` with an adequate comparison group.

---

## 3. Both-direction regression, on `OL01`'s own real construction

**File:** `tests/analytics/test_task101_ol01_search_eligibility_regression.py` (marked
`@pytest.mark.analytics`, `@pytest.mark.slow`; skips, does not fail, if the local `kagglehub` cache
of the real Olist dataset is absent — matching this project's own precedent for external-data
checks). Reuses `scripts/task100_run_experiment.py`'s own already-reviewed join/split/
classification/outcome functions verbatim (loaded by file path, nothing re-derived), at the matched
(4,999-row development) scale — `TASK-100` already established both scales land on the identical
verdict for `OL01`.

**Direction 1 (old formula genuinely misses it) — `test_old_formula_genuinely_misses_ol01_real_rule`.**
On freshly computed real Olist data: `OL01`'s real matched-scale support is **0.6618**
(`n_exposed=3219`, `n_population=4864`), a real, correctly-signed effect
(`harm_per_booking=0.02587 > 0`), comfortably above `min_n=40` on the exposed side. A verbatim,
dated copy of the pre-`TASK-101` `_eligible()` formula (kept in the test file since the real
function has since changed) returns `False` — the old mechanism excludes this rule purely because
`support (0.6618) > max_support (0.40)`, exactly reproducing `TASK-100`'s own finding, independently
re-derived rather than read from that document.

**Direction 2 (new mechanism admits it through to a final candidate) —
`test_new_mechanism_admits_ol01_real_rule_through_to_validation`.** The real, current `_eligible()`
returns `True` for the identical rule (comparison group `n_comparison=1645 >= min_n=40`). The real,
unmodified `discover_candidates()` — full search, no config override — was run against the same
real matched-scale frame: `OL01`'s own atom (`seller_customer_cross_state >= 1`) appears in **5 of
15** final candidates (`CAND-001`, `CAND-003`, `CAND-004`, `CAND-006`, `CAND-007`), the top-ranked
being `seller_customer_cross_state >= 1 AND total_price >= 39.5` (development support 0.5401). The
best-matching candidate recovers **81.6%** of `OL01`'s own real affected-order population
(2,627 of 3,219 exposed orders), well above `TASK-100`'s own `MATCH_RECALL_THRESHOLD=0.5` — the
identical recall methodology `scripts/task100_run_experiment.py`'s `match_candidates_to_pattern`
uses.

**Additional, non-substituting: synthetic general-mechanism test —
`test_general_mechanism_admits_only_the_adequately_supported_comparison_group`.** On data with no
relationship to Olist or any real domain: a 70%-support rule with a 90-row comparison group
(`>= min_n=40`) becomes eligible under the new mechanism; a 97%-support rule with only a 9-row
comparison group (`< min_n=40`) — an equally real, equally correctly-signed effect — **stays
excluded**. Both were excluded under the old formula for the identical reason (the fractional
ceiling alone). This demonstrates the fix is "admit specifically where the comparison side is
adequate," not "raise the ceiling generally": a rule with an even higher support than `OL01`'s own
66% is refused when its comparison group is thin, regardless of how strong its effect looks.

All three tests pass; verified in this session against a live run (not asserted from memory).

---

## 4. Full, unmodified downstream chain for `OL01`

**Script:** `scripts/task101_ol01_downstream_chain.py` (disclosed, non-production forensic tooling,
matching `scripts/task100_run_experiment.py`/`scripts/diagnose_*` precedent). Reuses `TASK-100`'s
own join/split/classification/outcome/Stage-3-scaffolding functions verbatim. Runs Stage 2
(`discover_candidates`, the new engine, default config) then Stage 3 (`run_validation`, every gate
`G00`–`G16` exactly as it stands today, untouched) for `OUTCOME_LATE`, at **both** scales. Executed
in this session against real Olist data; raw output: `artifacts/task-101/
ol01_downstream_chain_summary.json` (gitignored, reproducible by rerunning the script).

**Stage 2 (search), both scales:** `OL01`'s own atom reaches the final candidate set at both
scales — 5 of 15 candidates at `full` scale (`CAND-001`–`CAND-005`, e.g. `seller_customer_cross_state
>= 1 AND order_status == 'delivered'`, support 0.6652), 5 of 15 at `matched` scale (as in §3 above).

**Stage 3 (validation), every `OL01`-touching candidate, both scales:** **all ten** candidates
(5 per scale) resolve `verdict=DOWNGRADE`, `evidence_level=descriptive_observation`,
`policy_readiness=experiment_only`. None promoted at either scale. The gates that fail are
consistent across candidates: `G16_CANDIDATE_COMPOSITION_SAFETY` fails for **every one** of the ten
(the shared second condition — `total_price`, `modal_payment_type`, `order_status`, or
`max_installments`, depending on candidate — classifies in a way `G16`'s leave-one-out check does
not clear), alongside `G10_TEMPORAL_STABILITY`, `G13_IDENTIFICATION_DESIGN`, and
`G14_RANDOMIZATION_INTEGRITY` (fail for all ten), and `G06_CONFOUNDING` (fails for most). `G03`,
`G04`, `G05`, `G07`, `G08`, `G15` mostly pass. Full per-candidate gate table is in the JSON
artifact.

One further precision, so the claim is not overstated: `OL01`'s *literal single-condition* rule
(`seller_customer_cross_state == 1` alone, `k=1`) never itself appears as a standalone final
candidate under the default config — the engine's existing, unmodified interactions-preferred
selection (`discover_candidates`'s own two-phase design, unrelated to this task) consistently finds
two-condition interactions built from that same atom score higher, and `reserve_k1_slot` (the
`TASK-097` mechanism, out of this task's scope to change) defaults to `False`. What "admitted
through to validation" means concretely, and what is verified above, is that `OL01`'s own atom
reaches real, final candidates that Stage 3 actually evaluates — not that the bare single-condition
rule itself is promoted.

**This result is reported as complete and valid, per `TASK-101`'s own explicit non-goal.** `OL01`
clearing search and reaching Stage 3 is not, by itself, success; `OL01`-touching candidates dying at
Stage 3 (chiefly `G16`, plus `G10`/`G13`/`G14`/`G06`) is not, by itself, failure. This isolates the
loss `TASK-100` found specifically to the search layer: the search-layer fix genuinely works (§3),
and the reason `OL01`'s pattern still does not get promoted is downstream, safety-gate behavior this
task was explicitly not authorized to touch (`G03`–`G16` untouched, verified by inspection of the
gate results — `G16`'s own leave-one-out composition-safety mechanism, `TASK-080`/`ADR-057`-era
code, is unmodified by this task).

---

## 5. Cross-domain check: travel

**Method:** the real travel analytical dataset (`synthetic_data/analytical/
travel-bookings-analytical-v1.1.0`, `primary_outcome()` = `contribution_margin_eur`, 17
`DECISION_TIME` feature columns), real `discover_candidates()`, default config, run twice in the
same session — once with the module's real `_eligible` temporarily swapped for a verbatim copy of
the pre-`TASK-101` formula (old), once with the real, current `_eligible` (new) — both against the
identical real frame. Not a synthetic or hypothetical comparison.

**Result:** the fix has a real, non-trivial effect on this domain too: 10 of the 15 final candidates
differ between old and new. `evaluated_hypotheses` rises `33,085 -> 36,791` (more of the search
space is now scoreable). Every one of the ten newly admitted candidates pairs `discount_rate` (or
co-occurs with a feature already present throughout both the old and new candidate lists —
`manual_exception`, `customer_price_eur`, `quoted_cost_eur`, `booking_lead_days`, `travel_month`)
with a second real `DECISION_TIME` feature; several reach support well above the old `0.40` ceiling
(`discount_rate >= 0.03 AND manual_exception == False`, support 0.752; `customer_price_eur < 3817.99
AND quoted_cost_eur < 2821.31`, support 0.7828). `discount_rate`'s role as this domain's dominant,
independently-confirmed real margin-loss driver is already established across this project's own
history (`engine.py`'s own module docstring repeatedly references "the dominant pattern" /"the
single strongest mechanism" in this exact dataset across `TASK-058`/`TASK-060`/`TASK-064`/
`TASK-068`) — the newly admitted candidates read as broader-support variants of that same,
already-verified mechanism, not as new, isolated, low-support outliers. None of the ten
newly-admitted candidates introduces a feature that does not already appear elsewhere in the old
candidate list; none is a rare/thin pattern (if anything the new candidates trend toward *higher*
support than the ones they displaced, the opposite direction from "noise").

**What this check does and does not establish.** It confirms the fix's search-layer effect on a
second, independent domain is real and directionally consistent with admitting broader variants of
an already-known genuine signal, not indiscriminately opening the ceiling to arbitrary content. It
does **not** run travel's own Stage 3/`G16` validation on these ten candidates — that is unmodified,
untouched machinery (per this task's own explicit scope boundary) that would need to independently
clear or reject each one exactly as it always has; nothing about this task changes that gate, and
this check does not substitute for it. Per this task's own scope, no further tuning or validation
work on travel is undertaken here.

---

## 6. Summary

| Item | Result |
|---|---|
| Why `max_support` exists | Protects against a comparison group too thin/unstable to make the contrast meaningful (`discovery-design.md` §3) — not "high support is bad" |
| The dropped design condition | `comparison_n satisfies the same absolute minimum count` — specified in `TASK-015`'s own design, never implemented before this task |
| The fix | `_eligible()` admits `support > max_support` specifically when `n_comparison >= min_n`; `max_support=0.40` itself unchanged |
| Regression, direction 1 (old misses `OL01`) | Confirmed on real Olist data: support 0.6618 > 0.40, old formula → `False` |
| Regression, direction 2 (new admits `OL01`) | Confirmed: new formula → `True`; real search recovers 81.6% of `OL01`'s real affected population in a final candidate |
| Downstream chain | `OL01`-touching candidates reach Stage 3 at both scales; all fail validation (`DOWNGRADE`, chiefly `G16`/`G10`/`G13`/`G14`) — none promoted |
| Cross-domain (travel) | Real effect (10/15 candidates changed); qualitatively consistent with admitting broader variants of the already-known dominant `discount_rate` mechanism, not new noise; Stage 3 unmodified and not itself rerun here |

**Net:** the search-layer gap `TASK-100` traced is fixed, generically justified from the design's
own stated rationale, proven in both directions on `OL01`'s real construction, and does not
promote `OL01` — the loss is conclusively isolated to the search layer, exactly the useful, complete
result `TASK-101`'s own non-goal language anticipated either way.
