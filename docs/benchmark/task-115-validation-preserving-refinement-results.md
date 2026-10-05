# TASK-115 — validation-preserving, post-acquisition, one-literal refinement step: results

**Status:** IN PROGRESS — this document is filled in incrementally as each step's real
computation completes (`ADR-116`/`TASK-115`'s own incremental-commit requirement). Placeholder
sections below are marked `[PENDING]` and are not final numbers.

**Owner:** ML_DISCOVERY. **Support:** STATISTICS, ARCHITECT. **Depends on:** `ADR-116`,
`TASK-114`'s revised verdict, `docs/benchmark/task-107-freeze-manifest.md`.

## 0. Scope and the one permitted mechanism

Exactly as scoped by `ADR-116`/`TASK-115` (see `TASKS.md` entry and `DECISIONS.md` `ADR-116` for
the binding text, reproduced only in summary here): keep the existing search/ranking
(`_development_score`, beam, `max_conditions`) completely unmodified as the acquisition path.
After its shortlist, a deterministic refinement pass tries exactly one additional real atom per
already-shortlisted parent, admits a descendant only if it passes the real, frozen validation
contract (1.3.0, verdict `PASS` or `DOWNGRADE`, never `REJECT`), and never consults benchmark
ground truth or a specificity/Jaccard comparison to decide admissibility. See `engine.py`'s own
module docstring (`v0.6.4` entry) for the full mechanism description.

## 1. Pre-registered predictions (Step 1)

See `docs/benchmark/task-115-evidence/step1-predictions.md`, committed before any code change
(commit `765f211`). Summary: for each of `C04, C06, C09, C14, C15`, predicted the parent pattern
and added literal expected to PASS and improve the exposure-Jaccard (`j_e`)/literal-match recall
(`cr`) toward the target, reusing `TASK-114` Method B's own measured dev-score steps. Flagged
`C09`/`C14` as highest-confidence (Method-A real-top-15 support already observed in `TASK-114`)
and `C04`/`C06`/`C15` as lower-confidence (zero Method-A "clean" support, but a supplementary scan
found a real top-15 shortlist member overlapping the target's canonical literals, with room, on
58-60/60 development seeds for every one of the 5 targets). `C07` guard: predicted the known
`party_size>=4.0` destructive-narrowing descendant may again be tried and may even PASS validation,
but is structurally harmless because refinement candidates are strictly *appended*, never replacing
or removing an existing shortlisted candidate — so `C07`'s own baseline-covering candidate(s)
always remain in the returned list regardless of what the refinement pass does elsewhere.

## 2. The exact code change (Step 2)

`packages/analytics/src/policy_analytics/discovery/engine.py`:
- `DISCOVERY_METHOD_VERSION`: `discovery-engine-v0.6.2` -> `discovery-engine-v0.6.4` (`v0.6.3` was
  `TASK-112`'s rejected/reverted attempt, not reused, per `TASK-101`'s own versioning precedent).
- New `RefinementValidator` type alias, `_format_rule()` helper, `_refinement_candidates()`
  function, and the wiring at the tail of `discover_candidates()` (new keyword-only
  `refine_with_validation` parameter, default `None` — every pre-existing call site, including
  every test, omits it, so behavior is byte-identical to `v0.6.2` except for the version string).
- `_development_score`, beam width/depth, `max_conditions`, the generator, and the scorer are
  untouched. `discovery/` gains no import of `validation/`.
- Engine sha256 before any change: `fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549`
  (`discovery-engine-v0.6.2`, matches `docs/benchmark/task-107-freeze-manifest.md`). After all of
  Step 2's commits: `[PENDING final hash once Step 2 is fully closed]`.
- Full diff: `git log` on this branch, commits tagged "TASK-115 Step 2" (implementation + the
  signature/performance follow-up fixes, each documented inline in its own commit message).
- Verification: `uv run ruff check` clean; `uv run pyright
  packages/analytics/src/policy_analytics/discovery/engine.py` 0 errors (pyright's own
  `pyproject.toml` scope does not include `tests/`, confirmed by reading
  `[tool.pyright].include`); full-project `uv run pyright` shows the same 177 pre-existing errors
  in unrelated `scripts/` files it showed before this change, none in `discovery/engine.py`
  (confirmed by grep); `uv run pytest -m analytics`: 874 passed, 1 skipped, 193 deselected, 12
  xfailed, 4 failed — all 4 the pre-existing gitignored-`artifacts/` `FileNotFoundError` class
  already catalogued by `TASK-077`'s independent review, confirmed by re-checking each traceback.
  3 tests that hardcoded the literal string `"discovery-engine-v0.6.2"` were updated to
  `"discovery-engine-v0.6.4"` (documented inline in each test and in the Step 2 commit message);
  no other test touched, none weakened.

**Performance note (disclosed, not a scope change):** an early implementation validated every
admissible one-literal descendant in one batch; measured on seed 4001, a 15-member shortlist
produces 889 admissible descendants, and real `run_validation` costs ~0.7-0.9s/candidate — making
a 60+-seed evaluation impractical. Fixed by validating in descending-`(-development_score, rule)`
order (the exact capacity tie-break `ADR-116` Decision 2 already specifies) in batches of
`config.top_k`, stopping once `config.top_k` descendants have PASSed — provably identical to
validating everything and then keeping the top `config.top_k` by score (see the commit message for
the short proof), confirmed empirically with a stub validator. This changes nothing about
admissibility or which descendants are ultimately kept.

## 3. Mechanism PASS evaluation (Step 3) — development seeds `4001-4030`, `4101-4130`

**[PENDING — background batch run in progress as of this commit; see
`docs/benchmark/task-115-evidence/step3-dev-seeds/` for per-seed raw output and
`step3-analysis-results.json` for the aggregated comparison against the already-committed baseline
raw data (`docs/benchmark/task-109-evidence/engine-raw/`,
`docs/benchmark/task-112-evidence/step5-paired-4101-4130/baseline-seed-*.json`).]**

Per-target evidence, `C07` guard check, and the explicit `>=4/5` bar verdict will be filled in here
once `step3_analyze.py` has run against the complete 60-seed modified-engine output.

## 4. Fresh evaluation reserve (Step 4)

See `docs/benchmark/task-115-evidence/step4-fresh-reserve.md` — `5001-5030`, grep-verified
untouched (zero seed-context or range-literal occurrences anywhere in tracked files or
`git log --all -p` history), committed only after Step 3's Mechanism PASS verdict.
**[PENDING Step 3 completion before this range is formally adopted/committed per the binding
order.]**

## 5. Paired evaluation on the fresh reserve (Step 5)

**[PENDING]** Absolute numbers for both engines (baseline, frozen `discovery-engine-v0.6.2`;
modified, `discovery-engine-v0.6.4` with the refinement pass) on identical `5001-5030` draws:
Reliable Specific Recall (CP-LB `>=0.90` on k/30 per Core target), total Specific-hit count across
`11x30`, Coverage Recall, Exact Recall.

## 6. Two-sided go/no-go verdict (Step 6)

**[PENDING]** `ADR-116` Decision 7's 7 conditions, evaluated explicitly, no rebalancing. Condition
7 (no change anywhere to the frozen benchmark/scorer/validation thresholds) is confirmed via
`git diff` showing only `packages/analytics/src/policy_analytics/discovery/engine.py` and this
task's own `docs/`/`tests/` changes — independent of the run results.

## 7. Hard-stop statement

If Step 3 passes but Step 5/6 shows regression or no Specific improvement, this task ends **NOT
SUCCESS** and stops there — no second refinement step, no different ordering rule, no new
threshold is added to try to rescue the result (`ADR-116` Decision 8, binding).
