# TASK-117 — Where the right rule is lost: lineage reconstruction and one-step replay

**Verdict: `H117` SUPPORTED** against the criterion fixed in
`task-117-evidence/preregistration.md` (at least 4 of the 5 strong targets share one first point of
irreversible divergence, and overriding that one step restores Specific recovery on most applicable
seeds). All five targets share the same point: **final top-K selection**.

## What was run

* Frozen engine `discovery-engine-v0.6.2` (`engine.py` sha256 `fefceeaa...e4549`), validation contract
  1.3.0, benchmark v2, evaluation seeds 4001-4030. The hash was verified before and after every seed.
* `task-117-evidence/trajectory.py` re-drives the search and the post-search selection with the
  engine's own functions and logs every rule that satisfies the Specific metric for the strong targets
  `C04, C06, C09, C14, C15` (control `C07`).
* **Fidelity:** the reconstructed final top-15 equals the committed TASK-109 candidates, condition for
  condition and in order, and the hypothesis count matches, on **30 of 30** seeds.
* **One-step replay:** on each seed where a target was missed, the highest-scoring right rule replaces
  the 15th selected rule; validation, multiplicity family and scorer run unchanged.

## Results

| Target | Seeds missed | First divergence | Replay restores Specific | Rank of best right rule (min / median / max) | Score vs. 15th selected (min / median / max) |
|---|---|---|---|---|---|
| C04 | 30 | final selection 30/30 | 28/30 | 2,338 / 3,737 / 7,451 | 0.22 / 0.42 / 0.58 |
| C06 | 30 | final selection 30/30 | 25/30 | 1,021 / 4,279 / 13,594 | 0.11 / 0.41 / 0.72 |
| C09 | 29 | final selection 29/29 | 28/29 | 89 / 519 / 1,018 | 0.52 / 0.67 / 0.95 |
| C14 | 9 | final selection 9/9 | 9/9 | 63 / 187 / 465 | 0.67 / 0.80 / 1.02 |
| C15 | 29 | final selection 29/29 | 29/29 | 282 / 995 / 2,393 | 0.42 / 0.62 / 0.90 |

Ranks are among roughly 24,000 scored two- and three-condition rules, by effective (stability-credited)
score. In total the replay restores **119 of 127** target-seeds.

* On every seed where a target was missed, at least one right rule had been generated, found eligible
  and scored. **No right rule was lost at generation.**
* **Every failed replay failed at validation, not selection.** Five of C06's cases forced the
  two-literal partial `returning AND Reykjavik`, which fails multiplicity or temporal stability.
* **Twice for C14 the right rule outscored the 15th selected rule and was still left out:** the greedy
  selection is by marginal gain under a diversity penalty, not by score alone.

## Reading

The engine finds the right rules, and validation accepts them. The step that loses them is the ranking
by the development score, followed by the diversity rule. Earlier studies located a "generation gap"
for C04, C06 and C15. That gap concerns the one-literal refinements of already-shortlisted parents,
not the main search.

The replay uses knowledge of the answer, so it is a diagnostic, not a method. Reliable Specific Recall
from the last valid blind measurement (TASK-109) remains 1/11, and Exact 0/11.

## Files

`task-117-evidence/preregistration.md` (definitions and verdict rule, written before the run),
`trajectory.py` (re-driven search, lineage, replay), `verdict.py` and `verdict.json` (pre-registered
aggregation), and `raw/seed-4001.json` … `seed-4030.json`.
