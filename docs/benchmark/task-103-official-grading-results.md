# TASK-103 - Results: grading `discovery-engine-v0.6.2` against the frozen `TASK-102`/`ADR-097` outreach evidence bar

**Owner:** STATISTICS (lead), ARCHITECT (support). **Recorded:** 2026-09-24.
**Nothing was changed** in `engine.py`, any gate, `apply.py`, `contract.py`, `grading.py`, or any
threshold (`git diff 2e1c45c -- packages tools` is empty). The frozen bar is graded exactly as written in
`docs/strategy/task-102-outreach-evidence-bar-proposal.md`. Scripts: `scripts/task103_grade_overlay.py`
(ruff and pyright clean). Evidence: `docs/benchmark/task-103-evidence/` (frozen candidates, metrics,
hashes, signed manifests, validation and evaluation reports per run, plus `overlay-raw.json`).

## 0. Headline

1. Measured on the current engine, **each run individually meets Dimension 1 (Top-10 precision 100%)
   and Dimension 3 (`{P01, P06}` 2/2 at `predictive_association`, non-trap)**, and Dimension 2 Part A holds
   (0 promotions).
2. **The two runs are not two independent draws.** `seed` is an unused `DiscoveryConfig` field; the two
   runs' discovery output is identical apart from the `run_id` string. Under the frozen bar's own
   rationale (Dimension 5(a); the exclusion of `TASK-073`/`TASK-083`), effective independent runs = **1**.
3. Mechanical overlay: **D1 FAIL, D2 FAIL, D3 FAIL, D5 FAIL, D4 UNKNOWN**. Section 6 explains which
   of these turn on the run count and which do not, and gives the alternative label-only reading for the
   founder's ruling (Section 5 records only the gate entry).

## 1. Starting-state confirmation

- Commit `2e1c45c` (HEAD when both runs were issued and this branch was cut).
- `DISCOVERY_METHOD_VERSION = "discovery-engine-v0.6.2"` (`engine.py` line 117); `TASK-101`'s change is
  the last engine commit (`8eba69b`).
- `DiscoveryConfig()` defaults printed at run time: `seed=1729, min_support=0.01, max_support=0.4,
  min_n=40, max_conditions=3, beam_width=80, beam_rules_per_structure=2, max_expansion_beam_size=512,
  top_k=15, numeric_quantiles=(0.2,0.4,0.6,0.8), max_categorical_levels=12, max_candidate_jaccard=0.85,
  max_candidates_per_atom=5, population_score_exponent=0.5, diversity_discount_weight=0.5,
  min_diversity_relevance_ratio=0.5, stability_credit_weight=0.5, relevance_floor_percentile=0.75,
  max_feature_identity_fraction=1.0, reserve_k1_slot=False`.
  `tests/analytics/test_discovery_config_accepted_defaults.py`: 21 passed.
- `engine.py` sha256 `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`; both runs'
  `verify`/`launch` re-checked the source snapshot against the issued signed manifest (no drift).
- Validation contract `1.3.0` (with `G16`); dataset `travel-bookings-analytical-v1.1.0`, identity
  `b6128eb3...4b60a683` (full value in the `decision-gate.md` entry); image
  `policy-blind-agent@sha256:9ad6e1a78ca41a7c04895d1d99c7775e77fc2c8fbb4f23cee268ed04534c7c9b`,
  deterministic actor, network `none`.

## 2. Custody protocol, both runs

Common: `make blind-key-init`, `make blind-rehearsal BLIND_DATASET=travel` -> `BLIND_REHEARSAL_VALID`.
Because the `Makefile`'s `blind-issue` target does not expose `--seed` (so every prior official run used
the CLI default `1729`), issuance was invoked directly as `python -m tools.blind_agent.cli issue ...
--seed <N> --max-feature-identity-fraction 1.0` with otherwise identical arguments; verify, launch
(`make blind-shell`) and freeze used the `Makefile` targets unchanged.

| | Run A | Run B |
|---|---|---|
| Run ID | `task-103-official-20260922-001` | `task-103-official-20260922-003` |
| Seed | `4242` | `8916` |
| issue / verify / launch / freeze | all succeeded (`BLIND_WORKSPACE_VALID`) | all succeeded |
| Frozen `candidates.json` sha256 | `f63dbbb4...ad2d` (full in `hashes.json`) | `5a4b35d3...ba2e` |
| Hypotheses evaluated | 36,791 | 36,791 |
| Candidates | 15, `PERSISTED` | 15, `PERSISTED` |
| Validation | `task-019-official-20260922-task-103-001` | `...-002`; 15 x `DOWNGRADE` each |
| Evaluation | `task-028-task-103-official-001` | `...-002` |

**Run `-002`, disclosed.** It was issued and verified with seed `8916`, its launch was interrupted by an
API rate-limit stop (state left `RUNNING`, no `output/` files, container gone). A `RUNNING` run cannot be
relaunched and the ID cannot be reused, so `-003` was issued with the same seed. No result from `-002`
existed, so nothing was selected or discarded on outcome.

**Custody re-derivation (own code, not the tool's checks).** SHA-256 of the three frozen files of each run
match `frozen/hashes.json`; the manifest HMAC-SHA256 (domain `blind-agent-manifest-v1\0`, canonical JSON)
recomputed with the evaluator key matches `evaluator_signature` for both runs. The whole worktree that
issued Run A was later lost (see 7); the runs directory in `/tmp` survived, and every artifact here was
re-derived or copied from it.

## 3. Independence verification

- Seed labels differ (`4242` vs `8916`), signed into each manifest and echoed in `discovery_metrics.json`.
- **Discovery output does not differ.** `candidates.json`, compared as parsed JSON with `run_id`
  excluded, is identical (raw diff: one differing line, the `run_id`). Same 15 candidates, conditions,
  thresholds, sample sizes, effects, and the same 36,791 evaluated hypotheses.
- Cause: `engine.py` uses `seed` only as a field definition (`seed: int = 1729`, line 129); there is no
  RNG, shuffle, or sampling anywhere in discovery. The project's own doc says so
  (`docs/analytics/discovery-engine-v0.md` line 39: "deterministic; the seed is recorded for forward
  compatibility"). Validation's bootstrap seed is fixed by the contract, not by the run seed, so the
  validation and evaluation reports are identical too (compared with paths/timestamps/run ids dropped).
- `blind_bundle_id` is also identical (it hashes the allowlisted inputs, which do not include the seed).
- Consequence: the pair has exactly the `TASK-073`/`TASK-083` shape (different label, identical
  discovery output), reached via a different route. Genuinely varying the draw requires varying the
  temporal split or the dataset/domain, neither of which is a seed change. That was not done here: no
  other split or dataset carries the frozen `{P01, P06}` denominator, and building one is new
  infrastructure, outside this task's binding scope.

## 4. Raw measurements (identical for both runs)

| | Run A | Run B |
|---|---|---|
| **D1** Top-10 precision (K=10, `TASK-028` 0.5-recall match, non-trap) | 100% (10/10); exact 90% CI lower bound 74.1% (Clopper-Pearson, x=n=10) | same |
| **D2 Part A** trap at `SHADOW_POLICY`/`HIGH_CONFIDENCE` | none (0/5 promoted) | same |
| **D2 Part B** trap types appearing as candidates this run | **none of T01-T05** (so none capped-with-caveat this run) | same |
| **D3** `{P01, P06}` at >= `predictive_association`, non-trap | P01 yes (`predictive_association`), P06 yes (`predictive_association`, via `CAND-001`, `CAND-008`, `CAND-012`): 2/2 | same |
| Evidence levels of 15 candidates | 13 `predictive_association`, 2 `descriptive_observation`, 0 higher | same |
| Other decision-gate metrics | econ-weighted recall 100.0%, leakage 0, direction accuracy 13/13 | same |

**Reading caveat (disclosed, nothing reinterpreted).** The 100% figures arise under `TASK-028`'s
unchanged lenient match statistic applied to a candidate set of broad rules (exposed populations up to
~7,800 rows (7,817, `CAND-015`); several candidates match up to 8 patterns, including `P05`/`P07`). Only 9 of 15 candidates
match `P01` alone. This is a very different set from `v0.6.0`'s (70% precision, 45.2% recall), consistent
with `TASK-101`'s finding that `v0.6.2` changes 10 of 15 travel candidates. Whether the broad-rule regime
is desirable is a question for a reviewer, not something this task adjusts. Also: with no trap present,
`G16` was never exercised on a trap this cycle.

## 5. `decision-gate.md` entries

One combined entry covering both runs was appended (same format as `TASK-073`/`TASK-083`; not one entry per run), stating the identical
result and the independence disclosure: overall verdict **PROMISING** (STRONG on precision, recall,
direction; PROMISING on trap rejection because no trap appeared; leakage 0; no hard disqualifier).

## 6. Mechanical overlay against the frozen bar

Rules are applied literally. `enough runs` means >= 2 qualifying independent runs.

| # | Dimension | Verdict | Basis |
|---|---|---|---|
| 1 | Precision | **FAIL** | Measurement passes on both runs (100% >= 80%), but the 2 runs are 1 effective draw (Section 3), so "fewer than 2 qualifying independent runs" applies |
| 2 | Safety | **FAIL** | Part A holds (0 promotions), but only by absence again. Part B cumulative stays **2/5** (`T03`, `T04` from `TASK-083`); this cycle added none, so 5/5 is not met. Independent of the run count |
| 3 | Recall (`{P01, P06}`) | **FAIL** | 2/2 on both runs; FAIL only through the run-count rule, as D1 |
| 4 | Economic impact | **UNKNOWN** | No instrument exists; out of scope by `ADR-097` |
| 5 | Independent runs | **FAIL** | Needs >= 2 qualifying runs each clearing D1-D4; D2 fails and D4 is UNKNOWN, so this fails under every reading of the run count. With effective draws = 1 it also fails on count |

**The one interpretive fork, stated for the founder rather than resolved silently.** D1 and D3 turn on
whether "varies at least one of random seed" (section 5(b) of the frozen document) is satisfied by a seed
label that has no effect on output. I graded the substantive reading because the frozen text's own
exclusion of `TASK-073`/`TASK-083` and Dimension 5(a) ("not a single favorable draw") are about
identical discovery output. Under the label-only reading D1 and D3 would each read `PASS` on the
measurements above, and D2/D5 would still be `FAIL`, D4 `UNKNOWN`, so **the conjunction (D6) is `FAIL`
under either reading**. Choosing between the readings is a founder decision (a new dated `ADR`), not
mine.

**Dimension 6:** FAIL (D2, D4, D5 not PASS; founder threshold confirmation done by `ADR-097`, `TASK-057`
unpause not done and untouched).

## 7. Stop-rule findings (recorded, not acted on)

1. **Diagnosed specific cause for the D1/D3/D5 shortfall:** `seed` is a dead parameter, so the
   frozen definition of an independent run cannot be satisfied by varying it. Independent draws need a
   different temporal split or dataset. A narrowly scoped follow-on task could be opened separately after
   this one closes; I did not open one, and no tuning is implied.
2. **D2 Part B is a coverage problem, not a rejection problem:** none of `T01`-`T05` surfaced in
   the current engine's candidates. Whether they can surface under `v0.6.2` is not learnable from this
   travel dataset with this deterministic engine.
3. Tooling note: `make blind-issue` cannot set a seed (defaults to `1729`).
4. Environment note: the original worktree (`agent-a84916b7400f0f5e8`) was removed during an
   interruption; nothing had been committed. This branch (`task-103-grading`, worktree
   `worktrees/task-103`, from `2e1c45c`) redid the validation/evaluation steps and re-ran Run B
   as `-003`. Run A's frozen output was reused from `/tmp/policy-blind-runs` after re-verifying hashes and
   signature.

## 8. Reproduce

`uv run python scripts/task103_grade_overlay.py docs/benchmark/task-103-evidence`, and
`cmp`-style comparison of `run1/candidates.json` vs `run2/candidates.json` (only `run_id` differs).
Validation: `scripts/validate_candidates.py --candidates <frozen>/candidates.json --metrics
<frozen>/discovery_metrics.json --dataset-root synthetic_data/analytical/travel-bookings-analytical-v1.1.0
...`; evaluation: `scripts/evaluate_benchmark.py --validation-report ... --dataset-root <same>`.
