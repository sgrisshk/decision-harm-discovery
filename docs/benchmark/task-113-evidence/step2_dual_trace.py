"""TASK-113 Step 2 -- per-seed, dual-formula stage trace.

READ-ONLY. Uses the real, frozen, unmodified `discovery-engine-v0.6.2` engine
(`packages/analytics/src/policy_analytics/discovery/engine.py`, verified by sha256 before and
after this script runs) via its own internal functions (`_atoms`, `_metric`, `_eligible`,
`_development_score`, `_select_expansion_beam`, `_exposed_rows`, `_temporal_consistency`,
`_apply_stability_credit`, `_greedy_diverse_select`) -- the exact same functions TASK-110/TASK-111
probed, called directly, never copied/edited.

This script reimplements `discover_candidates`'s OWN control flow (atoms -> depth loop ->
beam -> final greedy-diverse selection) exactly, calling the real functions for every single
non-trivial step, for TWO score variants in parallel at every depth:

  * "baseline": `_development_score` -- the real, unmodified v0.6.2 function, called directly.
  * "modified": `harm_per_booking / (1 + 0.15*(k-1))` -- NOT the v0.6.3 code (which no longer
    exists on `main`, correctly, and is never recreated here). This is a plain arithmetic
    recomputation of TASK-112's own documented, committed formula (Step 2 of
    `docs/benchmark/task-112-specificity-neutral-score-results.md`), applied to `SplitMetric`
    objects produced by the real, unmodified `_metric()` function -- exactly the same kind of
    "mechanically recomputed, no new engine run" technique TASK-112's own Step 1 used
    (`step1_prereg_counterfactual.py`), just extended across the full search tree instead of one
    pairwise comparison. No `_development_score`-shaped function is ever written or executed for
    the modified variant; it is one line of arithmetic on a real `SplitMetric`.

Because eligibility (`_eligible`) and atom generation (`_atoms`) never depend on
`_development_score` at all, the two variants' depth-1 eligible pools are provably identical
(verified below, not assumed). They diverge starting at `_select_expansion_beam`, which the real
engine uses to decide which depth-d rules may expand to depth d+1 -- this is the literal
mechanism by which "composition" at depth>=2 becomes score-dependent, which is exactly what this
trace needs to surface.

Validation built into this script (not a separate claim): the "baseline" simulation's final
top-15 is byte-for-byte compared against the real, already-committed
`step5-paired-4101-4130/baseline-seed-<seed>.json`, and the "modified" simulation's final top-15
is compared (by rule identity, i.e. conditions-set) against the real, already-committed
`modified-seed-<seed>.json`. A mismatch on "baseline" would mean this reimplementation has a bug
and nothing it says about "modified" can be trusted; a mismatch on "modified" bounds how far the
arithmetic-recomputation simulation can be trusted to represent what the real v0.6.3 run did.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
SCHEMAS_SRC = REPO / "packages/schemas/src"
ANALYTICS_SRC = REPO / "packages/analytics/src"
SCRIPTS = REPO / "scripts"
T107_EVIDENCE = REPO / "docs/benchmark/task-107-evidence"
EVAL_DIR = REPO / "docs/benchmark/task-112-evidence/step5-paired-4101-4130"
OUT_DIR = Path(__file__).resolve().parent / "step2-dual-trace-raw"

ENGINE_PATH = ANALYTICS_SRC / "policy_analytics/discovery/engine.py"
EXPECTED_SHA256 = "fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549"

sys.path[:0] = [str(ANALYTICS_SRC), str(SCHEMAS_SRC), str(SCRIPTS), str(T107_EVIDENCE)]


def _verify_engine_untouched() -> str:
    digest = hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"engine.py sha256 mismatch: got {digest}, expected {EXPECTED_SHA256}")
    return digest


_verify_engine_untouched()

import policy_analytics.discovery.engine as engine  # noqa: E402
import v2_common as vc  # noqa: E402
import policy_analytics.synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics.outcomes import primary_outcome  # noqa: E402

if engine.DISCOVERY_METHOD_VERSION != "discovery-engine-v0.6.2":
    raise SystemExit(f"unexpected engine version: {engine.DISCOVERY_METHOD_VERSION}")


def modified_score(metric: "engine.SplitMetric", condition_count: int) -> float:
    """Pure arithmetic recomputation of TASK-112's documented v0.6.3 formula. Not engine code."""
    return metric.harm_per_booking / (1.0 + 0.15 * (condition_count - 1))


def run_variant_search(frame, feature_columns, outcome, config, score_fn):
    """Reimplementation of `discover_candidates`'s search loop (atoms -> depth loop -> beam),
    calling the real `_atoms`/`_metric`/`_eligible`/`_exposed_rows`/`_select_expansion_beam`
    functions directly, parameterized only by which score function computes each rule's score.
    Returns full per-depth intermediate state (not just the final candidates), which is exactly
    what `discover_candidates` itself discards and TASK-112's committed raw files never recorded.
    """
    development = frame.filter(__import__("polars").col("split_label") == "development")
    atoms = engine._atoms(development, feature_columns, config)
    scored: dict[tuple, tuple[float, Any]] = {}
    frontier = [(atom,) for atom in atoms]
    by_depth: dict[int, dict[str, Any]] = {}

    for depth in range(1, config.max_conditions + 1):
        next_frontier: list[tuple] = []
        depth_eligible = []
        depth_dropped_redundant = []
        for rule in frontier:
            metric = engine._metric(frame, rule, outcome, "development")
            if engine._eligible(metric, config):
                if depth > 1:
                    parent_rules = [tuple(c for c in rule if c != removed) for removed in rule]
                    parent_metrics = [
                        engine._metric(frame, parent_rule, outcome, "development")
                        for parent_rule in parent_rules
                    ]
                    child_exposed_rows = engine._exposed_rows(development, rule)
                    if any(
                        parent is not None
                        and engine._exposed_rows(development, parent_rule) == child_exposed_rows
                        for parent_rule, parent in zip(parent_rules, parent_metrics, strict=True)
                    ):
                        depth_dropped_redundant.append(rule)
                        continue
                scored[rule] = (score_fn(metric, depth, config), metric)
                depth_eligible.append(rule)

        beam = engine._select_expansion_beam(scored, depth, config)
        by_depth[depth] = {
            "frontier_size": len(frontier),
            "eligible_count": len(depth_eligible),
            "dropped_redundant_count": len(depth_dropped_redundant),
            "beam_size": len(beam),
            "beam_rules": [tuple(str(c) for c in r) for r in beam],
            "scored_at_depth": {
                " & ".join(str(c) for c in r): scored[r][0] for r in depth_eligible
            },
        }
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

    return scored, by_depth, atoms


def run_variant_final_selection(scored, frame, feature_columns, outcome, config):
    """Reimplementation of `discover_candidates`'s final-assembly block (post search-loop),
    calling the real `_temporal_consistency`/`_apply_stability_credit`/`_greedy_diverse_select`
    directly. `reserve_k1_slot=False` and `max_feature_identity_fraction=1.0` are this benchmark's
    real defaults (confirmed in `DiscoveryConfig(seed=seed)` used by `step5_paired_eval.py` --
    no override), so Stage 3 (`_reserve_k1_slot`) and the feature-identity cap are both inactive
    here, exactly as in the real committed runs -- not reimplemented because not reached.
    """
    development = frame.filter(__import__("polars").col("split_label") == "development")
    ranked_rules = sorted(scored, key=lambda rule: (-scored[rule][0], rule))
    interactions = [r for r in ranked_rules if len(r) >= 2]
    singles = [r for r in ranked_rules if len(r) == 1]

    selected: list[tuple] = []
    selected_exposures: list[frozenset] = []
    atom_usage: dict = {}
    max_overlap: dict[tuple, float] = {}
    exposures: dict[tuple, frozenset] = {}
    effective_score: dict[tuple, float] = {}

    def _prepare(pool):
        for rule in pool:
            if rule not in exposures:
                exposures[rule] = engine._exposed_rows(development, rule)
                max_overlap[rule] = 0.0
                info = engine._temporal_consistency(frame, rule, outcome)
                effective_score[rule] = engine._apply_stability_credit(
                    scored[rule][0], info.consistency, config.stability_credit_weight
                )

    _prepare(interactions)
    engine._greedy_diverse_select(
        interactions, effective_score, exposures, config, selected, selected_exposures,
        atom_usage, max_overlap,
    )
    if len(selected) < config.top_k:
        _prepare(singles)
        engine._greedy_diverse_select(
            singles, effective_score, exposures, config, selected, selected_exposures,
            atom_usage, max_overlap,
        )
    return selected


def trace_seed(seed: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"task113-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        outcome = primary_outcome()
        config = engine.DiscoveryConfig(seed=seed)

        scored_b, by_depth_b, atoms_b = run_variant_search(
            draw.frame, draw.features, outcome, config, engine._development_score
        )
        scored_m, by_depth_m, atoms_m = run_variant_search(
            draw.frame, draw.features, outcome, config,
            lambda metric, depth, _config: modified_score(metric, depth),
        )
        assert atoms_b == atoms_m, "atoms differ between variants -- should be impossible (score-independent)"

        selected_b = run_variant_final_selection(scored_b, draw.frame, draw.features, outcome, config)
        selected_m = run_variant_final_selection(scored_m, draw.frame, draw.features, outcome, config)

    def _rule_str(rule):
        return [str(c) for c in rule]

    return {
        "seed": seed,
        "atoms_identical": atoms_b == atoms_m,
        "n_atoms": len(atoms_b),
        "by_depth_baseline": by_depth_b,
        "by_depth_modified": by_depth_m,
        "final_selected_baseline": [_rule_str(r) for r in selected_b],
        "final_selected_modified": [_rule_str(r) for r in selected_m],
        "final_scores_baseline": {str(r): scored_b[r][0] for r in selected_b},
        "final_scores_modified": {str(r): scored_m[r][0] for r in selected_m},
    }


def _committed_conditions_sets(variant: str, seed: int) -> list[frozenset[str]]:
    doc = json.loads((EVAL_DIR / f"{variant}-seed-{seed}.json").read_text(encoding="utf-8"))
    out = []
    for cand in doc["engine"]["candidates"]:
        conds = frozenset(
            f"Condition(feature={c['feature']!r}, operator={c['operator']!r}, value={c['value']!r})"
            for c in cand["conditions"]
        )
        out.append(conds)
    return out


def validate_against_committed(trace: dict, seed: int) -> dict:
    sim_baseline_sets = [frozenset(r) for r in trace["final_selected_baseline"]]
    sim_modified_sets = [frozenset(r) for r in trace["final_selected_modified"]]
    committed_baseline_sets = _committed_conditions_sets("baseline", seed)
    committed_modified_sets = _committed_conditions_sets("modified", seed)

    baseline_match = sim_baseline_sets == committed_baseline_sets
    modified_identity_match = sorted(sim_modified_sets, key=str) == sorted(committed_modified_sets, key=str)
    modified_order_match = sim_modified_sets == committed_modified_sets
    return {
        "seed": seed,
        "baseline_simulation_matches_committed_exactly_in_order": baseline_match,
        "modified_simulation_matches_committed_set_identity_any_order": modified_identity_match,
        "modified_simulation_matches_committed_exactly_in_order": modified_order_match,
        "sim_baseline_count": len(sim_baseline_sets),
        "committed_baseline_count": len(committed_baseline_sets),
        "sim_modified_count": len(sim_modified_sets),
        "committed_modified_count": len(committed_modified_sets),
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for seed in args.seeds:
        print(f"seed {seed}: tracing...", flush=True)
        trace = trace_seed(seed)
        validation = validate_against_committed(trace, seed)
        trace["validation_against_committed"] = validation
        out_path = OUT_DIR / f"trace-seed-{seed}.json"
        out_path.write_text(json.dumps(trace, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        print(f"  wrote {out_path}")
        print(f"  validation: {json.dumps(validation, indent=2)}")

    final_digest = _verify_engine_untouched()
    print(f"engine.py sha256 after run: {final_digest} (unchanged)")


if __name__ == "__main__":
    main()
