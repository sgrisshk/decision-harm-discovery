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
2. C constrains at least one feature of P's rule other than L's own feature (any operator/threshold; the recall match already establishes compatibility).

Otherwise T stays in `matched_traps`. Evaluated independently per trap; C is a trap iff any trap remains. `is_true_pattern`, `is_trap`, `is_noise`, trap
appeared/promoted and recovery all read the filtered `matched_traps`; nothing else is touched. A missing or unparsable pattern `rule` never exempts (fails closed).

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

## 5. Edge cases

* **Candidate exactly equal to the apparent feature** (`supplier=Atlas`), even when it recall-matches P04 (recall 1.0): stays T02. Tested.
* **Matches both a pattern and a trap at overlap thresholds:** the pattern match is unchanged; only the trap flag is decided by section 3. A candidate that recovers P03 with its own extra features is a pattern; it is a trap iff another trap's literal remains (e.g. P03 rule plus `supplier=Atlas` -> T02 only). Tested.
* **P03/P04/P06 exact rules:** pattern, not trap. Tested.
* **T03/T04 candidates from the TASK-073/TASK-083 evidence** (`paid_search AND discount_rate>=0.08`, no matched pattern; `discount_rate>=0.05 AND bank_transfer`, matches P06; `paid_search AND discount_rate>=0.03`, matches P03): stay traps (their extra feature is not a feature of the pattern whose rule contains the literal). The `TASK-073` and `TASK-083` official evaluation files are not in the available `artifacts/`; the identical rules appear in `task-028-task-064-beam-001`, `task-060-iteration-004*`, `task-060-remediation-001` and are used as fixtures and in the rescoring.
* **Trap literal + a feature of a different pattern that lacks the literal** (e.g. `bank_transfer AND supplier=BlueWing` matching P01): stays T04.
* **Boolean literal** (P05/T05): handled by the same coercion.
* **Pre-existing, unchanged:** `_matches_trap` hashes condition values, so a list-valued condition would raise `TypeError`; real candidates do not carry list values. Not touched.

## 6. Not decided here

Whether recovery of a pattern by a candidate that also covers other patterns/traps counts as *specific* recovery, which literal-containment semantics v2 should use, and the P03/P04/P06 "positive versus trap" precedence for the v2 benchmark are `TASK-107` (`ADR-106` Decisions 3 and 4). This specification only makes the v1 scorer stop scoring a correct pattern rule as a trap.
