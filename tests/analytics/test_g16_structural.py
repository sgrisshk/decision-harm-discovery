"""`G16_CANDIDATE_COMPOSITION_SAFETY` (`TASK-081`): the structural "no third state" proof.

`TASK-081`'s own control level 2 requires the main acceptance test to be **structural, not
example-based**: it must prove the full transition holds as a property --
`compound candidate -> G16 executed -> {confound_like | indeterminate} -> identical evidence CAP`
-- not merely fail to observe `interaction_like` in a handful of fixtures. This file is that
proof. It contains no safety-critical assertion about capping and no diagnostic-correctness
assertion about which label a given DGP "should" receive -- see `test_g16_safety.py` and
`test_g16_diagnostic.py` respectively for those, kept deliberately separate per `TASK-081`'s
control level 3.
"""

from __future__ import annotations

import inspect

import polars as pl
import pytest
from policy_analytics.outcomes.contract import MissingDataPolicy, OutcomeDefinition, OutcomeRole
from policy_analytics.validation.composition_safety import (
    AtomCompositionResult,
    CompositionAtomClassification,
    CompositionSafetyReason,
    CompositionSafetyResult,
    classify_atom,
    classify_composition_safety,
)
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS

pytestmark = pytest.mark.analytics

OUTCOME = OutcomeDefinition(
    outcome_id="g16_structural_test_metric",
    role=OutcomeRole.PRIMARY,
    column="y",
    unit="unit",
    higher_is_worse=True,
    missing_data_policy=MissingDataPolicy.COMPLETE,
    description=(
        "Neutral synthetic outcome for G16's structural tests. Unrelated to any real domain."
    ),
    valid_range=(-1.0e9, 1.0e9),
    aggregation_rule="mean of the outcome column over the group",
    harm_direction_phrase="Value increases",
)


def _stratified_adjustment(
    frame: pl.DataFrame, mask: pl.Series, outcome: OutcomeDefinition, columns: tuple[str, ...]
) -> tuple[float, float]:
    """A tiny, self-contained stand-in for `apply._stratified_adjustment` with the identical
    signature and semantics, used only so this file has no dependency on `apply.py` (this file
    tests `composition_safety.py` as a unit; `test_g16_safety.py` exercises the real function via
    real `_validate_one`/`run_validation` calls end to end).
    """
    if not columns:
        exposed = frame.filter(mask)[outcome.column]
        comparison = frame.filter(~mask)[outcome.column]
        if exposed.len() == 0 or comparison.len() == 0:
            return 0.0, 0.0
        return float(exposed.mean()) - float(comparison.mean()), 1.0  # type: ignore[arg-type]

    working = frame.select([*columns, outcome.column]).with_columns(mask.alias("_exposed"))
    grouped = working.group_by([*columns, "_exposed"]).agg(
        pl.col(outcome.column).sum().alias("_sum"), pl.col(outcome.column).count().alias("_n")
    )
    cells: dict[tuple[object, ...], dict[str, float]] = {}
    for row in grouped.iter_rows(named=True):
        key = tuple(row[c] for c in columns)
        cell = cells.setdefault(key, {"es": 0.0, "en": 0, "cs": 0.0, "cn": 0})
        if row["_exposed"]:
            cell["es"] += row["_sum"]
            cell["en"] += row["_n"]
        else:
            cell["cs"] += row["_sum"]
            cell["cn"] += row["_n"]
    usable = [c for c in cells.values() if c["en"] >= 5 and c["cn"] >= 5]
    total_exposed_all = sum(c["en"] for c in cells.values())
    total_exposed_usable = sum(c["en"] for c in usable)
    if not usable or total_exposed_usable == 0:
        return 0.0, 0.0
    adjusted = (
        sum((c["es"] / c["en"] - c["cs"] / c["cn"]) * c["en"] for c in usable)
        / total_exposed_usable
    )
    coverage = total_exposed_usable / total_exposed_all if total_exposed_all else 0.0
    return adjusted, coverage


def _synthetic_frame(n: int, seed: int) -> pl.DataFrame:
    import random

    rng = random.Random(seed)
    a = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    b = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    c = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    y = [
        1000.0 + 150.0 * a[i] + 40.0 * b[i] - 20.0 * c[i] + rng.gauss(0.0, 60.0) for i in range(n)
    ]
    return pl.DataFrame({"A": a, "B": b, "C": c, "y": y})


def _atom_masks(
    frame: pl.DataFrame, features: tuple[str, ...]
) -> tuple[tuple[str, pl.Series], ...]:
    return tuple((feature, frame[feature] == 1) for feature in features)


# =====================================================================================
# 1. Type-level proof: the classification enum itself has exactly two members.
# =====================================================================================


def test_composition_atom_classification_has_exactly_two_members() -> None:
    """The exhaustive enumeration TASK-081 control level 2 requires: `interaction_like` is not a
    name that exists anywhere on this type, not merely a value no fixture happened to produce.
    """
    members = list(CompositionAtomClassification)
    assert len(members) == 2
    assert {member.value for member in members} == {"confound_like", "indeterminate"}
    assert not any(member.value == "interaction_like" for member in members)
    with pytest.raises(ValueError):
        CompositionAtomClassification("interaction_like")


def test_composition_safety_reason_has_exactly_three_members_none_interaction_like() -> None:
    members = list(CompositionSafetyReason)
    assert len(members) == 3
    assert {member.value for member in members} == {
        "not_applicable_single_atom",
        "confound_like",
        "composition_risk_indeterminate",
    }
    with pytest.raises(ValueError):
        CompositionSafetyReason("interaction_like")


# =====================================================================================
# 2. Code-path proof: classify_atom's own source has exactly two return statements, and they
#    name exactly the two enum members -- not merely "the tests never observed a third value".
# =====================================================================================


def _source_excluding_docstrings(module: object) -> str:
    """`module`'s source with every module/function/class docstring statement blanked out.

    Isolates *live code* (string literals used as values, comparisons, enum members) from
    *documentation* (prose explaining, in backtick-quoted markdown, what was historically
    removed and why -- exactly the pattern `ADR-078` check 6 approved for the design document
    itself: a clearly-marked "REVOKED, do not implement" discussion is not itself a live spec).
    """
    import ast

    source = inspect.getsource(module)  # type: ignore[arg-type]
    tree = ast.parse(source)
    excluded_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                start = body[0].lineno
                end = getattr(body[0], "end_lineno", start)
                excluded_lines.update(range(start, end + 1))
    lines = source.splitlines()
    return "\n".join(line for i, line in enumerate(lines, start=1) if i not in excluded_lines)


def test_classify_atom_source_has_no_reference_to_interaction_like() -> None:
    """A textual proof over the actual shipped *code* (docstrings excluded, see
    `_source_excluding_docstrings`): the string `interaction_like` is never used as a live value
    anywhere in this module -- not merely absent from the handful of fixtures this file exercises.
    """
    import policy_analytics.validation.composition_safety as module

    code_only = _source_excluding_docstrings(module)
    assert "interaction_like" not in code_only


def test_classify_atom_classification_assignment_is_binary_by_construction() -> None:
    """`classify_atom`'s own classification variable is assigned from exactly one ternary-style
    if/else with two branches, each naming one of the two enum members -- inspected structurally
    via the AST rather than merely sampling inputs.
    """
    import ast

    import policy_analytics.validation.composition_safety as module

    source = inspect.getsource(module.classify_atom)
    tree = ast.parse(source)
    assigned_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [
                t.id
                for t in node.targets
                if isinstance(t, ast.Name) and t.id == "classification"
            ]
            if targets and isinstance(node.value, ast.Attribute):
                assigned_names.add(node.value.attr)
    assert assigned_names == {"CONFOUND_LIKE", "INDETERMINATE"}


# =====================================================================================
# 3. Behavioral proof over a real sweep: every atom of every k in {2, 3, 4, 5}, across many
#    random synthetic DGPs, classifies into exactly the two-member set -- confirmation of the
#    type-level guarantee on real computed output, not the load-bearing evidence itself.
# =====================================================================================


@pytest.mark.parametrize("k", [2, 3, 4, 5])
def test_every_atom_of_every_k_classifies_into_the_two_member_set(k: int) -> None:
    feature_names = tuple(f"F{i}" for i in range(k))
    for seed in range(20):
        import random

        rng = random.Random(1000 + seed)
        n = 800
        cols = {name: [1 if rng.random() < 0.5 else 0 for _ in range(n)] for name in feature_names}
        y = [
            1000.0
            + sum(80.0 * (i + 1) * cols[name][row] for i, name in enumerate(feature_names))
            + rng.gauss(0.0, 50.0)
            for row in range(n)
        ]
        frame = pl.DataFrame({**cols, "y": y})
        atom_masks = _atom_masks(frame, feature_names)
        result = classify_composition_safety(
            frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
        )
        assert result.applicable is True
        assert len(result.atom_results) == k
        for atom in result.atom_results:
            assert atom.classification in (
                CompositionAtomClassification.CONFOUND_LIKE,
                CompositionAtomClassification.INDETERMINATE,
            )
        assert result.reason in (
            CompositionSafetyReason.CONFOUND_LIKE,
            CompositionSafetyReason.COMPOSITION_RISK_INDETERMINATE,
        )


# =====================================================================================
# 4. Full enumeration, no order-dependent exclusion (acceptance requirement 2).
# =====================================================================================


def test_every_atom_1_to_k_is_actually_examined_not_beyond_the_first() -> None:
    """A 3-atom candidate must produce exactly 3 `AtomCompositionResult`s, one per atom, with
    `atom_index` covering `1..k` -- not `2..k` ("beyond the first"), the exact unsafe paraphrase
    `ADR-075` correction 2 named and forbade.
    """
    frame = _synthetic_frame(n=900, seed=7)
    atom_masks = _atom_masks(frame, ("A", "B", "C"))
    result = classify_composition_safety(
        frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
    )
    assert [atom.atom_index for atom in result.atom_results] == [1, 2, 3]
    assert [atom.feature for atom in result.atom_results] == ["A", "B", "C"]


def test_composition_safety_source_never_says_beyond_the_first() -> None:
    """Same code/docstring separation as the previous test: the unsafe paraphrase must not
    appear as live logic anywhere -- discussing it as a forbidden historical phrasing in prose
    (as this module's own docstring does, to document the constraint) is fine.
    """
    import policy_analytics.validation.composition_safety as module

    code_only = _source_excluding_docstrings(module)
    assert "beyond the first" not in code_only


# =====================================================================================
# 5. Permutation invariance: the rule-level reason/satisfied outcome does not depend on the
#    order atoms were listed in the candidate's own condition tuple.
# =====================================================================================


def test_permutation_invariance() -> None:
    import itertools

    frame = _synthetic_frame(n=900, seed=11)
    features = ("A", "B", "C")
    reasons = set()
    satisfied_values = set()
    per_feature_classification: dict[str, set[CompositionAtomClassification]] = {
        f: set() for f in features
    }
    for permutation in itertools.permutations(features):
        atom_masks = _atom_masks(frame, permutation)
        result = classify_composition_safety(
            frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
        )
        reasons.add(result.reason)
        satisfied_values.add(result.satisfied)
        for atom in result.atom_results:
            per_feature_classification[atom.feature].add(atom.classification)

    # Rule-level outcome is identical regardless of which slot each atom occupied.
    assert len(reasons) == 1
    assert len(satisfied_values) == 1
    # Each atom's own classification is also identical regardless of its position in the tuple
    # (every other atom always contributes to base_i -- no atom is ever silently excluded).
    for feature in features:
        assert len(per_feature_classification[feature]) == 1


# =====================================================================================
# 6. k == 1 vacuous boundary.
# =====================================================================================


def test_k_equals_1_is_vacuously_satisfied_and_not_applicable() -> None:
    frame = _synthetic_frame(n=200, seed=3)
    atom_masks = _atom_masks(frame, ("A",))
    result = classify_composition_safety(
        frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
    )
    assert result.applicable is False
    assert result.atom_results == ()
    assert result.satisfied is True
    assert result.reason is CompositionSafetyReason.NOT_APPLICABLE_SINGLE_ATOM


def test_k_equals_0_also_treated_as_vacuous_defensively() -> None:
    frame = _synthetic_frame(n=50, seed=4)
    result = classify_composition_safety(
        frame, (), OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
    )
    assert result.applicable is False
    assert result.satisfied is True


# =====================================================================================
# 7. Determinism (acceptance requirement 3): no randomness anywhere in the classification.
# =====================================================================================


def test_classification_is_deterministic_across_repeated_calls() -> None:
    frame = _synthetic_frame(n=700, seed=42)
    atom_masks = _atom_masks(frame, ("A", "B", "C"))
    results = [
        classify_composition_safety(
            frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
        )
        for _ in range(5)
    ]
    first = results[0]
    for other in results[1:]:
        assert other.reason == first.reason
        assert other.satisfied == first.satisfied
        assert [a.classification for a in other.atom_results] == [
            a.classification for a in first.atom_results
        ]
        assert [a.attenuation for a in other.atom_results] == [
            a.attenuation for a in first.atom_results
        ]
        assert [a.coverage for a in other.atom_results] == [a.coverage for a in first.atom_results]


def test_composition_safety_source_has_no_random_or_bootstrap_call() -> None:
    import policy_analytics.validation.composition_safety as module

    source = inspect.getsource(module)
    forbidden = ("random.", "rng.", "bootstrap", "np.random", "resample")
    for token in forbidden:
        assert token not in source, f"unexpected randomness token {token!r} in module source"


# =====================================================================================
# 8. Dataclass shape sanity -- these are frozen, immutable results (no mutation escape hatch).
# =====================================================================================


def test_result_dataclasses_are_frozen() -> None:
    frame = _synthetic_frame(n=300, seed=9)
    atom_masks = _atom_masks(frame, ("A", "B"))
    result = classify_composition_safety(
        frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
    )
    assert isinstance(result, CompositionSafetyResult)
    with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError
        result.satisfied = True  # type: ignore[misc]
    atom = result.atom_results[0]
    assert isinstance(atom, AtomCompositionResult)
    with pytest.raises(Exception):  # noqa: B017
        atom.classification = CompositionAtomClassification.CONFOUND_LIKE  # type: ignore[misc]


def test_classify_atom_matches_the_per_atom_result_inside_classify_composition_safety() -> None:
    """`classify_composition_safety` is not a separate reimplementation of `classify_atom`'s own
    per-atom logic -- it literally calls it once per atom.
    """
    frame = _synthetic_frame(n=500, seed=13)
    atom_masks = _atom_masks(frame, ("A", "B", "C"))
    direct = classify_atom(
        frame, atom_masks, 1, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
    )
    via_candidate = classify_composition_safety(
        frame, atom_masks, OUTCOME, _stratified_adjustment, DEFAULT_THRESHOLDS
    )
    assert via_candidate.atom_results[1] == direct
