"""TASK-112 Step 3 -- Mechanism PASS evidence, development seeds (4001-4030).

Adapted directly from `docs/benchmark/task-111-evidence/h111_decompose.py` (same canonical rules,
same named competitors, same universal proxy, same methodology) -- the only difference is that this
script imports `_development_score`/`_metric`/`_eligible` from the engine AFTER TASK-112's Step 2
code change, so every recorded `development_score` here reflects the real, modified formula, not a
hand recomputation. Read-only with respect to the engine: no engine code is written by this script.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPO / "packages/analytics/src"),
    str(REPO / "packages/schemas/src"),
    str(REPO / "scripts"),
    str(REPO / "docs/benchmark/task-107-evidence"),
]

import v2_common as vc  # noqa: E402
from policy_analytics import synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402  pyright: ignore[reportPrivateUsage]
    DISCOVERY_METHOD_VERSION,
    Condition,
    DiscoveryConfig,
    _development_score,
    _eligible,
    _metric,
)
from policy_analytics.outcomes import primary_outcome  # noqa: E402

OUT = Path(__file__).resolve().parent
RAW = REPO / "docs/benchmark/task-109-evidence/engine-raw"
SEEDS = list(range(4001, 4031))

TARGETS = ("C02", "C04", "C06", "C08", "C09", "C11", "C12", "C14", "C15", "H01")
GUARD = "C07"
ALL_TARGETS = TARGETS + (GUARD,)


def C(feature: str, operator: str, value) -> Condition:
    return Condition(feature, operator, value)


CANONICAL: dict[str, tuple[Condition, ...]] = {
    "C02": tuple(sorted((C("destination", "eq", "Rome"), C("customer_segment", "eq", "corporate")))),
    "C04": tuple(sorted((C("supplier", "eq", "Cedar"), C("customer_segment", "eq", "leisure"), C("trip_duration_days", "ge", 8)))),
    "C06": tuple(sorted((C("destination", "eq", "Reykjavik"), C("customer_type", "eq", "returning"), C("discount_rate", "ge", 0.05)))),
    "C08": (C("payment_method", "eq", "wallet"),),
    "C09": tuple(sorted((C("destination", "eq", "Tokyo"), C("customer_segment", "eq", "leisure"), C("product_category", "eq", "standard")))),
    "C11": tuple(sorted((C("destination", "eq", "Tokyo"), C("customer_segment", "eq", "family")))),
    "C12": tuple(sorted((C("acquisition_channel", "eq", "direct"), C("product_category", "eq", "premium"), C("customer_segment", "eq", "leisure")))),
    "C14": tuple(sorted((C("customer_segment", "eq", "leisure"), C("supplier", "eq", "BlueWing"), C("discount_rate", "ge", 0.08)))),
    "C15": tuple(sorted((C("customer_type", "eq", "returning"), C("acquisition_channel", "eq", "direct"), C("trip_duration_days", "ge", 6)))),
    "H01": tuple(sorted((C("supplier", "eq", "BlueWing"), C("destination", "eq", "Zanzibar"), C("customer_type", "eq", "new")))),
    "C07": tuple(sorted((C("supplier", "eq", "BlueWing"), C("acquisition_channel", "eq", "direct"), C("party_size", "ge", 3)))),
}

U_03 = tuple(sorted((C("discount_rate", "ge", 0.03), C("manual_exception", "eq", False))))
U_05 = tuple(sorted((C("discount_rate", "ge", 0.05), C("manual_exception", "eq", False))))

NAMED_COMPETITOR: dict[str, tuple[Condition, ...]] = {
    "C02": U_03,
    "C04": tuple(sorted((C("discount_rate", "ge", 0.03), C("trip_duration_days", "ge", 4.0)))),
    "C06": U_05,
    "C08": tuple(sorted((C("discount_rate", "ge", 0.03), C("payment_method", "eq", "wallet")))),
    "C09": U_03,
    "C11": U_03,
    "C12": U_03,
    "C14": tuple(sorted((C("discount_rate", "ge", 0.08), C("supplier", "eq", "BlueWing")))),
    "C15": tuple(sorted((C("discount_rate", "ge", 0.03), C("trip_duration_days", "ge", 4.0)))),
    "H01": U_03,
    "C07": U_03,
}

EXTRA_RULES: dict[str, tuple[Condition, ...]] = {
    "C09_partial": tuple(sorted((C("destination", "eq", "Tokyo"), C("product_category", "eq", "standard")))),
}


def condition_label(rule: tuple[Condition, ...]) -> list[str]:
    return [f"{c.feature} {c.operator} {c.value}" for c in rule]


def direct_eval(frame, rule: tuple[Condition, ...], outcome, config) -> dict:
    metric = _metric(frame, rule, outcome, "development")
    eligible = _eligible(metric, config)
    k = len(rule)
    if metric is None:
        return {
            "conditions": condition_label(rule),
            "k": k,
            "eligible": False,
            "harm_per_booking": None,
            "n_exposed": None,
            "development_score": None,
        }
    score = _development_score(metric, k, config)
    return {
        "conditions": condition_label(rule),
        "k": k,
        "eligible": eligible,
        "harm_per_booking": metric.harm_per_booking,
        "n_exposed": metric.n_exposed,
        "support": metric.support,
        "n_population": metric.n_population,
        "development_score": score,
    }


def sub_rules(rule: tuple[Condition, ...], size: int) -> list[tuple[Condition, ...]]:
    import itertools

    return [tuple(sorted(c)) for c in itertools.combinations(rule, size)]


def run() -> dict:
    outcome = primary_outcome()
    per_seed: dict[int, dict] = {}

    for seed in SEEDS:
        with tempfile.TemporaryDirectory(prefix=f"task112-{seed}-") as tmp:
            draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
            config = DiscoveryConfig(seed=seed)
            frame = draw.frame

            seed_report: dict = {}
            for tid in ALL_TARGETS:
                canon = CANONICAL[tid]
                competitor = NAMED_COMPETITOR[tid]
                universal = U_03

                specific_direct = direct_eval(frame, canon, outcome, config)
                competitor_direct = direct_eval(frame, competitor, outcome, config)
                universal_direct = direct_eval(frame, universal, outcome, config) if universal != competitor else competitor_direct

                singles = [direct_eval(frame, r, outcome, config) for r in sub_rules(canon, 1)]
                subpairs = [direct_eval(frame, r, outcome, config) for r in sub_rules(canon, 2)] if len(canon) >= 3 else []

                entry = {
                    "specific_direct": specific_direct,
                    "named_competitor_direct": competitor_direct,
                    "universal_proxy_direct": universal_direct,
                    "single_literal_eligibility": singles,
                    "any_single_eligible": any(s["eligible"] for s in singles),
                    "subpair_eligibility": subpairs,
                    "any_subpair_eligible": (any(s["eligible"] for s in subpairs) if subpairs else None),
                }
                seed_report[tid] = entry

            c09_partial = direct_eval(frame, EXTRA_RULES["C09_partial"], outcome, config)
            seed_report["C09_partial_extra"] = c09_partial

            per_seed[seed] = seed_report
        print(f"seed {seed} done", flush=True)

    return per_seed


def main() -> None:
    print("DISCOVERY_METHOD_VERSION:", DISCOVERY_METHOD_VERSION)
    per_seed = run()
    (OUT / "step3-decomposition-raw-modified-engine.json").write_text(
        json.dumps(per_seed, indent=1, sort_keys=True, default=str)
    )
    print("wrote", OUT / "step3-decomposition-raw-modified-engine.json")


if __name__ == "__main__":
    main()
