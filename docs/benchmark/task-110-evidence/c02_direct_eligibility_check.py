"""TASK-110 S3 counterfactual for C02: direct, real-function demonstration that the 2-literal
canonical rule is itself genuinely eligible/scorable (confirmed by calling the real, unmodified
`_metric`/`_eligible` directly), while its two individual single literals each fail `_eligible`'s
harm-direction check alone on this seed's real development split -- which is exactly why
`discover_candidates`'s own incremental depth-1-then-depth-2 construction never reaches it (depth
2's frontier is only built by extending depth-1's real `scored`/beam survivors).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPOSITORY / "packages/analytics/src"),
    str(REPOSITORY / "packages/schemas/src"),
    str(REPOSITORY / "scripts"),
    str(REPOSITORY / "docs/benchmark/task-107-evidence"),
]

import v2_common as vc  # noqa: E402
from policy_analytics import synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    Condition,
    DiscoveryConfig,
    _eligible,
    _exposed_rows,
    _metric,
)
from policy_analytics.outcomes import primary_outcome  # noqa: E402

OUT = Path(__file__).resolve().parent


def main(seed: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        outcome = primary_outcome()
        config = DiscoveryConfig(seed=seed)
        rule = tuple(
            sorted(
                [
                    Condition("customer_segment", "eq", "corporate"),
                    Condition("destination", "eq", "Rome"),
                ]
            )
        )
        m = _metric(draw.frame, rule, outcome, "development")
        result = {
            "seed": seed,
            "full_rule_metric": {
                "n_exposed": m.n_exposed,
                "support": m.support,
                "harm_per_booking": m.harm_per_booking,
            },
            "full_rule_eligible": _eligible(m, config),
            "single_literal_metrics": {},
        }
        for removed in rule:
            parent = tuple(c for c in rule if c != removed)
            pm = _metric(draw.frame, parent, outcome, "development")
            result["single_literal_metrics"][f"{parent[0].feature} {parent[0].operator} {parent[0].value}"] = {
                "n_exposed": pm.n_exposed,
                "harm_per_booking": pm.harm_per_booking,
                "eligible_alone": _eligible(pm, config),
            }
        (OUT / f"c02-direct-eligibility-check-seed-{seed}.json").write_text(
            json.dumps(result, indent=1, sort_keys=True)
        )
        print(json.dumps(result, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4001)
