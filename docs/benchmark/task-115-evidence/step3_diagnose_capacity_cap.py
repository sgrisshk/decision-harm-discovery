import sys
import tempfile
from pathlib import Path

REPO = Path("<repo>/worktrees/agent-ab783e08609be4ffa")
sys.path[:0] = [
    str(REPO / "packages/analytics/src"),
    str(REPO / "packages/schemas/src"),
    str(REPO / "scripts"),
    str(REPO / "docs/benchmark/task-107-evidence"),
]
import v2_common as vc  # noqa: E402
import policy_analytics.discovery.engine as engine  # noqa: E402
import policy_analytics.synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics.outcomes import primary_outcome  # noqa: E402
from policy_analytics import benchmark_v2_scoring as scoring  # noqa: E402
import polars as pl  # noqa: E402

seed = 4001
STRONG = ("C04", "C06", "C09", "C14", "C15")
DESIGN_INDEX = tg.design_index()

with tempfile.TemporaryDirectory(prefix="diagcap-") as tmp:
    draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
    outcome = primary_outcome()
    config = engine.DiscoveryConfig(seed=seed)
    development = draw.frame.filter(pl.col("split_label") == "development")
    atoms = engine._atoms(development, draw.features, config)
    doc = engine.discover_candidates(draw.frame, draw.features, outcome, config)
    selected = [
        tuple(engine.Condition(c["feature"], c["operator"], c["value"]) for c in cand["conditions"])
        for cand in doc["candidates"]
    ]

    def stub_validate(rules, family_size):
        return set(rules)

    # Call _refinement_candidates with config.top_k forced huge so NOTHING gets excluded by the
    # capacity cap -- this gives us the TRUE full admissible set, validated-equivalent (stub
    # accepts all), to compare against what the real top_k=15 cap would have kept.
    huge_config = engine.DiscoveryConfig(seed=seed, top_k=100000)
    kept_all, meta_all = engine._refinement_candidates(
        draw.frame, development, outcome, huge_config, atoms, selected, stub_validate,
        doc["search"]["evaluated_hypotheses"],
    )
    print(f"Full admissible set (no cap): {len(kept_all)} descendants")

    kept_capped, meta_capped = engine._refinement_candidates(
        draw.frame, development, outcome, config, atoms, selected, stub_validate,
        doc["search"]["evaluated_hypotheses"],
    )
    capped_rules = {item[0] for item in kept_capped}
    print(f"Capped set (real top_k={config.top_k}): {len(kept_capped)} descendants")

    for tid in STRONG:
        design = DESIGN_INDEX[tid]
        canon = tuple(scoring.CondSpec(c.feature, c.operator, c.value) for c in design.conditions)
        target = scoring.Target(
            target_id=tid, stratum="core", conditions=canon, affected=draw.masks[tid],
            canonical_in_language=canon, assessed=True,
        )
        best_full = (0.0, None)
        best_capped = (0.0, None)
        for rule, parent, metric, score in kept_all:
            cs = tuple(scoring.CondSpec(c.feature, c.operator, c.value) for c in rule)
            exposed_mask = draw.space.rule_mask(cs)
            eff = scoring.effective_rule(draw.space, cs, scoring.CONSTANTS.nu)
            pm = scoring.pair_metrics(draw.space, eff.conditions, exposed_mask, target)
            if pm.j_e > best_full[0]:
                best_full = (pm.j_e, rule)
            if rule in capped_rules and pm.j_e > best_capped[0]:
                best_capped = (pm.j_e, rule)
        print(f"\n{tid}: best j_e in FULL admissible set (uncapped) = {best_full[0]:.3f} "
              f"(rule={best_full[1]})")
        print(f"      best j_e among the REAL top_k=15 CAPPED/validated set = {best_capped[0]:.3f} "
              f"(rule={best_capped[1]})")
