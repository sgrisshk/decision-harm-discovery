"""TASK-110 step C: real, read-only depth-by-depth search trace.

This is the "throwaway diagnostic copy" the task text anticipates ("You may need to instrument the
engine ... to log intermediate search state"). It is NOT a copy or edit of `engine.py` -- it lives
entirely outside `packages/` (here, under `docs/benchmark/task-110-evidence/`), imports the real,
unmodified private functions directly from `policy_analytics.discovery.engine`
(`_atoms`, `_metric`, `_eligible`, `_development_score`, `_select_expansion_beam`, `_exposed_rows`,
`_beam_structure`), and re-drives exactly `discover_candidates`'s own depth-1..max_conditions loop
(copied verbatim in control flow from `engine.py`, lines ~880-932 at the frozen sha256) so it can
add external logging at each depth without touching the real file at all. No `engine.py` byte is
read differently, called differently, or monkeypatched; every scoring/eligibility/beam decision is
made by calling the real function, not a reimplementation of its logic.

For each of the 10 non-reliable Core targets' canonical literal sets, tracks across depths 1..3:
  * whether the exact canonical sub-conjunction (as real `Condition` objects matching the atoms the
    real `_atoms()` generated) was ever constructed in that depth's frontier at all;
  * if so, whether `_metric`/`_eligible` passed (eligibility);
  * if eligible, its `_development_score` and its rank among everything `scored` at that depth;
  * whether it survived `_select_expansion_beam` (core top-`beam_width` OR the
    `beam_rules_per_structure` structural reserve) to be expandable to the next depth.

Also logs, at the full depth-3 "scored" dict, the single highest-scoring rule overall (the
dominant structure that keeps winning development_score, independent of any target identity) for
direct comparison against each target's own canonical rule's score -- the S5 (objective bias)
counterfactual evidence.
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

import polars as pl  # noqa: E402
import v2_common as vc  # noqa: E402
from policy_analytics import synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402  pyright: ignore[reportPrivateUsage]
    Condition,
    DiscoveryConfig,
    _atoms,
    _eligible,
    _development_score,
    _exposed_rows,
    _metric,
    _select_expansion_beam,
)
from policy_analytics.outcomes import primary_outcome  # noqa: E402

OUT = Path(__file__).resolve().parent
TARGETS = ("C02", "C04", "C06", "C08", "C09", "C11", "C12", "C14", "C15", "H01")


def canonical_conditions(tid: str) -> tuple[Condition, ...]:
    design = tg.design_index()[tid]
    return tuple(sorted(Condition(c.feature, c.operator, c.value) for c in design.conditions))  # type: ignore[arg-type]


def run_search_with_trace(frame: pl.DataFrame, features: tuple[str, ...], config: DiscoveryConfig):
    """Re-drive `discover_candidates`'s own depth loop (identical control flow to the real
    function, lines ~880-932 of the frozen `engine.py`), calling only real imported functions,
    to capture per-depth state the real function's own return value does not expose."""
    outcome = primary_outcome()
    development = frame.filter(pl.col("split_label") == "development")
    atoms = _atoms(development, features, config)
    atom_set = set(atoms)
    scored: dict[tuple[Condition, ...], tuple[float, object]] = {}
    frontier: list[tuple[Condition, ...]] = [(a,) for a in atoms]
    depth_log: list[dict] = []
    beams: dict[int, list[tuple[Condition, ...]]] = {}

    for depth in range(1, config.max_conditions + 1):
        next_frontier: list[tuple[Condition, ...]] = []
        n_frontier = len(frontier)
        n_eligible_this_depth = 0
        for rule in frontier:
            metric = _metric(frame, rule, outcome, "development")
            if _eligible(metric, config):
                n_eligible_this_depth += 1
                if depth > 1:
                    parent_rules = [tuple(c for c in rule if c != removed) for removed in rule]
                    parent_metrics = [_metric(frame, pr, outcome, "development") for pr in parent_rules]
                    child_rows = _exposed_rows(development, rule)
                    if any(
                        pm is not None and _exposed_rows(development, pr) == child_rows
                        for pr, pm in zip(parent_rules, parent_metrics, strict=True)
                    ):
                        continue
                scored[rule] = (_development_score(metric, depth, config), metric)
        beam = _select_expansion_beam(scored, depth, config)
        beams[depth] = beam
        depth_log.append(
            {
                "depth": depth,
                "frontier_size": n_frontier,
                "n_eligible": n_eligible_this_depth,
                "n_scored_at_this_depth": sum(1 for r in scored if len(r) == depth),
                "beam_size": len(beam),
            }
        )
        if depth == config.max_conditions:
            break
        for rule in beam:
            used = {c.feature for c in rule}
            for atom in atoms:
                if atom.feature in used:
                    continue
                expanded = tuple(sorted((*rule, atom)))
                next_frontier.append(expanded)
        frontier = sorted(set(next_frontier))
    return atom_set, scored, beams, depth_log


def trace_target(tid: str, atom_set, scored, beams, depth_log) -> dict:
    canon = canonical_conditions(tid)
    k = len(canon)
    literals_all_present = all(c in atom_set for c in canon)
    report: dict = {
        "target_id": tid,
        "canonical_conditions": [f"{c.feature} {c.operator} {c.value}" for c in canon],
        "all_literals_present_as_atoms": literals_all_present,
        "by_prefix_depth": {},
    }
    # Check every ORDER-independent sub-conjunction of the canonical set at each depth 1..k
    # (the real search explores rules as sorted tuples, so canon itself, sorted, is the only
    # representation that matters -- there is exactly one canonical sorted tuple of length k, and
    # its depth-d "ancestors" the real engine could have built are its own depth-d sorted subsets).
    import itertools

    for d in range(1, k + 1):
        subsets = [tuple(sorted(c)) for c in itertools.combinations(canon, d)]
        sub_report = []
        for sub in subsets:
            in_scored = sub in scored
            rank = None
            score_val = None
            if in_scored:
                score_val = scored[sub][0]
                same_depth = [r for r in scored if len(r) == d]
                same_depth.sort(key=lambda r: (-scored[r][0], r))
                rank = same_depth.index(sub) + 1
            in_beam = sub in beams.get(d, [])
            sub_report.append(
                {
                    "conditions": [f"{c.feature} {c.operator} {c.value}" for c in sub],
                    "in_scored": in_scored,
                    "development_score": score_val,
                    "rank_among_depth_d_scored": rank,
                    "n_scored_at_depth_d": sum(1 for r in scored if len(r) == d),
                    "survives_to_beam": in_beam,
                }
            )
        report["by_prefix_depth"][d] = sub_report
    # Dominant structure at the final depth (max development_score overall), for S5 comparison.
    if scored:
        best_rule = max(scored, key=lambda r: scored[r][0])
        report["dominant_rule_overall"] = {
            "conditions": [f"{c.feature} {c.operator} {c.value}" for c in best_rule],
            "development_score": scored[best_rule][0],
        }
        if canon in scored:
            report["canonical_full_rule_development_score"] = scored[canon][0]
        else:
            report["canonical_full_rule_development_score"] = None
    report["depth_log"] = depth_log
    return report


def main(seeds: list[int]) -> None:
    for seed in seeds:
        with tempfile.TemporaryDirectory(prefix=f"task110-trace-{seed}-") as tmp:
            draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
            config = DiscoveryConfig(seed=seed)
            atom_set, scored, beams, depth_log = run_search_with_trace(
                draw.frame, draw.features, config
            )
            out = {
                "seed": seed,
                "depth_log": depth_log,
                "targets": {tid: trace_target(tid, atom_set, scored, beams, depth_log) for tid in TARGETS},
            }
            (OUT / f"search-trace-seed-{seed}.json").write_text(
                json.dumps(out, indent=1, sort_keys=True, default=str)
            )
            print(f"seed {seed}: wrote search-trace-seed-{seed}.json", flush=True)


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [4001]
    main(seeds)
