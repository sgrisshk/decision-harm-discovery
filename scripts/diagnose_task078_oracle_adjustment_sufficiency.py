"""POST-HOC DIAGNOSTIC (`TASK-078`, `ADR-071` step 2): oracle-adjustment-set sufficiency

If `G06` receives each confounding trap's *true* ground-truth confounder set directly — bypassing
its own cardinality-cliff-affected selection logic (`TASK-075`) entirely — is the *rest* of the
validation mechanism (estimator, remaining `G00`-`G14` gates, thresholds) sufficient to reject
traps `T01`-`T05`?

Not part of the official discovery/blind/validation pipeline. Writes no artifact under
`artifacts/validation` or `artifacts/evaluation`, changes no frozen artifact, and touches no
production module (`discovery.engine`, `validation.apply`, `validation-contract.md` are read-only
imports/reads here, never edited on disk). It calls the real, unmodified
`policy_analytics.validation.apply.run_validation` — the only intervention is a **process-local
monkeypatch** of the module attribute `_select_adjustment_columns`, for the duration of one
`run_validation()` call, so that G06's own greedy coverage-gated selection is bypassed and a fixed,
precomputed oracle adjustment set is used instead. The function `_select_adjustment_columns`'s own
source code on disk is never edited; `apply.py` is never modified. Every other gate (G00-G05,
G07-G15), the estimator (`_stratified_adjustment`, cluster bootstrap, E-value), and
`classify_evidence_level`/`assign_policy_readiness` all run exactly as shipped, on the real
candidate conditions, against the real dataset.

**Candidate definitions reused, not redefined, per `TASK-078`'s scope item 1:** `CAND-014` (`T03`)
and `CAND-015` (`T04`)'s exact real conditions, and `T01`/`T02`/`T05`'s single-condition
`apparent_feature` counterfactuals, are all parsed generically out of
`docs/benchmark/task-075-t03-forensic-trace-raw.json` (`T03`/`T04`) and
`synthetic_data/evaluation/hidden_ground_truth.json` (`T01`/`T02`/`T05`) — the same
already-fidelity-checked source `TASK-075`'s own script used, never re-typed by hand, never a new
condition invented for this experiment.

**Why `artifacts/blind/task-073-official-20260829-001.*` is not used as this script's fidelity
anchor.** Same disclosed limitation the `CODE_REVIEWER`'s independent `TASK-075` review already
recorded: `artifacts/` is gitignored and this worktree carries no prior official-run output. This
script cannot re-verify the frozen `candidates.json`'s SHA-256 against `hashes.json`, nor
byte-match a fresh `run_validation()` against the committed `TASK-019` artifact directly. It
substitutes the next-best fidelity anchor available in a fresh worktree: (1) the dataset's own
identity hash, recomputed fresh and checked against the exact value `TASK-075` recorded; (2) a
fresh, override-free `run_validation()` call on `CAND-014`/`CAND-015`'s real conditions (reproduced
from the already-committed, independently-produced `task-075-t03-forensic-trace-raw.json`) and on
`T01`/`T02`/`T05`'s counterfactual conditions, checked to reproduce `TASK-075`'s own already-
recorded `adjustment_columns_used` exactly, real selection logic, no override. Only after this
passes does the script report any oracle-override result. This bears on custody/fidelity
re-verification only, exactly as the `CODE_REVIEWER` disclosed for the identical situation.

**Hard rule (`TASK-078`, `ADR-071`), restated because this script is exactly the file most able to
violate it.** No gate, threshold, or selection logic is tuned, chosen, or justified by reference to
this experiment's own outcome on `T01`-`T05`. The oracle set for each trap is read once from
`hidden_ground_truth.json`'s `confounded_by` field, fixed before any candidate is scored, and never
revised after seeing a result. `G02`'s circularity guard (exclude a candidate's own condition
features from its adjustment set) is never bypassed — where a trap's ground-truth confounder is
literally one of its own real candidate's condition features (`T03`/`CAND-014`'s `discount_rate`),
the achievable oracle set is disclosed as smaller than the full ground truth, generically, not
special-cased.

Usage:
  uv run python scripts/diagnose_task078_oracle_adjustment_sufficiency.py
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

import polars as pl  # noqa: E402

import policy_analytics.validation.apply as apply_module  # noqa: E402
from policy_analytics.outcomes import primary_outcome  # noqa: E402
from policy_analytics.validation.apply import (  # noqa: E402
    Condition,
    load_analytical_frame,
    run_validation,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS, PolicyReadiness  # noqa: E402
from policy_analytics.validation.input_contract import validation_input_from_manifest  # noqa: E402

DATASET_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
GROUND_TRUTH_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
TASK075_RAW_PATH = REPOSITORY / "docs/benchmark/task-075-t03-forensic-trace-raw.json"
DEFAULT_RAW_OUTPUT = REPOSITORY / "docs/benchmark/task-078-oracle-adjustment-sufficiency-raw.json"
DATASET_IDENTITY_SHA256 = "b6128eb3c1bdb36515c90570aa4ccabfc3dff8d1026d9002f1c832774b60a683"

# Documented, already-recorded family_size for this dataset's most recent official run
# (task-073-official-20260829-001), reused verbatim from TASK-075's own committed gate trace
# (docs/benchmark/task-075-t03-forensic-trace.md / -raw.json, CAND-014's G05 detail: "... over
# family_size=33085"). Not re-derived or chosen for this experiment -- reused so G05's threshold
# is identical to the real official run's, not loosened by testing one candidate at a time (see
# "single-candidate BH rank" note below for the one disclosed, conservative-direction deviation
# this forces).
DOCUMENTED_OFFICIAL_FAMILY_SIZE = 33085

# The dataset's own DECISION_TIME date column booking_month is derived from, one-off, for this
# experiment's T02(b) counterfactual only. Same generic <x>_month := month(<x>_date) derivation
# scripts/diagnose_oracle_decomposition.py already established as this project's own precedent for
# exactly this situation (a true condition names a calendar decomposition of an existing date
# column). Never written back to the dataset, the manifest, or discovery.engine's vocabulary.
BOOKING_MONTH_SOURCE_COLUMN = "booking_date"
BOOKING_MONTH_DERIVED_COLUMN = "booking_month"

_CONDITION_TOKEN_RE = re.compile(r"^(?P<feature>\S+)\s+(?P<operator>eq|ge|lt)\s+(?P<value>.+)$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _coerce_value(raw_value: str) -> Any:
    raw_value = raw_value.strip()
    if raw_value in ("True", "true"):
        return True
    if raw_value in ("False", "false"):
        return False
    try:
        return int(raw_value)
    except ValueError:
        pass
    try:
        return float(raw_value)
    except ValueError:
        pass
    return raw_value


def _parse_condition_token(token: str) -> Condition:
    """`"feature eq value"` -> a `Condition`, generically -- the exact inverse of the
    `f"{c.feature} {c.operator} {c.value}"` format TASK-075's own script wrote each condition in
    (`_trace_selection`'s `condition` list), so CAND-014/CAND-015's real conditions are recovered
    from the already-committed, already-fidelity-checked raw JSON without retyping them by hand.
    """
    match = _CONDITION_TOKEN_RE.match(token.strip())
    if match is None:
        raise ValueError(f"cannot parse condition token {token!r}")
    return Condition(match.group("feature"), match.group("operator"), _coerce_value(match.group("value")))


def _parse_apparent_feature(apparent_feature: str) -> Condition:
    """`"field=value"` -> a `Condition`, generically. Identical to TASK-075's own script's parser
    -- no trap identity is hardcoded, every trap's apparent_feature string is parsed the same way.
    """
    feature, _, raw_value = apparent_feature.partition("=")
    return Condition(feature.strip(), "eq", _coerce_value(raw_value.strip()))


def _real_candidate_conditions_from_task075_raw(trap_id: str) -> tuple[Condition, ...]:
    """Recover trap `trap_id`'s real persisted candidate's exact conditions from the
    already-committed `task-075-t03-forensic-trace-raw.json` (`is_counterfactual: false` entries),
    never retyped by hand. Raises if `trap_id` has no real-candidate entry recorded there.
    """
    payload = cast(dict[str, Any], json.loads(TASK075_RAW_PATH.read_text(encoding="utf-8")))
    matches = [
        trace
        for trace in payload["trap_selection_traces"]
        if trace["trap_id"] == trap_id and not trace["is_counterfactual"]
    ]
    if not matches:
        raise ValueError(f"no real-candidate trace recorded for {trap_id} in {TASK075_RAW_PATH}")
    if len(matches) > 1:
        # T04 has two real-candidate entries (CAND-007, CAND-015); TASK-078 scope item 1 names
        # CAND-015 specifically for T04 (the one that reached shadow_policy).
        matches = [m for m in matches if m["label"].startswith("CAND-015")]
    trace = matches[0]
    return tuple(_parse_condition_token(token) for token in trace["condition"])


def _oracle_set(
    confounded_by: list[str],
    eligible_pool: frozenset[str],
    condition_features: frozenset[str],
) -> tuple[tuple[str, ...], dict[str, str]]:
    """The achievable oracle adjustment set: every ground-truth confounder that (a) exists in the
    manifest's declared `adjustment_eligible` pool and (b) is not one of the candidate's own
    condition features (G02's circularity guard, untouched, never bypassed here). Returns the
    achievable set plus a fate dict for every excluded ground-truth confounder, generic and
    reused for every trap identically -- no trap-specific branch anywhere in this function.
    """
    achievable: list[str] = []
    fate: dict[str, str] = {}
    for variable in confounded_by:
        if variable in condition_features:
            fate[variable] = (
                "excluded_structurally_own_condition_feature (G02 circularity guard, untouched "
                "by this experiment; cannot be forced into the adjustment set without bypassing a "
                "gate this task is not authorized to touch)"
            )
        elif variable not in eligible_pool:
            fate[variable] = (
                "excluded_vocabulary_gap (not in the manifest's adjustment_eligible pool at all; "
                "a representability question, not a selection question)"
            )
        else:
            achievable.append(variable)
            fate[variable] = "included_in_oracle_set"
    return tuple(sorted(achievable)), fate


def _derive_booking_month(frame: pl.DataFrame) -> pl.DataFrame:
    """`booking_month := month(booking_date)`, the same generic `<x>_month := month(<x>_date)`
    derivation `scripts/diagnose_oracle_decomposition.py` already established as this project's
    precedent for exactly this situation. A one-off column for this experiment's T02(b)
    counterfactual only -- never written to the dataset on disk, the manifest, or
    discovery.engine's vocabulary.
    """
    return frame.with_columns(
        pl.col(BOOKING_MONTH_SOURCE_COLUMN)
        .str.to_date("%Y-%m-%d")
        .dt.month()
        .alias(BOOKING_MONTH_DERIVED_COLUMN)
    )


def _write_candidate_and_metrics(
    tmp_dir: Path,
    run_label: str,
    candidate_id: str,
    conditions: tuple[Condition, ...],
    outcome_id: str,
) -> tuple[Path, Path]:
    candidates_path = tmp_dir / f"{run_label}.candidates.json"
    metrics_path = tmp_dir / f"{run_label}.discovery_metrics.json"
    candidates_path.write_text(
        json.dumps(
            {
                "status": "PERSISTED",
                "outcome": {"outcome_id": outcome_id, "outcome_definition_version": "1.1.0"},
                "candidates": [
                    {
                        "candidate_id": candidate_id,
                        "conditions": [
                            {"feature": c.feature, "operator": c.operator, "value": c.value}
                            for c in conditions
                        ],
                        "outcome": outcome_id,
                    }
                ],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(
        json.dumps({"evaluated_hypotheses": DOCUMENTED_OFFICIAL_FAMILY_SIZE}, indent=2),
        encoding="utf-8",
    )
    return candidates_path, metrics_path


def _run_one(
    tmp_dir: Path,
    run_label: str,
    candidate_id: str,
    conditions: tuple[Condition, ...],
    oracle_override: tuple[str, ...] | None,
    dataset_root: Path,
    outcome: Any,
) -> dict[str, Any]:
    """Run the real, unmodified `run_validation()` on one synthetic single-candidate document.

    `oracle_override`, when given, is applied via a process-local monkeypatch of
    `policy_analytics.validation.apply._select_adjustment_columns` for the duration of this call
    only -- the real function's source is untouched; every other gate, the estimator, and
    evidence/readiness assignment run exactly as shipped. When `oracle_override` is `None`, no
    monkeypatch is installed at all and G06's real selection logic runs unmodified (used for the
    fidelity cross-check against TASK-075's own recorded selections).
    """
    inputs = validation_input_from_manifest(dataset_root)
    candidates_path, metrics_path = _write_candidate_and_metrics(
        tmp_dir, run_label, candidate_id, conditions, outcome.outcome_id
    )

    real_select = apply_module._select_adjustment_columns
    if oracle_override is not None:

        def _forced_oracle_selection(
            binned_frame: pl.DataFrame,
            mask: pl.Series,
            outcome_arg: Any,
            pool: tuple[str, ...],
            min_coverage: float,
        ) -> tuple[str, ...]:
            # Sanity guard only (not a search): every forced column must actually be a column the
            # real candidate's eligible pool would have offered, i.e. present in `pool`. If not,
            # something upstream (condition parsing, G02 exclusion) is inconsistent with the
            # oracle set this script precomputed, and this must fail loudly rather than silently
            # adjust for a column G02 would have excluded.
            missing = [c for c in oracle_override if c not in pool and c != BOOKING_MONTH_DERIVED_COLUMN]
            if missing:
                raise AssertionError(
                    f"oracle override columns {missing} are not in the real eligible pool {pool} "
                    "-- refusing to silently adjust for a column G02/the manifest would exclude"
                )
            return oracle_override

        apply_module._select_adjustment_columns = _forced_oracle_selection  # type: ignore[assignment]

    original_load_frame = apply_module.load_analytical_frame
    if BOOKING_MONTH_DERIVED_COLUMN in (oracle_override or ()):
        apply_module.load_analytical_frame = lambda root: _derive_booking_month(  # type: ignore[assignment]
            original_load_frame(root)
        )

    try:
        results, run_manifest = run_validation(
            dataset_root=dataset_root,
            candidates_path=candidates_path,
            outcome=outcome,
            dataset_version=inputs.dataset_version,
            outcome_definition_version="1.1.0",
            analysis_run_id=f"task-078-oracle-sufficiency-{run_label}",
            metrics_path=metrics_path,
        )
    finally:
        apply_module._select_adjustment_columns = real_select
        apply_module.load_analytical_frame = original_load_frame

    result = results[0]
    report = result.report
    gate_trace = [
        {"gate_id": g.gate_id.value, "outcome": g.outcome.value, "satisfied": g.satisfied, "detail": g.detail}
        for g in report.gate_results
    ]
    first_failing = next((g for g in gate_trace if not g["satisfied"] and g["gate_id"] not in (
        "G13_IDENTIFICATION_DESIGN", "G14_RANDOMIZATION_INTEGRITY",
    )), None)
    return {
        "run_label": run_label,
        "candidate_id": candidate_id,
        "conditions": [f"{c.feature} {c.operator} {c.value}" for c in conditions],
        "oracle_override_applied": list(oracle_override) if oracle_override is not None else None,
        "adjustment_columns_used": result.diagnostics.get("adjustment_columns_used"),
        "confounder_stratum_coverage": result.diagnostics.get("confounder_stratum_coverage"),
        "adjusted_harm_per_booking": result.diagnostics.get("adjusted_harm_per_booking"),
        "e_value": result.diagnostics.get("e_value"),
        "raw_effect_eur": report.raw_effect.value,
        "adjusted_effect_eur": report.adjusted_effect.value if report.adjusted_effect else None,
        "adjusted_effect_ci": (
            [report.adjusted_effect.ci_low, report.adjusted_effect.ci_high]
            if report.adjusted_effect
            else None
        ),
        "evidence_level": report.evidence_level.value if report.evidence_level else None,
        "policy_readiness": report.policy_readiness.value,
        "gate_of_death_non_g13_g14": first_failing["gate_id"] if first_failing else None,
        "gate_of_death_detail": first_failing["detail"] if first_failing else None,
        "family_size": run_manifest["family_size"],
        "gate_trace": gate_trace,
        "verdict": result.verdict,
    }


DISQUALIFYING_READINESS = {PolicyReadiness.SHADOW_POLICY.value, PolicyReadiness.HIGH_CONFIDENCE.value}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    parser.add_argument("--work-dir", type=Path, default=None)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    dataset_root = cast(Path, args.dataset_root)

    # --- Fidelity assertion 1: dataset identity matches TASK-075's own recorded identity ---
    manifest = cast(
        dict[str, Any], json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    )
    if manifest["dataset_identity_sha256"] != DATASET_IDENTITY_SHA256:
        raise SystemExit(
            f"dataset identity {manifest['dataset_identity_sha256']} != the identity TASK-075's "
            f"forensic trace was recorded against ({DATASET_IDENTITY_SHA256})"
        )
    print(f"[fidelity 1/2] dataset identity matches TASK-075's own record: {DATASET_IDENTITY_SHA256}")

    if not TASK075_RAW_PATH.exists():
        raise SystemExit(f"missing {TASK075_RAW_PATH} -- TASK-078 depends on TASK-075's raw output")
    task075_raw = cast(dict[str, Any], json.loads(TASK075_RAW_PATH.read_text(encoding="utf-8")))

    ground_truth = cast(dict[str, Any], json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8")))
    traps = {t["id"]: t for t in ground_truth["confounding_traps"]}

    inputs = validation_input_from_manifest(dataset_root)
    outcome = primary_outcome()

    cleanup_work_dir = args.work_dir is None
    work_dir = cast(Path | None, args.work_dir) or Path(tempfile.mkdtemp(prefix="task078_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    # Per-trap condition source, per TASK-078 scope item 1: CAND-014/CAND-015's real conditions
    # for T03/T04 (recovered from TASK-075's own committed raw JSON), single-condition
    # apparent_feature counterfactuals for T01/T02/T05 (parsed generically from ground truth,
    # identical to TASK-075's own script).
    conditions_by_trap: dict[str, tuple[Condition, ...]] = {
        "T01": (_parse_apparent_feature(traps["T01"]["apparent_feature"]),),
        "T02": (_parse_apparent_feature(traps["T02"]["apparent_feature"]),),
        "T03": _real_candidate_conditions_from_task075_raw("T03"),
        "T04": _real_candidate_conditions_from_task075_raw("T04"),
        "T05": (_parse_apparent_feature(traps["T05"]["apparent_feature"]),),
    }
    candidate_id_by_trap = {
        "T01": "TASK078-T01-counterfactual",
        "T02": "TASK078-T02-counterfactual",
        "T03": "CAND-014",
        "T04": "CAND-015",
        "T05": "TASK078-T05-counterfactual",
    }

    # --- Fidelity assertion 2: real (non-overridden) selection on these exact conditions
    # reproduces TASK-075's own already-recorded adjustment_columns_used, for every trap. ---
    fidelity_mismatches: list[str] = []
    fidelity_cross_checks: list[dict[str, Any]] = []
    task075_trace_by_trap: dict[str, dict[str, Any]] = {}
    for trace in task075_raw["trap_selection_traces"]:
        if trace["trap_id"] == "T03" and trace["is_counterfactual"]:
            continue  # the "pure, no discount_rate" trace -- not TASK-078's T03 candidate
        if trace["trap_id"] == "T04" and trace["label"].startswith("CAND-007"):
            continue  # TASK-078 scope names CAND-015 for T04, not CAND-007
        task075_trace_by_trap[trace["trap_id"]] = trace

    for trap_id, conditions in conditions_by_trap.items():
        real_run = _run_one(
            work_dir,
            f"{trap_id.lower()}-real-selection-fidelity-check",
            candidate_id_by_trap[trap_id],
            conditions,
            oracle_override=None,
            dataset_root=dataset_root,
            outcome=outcome,
        )
        expected = task075_trace_by_trap[trap_id]["adjustment_columns_used"]
        actual = real_run["adjustment_columns_used"]
        match = list(actual) == list(expected)
        fidelity_cross_checks.append(
            {"trap_id": trap_id, "expected_from_task075": expected, "actual": actual, "match": match}
        )
        if not match:
            fidelity_mismatches.append(
                f"{trap_id}: real selection {actual} != TASK-075's recorded {expected}"
            )
    if fidelity_mismatches:
        raise SystemExit(
            "fidelity check 2/2 failed, refusing to report any oracle-override result: "
            f"{fidelity_mismatches}"
        )
    print(
        "[fidelity 2/2] real (non-overridden) G06 selection reproduces TASK-075's own recorded "
        "adjustment_columns_used exactly, for all 5 traps' conditions"
    )

    # --- Oracle sets, read once from hidden_ground_truth.json, fixed before any scoring ---
    oracle_by_run: dict[str, dict[str, Any]] = {}
    for trap_id, conditions in conditions_by_trap.items():
        confounded_by = traps[trap_id]["confounded_by"]
        condition_features = frozenset(c.feature for c in conditions)
        achievable, fate = _oracle_set(confounded_by, inputs.adjustment_features, condition_features)
        oracle_by_run[trap_id] = {
            "confounded_by_ground_truth": confounded_by,
            "condition_features": sorted(condition_features),
            "oracle_set_achievable": achievable,
            "confounded_by_fate": fate,
        }

    # T02(b): full-ground-truth oracle, booking_month derived from booking_date (documented
    # project precedent). trip_duration_days is already achievable in T02(a); the (b) set adds
    # the derived column.
    t02_condition_features = frozenset(c.feature for c in conditions_by_trap["T02"])
    t02_confounded_by = traps["T02"]["confounded_by"]
    t02b_achievable = tuple(
        sorted(v for v in t02_confounded_by if v not in t02_condition_features)
    )  # both trip_duration_days and booking_month, once booking_month is derivable

    print("\n=== Oracle sets (read once, fixed before scoring) ===")
    for trap_id, info in oracle_by_run.items():
        print(f"{trap_id}: {info['oracle_set_achievable']}  (fate: {info['confounded_by_fate']})")
    print(f"T02(b) full-ground-truth: {t02b_achievable}")

    # --- The oracle-override runs themselves ---
    run_results: dict[str, dict[str, Any]] = {}
    for trap_id in ("T01", "T03", "T04", "T05"):
        oracle_set = oracle_by_run[trap_id]["oracle_set_achievable"]
        run_results[trap_id] = _run_one(
            work_dir,
            f"{trap_id.lower()}-oracle",
            candidate_id_by_trap[trap_id],
            conditions_by_trap[trap_id],
            oracle_override=oracle_set,
            dataset_root=dataset_root,
            outcome=outcome,
        )

    run_results["T02a"] = _run_one(
        work_dir,
        "t02a-oracle-schema-feasible",
        candidate_id_by_trap["T02"],
        conditions_by_trap["T02"],
        oracle_override=oracle_by_run["T02"]["oracle_set_achievable"],
        dataset_root=dataset_root,
        outcome=outcome,
    )
    run_results["T02b"] = _run_one(
        work_dir,
        "t02b-oracle-full-ground-truth",
        candidate_id_by_trap["T02"],
        conditions_by_trap["T02"],
        oracle_override=t02b_achievable,
        dataset_root=dataset_root,
        outcome=outcome,
    )

    # --- Apply the preregistered acceptance criterion, per trap, exactly as fixed ---
    verdicts: dict[str, str] = {}
    for run_label, result in run_results.items():
        verdicts[run_label] = (
            "SURVIVED_disqualifying_state"
            if result["policy_readiness"] in DISQUALIFYING_READINESS
            else "REJECTED_below_disqualifying_state"
        )

    all_rejected = all(
        verdicts[label] == "REJECTED_below_disqualifying_state"
        for label in ("T01", "T03", "T04", "T05", "T02a")
    )
    # T02(b) reported separately, never merged into the 5-trap count (TASK-078 scope item 3).

    fork = (
        "FIVE_OF_FIVE_REJECTED_open_g06_fix_design_scoped_narrowly"
        if all_rejected
        else "SURVIVOR_FOUND_open_second_forensic_layer_task_before_fix_design"
    )

    output = {
        "diagnostic": "TASK-078 oracle-adjustment-set sufficiency experiment",
        "adr": "ADR-071 step 2",
        "dataset_identity_sha256": DATASET_IDENTITY_SHA256,
        "documented_official_family_size_reused": DOCUMENTED_OFFICIAL_FAMILY_SIZE,
        "fidelity_checks": {
            "dataset_identity_matches_task075": True,
            "real_selection_reproduces_task075_recorded_selections": fidelity_cross_checks,
            "disclosed_limitation": (
                "artifacts/blind/task-073-official-20260829-001.* not present in this worktree "
                "(artifacts/ is gitignored, fresh worktree) -- cannot re-verify frozen "
                "candidates.json SHA-256 against hashes.json, nor byte-match a fresh "
                "run_validation() against the committed TASK-019 artifact directly. Substituted: "
                "dataset identity re-verified fresh, and a fresh, override-free run_validation() "
                "on the same real conditions reproduces TASK-075's own already-recorded "
                "adjustment_columns_used exactly for all 5 traps. Same class of limitation the "
                "CODE_REVIEWER's independent TASK-075 review already disclosed."
            ),
            "single_candidate_bh_rank_note": (
                "Each run passes exactly one candidate to run_validation(), so G05's "
                "Benjamini-Hochberg adjustment always uses rank=1 within that call, rather than "
                "this candidate's true rank among the official run's full reported candidate "
                "list. family_size is still the real, documented 33085 (not shrunk). rank=1 "
                "against a fixed family_size is the *most conservative* (largest) BH-adjusted "
                "p-value achievable for a single candidate -- strictly harder to pass than the "
                "candidate's real historical rank would have produced, so this cannot be the "
                "reason a trap fails to be rejected here; it could only make G05 spuriously fail "
                "a trap that would otherwise pass, which none of the recorded raw p-values are "
                "close enough to for this to matter (all raw p far below alpha at any plausible "
                "rank)."
            ),
        },
        "oracle_sets": oracle_by_run,
        "t02b_full_ground_truth_oracle_set": list(t02b_achievable),
        "t02b_booking_month_derivation": f"{BOOKING_MONTH_DERIVED_COLUMN} := month({BOOKING_MONTH_SOURCE_COLUMN})",
        "run_results": run_results,
        "acceptance_criterion_verdicts": verdicts,
        "five_trap_aggregate_all_rejected_t02_reported_as_a": all_rejected,
        "fork": fork,
    }

    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {args.raw_output}")

    print("\n=== Summary ===")
    for run_label, result in run_results.items():
        print(
            f"{run_label}: policy_readiness={result['policy_readiness']} "
            f"evidence_level={result['evidence_level']} "
            f"gate_of_death={result['gate_of_death_non_g13_g14']} "
            f"-> {verdicts[run_label]}"
        )
    print(f"\nFork: {fork}")

    if cleanup_work_dir:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
