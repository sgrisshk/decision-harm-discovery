# TASK-115 Step 4 — fresh, genuinely untouched evaluation reserve

**NOT ADOPTED. Prepared in advance of Step 3's result (research + grep verification only);
committed here afterward, for transparency and future reuse, once Step 3's real Mechanism PASS
verdict came back NOT MET (0/5 strong targets, bar `>=4/5` — see
`docs/benchmark/task-115-validation-preserving-refinement-results.md` §3).** Per the binding order
("Step 4 — only if Step 3 passes"), this task does not authorize or adopt this range: no engine
(baseline or modified) was ever run on any seed in it. It is disclosed here only so the research
and verification work is not silently lost, and so a future task can reuse `5001-5030` (or know to
pick a different range) without redoing this check. Everything below describes the verification as
performed; none of it constitutes this task actually exercising Step 4.

This document would name the range, state its exact bounds and size, and show the grep
verification that it has never appeared anywhere in this project's history before adoption — per
`ADR-116` Decision 5 and `docs/benchmark/task-107-freeze-manifest.md`'s own seed-range ledger (§4),
which lists as already spent or reserved for other purposes: `1001-1030`, `9001-9010`,
`9101-9130`, `2001-2030`, `3001-3030` (spent); `2101-2130`, `3101-3130`, `3201-3230` (reserved for
other purposes, not usable here); `4001-4030`, `4101-4130` (final-evaluation reserves, now also
spent per `TASK-112`/`TASK-113`/`TASK-114`'s own use, and per this task's own Step 3).

## Range adopted

**`5001-5030`** — 30 seeds, the same size as every prior reserve in this ledger. Chosen as the
next unused thousand-block after `4101-4130`, following this project's own existing numbering
convention (`1001-, 2001-/2101-, 3001-/3101-/3201-, 4001-/4101-`) rather than an arbitrary or
hand-picked value.

## Verification method and why a naive whole-repo digit grep is not the right check

A first attempt — a literal, digit-boundary-safe (even hex-boundary-safe, to rule out sha256/sha1
substrings) grep for the bare 4-digit tokens `5001`-`5030` anywhere in tracked files and across
`git log --all -p` — found **all 30 numbers**, hundreds of times each
(`step1_scan_shortlist_overlap.py`'s sibling diagnostic, not committed as a separate file; see the
raw counts below). Inspecting the hits showed why: this repo's synthetic data files and raw
JSON evidence contain enormous amounts of incidental 4-digit numeric content with no relationship
to seeds at all — row counts (`"development_rows": 5005`), exposure counts
(`"n_exposed": 5002`), decimal fractions whose digits-after-the-point happen to read as a 4-digit
number (`"frac_hz_lt_hc": 0.5025`), dollar/harm amounts (`"harm_per_booking": 776.5005`), and
`git log -p` hunk-header line numbers. None of these are the project's own seed-range notation,
and demanding zero occurrences of this kind for *any* 4-digit range would reject every possible
choice (every sampled run below `3001-3030`/`4001-4030`/etc. would show the identical pattern if
checked the same naive way). The standard that actually matches `ADR-116`'s intent and this
project's own prior practice (`docs/benchmark/task-107-freeze-manifest.md` §4's seed-range ledger;
every prior range was verified as "never appeared anywhere... as a seed range", not "the bare
digits never occur anywhere in any numeric data") is: has this range, or any seed in it, ever been
used **as a seed** — in a `seed`/`seeds`/`SEED` context, a `seed-<N>.*` filename, or the
`<N>-<N>` / `range(<N>` range notation this project's own scripts and docs already use for every
prior reserve.

## The real check (`step4_grep_verify_fresh_reserve.py`)

1. **Wide seed-proximity pattern**: `5001`-`5030` (digit-boundary-safe) within 40 characters of
   the word "seed" in either direction, case-insensitive — catches `SEEDS = list(range(5001,`,
   `seed-5001.json`, `` `5001-5030`, reserved for... `` style prose, and `seeds 5001-5030` alike.
2. **Explicit range-literal pattern**: `5001-5030`/`5001, 5030`/`range(5001` substrings, regardless
   of "seed" proximity — this project's own markdown range notation.
3. Applied to: (a) every tracked working-tree file (`git ls-files`, so `.venv`/untracked/gitignored
   content is correctly excluded — it is not "this project's history or committed files"); (b)
   every content line (`+`/`-`, diff metadata excluded) across `git log --all -p -- .`, i.e. every
   commit on every branch, not just the current `HEAD`.

**Sanity check that the pattern itself actually works** (run against the real, already-used
`4001`/`4030` range before trusting a zero result for `5001-5030`):

```
SEEDS = list(range(4001, 4031))  -> False   (gap too wide for the narrow first-draft pattern;
                                               confirmed the WIDENED 40-char-gap pattern used in
                                               the real script catches this case)
seed-4001.json                   -> True
4001-4030                        -> True    (range-literal pattern)
seeds 4001                       -> True
```

**Result for `5001-5030`, full repo + full history:**

```
=== Tracked files: wide seed-proximity OR range-literal hits: 0 ===

=== git history content lines: wide seed-proximity OR range-literal hits: 0 ===
```

Zero hits, in any tracked file (current state) and in every commit's content lines on every
branch. `5001-5030` has never been used as a seed, a seed filename, or a seed-range literal
anywhere in this project's history. Full script: `step4_grep_verify_fresh_reserve.py`; raw output:
`step4-grep-verification-output.txt`.

## Adoption — NOT EXERCISED

`5001-5030` is **not** adopted as a `TASK-115` evaluation reserve: Step 3's Mechanism PASS bar was
not met (§3 of the results document), so per the binding order this task never reaches Step 4. No
run of either engine (baseline or modified) on any seed in this range occurred at any point in
this task. The verified-untouched status recorded above is still accurate and reusable by a future
task; it is simply not being spent by this one.
