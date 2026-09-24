# TASK-108 - Specification: trap match versus legitimate pattern match in the scorer

**Owner:** STATISTICS (lead), ARCHITECT (support). Binding on `ADR-106` Decision 1 and `docs/benchmark/task-106-fn-autopsy.md` section 5.4.
Scope: only the trap-vs-pattern classification in `scripts/evaluate_benchmark.py`. The lenient recall match (`recall >= 0.5`), search, engine, gates,
thresholds, generator and catalogue are unchanged.

## 1. The defect being specified

Before this task the scorer set `matched_traps` for a candidate whenever a trap's `apparent_feature` literal was among the candidate's conditions
(`_matches_trap`), then `is_true_pattern = bool(matched) and not matched_traps` and recovery excluded `is_trap` candidates. Three ground-truth
patterns have an exact rule that contains a trap's apparent-feature literal, so a candidate that reproduces the pattern was classified as the trap:

| Pattern | Rule literal | Trap | Trap apparent feature |
|---|---|---|---|
| P03 | `acquisition_channel=paid_search` | T03 | `acquisition_channel=paid_search` |
| P04 | `supplier=Atlas` | T02 | `supplier=Atlas` |
| P06 | `payment_method=bank_transfer` | T04 | `payment_method=bank_transfer` |

(P05 / T05 `manual_exception=true` is the same shape; the ground truth itself states: "P05 is a genuine interaction; the main effect is a trap".
Non-travel domains follow the same convention: `E05`/`ET05`, `B07`/`BT04`, `E03`/`ET03`.)

## 2. What the ground truth says

* A **trap** (`confounding_traps[]`) is a *single-literal* deceptive rule: one `apparent_feature` (`col=value`), `direct_effect = 0`, its association
  with the outcome produced entirely by the listed `confounded_by` features. The trap object is "the apparent feature, taken as the explanation".
* A **pattern** (`patterns[]`) is a multi-condition `rule` with a real effect and an `affected_*_ids` set.
* The travel ground truth (and every `synthetic_data_domains/*` ground truth) gives each pattern `rule` as `"a=x AND b>=3 AND m IN [..]"`, parseable
  into constrained features and equality literals. For the three overlaps the trap's `confounded_by` features are exactly the pattern's other rule features
  (T02: `trip_duration_days`, `booking_month`; T04: `booking_lead_days`, `destination`; T03: `customer_type`, `installments`, plus `discount_rate`).

So the deceptive object is the apparent-feature literal *standing for the effect*. A rule that carries the literal *together with the pattern's other defining
conditions* is the pattern (an interaction), not the trap; the literal alone, or the literal plus features that are not part of a pattern whose rule contains
it, is the trap.

## 3. The rule

For a candidate C, matched patterns `M(C)` (unchanged lenient recall >= 0.5), and a trap T whose apparent literal L is a condition of C (the existing literal
check), T is **not** matched (C is not a trap on account of T) iff there exists P in `M(C)` such that

1. L is one of the equality literals of P's ground-truth `rule` (same `(feature, "eq", value)` shape and `true`/`false` coercion as `_parse_apparent_feature`), and
2. C constrains at least one feature of P's rule other than L's own feature (any operator/threshold). **Correction (revision R1, F1):** an earlier draft added "the recall match
   already establishes compatibility". That is wrong. Condition 2 is purely syntactic (feature names only). The lenient recall match (`recall >= 0.5`) accepts any *superset* of
   a pattern's affected set, so it does not establish that the extra condition is compatible with, or specific to, the pattern; see "Known limitation" below.

Otherwise T stays in `matched_traps`. Evaluated independently per trap; C is a trap iff any trap remains. `is_true_pattern`, `is_trap`, `is_noise`, trap
appeared/promoted and recovery all read the filtered `matched_traps`; nothing else is touched. A missing or unparsable pattern `rule` never exempts (fails closed).

**Known limitation (revision R1, F1; undisclosed in the original TASK-108 record; OPEN ITEM for `TASK-107`).** The exemption inherits the lenient recall match's superset
permissiveness. "A bare literal stays a trap" holds only for the literally bare rule (the literal alone). A candidate that is the trap literal plus a *vacuous* condition on a
pattern feature (a threshold that excludes no rows, or nearly none) has the same exposure as the bare trap, recall-matches the pattern exactly as the bare trap does, satisfies
condition 2 syntactically, and is therefore un-flagged although it was a trap before this task. Reproduced read-only with the real scorer code path (`_genuine_trap_matches`, real
recall against the real ground truth and the real travel dataset `travel-bookings-analytical-v1.0.0`; scratch script outside the repo):

| Candidate | Exposed n | Recall-matched | Old `matched_traps` | New `matched_traps` | Bare-trap exposure |
|---|---|---|---|---|---|
| `payment_method=bank_transfer AND booking_lead_days<400` | 3077 | P06 | T04 | none | 3077 (= bare T04) |
| `payment_method=bank_transfer AND booking_lead_days<60` | 1825 | P06 | T04 | none | 3077 |
| `acquisition_channel=paid_search AND installments>=1` | 2726 | P03 | T03 | none | 2726 (= bare T03) |
| `acquisition_channel=paid_search AND customer_type=new` | 1706 | P03 | T03 | none | 2726 |
| `acquisition_channel=paid_search AND installments>=3 AND discount_rate>=0.03` (P-feature plus non-P feature) | 431 | P03 | T03 | none | 2726 |
| `supplier=Atlas AND trip_duration_days>=1` | 2530 | P04 | T02 | none | 2530 (= bare T02) |
| `manual_exception=true AND customer_price_eur>=0` | 688 | P05 | T05 | none | 688 (= bare T05) |

The four bare rules (`bank_transfer`, `paid_search`, `Atlas`, `manual_exception`) still return their trap (T04, T03, T02, T05), as specified. `booking_lead_days`, `installments` and
`customer_type` are also `confounded_by` features of T04 and T03, so a candidate whose extra condition is a confounder of the trap, not a pattern-specific condition, is exempted. A
candidate adding one P-feature plus one non-P feature is exempt too (only condition 2's "at least one" is needed). None of these shapes exists in any archive (no historical impact,
see below), but a future *promoted* trap of this form would evade hard disqualifier 2, and the P06/T04 pair already has this exposure shape (the engine does emit trap-literal-plus-pattern-feature
candidates, e.g. the old `lead<23 AND Tokyo AND bank_transfer`, which is a genuine pattern recovery, not a vacuous one).

**Risk until `TASK-107` lands.** The discovery engine is frozen (`v0.6.2`, contract 1.3.0) and no official run is pending, so the exposure is latent. Any official run performed
before benchmark v2 must have its trap verdicts (`matched_traps`, `trap_promoted`, `any_trap_promoted`, hard disqualifier 2) **manually checked** for exempted-shape candidates,
i.e. every candidate containing a trap's apparent literal together with a matched pattern's other feature, comparing its exposure with the bare trap's.

## 4. Alternatives considered

| Option | Verdict | Why |
|---|---|---|
| A. Pattern precedence: if C matches P and P's rule contains L, never a trap | Rejected | The bare `supplier=Atlas` rule has recall 1.0 of P04 (every P04 record is Atlas), so it would become a "true pattern". The trap must stay a trap; this option hides exactly the failure the trap metric exists to catch. |
| B. Exempt only if C's condition set equals P's exact rule literals | Rejected | Real candidates never reproduce thresholds exactly (the archived old-P06 candidate has `booking_lead_days < 23` vs `< 10`); P04's `booking_month IN [...]` is not expressible by the engine. It would exempt nothing in practice, leaving the defect. |
| C. Require C to contain all of P's features | Rejected | Engine depth limit is 3; P04 (3 features incl. an inexpressible month atom) and any 4-condition pattern could never be recovered; a stricter bar is not derivable from the ground truth and would change what counts as recovery (v2 design, `TASK-107`). |
| D. Exempt if C conditions on any of T's `confounded_by` features | Rejected | Would un-flag genuine traps: `T03` `paid_search AND discount_rate>=0.03` (a `confounded_by` feature) reached `shadow_policy` in `TASK-073`-era runs and must stay a trap; and it would fail P05 (`confounded_by` does not include P05's own features), E05, B07. |
| E (chosen). L is a literal of a matched P's rule and C adds at least one other feature of P's rule | Chosen | Derived only from ground-truth `rule` and `apparent_feature` strings; keeps the bare literal and literal-plus-unrelated-feature candidates as traps; needs no threshold; touches only the overlap. |

Residual judgment (disclosed, not hidden): E requires >= 1 additional pattern feature, not all. `Atlas AND trip_duration_days>=14` that recall-matches P04 would be a
pattern. The archived evidence is insensitive to this: on every archived input the set of changed candidates is identical under "at least one" and "all features"
(only the old three-condition P06 candidate, which carries all three P06 features, changes).
That equivalence is an archive-only observation (revision R2, F2). It does not make "at least one" safe: it is not safe against vacuous thresholds (Section 3, Known limitation).
Nor would "all features" close F1: its extra conditions can also be vacuous (e.g. all three P06 features with a threshold that excludes nothing), and "all features" is impossible for P04,
whose `booking_month IN [1,2,12]` atom the engine cannot express. A specific-recovery definition that handles vacuous thresholds is an open item for `TASK-107`.

## 5. Edge cases

* **Candidate exactly equal to the apparent feature** (`supplier=Atlas`), even when it recall-matches P04 (recall 1.0): stays T02. Tested.
* **Matches both a pattern and a trap at overlap thresholds:** the pattern match is unchanged; only the trap flag is decided by section 3. A candidate that recovers P03 with its own extra features is a pattern; it is a trap iff another trap's literal remains (e.g. P03 rule plus `supplier=Atlas` -> T02 only). Tested.
* **P03/P04/P06 exact rules:** pattern, not trap. Tested.
* **T03/T04 candidates from the TASK-073/TASK-083 evidence** (`paid_search AND discount_rate>=0.08`, no matched pattern; `discount_rate>=0.05 AND bank_transfer`, matches P06; `paid_search AND discount_rate>=0.03`, matches P03): stay traps (their extra feature is not a feature of the pattern whose rule contains the literal). The `TASK-073` and `TASK-083` official evaluation files are not in the available `artifacts/`; the identical rules appear in `task-028-task-064-beam-001`, `task-060-iteration-004*`, `task-060-remediation-001` and are used as fixtures and in the rescoring.
* **Trap literal + a feature of a different pattern that lacks the literal** (e.g. `bank_transfer AND supplier=BlueWing` matching P01): stays T04.
* **Boolean literal** (P05/T05): handled by the same coercion.
* **Pre-existing, unchanged:** `_matches_trap` hashes condition values, so a list-valued condition would raise `TypeError`; real candidates do not carry list values. Not touched.
* **Vacuous-threshold candidates (revision R1, F1):** `bank_transfer AND booking_lead_days<400` and the analogous shapes are un-flagged (not a trap) although equal in exposure to the bare
  trap. This edge case is neither tested nor documented in the tests; see Section 3, Known limitation, and Section 8.
* **Changed set under the rule:** no historical verdict changes. The set of (trap, pattern) pairs whose classification can change is exactly T03/P03, T02/P04, T04/P06 and T05/P05.
  The promoted `TASK-073` T03/T04 candidates cannot be reclassified: their extra feature `discount_rate` is in neither P03's rule (`installments`, `customer_type`, `acquisition_channel`)
  nor P06's rule (`destination`, `booking_lead_days`, `payment_method`), so condition 2 fails.
* **Unguarded lookup (revision R5, F5):** `_genuine_trap_matches` reads `patterns_by_id[pid]` for each matched pattern id without a guard. A matched id absent from the ground truth raises
  `KeyError`. This is reachable only when an archive is replayed against the wrong ground truth; the recall step builds `matched` from the same `patterns_by_id`, so a normal run cannot hit it.

## 6. Not decided here

Whether recovery of a pattern by a candidate that also covers other patterns/traps counts as *specific* recovery, which literal-containment semantics v2 should use, and the P03/P04/P06 "positive versus trap" precedence for the v2 benchmark are `TASK-107` (`ADR-106` Decisions 3 and 4). This specification only makes the v1 scorer stop scoring a correct pattern rule as a trap.

## 7. Disclosure notes (revision R1-R5)

* **Test coverage (F4).** P03/P04/P05 exact-rule shapes are covered by unit tests only; no archive contains them. The "mutation" test is a wholesale monkeypatch of the call site back to
  `_matches_trap`: it proves the tests read `_genuine_trap_matches`, but it does not mutate condition (1) or condition (2) of the rule, so it does not show that either condition is
  individually load-bearing. The F1 vacuous-threshold cases are neither tested nor documented in the tests (no test added in this revision).
* **Unrescored candidate (F3).** `artifacts/blind/task-060-iteration-20260820-003.candidates.json` CAND-007 has the same changing shape (`lead<23 AND Tokyo AND bank_transfer`) but
  there is no evaluation file for that run, so it was not rescored. The `TASK-073` and `TASK-083` official evaluation files are also missing (Section 5, comparison document); both gaps stand.
* **`decision-gate.md` simplification (F3).** `decision-gate.md` (line ~164, `task-058-remediation-001`) describes the changing candidate as `destination==Tokyo AND payment_method==bank_transfer`
  (two conditions). The archived rule has a third condition, `booking_lead_days < 23`. In that run T04 was `experiment_only`. The entry was not edited (append-only record).
* **Machine-local paths (F3).** The committed `task-108-rescore-comparison.json` has two `candidates_file` values (the `task-103-evidence` run1/run2 entries) that are absolute paths into
  another agent's worktree (`worktrees/agent-a1487ed9c0afeab2b/...`). This is a machine-local-path nit; the JSON is committed evidence and was not edited.
* **Failure modes (F5).** The unguarded `patterns_by_id[pid]` lookup (Section 5) and the pre-existing `_matches_trap` `TypeError` on list-valued conditions are unchanged and undisturbed.

## 8. Open items for `TASK-107`

1. **Vacuous thresholds (from F1).** The specific-recovery definition must handle vacuous or near-vacuous thresholds on a pattern feature (and confounder features), so that trap literal plus a
   condition that removes no rows is not counted as specific pattern recovery, and is not exempted from trap status. Neither "at least one" nor "all" pattern features achieves this on
   its own (Sections 3 and 4).
2. Until then the "Risk until `TASK-107` lands" procedure in Section 3 applies.
