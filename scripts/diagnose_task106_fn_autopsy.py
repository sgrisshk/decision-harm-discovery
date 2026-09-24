"""POST-HOC DIAGNOSTIC (`TASK-106`, `ADR-105`/`ADR-103`): per-pattern FN autopsy of travel's
scoreable patterns at the FROZEN engine (`discovery-engine-v0.6.2`, `engine.py` sha256 prefix
`fefceeaac20e8ff7`, validation contract 1.3.0, no `G17`).

Forensic only. It changes no engine, gate, threshold, generator, catalogue or denominator; it
imports the real, unmodified production functions and only records what they do. It re-uses
`scripts/diagnose_oracle_decomposition.py` (`trace_search`, `build_projection`, true-rule parsing,
exact-true-rule reference) and `scripts/diagnose_validation_power.py` (power reference, gate map)
rather than re-deriving them.

Two subcommands:

* `seed --seed S --out F [--engine] [--trace]` — one benchmark realisation. `S == 20260813` is the
  committed benchmark (`travel-bookings-analytical-v1.1.0`, asserted against the committed dataset
  identity); any other `S` re-runs the *unchanged* generator with that seed and rebuilds the
  analytical dataset with the unchanged builder. Per pattern it records: ground truth, the exact
  true rule's engine eligibility and G03/G05 power bound, the tightest engine-representable
  ("oracle projection") rule and what the real validation contract says about it. With `--engine`
  it also runs the real `discover_candidates`, validates the 15 candidates with the real contract
  and scores each candidate x pattern under BOTH TASK-028's lenient statistic (recall >= 0.5) and
  a specific-rule statistic (Jaccard >= 0.5). With `--trace` (committed seed only) it also traces
  the search pool.
* `exact --seed S --out F` — the EXACT true rule (incl. calendar conjuncts) graded by the real
  contract as one idealised Boolean atom (not engine-representable; tests statistical
  detectability only). `rates --dirs D... --out F` — detectability rates with Wilson intervals.
  `poolrules` — counterfactual validation of the closest pool rule. `engine-summary` — engine
  outcomes over seeds. `--family-size N` overrides the oracle multiplicity family (sensitivity).

Pre-declared matching definitions (fixed before any Jaccard was computed):
  lenient  = candidate exposed-set recall of the pattern's affected records >= 0.5 (TASK-028)
  specific = Jaccard(candidate exposed set, pattern affected set) >= 0.5
Sensitivity thresholds 0.3 is also reported. A candidate that is lenient-only is a broad rule.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import polars as pl  # noqa: E402
from diagnose_oracle_decomposition import (  # noqa: E402
    _frame_mask,
    _render_rule,
    _rule_expr_local,
    _true_rule_reference,
    build_projection,
    trace_search,
)
from diagnose_validation_power import _gate_map, _true_rule_power_reference  # noqa: E402
from evaluate_benchmark import _scoreable_pattern_ids  # noqa: E402
from policy_analytics.analytical_dataset import build_analytical_dataset  # noqa: E402
from policy_analytics.discovery.engine import (  # noqa: E402
    DISCOVERY_METHOD_VERSION,
    Condition,
    DiscoveryConfig,
    _atoms,
    discover_candidates,
)
from policy_analytics.outcomes import (  # noqa: E402
    outcome_definition_from_manifest,
    primary_outcome,
)
from policy_analytics.synthetic_benchmark import BenchmarkConfig, generate_benchmark  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    load_analytical_frame,
    run_validation,
)
from policy_analytics.validation.contract import (  # noqa: E402
    DEFAULT_THRESHOLDS,
    LEVEL_REQUIREMENTS,
    GateId,
)
from policy_schemas.domain import EvidenceLevel  # noqa: E402

COMMITTED_SEED = 20260813
COMMITTED_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
COMMITTED_GT = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
COMMITTED_IDENTITY = "b6128eb3c1bdb36515c90570aa4ccabfc3dff8d1026d9002f1c832774b60a683"
TASK103_RUN1 = REPOSITORY / "docs/benchmark/task-103-evidence/run1"
ENGINE_PATH = REPOSITORY / "packages/analytics/src/policy_analytics/discovery/engine.py"
FROZEN_ENGINE_SHA_PREFIX = "fefceeaac20e8ff7"
FROZEN_METHOD_VERSION = "discovery-engine-v0.6.2"
FROZEN_CONTRACT = "1.3.0"
#: Family size of the frozen v0.6.2 search (TASK-103), used for every oracle validation so all
#: seeds share one multiplicity family. Disclosed: engine runs on other seeds evaluate ~this many.
ORACLE_FAMILY_SIZE = 36791
LENIENT_RECALL = 0.5
SPECIFIC_JACCARD = 0.5
SENSITIVITY_JACCARD = 0.3
LEVEL2_GATES = tuple(
    gate.value
    for gate in GateId
    if gate in LEVEL_REQUIREMENTS[EvidenceLevel.PREDICTIVE]
    and gate not in LEVEL_REQUIREMENTS[EvidenceLevel.DESCRIPTIVE]
)
PREDICTIVE_OR_ABOVE = (
    "predictive_association",
    "adjusted_observational_association",
    "quasi_causal_evidence",
    "experimental_evidence",
)


def frozen_version_record() -> dict[str, Any]:
    sha = hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest()
    defaults: dict[str, Any] = dict(asdict(DiscoveryConfig()))
    record: dict[str, Any] = {
        "discovery_method_version": DISCOVERY_METHOD_VERSION,
        "engine_py_sha256": sha,
        "validation_contract_version": DEFAULT_THRESHOLDS.version,
        "gate_ids": sorted(gate.value for gate in GateId),
        "g17_present": any("G17" in gate.value for gate in GateId),
        "discovery_config_defaults": {
            k: (list(cast("tuple[Any, ...]", v)) if isinstance(v, tuple) else v)
            for k, v in defaults.items()
        },
    }
    if (
        DISCOVERY_METHOD_VERSION != FROZEN_METHOD_VERSION
        or not sha.startswith(FROZEN_ENGINE_SHA_PREFIX)
        or DEFAULT_THRESHOLDS.version != FROZEN_CONTRACT
        or record["g17_present"]
    ):
        raise SystemExit(f"NOT the frozen engine/contract: {record}")
    return record


def _prepare_dataset(seed: int, work: Path) -> tuple[Path, Path]:
    if seed == COMMITTED_SEED:
        manifest = json.loads((COMMITTED_ROOT / "manifest.json").read_text(encoding="utf-8"))
        if manifest["dataset_identity_sha256"] != COMMITTED_IDENTITY:
            raise SystemExit("committed dataset identity drifted")
        return COMMITTED_ROOT, COMMITTED_GT
    generate_benchmark(work / "g", BenchmarkConfig(seed=seed))
    manifest = build_analytical_dataset(
        work / "g/reference/travel_bookings_clean.csv",
        work / "g/metadata/feature_timing.json",
        work / "a",
    )
    return work / "a" / str(
        manifest["dataset_version"]
    ), work / "g/evaluation/hidden_ground_truth.json"


def _validate_rules(
    root: Path,
    rules: list[tuple[str, tuple[Condition, ...]]],
    family_size: int,
    label: str,
) -> dict[str, Any]:
    """Real, unmodified `run_validation` on a list of (id, rule); returns id -> summary."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    validation_outcome, outcome_version = outcome_definition_from_manifest(manifest, root)
    outcome = primary_outcome()
    docs = [
        {
            "candidate_id": cid,
            "conditions": [
                {"feature": c.feature, "operator": c.operator, "value": c.value} for c in rule
            ],
            "outcome": outcome.outcome_id,
            "discovery_method": DISCOVERY_METHOD_VERSION,
            "description": f"POST-HOC DIAGNOSTIC (TASK-106) {label}: {_render_rule(rule)}",
            "warnings": ["POST-HOC DIAGNOSTIC; not a discovered or selected candidate."],
        }
        for cid, rule in rules
    ]
    document = {
        "schema_version": "1.1.0",
        "run_id": f"task106-{label}",
        "status": "PERSISTED",
        "candidates": docs,
    }
    out: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmp:
        cpath = Path(tmp) / "candidates.json"
        cpath.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        mpath = Path(tmp) / "metrics.json"
        mpath.write_text(json.dumps({"evaluated_hypotheses": family_size}), encoding="utf-8")
        validations, summary = run_validation(
            dataset_root=root,
            candidates_path=cpath,
            outcome=validation_outcome,
            dataset_version=str(manifest["dataset_version"]),
            outcome_definition_version=outcome_version,
            analysis_run_id=f"task106-{label}",
            metrics_path=mpath,
        )
    if int(summary["family_size"]) != family_size:
        raise SystemExit("family size mismatch")
    for (cid, _), validation in zip(rules, validations, strict=True):
        report = validation.report
        gates = _gate_map(report.gate_results)
        failed = sorted(g for g, info in gates.items() if info["outcome"] == "fail")
        out[cid] = {
            "verdict": validation.verdict,
            "evidence_level": str(report.evidence_level),
            "policy_readiness": str(report.policy_readiness),
            "failed_gates": failed,
            "level2_failed_gates": [g for g in failed if g in LEVEL2_GATES],
            "g06": gates.get("G06_CONFOUNDING_ADJUSTMENT", gates.get("G06", {})).get("outcome"),
            "gate_outcomes": {g: info["outcome"] for g, info in sorted(gates.items())},
            "g05_detail": next(
                (info["detail"] for g, info in gates.items() if g.startswith("G05")), None
            ),
            "exposed_records_development": report.exposed_records,
        }
    return out


def _summarise_pattern(pid: str, cand_rows: list[dict[str, Any]]) -> dict[str, Any]:
    def recall(c: dict[str, Any]) -> float:
        return float(c["per_pattern"][pid]["recall"])

    def jac(c: dict[str, Any]) -> float:
        return float(c["per_pattern"][pid]["jaccard"])

    def predictive(c: dict[str, Any]) -> bool:
        return bool(c["evidence_level"] in PREDICTIVE_OR_ABOVE)

    def ids(selected: list[dict[str, Any]]) -> list[str]:
        return [str(c["candidate_id"]) for c in selected]

    best = max(cand_rows, key=jac)
    pred_rows = [c for c in cand_rows if predictive(c)]
    best_pred = max(pred_rows, key=jac, default=None)
    return {
        "lenient_any_level": ids([c for c in cand_rows if recall(c) >= LENIENT_RECALL]),
        "lenient_predictive": ids([c for c in pred_rows if recall(c) >= LENIENT_RECALL]),
        "specific_any_level": ids([c for c in cand_rows if jac(c) >= SPECIFIC_JACCARD]),
        "specific_predictive": ids([c for c in pred_rows if jac(c) >= SPECIFIC_JACCARD]),
        "sensitivity_j0.3_any_level": ids([c for c in cand_rows if jac(c) >= SENSITIVITY_JACCARD]),
        "sensitivity_j0.3_predictive": ids([c for c in pred_rows if jac(c) >= SENSITIVITY_JACCARD]),
        "best_jaccard_candidate": best["candidate_id"],
        "best_jaccard": jac(best),
        "best_jaccard_evidence_level": best["evidence_level"],
        "best_jaccard_predictive_candidate": None
        if best_pred is None
        else best_pred["candidate_id"],
        "best_jaccard_predictive": None if best_pred is None else jac(best_pred),
        "promoted_any_matching": ids(
            [
                c
                for c in cand_rows
                if c["policy_readiness"] in ("shadow_policy", "high_confidence")
                and recall(c) >= LENIENT_RECALL
            ]
        ),
    }


def _score_candidates(
    frame: pl.DataFrame,
    candidates: list[dict[str, Any]],
    validations: dict[str, Any],
    pattern_masks: dict[str, int],
    scoreable: list[str],
) -> dict[str, Any]:
    n_rows = frame.height
    cand_rows: list[dict[str, Any]] = []
    for cand in candidates:
        rule = tuple(Condition(c["feature"], c["operator"], c["value"]) for c in cand["conditions"])
        mask = _frame_mask(frame, _rule_expr_local(rule))
        exposed = mask.bit_count()
        per: dict[str, Any] = {}
        for pid, affected in pattern_masks.items():
            inter = (mask & affected).bit_count()
            union = (mask | affected).bit_count()
            n_aff = affected.bit_count()
            per[pid] = {
                "recall": inter / n_aff if n_aff else 0.0,
                "precision": inter / exposed if exposed else 0.0,
                "jaccard": inter / union if union else 0.0,
            }
        val = validations[cand["candidate_id"]]
        cand_rows.append(
            {
                "candidate_id": cand["candidate_id"],
                "rule": _render_rule(rule),
                "n_exposed_full_cohort": exposed,
                "support_full_cohort": exposed / n_rows,
                "evidence_level": val["evidence_level"],
                "policy_readiness": val["policy_readiness"],
                "verdict": val["verdict"],
                "failed_gates": val["failed_gates"],
                "level2_failed_gates": val["level2_failed_gates"],
                "per_pattern": per,
                "lenient_matches": [p for p in pattern_masks if per[p]["recall"] >= LENIENT_RECALL],
                "specific_matches": [
                    p for p in pattern_masks if per[p]["jaccard"] >= SPECIFIC_JACCARD
                ],
            }
        )
    summary = {pid: _summarise_pattern(pid, cand_rows) for pid in scoreable}
    return {"candidates": cand_rows, "per_pattern": summary}


def run_seed(seed: int, out: Path, with_engine: bool, with_trace: bool) -> None:
    version = frozen_version_record()
    cand_list: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"task106-seed{seed}-") as tmp:
        root, gt_path = _prepare_dataset(seed, Path(tmp))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        frame = load_analytical_frame(root)
        timing = {n: str(m["classification"]) for n, m in manifest["feature_timing"].items()}
        feature_columns = tuple(
            n
            for n in frame.columns
            if timing.get(n) == "DECISION_TIME" and n not in {"booking_date", "travel_date"}
        )
        outcome = primary_outcome()
        config = DiscoveryConfig()
        development = frame.filter(pl.col("split_label") == "development")  # pyright: ignore[reportUnknownMemberType]
        dev_ids = frozenset(cast("list[str]", development["booking_id"].to_list()))
        scoreable = list(_scoreable_pattern_ids(gt, dev_ids))
        atoms = _atoms(development, feature_columns, config)
        frame_columns = frozenset(frame.columns)
        booking_ids = cast("list[str]", frame["booking_id"].to_list())
        index_of = {b: i for i, b in enumerate(booking_ids)}
        pattern_masks: dict[str, int] = {}
        for pattern in gt["patterns"]:
            packed = 0
            for b in pattern["affected_booking_ids"]:
                packed |= 1 << index_of[b]
            pattern_masks[str(pattern["id"])] = packed
        dev_sd = float(cast(float, development[outcome.column].std()))
        result: dict[str, Any] = {
            "seed": seed,
            "committed_benchmark": seed == COMMITTED_SEED,
            "frozen_version": version,
            "dataset_identity_sha256": manifest["dataset_identity_sha256"],
            "scoreable_pattern_ids": scoreable,
            "oracle_family_size": ORACLE_FAMILY_SIZE,
            "development_rows": development.height,
            "patterns": {},
        }
        oracle_rules: list[tuple[str, tuple[Condition, ...]]] = []
        for pattern in gt["patterns"]:
            pid = str(pattern["id"])
            affected = pattern_masks[pid]
            n_aff = affected.bit_count()
            n_dev = len(dev_ids & set(pattern["affected_booking_ids"]))
            projection = build_projection(
                pid,
                str(pattern["rule"]),
                atoms,
                feature_columns,
                frame_columns,
                timing,
                development,
                config,
            )
            exact = _true_rule_reference(frame, projection.true_conditions, outcome, config)
            power = _true_rule_power_reference(
                exact, development.height, dev_sd, ORACLE_FAMILY_SIZE
            )
            entry: dict[str, Any] = {
                "scoreable": pid in scoreable,
                "true_rule": str(pattern["rule"]),
                "n_affected": n_aff,
                "n_affected_development": n_dev,
                "realized_effect_eur": pattern["true_effect"]["realized_effect"],
                "exact_rule_reference": {
                    k: v for k, v in exact.items() if k != "sub_conjunction_ladder"
                },
                "exact_rule_dev_n_matches_ground_truth_ids": (
                    exact.get("development_n_exposed") == n_dev
                ),
                "exact_rule_power_bound": power,
                "exact_rule_power_bound_passes": None
                if power is None
                else bool(
                    power["g03_would_pass_on_power"]
                    and power["g03_would_pass_on_floors"]
                    and not power["conclusively_below_bh_at_any_rank"]
                ),
            }
            if projection.over_depth or not projection.atoms:
                entry["projection"] = None
            else:
                mask = _frame_mask(frame, _rule_expr_local(projection.atoms))
                inter = (mask & affected).bit_count()
                union = (mask | affected).bit_count()
                entry["projection"] = {
                    "rule": _render_rule(projection.atoms),
                    "recall": inter / n_aff if n_aff else 0.0,
                    "jaccard": inter / union if union else 0.0,
                    "broadening": mask.bit_count() / n_aff if n_aff else None,
                    "notes": projection.notes,
                }
                if pid in scoreable:
                    oracle_rules.append((pid, projection.atoms))
            result["patterns"][pid] = entry
        print(f"seed {seed}: validating {len(oracle_rules)} oracle projections", flush=True)
        oracle_val = _validate_rules(root, oracle_rules, ORACLE_FAMILY_SIZE, f"oracle-{seed}")
        for pid, val in oracle_val.items():
            result["patterns"][pid]["projection"]["oracle_validation"] = val
            result["patterns"][pid]["oracle_reaches_predictive"] = (
                val["evidence_level"] in PREDICTIVE_OR_ABOVE
            )

        if with_engine:
            if seed == COMMITTED_SEED:
                cand_doc = json.loads(
                    (TASK103_RUN1 / "candidates.json").read_text(encoding="utf-8")
                )
                cand_list = cast("list[dict[str, Any]]", cand_doc["candidates"])
                family = int(
                    json.loads((TASK103_RUN1 / "discovery_metrics.json").read_text())[
                        "evaluated_hypotheses"
                    ]
                )
                source = "TASK-103 run1 frozen candidates.json"
            else:
                print(f"seed {seed}: running real discover_candidates", flush=True)
                doc = discover_candidates(frame, feature_columns, outcome, config)
                cand_list = cast("list[dict[str, Any]]", doc["candidates"])
                family = int(doc["search"]["evaluated_hypotheses"])
                source = "discover_candidates() at frozen engine, default config"
            rules = [
                (
                    c["candidate_id"],
                    tuple(
                        Condition(x["feature"], x["operator"], x["value"]) for x in c["conditions"]
                    ),
                )
                for c in cand_list
            ]
            print(f"seed {seed}: validating {len(rules)} engine candidates", flush=True)
            cand_val = _validate_rules(root, rules, family, f"engine-{seed}")
            scored = _score_candidates(frame, cand_list, cand_val, pattern_masks, scoreable)
            scored["source"] = source
            scored["family_size"] = family
            result["engine"] = scored

        if with_trace:
            result["trace"] = _trace(
                frame, feature_columns, outcome, config, pattern_masks, scoreable, result, cand_list
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print(f"wrote {out}")


def _trace(
    frame: pl.DataFrame,
    feature_columns: tuple[str, ...],
    outcome: Any,
    config: DiscoveryConfig,
    pattern_masks: dict[str, int],
    scoreable: list[str],
    result: dict[str, Any],
    cand_list: list[dict[str, Any]],
) -> dict[str, Any]:
    print("tracing search pool (v0.6.2)", flush=True)
    trace = trace_search(frame, feature_columns, outcome, config)
    committed_rules = [
        tuple(
            sorted(Condition(c["feature"], c["operator"], c["value"]) for c in cand["conditions"])
        )
        for cand in cand_list
    ]
    if trace.evaluated != ORACLE_FAMILY_SIZE or committed_rules != trace.selected:
        raise SystemExit("trace does not reproduce the TASK-103 v0.6.2 search; refusing to report")
    pool_ranked = sorted(trace.scored, key=lambda r: (-trace.scored[r][0], r))
    pool_rank = {r: i + 1 for i, r in enumerate(pool_ranked)}
    atom_masks = {a: _frame_mask(frame, _rule_expr_local((a,))) for a in trace.atoms}
    full = (1 << frame.height) - 1

    def rmask(rule: tuple[Condition, ...]) -> int:
        packed = full
        for c in rule:
            packed &= (
                atom_masks[c] if c in atom_masks else _frame_mask(frame, _rule_expr_local((c,)))
            )
        return packed

    selected_set = set(trace.selected)
    out: dict[str, Any] = {
        "atoms": len(trace.atoms),
        "evaluated_hypotheses": trace.evaluated,
        "pool_size": len(pool_ranked),
        "phase_floor": trace.phase_floor,
        "phase_reference": trace.phase_reference,
        "fidelity": "evaluated_hypotheses and all 15 selected rules reproduce TASK-103 run1",
        "per_pattern": {},
    }
    masks_cache = {r: rmask(r) for r in pool_ranked}
    for pid in scoreable:
        affected = pattern_masks[pid]
        n_aff = affected.bit_count()
        best_j = (0.0, None)
        n_specific = 0
        n_lenient = 0
        for r, m in masks_cache.items():
            inter = (m & affected).bit_count()
            union = (m | affected).bit_count()
            j = inter / union if union else 0.0
            if inter / n_aff >= LENIENT_RECALL:
                n_lenient += 1
            if j >= SPECIFIC_JACCARD:
                n_specific += 1
            if j > best_j[0]:
                best_j = (j, r)
        entry: dict[str, Any] = {
            "pool_rules_lenient_match": n_lenient,
            "pool_rules_specific_match_j0.5": n_specific,
            "best_jaccard_in_pool": best_j[0],
        }
        br = best_j[1]
        if br is not None:
            phase = "interactions" if len(br) >= 2 else "singletons"
            eff = trace.effective_score.get(br)
            floor = trace.phase_floor.get(phase)
            entry["best_jaccard_rule"] = {
                "rule": _render_rule(br),
                "pool_rank": pool_rank[br],
                "selected": br in selected_set,
                "effective_score": eff,
                "phase_floor": floor,
                "clears_floor": None if eff is None or floor is None else bool(eff >= floor),
            }
        out["per_pattern"][pid] = entry
    # projection-level stage record uses the rule objects directly (re-derived, not parsed)
    development = frame.filter(pl.col("split_label") == "development")  # pyright: ignore[reportUnknownMemberType]
    gt = json.loads(COMMITTED_GT.read_text(encoding="utf-8"))
    timing_manifest = json.loads((COMMITTED_ROOT / "manifest.json").read_text(encoding="utf-8"))
    timing = {n: str(m["classification"]) for n, m in timing_manifest["feature_timing"].items()}
    for pattern in gt["patterns"]:
        pid = str(pattern["id"])
        if pid not in scoreable:
            continue
        proj = build_projection(
            pid,
            str(pattern["rule"]),
            trace.atoms,
            feature_columns,
            frozenset(frame.columns),
            timing,
            development,
            config,
        )
        if proj.over_depth or not proj.atoms:
            continue
        rule = proj.atoms
        depth = len(rule)
        stage: dict[str, Any] = {
            "rule": _render_rule(rule),
            "generated": rule in trace.generated_at_depth.get(depth, set()),
            "redundant_skipped_as_exposure_identical": rule
            in trace.redundant_at_depth.get(depth, set()),
            "eligible_and_scored": rule in trace.scored,
        }
        if rule in trace.scored:
            phase = "interactions" if depth >= 2 else "singletons"
            eff = trace.effective_score.get(rule)
            floor = trace.phase_floor.get(phase)
            stage.update(
                pool_rank=pool_rank[rule],
                effective_score=eff,
                phase_floor=floor,
                clears_floor=None if eff is None or floor is None else bool(eff >= floor),
                selected=rule in selected_set,
            )
        # nearest ancestor in the expansion beam?
        stage["ancestors_in_expansion_beam"] = [
            _render_rule(a)
            for d in range(1, depth)
            for a in trace.beam_at_depth.get(d, [])
            if set(a) <= set(rule)
        ]
        out["per_pattern"][pid]["projection_stage"] = stage
    return out


def _augment_with_exact_columns(
    root: Path, work: Path, frame: pl.DataFrame, pattern_masks: dict[str, int], pids: list[str]
) -> Path:
    """Copy of the analytical dataset with one extra Boolean DECISION_TIME feature per pattern,
    `oracle_exact_<Pxx>` = membership in the pattern's ground-truth affected set. Diagnostic only:
    it lets the real validation contract grade the EXACT true rule (including calendar conjuncts
    the engine vocabulary cannot express) as a single idealised boolean atom. The partition hash
    and column lists are updated so the real loader accepts the copy; the copy is never persisted.
    """
    dest = work / "exact_copy"
    dest.mkdir(parents=True, exist_ok=True)
    for path in root.iterdir():
        if path.is_file():
            (dest / path.name).write_bytes(path.read_bytes())
    features = pl.read_csv(root / "features.csv")
    for pid in pids:
        mask = pattern_masks[pid]
        bits = [bool((mask >> i) & 1) for i in range(frame.height)]
        features = features.with_columns(pl.Series(f"oracle_exact_{pid}", bits))
    features.write_csv(dest / "features.csv")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    part = manifest["partitions"]["features"]
    for pid in pids:
        name = f"oracle_exact_{pid}"
        part["columns"].append(name)
        part["schema"].append({"dtype": "Boolean", "name": name})
        manifest["feature_timing"][name] = {
            "classification": "DECISION_TIME",
            "discovery_feature_allowed": True,
            "leakage_risk": "LOW",
        }
    part["sha256"] = hashlib.sha256((dest / "features.csv").read_bytes()).hexdigest()
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dest


def run_exact(seed: int, out: Path) -> None:
    """Exact-true-rule oracle under the real contract (idealised single Boolean atom)."""
    frozen_version_record()
    with tempfile.TemporaryDirectory(prefix=f"task106-exact{seed}-") as tmp:
        root, gt_path = _prepare_dataset(seed, Path(tmp))
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        frame = load_analytical_frame(root)
        dev_frame = frame.filter(pl.col("split_label") == "development")  # pyright: ignore[reportUnknownMemberType]
        dev_ids = frozenset(cast("list[str]", dev_frame["booking_id"].to_list()))
        scoreable = list(_scoreable_pattern_ids(gt, dev_ids))
        index_of = {b: i for i, b in enumerate(cast("list[str]", frame["booking_id"].to_list()))}
        masks: dict[str, int] = {}
        for pattern in gt["patterns"]:
            packed = 0
            for b in pattern["affected_booking_ids"]:
                packed |= 1 << index_of[b]
            masks[str(pattern["id"])] = packed
        copy_root = _augment_with_exact_columns(root, Path(tmp), frame, masks, scoreable)
        rules = [(pid, (Condition(f"oracle_exact_{pid}", "eq", True),)) for pid in scoreable]
        val = _validate_rules(copy_root, rules, ORACLE_FAMILY_SIZE, f"exact-{seed}")
    payload = {
        "seed": seed,
        "scoreable_pattern_ids": scoreable,
        "family_size": ORACLE_FAMILY_SIZE,
        "note": "exact true rule as one idealised Boolean atom (k=1); not engine-representable",
        "exact_oracle_validation": val,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")


def _wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def rates(dirs: list[Path], out: Path) -> None:
    """Detectability rates over generator seeds, per pattern, with Wilson 95% intervals.

    Each dir holds per-seed files of one kind: `seed` files (engine-representable projection
    oracle) or `exact` files (idealised exact-rule oracle). The denominator for a pattern is the
    seeds in which that pattern is scoreable (TASK-028's own rule) in that seed's realisation.
    """
    result: dict[str, Any] = {}
    for d in dirs:
        files = sorted(d.glob("seed-*.json"))
        payloads = [json.loads(f.read_text(encoding="utf-8")) for f in files]
        block: dict[str, Any] = {"n_seeds": len(payloads)}
        for pid in ("P01", "P02", "P03", "P04", "P06", "P08", "P09"):
            rows: list[dict[str, Any]] = []
            for pl_ in payloads:
                if pid not in pl_["scoreable_pattern_ids"]:
                    continue
                if "exact_oracle_validation" in pl_:
                    rows.append(pl_["exact_oracle_validation"][pid])
                elif pl_["patterns"][pid]["projection"] is not None:
                    rows.append(pl_["patterns"][pid]["projection"]["oracle_validation"])
            n = len(rows)
            pred = sum(1 for r in rows if r["evidence_level"] in PREDICTIVE_OR_ABOVE)
            adj = sum(1 for r in rows if r["evidence_level"] in PREDICTIVE_OR_ABOVE[1:])
            fails: dict[str, int] = {}
            for r in rows:
                for g in r["level2_failed_gates"]:
                    fails[g] = fails.get(g, 0) + 1
            block[pid] = {
                "seeds_where_scoreable": n,
                "reaches_predictive": {
                    "k": pred,
                    "n": n,
                    "rate": pred / n if n else None,
                    "wilson95": _wilson(pred, n),
                },
                "reaches_adjusted_or_above": {"k": adj, "n": n},
                "level2_gate_failures": dict(sorted(fails.items())),
            }
        result[str(d)] = block
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for name, block in result.items():
        print(name, block["n_seeds"])
        for pid, v in block.items():
            if pid != "n_seeds":
                r = v["reaches_predictive"]
                print(
                    f"  {pid}: scoreable {v['seeds_where_scoreable']}, "
                    f"predictive {r['k']}/{r['n']} {r['wilson95']} "
                    f"adj {v['reaches_adjusted_or_above']['k']} {v['level2_gate_failures']}"
                )


def _parse_rendered_rule(text: str) -> tuple[Condition, ...]:
    conditions: list[Condition] = []
    for part in text.split(" AND "):
        feature, operator, raw = part.split(" ", 2)
        value: Any
        if raw in ("True", "False"):
            value = raw == "True"
        elif operator == "eq":
            value = raw
        else:
            value = float(raw)
        conditions.append(Condition(feature, cast(Any, operator), value))
    return tuple(conditions)


def run_poolrules(committed_json: Path, out: Path) -> None:
    """Counterfactual validation (real contract, family 36,791) of, per pattern, the pool rule
    with the highest Jaccard to the pattern (from the committed-seed trace). Answers: is the
    closest rule the v0.6.2 search ever scored itself one the contract would validate?"""
    frozen_version_record()
    data = json.loads(committed_json.read_text(encoding="utf-8"))
    rules = [
        (pid, _parse_rendered_rule(entry["best_jaccard_rule"]["rule"]))
        for pid, entry in data["trace"]["per_pattern"].items()
        if "best_jaccard_rule" in entry
    ]
    val = _validate_rules(COMMITTED_ROOT, rules, ORACLE_FAMILY_SIZE, "poolbest")
    rendered = {pid: _render_rule(rule) for pid, rule in rules}
    payload: dict[str, Any] = {
        "family_size": ORACLE_FAMILY_SIZE,
        "rules": rendered,
        "validation": val,
    }
    out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for pid, v in val.items():
        print(pid, rendered[pid], v["evidence_level"], v["level2_failed_gates"])


def engine_summary(in_dir: Path, out: Path) -> None:
    """Per-pattern engine outcomes over the seed files that carry an `engine` block."""
    seeds = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(in_dir.glob("seed-*.json"))]
    seeds = [s for s in seeds if "engine" in s]
    summary: dict[str, Any] = {"n_seeds": len(seeds), "seeds": [s["seed"] for s in seeds]}
    for pid in ("P01", "P02", "P03", "P04", "P06", "P08", "P09"):
        rows = [s["engine"]["per_pattern"][pid] for s in seeds if pid in s["engine"]["per_pattern"]]
        n = len(rows)
        entry: dict[str, Any] = {"n_seeds_scoreable": n}
        for key in (
            "lenient_predictive",
            "specific_any_level",
            "specific_predictive",
            "sensitivity_j0.3_predictive",
        ):
            k = sum(1 for r in rows if r[key])
            entry[key] = {"k": k, "n": n, "wilson95": _wilson(k, n)}
        entry["best_jaccard_per_seed"] = [round(r["best_jaccard"], 3) for r in rows]
        summary[pid] = entry
    out.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--engine", action="store_true")
    s.add_argument("--trace", action="store_true")
    s.add_argument("--family-size", type=int, default=None)
    x = sub.add_parser("exact")
    x.add_argument("--seed", type=int, required=True)
    x.add_argument("--out", type=Path, required=True)
    x.add_argument("--family-size", type=int, default=None)
    r = sub.add_parser("rates")
    r.add_argument("--dirs", type=Path, nargs="+", required=True)
    r.add_argument("--out", type=Path, required=True)
    q = sub.add_parser("poolrules")
    q.add_argument("--committed-json", type=Path, required=True)
    q.add_argument("--out", type=Path, required=True)
    a = sub.add_parser("engine-summary")
    a.add_argument("--in", dest="in_dir", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if getattr(args, "family_size", None):
        globals()["ORACLE_FAMILY_SIZE"] = int(args.family_size)
    if args.cmd == "seed":
        if args.trace and (args.seed != COMMITTED_SEED or not args.engine):
            raise SystemExit("--trace requires --engine and the committed seed")
        run_seed(args.seed, args.out, args.engine, args.trace)
    elif args.cmd == "poolrules":
        run_poolrules(args.committed_json, args.out)
    elif args.cmd == "rates":
        rates(args.dirs, args.out)
    elif args.cmd == "exact":
        run_exact(args.seed, args.out)
    else:
        engine_summary(args.in_dir, args.out)


if __name__ == "__main__":
    main()
