# TASK-116 — Frozen-engine capacity-allocation autopsy: results

**Status: DRAFT — population in progress.**

**Owner:** STATISTICS. **Support:** ML_DISCOVERY, ARCHITECT. **Depends on:** `ADR-117`, `TASK-114`,
`TASK-115`.

## 0. Scope, binding rules, and read-only confirmation

Exactly as scoped by `ADR-117`/`TASK-116` (see `TASKS.md` and `DECISIONS.md` for the binding
text): no change to `engine.py`, `_development_score`, beam, `max_conditions`, `config.top_k`, or
any other search/ranking parameter. `H116` is tested by instrumenting/replaying the real, frozen
`discovery-engine-v0.6.2` diagnostically from our own scripts under
`docs/benchmark/task-116-evidence/`, never by editing `engine.py`.

- `engine.py` sha256 before this task: `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`
- `engine.py` sha256 after this task: TBD (confirmed identical at close-out)

## 1. The one-literal admissible-descendant pool: method

TBD — see `docs/benchmark/task-116-evidence/step1_build_pool.py`'s own docstring for the full
reconstruction method (reconstructed from the reverted `discovery-engine-v0.6.4`
`_refinement_candidates` diff, calling only the real frozen engine functions `_atoms`, `_metric`,
`_eligible`, `_exposed_rows`, `_development_score`, `discover_candidates`).

## 2. Measurement 1 — counterfactual unlimited-cap (the decisive test)

TBD, per target per seed.

## 3. Measurement 2 — displacement accounting

TBD.

## 4. Measurement 3 — capacity-sensitivity curve (diagnostic only; NOT a benchmark-improvement
proposal; NOT a recommendation for any new `K`)

TBD.

## 5. Measurement 4 — role competition

TBD.

## 6. C07 negative-control guard

TBD.

## 7. `H116` verdict against the pre-registered criterion

TBD.

## 8. Evidence-bar discipline

Reliable Specific Recall remains **1/11** and Exact remains **0/11** from `TASK-109`'s last valid
blind measurement. This task, even with a fully SUPPORTED `H116`, does **not** move that number —
it is a mechanistic-understanding result only, same as `TASK-112`/`TASK-115`.

## 9. What this result does and does not license

Per `ADR-117` Decision 6/7: a SUPPORTED `H116` licenses considering a *different class* of
architecture (e.g. partitioned/reserved capacity) as a separately-authorized future task — this
task does **not** design or implement any such thing, propose a new `K`, or claim to narrow the
gap to the evidence bar.
