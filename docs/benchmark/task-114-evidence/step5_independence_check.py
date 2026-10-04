"""TASK-114 Step 5 -- independence check, applying `TASK-113`'s own corrective lesson directly
(`ADR-115` Decision 4 / this task's binding "Bar" paragraph): verify that a qualifying target's
positive-pattern evidence does not reduce to ONE shared underlying event/literal reflected across
multiple target labels.

Unlike `TASK-113` (where the non-independence was literally the SAME candidate at the SAME seed
being credited to 7 different target labels), here every target's canonical literals are target-
specific by design (`synthetic_benchmark_v2_targets.DESIGNS`) -- no two Core targets share an
IDENTICAL canonical rule. The concrete, checkable non-independence risk at THIS level is narrower:
two different targets can still share one exact literal (same feature AND same value) among their
own canonical conditions (e.g. `C14` and `H01` both have `supplier=BlueWing`), so a chain that
happens to start from that shared literal produces an IDENTICAL broad "step 0" rule (same seed,
same conditions, same `_development_score`) for both targets -- not the same full comparison (the
literals added afterward differ, so the final, more-specific rule and its target-affected mask
differ), but a PARTIALLY shared root worth disclosing and, more importantly, worth testing whether
it is load-bearing.

This script answers, per target that `step2b_classify_method_b.py` found qualifying: does the
target still qualify ("positive pattern on >50% of applicable seeds") using ONLY its starting
literals that are NOT exactly shared (same feature + same value) with any OTHER qualifying
target's own canonical literals? A target that still qualifies this way is independently
confirmed; a target that does not is flagged explicitly as dependent on a shared literal with
another qualifying target, and is EXCLUDED from the final independent count unless its
shared-literal reliance is disclosed and justified separately in the results document.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEP2B = json.loads((HERE / "step2b-classification-results.json").read_text(encoding="utf-8"))
OUT = HERE / "step5-independence-results.json"


def canonical_literal_set(target_id: str) -> set[tuple]:
    import sys

    sys.path[:0] = [str(HERE)]
    import step1_build_chains as s1  # noqa: E402

    return {
        (c.feature, c.operator, c.value) if c.operator == "eq" else (c.feature, c.operator)
        for c in s1.canonical_conditions(target_id)
    }


def main() -> None:
    summary = STEP2B["per_target_summary"]
    detail = STEP2B["per_target_detail"]
    qualifying = sorted(t for t, s in summary.items() if s.get("chainable") and s.get("qualifies_on_most_applicable_seeds"))

    # Build each qualifying target's canonical literal "identity" set: (feature, value) for eq
    # literals (exact-value sharing is the only kind that produces a byte-identical broad rule
    # across targets); (feature, operator) for ge/lt literals is tracked too but reported
    # separately since different thresholds on the same feature are NOT the same rule/event, just
    # the same feature reused with a different value -- not pooled into the "shared" exclusion.
    literal_sets: dict[str, set[tuple]] = {t: canonical_literal_set(t) for t in qualifying}

    # An eq literal (feature, operator, value) is "shared" if >=2 qualifying targets have it
    # identically. ge/lt literals are tracked as (feature, operator) "same feature family" only,
    # reported for transparency but NOT treated as a disqualifying share (different threshold =
    # different rows, see this task's own results doc for the argument).
    eq_literal_owners: dict[tuple, list[str]] = {}
    for t, lits in literal_sets.items():
        for lit in lits:
            if len(lit) == 3:  # eq literal: (feature, operator, value)
                eq_literal_owners.setdefault(lit, []).append(t)
    shared_eq_literals = {lit: owners for lit, owners in eq_literal_owners.items() if len(owners) >= 2}

    report = {}
    for t in qualifying:
        pt = detail[t]
        results = list(pt["seed_start_results"].values())
        shared_literal_values = {
            lit[2]
            for lit in literal_sets[t]
            if len(lit) == 3 and lit in shared_eq_literals
        }
        shared_literal_full = [lit for lit in literal_sets[t] if len(lit) == 3 and lit in shared_eq_literals]

        # Recompute qualification using only starts whose starting literal is NOT one of the
        # shared-eq literals.
        per_seed_unique_positive: dict[int, bool] = {}
        per_seed_unique_applicable: set[int] = set()
        per_literal_rate: dict[str, dict] = {}
        for r in results:
            lit = r["starting_literal"]
            lit_key = f"{lit['feature']} {lit['operator']} {lit['value']!r}"
            per_literal_rate.setdefault(lit_key, {"n": 0, "pos": 0, "is_shared": False})
            per_literal_rate[lit_key]["n"] += 1
            if r["any_positive_transition"]:
                per_literal_rate[lit_key]["pos"] += 1
            is_shared_literal = lit["operator"] == "eq" and (lit["feature"], "eq", lit["value"]) in shared_eq_literals
            per_literal_rate[lit_key]["is_shared"] = is_shared_literal
            if is_shared_literal:
                continue
            per_seed_unique_applicable.add(r["seed"])
            if r["any_positive_transition"]:
                per_seed_unique_positive[r["seed"]] = True

        n_app = len(per_seed_unique_applicable)
        n_pos = sum(1 for s in per_seed_unique_applicable if per_seed_unique_positive.get(s))
        independently_qualifies = n_app > 0 and n_pos / n_app > 0.5

        report[t] = {
            "canonical_eq_literals_shared_with_other_qualifying_targets": [
                {"feature": f, "operator": o, "value": v} for (f, o, v) in shared_literal_full
            ],
            "shared_with_targets": {
                f"{f}={v!r}": [o for o in owners if o != t]
                for (f, _op, v), owners in shared_eq_literals.items()
                if t in owners and any(o != t for o in owners)
            },
            "per_starting_literal_positive_rate": per_literal_rate,
            "n_seeds_applicable_excluding_shared_literal_starts": n_app,
            "n_seeds_positive_excluding_shared_literal_starts": n_pos,
            "fraction_positive_excluding_shared": (n_pos / n_app) if n_app else None,
            "independently_qualifies_excluding_shared_literal_starts": independently_qualifies,
        }

    n_independent = sum(1 for v in report.values() if v["independently_qualifies_excluding_shared_literal_starts"])
    out = {
        "qualifying_targets_method_b": qualifying,
        "n_qualifying_targets_method_b": len(qualifying),
        "shared_eq_literals_across_qualifying_targets": {
            f"{f} eq {v!r}": owners for (f, _op, v), owners in shared_eq_literals.items()
        },
        "per_target_independence_detail": report,
        "n_targets_independently_qualifying_excluding_shared_literals": n_independent,
        "bar_met_independently": n_independent >= 5,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"qualifying (Method B, raw): {qualifying}")
    print(f"shared eq literals: { {f'{f} eq {v!r}': o for (f,_o,v),o in shared_eq_literals.items()} }")
    for t, v in report.items():
        print(f"{t}: independent={v['independently_qualifies_excluding_shared_literal_starts']} "
              f"(n_app={v['n_seeds_applicable_excluding_shared_literal_starts']}, "
              f"n_pos={v['n_seeds_positive_excluding_shared_literal_starts']}) "
              f"shared_literals={v['canonical_eq_literals_shared_with_other_qualifying_targets']}")
    print(f"n independently qualifying: {n_independent} (bar >=5: {n_independent >= 5})")


if __name__ == "__main__":
    main()
