"""TASK-116 Step 1 -- reconstruct, per development seed, the FULL one-literal admissible-
descendant pool the real frozen v0.6.2 engine's shortlist would feed into a capacity cutoff,
WITHOUT editing engine.py (`ADR-117` Decision 1, binding).

Read-only diagnostic. Calls the real, frozen `discovery-engine-v0.6.2` functions directly
(`discover_candidates`, `_atoms`, `_metric`, `_eligible`, `_exposed_rows`, `_development_score`)
exactly as `TASK-114`/`TASK-115`'s own evidence scripts already do (see
`docs/benchmark/task-114-evidence/step1_build_chains.py`,
`docs/benchmark/task-115-evidence/step3_diagnose_capacity_cap.py`). The one-literal descendant
generation/admissibility logic below is OUR OWN diagnostic re-implementation (not an import from
engine.py -- that code was added in the now-reverted `discovery-engine-v0.6.4`, TASK-115, and no
longer exists in the frozen file), reconstructed byte-for-byte from that reverted commit's diff
(`git show 5e84c4f^:.../engine.py`) so the replay matches the real mechanism exactly:

  for each shortlisted parent (real top-K acquisition output, `len(parent) < max_conditions`):
    for each atom in the same frozen `_atoms()` vocabulary, on a feature the parent does not
    already use:
      descendant = sorted(parent + atom)
      skip if already seen (shared across parents) or == an existing shortlist member
      skip unless `_eligible(_metric(descendant))` (real engine `_eligible`)
      skip if `_exposed_rows(descendant) == _exposed_rows(parent)` (non-redundant guard, same
        `_exposed_rows`-equality check `discover_candidates` itself already applies at depth>1)
      else: admissible, score = `_development_score(metric, len(descendant), config)`

No capacity cutoff is applied here -- this script produces the UNCAPPED pool. Capacity replay at
K/2K/4K/unlimited and real validation happen in later steps.

Engine sha256 verified before and after every invocation.
"""
# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parents[3]
ANALYTICS_SRC = REPO / "packages/analytics/src"
SCHEMAS_SRC = REPO / "packages/schemas/src"
SCRIPTS = REPO / "scripts"
T107_EVIDENCE = REPO / "docs/benchmark/task-107-evidence"
HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "step1-pool-raw"

ENGINE_PATH = ANALYTICS_SRC / "policy_analytics/discovery/engine.py"
EXPECTED_ENGINE_SHA256 = "fefceeaac20e8ff7b57f4e7a9cc9a1e9c649dd05269e10884d358d326d2e4549"

sys.path[:0] = [str(ANALYTICS_SRC), str(SCHEMAS_SRC), str(SCRIPTS), str(T107_EVIDENCE)]


def _verify_engine() -> str:
    digest = hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest()
    if digest != EXPECTED_ENGINE_SHA256:
        raise SystemExit(f"engine.py sha256 mismatch: got {digest}, expected {EXPECTED_ENGINE_SHA256}")
    return digest


_verify_engine()

import polars as pl  # noqa: E402
import v2_common as vc  # noqa: E402
import policy_analytics.discovery.engine as engine  # noqa: E402
import policy_analytics.synthetic_benchmark_v2_targets as tg  # noqa: E402
from policy_analytics import benchmark_v2_scoring as scoring  # noqa: E402
from policy_analytics.outcomes import primary_outcome  # noqa: E402

if engine.DISCOVERY_METHOD_VERSION != "discovery-engine-v0.6.2":
    raise SystemExit(f"unexpected engine version: {engine.DISCOVERY_METHOD_VERSION}")

# 5 strong H114 targets + C07 mandatory negative control (ADR-117 Decision 3/5).
TARGETS: tuple[str, ...] = ("C04", "C06", "C09", "C14", "C15", "C07")
DESIGN_INDEX = tg.design_index()

# C07's own known negative-control literal (TASK-114 step3_negative_control_mining.py, seed 4124,
# the only real-top-15 one-literal-added pair found): acquisition_channel=direct & supplier=
# BlueWing -> +party_size>=4.0. Checked explicitly in every seed's pool (ADR-117 Decision 5 guard),
# regardless of whether this exact parent is itself shortlisted in a given seed.
C07_GUARD_ADDED_LITERAL = {"feature": "party_size", "operator": "ge", "value": 4.0}


def _condspecs(conds: tuple[engine.Condition, ...]) -> tuple[scoring.CondSpec, ...]:
    return tuple(scoring.CondSpec(c.feature, c.operator, c.value) for c in conds)


def _rule_dict(rule: tuple[engine.Condition, ...]) -> list[dict[str, Any]]:
    return [{"feature": c.feature, "operator": c.operator, "value": c.value} for c in rule]


def build_pool(
    frame: pl.DataFrame,
    development: pl.DataFrame,
    outcome: Any,
    config: "engine.DiscoveryConfig",
    atoms: tuple[engine.Condition, ...],
    shortlist: list[tuple[engine.Condition, ...]],
) -> list[dict[str, Any]]:
    """Our own diagnostic re-implementation of the reverted `_refinement_candidates`'s admissible-
    descendant GENERATION logic only (no capacity cap, no validation -- those are separate steps).
    """
    shortlist_set = set(shortlist)
    seen: set[tuple[engine.Condition, ...]] = set(shortlist)
    parent_exposed_cache: dict[tuple[engine.Condition, ...], frozenset[int]] = {}
    admissible: list[dict[str, Any]] = []
    for parent in shortlist:
        if len(parent) >= config.max_conditions:
            continue
        used_features = {c.feature for c in parent}
        if parent not in parent_exposed_cache:
            parent_exposed_cache[parent] = engine._exposed_rows(development, parent)
        parent_exposed = parent_exposed_cache[parent]
        for atom in atoms:
            if atom.feature in used_features or atom in parent:
                continue
            descendant = tuple(sorted((*parent, atom)))
            if descendant in seen or descendant in shortlist_set:
                continue
            seen.add(descendant)
            metric = engine._metric(frame, descendant, outcome, "development")
            if not engine._eligible(metric, config):
                continue
            assert metric is not None
            if engine._exposed_rows(development, descendant) == parent_exposed:
                continue
            score = engine._development_score(metric, len(descendant), config)
            admissible.append(
                {
                    "conditions": _rule_dict(descendant),
                    "parent_conditions": _rule_dict(parent),
                    "added_condition": _rule_dict((atom,))[0],
                    "development_score": score,
                    "n_exposed_development": metric.n_exposed,
                    "support_development": metric.support,
                    "harm_per_booking_development": metric.harm_per_booking,
                }
            )
    admissible.sort(key=lambda item: -item["development_score"])
    return admissible


def score_against_targets(
    draw: "vc.Draw", pool: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """For every target, attach j_e/cp/cr/recall/is_specific to every pool item (real, unmodified
    `benchmark_v2_scoring` functions -- same ones TASK-114/115 already use). Returns, per target,
    the pool re-sorted by development_score (unchanged order) with per-target metrics attached,
    plus rank (1-based, by development_score desc -- the real capacity tie-break order)."""
    targets: dict[str, scoring.Target] = {}
    for tid in TARGETS:
        design = DESIGN_INDEX[tid]
        canon = tuple(scoring.CondSpec(c.feature, c.operator, c.value) for c in design.conditions)
        targets[tid] = scoring.Target(
            target_id=tid, stratum="core", conditions=canon, affected=draw.masks[tid],
            canonical_in_language=canon, assessed=True,
        )

    out: dict[str, list[dict[str, Any]]] = {tid: [] for tid in TARGETS}
    for rank, item in enumerate(pool, start=1):
        cs = tuple(
            scoring.CondSpec(c["feature"], c["operator"], c["value"]) for c in item["conditions"]
        )
        exposed_mask = draw.space.rule_mask(cs)
        eff = scoring.effective_rule(draw.space, cs, scoring.CONSTANTS.nu)
        for tid in TARGETS:
            pm = scoring.pair_metrics(draw.space, eff.conditions, exposed_mask, targets[tid])
            is_specific = scoring.metric_specific(pm, scoring.CONSTANTS.theta_j, scoring.CONSTANTS.theta_p)
            out[tid].append(
                {
                    "rank": rank,
                    "conditions": item["conditions"],
                    "parent_conditions": item["parent_conditions"],
                    "added_condition": item["added_condition"],
                    "development_score": item["development_score"],
                    "j_e": pm.j_e,
                    "cp": pm.cp,
                    "cr": pm.cr,
                    "recall": pm.recall,
                    "is_specific": is_specific,
                }
            )
    return out


def is_c07_guard_literal(added: dict[str, Any]) -> bool:
    return (
        added["feature"] == C07_GUARD_ADDED_LITERAL["feature"]
        and added["operator"] == C07_GUARD_ADDED_LITERAL["operator"]
        and float(added["value"]) == C07_GUARD_ADDED_LITERAL["value"]
    )


def run_seed(seed: int, out: Path) -> None:
    with tempfile.TemporaryDirectory(prefix=f"task116-pool-{seed}-") as tmp:
        draw = vc.build_draw(seed, Path(tmp), tg.DESIGNS)
        outcome = primary_outcome()
        config = engine.DiscoveryConfig(seed=seed)
        development = draw.frame.filter(pl.col("split_label") == "development")
        atoms = engine._atoms(development, draw.features, config)

        doc = engine.discover_candidates(draw.frame, draw.features, outcome, config)
        shortlist = [
            tuple(engine.Condition(c["feature"], c["operator"], c["value"]) for c in cand["conditions"])
            for cand in doc["candidates"]
        ]
        evaluated_hypotheses = int(cast(dict[str, Any], doc["search"])["evaluated_hypotheses"])

        pool = build_pool(draw.frame, development, outcome, config, atoms, shortlist)
        scored = score_against_targets(draw, pool)

        # Per-target summary: best is_specific descendant (the "productive descendant"), else best
        # j_e regardless of is_specific (reported as "no productive descendant this seed").
        summary: dict[str, Any] = {}
        for tid in TARGETS:
            rows = scored[tid]
            specific_rows = [r for r in rows if r["is_specific"]]
            best_specific = max(specific_rows, key=lambda r: r["j_e"]) if specific_rows else None
            best_any = max(rows, key=lambda r: r["j_e"]) if rows else None
            summary[tid] = {
                "has_productive_descendant": best_specific is not None,
                "productive_descendant": best_specific,
                "best_j_e_descendant_any": best_any,
                "n_admissible_total": len(rows),
                "n_specific_in_pool": len(specific_rows),
            }

        # C07 guard literal: does `+party_size>=4.0` appear anywhere in this seed's pool at all,
        # and if so at what rank/j_e/recall (ADR-117 Decision 5).
        c07_guard_hits = [
            r for r in scored["C07"] if is_c07_guard_literal(r["added_condition"])
        ]

        result = {
            "seed": seed,
            "engine_sha256": EXPECTED_ENGINE_SHA256,
            "evaluated_hypotheses": evaluated_hypotheses,
            "shortlist_conditions": [_rule_dict(r) for r in shortlist],
            "n_shortlist": len(shortlist),
            "n_admissible_pool": len(pool),
            "top60_pool": pool[:60],
            "per_target_summary": summary,
            "c07_guard_literal_hits": c07_guard_hits,
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"seed {seed}: pool={len(pool)} wrote {out}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for seed in args.seeds:
        out_path = OUT_DIR / f"pool-seed-{seed}.json"
        if out_path.exists():
            print(f"seed {seed}: already built, skipping")
            continue
        run_seed(seed, out_path)
    final_digest = _verify_engine()
    print(f"engine.py sha256 after run: {final_digest} (unchanged)")


if __name__ == "__main__":
    main()
