"""TASK-117: frozen-engine search-trajectory decomposition and one-step counterfactual replay (`H117`).

Read-only. Re-drives `discover_candidates`'s depth loop and post-loop selection with control flow
copied from the frozen `engine.py` (sha256 `fefceeaa...e4549`), calling only the real imported
functions, so per-depth state can be logged and one selection step can be overridden. Nothing under
`packages/` is edited, copied with different logic, or monkeypatched. Operational definitions and the
verdict rule are fixed in `preregistration.md` (written before this script was first run).

  seed   --seed S --out F
  batch  --seeds A B --dir D [--procs N]
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import itertools
import json
import sys
import tempfile
from dataclasses import asdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPOSITORY / "packages/analytics/src"),
    str(REPOSITORY / "packages/schemas/src"),
    str(REPOSITORY / "scripts"),
    str(REPOSITORY / "docs/benchmark/task-107-evidence"),
    str(REPOSITORY / "docs/benchmark/task-109-evidence"),
]

import polars as pl  # noqa: E402
import run_blind_engine as rbe  # noqa: E402
import v2_common as vc  # noqa: E402
from diagnose_validation_power import _gate_map  # noqa: E402
from policy_analytics.discovery.actionability import actionability_label  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    DISCOVERY_METHOD_VERSION,
    Candidate,
    Condition,
    DiscoveryConfig,
    _apply_stability_credit,
    _atoms,
    _development_score,
    _eligible,
    _exposed_rows,
    _greedy_diverse_select,
    _metric,
    _select_expansion_beam,
    _temporal_consistency,
)
from policy_analytics.outcomes import outcome_definition_from_manifest, primary_outcome  # noqa: E402
from policy_analytics.validation.apply import run_validation  # noqa: E402

tg = vc.tg
scoring = vc.scoring

STRONG: tuple[str, ...] = ("C04", "C06", "C09", "C14", "C15")
GUARD: tuple[str, ...] = ("C07",)
TRACKED = (*STRONG, *GUARD)
THETA_J = scoring.CONSTANTS.theta_j
THETA_P = scoring.CONSTANTS.theta_p
RAW_109 = REPOSITORY / "docs/benchmark/task-109-evidence/engine-raw"

Rule = tuple[Condition, ...]


def label(rule: Rule) -> list[str]:
    return [f"{c.feature} {c.operator} {c.value}" for c in rule]


def canonical(tid: str) -> Rule:
    design = tg.design_index()[tid]
    return tuple(sorted(Condition(c.feature, c.operator, c.value) for c in design.conditions))  # type: ignore[arg-type]


def to_spec(rule: Rule) -> tuple[Any, ...]:
    return tuple(scoring.CondSpec(c.feature, c.operator, c.value) for c in rule)


# ------------------------------------------------------------------------- re-driven depth loop --
def search(
    frame: pl.DataFrame,
    features: tuple[str, ...],
    config: DiscoveryConfig,
    force_beam: dict[int, Rule] | None = None,
) -> dict[str, Any]:
    """Control flow of `discover_candidates` lines ~880-932 (frozen), real functions only.
    `force_beam[d]` appends one rule to depth-`d`'s real beam (the one-step replay); `None` = baseline."""
    outcome = primary_outcome()
    development = frame.filter(pl.col("split_label") == "development")  # pyright: ignore[reportUnknownMemberType]
    atoms = _atoms(development, features, config)
    evaluated = 0
    scored: dict[Rule, tuple[float, Any]] = {}
    frontier: list[Rule] = [(atom,) for atom in atoms]
    frontiers: dict[int, set[Rule]] = {}
    ineligible: dict[int, set[Rule]] = {}
    identical_dropped: set[Rule] = set()
    beams: dict[int, list[Rule]] = {}
    for depth in range(1, config.max_conditions + 1):
        frontiers[depth] = set(frontier)
        ineligible[depth] = set()
        next_frontier: list[Rule] = []
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
                        identical_dropped.add(rule)
                        continue
                scored[rule] = (_development_score(metric, depth, config), metric)
            else:
                ineligible[depth].add(rule)
        beam = _select_expansion_beam(scored, depth, config)
        if force_beam and depth in force_beam and force_beam[depth] not in beam:
            beam = [*beam, force_beam[depth]]
        beams[depth] = beam
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
    return {
        "atoms": set(atoms),
        "evaluated": evaluated,
        "scored": scored,
        "frontiers": frontiers,
        "ineligible": ineligible,
        "identical_dropped": identical_dropped,
        "beams": beams,
        "development": development,
    }


def final_select(frame: pl.DataFrame, state: dict[str, Any], config: DiscoveryConfig) -> dict[str, Any]:
    """Post-loop selection of `discover_candidates` (frozen), real functions only. The identity cap
    and k==1 reservation are inactive at the frozen defaults (asserted)."""
    assert config.max_feature_identity_fraction >= 1.0 and not config.reserve_k1_slot
    outcome = primary_outcome()
    scored = cast(dict[Rule, tuple[float, Any]], state["scored"])
    development = cast(pl.DataFrame, state["development"])
    ranked_rules = sorted(scored, key=lambda rule: (-scored[rule][0], rule))
    interactions = [rule for rule in ranked_rules if len(rule) >= 2]
    singles = [rule for rule in ranked_rules if len(rule) == 1]
    selected: list[Rule] = []
    selected_exposures: list[frozenset[int]] = []
    atom_usage: dict[Condition, int] = {}
    max_overlap: dict[Rule, float] = {}
    exposures: dict[Rule, frozenset[int]] = {}
    stability: dict[Rule, Any] = {}
    effective_score: dict[Rule, float] = {}

    def prepare(pool: list[Rule]) -> None:
        for rule in pool:
            if rule not in exposures:
                exposures[rule] = _exposed_rows(development, rule)
                max_overlap[rule] = 0.0
                info = _temporal_consistency(frame, rule, outcome)
                stability[rule] = info
                effective_score[rule] = _apply_stability_credit(
                    scored[rule][0], info.consistency, config.stability_credit_weight
                )

    prepare(interactions)
    _greedy_diverse_select(
        interactions, effective_score, exposures, config, selected, selected_exposures,
        atom_usage, max_overlap,
    )
    if len(selected) < config.top_k:
        prepare(singles)
        _greedy_diverse_select(
            singles, effective_score, exposures, config, selected, selected_exposures,
            atom_usage, max_overlap,
        )
    return {
        "selected": selected,
        "stability": stability,
        "effective_score": effective_score,
        "interactions": interactions,
        "prepare": prepare,
    }


def assemble(rules: list[Rule], state: dict[str, Any], sel: dict[str, Any], config: DiscoveryConfig) -> dict[str, Any]:
    """Candidate assembly loop of `discover_candidates` (frozen), unchanged."""
    sel["prepare"](rules)
    scored = state["scored"]
    candidates: list[Candidate] = []
    for index, rule in enumerate(rules, start=1):
        score, development_metric = scored[rule]
        info = sel["stability"][rule]
        warnings = ["Raw descriptive association; not adjusted and not causal."]
        if info.consistency < 1.0:
            warnings.append("Harm direction is not stable across all later chronological splits.")
        if actionability_label(rule) != "HIGH":
            warnings.append(
                "Actionability requires business review; condition may not be controllable."
            )
        candidates.append(
            Candidate(
                candidate_id=f"CAND-{index:03d}",
                conditions=rule,
                fit_split="development",
                development=development_metric,
                validation=info.validation,
                future_holdout=info.future_holdout,
                temporal_direction_consistency=info.consistency,
                actionability=actionability_label(rule),
                rank_score=score,
                warnings=tuple(warnings),
            )
        )
    outcome = primary_outcome()
    return {
        "methodology_version": DISCOVERY_METHOD_VERSION,
        "search": {**asdict(config), "evaluated_hypotheses": state["evaluated"]},
        "outcome": {
            "outcome_id": outcome.outcome_id,
            "column": outcome.column,
            "unit": outcome.unit,
            "higher_is_worse": outcome.higher_is_worse,
        },
        "candidate_count": len(candidates),
        "candidates": [asdict(candidate) for candidate in candidates],
        "evidence_boundary": "Candidate discovery only; requires Statistics validation.",
        "k1_reservation": {"eligible": False, "activated": False, "promoted_conditions": None,
                           "displaced_conditions": None},
    }


def validate_and_score(draw: Any, doc: dict[str, Any], tag: str, tmp: Path) -> dict[str, Any]:
    """Real `run_validation` + real `score()`, exactly as TASK-109's `run_seed`."""
    family_size = int(doc["search"]["evaluated_hypotheses"])
    cpath = tmp / f"candidates-{tag}.json"
    cpath.write_text(
        json.dumps({**doc, "status": "PERSISTED", "run_id": f"task117-{tag}"}, sort_keys=True, default=str),
        encoding="utf-8",
    )
    validation_outcome, outcome_version = outcome_definition_from_manifest(draw.manifest, draw.root)
    validations, summary = run_validation(
        dataset_root=draw.root,
        candidates_path=cpath,
        outcome=validation_outcome,
        dataset_version=str(draw.manifest["dataset_version"]),
        outcome_definition_version=outcome_version,
        analysis_run_id=f"task117-{tag}",
    )
    if int(summary["family_size"]) != family_size:
        raise SystemExit(f"{tag}: family size mismatch {summary['family_size']} != {family_size}")
    cands: list[Any] = []
    levels: dict[str, Any] = {}
    for raw, validation in zip(doc["candidates"], validations, strict=True):
        report = validation.report
        level = None if report.evidence_level is None else str(report.evidence_level)
        gates = _gate_map(report.gate_results)
        levels[str(raw["candidate_id"])] = {
            "verdict": validation.verdict,
            "evidence_level": level,
            "failed_gates": sorted(g for g, info in gates.items() if info["outcome"] == "fail"),
        }
        cands.append(
            scoring.Candidate(
                candidate_id=str(raw["candidate_id"]),
                conditions=tuple(
                    scoring.CondSpec(str(c["feature"]), str(c["operator"]), c["value"])
                    for c in raw["conditions"]
                ),
                evidence_level=level,
                policy_readiness=str(report.policy_readiness),
            )
        )
    result = scoring.score(draw.space, rbe.targets_for_draw(draw), rbe.traps_list(), cands)
    core = result["strata"]["core"]
    return {
        "specific_targets": core["specific_targets"][f"{THETA_J:.2f}"],
        "coverage_targets": core["coverage_targets"],
        "validation": levels,
    }


# --------------------------------------------------------------------------------- productivity --
class Productivity:
    def __init__(self, draw: Any) -> None:
        self.space = draw.space
        self.targets = rbe.targets_for_draw(draw)
        self.by_id = {t.target_id: t for t in self.targets}
        self.cache: dict[Rule, tuple[str | None, dict[str, Any]]] = {}

    def credited(self, rule: Rule) -> tuple[str | None, dict[str, Any]]:
        if rule in self.cache:
            return self.cache[rule]
        spec = to_spec(rule)
        exposed = self.space.rule_mask(spec)
        eff = scoring.effective_rule(self.space, spec)
        best_j, best_t, best_pm = 0.0, None, None
        for t in sorted(self.targets, key=lambda x: x.target_id):
            if not t.assessed:
                continue
            pm = scoring.pair_metrics(self.space, eff.conditions, exposed, t)
            if pm.j_e > best_j:
                best_j, best_t, best_pm = pm.j_e, t.target_id, pm
        ok = best_pm is not None and scoring.metric_specific(best_pm, THETA_J, THETA_P)
        out = (best_t if ok else None, {"credited": best_t, "j_e": best_j,
                                        "cp": None if best_pm is None else best_pm.cp})
        self.cache[rule] = out
        return out

    def productive_for(self, rule: Rule, tid: str) -> bool:
        target = self.by_id[tid]
        # cheap necessary condition: Cp = 1 needs every effective condition on a canonical feature,
        # and vacuity can only drop conditions, so at least one raw condition must be canonical.
        feats = {c.feature for c in target.conditions}
        if not any(c.feature in feats for c in rule):
            return False
        return self.credited(rule)[0] == tid


# -------------------------------------------------------------------------------- lineage logic --
def subset_status(s: Rule, state: dict[str, Any], ranks: dict[int, dict[Rule, int]]) -> dict[str, Any]:
    d = len(s)
    return {
        "conditions": label(s),
        "atoms_present": all(c in state["atoms"] for c in s),
        "generated": s in state["frontiers"].get(d, set()),
        "ineligible": s in state["ineligible"].get(d, set()),
        "identical_dropped": s in state["identical_dropped"],
        "scored": s in state["scored"],
        "rank_at_depth": ranks.get(d, {}).get(s),
        "n_scored_at_depth": len(ranks.get(d, {})),
        "in_beam": s in state["beams"].get(d, []),
    }


def classify_generation(s: Rule, state: dict[str, Any], ranks: dict[int, dict[Rule, int]]) -> dict[str, Any]:
    """First divergence for a productive canonical subset that was not scored (preregistration)."""
    if not all(c in state["atoms"] for c in s):
        return {"cause": "a", "principle": "VOCABULARY"}
    d = len(s)
    if s in state["frontiers"].get(d, set()):
        if s in state["ineligible"].get(d, set()):
            return {"cause": "e", "principle": "ELIGIBILITY", "detail": "child ineligible"}
        return {"cause": "d'", "principle": "EXPOSURE_IDENTICAL_DROP"}
    parents = [tuple(c for c in s if c != r) for r in s]
    if any(p in state["beams"].get(d - 1, []) for p in parents):
        return {"cause": "c", "principle": "ENUMERATION"}
    scored_parents = [p for p in parents if p in state["scored"]]
    if scored_parents:
        best = min(scored_parents, key=lambda p: ranks[d - 1][p])
        return {"cause": "b", "principle": "BEAM_SELECTION", "parent": label(best),
                "parent_rank": ranks[d - 1][best], "n_scored_at_parent_depth": len(ranks[d - 1]),
                "beam_size": len(state["beams"][d - 1]), "_parent": best}
    inner = [classify_generation(p, state, ranks) for p in parents]
    return {"cause": "e", "principle": "ELIGIBILITY", "detail": "no parent scored",
            "parents": [{k: v for k, v in i.items() if not k.startswith("_")} for i in inner]}


def depth_ranks(scored: dict[Rule, tuple[float, Any]]) -> dict[int, dict[Rule, int]]:
    out: dict[int, dict[Rule, int]] = {}
    for d in (1, 2, 3):
        rules = sorted((r for r in scored if len(r) == d), key=lambda r: (-scored[r][0], r))
        out[d] = {r: i + 1 for i, r in enumerate(rules)}
    return out


# ------------------------------------------------------------------------------------- one seed --
def run_seed(seed: int, out: Path) -> None:
    frozen_before = rbe.verify_frozen_state()
    committed = json.loads((RAW_109 / f"seed-{seed}.json").read_text(encoding="utf-8"))
    baseline_specific = set(committed["score"]["strata"]["core"]["specific_targets"][f"{THETA_J:.2f}"])
    with tempfile.TemporaryDirectory(prefix=f"task117-{seed}-") as tmpdir:
        tmp = Path(tmpdir)
        draw = vc.build_draw(seed, tmp, tg.DESIGNS)
        config = DiscoveryConfig(seed=seed)
        state = search(draw.frame, draw.features, config)
        sel = final_select(draw.frame, state, config)
        selected: list[Rule] = sel["selected"]

        committed_rules = [
            [f"{c['feature']} {c['operator']} {c['value']}" for c in cand["conditions"]]
            for cand in committed["engine"]["candidates"]
        ]
        fidelity = [label(r) for r in selected] == committed_rules and (
            state["evaluated"] == committed["engine"]["evaluated_hypotheses"]
        )
        prod = Productivity(draw)
        ranks = depth_ranks(state["scored"])
        eff = sel["effective_score"]
        last_selected_eff = eff[selected[-1]]
        interactions = [r for r in state["scored"] if len(r) >= 2]
        productive_any = [r for r in state["scored"] if any(prod.productive_for(r, t) for t in TRACKED)]
        sel["prepare"](productive_any)
        # Exact pruning for the rank statistic: effective = raw * (1 + w * consistency) with
        # consistency <= 1 and raw > 0 for every scored rule, so effective <= (1 + w) * raw. A rule whose
        # raw score is below min(effective of the productive rules) / (1 + w) cannot outrank any of
        # them, and its effective score is not needed to rank them.
        bound = 1.0 + config.stability_credit_weight
        floor = min((eff[r] for r in productive_any), default=float("inf")) / bound
        contenders = [r for r in interactions if state["scored"][r][0] >= floor]
        sel["prepare"](contenders)
        contenders.sort(key=lambda r: (-eff[r], r))

        def eff_rank_of(rule: Rule) -> int:
            key = (-eff[rule], rule)
            return 1 + sum(1 for q in contenders if (-eff[q], q) < key)

        interactions_by_eff = interactions  # only its length is reported

        targets: dict[str, Any] = {}
        for tid in TRACKED:
            canon = canonical(tid)
            subsets = [tuple(sorted(c)) for d in range(1, len(canon) + 1) for c in itertools.combinations(canon, d)]
            productive_scored = [r for r in state["scored"] if prod.productive_for(r, tid)]
            productive_selected = [r for r in selected if r in productive_scored]
            prod_subsets = [s for s in subsets if prod.productive_for(s, tid)]
            rec: dict[str, Any] = {
                "canonical": label(canon),
                "all_literals_atoms": all(c in state["atoms"] for c in canon),
                "baseline_specific_task109": tid in baseline_specific,
                "subsets": {" & ".join(label(s)): {**subset_status(s, state, ranks),
                                                    "productive": s in prod_subsets} for s in subsets},
                "n_productive_scored": len(productive_scored),
                "productive_in_final_top15": [label(r) for r in productive_selected],
            }
            if productive_scored:
                best = min(productive_scored, key=lambda r: (-eff[r], r))
                rec["best_productive_scored"] = {
                    "conditions": label(best),
                    "development_score": state["scored"][best][0],
                    "effective_score": eff[best],
                    "effective_rank_among_interactions": eff_rank_of(best) if len(best) >= 2 else None,
                    "n_interactions": len(interactions_by_eff),
                    "effective_score_of_15th_selected": last_selected_eff,
                    "ratio_to_15th_selected": eff[best] / last_selected_eff,
                    "n_exposed_development": state["scored"][best][1].n_exposed,
                }
            # --- first divergence -------------------------------------------------------------
            if productive_selected:
                rec["divergence"] = {"cause": None, "principle": "NONE_PRODUCTIVE_SELECTED"}
            elif productive_scored:
                rec["divergence"] = {"cause": "d", "principle": "FINAL_SELECTION"}
            else:
                options = [classify_generation(s, state, ranks) for s in prod_subsets]
                beam_opts = [o for o in options if o["principle"] == "BEAM_SELECTION"]
                chosen = (min(beam_opts, key=lambda o: o["parent_rank"]) if beam_opts
                          else (options[0] if options else {"cause": "e", "principle": "NO_PRODUCTIVE_SUBSET"}))
                rec["divergence"] = {k: v for k, v in chosen.items() if not k.startswith("_")}
                rec["_force_parent"] = chosen.get("_parent")
                rec["_force_depth"] = len(chosen["_parent"]) if chosen.get("_parent") else None
            targets[tid] = rec

        # --- one-step counterfactual replays (only where the target is not Specific at baseline) --
        for tid in TRACKED:
            rec = targets[tid]
            principle = rec["divergence"]["principle"]
            cf: dict[str, Any] = {"applicable": not rec["baseline_specific_task109"]}
            if not cf["applicable"]:
                rec["counterfactual"] = cf
                continue
            if principle == "FINAL_SELECTION":
                best = next(r for r in state["scored"]
                            if label(r) == rec["best_productive_scored"]["conditions"])
                forced = [*selected[:-1], best]
                vs = validate_and_score(draw, assemble(forced, state, sel, config), f"{seed}-{tid}-final", tmp)
                cand_id = f"CAND-{len(forced):03d}"
                cf.update({"intervention": "force best productive rule into final slot 15",
                           "displaced": label(selected[-1]),
                           "forced_validation": vs["validation"][cand_id],
                           "restored_specific": tid in vs["specific_targets"],
                           "interventions_needed": 1 if tid in vs["specific_targets"] else None})
            elif principle == "BEAM_SELECTION":
                parent = rec.pop("_force_parent")
                depth = rec.pop("_force_depth")
                state2 = search(draw.frame, draw.features, config, force_beam={depth: parent})
                sel2 = final_select(draw.frame, state2, config)
                prod_sel = [r for r in sel2["selected"] if prod.productive_for(r, tid)]
                prod_scored = [r for r in state2["scored"] if prod.productive_for(r, tid)]
                cf.update({"intervention": f"force parent into depth-{depth} beam", "parent": label(parent),
                           "productive_generated_after": len(prod_scored),
                           "productive_selected_after": [label(r) for r in prod_sel]})
                if prod_sel:
                    vs = validate_and_score(draw, assemble(sel2["selected"], state2, sel2, config),
                                            f"{seed}-{tid}-beam", tmp)
                    cf["restored_specific"] = tid in vs["specific_targets"]
                    cf["interventions_needed"] = 1 if cf["restored_specific"] else None
                elif prod_scored:
                    sel2["prepare"](prod_scored)
                    best2 = min(prod_scored, key=lambda r: (-sel2["effective_score"][r], r))
                    forced = [*sel2["selected"][:-1], best2]
                    vs = validate_and_score(draw, assemble(forced, state2, sel2, config),
                                            f"{seed}-{tid}-beam+final", tmp)
                    cf["restored_specific"] = False
                    cf["second_intervention"] = {"intervention": "force into final slot 15",
                                                 "restored_specific": tid in vs["specific_targets"]}
                    cf["interventions_needed"] = 2 if tid in vs["specific_targets"] else None
                else:
                    cf["restored_specific"] = False
                    cf["interventions_needed"] = None
            else:
                cf.update({"intervention": None, "restored_specific": False,
                           "note": "no one-step forcing defined for this principle (preregistration)"})
            rec["counterfactual"] = cf
        for rec in targets.values():
            rec.pop("_force_parent", None)
            rec.pop("_force_depth", None)

    frozen_after = rbe.verify_frozen_state()
    result = {
        "seed": seed,
        "frozen_before": frozen_before,
        "frozen_after": frozen_after,
        "fidelity_matches_task109": fidelity,
        "evaluated_hypotheses": state["evaluated"],
        "selected": [label(r) for r in selected],
        "targets": targets,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"seed {seed}: fidelity={fidelity} wrote {out}", flush=True)


def run_seed_if_missing(seed: int, out: Path) -> None:
    """Skip a seed another concurrent batch has already written (checked when the seed starts)."""
    if out.exists():
        print(f"seed {seed}: already present, skipped", flush=True)
        return
    run_seed(seed, out)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("batch")
    b.add_argument("--seeds", type=int, nargs=2, required=True)
    b.add_argument("--dir", type=Path, required=True)
    b.add_argument("--procs", type=int, default=1)
    b.add_argument("--reverse", action="store_true")
    a = ap.parse_args()
    if a.cmd == "seed":
        run_seed(a.seed, a.out)
    else:
        todo = [(x, a.dir / f"seed-{x}.json") for x in range(a.seeds[0], a.seeds[1] + 1)
                if not (a.dir / f"seed-{x}.json").exists()]
        if a.reverse:
            todo.reverse()
        with Pool(a.procs) as pool:
            pool.starmap(run_seed_if_missing, todo, chunksize=1)


if __name__ == "__main__":
    main()
