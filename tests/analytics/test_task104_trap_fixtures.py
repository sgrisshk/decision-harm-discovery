"""`TASK-104`: controlled-fixture demonstration of `T01`/`T02`/`T05` against the real gates.

`D2` Part B of the frozen `TASK-102` bar needs each catalogued confounding trap shown to be
*capped* (below `SHADOW_POLICY`, with a stated confounding caveat), not merely absent from official
runs. `T01`/`T02`/`T05` never appear as candidates, so this file builds, per trap, a controlled
dataset with that trap's catalogued structure and runs a candidate carrying the trap's
`apparent_feature` through the REAL, unmodified `policy_analytics.validation.apply.run_validation`
(all of G00-G16, `assign_policy_readiness`). Nothing here re-implements a gate.

**Fixture construction (test-side only; no engine/gate/contract source is edited).** The delivered
`travel-bookings-analytical-v1.1.0` dataset is copied to a temp directory (real schema, real
manifest roles, real split labels, real cardinalities). Two things are rewritten, then the copied
manifest's partition hashes are refreshed so `validation_input_from_manifest` accepts it:

1. the trap's `apparent_feature` column `X` (`manager`/`supplier`/`manual_exception`): membership
   is drawn (seeded, deterministic) with probability increasing in a confounder score `s`;
2. `contribution_margin_eur` (the primary outcome): `margin - A * s`, so `X` has *zero direct
   effect* (`direct_effect: 0` in the trap catalogue) and its entire raw association with harm
   flows through the trap's `confounded_by` columns. `A` is calibrated so the raw exposed-vs-rest
   harm is `TARGET_RAW_HARM_EUR` -- strong enough to clear G03/G04/G05/G15 on its own, so a
   surviving cap can only come from a confounding-type mechanism.

The real delivered data cannot serve as the fixture: `X` is essentially uncorrelated with its
catalogued confounders there (measured, see the results doc), so a real-data single-atom trap
candidate is stopped by G03/G04/G05 for having no effect at all, which says nothing about
confounding safety.

**What "capped" means here** (matches `decision-gate.md`'s 2026-08-30 entry for `T03`/`T04`):
`policy_readiness` is below `SHADOW_POLICY` (`NOT_READY`/`EXPERIMENT_ONLY`), the evidence level is
at most `predictive_association`, and the report's `warnings` carry the failing confounding-type
gate's own caveat text (`G06_CONFOUNDING`, `G11_SEASONALITY`, or `G16`).

**Adversarial regressions** disable the protection *inside the test only* (`monkeypatch` on the
`apply` module attributes) and re-run the same fixture through the same entry point.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import shutil
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from policy_analytics.outcomes import primary_outcome
from policy_analytics.validation import apply as apply_module
from policy_analytics.validation.apply import CandidateValidation, run_validation
from policy_analytics.validation.contract import (
    LEVEL_ORDER,
    GateId,
    PolicyReadiness,
)
from policy_schemas.domain import EvidenceLevel

pytestmark = pytest.mark.analytics

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAVEL_DATASET = REPO_ROOT / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
TASK075_RAW = REPO_ROOT / "docs/benchmark/task-075-t03-forensic-trace-raw.json"
DATASET_VERSION = "travel-bookings-analytical-v1.1.0"
OUTCOME_VERSION = "1.1.0"
FAMILY_SIZE = 33_085  # the real official-run family size, as in test_g16_regression.py

#: Calibrated raw exposed-vs-comparison harm (EUR/booking) on the development split.
TARGET_RAW_HARM_EUR = 400.0
BASE_MARGIN_EUR = 400.0
NOISE_SD_EUR = 250.0
GROSS_OVER_MARGIN_EUR = 120.0

#: Fixed indicator definitions for each catalogued confounder (`hidden_ground_truth`'s
#: `confounded_by` names). Arbitrary but fixed and documented; each maps a row to {0, 1}.
HIGH_DESTINATIONS = frozenset({"Tokyo", "Reykjavik"})
#: Months spanning BOTH the validation (Jan-Jun 2025) and holdout (Jul-Dec 2025) splits, so a
#: month-driven effect is present in all three temporal splits and G10 does not confound the test.
HIGH_MONTHS = frozenset({4, 5, 6, 10, 11, 12})

TRAP_SPEC: dict[str, dict[str, Any]] = {
    "T01": {
        "x_column": "manager",
        "x_value": "Manager 2",
        "x_other": "Manager 1",
        "confounders": ("destination", "booking_lead_days", "party_size", "trip_duration_days"),
    },
    "T02": {
        "x_column": "supplier",
        "x_value": "Atlas",
        "x_other": "BlueWing",
        "confounders": ("trip_duration_days", "booking_month"),
    },
    "T05": {
        "x_column": "manual_exception",
        "x_value": True,
        "x_other": False,
        "confounders": ("destination", "party_size", "trip_duration_days", "booking_lead_days"),
    },
}


# ------------------------------------------------------------------------------------------
# Fixture construction (test-side only)
# ------------------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _indicator(frame: pl.DataFrame, confounder: str) -> list[int]:
    """0/1 per row for one catalogued confounder (fixed, documented definitions)."""
    if confounder == "destination":
        return [int(v in HIGH_DESTINATIONS) for v in frame["destination"].to_list()]
    if confounder == "booking_month":
        months = frame["booking_date"].str.slice(5, 2).cast(pl.Int64).to_list()
        return [int(m in HIGH_MONTHS) for m in months]
    values = frame[confounder].to_list()
    # Threshold = the gate's own second quartile breakpoint convention (sorted[n // 2]), so the
    # 0/1 boundary coincides with a G06 quartile-bin edge and a confounder G06 does retain is
    # genuinely adjustable (rather than split inside a bin by an arbitrary cut).
    threshold = sorted(values)[len(values) // 2]
    return [int(v >= threshold) for v in values]


def _trap_conditions(trap_id: str) -> list[dict[str, Any]]:
    """The trap's `apparent_feature` condition, parsed from the committed `TASK-075` raw JSON."""
    payload = json.loads(TASK075_RAW.read_text(encoding="utf-8"))
    trace = next(
        t
        for t in payload["trap_selection_traces"]
        if t["trap_id"] == trap_id and t["is_counterfactual"] is True
    )
    (token,) = trace["condition"]
    feature, operator, value = token.split(" ", 2)
    coerced: object = {"True": True, "False": False}.get(value, value)
    return [{"feature": feature, "operator": operator, "value": coerced}]


def build_fixture(
    dest: Path,
    trap_id: str,
    weights: dict[str, float],
    *,
    seed: int,
    target_raw_harm: float = TARGET_RAW_HARM_EUR,
    validation_roles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Copy the delivered dataset to `dest` and rewrite `X` and the primary outcome.

    `weights` maps each catalogued confounder to its share of the confounding (normalised to
    sum 1). Returns fixture bookkeeping (calibrated `A`, exposure counts) for the results doc.
    """
    spec = TRAP_SPEC[trap_id]
    shutil.copytree(TRAVEL_DATASET, dest)
    features = pl.read_csv(dest / "features.csv")
    outcomes = pl.read_csv(dest / "outcomes.csv")
    metadata = pl.read_csv(dest / "metadata.csv")

    total = sum(weights.values())
    score = [0.0] * features.height
    for confounder, weight in weights.items():
        assert confounder in spec["confounders"], (trap_id, confounder)
        for i, flag in enumerate(_indicator(features, confounder)):
            score[i] += (weight / total) * flag

    rng = random.Random(seed)
    in_x = [rng.random() < 0.03 + 0.62 * s for s in score]

    x_column = spec["x_column"]
    original_x = features[x_column].to_list()
    new_x = [
        spec["x_value"] if flagged else (spec["x_other"] if v == spec["x_value"] else v)
        for flagged, v in zip(in_x, original_x, strict=True)
    ]
    features = features.with_columns(pl.Series(x_column, new_x))

    dev = [label == "development" for label in metadata["split_label"].to_list()]
    e_scores = [s for s, x, d in zip(score, in_x, dev, strict=True) if d and x]
    c_scores = [s for s, x, d in zip(score, in_x, dev, strict=True) if d and not x]
    gap = sum(e_scores) / len(e_scores) - sum(c_scores) / len(c_scores)
    amplitude = target_raw_harm / gap
    # Outcome noise is synthetic, small and Gaussian (seeded): the delivered margin's heavy tails
    # (-5,777 EUR outliers) make thin-cell stratified estimates noisy enough to blur the gate
    # under test. Margin depends ONLY on the confounder score; X never enters it (zero direct
    # effect). `gross_profit_eur` (G12's admissible alternative outcome) moves identically.
    noise_rng = random.Random(seed + 1)
    margin = [
        round(BASE_MARGIN_EUR - amplitude * s + noise_rng.gauss(0, NOISE_SD_EUR), 2) for s in score
    ]
    outcomes = outcomes.with_columns(
        pl.Series("contribution_margin_eur", margin),
        pl.Series("gross_profit_eur", [round(m + GROSS_OVER_MARGIN_EUR, 2) for m in margin]),
    )

    features.write_csv(dest / "features.csv")
    outcomes.write_csv(dest / "outcomes.csv")
    manifest_path = dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if validation_roles:
        manifest["validation_roles"].update(validation_roles)
    for partition in manifest["partitions"].values():
        partition["sha256"] = _sha256(dest / partition["path"])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "amplitude_eur": amplitude,
        "dev_exposed": len(e_scores),
        "dev_comparison": len(c_scores),
        "score_gap": gap,
    }


def run_real_gates(
    dataset_root: Path, conditions: list[dict[str, Any]], label: str
) -> CandidateValidation:
    """One candidate through the real `run_validation` (all gates, readiness, warnings)."""
    outcome = primary_outcome()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        candidates_path = tmp / "candidates.json"
        metrics_path = tmp / "metrics.json"
        candidates_path.write_text(
            json.dumps(
                {
                    "status": "PERSISTED",
                    "outcome": {
                        "outcome_id": outcome.outcome_id,
                        "outcome_definition_version": OUTCOME_VERSION,
                    },
                    "candidates": [
                        {
                            "candidate_id": label,
                            "conditions": conditions,
                            "outcome": outcome.outcome_id,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        metrics_path.write_text(json.dumps({"evaluated_hypotheses": FAMILY_SIZE}), encoding="utf-8")
        results, _ = run_validation(
            dataset_root=dataset_root,
            candidates_path=candidates_path,
            outcome=outcome,
            dataset_version=DATASET_VERSION,
            outcome_definition_version=OUTCOME_VERSION,
            analysis_run_id=f"task104-{label}",
            metrics_path=metrics_path,
        )
    assert len(results) == 1
    return results[0]


# ------------------------------------------------------------------------------------------
# Protection switches (in-test monkeypatch only; restored by pytest on exit)
# ------------------------------------------------------------------------------------------


@contextmanager
def g06_disabled() -> Iterator[None]:
    """G06's covariate adjustment neutralised: `_stratified_adjustment` is wrapped so it always
    stratifies on NO columns, i.e. the "adjusted" estimate equals the raw estimate (attenuation
    0, coverage 1.0). The selected adjustment-set names are still reported (the report requires
    them at adjusted evidence levels); only the adjustment arithmetic is switched off. Every other
    gate is untouched. Note this wrapper is also what G16 receives, which is irrelevant for the
    k == 1 fixtures it is used on (G16 is vacuous there).
    """
    original = apply_module._stratified_adjustment  # pyright: ignore[reportPrivateUsage]

    def no_adjustment(
        frame: pl.DataFrame, mask: pl.Series, outcome: Any, columns: tuple[str, ...]
    ) -> tuple[float, float]:
        return original(frame, mask, outcome, ())

    apply_module._stratified_adjustment = no_adjustment  # pyright: ignore[reportPrivateUsage]
    try:
        yield
    finally:
        apply_module._stratified_adjustment = original  # pyright: ignore[reportPrivateUsage]


@contextmanager
def g11_disabled() -> Iterator[None]:
    """G11's concentration ceiling lifted to infinity (the gate can no longer fail)."""
    original = apply_module.DEFAULT_THRESHOLDS
    apply_module.DEFAULT_THRESHOLDS = dataclasses.replace(
        original, seasonal_concentration_index=1e9
    )
    try:
        yield
    finally:
        apply_module.DEFAULT_THRESHOLDS = original


# ------------------------------------------------------------------------------------------
# Result extraction
# ------------------------------------------------------------------------------------------


def gate(result: CandidateValidation, gate_id: GateId) -> Any:
    return next(g for g in result.report.gate_results if g.gate_id is gate_id)


def failing_gates(result: CandidateValidation) -> list[str]:
    return [g.gate_id.value for g in result.report.gate_results if not g.satisfied]


def is_below_shadow_policy(result: CandidateValidation) -> bool:
    return result.report.policy_readiness in (
        PolicyReadiness.NOT_READY,
        PolicyReadiness.EXPERIMENT_ONLY,
    )


def has_confounding_caveat(result: CandidateValidation, gate_id: GateId) -> bool:
    return any(w.startswith(f"{gate_id.value} ") for w in result.report.warnings)


def summarize(result: CandidateValidation) -> dict[str, Any]:
    report = result.report
    return {
        "readiness": report.policy_readiness.value,
        "evidence_level": report.evidence_level.value if report.evidence_level else None,
        "failing_gates": failing_gates(result),
        "g06": gate(result, GateId.CONFOUNDING).detail,
        "g11": gate(result, GateId.SEASONALITY).detail,
        "g16": gate(result, GateId.COMPOSITION_SAFETY).detail,
        "raw_harm": report.raw_effect.value,
    }


@contextmanager
def g16_disabled() -> Iterator[None]:
    """G16 composition safety switched off: the real `classify_composition_safety` still runs,
    its result is then flipped to `satisfied=True` (so the k >= 2 cap can no longer fire)."""
    original = apply_module.classify_composition_safety

    def flipped(*args: Any, **kwargs: Any) -> Any:
        return dataclasses.replace(original(*args, **kwargs), satisfied=True)

    apply_module.classify_composition_safety = flipped
    try:
        yield
    finally:
        apply_module.classify_composition_safety = original


def cap_confirmed(result: CandidateValidation, gate_id: GateId) -> bool:
    """The full cap definition (see module docstring): below `SHADOW_POLICY`, evidence at most
    `predictive_association`, the named gate FAILED, and its caveat is in `report.warnings`."""
    level = result.report.evidence_level
    level_ok = level is None or LEVEL_ORDER.index(level) <= LEVEL_ORDER.index(
        EvidenceLevel.PREDICTIVE
    )
    return (
        is_below_shadow_policy(result)
        and level_ok
        and not gate(result, gate_id).satisfied
        and has_confounding_caveat(result, gate_id)
    )


def reaches_shadow_policy(result: CandidateValidation) -> bool:
    return result.report.policy_readiness in (
        PolicyReadiness.SHADOW_POLICY,
        PolicyReadiness.HIGH_CONFIDENCE,
    )


# ------------------------------------------------------------------------------------------
# Named confounding-weight designs
# ------------------------------------------------------------------------------------------

SEEDS = (101, 102, 103, 104, 105, 106)
#: Moves `G12`'s leave-one-group-out column off `manager` (T01 only; see `TestT01`).
MONTH_ONLY = {"booking_month": 1.0}
DURATION_ONLY = {"trip_duration_days": 1.0}
ISOLATE_G12_ROLES = {"robustness_group_column": "acquisition_channel"}


def catalogue_weights(trap_id: str) -> dict[str, float]:
    """Equal weight on every catalogued `confounded_by` variable (the trap as catalogued)."""
    return {c: 1.0 for c in TRAP_SPEC[trap_id]["confounders"]}


def party_control_weights(trap_id: str) -> dict[str, float]:
    """G06 retains exactly one catalogued confounder on this dataset (`party_size`); this control
    gives it 60% of the confounding (rest split evenly) -- inside the band (about 50-70%) where
    G06 alone decides the outcome (no other gate fails)."""
    others = [c for c in TRAP_SPEC[trap_id]["confounders"] if c != "party_size"]
    return {"party_size": 0.6, **{c: 0.4 / len(others) for c in others}}


# ------------------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------------------

Builder = Callable[..., Path]


@pytest.fixture(scope="module")
def build(tmp_path_factory: pytest.TempPathFactory) -> Builder:
    cache: dict[tuple[Any, ...], Path] = {}

    def _build(
        trap_id: str,
        weights: dict[str, float],
        seed: int = 104,
        roles: dict[str, str] | None = None,
    ) -> Path:
        key = (trap_id, tuple(sorted(weights.items())), seed, tuple(sorted((roles or {}).items())))
        if key not in cache:
            dest = tmp_path_factory.mktemp("task104") / "dataset"
            build_fixture(dest, trap_id, weights, seed=seed, validation_roles=roles)
            cache[key] = dest
        return cache[key]

    return _build


def run_trap(dataset: Path, trap_id: str, label: str) -> CandidateValidation:
    return run_real_gates(dataset, _trap_conditions(trap_id), label)


needs_dataset = pytest.mark.skipif(
    not TRAVEL_DATASET.exists(), reason="delivered analytical dataset not present"
)


@needs_dataset
class TestFixtureReachesRealGates:
    """Evidence that the fixture goes through the real code path, not a re-implementation."""

    def test_real_functions_are_called_with_the_real_adjustment_set(
        self, build: Builder, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, ...]] = []
        g16_calls: list[int] = []
        real_adjust = apply_module._stratified_adjustment  # pyright: ignore[reportPrivateUsage]
        real_g16 = apply_module.classify_composition_safety

        def spy_adjust(
            frame: pl.DataFrame, mask: pl.Series, outcome: Any, columns: tuple[str, ...]
        ) -> tuple[float, float]:
            calls.append(tuple(columns))
            return real_adjust(frame, mask, outcome, columns)

        def spy_g16(*args: Any, **kwargs: Any) -> Any:
            g16_calls.append(len(args[1]))
            return real_g16(*args, **kwargs)

        monkeypatch.setattr(apply_module, "_stratified_adjustment", spy_adjust)
        monkeypatch.setattr(apply_module, "classify_composition_safety", spy_g16)
        result = run_trap(build("T05", party_control_weights("T05")), "T05", "spy")
        # The real _stratified_adjustment was called with the real selected set (party_size, the
        # retained catalogued confounder, among it); G16 was invoked with k == 1 atom (vacuous).
        used = tuple(result.diagnostics["adjustment_columns_used"])
        assert "party_size" in used
        assert used in calls
        assert g16_calls == [1]
        assert apply_module.run_validation is run_validation

    def test_protections_restore_after_context(self) -> None:
        before = (
            apply_module._stratified_adjustment,  # pyright: ignore[reportPrivateUsage]
            apply_module.DEFAULT_THRESHOLDS,
            apply_module.classify_composition_safety,
        )
        with g06_disabled(), g11_disabled(), g16_disabled():
            assert (
                apply_module._stratified_adjustment  # pyright: ignore[reportPrivateUsage]
                is not before[0]
            )
        after = (
            apply_module._stratified_adjustment,  # pyright: ignore[reportPrivateUsage]
            apply_module.DEFAULT_THRESHOLDS,
            apply_module.classify_composition_safety,
        )
        assert after == before


@needs_dataset
class TestSchemaFacts:
    """Testability findings read from the real manifest (no run needed)."""

    def test_booking_month_is_not_an_adjustment_candidate_or_a_column(self) -> None:
        manifest = json.loads((TRAVEL_DATASET / "manifest.json").read_text(encoding="utf-8"))
        roles = manifest["validation_roles"]
        columns = {c for p in manifest["partitions"].values() for c in p["columns"]}
        assert "booking_month" not in columns
        assert "booking_month" not in roles["adjustment_eligible"]
        assert "booking_date" not in roles["adjustment_eligible"]
        assert "travel_month" not in roles["adjustment_eligible"]
        # The only mechanism that sees booking month at all is G11, via booking_date.
        assert roles["seasonality_column"] == "booking_date"
        # G12's leave-one-group-out column is `manager` = T01's apparent_feature column.
        assert roles["robustness_group_column"] == "manager"


@needs_dataset
class TestT01:
    """`manager = Manager 2`; confounded_by destination, booking_lead_days, party_size,
    trip_duration_days. Designated confounding mechanism: G06 (single atom, so G16 is vacuous)."""

    def test_as_shipped_manifest_is_capped_but_by_g12_not_by_a_confounding_gate(
        self, build: Builder
    ) -> None:
        for seed in SEEDS[:3]:
            result = run_trap(build("T01", catalogue_weights("T01"), seed), "T01", "shipped")
            assert is_below_shadow_policy(result)
            assert gate(result, GateId.CONFOUNDING).satisfied  # G06 does NOT stop it
            assert gate(result, GateId.COMPOSITION_SAFETY).satisfied  # k == 1: vacuous
            assert not gate(result, GateId.ROBUSTNESS).satisfied
            # 8 of 9 refits agree: the leave-one-manager-out refit for Manager 2 has no exposed
            # rows at all, so it can never agree, for ANY manager=... candidate.
            assert "89%" in gate(result, GateId.ROBUSTNESS).detail
            assert not cap_confirmed(result, GateId.CONFOUNDING)

    @pytest.mark.parametrize("seed", SEEDS)
    def test_catalogue_structure_is_not_capped_by_g06_once_g12_artifact_removed(
        self, build: Builder, seed: int
    ) -> None:
        dataset = build("T01", catalogue_weights("T01"), seed, ISOLATE_G12_ROLES)
        result = run_trap(dataset, "T01", "catalogue")
        assert gate(result, GateId.CONFOUNDING).satisfied
        assert gate(result, GateId.COMPOSITION_SAFETY).satisfied
        assert reaches_shadow_policy(result)
        assert result.report.evidence_level is EvidenceLevel.ADJUSTED_OBSERVATIONAL
        assert not cap_confirmed(result, GateId.CONFOUNDING)

    def test_g06_adversarial_flip_on_adjustable_control(self, build: Builder) -> None:
        dataset = build("T01", party_control_weights("T01"), 104, ISOLATE_G12_ROLES)
        assert cap_confirmed(run_trap(dataset, "T01", "control"), GateId.CONFOUNDING)
        with g06_disabled():
            off = run_trap(dataset, "T01", "control-g06-off")
        assert not cap_confirmed(off, GateId.CONFOUNDING)
        assert gate(off, GateId.CONFOUNDING).satisfied
        assert "attenuation 0.00" in gate(off, GateId.CONFOUNDING).detail
        assert reaches_shadow_policy(off)
        assert cap_confirmed(run_trap(dataset, "T01", "control-restored"), GateId.CONFOUNDING)


@needs_dataset
class TestT05:
    """`manual_exception = true`; confounded_by destination, party_size, trip_duration_days,
    booking_lead_days. Designated confounding mechanism: G06 (single atom, G16 vacuous)."""

    @pytest.mark.parametrize("seed", SEEDS)
    def test_catalogue_structure_is_not_capped(self, build: Builder, seed: int) -> None:
        result = run_trap(build("T05", catalogue_weights("T05"), seed), "T05", "catalogue")
        assert gate(result, GateId.CONFOUNDING).satisfied
        assert gate(result, GateId.COMPOSITION_SAFETY).satisfied
        assert reaches_shadow_policy(result)
        assert result.report.evidence_level is EvidenceLevel.ADJUSTED_OBSERVATIONAL
        assert not cap_confirmed(result, GateId.CONFOUNDING)

    def test_g06_adversarial_flip_on_adjustable_control(self, build: Builder) -> None:
        dataset = build("T05", party_control_weights("T05"))
        assert cap_confirmed(run_trap(dataset, "T05", "control"), GateId.CONFOUNDING)
        with g06_disabled():
            off = run_trap(dataset, "T05", "control-g06-off")
        assert not cap_confirmed(off, GateId.CONFOUNDING)
        assert gate(off, GateId.CONFOUNDING).satisfied
        assert "attenuation 0.00" in gate(off, GateId.CONFOUNDING).detail
        assert reaches_shadow_policy(off)
        assert cap_confirmed(run_trap(dataset, "T05", "control-restored"), GateId.CONFOUNDING)


@needs_dataset
class TestT02:
    """`supplier = Atlas`; confounded_by trip_duration_days, booking_month. G06 cannot see
    `booking_month`; the only mechanism that can is G11 (seasonality, via `booking_date`)."""

    def test_g11_caps_month_driven_confounding_and_g06_is_not_the_mechanism(
        self, build: Builder
    ) -> None:
        dataset = build("T02", MONTH_ONLY)
        on = run_trap(dataset, "T02", "month")
        assert cap_confirmed(on, GateId.SEASONALITY)
        assert gate(on, GateId.CONFOUNDING).satisfied  # G06 passes: cannot see booking month
        # Disabling G06 changes nothing: it was never the stopper.
        with g06_disabled():
            g06_off = run_trap(dataset, "T02", "month-g06-off")
        assert cap_confirmed(g06_off, GateId.SEASONALITY)

    def test_g11_adversarial_flip(self, build: Builder) -> None:
        dataset = build("T02", MONTH_ONLY)
        assert cap_confirmed(run_trap(dataset, "T02", "month"), GateId.SEASONALITY)
        with g11_disabled():
            off = run_trap(dataset, "T02", "month-g11-off")
        assert not cap_confirmed(off, GateId.SEASONALITY)
        assert gate(off, GateId.SEASONALITY).satisfied
        assert reaches_shadow_policy(off)
        assert cap_confirmed(run_trap(dataset, "T02", "month-restored"), GateId.SEASONALITY)

    def test_duration_driven_confounding_is_not_capped(self, build: Builder) -> None:
        result = run_trap(build("T02", DURATION_ONLY), "T02", "duration")
        assert gate(result, GateId.CONFOUNDING).satisfied
        assert gate(result, GateId.SEASONALITY).satisfied
        assert reaches_shadow_policy(result)

    def test_catalogue_equal_weights_is_capped_only_knife_edge(self, build: Builder) -> None:
        """Equal weight on duration and booking_month: G11's concentration ratio sits at the 1.5
        ceiling, so the outcome is seed-dependent (4 of 6 seeds capped, 2 of 6 reach
        SHADOW_POLICY). Recorded exactly, because the result is not robust."""
        capped: dict[int, bool] = {}
        for seed in SEEDS:
            result = run_trap(build("T02", catalogue_weights("T02"), seed), "T02", "catalogue")
            assert gate(result, GateId.CONFOUNDING).satisfied
            capped[seed] = cap_confirmed(result, GateId.SEASONALITY)
            assert capped[seed] is not reaches_shadow_policy(result)
        assert capped == {101: True, 102: True, 103: False, 104: True, 105: False, 106: True}


@needs_dataset
class TestG16CompoundForms:
    """Supplementary: if a trap's apparent_feature is proposed inside a compound (k >= 2) rule,
    G16 caps it (as `TASK-083` showed for T03/T04). The pure catalogued single-atom forms above
    are outside G16's domain by design."""

    @pytest.mark.parametrize("trap_id", ["T01", "T02", "T05"])
    def test_compound_form_is_capped_by_g16_and_flips_when_disabled(
        self, build: Builder, trap_id: str
    ) -> None:
        dataset = build(
            trap_id,
            catalogue_weights(trap_id),
            104,
            ISOLATE_G12_ROLES if trap_id == "T01" else None,
        )
        conditions = [
            *_trap_conditions(trap_id),
            {"feature": "destination", "operator": "eq", "value": "Tokyo"},
        ]
        on = run_real_gates(dataset, conditions, f"{trap_id}-compound")
        assert cap_confirmed(on, GateId.COMPOSITION_SAFETY)
        assert on.diagnostics["composition_safety_reason"] in (
            "confound_like",
            "composition_risk_indeterminate",
        )
        with g16_disabled():
            off = run_real_gates(dataset, conditions, f"{trap_id}-compound-g16-off")
        assert gate(off, GateId.COMPOSITION_SAFETY).satisfied
        assert not cap_confirmed(off, GateId.COMPOSITION_SAFETY)
        assert cap_confirmed(
            run_real_gates(dataset, conditions, f"{trap_id}-compound-restored"),
            GateId.COMPOSITION_SAFETY,
        )
