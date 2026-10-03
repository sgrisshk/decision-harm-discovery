"""TASK-111 -- H111 falsification/decomposition, primary evidence script.

Read-only. Imports the real, unmodified private functions directly from
`policy_analytics.discovery.engine` (`_metric`, `_development_score`, `_eligible`, `Condition`,
`DiscoveryConfig`) -- nothing is copied, monkeypatched, or reimplemented with different logic. The
draw-construction call (`v2_common.build_draw`) and `DiscoveryConfig(seed=seed)` are byte-identical
to the calls `TASK-109`'s `run_blind_engine.py` and `TASK-110`'s `search_trace.py` already make (same
defaults, same seed, same designs module) -- this script never perturbs any config field.

Scope decision, disclosed upfront: this script computes `_development_score` and its formula
components DIRECTLY via `_metric` on named rule tuples (the canonical/specific rule, each of its
single-literal and (k-1)-literal sub-rules, and each target's identified competing broad rule),
for all 30 of TASK-109's seeds. It does NOT re-run the full atoms-generation + depth-1..3
frontier/beam search for all 30 seeds -- that full re-derivation is expensive (~144s/seed observed
for a single seed's full-depth trace, ~70+ minutes for all 30) and, for the specific 3-part
decomposition TASK-111 asks for (Delta-score decomposition, preference consistency, margin), is not
needed: those three things are properties of the real `_development_score` applied to two named,
fully-specified rules, not of the search's own traversal order.

Where TASK-111 additionally requires "counterfactual reachability" (was the specific candidate
actually constructed/eligible before the ranking decision), this script:
  (a) directly re-derives eligibility (`_eligible`) of every single-literal and (k-1)-literal
      sub-rule of each target's canonical rule, on all 30 seeds -- this is the precise necessary
      condition for the real search's depth-1-to-depth-k frontier construction (engine.py lines
      ~883, 925-932: depth d+1's frontier is built ONLY by extending whatever is in depth d's beam,
      and a rule can only be IN a depth-d beam if some eligible depth-d construction of it exists).
      Where this necessary condition fails on a seed, the rule is PROVABLY never constructed that
      seed (no appeal needed to beam capacity) -- this is the same logic `TASK-110` section 4.1 used
      for `C02`.
  (b) for the sufcient side (does an eligible anchor's sub-rule actually SURVIVE the beam to depth
      k), this script relies on TASK-110's own already-independently-reviewed 5-representative-seed
      full search traces (`docs/benchmark/task-110-evidence/search-trace-seed-{4001,4002,4010,4019,
      4030}.json`), which answered this exact question for 8 of the 10 targets by running the real,
      unperturbed `discover_candidates` depth loop end to end. This script does not re-derive that
      beam-survival fact for all 30 seeds (disclosed limitation, not silently assumed); instead it
      reports the 30-seed eligibility necessary-condition pattern as corroborating evidence for
      generalizing TASK-110's 5-seed finding, and flags explicitly wherever the two could plausibly
      diverge.

Also reads, directly and without modification, TASK-109's own committed
`docs/benchmark/task-109-evidence/engine-raw/seed-*.json` files to report each target's/rule's
actual final-selection outcome (in the real top-15 or not) on every one of the 30 seeds -- no
engine call needed for this part since `TASK-109` already ran `discover_candidates` and committed
its output.
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


# Canonical (specific/ground-truth) rules -- independently re-confirmed against
# `tg.design_index()` (see transcript); sorted tuples, matching the engine's own representation.
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

# Universal broad proxy U -- the same unrelated 2-literal structure `TASK-110` identified as the
# dominant stable best-Coverage candidate for 5/10 targets (`discount_rate`/`manual_exception`-
# anchored). Used uniformly against every target (including C07, the guard) so the kill-criterion's
# "SAME identifiable score mechanism" is tested apples-to-apples, not re-picked per target.
U_03 = tuple(sorted((C("discount_rate", "ge", 0.03), C("manual_exception", "eq", False))))
U_05 = tuple(sorted((C("discount_rate", "ge", 0.05), C("manual_exception", "eq", False))))

# Target-specific named competitor, taken directly from TASK-110's own
# `stable-coverage-candidate-summary.json` top entry per target (re-read, not re-typed from prose).
NAMED_COMPETITOR: dict[str, tuple[Condition, ...]] = {
    "C02": U_03,
    "C04": tuple(sorted((C("discount_rate", "ge", 0.03), C("trip_duration_days", "ge", 4.0)))),
    "C06": U_05,
    "C08": tuple(sorted((C("discount_rate", "ge", 0.03), C("payment_method", "eq", "wallet")))),
    "C09": U_03,
    "C11": U_03,  # C11 has no distinct named competitor in TASK-110; U is used as the probe.
    "C12": U_03,
    "C14": tuple(sorted((C("discount_rate", "ge", 0.08), C("supplier", "eq", "BlueWing")))),  # own 2-of-3 subset
    "C15": tuple(sorted((C("discount_rate", "ge", 0.03), C("trip_duration_days", "ge", 4.0)))),
    "H01": U_03,
    "C07": U_03,  # guard probe
}

# C09/C14 paired analysis: C09's own 2-literal partial (missing the true `customer_segment=leisure`)
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
            "metric": None,
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


def final_topk_membership(seed: int, rule: tuple[Condition, ...]) -> dict | None:
    """Pure read of TASK-109's own committed raw output -- no engine call."""
    d = json.loads((RAW / f"seed-{seed}.json").read_text())
    want = set(condition_label(rule))
    for c in d["score"]["candidates"]:
        if set(c["conditions"]) == want:
            return {
                "candidate_id": c["candidate_id"],
                "credited_target": c["credited_target"],
                "evidence_level": c["evidence_level"],
            }
    return None


def run() -> dict:
    outcome = primary_outcome()
    per_seed: dict[int, dict] = {}

    for seed in SEEDS:
        with tempfile.TemporaryDirectory(prefix=f"task111-{seed}-") as tmp:
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
                    "specific_in_final_top15": final_topk_membership(seed, canon),
                    "named_competitor_in_final_top15": final_topk_membership(seed, competitor),
                }
                seed_report[tid] = entry

            # C09/C14 paired analysis extra rule
            c09_partial = direct_eval(frame, EXTRA_RULES["C09_partial"], outcome, config)
            c09_partial["in_final_top15"] = final_topk_membership(seed, EXTRA_RULES["C09_partial"])
            seed_report["C09_partial_extra"] = c09_partial

            per_seed[seed] = seed_report
        print(f"seed {seed} done", flush=True)

    return per_seed


def main() -> None:
    per_seed = run()
    (OUT / "h111-decomposition-raw.json").write_text(
        json.dumps(per_seed, indent=1, sort_keys=True, default=str)
    )
    print("wrote", OUT / "h111-decomposition-raw.json")


if __name__ == "__main__":
    main()
