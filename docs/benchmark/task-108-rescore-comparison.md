# TASK-108 - Original versus rescored archived evaluations

Original values are the archived `TASK-028` evaluation outputs, left untouched (nothing under `artifacts/` or `docs/benchmark/task-103-evidence` was written, and no
`decision-gate.md` entry was edited). Rescored values apply only the corrected trap-vs-pattern classification
(`docs/benchmark/task-108-scorer-trap-classification-spec.md`); the lenient 0.5 recall match is the archived `matched_patterns`, not recomputed.
Machine-readable: `docs/benchmark/task-108-rescore-comparison.json` (produced by `scripts/rescore_task108_trap_classification.py`).

Two independent checks agree: (1) the rescorer recomputes each archived metric from the archived scores and equals the archived value in all 12 runs
(`recomputed_original_metrics_equal_archived_metrics: true`); (2) a full replay of the real `evaluate_benchmark.main()` on the 10 `artifacts/evaluation` runs
(`docs/benchmark/task-108-replay-crosscheck.txt`) differs from the archived candidate scores in exactly the candidates the rescorer lists and in no other field of any candidate.
Ground-truth sha256 matches the recorded hash for all runs that recorded one. The two TASK-103 runs replay byte-identical (also a committed test).

## Where the reading changes

Only one candidate shape changes, in six archived runs: the precise P06 candidate
`booking_lead_days lt 23 AND destination eq Tokyo AND payment_method eq bank_transfer` (all three P06 features, `predictive_association`, `experiment_only`),
matched pattern `P06`, was `matched_traps=['T04']`, `is_true_pattern=False`, `is_trap=True`; rescored `matched_traps=[]`, `is_true_pattern=True`.

| Evaluation (engine) | Candidate | n_true_pattern | n_trap | Top-K precision | Econ.-weighted recall | Trap appeared: T04 | any_trap_promoted / trap_promoted map |
|---|---|---|---|---|---|---|---|
| task-058-remediation-001 (v0.2.0) | CAND-014 | 12 -> 13 | 1 -> 0 | 0.9 -> 0.9 | 45.17% -> 45.17% | True -> False | False -> False |
| task-060-iteration-002 (v0.3.1) | CAND-007 | 13 -> 14 | 1 -> 0 | 0.9 -> 0.9 | 45.17% -> 45.17% | True -> False | False -> False |
| task-060-iteration-004 | CAND-007 | 10 -> 11 | 3 -> 2 | 0.7 -> 0.7 | 45.17% -> 45.17% | True -> True (CAND-014 remains) | True -> True |
| task-060-iteration-004-g06v2 | CAND-007 | 10 -> 11 | 3 -> 2 | 0.7 -> 0.7 | 45.17% -> 45.17% | True -> True | True -> True |
| task-060-remediation-001 | CAND-004 | 6 -> 7 | 3 -> 2 | 0.4 -> 0.4 | 45.17% -> 45.17% | True -> True | True -> True |
| task-064-beam-001 (v0.5.0) | CAND-007 | 9 -> 10 | 3 -> 2 | 0.7 -> 0.7 | 45.17% -> 45.17% | True -> True | False -> False |

Unchanged runs (no candidate changes): `task-028-benchmark-evaluation` (task-015 official), the b2b comparable run, both ecommerce runs, TASK-103 run1 and run2.

* **Metrics that move:** none of Top-K precision, economic-weighted recall, `trap_promoted` map or `any_trap_promoted` changes in any run. Only the per-candidate labels, the
  `n_true_pattern`/`n_trap` counts, and (in `task-058-remediation-001` and `task-060-iteration-002`) `trap_appeared_as_candidate["T04"]` (True -> False) change.
  Economic recall is unchanged because P06 was already recovered in each of these runs through the broad lenient candidate (`booking_lead_days lt 23 AND discount_rate ge 0.05`, `matched_patterns=[P01,P06]`),
  as recorded in `task-106-fn-autopsy.md` D2.
* **Genuine traps preserved:** `T03` `acquisition_channel eq paid_search AND discount_rate ge 0.03` (`shadow_policy`, matches P03) in `task-060-iteration-004*`/`task-060-remediation-001`,
  `T03` `... discount_rate ge 0.08` (no pattern) and `T04` `discount_rate ge 0.05 AND payment_method eq bank_transfer` (matches P06) remain traps in every run they appear in.
* **No P03 or P04 candidate in any archived run** carries the exact-rule shape, so the fix changes no P03/P04 reading historically (they are covered by the unit tests).
* **The `TASK-073` and `TASK-083` official evaluation files** (`task-028-task-073-official-001.json` and the `TASK-083` run) are not among the available archives (`artifacts/evaluation` has 10 files, none of them these), so they were not rescored;
  the same candidate rules appear in the archived files above.

## Revision R1-R5 disclosures (documentation only; the .json evidence is untouched)

* **Changed set.** Under the rule no historical verdict changes. The (trap, pattern) pairs whose classification can change are exactly T03/P03, T02/P04, T04/P06 and T05/P05. The promoted
  `TASK-073` T03/T04 candidates cannot be reclassified: their extra feature `discount_rate` is in neither P03's nor P06's rule.
* **Unrescored.** `artifacts/blind/task-060-iteration-20260820-003.candidates.json` CAND-007 has the same changing shape (`lead<23 AND Tokyo AND bank_transfer`) but no evaluation file exists for that run, so it
  was not rescored. The `TASK-073`/`TASK-083` official evaluation files are missing (above).
* **Simplified description elsewhere.** `decision-gate.md` (line ~164, `task-058-remediation-001`) calls the changing candidate `Tokyo AND bank_transfer` (2 conditions); the archived rule is
  `booking_lead_days < 23 AND destination eq Tokyo AND payment_method eq bank_transfer` (T04 was `experiment_only` there). Not edited.
* **Machine-local paths.** `task-108-rescore-comparison.json` has two `candidates_file` values (TASK-103 run1/run2) that are absolute paths into another agent's worktree
  (`worktrees/agent-a1487ed9c0afeab2b/...`); a machine-local-path nit, not edited.
* **Exemption is only syntactic (F1).** The exemption inherits the lenient recall match's superset permissiveness, so trap-literal plus a vacuous pattern-feature condition
  (e.g. `bank_transfer AND booking_lead_days<400`, exposure 3077 = bare T04) is un-flagged. No such shape exists in any archived run, so none of the numbers above are affected. Details, the reproduced
  exposure table, the "Risk until `TASK-107` lands" note and the `TASK-107` open item are in the specification, Sections 3 and 8.
* **Coverage and failure modes.** P03/P04/P05 exact-rule shapes are unit-test-only; the mutation test is a wholesale revert to `_matches_trap` (it does not mutate conditions (1)/(2)); vacuous-threshold cases are untested.
  `_genuine_trap_matches` does an unguarded `patterns_by_id[pid]` (`KeyError` if an archive is replayed against the wrong ground truth); the pre-existing `_matches_trap` `TypeError` on list-valued conditions is unchanged.

## Changed historical verdict

**None found.** No archived run's `trap_promoted` map, `any_trap_promoted`, Top-K precision or economic-weighted recall changes, so no recorded hard-disqualifier or graded-metric verdict changes on the
archived inputs available here. The reading that changes is qualitative and already disclosed in `task-106-fn-autopsy.md` D2: the old precise P06 candidate is a pattern recovery, not a trap (Reported, not adjudicated;
the `TASK-073`/`TASK-083` verdicts could not be rescored for the reason above).
