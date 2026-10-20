# TASK-117 — pre-registration of operational definitions (written before any TASK-117 result)

**Binding:** `ADR-118`, `TASKS.md` `TASK-117` (criterion text quoted there is not restated or altered here).
This note only fixes how the task's terms are operationalised, so the verdict cannot be shaped after
seeing results. Recorded 2026-10-20, before `trajectory.py` was first run.

## Scope

* Engine `discovery-engine-v0.6.2`, `engine.py` sha256 `fefceeaa...e4549`, verified before and after
  every seed by the script (it reuses `run_blind_engine.verify_frozen_state`). No file under
  `packages/` is edited.
* Seeds `4001-4030` (development evidence, already spent; no new reserve consumed).
* Strong targets: `C04, C06, C09, C14, C15` (TASK-114). Guard: `C07` (reported, never counted).

## Re-driven search and fidelity

`trajectory.py` re-drives `discover_candidates`'s depth loop and post-loop selection with control
flow copied from the frozen file, calling only the real imported functions (`_atoms`, `_metric`,
`_eligible`, `_development_score`, `_select_expansion_beam`, `_exposed_rows`,
`_temporal_consistency`, `_apply_stability_credit`, `_greedy_diverse_select`). **Fidelity check:** the
re-driven final top-15 must equal, condition for condition and in order, TASK-109's committed
`engine-raw/seed-<seed>.json` candidates; a seed that fails this check is excluded and reported.

## Productive rule

A rule `r` is *productive for target T* iff the real scorer's metric part of Specific holds:
`metric_specific(pair_metrics(space, effective_rule(space, r).conditions, rule_mask(r), T), 0.50, 1.00)`
and `T` is the highest-`J_e` (credited) target for `r`. (Specific additionally needs validation at
`predictive_association`+; that is checked only where a candidate is actually validated.)

## Lineage and first irreversible divergence (per seed, per target not already Specific)

Tracked for every non-empty subset of the canonical literals and for every scored productive rule:
atom present; generated (in the depth's frontier); eligible; scored (not dropped as
exposure-identical to a parent); rank at its depth; in expansion beam; in final top-15.

* If some productive rule is scored but none is in the final top-15, the first irreversible
  divergence is **final top-K selection** (cause class (d), principle `FINAL_SELECTION`).
* If no productive rule is scored, the divergence is at generation, classified for the productive
  canonical subset closest to being generated: (a) a literal absent from `_atoms`; (b) a parent subset
  was scored but no parent entered the expansion beam (principle `BEAM_SELECTION`); (c) a parent was in
  the beam but the child was not enumerated; (d') generated but dropped as exposure-identical;
  (e) other, documented — specifically including *parents ineligible* (`ELIGIBILITY`: `harm <= 0` or
  support), which is a filter, not a ranking.

## One-step counterfactual replay

* `FINAL_SELECTION` divergence: replace the last (15th) selected rule with the productive rule of highest
  effective (stability-credited) score; assemble candidates exactly as the engine does; run the real,
  unmodified `run_validation` (family size = the engine's own `evaluated_hypotheses`) and the real
  `score()`. **Restored** iff `T` is in that seed's Specific set.
* `BEAM_SELECTION` divergence: add the highest-scoring scored parent to that depth's beam; continue the
  real search and the real final selection unmodified. Restored iff a productive rule reaches the final
  top-15 and then validates to Specific. If it is generated but not selected, the outcome is
  **multi-stage** (ii); the final-selection forcing is then applied as a second, disclosed intervention.
* `ELIGIBILITY` divergence: no one-step forcing is defined without introducing a new rule; reported as (e),
  counted as not restored.

## Verdict rule (TASK-117 criterion, operationalised)

A strong target counts toward `H117` iff, on a majority (> 50%) of its applicable seeds (seeds where it
was not Specific at baseline): (1) all canonical literals are atoms; (2) the first divergence has the
**same principle label**, and that label is the same one shared by the other counting targets;
(3) the one-step replay restores Specific with no further intervention. **SUPPORTED iff at least 4 of 5
strong targets count with one common principle.** Otherwise NOT SUPPORTED, including when the targets
split across principles.

Interpretive constraint carried from `ADR-118`: a shared principle that is *score-ranked* is reported as
a causal role of `_development_score` only because the replay overrides the score's influence at that
step and the outcome changes; no score/capacity change is proposed under any outcome.
