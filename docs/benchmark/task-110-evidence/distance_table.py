"""TASK-110 deliverable 5: distance from the best STABLE Coverage candidate to the canonical
target rule, for all 10 targets. "Stable" = the most-frequent best-coverage-candidate condition
set across the 30 TASK-109 seeds (`stable-coverage-candidate-summary.json`, itself built by
`mine_seed_evidence.py` straight from TASK-109's own committed, untouched raw evidence). Pure
read + compare; no engine call.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent

CANONICAL_LITERALS = {
    "C02": {"destination eq 'Rome'", "customer_segment eq 'corporate'"},
    "C04": {"supplier eq 'Cedar'", "customer_segment eq 'leisure'", "trip_duration_days ge 8.0"},
    "C06": {"destination eq 'Reykjavik'", "customer_type eq 'returning'", "discount_rate ge 0.05"},
    "C08": {"payment_method eq 'wallet'"},
    "C09": {"destination eq 'Tokyo'", "customer_segment eq 'leisure'", "product_category eq 'standard'"},
    "C11": {"destination eq 'Tokyo'", "customer_segment eq 'family'"},
    "C12": {
        "acquisition_channel eq 'direct'",
        "product_category eq 'premium'",
        "customer_segment eq 'leisure'",
    },
    "C14": {"customer_segment eq 'leisure'", "supplier eq 'BlueWing'", "discount_rate ge 0.08"},
    "C15": {
        "customer_type eq 'returning'",
        "acquisition_channel eq 'direct'",
        "trip_duration_days ge 6.0",
    },
    "H01": {"supplier eq 'BlueWing'", "destination eq 'Zanzibar'", "customer_type eq 'new'"},
}


def main() -> None:
    summary = json.loads((OUT / "stable-coverage-candidate-summary.json").read_text())
    rows = []
    for tid, canon in CANONICAL_LITERALS.items():
        top = summary[tid]["most_common"][0]
        stable_conds = set(top["conditions"])
        missing = sorted(canon - stable_conds)
        extra = sorted(stable_conds - canon)
        exact_matches = sorted(canon & stable_conds)
        rows.append(
            {
                "target_id": tid,
                "stable_best_coverage_rule": sorted(stable_conds),
                "n_seeds_of_30_this_exact_rule_was_the_best_coverage_candidate": top["n_seeds"],
                "canonical_literals": sorted(canon),
                "true_literals_exactly_present": exact_matches,
                "true_literals_missing": missing,
                "spurious_literals_present": extra,
                "n_true_literals_total": len(canon),
                "n_true_literals_recovered_exactly": len(exact_matches),
                "n_spurious": len(extra),
                "shares_any_true_literal": len(exact_matches) > 0,
            }
        )
    (OUT / "distance-table.json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(
            f"{r['target_id']}: recovered {r['n_true_literals_recovered_exactly']}/"
            f"{r['n_true_literals_total']} true literals, {r['n_spurious']} spurious -- "
            f"missing={r['true_literals_missing']} extra={r['spurious_literals_present']}"
        )


if __name__ == "__main__":
    main()
