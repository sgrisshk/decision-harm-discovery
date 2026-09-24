"""`TASK-105` Phase 1: prove what the REAL benchmark generator creates for `T01`-`T05`.

`ADR-100` decision 2 keeps three levels apart: threat specification -> generator realization ->
observed run. A confounder listed in the catalogue (`hidden_ground_truth.json` `confounded_by`) is
not thereby implemented. `docs/benchmark/task-105-trap-manifests.json` records, per trap, both the
catalogue (`intended_confounders`) and what the generator actually does
(`implemented_confounders`). This file checks that manifest against the real generator two
independent ways, and turns every catalogue/generator disagreement into a *visible* strict `xfail`
(never a silent pass):

1. **Measurement.** Rows come from the real, unmodified `_generate_row` (same call and RNG stream as
   `generate_benchmark`). Per trap we fit `X ~ pool` and `contribution_margin_eur ~ X + pool`
   (`scripts/measure_task105_generator_realization.py`) and require the dependence pattern to match
   the manifest.
2. **Structure.** The generator's own source (`inspect.getsource(_generate_row)`) is parsed with
   `ast`; the direct column-level parents of each exposure variable are read off the data flow
   (assignments plus enclosing `if` conditions), which gives the *causal direction* that a
   correlation cannot (`T03`'s `discount_rate` is a child of the exposure, not a parent).

Nothing re-implements the generator. No gate/engine/threshold is touched.

Strict `xfail` reasons name the manifest field (`traps.<id>.intended_not_implemented` or
`traps.<id>.implemented_not_catalogued`). Correcting the catalogue flips the whole-trap and
`implemented_not_catalogued` xfails; the per-confounder `intended_not_implemented` xfails assert against generator
measurements, so only a generator change flips them. Either way the manifest must be updated in the same commit.
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
from functools import cache
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from policy_analytics import synthetic_benchmark
from policy_analytics.synthetic_benchmark import (
    BenchmarkConfig,
    generate_benchmark,
)

from scripts import measure_task105_generator_realization as m

pytestmark = pytest.mark.analytics

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "docs/benchmark/task-105-trap-manifests.json"
HIDDEN_TRUTH = REPO_ROOT / "synthetic_data/evaluation/hidden_ground_truth.json"
TRAP_IDS = ("T01", "T02", "T03", "T04", "T05")
MEASURE_N = 60_000
MEASURE_SEED = 105_001

REQUIRED_FIELDS = (
    "intended_confounders",
    "implemented_confounders",
    "causal_role",
    "expected_direction",
    "expected_strength_or_range",
    "observable_columns",
    "applicable_gate",
    "confounder_class",
)

#: `_generate_row` local variable -> the data column it produces (columns only; everything else in
#: the function is an intermediate the data-flow walk passes through).
COLUMN_VARS: dict[str, str] = {
    "booking_date": "booking_date",
    "month": "booking_month",
    "segment": "customer_segment",
    "customer_type": "customer_type",
    "destination": "destination",
    "lead_time": "booking_lead_days",
    "party_size": "party_size",
    "trip_duration": "trip_duration_days",
    "category": "product_category",
    "channel": "acquisition_channel",
    "manager": "manager",
    "supplier": "supplier",
    "discount": "discount_rate",
    "payment_method": "payment_method",
    "installments": "installments",
    "manual_exception": "manual_exception",
    "customer_price": "customer_price_eur",
}
#: exposure column -> local variable that draws it
EXPOSURE_VAR: dict[str, str] = {
    "T01": "manager",
    "T02": "supplier",
    "T03": "channel",
    "T04": "payment_method",
    "T05": "manual_exception",
}


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------
# Structural (AST) reading of the real generator
# --------------------------------------------------------------------------------------------


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _target_base(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Subscript):
        return _target_base(target.value)
    if isinstance(target, ast.Tuple):
        return [b for elt in target.elts for b in _target_base(elt)]
    return []


@cache
def _dependency_graph() -> dict[str, set[str]]:
    """local variable -> variables its value/assignment depends on (RHS names + the conditions of
    every enclosing `if`). Read from the real `_generate_row` source."""
    source = textwrap.dedent(inspect.getsource(synthetic_benchmark._generate_row))  # pyright: ignore[reportPrivateUsage]
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef))
    deps: dict[str, set[str]] = {}

    def visit(statements: list[ast.stmt], context: set[str]) -> None:
        for statement in statements:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    for base in _target_base(target):
                        deps.setdefault(base, set()).update(_names(statement.value) | context)
            elif isinstance(statement, ast.AugAssign) or (
                isinstance(statement, ast.AnnAssign) and statement.value is not None
            ):
                assert statement.value is not None
                for base in _target_base(statement.target):
                    deps.setdefault(base, set()).update(_names(statement.value) | context)
            elif isinstance(statement, ast.If):
                condition = _names(statement.test)
                visit(statement.body, context | condition)
                visit(statement.orelse, context | condition)

    visit(function.body, set())
    return deps


def _column_parents(variable: str) -> set[str]:
    """Data columns that directly cause `variable`, passing through non-column intermediates
    (weight lists, `complexity`) but stopping at the first column variable."""
    graph = _dependency_graph()
    found: set[str] = set()
    seen: set[str] = set()

    def walk(name: str) -> None:
        for dep in graph.get(name, set()):
            if dep == variable:
                continue
            if dep in COLUMN_VARS:
                found.add(COLUMN_VARS[dep])
            elif dep in graph and dep not in seen:
                seen.add(dep)
                walk(dep)

    walk(variable)
    return found


def _column_children(variable: str) -> set[str]:
    column = COLUMN_VARS[variable]
    return {
        COLUMN_VARS[other]
        for other in COLUMN_VARS
        if other != variable and column in _column_parents(other)
    }


def _reaches_outcome(column: str) -> bool:
    """Does `column` feed `contribution_margin` (transitively, through any variable)?"""
    graph = _dependency_graph()
    variable = next(v for v, c in COLUMN_VARS.items() if c == column)
    frontier, seen = ["contribution_margin"], set[str]()
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        for dep in graph.get(current, set()):
            if dep == variable:
                return True
            frontier.append(dep)
    return False


# --------------------------------------------------------------------------------------------
# Measurement (real generator output)
# --------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def generated() -> pl.DataFrame:
    return m.generate_rows(MEASURE_N, MEASURE_SEED)


@pytest.fixture(scope="module")
def measurements(generated: pl.DataFrame) -> dict[str, dict[str, Any]]:
    return {trap_id: m.measure_trap(generated, trap_id) for trap_id in TRAP_IDS}


def _both_sides_significant(measurement: dict[str, Any]) -> set[str]:
    return {
        block
        for block, stats in measurement["blocks"].items()
        if stats["both_sides_significant_p001"]
    }


def _expected_measured(trap: dict[str, Any]) -> set[str]:
    descendants = {z for z, role in trap["causal_role"].items() if role == "descendant_of_exposure"}
    return (
        set(trap["implemented_confounders"]) | set(trap["implemented_not_catalogued"]) | descendants
    )


# --------------------------------------------------------------------------------------------
# Manifest hygiene and catalogue provenance
# --------------------------------------------------------------------------------------------


def test_manifest_has_every_required_field_for_every_trap() -> None:
    manifest = _manifest()
    assert sorted(manifest["traps"]) == list(TRAP_IDS)
    for trap_id, trap in manifest["traps"].items():
        for field in REQUIRED_FIELDS:
            assert field in trap, f"{trap_id} lacks `{field}`"
        assert set(trap["implemented_confounders"]) <= set(trap["intended_confounders"])
        assert set(trap["intended_not_implemented"]) == set(trap["intended_confounders"]) - set(
            trap["implemented_confounders"]
        )
        for confounder in trap["intended_confounders"]:
            assert confounder in trap["causal_role"]
            assert confounder in trap["confounder_class"]
            assert confounder in trap["observable_columns"]
            assert confounder in trap["expected_direction"]
    assert manifest["latent_confounders_implemented_by_generator"] == []


def test_manifest_intended_confounders_equal_committed_catalogue() -> None:
    catalogue = {
        t["id"]: t
        for t in json.loads(HIDDEN_TRUTH.read_text(encoding="utf-8"))["confounding_traps"]
    }
    for trap_id, trap in _manifest()["traps"].items():
        assert trap["intended_confounders"] == catalogue[trap_id]["confounded_by"], trap_id
        column, value = trap["exposure"]["column"], trap["exposure"]["value"]
        rendered = f"{column}={value}" if not isinstance(value, bool) else f"{column}=true"
        assert rendered == catalogue[trap_id]["apparent_feature"], trap_id


def test_committed_catalogue_is_what_the_real_generator_emits(tmp_path: Path) -> None:
    """The catalogue is not hand-maintained elsewhere: regenerate it with the real
    `generate_benchmark` (small row count; the trap list is row-count independent)."""
    generate_benchmark(tmp_path, BenchmarkConfig(row_count=200))
    fresh = json.loads((tmp_path / "evaluation/hidden_ground_truth.json").read_text("utf-8"))
    committed = json.loads(HIDDEN_TRUTH.read_text(encoding="utf-8"))
    assert fresh["confounding_traps"] == committed["confounding_traps"]


def test_generator_reproduces_the_delivered_clean_dataset() -> None:
    """The measured generator IS the one that produced the delivered data (0 mismatching rows)."""
    result = m.generator_matches_delivered()
    assert result["rows"] == 10_000
    assert all(v == 0 for v in result["mismatching_rows_by_column"].values()), result


# --------------------------------------------------------------------------------------------
# Column availability classes (ADR-100 decision 3) read from the delivered manifests
# --------------------------------------------------------------------------------------------


def test_confounder_classes_match_delivered_adjustment_representation() -> None:
    eligible = set(m.manifest_adjustment_eligible())
    roles = m.manifest_feature_roles()
    for trap_id, trap in _manifest()["traps"].items():
        for confounder, cls in trap["confounder_class"].items():
            columns = trap["observable_columns"][confounder]
            if cls == "observable":
                assert confounder in eligible, (trap_id, confounder)
                assert roles[confounder] == "DECISION_TIME", (trap_id, confounder)
                assert columns == [confounder]
            elif cls == "specified_but_unavailable":
                assert confounder not in eligible, (trap_id, confounder)
                assert columns is None
            else:  # 'latent' is not asserted for any trap: see the latent test
                pytest.fail(f"unexpected class {cls!r} for {trap_id}.{confounder}")


def test_booking_month_is_specified_but_not_adjustment_eligible() -> None:
    """`T02`'s `booking_month`: no such column, and both date-carrying columns are excluded from
    G06's pool (`analytical_dataset.py` `validation_roles.adjustment_eligible`)."""
    eligible = set(m.manifest_adjustment_eligible())
    assert "booking_month" not in eligible
    assert "booking_date" not in eligible  # seasonality_column only (G11), not adjustment
    assert "travel_month" not in eligible


# --------------------------------------------------------------------------------------------
# Generator realization: structure (AST) and measurement agree with the manifest
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("trap_id", TRAP_IDS)
def test_structural_parents_of_exposure_match_manifest(trap_id: str) -> None:
    trap = _manifest()["traps"][trap_id]
    parents = _column_parents(EXPOSURE_VAR[trap_id])
    expected = set(trap["implemented_confounders"]) | set(trap["implemented_not_catalogued"])
    assert parents == expected, (
        f"generator source: parents of {trap_id} exposure = {sorted(parents)}"
    )


@pytest.mark.parametrize("trap_id", TRAP_IDS)
def test_structural_role_labels_match_manifest(trap_id: str) -> None:
    trap = _manifest()["traps"][trap_id]
    variable = EXPOSURE_VAR[trap_id]
    parents, children = _column_parents(variable), _column_children(variable)
    for confounder, role in trap["causal_role"].items():
        if role == "common_cause":
            assert confounder in parents, (trap_id, confounder)
            assert _reaches_outcome(confounder), (trap_id, confounder)
        elif role == "descendant_of_exposure":
            assert confounder in children and confounder not in parents, (trap_id, confounder)
        elif role == "not_a_cause_of_exposure":
            assert confounder not in parents and confounder not in children, (trap_id, confounder)
        else:
            pytest.fail(f"unknown role {role!r}")


@pytest.mark.parametrize("trap_id", TRAP_IDS)
def test_no_unobserved_common_cause_of_exposure_in_generator(trap_id: str) -> None:
    """ADR-100 class (iii): the generator gives every exposure only column-level parents. Every
    non-column variable the exposure depends on is a deterministic function of columns
    (weights, `complexity`), so no trap has a latent common cause."""
    graph = _dependency_graph()
    variable = EXPOSURE_VAR[trap_id]
    non_column_roots: set[str] = set()
    seen: set[str] = set()

    def walk(name: str) -> None:
        for dep in graph.get(name, set()):
            if dep in COLUMN_VARS or dep in seen:
                continue
            if dep in graph:
                seen.add(dep)
                walk(dep)
            else:
                non_column_roots.add(dep)

    walk(variable)
    # Only the generator's plumbing (rng, helpers, config, the mapping comprehension variable).
    assert non_column_roots <= {"rng", "config", "_weighted", "number", "f", "int", "range"}, (
        non_column_roots
    )


@pytest.mark.parametrize("trap_id", TRAP_IDS)
def test_measured_dependence_pattern_matches_manifest(
    trap_id: str, measurements: dict[str, dict[str, Any]]
) -> None:
    """Blocks significant on BOTH the exposure side and the outcome side (Wald chi-square,
    p<0.001) equal the manifest's implemented + uncatalogued + descendant set."""
    trap = _manifest()["traps"][trap_id]
    assert _both_sides_significant(measurements[trap_id]) == _expected_measured(trap)


@pytest.mark.parametrize("trap_id", TRAP_IDS)
def test_booking_month_never_drives_any_exposure(
    trap_id: str, measurements: dict[str, dict[str, Any]]
) -> None:
    month = measurements[trap_id]["blocks"]["booking_month"]["x_side"]
    assert month["significant_p001"] == 0.0, month


@pytest.mark.parametrize("trap_id", TRAP_IDS)
def test_expected_rates_match_generator_output(trap_id: str, generated: pl.DataFrame) -> None:
    trap = _manifest()["traps"][trap_id]
    expected = trap["expected_strength_or_range"]["expected_rates"]
    measured = m.generator_score_rates(generated, trap_id)
    assert set(expected) <= set(measured)
    checked = 0
    for stratum, rate in expected.items():
        n = measured[stratum]["n"]
        if n < 200:  # too thin to test at MEASURE_N (T05 complexity=4); still in the raw JSON
            continue
        checked += 1
        tolerance = 5.0 * (rate * (1 - rate) / n) ** 0.5 + 0.003
        assert abs(measured[stratum]["rate"] - rate) <= tolerance, (
            f"{trap_id} {stratum}: measured {measured[stratum]['rate']:.4f} vs manifest {rate} "
            f"(tol {tolerance:.4f}, n={n:.0f})"
        )
    assert checked >= len(expected) - 1


@pytest.mark.parametrize("trap_id", TRAP_IDS)
def test_expected_direction_on_exposure_matches_measured_rate_differences(
    trap_id: str, generated: pl.DataFrame
) -> None:
    trap = _manifest()["traps"][trap_id]
    rates = m.indicator_rates(generated, trap_id)
    indicator_of = {
        "destination": "dest_in_Tokyo_Zanzibar",
        "booking_lead_days": "lead_lt_14",
        "party_size": "party_ge_5",
        "trip_duration_days": "trip_ge_14",
    }
    for confounder, direction in trap["expected_direction"].items():
        if confounder not in indicator_of:
            continue
        stats = rates[indicator_of[confounder]]
        expected = direction["on_exposure"]
        if trap_id == "T02" and confounder == "destination":
            stats = rates["destination=Tokyo"]  # the generator's uncatalogued driver is Tokyo only
        if expected == "+":
            assert stats["rate_diff"] > 0.02, (trap_id, confounder, stats)
        elif expected == "-":
            assert stats["rate_diff"] < -0.02, (trap_id, confounder, stats)
        elif expected == "none":
            assert abs(stats["rate_diff"]) < 0.02, (trap_id, confounder, stats)
        assert direction["on_outcome"] == "-"
        assert stats["outcome_mean_diff_eur"] < 0, (trap_id, confounder, stats)


def test_t03_discount_is_downstream_of_exposure_in_data(generated: pl.DataFrame) -> None:
    """Data-level evidence for `T03`'s role labels: paid_search raises the high-discount rate
    (exposure -> discount), while customer_type / installments do not move the exposure."""
    trap = _manifest()["traps"]["T03"]
    rates = m.generator_score_rates(generated, "T03")
    lift = (
        rates["discount>=0.12_given_paid_search"]["rate"]
        - rates["discount>=0.12_given_not_paid_search"]["rate"]
    )
    assert lift > 0.03
    assert trap["causal_role"]["discount_rate"] == "descendant_of_exposure"
    assert abs(rates["customer_type=new"]["rate"] - rates["customer_type=returning"]["rate"]) < 0.02
    assert abs(rates["installments>=3"]["rate"] - rates["installments<3"]["rate"]) < 0.02


# --------------------------------------------------------------------------------------------
# Catalogue <-> generator DISAGREEMENTS: surfaced as strict xfail, never hidden
# --------------------------------------------------------------------------------------------


def _disagreements(kind: str) -> list[Any]:
    out: list[Any] = []
    for trap_id, trap in _manifest()["traps"].items():
        for confounder in trap[kind]:
            out.append(
                pytest.param(
                    trap_id,
                    confounder,
                    id=f"{trap_id}-{confounder}",
                    marks=pytest.mark.xfail(
                        strict=True,
                        reason=(
                            "CATALOGUE/GENERATOR DISAGREEMENT recorded in "
                            f"docs/benchmark/task-105-trap-manifests.json traps.{trap_id}.{kind} "
                            f"contains '{confounder}': {trap['notes'][:180]}"
                        ),
                    ),
                )
            )
    return out


def _agreements() -> list[Any]:
    out: list[Any] = []
    for trap_id, trap in _manifest()["traps"].items():
        for confounder in trap["implemented_confounders"]:
            out.append(pytest.param(trap_id, confounder, id=f"{trap_id}-{confounder}"))
    return out


def _is_real_common_cause(
    trap_id: str, confounder: str, measurements: dict[str, dict[str, Any]]
) -> bool:
    """A catalogued confounder is genuinely implemented iff the generator's data flow makes it a
    parent of the exposure AND the data shows dependence on both sides."""
    structural = confounder in _column_parents(EXPOSURE_VAR[trap_id])
    block = measurements[trap_id]["blocks"].get(confounder)
    return bool(structural and block is not None and block["both_sides_significant_p001"])


@pytest.mark.parametrize(("trap_id", "confounder"), _agreements())
def test_catalogued_confounder_is_implemented(
    trap_id: str, confounder: str, measurements: dict[str, dict[str, Any]]
) -> None:
    assert _is_real_common_cause(trap_id, confounder, measurements)


@pytest.mark.parametrize(("trap_id", "confounder"), _disagreements("intended_not_implemented"))
def test_catalogued_confounder_is_implemented_DISAGREEMENT(
    trap_id: str, confounder: str, measurements: dict[str, dict[str, Any]]
) -> None:
    """Expected to FAIL: the catalogue names this confounder but the generator does not make it a
    cause of the exposure (or, for T03's `discount_rate`, makes it a descendant)."""
    assert _is_real_common_cause(trap_id, confounder, measurements)


@pytest.mark.parametrize(("trap_id", "confounder"), _disagreements("implemented_not_catalogued"))
def test_generator_confounders_are_all_catalogued_DISAGREEMENT(
    trap_id: str, confounder: str
) -> None:
    """Expected to FAIL: the generator makes this a common cause but the catalogue omits it."""
    catalogue = json.loads(HIDDEN_TRUTH.read_text(encoding="utf-8"))["confounding_traps"]
    listed = next(t for t in catalogue if t["id"] == trap_id)["confounded_by"]
    assert confounder in listed


def _whole_trap_cases() -> list[Any]:
    out: list[Any] = []
    for trap_id, trap in _manifest()["traps"].items():
        marks: list[Any] = []
        if trap["intended_not_implemented"] or trap["implemented_not_catalogued"]:
            marks.append(
                pytest.mark.xfail(
                    strict=True,
                    reason=(
                        f"CATALOGUE/GENERATOR DISAGREEMENT: manifest traps.{trap_id} "
                        f"intended_not_implemented={trap['intended_not_implemented']}, "
                        f"implemented_not_catalogued={trap['implemented_not_catalogued']}"
                    ),
                )
            )
        out.append(pytest.param(trap_id, id=trap_id, marks=marks))
    return out


@pytest.mark.parametrize("trap_id", _whole_trap_cases())
def test_catalogue_equals_realized_confounder_set(trap_id: str) -> None:
    """Whole-trap statement: the catalogue's `confounded_by` equals the generator's real direct
    parents of the exposure. Strict-xfails for T01-T04 (recorded disagreements); passes for T05."""
    catalogue = json.loads(HIDDEN_TRUTH.read_text(encoding="utf-8"))["confounding_traps"]
    listed = set(next(t for t in catalogue if t["id"] == trap_id)["confounded_by"])
    assert _column_parents(EXPOSURE_VAR[trap_id]) == listed
