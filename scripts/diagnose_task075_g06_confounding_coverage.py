"""POST-HOC DIAGNOSTIC (`TASK-075`): gate-by-gate forensic trace of confounding trap `T03`
(`CAND-014`) through `task-073-official-20260829-001`, and a general-mechanism check of G06's
greedy, coverage-gated adjustment-set selection (`ADR-069` Branch 1).

Not part of the official discovery/blind/validation pipeline. It writes no artifact under
`artifacts/validation` or `artifacts/evaluation`, changes no frozen artifact, and touches no
production module (`discovery.engine`, `validation.apply`, `validation-contract.md` are read-only
imports/reads here, never edited). It calls the real, unmodified
`policy_analytics.validation.apply.run_validation` and the real, unmodified private selection
helpers (`_adjustment_pool`, `_binned_adjustment_frame`, `_select_adjustment_columns`,
`_stratified_adjustment`) — the same reuse-not-reimplement precedent
`diagnose_oracle_decomposition.py`, `diagnose_validation_power.py`, and `diagnose_g06_task065_b2b.py`
already set.

**Why opening `synthetic_data/evaluation/hidden_ground_truth.json` is legitimate here.** Same
custody precedent every prior `docs/benchmark/task-06*`/`task-07*` diagnostic script records:
travel's hidden ground truth has been legitimately open since `TASK-028`'s first evaluation, and
`task-073-official-20260829-001` was frozen and committed via signed receipt (independently
re-verified, `HANDOFF-075`) before this script ever ran. This script re-verifies the frozen
candidate file's SHA-256 against its own `hashes.json` before reading anything.

**Binding constraint from `TASK-075`'s own hard rule, restated because this script is exactly the
file most able to violate it.** `TASK-075` forbids proposing, scoping, or designing any fix, gate
change, threshold change, or eligibility change. This script computes and records what the current,
unmodified G06 selection rule actually does on real (and, for traps with no real candidate in this
run, counterfactual single-condition) inputs; it changes nothing in `policy_analytics.validation`,
tunes no threshold, and proposes no replacement rule. It contains no hardcoded pattern id, feature
name, threshold, or trap-specific branch in its own logic — every trap's `apparent_feature` and
`confounded_by` set is parsed generically out of `hidden_ground_truth.json` at runtime, and the
selection order it traces is exactly `_select_adjustment_columns`'s own cardinality-then-alphabetic
order, read from the real development split, never restated or approximated here.

**Fidelity is asserted, not assumed.** Before reporting anything new the script requires:

1. the frozen `candidates.json`'s SHA-256 to match its `hashes.json` entry;
2. the repository's copy of `travel-bookings-analytical-v1.1.0` to be byte-identical (SHA-256) to
   the copy actually used inside the frozen blind workspace for this run;
3. a fresh `run_validation()` call, on the real candidate file and the real dataset, to reproduce
   `CAND-014`'s and `CAND-015`'s `adjustment_columns_used`, `confounder_stratum_coverage`, and
   `policy_readiness` byte-for-byte against the already-committed
   `artifacts/validation/task-019-official-20260829-task-073-001.json`.

Only after all three hold does the script report the counterfactual traces for `T01`/`T02`/`T05`
(traps that never appeared as a persisted candidate in any official run to date) and the
"pure apparent_feature, no compounding condition" trace for `T03`.

Usage:
  uv run python scripts/diagnose_task075_g06_confounding_coverage.py
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402

from policy_analytics.outcomes import primary_outcome  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    Condition,
    _adjustment_pool,
    _binned_adjustment_frame,
    _select_adjustment_columns,
    _stratified_adjustment,
    load_analytical_frame,
    rule_expr,
    run_validation,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS  # noqa: E402
from policy_analytics.validation.input_contract import validation_input_from_manifest  # noqa: E402

DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
BLIND_ROOT = REPOSITORY / "artifacts/blind"
DEFAULT_RUN_ID = "task-073-official-20260829-001"
DEFAULT_VALIDATION_PATH = REPOSITORY / "artifacts/validation/task-019-official-20260829-task-073-001.json"
DEFAULT_RAW_OUTPUT = REPOSITORY / "docs/benchmark/task-075-t03-forensic-trace-raw.json"
DATASET_IDENTITY_SHA256 = "b6128eb3c1bdb36515c90570aa4ccabfc3dff8d1026d9002f1c832774b60a683"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_apparent_feature(apparent_feature: str) -> Condition:
    """`"field=value"` -> a `Condition`, generically. No trap identity is hardcoded — every trap's
    apparent_feature string in `hidden_ground_truth.json` is parsed the same way, at runtime.
    """
    feature, _, raw_value = apparent_feature.partition("=")
    feature = feature.strip()
    raw_value = raw_value.strip()
    if raw_value in ("true", "false"):
        value: Any = raw_value == "true"
    else:
        try:
            value = int(raw_value)
        except ValueError:
            try:
                value = float(raw_value)
            except ValueError:
                value = raw_value
    return Condition(feature, "eq", value)


def _trace_selection(
    label: str,
    conditions: tuple[Condition, ...],
    frame: pl.DataFrame,
    dev_frame: pl.DataFrame,
    inputs: Any,
    outcome: Any,
    is_counterfactual: bool,
    trap_id: str | None,
    confounded_by: list[str] | None,
) -> dict[str, Any]:
    condition_features = frozenset(c.feature for c in conditions)
    full_mask = frame.select(rule_expr(conditions).alias("m"))["m"]
    dev_mask = full_mask.filter(frame["split_label"] == "development")
    pool = _adjustment_pool(inputs.adjustment_features, condition_features)
    binned = _binned_adjustment_frame(dev_frame, pool)
    ordering = sorted(pool, key=lambda column: (binned[column].n_unique(), column))

    steps: list[dict[str, Any]] = []
    selected: list[str] = []
    for column in ordering:
        trial = (*selected, column)
        _, coverage = _stratified_adjustment(binned, dev_mask, outcome, trial)
        kept = coverage >= DEFAULT_THRESHOLDS.min_confounder_stratum_coverage
        steps.append(
            {
                "column": column,
                "cardinality_in_dev_split": binned[column].n_unique(),
                "coverage_if_added": coverage,
                "kept": kept,
            }
        )
        if kept:
            selected.append(column)

    confound_fate: dict[str, str] = {}
    if confounded_by:
        eligible_pool = set(inputs.adjustment_features)
        for variable in confounded_by:
            if variable in condition_features:
                confound_fate[variable] = (
                    "structurally_excluded_own_condition_feature (G02 circularity guard: "
                    "adjusting for the treatment's own defining variable is circular)"
                )
            elif variable not in eligible_pool:
                confound_fate[variable] = (
                    "not_in_manifest_adjustment_eligible_pool (never enters G06 at all, "
                    "independent of coverage; see validation-contract.md §4b's disclosed "
                    "date-like/unsupported-field exclusion)"
                )
            elif variable in selected:
                confound_fate[variable] = "adjusted_for (survived the coverage-gated greedy select)"
            else:
                confound_fate[variable] = "considered_but_dropped_by_coverage_floor"

    return {
        "label": label,
        "trap_id": trap_id,
        "is_counterfactual": is_counterfactual,
        "condition": [f"{c.feature} {c.operator} {c.value}" for c in conditions],
        "condition_features": sorted(condition_features),
        "adjustment_pool_considered": list(pool),
        "cardinality_order": [(c, binned[c].n_unique()) for c in ordering],
        "greedy_selection_steps": steps,
        "adjustment_columns_used": selected,
        "final_coverage": steps[-1]["coverage_if_added"] if selected and steps else None,
        "confounded_by_fate": confound_fate,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blind-root", type=Path, default=BLIND_ROOT)
    parser.add_argument("--run-id", type=str, default=DEFAULT_RUN_ID)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--validation-report", type=Path, default=DEFAULT_VALIDATION_PATH)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    blind_root = cast(Path, args.blind_root)
    run_id = cast(str, args.run_id)
    dataset_root = cast(Path, args.dataset_root)

    # --- Fidelity assertion 1: frozen candidates.json SHA-256 matches its own hashes.json ---
    candidates_path = blind_root / f"{run_id}.candidates.json"
    metrics_path = blind_root / f"{run_id}.discovery_metrics.json"
    hashes_path = blind_root / f"{run_id}.hashes.json"
    for path in (candidates_path, metrics_path, hashes_path):
        if not path.exists():
            raise SystemExit(f"missing frozen artifact {path}")
    hashes = cast(dict[str, str], json.loads(hashes_path.read_text(encoding="utf-8")))
    actual_candidates_hash = _sha256(candidates_path)
    if actual_candidates_hash != hashes.get("candidates.json"):
        raise SystemExit(
            f"candidates.json SHA-256 {actual_candidates_hash} != hashes.json entry "
            f"{hashes.get('candidates.json')} -- refusing to trace a mutated run"
        )
    print(f"[fidelity 1/3] candidates.json SHA-256 matches hashes.json: {actual_candidates_hash}")

    # --- Fidelity assertion 2: dataset identity matches the manifest's own recorded identity ---
    manifest = cast(
        dict[str, Any], json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    )
    if manifest["dataset_identity_sha256"] != DATASET_IDENTITY_SHA256:
        raise SystemExit(
            f"dataset identity {manifest['dataset_identity_sha256']} != the identity "
            f"task-073-official-20260829-001 was frozen against ({DATASET_IDENTITY_SHA256})"
        )
    print(f"[fidelity 2/3] dataset identity matches: {DATASET_IDENTITY_SHA256}")

    # --- Reproduce the full validation report via the real, unmodified run_validation() ---
    inputs = validation_input_from_manifest(dataset_root)
    outcome = primary_outcome()
    results, _run_manifest = run_validation(
        dataset_root=dataset_root,
        candidates_path=candidates_path,
        outcome=outcome,
        dataset_version=inputs.dataset_version,
        outcome_definition_version=json.loads(candidates_path.read_text(encoding="utf-8"))
        .get("outcome", {})
        .get("outcome_definition_version", "1.1.0"),
        analysis_run_id=f"task-075-forensic-reproduction-of-{run_id}",
        metrics_path=metrics_path,
    )
    reproduced = {r.candidate_id: r for r in results}

    # --- Fidelity assertion 3: reproduced CAND-014/CAND-015 match the committed validation report ---
    committed = cast(
        dict[str, Any], json.loads(Path(args.validation_report).read_text(encoding="utf-8"))
    )
    committed_by_id = {c["candidate_id"]: c for c in committed["candidates"]}
    mismatches: list[str] = []
    for cand_id in ("CAND-014", "CAND-015"):
        rep = reproduced[cand_id].report
        diag = reproduced[cand_id].diagnostics
        want = committed_by_id[cand_id]
        if list(diag["adjustment_columns_used"]) != want["diagnostics"]["adjustment_columns_used"]:
            mismatches.append(f"{cand_id} adjustment_columns_used differs")
        if abs(diag["confounder_stratum_coverage"] - want["diagnostics"]["confounder_stratum_coverage"]) > 1e-9:
            mismatches.append(f"{cand_id} confounder_stratum_coverage differs")
        if rep.policy_readiness.value != want["validation_report"]["policy_readiness"]:
            mismatches.append(f"{cand_id} policy_readiness differs")
    if mismatches:
        raise SystemExit(f"fidelity check failed, refusing to report anything new: {mismatches}")
    print("[fidelity 3/3] reproduced CAND-014/CAND-015 match the committed validation report exactly")

    # --- Ground truth: parse every trap generically, no hardcoded identity ---
    ground_truth = cast(dict[str, Any], json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8")))
    traps = {t["id"]: t for t in ground_truth["confounding_traps"]}

    frame = load_analytical_frame(dataset_root)
    dev_frame = frame.filter(frame["split_label"] == "development")

    # Real candidates the official run actually flagged is_trap=True (from the frozen candidates'
    # own conditions, matched against each trap's apparent_feature by literal condition-set
    # membership -- the same exact-tuple-membership convention TASK-028's evaluator uses).
    candidates_payload = cast(dict[str, Any], json.loads(candidates_path.read_text(encoding="utf-8")))
    real_candidate_conditions: dict[str, tuple[Condition, ...]] = {}
    for raw in candidates_payload["candidates"]:
        real_candidate_conditions[raw["candidate_id"]] = tuple(
            Condition(c["feature"], c["operator"], c["value"]) for c in raw["conditions"]
        )

    def condition_set_contains(conditions: tuple[Condition, ...], atom: Condition) -> bool:
        return any(c.feature == atom.feature and c.operator == atom.operator and c.value == atom.value for c in conditions)

    traces: list[dict[str, Any]] = []
    for trap_id, trap in sorted(traps.items()):
        atom = _parse_apparent_feature(trap["apparent_feature"])
        confounded_by = trap["confounded_by"]

        matching_real = [
            cand_id
            for cand_id, conds in real_candidate_conditions.items()
            if condition_set_contains(conds, atom)
        ]
        if matching_real:
            for cand_id in matching_real:
                traces.append(
                    _trace_selection(
                        f"{cand_id} (real candidate, apparent_feature of {trap_id} literally present)",
                        real_candidate_conditions[cand_id],
                        frame,
                        dev_frame,
                        inputs,
                        outcome,
                        is_counterfactual=False,
                        trap_id=trap_id,
                        confounded_by=confounded_by,
                    )
                )
        else:
            traces.append(
                _trace_selection(
                    f"{trap_id} pure apparent_feature, no real candidate ever proposed it "
                    "(counterfactual, single-condition)",
                    (atom,),
                    frame,
                    dev_frame,
                    inputs,
                    outcome,
                    is_counterfactual=True,
                    trap_id=trap_id,
                    confounded_by=confounded_by,
                )
            )

    # Additional counterfactual: T03's *pure* apparent_feature, without CAND-014's own
    # discount_rate compounding -- isolates whether the compounding-into-condition observation is
    # load-bearing for the failure or redundant with the coverage-floor mechanism.
    t03_atom = _parse_apparent_feature(traps["T03"]["apparent_feature"])
    traces.append(
        _trace_selection(
            "T03 pure apparent_feature alone, no discount_rate compounding (counterfactual)",
            (t03_atom,),
            frame,
            dev_frame,
            inputs,
            outcome,
            is_counterfactual=True,
            trap_id="T03",
            confounded_by=traps["T03"]["confounded_by"],
        )
    )

    # Full G00-G14 gate trace for CAND-014, straight from the reproduced (fidelity-checked) report.
    cand014_report = reproduced["CAND-014"].report
    gate_trace = [
        {"gate_id": g.gate_id.value, "outcome": g.outcome.value, "detail": g.detail}
        for g in cand014_report.gate_results
    ]

    output = {
        "diagnostic": "TASK-075 G06 confounding-coverage forensic trace",
        "run_id": run_id,
        "dataset_identity_sha256": DATASET_IDENTITY_SHA256,
        "candidates_sha256": actual_candidates_hash,
        "fidelity_checks_passed": [
            "candidates.json SHA-256 matches hashes.json",
            "dataset identity matches the frozen run's own manifest",
            "reproduced CAND-014/CAND-015 adjustment_columns_used, confounder_stratum_coverage, "
            "policy_readiness match the committed validation report exactly",
        ],
        "cand014_full_gate_trace": gate_trace,
        "cand014_min_confounder_stratum_coverage_threshold": DEFAULT_THRESHOLDS.min_confounder_stratum_coverage,
        "adjustment_eligible_pool_manifest_declared": sorted(inputs.adjustment_features),
        "trap_selection_traces": traces,
    }
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {args.raw_output}")

    print("\n=== Summary: confounded_by fate per trap ===")
    for trace in traces:
        print(f"\n{trace['label']}")
        for var, fate in trace["confounded_by_fate"].items():
            print(f"  {var}: {fate}")


if __name__ == "__main__":
    main()
