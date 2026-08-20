"""Diagnostic: is TASK-060's 2-of-7 unique-pattern ceiling in top-K selection, or upstream of it?

Not part of the official discovery/blind/validation pipeline. Never runs as part of an official
blind run and never influences one — it locally reproduces an *already-committed* official run's
search (same dataset identity, seed, and `discovery.engine` code) purely to inspect the full
eligible candidate pool `_greedy_diverse_select` (TASK-060, `ADR-035`/`ADR-037`) chooses from,
before any selection happens, rather than only the persisted top-15.

**Why opening `hidden_ground_truth.json` here is legitimate:** the search this script re-derives
already ran deterministically and was committed via signed receipt
(`scripts/commit_blind_candidates.py`) before this script ever executes — exactly the same
"already frozen, now graded" discipline `scripts/evaluate_benchmark.py` (`TASK-028`) uses, and the
same one `ADR-025`/`HANDOFF-054` established for post-hoc analysis of a committed run. This script
never selects, ranks, or reports an official candidate; it only measures how much true-pattern
signal an already-committed search's full pool contains, to tell a fixable-by-selection-tuning
defect apart from a fixable-only-upstream one before scoping another `TASK-060` iteration.

Usage:
  uv run python scripts/diagnose_candidate_pool_recall.py \\
      --run-metrics artifacts/blind/task-060-iteration-20260820-002.discovery_metrics.json
"""

# pyright: reportPrivateUsage=false
# Reuses discovery.engine's own private search functions verbatim rather than reimplementing them
# (see module docstring and _reproduce_eligible_pool's docstring) — deliberate, not a layering
# violation to silently ignore case-by-case.
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    Condition,
    DiscoveryConfig,
    SplitMetric,
    _atoms,
    _development_score,
    _eligible,
    _metric,
)
from policy_analytics.outcomes import primary_outcome  # noqa: E402
from policy_analytics.validation.apply import Condition as ValCondition  # noqa: E402
from policy_analytics.validation.apply import load_analytical_frame, rule_expr  # noqa: E402

DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.0.0"
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
DEFAULT_RUN_METRICS = (
    REPOSITORY / "artifacts/blind/task-060-iteration-20260820-002.discovery_metrics.json"
)
# P05/P07 excluded from the scoreable denominator, same convention as TASK-028.
SCOREABLE_PATTERNS = ("P01", "P02", "P03", "P04", "P06", "P08", "P09")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-metrics", type=Path, default=DEFAULT_RUN_METRICS)
    parser.add_argument(
        "--recall-threshold",
        type=float,
        default=0.3,
        help="partial-match threshold for the verdict (full match is 0.5, TASK-028's own bar)",
    )
    return parser.parse_args(argv)


def _reproduce_eligible_pool(
    frame: pl.DataFrame, feature_columns: tuple[str, ...], config: DiscoveryConfig
) -> tuple[dict[tuple[Condition, ...], tuple[float, SplitMetric]], int]:
    """Replicates `discover_candidates`'s search loop up to (not including) top-K selection.

    Every actual computation is the real `_atoms`/`_metric`/`_eligible`/`_development_score` from
    `discovery.engine` — nothing here reimplements the search's own arithmetic, only the same
    control flow `discover_candidates` uses, so `scored` at the end is exactly what that function
    would have computed internally before ever calling `_greedy_diverse_select`.
    """
    outcome = primary_outcome()
    development = frame.filter(  # pyright: ignore[reportUnknownMemberType]
        pl.col("split_label") == "development"
    )
    atoms = _atoms(development, feature_columns, config)

    scored: dict[tuple[Condition, ...], tuple[float, SplitMetric]] = {}
    frontier: list[tuple[Condition, ...]] = [(atom,) for atom in atoms]
    evaluated = 0
    for depth in range(1, config.max_conditions + 1):
        next_frontier: list[tuple[Condition, ...]] = []
        for rule in frontier:
            evaluated += 1
            metric = _metric(frame, rule, outcome, "development")
            if _eligible(metric, config):
                assert metric is not None
                if depth > 1:
                    parent_metrics = [
                        _metric(
                            frame, tuple(c for c in rule if c != removed), outcome, "development"
                        )
                        for removed in rule
                    ]
                    if any(
                        p and p.n_exposed == metric.n_exposed for p in parent_metrics
                    ):
                        continue
                scored[rule] = (_development_score(metric, depth, config), metric)
        beam = [
            rule
            for rule, _ in sorted(scored.items(), key=lambda item: (-item[1][0], item[0]))
            if len(rule) == depth
        ][: config.beam_width]
        if depth == config.max_conditions:
            break
        for rule in beam:
            used = {condition.feature for condition in rule}
            for atom in atoms:
                if atom.feature in used:
                    continue
                next_frontier.append(tuple(sorted((*rule, atom))))
        frontier = sorted(set(next_frontier))
    return scored, evaluated


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    run_metrics = cast(dict[str, Any], json.loads(args.run_metrics.read_text(encoding="utf-8")))
    manifest_path = DATASET_ROOT / "manifest.json"
    manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    if run_metrics["dataset_identity_sha256"] != manifest["dataset_identity_sha256"]:
        raise SystemExit("dataset identity drifted since the committed run; results untrustworthy")
    seed = int(run_metrics["random_seed"])
    print(f"Reproducing search: seed={seed}, committed run={run_metrics['run_id']}")

    timing = cast(dict[str, dict[str, Any]], manifest["feature_timing"])
    excluded = {"booking_date", "travel_date"}
    feature_columns = tuple(
        name
        for name, meta in sorted(timing.items())
        if meta["classification"] == "DECISION_TIME" and name not in excluded
    )
    frame = load_analytical_frame(DATASET_ROOT)
    config = DiscoveryConfig(seed=seed)  # selection params (weight/floor) don't matter here — this
    # script stops before selection ever runs.

    scored, evaluated = _reproduce_eligible_pool(frame, feature_columns, config)
    development = frame.filter(  # pyright: ignore[reportUnknownMemberType]
        pl.col("split_label") == "development"
    )
    atom_count = len(_atoms(development, feature_columns, config))
    print(f"Atoms: {atom_count}")
    print(f"evaluated_hypotheses={evaluated}  full eligible pool (pre-selection)={len(scored)}")
    if evaluated != run_metrics["evaluated_hypotheses"]:
        raise SystemExit(
            f"evaluated_hypotheses mismatch: reproduced {evaluated}, committed run reports "
            f"{run_metrics['evaluated_hypotheses']} -- search did not reproduce identically"
        )

    ground_truth = cast(dict[str, Any], json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8")))
    patterns_by_id = {p["id"]: p for p in ground_truth["patterns"]}
    affected_by_pattern = {
        pid: frozenset(p["affected_booking_ids"]) for pid, p in patterns_by_id.items()
    }
    booking_ids = frame["booking_id"].to_list()

    exposed_by_rule: dict[tuple[Condition, ...], frozenset[str]] = {}
    for rule in scored:
        conditions = [ValCondition(c.feature, c.operator, c.value) for c in rule]
        mask = frame.select(rule_expr(conditions).alias("m"))["m"].to_list()
        exposed_by_rule[rule] = frozenset(
            bid for bid, exp in zip(booking_ids, mask, strict=True) if exp
        )

    best_recall: dict[str, tuple[float, tuple[Condition, ...] | None, int]] = {
        pid: (0.0, None, 0) for pid in patterns_by_id
    }
    full_match_counts: dict[str, int] = dict.fromkeys(patterns_by_id, 0)
    for rule, (_score, metric) in scored.items():
        exposed_ids = exposed_by_rule[rule]
        for pid, affected in affected_by_pattern.items():
            recall = len(exposed_ids & affected) / len(affected) if affected else 0.0
            if recall > best_recall[pid][0]:
                best_recall[pid] = (recall, rule, metric.n_exposed)
            if recall >= 0.5:
                full_match_counts[pid] += 1

    ranked = sorted(scored, key=lambda r: (-scored[r][0], r))
    rank_of = {rule: i + 1 for i, rule in enumerate(ranked)}
    pool_best_score = max(s for s, _ in scored.values())
    missing = tuple(pid for pid in SCOREABLE_PATTERNS if pid not in {"P01", "P06"})

    print("\nBest recall per pattern, anywhere in the full pre-selection eligible pool:")
    for pid in sorted(patterns_by_id):
        recall, rule, n_exposed = best_recall[pid]
        rule_str = (
            " AND ".join(f"{c.feature} {c.operator} {c.value}" for c in rule)
            if rule
            else "(none eligible)"
        )
        flag = " <-- currently missing" if pid in missing else ""
        print(f"  {pid}{flag}: best_recall={recall:.3f}  n_exposed={n_exposed}  rule=[{rule_str}]")

    print(f"\nPool size={len(scored)}; best raw score in pool={pool_best_score:.1f}")
    for pid in missing:
        recall, rule, _n = best_recall[pid]
        if rule is None:
            continue
        own_score = scored[rule][0]
        print(
            f"  {pid}: best rule rank={rank_of[rule]}/{len(scored)} "
            f"(score {own_score:.1f} vs pool-best {pool_best_score:.1f}, "
            f"ratio={own_score / pool_best_score:.3f}); "
            f"{full_match_counts[pid]} pool candidate(s) clear full-match recall>=0.5"
        )

    print("\nTrap apparent-feature collisions (best rule literally matching a trap):")
    for trap in ground_truth["confounding_traps"]:
        trap_feature, trap_value = trap["apparent_feature"].split("=", 1)
        for pid in missing:
            _recall, rule, _n = best_recall[pid]
            if rule is None:
                continue
            for condition in rule:
                if condition.feature == trap_feature and str(condition.value) == trap_value:
                    print(
                        f"  COLLISION: {pid}'s best rule uses "
                        f"{condition.feature}={condition.value}, identical to trap {trap['id']}'s "
                        f"apparent_feature (confounded_by={trap['confounded_by']})"
                    )

    print(f"\n=== VERDICT (partial-recall threshold {args.recall_threshold}) ===")
    any_hit = False
    for pid in missing:
        recall, rule, _n = best_recall[pid]
        if recall >= args.recall_threshold:
            any_hit = True
            rule_str = (
                " AND ".join(f"{c.feature} {c.operator} {c.value}" for c in rule) if rule else ""
            )
            threshold = args.recall_threshold
            print(f"  HIT  {pid}: recall={recall:.3f} >= {threshold} -- rule=[{rule_str}]")
        else:
            print(f"  miss {pid}: best_recall={recall:.3f} < {args.recall_threshold}")
    print()
    if any_hit:
        print("Ceiling is in top-K selection for at least one missing pattern: it has a partially")
        print("matching eligible candidate somewhere in the pre-selection pool. See rank/ratio and")
        print("trap-collision output above before scoping the next TASK-060 iteration.")
    else:
        print("Ceiling is upstream of selection: no missing pattern has ANY partially-matching")
        print("eligible candidate anywhere in the full pre-selection pool. Top-K selection tuning")
        print("cannot fix this on its own.")


if __name__ == "__main__":
    main()
