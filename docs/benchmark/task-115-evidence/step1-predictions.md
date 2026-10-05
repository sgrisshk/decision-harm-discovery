# TASK-115 Step 1 — pre-registered mechanism-test predictions (committed BEFORE any code change)

**Scope:** `ADR-116`/`TASK-115` Step 1. Predicts, for the 5 strong `H114` targets (`C04, C06, C09,
C14, C15`), the specific previously-established productive descendant the new refinement path is
expected to make reachable, using only `TASK-114`'s own committed evidence
(`docs/benchmark/task-114-h114-nested-refinement-autopsy.md`, `docs/benchmark/task-114-evidence/`)
and `TASK-113`/`TASK-112`'s raw data — nothing run by this task yet. `engine.py` is untouched as of
this commit (verified sha256 below). No code for the refinement mechanism exists yet.

## 0. Engine integrity at prediction time

`packages/analytics/src/policy_analytics/discovery/engine.py` sha256:
`fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549` (`discovery-engine-v0.6.2`,
matches `docs/benchmark/task-107-freeze-manifest.md` and every prior task in this arc). Confirmed
via `shasum -a 256` immediately before writing this document.

## 1. What "existing shortlisted parent" means for this prediction, and why it matters

`ADR-116`'s mechanism is `existing shortlisted parent -> +one eligible literal -> validation ->
PASS`. "Shortlisted" means a member of `discover_candidates()`'s own final, already-assembled
top-K list (`top_k=15` by default) — not merely any rule the search happened to score internally.
This is a materially different anchor than `TASK-114` Method B (which starts chains from a
target's own canonical literal regardless of whether it ever reached the real top-15) and stricter
than `TASK-114` Method A's own "clean broad candidate" reading (which additionally required the
parent's conditions to be a non-extraneous subset of the canonical literals).

`TASK-114` Method A (`step2-classification-results.json`) found, using the *clean* reading, zero
real-top-15 anchors across all 60 development seeds for `C04`, `C06`, `C15` (and `H01`) — only
`C09` (7/60) and `C14` (45/60) had any Method-A support at all. Taken literally, this would predict
only 2 of the 5 strong targets are reachable. **Before committing to that pessimistic reading, this
task ran one additional, read-only, already-permitted check** (`step1_scan_shortlist_overlap.py`,
`step1-shortlist-overlap-scan.json`, over the same already-committed `4001-4030`/`4101-4130` raw
data) relaxing only the "clean" (no extraneous condition) requirement — i.e. asking "does *any*
real top-15 candidate, clean or not, share at least one of this target's canonical literals and
still have room (`<3` conditions) for the refinement pass to add one more?":

| Target | Seeds (of 60) with an overlapping, room-having top-15 candidate | Seeds with a *clean* one (Method A) |
|---|---|---|
| C04 | 58 | 0 |
| C06 | 60 | 1 |
| C09 | 60 | 7 |
| C14 | 60 | 45 |
| C15 | 60 | 0 |

**Prediction, stated plainly:** the refinement mechanism has a structural opportunity (an
overlapping, room-having real shortlist parent exists) on nearly every development seed for all 5
targets. Confidence in the mechanism actually reaching a validation-PASSing, more-specific,
better-evidenced descendant is **highest for `C09`/`C14`** (Method-A clean support already
observed) and **lower but still expected to succeed on most seeds for `C04`/`C06`/`C15`**, because
the refinement step tries *every* eligible real atom per parent (not only the clean canonical one),
so a currently-unclean top-15 parent's own vacuous/irrelevant extraneous condition is expected (per
the validation contract's own scoring semantics used throughout this arc, e.g.
`benchmark_v2_scoring`'s sequential-vacuity construction of the effective condition set) not to
block the added canonical literal from being admissible and informative, even though that
structural detail is scored by `benchmark_v2_scoring`, not by the engine's own `_eligible()` or the
validation contract. This is disclosed as the weaker part of the prediction, not minimized.

## 2. Per-target prediction (parent pattern, added literal, expected outcome)

For each target, the predicted productive descendant reuses exactly the missing-literal chain
`TASK-114` Method B already measured with the real, unmodified engine/scoring functions
(`docs/benchmark/task-114-evidence/step1b-canonical-prefix-raw/`,
`step2-classification-results.json` table in §3 of the autopsy) — this task invents no new rule.

| Target | Canonical rule | Predicted parent pattern (whatever real top-15 member on a given seed contains it, with room) | Predicted added literal (tried among all eligible atoms; this is the one expected to PASS and improve `j_e`) | Basis (TASK-114 Method B dev-score step) | Seeds predicted to show the pattern |
|---|---|---|---|---|---|
| C04 | `supplier=Cedar AND customer_segment=leisure AND trip_duration_days>=8` | contains `trip_duration_days>=8` | `supplier=Cedar` (else `customer_segment=leisure`) | seed 4001: dev_score 10331.71 (`trip_duration_days>=8`) -> 4026.95 (`+supplier=Cedar`), `j_e` 0.137->0.645, recall held at 1.000 | most of 60 (`4001-4030`, `4101-4130`); weaker confidence per §1 |
| C06 | `destination=Reykjavik AND customer_type=returning AND discount_rate>=0.05` | contains `discount_rate>=0.05`-structure (`ge` on `discount_rate`) | `destination=Reykjavik` | seed 4001: dev_score 21882.28 -> 4032.15, `j_e` 0.055->0.356, recall held at 1.000 | most of 60; weaker confidence per §1 |
| C09 | `destination=Tokyo AND customer_segment=leisure AND product_category=standard` | contains `destination=Tokyo` | `customer_segment=leisure` (else `product_category=standard`) | seed 4001: dev_score 10264.14 -> 4794.95, `j_e` 0.337->0.571, recall held at 1.000 | most of 60; highest confidence (Method-A support 7/60 + universal overlap-room 60/60) |
| C14 | `customer_segment=leisure AND supplier=BlueWing AND discount_rate>=0.08` | contains `discount_rate>=0.08`-structure | `customer_segment=leisure` (else `supplier=BlueWing`) | seed 4001: dev_score 20072.28 -> 9458.91, `j_e` 0.169->0.296, recall held at 1.000 | most of 60; highest confidence (Method-A support 45/60) |
| C15 | `customer_type=returning AND acquisition_channel=direct AND trip_duration_days>=6` | contains `trip_duration_days>=6`-structure | `customer_type=returning` (else `acquisition_channel=direct`) | seed 4001: dev_score 10109.85 -> 7333.46, `j_e` 0.128->0.343, recall held at 1.000 | most of 60; weaker confidence per §1 |

`H01` (secondary, not required): predicted pattern is the step1->2 transition
(`+supplier=BlueWing` then `+destination=Zanzibar`), since step0 (`customer_type=new` alone) is
itself `_eligible()`-negative on development data (TASK-114 §3) and so can never be a parent at
all — the refinement mechanism can only ever reach `H01` through a 2-literal parent already
containing `supplier=BlueWing`, consistent with the autopsy's own finding that this is what
actually drives `H01`'s qualification in most seeds.

**What "a better evidence/Specific-metric outcome than before" means for this prediction:** the
refinement candidate need not reach `j_e=1.0` (full canonical match) to count — only to (a) PASS
the real validation contract (verdict `PASS` or `DOWNGRADE`, not `REJECT` — reusing exactly
`TASK-114` §6's own "PASS/DOWNGRADE are both real evidence, FAIL/REJECT is not" framing, not a new
threshold), and (b) show a materially higher exposure-Jaccard (`j_e`) / literal-match recall (`cr`)
toward the target than any candidate already in the un-refined shortlist achieved, i.e. genuinely
new specificity the acquisition path alone would not have surfaced.

## 3. C07 negative-control guard (mandatory)

**Prediction:** `C07` does not lose its baseline Coverage/Specific recovery, and is not durably
replaced by a worse structure. Zero extra `C07` descendants is explicitly *not* required — the
mechanism may legitimately pass some. Basis: `TASK-114` §5.1/§5.2 found a real, reproducible
destructive-narrowing mechanism on `C07` specifically — adding the real atom `party_size>=4.0`
(the engine's nearest grid point to `C07`'s true canonical threshold `party_size>=3`) to an
already-covering `C07` parent collapses Coverage recall below 0.5 and drops `j_e`, in 27 of the
60 development seeds (1 real-top-15 pair + 26 atom-sweep instances), while remaining
`_eligible()` (positive harm, sufficient support) on the development split. **We predict this same
descendant will be tried again by the refinement mechanism** (it is a real, eligible atom on a
real `C07`-covering shortlist parent) **and may well PASS the real validation contract** (the
contract scores statistical validity, not recall against a hidden canonical target, so nothing
about it is expected to catch this specific failure mode) — **but this is structurally harmless to
the guard by construction of this task's own implementation choice (§4 below): refinement
candidates are only ever *added* to the shortlist, never used to replace or remove an existing
shortlisted candidate.** `C07`'s own already-shortlisted covering candidate(s) remain in the
returned candidate list exactly as the unmodified acquisition path produced them, so `C07`'s
baseline Coverage/Specific recovery cannot be lost by this mechanism, regardless of what the
`party_size>=4.0` descendant's own validation verdict turns out to be. This is disclosed as a
property of the chosen implementation (pure addition, no replacement — see Step 2), not an
empirical finding yet; Step 3 still checks it directly against real output.

## 4. Implementation choice fixed now (governs the prediction and is binding on Step 2)

Refinement candidates are **appended** to `discover_candidates()`'s existing final shortlist; the
existing shortlist itself (identity, order, count, every per-candidate field) is never modified,
reordered, or pruned by the refinement pass. This is the only reading consistent with "the parent
is always a candidate the current engine already found... not a second independent search and not
a new scoring objective" (`ADR-116`) while still letting a validation-only-admissible descendant
reach the reported candidate set. One direct consequence, stated now so it cannot be seen as
rationalized after results: Coverage Recall, Exact Recall, and per-target Specific-hit counts on
any given seed can only stay the same or increase relative to the baseline engine by this
construction alone (scoring is an OR over the full candidate list per target) — the two real,
not-structurally-guaranteed questions this task still has to answer empirically are (a) whether
any seed actually sees an increase at all (vs. zero refinement candidates ever passing), and (b)
whether the precision/safety regression suite (trap promotion) gets worse, since added candidates
can also newly hit a trap. Both are measured, not assumed, in Steps 3/5/6.

## 5. Canonical descendant-ordering rule (fixed now, before any code runs)

Eligible literals for a given parent are considered in `_atoms()`'s own existing, already-
deterministic order (`tuple(sorted(atoms))` — alphabetical by `feature`, then `operator`, then
`value`; this is the real frozen atom-grid order the engine already produces, not a new rule). When
more admissible, validation-PASSing descendants exist across all parents combined than the reused
downstream limit (`config.top_k`, the only existing parameter in this codebase that caps "how many
final candidates are produced" — reused rather than inventing a new one) can hold, the kept subset
is chosen by the existing, unmodified `_development_score` (descending), tie-broken by the
candidate's own canonical `Condition` tuple order (`<` on the frozen, `order=True` dataclass) —
the same `(-score, rule)` tie-break pattern `discover_candidates()` already uses elsewhere
(`ranked_rules`, `_select_expansion_beam`). No new "specificity score" of any kind is introduced.

## 6. Falsifiable statement

If, on `4001-4030`/`4101-4130`, fewer than 4 of the 5 strong targets (`C04, C06, C09, C14, C15`)
show a refinement candidate that PASSes the real validation contract and reaches a materially
higher `j_e`/`cr` than the un-refined shortlist's own best candidate for that target, on most
applicable seeds, this prediction is wrong and Step 3's Mechanism PASS bar is not met — reported
plainly, not reinterpreted.
