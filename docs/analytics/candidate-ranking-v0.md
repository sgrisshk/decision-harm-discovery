# Candidate ranking v0 methodology

**Owner:** ML Discovery · **Task:** TASK-016 · **Ranking method version:**
`candidate-ranking-v0.1.0`

## Scope and evidence boundary

This module orders an already-frozen, `status=PERSISTED` candidate set for review priority. It
does not select, drop, add, or edit a candidate, does not compute an evidence level or policy
readiness (that is `TASK-018`/`TASK-019`, owned by Statistics), and never opens hidden ground
truth. Reordering the review queue does not change which candidates were reported, their
conditions, or their own committed metrics.

## Why this exists

`docs/analytics/discovery-engine-v0.md` fixed the search's own preliminary order as a single
number — development historical exposure with a mild complexity penalty — used only to decide
which candidates survive the beam search, and said explicitly: *"Full multi-factor ranking is
TASK-016."* `policy_analytics.outcomes.aggregation`'s module docstring restates the same boundary:
*"producing the set of candidates is TASK-015; ordering them is TASK-016."* This document and
`packages/analytics/src/policy_analytics/discovery/ranking.py` are that ranking.

## Components

Each candidate gets five components, all in `[0, 1]`, plus a warning penalty:

- **economic_impact** — `abs(economic_exposure)` from the frozen candidate document, min-max
  normalized against the rest of the ranked batch. Trusted as committed, never recomputed.
- **support** — the frozen `support` fraction, min-max normalized against the batch.
- **stability** — the share of *available* later chronological splits (`validation`,
  `future_holdout`) whose recomputed harm direction agrees with the candidate's committed sign.
  Recomputed from the analytical dataset because the frozen blind-agent schema
  (`tools/blind_agent/models.py`, `OUTPUT_SCHEMA_VERSION = "1.1.0"`) carries no per-split
  breakdown. **Missing stability (no later split had any exposure) scores `0.0`, not `1.0` or an
  omitted term** — a candidate this ranking cannot vouch for as stable must not rank as if it were
  stable. `stability_missing` is carried on the output so this is visible, not silent.
- **actionability** — `policy_analytics.discovery.actionability`; `HIGH` (a condition touches a
  directly controllable commercial field) scores `1.0`, `REVIEW_REQUIRED` scores `0.35` — low
  enough to matter, high enough that a genuinely actionable-after-review candidate is not treated
  as nearly worthless. Shared with `discovery.engine`'s own search-time label so the two can never
  silently diverge.
- **novelty** — `1 - ` the largest pairwise Jaccard overlap of a candidate's development-split
  exposed row set against every other candidate in the same ranked batch. A candidate that mostly
  re-slices another candidate's population is scored low here even when its own economic exposure
  looks large, so the reported set is not dominated by cosmetic variants of one broad effect.
- **warning_penalty** — `0.05` per warning beyond the one standard non-causal boilerplate warning
  every candidate carries, capped at `0.20`.

Economic impact and support are the only unbounded raw magnitudes, so they are the only two
components normalized against the batch; stability, actionability, and novelty are already
meaningful in absolute `[0, 1]` terms and are used as-is. A degenerate batch (every candidate has
the same raw value on a normalized component) scores that component `1.0` for everyone — it
cannot break any tie either way, so it is neutral rather than an arbitrary penalty.

## Composite score and ranking

```text
rank_score = max(0, weighted_sum(components) - warning_penalty)
weighted_sum = 0.35·economic_impact + 0.15·support + 0.20·stability
             + 0.15·actionability   + 0.15·novelty
```

Ties break on `candidate_id`, never on input order — ranking is a pure, deterministic function of
`CandidateSignals` (`policy_analytics.discovery.ranking.rank_candidates`).

## Weight provenance

`DEFAULT_WEIGHTS` are **ML_DISCOVERY-authored v0 defaults**, fixed from ordinary business
reasoning — economic impact and durability (stability) matter most; support, actionability, and
novelty matter but less — before this module was ever run against a specific candidate set. They
were not fit, tuned, or reweighted after looking at any ranking output, benchmark grade, or hidden
ground truth; the module was implemented and this document written without opening
`hidden_ground_truth.json` or `synthetic_benchmark.py`, the same discipline Statistics used for its
confounder set (`validation/apply.py`).

`docs/analytics/discovery-design.md` §7 calls for business-materiality weights to eventually come
from a Product/Statistics-approved contract rather than ML Discovery invention alone. That review
is requested in `HANDOFF-045` (`memory/HANDOFFS.md`); `RANKING_METHOD_VERSION` exists so a future
contract change is visible and comparable, never silently retroactive to an already-frozen ranking
artifact.

## Reproduction

```sh
uv run python scripts/rank_candidates.py \
    --candidates artifacts/blind/task-015-official-20260816-015.candidates.json \
    --dataset-root synthetic_data/analytical/travel-bookings-analytical-v1.0.0 \
    --output artifacts/discovery/task-016-candidate-ranking-task-015-official-20260816-015.json
```

The 2026-08-16 run ranked all 15 `task-015-official-20260816-015` candidates; scores ranged
0.434–0.798, all fully stable (`stability_missing=false`) across validation and future-holdout.
The frozen artifact records exact weights, the frozen-vs-recomputed provenance note above, and
every component per candidate.

## Known limitation

Novelty compares only candidates within one ranked batch; it has no notion of overlap with a
future run's candidates. Support and economic impact are batch-relative (min-max), so the same
candidate can carry a different normalized score if ranked alongside a different candidate set —
`rank_score` is a within-run ordering tool, not a portable absolute score across runs.
