"""POST-HOC DIAGNOSTIC (`TASK-069` reprioritization item 1): validation-power autopsy.

Companion to `scripts/diagnose_oracle_decomposition.py` (research-plan item 7), which established
*that* every one of travel's seven scoreable ground-truth patterns' oracle branches caps at
`descriptive_observation` (six counterfactually, `P06` actually reaching `predictive_association`).
That script recorded only the *names* of the failing gates. This one answers the question item 1
actually asks: **for each pattern, which gate is binding, with the real computed value against the
real preregistered threshold** — so that "genuinely insufficient data at this `n`" and "the
validation test is statistically inefficient for this effect/sample shape" can be told apart with
numbers instead of adjectives.

Not part of the official discovery/blind/validation pipeline. It writes no artifact under
`artifacts/`, produces no official metric, changes no frozen artifact, and touches no production
module. It calls the real, unmodified `policy_analytics.validation.apply.run_validation` and the
real, unmodified `_robustness_battery`; only the *recording* is new.

**Why opening `synthetic_data/evaluation/hidden_ground_truth.json` is legitimate here.** Same
custody precedent `diagnose_oracle_decomposition.py` §0 records: travel's hidden ground truth has
been legitimately open since `TASK-028`'s first evaluation
(`docs/benchmark/task-029-benchmark-report-v1.md` §1), and the traced run was frozen and committed
via signed receipt before any evaluation opened it. This script re-verifies the frozen candidate
file's SHA-256 against its own `hashes.json` before reading anything.

**Binding constraint from `TASK-069`'s own hard rule, restated.** `TASK-069` forbids any new search
objective, scoring term, expansion policy, eligibility-gate redesign, or validation-gate change
being designed, scoped, or justified by reference to travel's specific pattern identities or
feature values; it permits a diagnostic to read those identities *to explain failures*. This script
is strictly diagnostic: it proposes no mechanism, changes no threshold, and writes nothing into
`policy_analytics.validation`. It contains **no hardcoded pattern id, feature name, threshold, or
rule** — every pattern's true condition set is parsed generically out of `hidden_ground_truth.json`
at runtime by `diagnose_oracle_decomposition.build_projection`, and every threshold it compares
against is read from `DEFAULT_THRESHOLDS`, never restated here.

**Fidelity is asserted, not assumed.** Before reporting anything the script requires:

1. the frozen candidate file's SHA-256 to match its `hashes.json` entry;
2. every re-derived oracle projection to equal, condition-for-condition, the one item 7 committed
   to `docs/benchmark/task-069-oracle-decomposition-raw.json`;
3. the counterfactual validation's evidence level and failed-gate set, per pattern, to equal item
   7's committed result exactly (same rules, same order, same family size — so the Benjamini-
   Hochberg family is identical and the numbers below explain *those* verdicts, not new ones);
4. the recorded per-check robustness decomposition to reproduce `_robustness_battery`'s own
   aggregate sign-agreement, magnitude-deviation, and check-count outputs exactly.

`P06` is handled differently and deliberately: its oracle projection *was* selected (committed
`CAND-007`), so its gate numbers are read from the frozen `TASK-019` report rather than recomputed
counterfactually. Its role here is the control — the one pattern that cleared the evidence gates,
against which the other six are compared.

Usage:
  uv run python scripts/diagnose_validation_power.py
  uv run python scripts/diagnose_validation_power.py --blind-root /path/to/checkout/artifacts/blind
"""

# pyright: reportPrivateUsage=false
# Reuses `validation.apply`'s and `diagnose_oracle_decomposition`'s own private functions verbatim
# rather than reimplementing their arithmetic — the same precedent
# `diagnose_oracle_decomposition.py`, `diagnose_candidate_pool_recall.py`, and
# `diagnose_g06_task065_b2b.py` already set.
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import polars as pl  # noqa: E402
from diagnose_oracle_decomposition import (  # noqa: E402
    BLIND_ROOT,
    DATASET_ROOT,
    DEFAULT_RUN_ID,
    DEFAULT_VALIDATION_PATH,
    GROUND_TRUTH_PATH,
    NON_SCOREABLE_PATTERNS,
    _render_rule,
    build_projection,
)
from policy_analytics.discovery.engine import (  # noqa: E402
    DISCOVERY_METHOD_VERSION,
    DiscoveryConfig,
    _atoms,
)
from policy_analytics.outcomes import (  # noqa: E402
    OUTCOME_BY_ID,
    OutcomeDefinition,
    outcome_definition_from_manifest,
    primary_outcome,
)
from policy_analytics.validation.apply import (  # noqa: E402
    PERTURBATION_QUANTILES,
    Condition,
    SplitStats,
    _robustness_battery,
    load_analytical_frame,
    minimum_detectable_effect,
    rule_expr,
    run_validation,
    split_stats,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS, GateId  # noqa: E402
from policy_analytics.validation.grading import benjamini_hochberg_adjusted  # noqa: E402
from policy_analytics.validation.input_contract import (  # noqa: E402
    ValidationInput,
    validation_input_from_manifest,
)

DEFAULT_ORACLE_RAW = REPOSITORY / "docs/benchmark/task-069-oracle-decomposition-raw.json"
DEFAULT_RAW_OUTPUT = REPOSITORY / "docs/benchmark/task-069-validation-power-autopsy-raw.json"

#: Gates `LEVEL_REQUIREMENTS[PREDICTIVE]` adds on top of `DESCRIPTIVE`'s. These, and only these,
#: are what can hold an otherwise-clean candidate at `descriptive_observation`; read from the
#: contract's own level table rather than restated, so it cannot drift from `contract.py`.
from policy_analytics.validation.contract import LEVEL_REQUIREMENTS  # noqa: E402
from policy_schemas.domain import EvidenceLevel  # noqa: E402

LEVEL_2_GATES: tuple[GateId, ...] = tuple(
    gate
    for gate in GateId
    if gate in LEVEL_REQUIREMENTS[EvidenceLevel.PREDICTIVE]
    and gate not in LEVEL_REQUIREMENTS[EvidenceLevel.DESCRIPTIVE]
)


# --------------------------------------------------------------------------------------------
# Per-check robustness decomposition (G12)
# --------------------------------------------------------------------------------------------


def _robustness_decomposition(
    dev_frame: pl.DataFrame,
    conditions: tuple[Condition, ...],
    dev_mask: pl.Series,
    outcome: OutcomeDefinition,
    dev: SplitStats,
    inputs: ValidationInput,
) -> tuple[list[dict[str, Any]], float, float, int]:
    """Mirror `validation.apply._robustness_battery` check for check, recording each one.

    Control flow is a line-for-line mirror of the real battery (same order, same perturbation
    quantiles, same winsorisation bounds, same alternative outcome); the only addition is that each
    check's own result is kept instead of being folded straight into two scalars. The caller
    asserts this reproduces `_robustness_battery`'s own three outputs before any of it is reported.
    """
    checks: list[dict[str, Any]] = []
    sign_agree = 0
    checks_run = 0
    magnitude_ratios: list[float] = []

    def _record(label: str, detail: dict[str, Any], stats: SplitStats | None) -> None:
        nonlocal sign_agree, checks_run
        checks_run += 1
        entry: dict[str, Any] = {"check": label, **detail}
        if stats is None or not dev.harm_per_booking:
            entry.update(
                {
                    "n_exposed": stats.n_exposed if stats else 0,
                    "harm_per_booking": stats.harm_per_booking if stats else None,
                    "sign_agrees": False,
                    "magnitude_ratio": None,
                    "note": "no estimate produced; counted as a run check that does not agree",
                }
            )
            checks.append(entry)
            return
        agrees = (stats.harm_per_booking > 0) == (dev.harm_per_booking > 0)
        if agrees:
            sign_agree += 1
        ratio = abs(stats.harm_per_booking / dev.harm_per_booking)
        magnitude_ratios.append(ratio)
        entry.update(
            {
                "n_exposed": stats.n_exposed,
                "harm_per_booking": round(stats.harm_per_booking, 4),
                "sign_agrees": agrees,
                "magnitude_ratio": round(ratio, 4),
                "magnitude_deviation": round(abs(ratio - 1.0), 4),
            }
        )
        checks.append(entry)

    if inputs.robustness_group_column is not None:
        group_column = inputs.robustness_group_column
        # `_robustness_battery` iterates `.unique().to_list()`, whose order polars does not
        # guarantee run-to-run (the `HANDOFF-047` failure mode). That is harmless there — its three
        # outputs are order-independent aggregates — but it would make *this* script's recorded
        # per-check list differ byte-for-byte between identical runs. Sorting only fixes the
        # recording order; the same set of refits runs, and the caller's assertion against
        # `_robustness_battery`'s own aggregates is what proves the two agree.
        for group_value in sorted(dev_frame[group_column].unique().to_list()):
            subset = dev_frame.filter(pl.col(group_column) != group_value)  # pyright: ignore[reportUnknownMemberType]
            submask = subset.select(rule_expr(conditions).alias("m"))["m"]
            _record(
                "leave_one_cluster_out",
                {"dropped_group": f"{group_column}={group_value}"},
                split_stats(subset, submask, outcome, "development"),
            )

    low, high = dev_frame[outcome.column].quantile(0.01), dev_frame[outcome.column].quantile(0.99)
    winsor_frame = dev_frame.with_columns(
        pl.col(outcome.column).clip(cast(float, low), cast(float, high))
    )
    _record(
        "winsorize_top_bottom_1pct",
        {"clip_bounds": [low, high]},
        split_stats(winsor_frame, dev_mask, outcome, "development"),
    )

    if inputs.alternative_outcome_id is not None:
        alt_outcome = OUTCOME_BY_ID.get(inputs.alternative_outcome_id)
        if alt_outcome is None:
            raise ValueError(
                f"no reviewed OutcomeDefinition for alternative outcome "
                f"{inputs.alternative_outcome_id!r}"
            )
        _record(
            "alternative_outcome",
            {"outcome_id": inputs.alternative_outcome_id},
            split_stats(dev_frame, dev_mask, alt_outcome, "development"),
        )

    for condition in conditions:
        if not isinstance(condition.value, int | float) or isinstance(condition.value, bool):
            continue
        column = dev_frame[condition.feature]
        # Where the candidate's own threshold sits in its column's development distribution. The
        # perturbation below replaces it with a *fixed* low quantile of the same column, so this
        # number is exactly how far the "one-bin perturbation" actually moves.
        below_share = cast(Any, (column < condition.value).mean())
        original_pct = 0.0 if below_share is None else float(cast(float, below_share))
        for quantile in PERTURBATION_QUANTILES:
            perturbed_value = column.quantile(quantile)
            if perturbed_value is None:
                continue
            perturbed = tuple(
                Condition(c.feature, c.operator, round(float(perturbed_value), 8))
                if c is condition
                else c
                for c in conditions
            )
            pmask = dev_frame.select(rule_expr(perturbed).alias("m"))["m"]
            _record(
                "numeric_threshold_perturbation",
                {
                    "condition": f"{condition.feature} {condition.operator} {condition.value}",
                    "threshold_percentile_in_development": round(original_pct, 4),
                    "perturbation_quantile": quantile,
                    "perturbed_value": round(float(perturbed_value), 8),
                    "threshold_percentile_shift": round(original_pct - quantile, 4),
                },
                split_stats(dev_frame, pmask, outcome, "development"),
            )

    sign_agreement = sign_agree / checks_run if checks_run else 0.0
    max_magnitude_deviation = max((abs(r - 1.0) for r in magnitude_ratios), default=1.0)
    return checks, sign_agreement, max_magnitude_deviation, checks_run


# --------------------------------------------------------------------------------------------
# Power arithmetic (diagnostic only: inverts the gate's own MDE formula, changes nothing)
# --------------------------------------------------------------------------------------------


def _required_exposed_n_for_power(
    harm_per_booking: float, comparison_n: int, pooled_sd: float
) -> float | None:
    """Exposed-group size at which G03's own `minimum_detectable_effect` would equal the observed
    |harm|, holding the comparison group and pooled sd fixed. Pure inversion of the gate's existing
    formula — it proposes no threshold change and is reported only to size the gap between "this
    sample is too small" and "this sample is fine but the test is wasteful".
    """
    from policy_analytics.validation.apply import Z_95, Z_POWER_80

    target = abs(harm_per_booking)
    if target <= 0 or pooled_sd <= 0 or comparison_n <= 0:
        return None
    # (Z95 + Z80) * sd * sqrt(1/n_e + 1/n_c) = target  ->  1/n_e = (target/((Z95+Z80)*sd))^2 - 1/n_c
    inverse = (target / ((Z_95 + Z_POWER_80) * pooled_sd)) ** 2 - 1.0 / comparison_n
    if inverse <= 0:
        return math.inf  # unreachable at any exposed n against this comparison group
    return 1.0 / inverse


# --------------------------------------------------------------------------------------------


def _true_rule_power_reference(
    reference: dict[str, Any],
    development_rows: int,
    development_outcome_sd: float,
    family_size: int,
) -> dict[str, Any] | None:
    """Apply G03's and G05's own formulas to the **exact true rule**'s development exposure, as
    item 7 already committed it (`true_rule_engine_reference`), using an *unclustered* standard
    error.

    Deliberately optimistic, and reported as a bound rather than an estimate: clustering the
    bootstrap on `customer_id` can only widen the interval relative to an i.i.d. standard error, so
    the p-value below is a lower bound on what the real contract would compute. Its only use is
    one-directional — when even this optimistic bound cannot clear Benjamini-Hochberg's most
    lenient requirement (`fdr_alpha / family_size`, the rank-1 case), "no estimator could have
    promoted this rule at this sample size" is settled, not argued. When it does clear, nothing is
    concluded from that alone.

    `development_outcome_sd` is the development split's own outcome standard deviation, used in
    place of each rule's own pooled sd; across every pattern's oracle branch that pooled sd sits in
    a ~1% band, so this substitution is disclosed as immaterial rather than assumed away.
    """
    if not reference.get("available"):
        return None
    if reference.get("development_n_exposed") is None or (
        reference.get("development_harm_per_booking") is None
    ):
        return None
    n_exposed = int(cast(int, reference["development_n_exposed"]))
    harm = float(cast(float, reference["development_harm_per_booking"]))
    n_comparison = development_rows - n_exposed
    if n_exposed <= 0 or n_comparison <= 0:
        return None
    from policy_analytics.validation.grading import normal_approx_two_sided_p

    mde = minimum_detectable_effect(n_exposed, n_comparison, development_outcome_sd)
    se = development_outcome_sd * math.sqrt(1.0 / n_exposed + 1.0 / n_comparison)
    optimistic_p = normal_approx_two_sided_p(harm, se)
    most_lenient = DEFAULT_THRESHOLDS.fdr_alpha / family_size
    return {
        "note": (
            "OPTIMISTIC BOUND on the exact true rule, unclustered SE; clustering can only widen "
            "it. Conclusive only when it fails."
        ),
        "development_n_exposed": n_exposed,
        "development_harm_per_booking": round(harm, 4),
        "development_outcome_sd": round(development_outcome_sd, 4),
        "minimum_detectable_effect_eur": round(mde, 4),
        "g03_would_pass_on_power": bool(abs(harm) > mde),
        "g03_would_pass_on_floors": n_exposed >= DEFAULT_THRESHOLDS.min_exposed_records,
        "optimistic_unclustered_p": optimistic_p,
        "bh_most_lenient_raw_p_required": most_lenient,
        "conclusively_below_bh_at_any_rank": bool(optimistic_p > most_lenient),
    }


def _gate_map(gate_results: Sequence[Any]) -> dict[str, dict[str, str]]:
    """Normalise either shape a gate result arrives in — a live `GateResult` from
    `run_validation`, or the already-serialised dict a frozen `TASK-019` report holds — into one
    `{gate_id: {outcome, detail}}` map. Nothing is recomputed; only the container differs.
    """
    out: dict[str, dict[str, str]] = {}
    for gate in gate_results:
        if isinstance(gate, dict):
            raw = cast(dict[str, Any], gate)
            gate_id, outcome, detail = raw["gate_id"], raw["outcome"], raw["detail"]
        else:
            gate_id, outcome, detail = gate.gate_id.value, gate.outcome.value, gate.detail
        out[str(gate_id)] = {"outcome": str(outcome), "detail": str(detail)}
    return out


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-id", type=str, default=DEFAULT_RUN_ID)
    parser.add_argument("--blind-root", type=Path, default=BLIND_ROOT)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--validation-report", type=Path, default=DEFAULT_VALIDATION_PATH)
    parser.add_argument("--oracle-raw", type=Path, default=DEFAULT_ORACLE_RAW)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    blind_root = cast(Path, args.blind_root)
    run_id = cast(str, args.run_id)
    dataset_root = cast(Path, args.dataset_root)

    candidates_path = blind_root / f"{run_id}.candidates.json"
    metrics_path = blind_root / f"{run_id}.discovery_metrics.json"
    hashes_path = blind_root / f"{run_id}.hashes.json"
    for path in (candidates_path, metrics_path, hashes_path):
        if not path.exists():
            raise SystemExit(
                f"missing frozen artifact {path}; `artifacts/` is gitignored and per-checkout — "
                "point --blind-root at a checkout that holds this run's frozen outputs"
            )
    hashes = cast(dict[str, str], json.loads(hashes_path.read_text(encoding="utf-8")))
    actual = hashlib.sha256(candidates_path.read_bytes()).hexdigest()
    if actual != hashes.get("candidates.json"):
        raise SystemExit(
            f"candidate file SHA-256 {actual} does not match the frozen hashes.json entry "
            f"{hashes.get('candidates.json')} — refusing to explain a mutated run"
        )

    run_metrics = cast(dict[str, Any], json.loads(metrics_path.read_text(encoding="utf-8")))
    manifest = cast(
        dict[str, Any], json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    )
    if run_metrics["dataset_identity_sha256"] != manifest["dataset_identity_sha256"]:
        raise SystemExit("dataset identity drifted since the committed run; results untrustworthy")

    oracle_raw = cast(
        dict[str, Any], json.loads(cast(Path, args.oracle_raw).read_text(encoding="utf-8"))
    )
    oracle_by_pattern = {
        str(entry["pattern_id"]): entry
        for entry in cast(list[dict[str, Any]], oracle_raw["patterns"])
    }
    oracle_counterfactual = cast(
        dict[str, Any], oracle_raw["stage_6_counterfactual_validation"]["by_pattern"]
    )

    config = DiscoveryConfig(
        seed=int(run_metrics["random_seed"]),
        max_feature_identity_fraction=float(run_metrics.get("max_feature_identity_fraction", 1.0)),
    )
    timing_meta = cast(dict[str, dict[str, Any]], manifest["feature_timing"])
    timing = {name: str(meta["classification"]) for name, meta in timing_meta.items()}
    excluded_dates = {"booking_date", "travel_date"}
    frame = load_analytical_frame(dataset_root)
    feature_columns = tuple(
        name
        for name in frame.columns
        if timing.get(name) == "DECISION_TIME" and name not in excluded_dates
    )
    outcome = primary_outcome()
    development = frame.filter(pl.col("split_label") == "development")  # pyright: ignore[reportUnknownMemberType]
    atoms = _atoms(development, feature_columns, config)
    frame_columns = frozenset(frame.columns)

    print(f"Autopsy of committed run {run_id} (engine {DISCOVERY_METHOD_VERSION})")
    print(f"  atoms={len(atoms)}  feature vocabulary={len(feature_columns)} DECISION_TIME columns")

    ground_truth = cast(dict[str, Any], json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8")))
    patterns = cast(list[dict[str, Any]], ground_truth["patterns"])

    # ---- Re-derive every oracle projection and assert it equals item 7's committed one ----
    canonical: dict[str, tuple[Condition, ...]] = {}
    for pattern in patterns:
        pattern_id = str(pattern["id"])
        projection = build_projection(
            pattern_id,
            str(pattern["rule"]),
            atoms,
            feature_columns,
            frame_columns,
            timing,
            development,
            config,
        )
        if projection.over_depth or not projection.atoms:
            recorded = oracle_by_pattern[pattern_id]["canonical_representable_rule"]
            if recorded is not None:
                raise SystemExit(
                    f"{pattern_id}: item 7 recorded a canonical rule this re-derivation cannot "
                    "reproduce; refusing to report"
                )
            continue
        rendered = _render_rule(projection.atoms)
        if rendered != oracle_by_pattern[pattern_id]["canonical_representable_rule"]:
            raise SystemExit(
                f"{pattern_id}: re-derived oracle projection {rendered!r} differs from item 7's "
                f"committed {oracle_by_pattern[pattern_id]['canonical_representable_rule']!r} — "
                "refusing to report numbers for a different rule"
            )
        canonical[pattern_id] = tuple(
            Condition(c.feature, cast(Any, c.operator), c.value) for c in projection.atoms
        )
    print(f"  FIDELITY OK: {len(canonical)} oracle projections reproduce item 7 exactly")

    # ---- Which oracle branches were actually selected by the committed run ----
    committed = cast(dict[str, Any], json.loads(candidates_path.read_text(encoding="utf-8")))
    committed_rules: dict[str, tuple[tuple[str, str, Any], ...]] = {
        str(candidate["candidate_id"]): tuple(
            sorted(
                (str(c["feature"]), str(c["operator"]), c["value"])
                for c in cast(list[dict[str, Any]], candidate["conditions"])
            )
        )
        for candidate in cast(list[dict[str, Any]], committed["candidates"])
    }
    candidate_by_rule = {rule: cid for cid, rule in committed_rules.items()}

    def _key(rule: tuple[Condition, ...]) -> tuple[tuple[str, str, Any], ...]:
        return tuple(sorted((c.feature, str(c.operator), c.value) for c in rule))

    selected_pattern_candidate: dict[str, str] = {}
    counterfactual_order: list[str] = []
    for pattern in patterns:
        pattern_id = str(pattern["id"])
        rule = canonical.get(pattern_id)
        if rule is None:
            continue
        candidate_id = candidate_by_rule.get(_key(rule))
        if candidate_id is not None:
            selected_pattern_candidate[pattern_id] = candidate_id
        else:
            counterfactual_order.append(pattern_id)

    # ---- Counterfactual validation, same rule set / order / family as item 7 ----
    if sorted(counterfactual_order) != sorted(oracle_counterfactual):
        raise SystemExit(
            f"counterfactual rule set {sorted(counterfactual_order)} differs from item 7's "
            f"{sorted(oracle_counterfactual)} — refusing to report a different BH family"
        )
    document_candidates: list[dict[str, Any]] = []
    for index, pattern_id in enumerate(counterfactual_order, start=1):
        rule = canonical[pattern_id]
        document_candidates.append(
            {
                "candidate_id": f"ORACLE-{index:03d}",
                "conditions": [
                    {"feature": c.feature, "operator": c.operator, "value": c.value} for c in rule
                ],
                "outcome": outcome.outcome_id,
                "discovery_method": DISCOVERY_METHOD_VERSION,
                "description": (
                    f"POST-HOC DIAGNOSTIC oracle projection: {_render_rule(cast(Any, rule))}"
                ),
                "warnings": ["POST-HOC DIAGNOSTIC; never a discovered or selected candidate."],
            }
        )
    document = {
        "schema_version": "1.1.0",
        "run_id": "post-hoc-diagnostic-validation-power-autopsy",
        "status": "PERSISTED",
        "candidates": document_candidates,
    }
    validation_outcome, outcome_version = outcome_definition_from_manifest(manifest, dataset_root)
    print(f"  running the real contract counterfactually on {len(document_candidates)} rules ...")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "candidates.json"
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        validations, summary = run_validation(
            dataset_root=dataset_root,
            candidates_path=path,
            outcome=validation_outcome,
            dataset_version=str(manifest["dataset_version"]),
            outcome_definition_version=outcome_version,
            analysis_run_id="post-hoc-diagnostic-validation-power-autopsy",
            metrics_path=metrics_path,
        )
    family_size = int(summary["family_size"])

    counterfactual_by_pattern: dict[str, Any] = {}
    raw_p_by_pattern: dict[str, float] = {}
    for pattern_id, validation in zip(counterfactual_order, validations, strict=True):
        report = validation.report
        gates = _gate_map(report.gate_results)
        failed = sorted(gate for gate, info in gates.items() if info["outcome"] == "fail")
        recorded = cast(dict[str, Any], oracle_counterfactual[pattern_id])
        if str(report.evidence_level) != str(recorded["evidence_level"]) or failed != sorted(
            cast(list[str], recorded["failed_gates"])
        ):
            raise SystemExit(
                f"{pattern_id}: counterfactual verdict does not reproduce item 7's committed "
                f"result ({report.evidence_level} / {failed} vs {recorded['evidence_level']} / "
                f"{recorded['failed_gates']}) — refusing to report"
            )
        counterfactual_by_pattern[pattern_id] = {
            "source": "COUNTERFACTUAL (never selected by the committed run)",
            "rule": report.pattern_definition,
            "verdict": validation.verdict,
            "evidence_level": str(report.evidence_level),
            "policy_readiness": str(report.policy_readiness),
            "exposed_records_development": report.exposed_records,
            "comparison_records_development": report.comparison_records,
            "raw_effect": {
                "value": report.raw_effect.value,
                "ci_low": report.raw_effect.ci_low,
                "ci_high": report.raw_effect.ci_high,
            },
            "adjusted_p_value": report.adjusted_p_value,
            "family_size": report.family_size,
            "gates": gates,
            "diagnostics": validation.diagnostics,
        }
        raw_p_by_pattern[pattern_id] = float(
            cast(float, validation.diagnostics["p_value_normal_approx_bootstrap_se"])
        )
    print("  FIDELITY OK: counterfactual verdicts reproduce item 7's committed result exactly")

    # ---- P06-style actual results, read from the frozen official TASK-019 report ----
    frozen_validation = cast(
        dict[str, Any], json.loads(cast(Path, args.validation_report).read_text(encoding="utf-8"))
    )
    frozen_by_candidate = {
        str(entry["candidate_id"]): entry
        for entry in cast(list[dict[str, Any]], frozen_validation["candidates"])
    }
    actual_by_pattern: dict[str, Any] = {}
    for pattern_id, candidate_id in selected_pattern_candidate.items():
        entry = frozen_by_candidate[candidate_id]
        report = cast(dict[str, Any], entry["validation_report"])
        actual_by_pattern[pattern_id] = {
            "source": f"ACTUAL — frozen TASK-019 report, candidate {candidate_id}",
            "candidate_id": candidate_id,
            "rule": report["pattern_definition"],
            "evidence_level": report["evidence_level"],
            "policy_readiness": report["policy_readiness"],
            "exposed_records_development": report["exposed_records"],
            "comparison_records_development": report["comparison_records"],
            "raw_effect": report["raw_effect"],
            "adjusted_p_value": report["adjusted_p_value"],
            "family_size": report["family_size"],
            "gates": _gate_map(cast(list[Any], report["gate_results"])),
            "diagnostics": entry["diagnostics"],
        }

    # ---- BH arithmetic, made explicit for every pattern in the counterfactual family ----
    ordered = sorted(raw_p_by_pattern.items(), key=lambda item: item[1])
    bh_rank = {pattern_id: index for index, (pattern_id, _) in enumerate(ordered, start=1)}
    adjusted_check = benjamini_hochberg_adjusted(
        [raw_p_by_pattern[pid] for pid in counterfactual_order], family_size=family_size
    )
    for pattern_id, adjusted in zip(counterfactual_order, adjusted_check, strict=True):
        entry = counterfactual_by_pattern[pattern_id]
        rank = bh_rank[pattern_id]
        entry["g05_arithmetic"] = {
            "raw_p_normal_approx": raw_p_by_pattern[pattern_id],
            "rank_within_counterfactual_family": rank,
            "family_size": family_size,
            "bh_raw_p_required_at_this_rank": DEFAULT_THRESHOLDS.fdr_alpha * rank / family_size,
            "bh_adjusted_p": adjusted,
            "fdr_alpha": DEFAULT_THRESHOLDS.fdr_alpha,
            "passes": adjusted <= DEFAULT_THRESHOLDS.fdr_alpha,
            "shortfall_factor": (
                raw_p_by_pattern[pattern_id] / (DEFAULT_THRESHOLDS.fdr_alpha * rank / family_size)
            ),
        }
        if abs(adjusted - float(cast(float, entry["adjusted_p_value"]))) > 1e-12:
            raise SystemExit(f"{pattern_id}: recomputed BH-adjusted p disagrees with the report")

    # ---- G12 per-check decomposition and G03 power inversion, for every scoreable pattern ----
    inputs = validation_input_from_manifest(dataset_root)
    dev_frame = frame.filter(frame["split_label"] == "development")  # pyright: ignore[reportUnknownMemberType]
    dev_outcome_values = [
        float(value)
        for value in dev_frame[validation_outcome.column].to_list()
        if value is not None
    ]
    dev_outcome_mean = sum(dev_outcome_values) / len(dev_outcome_values)
    dev_outcome_sd = math.sqrt(
        sum((value - dev_outcome_mean) ** 2 for value in dev_outcome_values)
        / len(dev_outcome_values)
    )
    per_pattern: list[dict[str, Any]] = []
    for pattern in patterns:
        pattern_id = str(pattern["id"])
        rule = canonical.get(pattern_id)
        if rule is None:
            continue
        graded = counterfactual_by_pattern.get(pattern_id) or actual_by_pattern.get(pattern_id)
        if graded is None:
            continue
        full_mask = frame.select(rule_expr(rule).alias("m"))["m"]
        dev_mask = full_mask.filter(frame["split_label"] == "development")
        dev = split_stats(dev_frame, dev_mask, validation_outcome, "development")
        if dev is None:
            continue
        checks, sign_agreement, max_deviation, checks_run = _robustness_decomposition(
            dev_frame, rule, dev_mask, validation_outcome, dev, inputs
        )
        battery = _robustness_battery(dev_frame, rule, dev_mask, validation_outcome, dev, inputs)
        if (
            abs(battery[0] - sign_agreement) > 1e-12
            or abs(battery[1] - max_deviation) > 1e-12
            or battery[2] != checks_run
        ):
            raise SystemExit(
                f"{pattern_id}: recorded robustness decomposition does not reproduce "
                f"_robustness_battery ({battery} vs {(sign_agreement, max_deviation, checks_run)})"
            )
        worst = max(
            (c for c in checks if c.get("magnitude_deviation") is not None),
            key=lambda c: cast(float, c["magnitude_deviation"]),
            default=None,
        )
        mde = minimum_detectable_effect(dev.n_exposed, dev.n_comparison, dev.pooled_sd)
        required_n = _required_exposed_n_for_power(
            dev.harm_per_booking, dev.n_comparison, dev.pooled_sd
        )
        blocking = [
            gate.value
            for gate in LEVEL_2_GATES
            if cast(dict[str, Any], graded["gates"])[gate.value]["outcome"] not in ("pass", "warn")
        ]
        per_pattern.append(
            {
                "pattern_id": pattern_id,
                "name": str(pattern["name"]),
                "scoreable": pattern_id not in NON_SCOREABLE_PATTERNS,
                "true_rule": str(pattern["rule"]),
                "true_rule_affected_n": len(cast(list[str], pattern["affected_booking_ids"])),
                "oracle_rule": _render_rule(cast(Any, rule)),
                "graded": graded,
                "level_2_blocking_gates": blocking,
                "first_level_2_blocking_gate": blocking[0] if blocking else None,
                "development_sample": {
                    "n_exposed": dev.n_exposed,
                    "n_comparison": dev.n_comparison,
                    "harm_per_booking": round(dev.harm_per_booking, 4),
                    "pooled_sd": round(dev.pooled_sd, 4),
                    "min_exposed_records_threshold": DEFAULT_THRESHOLDS.min_exposed_records,
                },
                "g03_power": {
                    "minimum_detectable_effect_eur": round(mde, 4),
                    "observed_harm_eur": round(abs(dev.harm_per_booking), 4),
                    "mde_over_observed_harm": (
                        round(mde / abs(dev.harm_per_booking), 4) if dev.harm_per_booking else None
                    ),
                    "required_exposed_n_for_80pct_power": (
                        None
                        if required_n is None
                        else ("unreachable" if math.isinf(required_n) else round(required_n, 1))
                    ),
                },
                "true_rule_power_reference": _true_rule_power_reference(
                    cast(
                        dict[str, Any],
                        oracle_by_pattern[pattern_id]["true_rule_engine_reference"],
                    ),
                    dev_frame.height,
                    dev_outcome_sd,
                    family_size,
                ),
                "g12_robustness": {
                    "sign_agreement": round(sign_agreement, 4),
                    "sign_agreement_floor": DEFAULT_THRESHOLDS.min_robustness_sign_agreement,
                    "max_magnitude_deviation": round(max_deviation, 4),
                    "max_magnitude_deviation_ceiling": (
                        DEFAULT_THRESHOLDS.max_robustness_magnitude_deviation
                    ),
                    "checks_run": checks_run,
                    "binding_check": worst,
                    "checks": checks,
                },
            }
        )

    payload: dict[str, Any] = {
        "diagnostic": "POST_HOC_DIAGNOSTIC",
        "task": "TASK-069 reprioritization item 1 (validation power autopsy)",
        "disclosure": (
            "Not an official TASK-015/TASK-019/TASK-028 run. Produces no official metric, changes "
            "no frozen artifact, proposes no mechanism, and changes no gate or threshold. Six "
            "patterns' numbers are counterfactual validations of rules that were never selected; "
            "one pattern's are read from the frozen official TASK-019 report."
        ),
        "traced_run_id": run_id,
        "traced_candidates_sha256": actual,
        "dataset_identity_sha256": manifest["dataset_identity_sha256"],
        "validation_contract_version": DEFAULT_THRESHOLDS.version,
        "counterfactual_family_size": family_size,
        "counterfactual_family_size_source": str(metrics_path.name),
        "level_2_gates": [gate.value for gate in LEVEL_2_GATES],
        "patterns": per_pattern,
    }
    output = cast(Path, args.raw_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nRaw output written to {output}")

    print("\n=== Level-2 blocking gates per pattern ===")
    for entry in per_pattern:
        if not entry["scoreable"]:
            continue
        blocking = cast(list[str], entry["level_2_blocking_gates"])
        print(
            f"  {entry['pattern_id']}: "
            f"{', '.join(blocking) if blocking else 'none — reaches predictive_association'}"
        )
    print("\n=== G12 robustness, the gate every scoreable pattern is measured against ===")
    for entry in per_pattern:
        if not entry["scoreable"]:
            continue
        g12 = cast(dict[str, Any], entry["g12_robustness"])
        binding = cast(dict[str, Any] | None, g12["binding_check"])
        print(
            f"  {entry['pattern_id']}: sign {g12['sign_agreement']:.0%} "
            f"(floor {g12['sign_agreement_floor']:.0%}), max deviation "
            f"{g12['max_magnitude_deviation']:.0%} "
            f"(ceiling {g12['max_magnitude_deviation_ceiling']:.0%}) over "
            f"{g12['checks_run']} checks"
        )
        if binding is not None:
            print(f"      binding check: {binding}")


if __name__ == "__main__":
    main()
