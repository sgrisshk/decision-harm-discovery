"""POST-HOC DIAGNOSTIC (`TASK-094` scope question 1): does the `G03`/`G05` power ceiling `ADR-092`/
`TASK-069` measured for `k>=2` compound candidates (`P04`/`P08`/`P09`, conclusively unpromotable at
travel's sample size even given the exact true rule) also bind on candidates that are naturally
`k==1`, or do singletons have materially different power characteristics?

Not part of the official discovery/blind/validation pipeline. Never runs as part of an official
blind run and never influences one. It locally reproduces the real, unmodified `discovery.engine`
search (`_atoms`/`_metric`/`_eligible`/`_development_score`/`_select_expansion_beam`/
`_exposed_rows`, verbatim, not reimplemented) against the real travel analytical dataset, under the
actual current default `DiscoveryConfig()` — the same configuration `scripts/run_discovery.py`
uses — purely to inspect the **full eligible candidate pool** at every depth, not just the
persisted top-K. This is
the same reproduction technique `scripts/diagnose_candidate_pool_recall.py` (`TASK-060`, `ADR-038`)
established, updated to mirror `discover_candidates`'s current redundancy-pruning logic exactly
(`TASK-071`'s exposed-row-set comparison, not the older `n_exposed`-count proxy).

**Why this script opens no hidden ground truth at all.** Unlike `diagnose_validation_power.py`
(`TASK-069` item 1), this diagnostic asks a structural question about the search's own eligible
pool — singleton vs. compound power characteristics — not about recovering any specific named
pattern. It never reads `synthetic_data/evaluation/hidden_ground_truth.json` and contains no
pattern id, feature name, or threshold value chosen with reference to one. Every number below is a
property of the real pool the real engine produces on real data, read generically.

**`TASK-094`'s hard rule, honoured.** No pattern identity or feature value from travel shapes any
conclusion here; only the generic, structural question is answered: does a `k==1` candidate have
systematically different `n_exposed`/effect-dilution/power characteristics than its `k>=2`
descendants, given how `G03` (sample adequacy, via `minimum_detectable_effect`) and `G05`
(multiplicity, via `normal_approx_two_sided_p` against the real family's Benjamini-Hochberg bound)
are actually computed.

Usage:
  uv run python scripts/diagnose_task094_k1_power_ceiling.py
  uv run python scripts/diagnose_task094_k1_power_ceiling.py --dataset-root <path>
"""

# pyright: reportPrivateUsage=false
# Reuses discovery.engine's and validation.apply's own private/public functions verbatim rather
# than reimplementing their arithmetic — the same precedent diagnose_candidate_pool_recall.py,
# diagnose_validation_power.py, and diagnose_g06_task065_b2b.py already set.
from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    DISCOVERY_METHOD_VERSION,
    Condition,
    DiscoveryConfig,
    SplitMetric,
    _atoms,
    _development_score,
    _eligible,
    _exposed_rows,
    _metric,
    _rule_expr,
    _select_expansion_beam,
)
from policy_analytics.outcomes import (  # noqa: E402
    outcome_definition_from_manifest,
    primary_outcome,
)
from policy_analytics.validation.apply import (  # noqa: E402
    Z_95,
    Z_POWER_80,
    load_analytical_frame,
    minimum_detectable_effect,
    run_validation,
    split_stats,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS  # noqa: E402
from policy_analytics.validation.grading import normal_approx_two_sided_p  # noqa: E402

DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
DEFAULT_RAW_OUTPUT = REPOSITORY / "docs/benchmark/task-094-k1-power-ceiling-raw.json"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    parser.add_argument(
        "--seed",
        type=int,
        default=DiscoveryConfig().seed,
        help="DiscoveryConfig.seed — default matches the real production default exactly.",
    )
    return parser.parse_args(argv)


def _reproduce_full_pool(
    frame: pl.DataFrame,
    development: pl.DataFrame,
    feature_columns: tuple[str, ...],
    config: DiscoveryConfig,
) -> tuple[dict[tuple[Condition, ...], tuple[float, SplitMetric]], int, tuple[Condition, ...]]:
    """Line-for-line mirror of `discover_candidates`'s own search loop (engine.py), up to but not
    including `_greedy_diverse_select` / final top-K assembly. Every step calls the real,
    unmodified private function discover_candidates itself calls — nothing here reimplements
    eligibility, scoring, beam selection, or the TASK-071 exposure-identical-parent redundancy
    check. The only difference from `discover_candidates` is that `scored` (every eligible rule at
    every depth, not just the persisted top-K) is returned instead of being discarded after
    selection.
    """
    outcome = primary_outcome()
    atoms = _atoms(development, feature_columns, config)
    evaluated = 0
    scored: dict[tuple[Condition, ...], tuple[float, SplitMetric]] = {}
    frontier: list[tuple[Condition, ...]] = [(atom,) for atom in atoms]

    for depth in range(1, config.max_conditions + 1):
        next_frontier: list[tuple[Condition, ...]] = []
        for rule in frontier:
            evaluated += 1
            metric = _metric(frame, rule, outcome, "development")
            if _eligible(metric, config):
                assert metric is not None
                if depth > 1:
                    parent_rules = [tuple(c for c in rule if c != removed) for removed in rule]
                    parent_metrics = [
                        _metric(frame, parent_rule, outcome, "development")
                        for parent_rule in parent_rules
                    ]
                    child_exposed_rows = _exposed_rows(development, rule)
                    if any(
                        parent is not None
                        and _exposed_rows(development, parent_rule) == child_exposed_rows
                        for parent_rule, parent in zip(parent_rules, parent_metrics, strict=True)
                    ):
                        continue
                scored[rule] = (_development_score(metric, depth, config), metric)

        beam = _select_expansion_beam(scored, depth, config)
        if depth == config.max_conditions:
            break
        for rule in beam:
            used = {condition.feature for condition in rule}
            for atom in atoms:
                if atom.feature in used:
                    continue
                expanded = tuple(sorted((*rule, atom)))
                next_frontier.append(expanded)
        frontier = sorted(set(next_frontier))

    return scored, evaluated, atoms


def _power_row(
    development: pl.DataFrame,
    rule: tuple[Condition, ...],
    metric: SplitMetric,
    development_score: float,
    family_size: int,
) -> dict[str, Any]:
    """Apply G03's and G05's own formulas — `minimum_detectable_effect` and
    `normal_approx_two_sided_p`, both real production functions, not reimplemented — to one pool
    candidate's real development-split exposure, using an *unclustered* standard error. Deliberately
    optimistic and one-directional, the same convention `diagnose_validation_power.py`'s
    `_true_rule_power_reference` uses: clustering (on `customer_id`, per the real contract) can only
    widen the interval, so when even this bound cannot clear Benjamini-Hochberg's rank-1 bound, "no
    estimator could have promoted this rule" is settled, not argued; when it clears, nothing beyond
    G03/G05 is concluded (G06/G12/etc. are untouched by this diagnostic).
    """
    outcome = primary_outcome()
    mask = development.select(_rule_expr(rule).alias("m"))["m"]
    stats = split_stats(development, mask, outcome, "development")
    assert stats is not None
    # Fidelity check: the engine's own SplitMetric and apply.py's own SplitStats must agree on the
    # exposure/effect this rule produces — two independently-written production functions computing
    # the same thing from the same frame.
    harm_delta = abs(stats.harm_per_booking - metric.harm_per_booking)
    if stats.n_exposed != metric.n_exposed or harm_delta > 1e-6:
        raise SystemExit(
            f"SplitMetric/SplitStats disagree for {rule}: "
            f"({metric.n_exposed}, {metric.harm_per_booking}) vs "
            f"({stats.n_exposed}, {stats.harm_per_booking}) — refusing to report"
        )
    mde = minimum_detectable_effect(stats.n_exposed, stats.n_comparison, stats.pooled_sd)
    se = stats.pooled_sd * math.sqrt(1.0 / stats.n_exposed + 1.0 / stats.n_comparison)
    optimistic_p = normal_approx_two_sided_p(stats.harm_per_booking, se)
    bh_rank1_bound = DEFAULT_THRESHOLDS.fdr_alpha / family_size
    return {
        "k": len(rule),
        "rule": " AND ".join(f"{c.feature} {c.operator} {c.value}" for c in rule),
        "development_score": development_score,
        "n_exposed": stats.n_exposed,
        "n_comparison": stats.n_comparison,
        "support": metric.support,
        "harm_per_booking": round(stats.harm_per_booking, 4),
        "pooled_sd": round(stats.pooled_sd, 4),
        "minimum_detectable_effect_eur": round(mde, 4),
        "g03_would_pass_on_power": bool(abs(stats.harm_per_booking) > mde),
        "g03_would_pass_on_floor": stats.n_exposed >= DEFAULT_THRESHOLDS.min_exposed_records,
        "optimistic_unclustered_p": optimistic_p,
        "bh_rank1_bound": bh_rank1_bound,
        "clears_bh_rank1_bound": bool(optimistic_p <= bh_rank1_bound),
        "shortfall_factor_at_rank1": (None if optimistic_p <= 0 else optimistic_p / bh_rank1_bound),
    }


def _summarize(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    if not rows:
        return {"label": label, "count": 0}
    n_exposed = sorted(cast(int, r["n_exposed"]) for r in rows)
    harm = [abs(cast(float, r["harm_per_booking"])) for r in rows]
    mde = [cast(float, r["minimum_detectable_effect_eur"]) for r in rows]

    def _pct(values: list[float], q: float) -> float:
        if not values:
            return float("nan")
        ordered = sorted(values)
        idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
        return ordered[idx]

    clears_power = sum(1 for r in rows if r["g03_would_pass_on_power"])
    clears_floor = sum(1 for r in rows if r["g03_would_pass_on_floor"])
    clears_bh_rank1 = sum(1 for r in rows if r["clears_bh_rank1_bound"])
    clears_both = sum(
        1 for r in rows if r["g03_would_pass_on_power"] and r["clears_bh_rank1_bound"]
    )
    return {
        "label": label,
        "count": len(rows),
        "n_exposed": {
            "min": n_exposed[0],
            "p25": _pct([float(x) for x in n_exposed], 0.25),
            "median": _pct([float(x) for x in n_exposed], 0.5),
            "p75": _pct([float(x) for x in n_exposed], 0.75),
            "max": n_exposed[-1],
        },
        "abs_harm_per_booking_eur": {
            "min": round(min(harm), 4),
            "median": round(_pct(harm, 0.5), 4),
            "max": round(max(harm), 4),
        },
        "minimum_detectable_effect_eur": {
            "min": round(min(mde), 4),
            "median": round(_pct(mde, 0.5), 4),
            "max": round(max(mde), 4),
        },
        "clears_g03_power_count": clears_power,
        "clears_g03_power_fraction": round(clears_power / len(rows), 4),
        "clears_g03_floor_count": clears_floor,
        "clears_g03_floor_fraction": round(clears_floor / len(rows), 4),
        "clears_bh_rank1_bound_count": clears_bh_rank1,
        "clears_bh_rank1_bound_fraction": round(clears_bh_rank1 / len(rows), 4),
        "clears_both_g03_and_bh_rank1_count": clears_both,
        "clears_both_g03_and_bh_rank1_fraction": round(clears_both / len(rows), 4),
    }


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    dataset_root = cast(Path, args.dataset_root)
    manifest = cast(
        dict[str, Any], json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    )
    config = DiscoveryConfig(seed=int(args.seed))
    timing_meta = cast(dict[str, dict[str, Any]], manifest["feature_timing"])
    timing = {name: str(meta["classification"]) for name, meta in timing_meta.items()}
    excluded_dates = {"booking_date", "travel_date"}
    frame = load_analytical_frame(dataset_root)
    feature_columns = tuple(
        name
        for name in frame.columns
        if timing.get(name) == "DECISION_TIME" and name not in excluded_dates
    )
    development = frame.filter(pl.col("split_label") == "development")  # pyright: ignore[reportUnknownMemberType]

    print(
        f"Reproducing the real current search: engine {DISCOVERY_METHOD_VERSION}, "
        f"seed={config.seed}"
    )
    print(f"  dataset_identity_sha256={manifest['dataset_identity_sha256']}")
    print(
        f"  {len(feature_columns)} DECISION_TIME feature columns, "
        f"{development.height} development rows"
    )

    scored, evaluated, atoms = _reproduce_full_pool(frame, development, feature_columns, config)
    print(f"  atoms={len(atoms)}  evaluated_hypotheses={evaluated}  eligible_pool={len(scored)}")

    singles = [rule for rule in scored if len(rule) == 1]
    interactions = [rule for rule in scored if len(rule) >= 2]
    print(f"  eligible k==1: {len(singles)}   eligible k>=2: {len(interactions)}")

    # Real family size G05 would actually use for an official run under this exact search: the
    # total evaluated_hypotheses count, per apply.py's own family-size convention (same quantity
    # `discovery_metrics.json`'s `evaluated_hypotheses` records for every real official run).
    family_size = evaluated

    single_rows = [
        _power_row(development, rule, scored[rule][1], scored[rule][0], family_size)
        for rule in singles
    ]
    interaction_rows = [
        _power_row(development, rule, scored[rule][1], scored[rule][0], family_size)
        for rule in interactions
    ]

    # ---- Structural check: does every k>=2 rule's n_exposed sit at or below its own leave-one-out
    # parents' n_exposed? (Conjunction only ever removes rows — engine.py's own TASK-071 comment.
    # Verified directly over the real pool here, not merely cited.) ----
    subset_violations = 0
    checked_parent_pairs = 0
    for rule in interactions:
        parent_rules = [tuple(c for c in rule if c != removed) for removed in rule]
        child_n = scored[rule][1].n_exposed
        for parent_rule in parent_rules:
            parent_metric = _metric(frame, parent_rule, primary_outcome(), "development")
            if parent_metric is None:
                continue
            checked_parent_pairs += 1
            if child_n > parent_metric.n_exposed:
                subset_violations += 1

    single_summary = _summarize(single_rows, "k==1 (singleton) eligible pool")
    interaction_summary = _summarize(interaction_rows, "k>=2 (compound) eligible pool")

    # ---- The specific rule the interactions-first assembly rule would surface first (highest
    # development_score among interactions) vs. the specific rule a k==1 quota would surface first
    # (highest development_score among singles) — the two candidates final-assembly actually
    # trades off against each other under any quota/reweighting mechanism (TASK-094 Q2's subject),
    # reported generically (no rule content interpreted against any known pattern). ----
    top_single = max(single_rows, key=lambda r: cast(float, r["development_score"]), default=None)
    top_interaction = max(
        interaction_rows, key=lambda r: cast(float, r["development_score"]), default=None
    )

    # ---- Does the search pool's single highest-scoring k==1 candidate actually reach
    # adjusted_observational_association through the REAL, unmodified full validation pipeline
    # (not just the G03/G05 arithmetic bound above)? Mirrors the technique TASK-081's independent
    # `CODE_REVIEWER` review used to prove the k==1/k>=2 G16 boundary (check 3). ----
    top_single_full_pipeline: dict[str, Any] | None = None
    top_single_rule = max(singles, key=lambda r: scored[r][0], default=None) if singles else None
    if top_single_rule is not None:
        outcome_def, outcome_version = outcome_definition_from_manifest(manifest, dataset_root)
        document = {
            "schema_version": "1.1.0",
            "run_id": "post-hoc-diagnostic-task094-top-single",
            "status": "PERSISTED",
            "candidates": [
                {
                    "candidate_id": "DIAG-001",
                    "conditions": [
                        {"feature": c.feature, "operator": c.operator, "value": c.value}
                        for c in top_single_rule
                    ],
                    "outcome": outcome_def.outcome_id,
                    "discovery_method": DISCOVERY_METHOD_VERSION,
                    "description": "POST-HOC DIAGNOSTIC: real pool's top-scoring k==1 candidate.",
                    "warnings": ["POST-HOC DIAGNOSTIC; never a discovered or selected candidate."],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cand_path = Path(tmp) / "candidates.json"
            cand_path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
            metrics_path = Path(tmp) / "discovery_metrics.json"
            metrics_path.write_text(
                json.dumps({"evaluated_hypotheses": evaluated}), encoding="utf-8"
            )
            validations, summary = run_validation(
                dataset_root=dataset_root,
                candidates_path=cand_path,
                outcome=outcome_def,
                dataset_version=str(manifest["dataset_version"]),
                outcome_definition_version=outcome_version,
                analysis_run_id="post-hoc-diagnostic-task094-top-single",
                metrics_path=metrics_path,
            )
        report = validations[0].report
        gates = {g.gate_id.value: g.outcome.value for g in report.gate_results}
        top_single_full_pipeline = {
            "rule": " AND ".join(f"{c.feature} {c.operator} {c.value}" for c in top_single_rule),
            "evidence_level": str(report.evidence_level),
            "policy_readiness": str(report.policy_readiness),
            "family_size": report.family_size,
            "gate_outcomes": gates,
            "failed_gates": sorted(g for g, o in gates.items() if o == "fail"),
        }
        print(
            f"\nReal full-pipeline check of the pool's top-scoring k==1 candidate "
            f"({top_single_full_pipeline['rule']}): evidence_level="
            f"{top_single_full_pipeline['evidence_level']}, failed_gates="
            f"{top_single_full_pipeline['failed_gates']}"
        )

    payload: dict[str, Any] = {
        "diagnostic": "POST_HOC_DIAGNOSTIC",
        "task": "TASK-094 scope question 1 (does more k==1 representation buy anything)",
        "disclosure": (
            "Not an official TASK-015/TASK-019/TASK-028 run. Produces no official metric, changes "
            "no gate/threshold, proposes no mechanism. Opens no hidden ground truth — a purely "
            "structural comparison of the real eligible pool's own k==1 vs k>=2 power "
            "characteristics under G03's and G05's real formulas."
        ),
        "engine_version": DISCOVERY_METHOD_VERSION,
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "config": {
            "seed": config.seed,
            "min_n": config.min_n,
            "min_support": config.min_support,
            "max_support": config.max_support,
            "max_conditions": config.max_conditions,
            "beam_width": config.beam_width,
            "beam_rules_per_structure": config.beam_rules_per_structure,
        },
        "evaluated_hypotheses": evaluated,
        "family_size_used_for_bh": family_size,
        "eligible_pool_size": len(scored),
        "eligible_k1_count": len(singles),
        "eligible_k_ge2_count": len(interactions),
        "structural_subset_check": {
            "description": (
                "For every eligible k>=2 rule, its n_exposed should never exceed any of its "
                "leave-one-out parent rules' n_exposed (conjunction only removes rows)."
            ),
            "parent_pairs_checked": checked_parent_pairs,
            "violations": subset_violations,
        },
        "k1_pool_summary": single_summary,
        "k_ge2_pool_summary": interaction_summary,
        "top_scoring_single": top_single,
        "top_scoring_interaction": top_interaction,
        "top_scoring_single_full_pipeline_check": top_single_full_pipeline,
        "g03_thresholds": {
            "min_exposed_records": DEFAULT_THRESHOLDS.min_exposed_records,
            "z_95": Z_95,
            "z_power_80": Z_POWER_80,
        },
        "g05_thresholds": {"fdr_alpha": DEFAULT_THRESHOLDS.fdr_alpha},
    }
    output = cast(Path, args.raw_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nRaw output written to {output}")

    print("\n=== k==1 vs k>=2 eligible-pool power comparison ===")
    for summary in (single_summary, interaction_summary):
        print(f"\n{summary['label']} (n={summary['count']}):")
        if summary["count"] == 0:
            continue
        n_exp = summary["n_exposed"]
        print(f"  n_exposed: min={n_exp['min']} median={n_exp['median']:.0f} max={n_exp['max']}")
        print(
            f"  clears G03 power (|harm| > MDE): "
            f"{summary['clears_g03_power_count']}/{summary['count']} "
            f"({summary['clears_g03_power_fraction']:.1%})"
        )
        print(
            f"  clears BH rank-1 bound (optimistic, unclustered): "
            f"{summary['clears_bh_rank1_bound_count']}/{summary['count']} "
            f"({summary['clears_bh_rank1_bound_fraction']:.1%})"
        )
        print(
            f"  clears BOTH: {summary['clears_both_g03_and_bh_rank1_count']}/{summary['count']} "
            f"({summary['clears_both_g03_and_bh_rank1_fraction']:.1%})"
        )
    print(
        f"\nStructural subset check: {subset_violations} violations over "
        f"{checked_parent_pairs} checked parent/child pairs (0 expected)."
    )


if __name__ == "__main__":
    main()
