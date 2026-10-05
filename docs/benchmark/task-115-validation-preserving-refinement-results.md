# TASK-115 — validation-preserving, post-acquisition, one-literal refinement step: results

**Status: CLOSED — NOT SUCCESS at Step 3 (Mechanism PASS bar not met: 0/5 strong targets, bar is
`>=4/5`).** Per the binding order ("Step 4 — only if Step 3 passes"), `TASK-115` does not proceed
to Step 4 (fresh reserve), Step 5 (paired evaluation), or Step 6 (two-sided go/no-go). No
refinement candidate for any of `C04, C06, C09, C14, C15` reached the Specific-recovery threshold
on any of the 60 development seeds, despite the mechanism firing on every seed and finding, in its
own full admissible pool, descendants with much higher specificity (`C14`: a seed exists where the
*exact canonical rule*, `j_e=1.000`, is in the admissible pool) — they are excluded before ever
reaching validation by the capacity cap's own mandated ranking rule (`_development_score`, reused
exactly as `ADR-116` Decision 2 requires). See §3 for the full diagnosis. This is reported plainly,
not reinterpreted, per this project's own hard-stop discipline.

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
  Step 2's commits (final, closing): `a6de06a65dce636d617022a9af8ec7327e192c86391c4fc506ba7f55eed20bc7`.
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

**Real run, all 60 seeds, complete.** `step3_run_modified_dev_seeds.py` ran the real modified
engine (`discovery-engine-v0.6.4`, `refine_with_validation` wired to the real `run_validation`
contract 1.3.0) on every seed, end to end (search, refinement, validation of both the base
shortlist and the refinement probes, real `benchmark_v2_scoring.score()`); raw output committed at
`docs/benchmark/task-115-evidence/step3-dev-seeds/modified-seed-*.json` (commit `b5640f8`).
Compared against the already-committed baseline (pre-`TASK-115`) raw output for these identical
seeds (`docs/benchmark/task-109-evidence/engine-raw/`,
`docs/benchmark/task-112-evidence/step5-paired-4101-4130/baseline-seed-*.json` — not re-run) via
`step3_analyze.py`.

**The mechanism fires on every seed**: all 60/60 seeds produced at least one refinement candidate
(900 total across all seeds, ~15/seed — the `config.top_k` capacity cap from `ADR-116` Decision 2
binds on every single seed; see below for why this matters). `C07`'s guard holds exactly as
predicted: `baseline_specific_k=60/60`, `modified_specific_k=60/60`, zero lost-Specific or
lost-Coverage seeds — the append-only design (§1/§Step-2) structurally protected it.

**But the predicted pattern did not appear for any of the 5 strong targets:**

| Target | baseline Specific k/60 | modified Specific k/60 | seeds gaining Specific | seeds losing Specific |
|---|---|---|---|---|
| C04 | 0 | 0 | 0 | 0 |
| C06 | 0 | 0 | 0 | 0 |
| C09 | 7 | 7 | 0 | 0 |
| C14 | 38 | 38 | 0 | 0 |
| C15 | 2 | 2 | 0 | 0 |
| H01 (secondary) | 0 | 0 | 0 | 0 |
| C07 (negative control) | 60 | 60 | 0 | 0 |

**0 of 5 strong targets show the predicted pattern on any seed — far below the pre-registered
`>=4/5` bar. Mechanism PASS: NOT MET.** (Full per-target, per-seed detail:
`docs/benchmark/task-115-evidence/step3-analysis-results.json`.) Note `C11` (not a strong or
secondary target, not counted toward the bar) gained Specific on 3/60 seeds — reported for
completeness, not claimed as evidence for the mechanism.

### 3.1 Diagnosis — why the mechanism fires but never reaches specificity

`step3_diagnose.py` (sampled 10/60 seeds) confirmed refinement candidates genuinely touching each
strong target's own canonical features *were* produced in volume (23-148 per target across just
10 seeds) — the mechanism is not simply failing to try anything relevant. But the best
exposure-Jaccard (`j_e`) any of the *validated/kept* refinement candidates ever reached for these
targets was 0.06-0.31, all below the `theta_j=0.50` Specific-recovery floor — typically because the
kept candidate's parent already carried an off-canonical condition (`manual_exception`,
`quoted_cost_eur`, `customer_price_eur`, `acquisition_channel` paired with the wrong target's own
feature, etc.) that the one-literal addition could not remove (`max_conditions=3` leaves no room
to both drop an extraneous condition and add a canonical one).

`step3_diagnose_capacity_cap.py` (seed 4001, full detail) isolated the deeper cause. Comparing the
*full* admissible-descendant pool (889 descendants, before the `config.top_k=15` capacity cap) to
what the real capped/validated run actually kept:

| Target | best `j_e` in the FULL admissible pool (uncapped) | best `j_e` among the 15 that were actually validated/kept |
|---|---|---|
| C04 | 0.370 | 0.089 |
| C06 | 0.354 | 0.060 |
| C09 | 0.344 | 0.082 |
| **C14** | **1.000 (the exact canonical rule is in the pool)** | 0.163 |
| C15 | 0.248 | 0.133 |

**For `C14`, the exact canonical descendant (`customer_segment=leisure AND discount_rate>=0.08
AND supplier=BlueWing`, `j_e=1.000`) is genuinely admissible and present in the pool — it is never
validated at all**, because `ADR-116` Decision 2 mandates the capacity tie-break be the existing,
unmodified `_development_score` — and `_development_score` is exactly the objective `TASK-114`'s
own `H114` finding showed systematically prefers broad, off-canonical rules over specific ones.
With 889 admissible descendants competing for only 15 validation/keep slots per seed, the same
score bias the refinement mechanism was designed to route around re-enters at the capacity-cap
step and crowds out the specificity-improving descendants before they are ever checked against the
validation contract. **This is not an implementation defect — it is a direct, reproducible
consequence of implementing the mechanism exactly as `ADR-116` scoped it** (no new score, no
Jaccard/specificity comparison permitted anywhere in admissibility or ranking). Full evidence:
`docs/benchmark/task-115-evidence/step3-diagnose-output.txt`,
`step3-diagnose-capacity-cap-output.txt`.

## 4. Fresh evaluation reserve (Step 4) — NOT REACHED

Per the binding order ("Step 4 — only if Step 3 passes"), this step is not executed. A candidate
range (`5001-5030`) was researched and grep-verified untouched in advance of Step 3's result (see
`docs/benchmark/task-115-evidence/step4-fresh-reserve.md`, committed for transparency and future
reuse) — **but it is explicitly NOT adopted or authorized by this task**: no engine of any kind
was ever run on any seed in `5001-5030`, and this task does not claim to have exercised Step 4.
The range remains available, untouched, for whichever future task is authorized to name a fresh
reserve next.

## 5. Paired evaluation on the fresh reserve (Step 5) — NOT REACHED

Not executed; gated on Step 3 passing (it did not).

## 6. Two-sided go/no-go verdict (Step 6) — NOT REACHED; overall verdict NOT SUCCESS

`ADR-116` Decision 7's 7 conditions are not evaluated — Step 3 itself is the gating failure, prior
to any question Step 5/6 would otherwise answer. **Overall `TASK-115` verdict: NOT SUCCESS.** Per
`ADR-116` Decision 9's own framing (even a SUCCESS would not have closed the discovery-quality
question), a NOT SUCCESS here likewise closes nothing beyond this one scoped mechanism: it answers
exactly one question — "does the exact mechanism `ADR-116` specified, implemented faithfully,
clear its own pre-registered Mechanism PASS bar on development evidence" — with a reproducible,
diagnosed **no**.

## 7. Hard-stop statement

**No second refinement step, no different ordering rule, no new threshold was added inside this
task to try to rescue the result** (`ADR-116` Decision 8, binding) — including the capacity-cap
finding in §3.1, which is exactly the kind of result this discipline exists to report plainly
rather than patch around. `engine.py`'s `_refinement_candidates`/`discover_candidates` wiring is
left exactly as implemented and verified in Step 2; no further engine change was made after
Step 3's result was known.
