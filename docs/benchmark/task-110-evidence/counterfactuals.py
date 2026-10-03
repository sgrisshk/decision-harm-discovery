"""TASK-110 step D: mandatory counterfactuals. Every call here uses the REAL, unmodified
`discover_candidates` / `_select_expansion_beam` / `_metric` / `_eligible` functions imported
directly from `policy_analytics.discovery.engine` -- nothing in `packages/` is copied or edited.
Where a counterfactual needs "one constraint diagnostically lifted", it does so exclusively
through `DiscoveryConfig`'s own pre-existing, already-shipped fields (e.g. `reserve_k1_slot`,
`beam_rules_per_structure`) -- these are not new tunables invented for this task, and nothing here
is persisted as a new default or used to recompute any TASK-109 score.
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import replace
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
    _beam_structure,
    _eligible,
    _metric,
    discover_candidates,
)
from policy_analytics.outcomes import primary_outcome  # noqa: E402

OUT = Path(__file__).resolve().parent


def rule_in_output(doc, rule_conditions: set[str]) -> dict | None:
    for c in doc["candidates"]:
        rendered = {f"{cc['feature']} {cc['operator']} {cc['value']}" for cc in c["conditions"]}
        if rendered == rule_conditions:
            return c
    return None


def counterfactual_c08_reserve_k1(seeds: list[int]) -> dict:
    """S4 claim: C08's single-literal canonical rule ('payment_method eq wallet') is individually
    eligible and well-ranked at depth 1 on every seed checked (see `search_trace.py` output), but
    is structurally excluded from the final top-K by `discover_candidates`'s own two-phase
    "interactions fill top_k first, singles only as fallback" design UNLESS
    `DiscoveryConfig.reserve_k1_slot=True` (an already-shipped, off-by-default flag, `TASK-097`).
    Demonstrates: (a) with the real default config (reserve_k1_slot=False, exactly what TASK-109
    used) the wallet single is absent from the final candidates; (b) with only that one existing
    flag flipped and nothing else changed, the single is admitted (or the mechanism's own
    eligible/activated bookkeeping explains why not)."""
    out = {}
    for seed in seeds:
        with tempfile.TemporaryDirectory(prefix=f"task110-cf-c08-{seed}-") as tmp:
            draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
            default_cfg = DiscoveryConfig(seed=seed)
            reserve_cfg = replace(default_cfg, reserve_k1_slot=True)
            doc_default = discover_candidates(draw.frame, draw.features, primary_outcome(), default_cfg)
            doc_reserve = discover_candidates(draw.frame, draw.features, primary_outcome(), reserve_cfg)
            wallet = {"payment_method eq wallet"}
            out[seed] = {
                "default_reserve_k1_slot_False": {
                    "wallet_single_in_final_top_k": rule_in_output(doc_default, wallet) is not None,
                    "k1_reservation_metadata": doc_default["k1_reservation"],
                },
                "counterfactual_reserve_k1_slot_True": {
                    "wallet_single_in_final_top_k": rule_in_output(doc_reserve, wallet) is not None,
                    "k1_reservation_metadata": doc_reserve["k1_reservation"],
                },
            }
            print(f"seed {seed}: C08 counterfactual done -> {out[seed]}", flush=True)
    return out


def counterfactual_c04_structural_reserve(seeds: list[int]) -> dict:
    """S4 claim: C04's canonical pair 'supplier eq Cedar AND trip_duration_days ge 8' is eligible
    and scored at depth 2 but excluded from `_select_expansion_beam`'s structural-reserve quota
    (`beam_rules_per_structure=2` by default) for its own (feature,operator) shape
    [('supplier','eq'), ('trip_duration_days','ge')]. Demonstrates: (a) which two higher-scoring
    rules of the SAME shape occupy that structure's reserve slots instead, under the real default
    config; (b) with only `beam_rules_per_structure` raised (an already-shipped, pre-existing
    config field -- not a new tunable) the target pair survives to the beam. Diagnostic only;
    never persisted as a new default, never used to rescore TASK-109."""
    out = {}
    target_rule = tuple(sorted([Condition("supplier", "eq", "Cedar"), Condition("trip_duration_days", "ge", 8.0)]))
    shape = _beam_structure(target_rule)
    for seed in seeds:
        with tempfile.TemporaryDirectory(prefix=f"task110-cf-c04-{seed}-") as tmp:
            draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
            outcome = primary_outcome()
            import polars as pl

            from policy_analytics.discovery.engine import _atoms, _select_expansion_beam

            default_cfg = DiscoveryConfig(seed=seed)
            development = draw.frame.filter(pl.col("split_label") == "development")
            atoms = _atoms(development, draw.features, default_cfg)
            scored = {}
            frontier = [(a,) for a in atoms]
            # depth 1
            for rule in frontier:
                m = _metric(draw.frame, rule, outcome, "development")
                if _eligible(m, default_cfg):
                    from policy_analytics.discovery.engine import _development_score

                    scored[rule] = (_development_score(m, 1, default_cfg), m)
            beam1 = _select_expansion_beam(scored, 1, default_cfg)
            # depth 2 frontier from beam1
            next_frontier = []
            for rule in beam1:
                used = {c.feature for c in rule}
                for atom in atoms:
                    if atom.feature in used:
                        continue
                    next_frontier.append(tuple(sorted((*rule, atom))))
            frontier2 = sorted(set(next_frontier))
            from policy_analytics.discovery.engine import _development_score

            scored2 = dict(scored)
            for rule in frontier2:
                m = _metric(draw.frame, rule, outcome, "development")
                if _eligible(m, default_cfg):
                    scored2[rule] = (_development_score(m, 2, default_cfg), m)
            beam2_default = _select_expansion_beam(scored2, 2, default_cfg)
            relaxed_cfg = replace(default_cfg, beam_rules_per_structure=10)
            beam2_relaxed = _select_expansion_beam(scored2, 2, relaxed_cfg)
            same_shape_rules = sorted(
                (r for r in scored2 if len(r) == 2 and _beam_structure(r) == shape),
                key=lambda r: -scored2[r][0],
            )
            out[seed] = {
                "target_pair_in_scored": target_rule in scored2,
                "target_pair_score": scored2.get(target_rule, (None,))[0],
                "target_pair_rank_within_its_own_shape": (
                    same_shape_rules.index(target_rule) + 1 if target_rule in same_shape_rules else None
                ),
                "n_rules_sharing_this_shape": len(same_shape_rules),
                "top2_rules_of_same_shape_that_occupy_the_reserve_quota": [
                    {
                        "conditions": [f"{c.feature} {c.operator} {c.value}" for c in r],
                        "score": scored2[r][0],
                    }
                    for r in same_shape_rules[:2]
                ],
                "survives_beam_default_beam_rules_per_structure_2": target_rule in beam2_default,
                "survives_beam_counterfactual_beam_rules_per_structure_10": target_rule in beam2_relaxed,
            }
            print(f"seed {seed}: C04 structural-reserve counterfactual done", flush=True)
    return out


def main() -> None:
    seeds_c08 = [4001, 4002, 4019]
    seeds_c04 = [4001, 4002]
    result = {
        "c08_reserve_k1_slot": counterfactual_c08_reserve_k1(seeds_c08),
        "c04_structural_reserve_quota": counterfactual_c04_structural_reserve(seeds_c04),
    }
    (OUT / "counterfactuals-result.json").write_text(json.dumps(result, indent=1, sort_keys=True, default=str))
    print("wrote", OUT / "counterfactuals-result.json")


if __name__ == "__main__":
    main()
