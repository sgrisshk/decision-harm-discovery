"""`TASK-086` (implementing `TASK-085` §5.3): user-facing disclosure text.

Both pieces reuse already-computed quantities only -- `G16`'s own per-atom classification
diagnostics and nothing else. No new computation is exercised or expected here.
"""

import pytest
from policy_analytics.validation.exposure_disclosure import (
    NON_IDENTIFIABILITY_STATEMENT,
    build_exposure_disclosure,
    g16_composition_caveat,
)

pytestmark = pytest.mark.analytics


def test_g16_caveat_is_none_when_g16_did_not_run() -> None:
    # k == 1: composition_safety_atoms is an empty list (matching apply.py's own diagnostic for a
    # single-condition candidate). Must never fabricate a caveat for a rule G16 is vacuous for.
    assert g16_composition_caveat([]) is None
    assert g16_composition_caveat(None) is None


def test_g16_caveat_surfaces_confound_like_atoms_verbatim() -> None:
    atoms = [
        {"atom_index": 1, "feature": "discount_rate", "classification": "confound_like"},
        {"atom_index": 2, "feature": "lead_time_days", "classification": "indeterminate"},
        {"atom_index": 3, "feature": "manual_exception", "classification": "confound_like"},
    ]
    caveat = g16_composition_caveat(atoms)
    assert caveat is not None
    assert (
        "2 of 3 conditions in this rule show no evidence against a confounding explanation"
        in caveat
    )
    assert "1 of 3 conditions" in caveat


def test_g16_caveat_all_indeterminate() -> None:
    atoms = [
        {"atom_index": 1, "feature": "a", "classification": "indeterminate"},
        {"atom_index": 2, "feature": "b", "classification": "indeterminate"},
    ]
    caveat = g16_composition_caveat(atoms)
    assert caveat is not None
    assert "could not rule out confounding for 2 of 2 conditions" in caveat
    assert "confound" in caveat.lower()
    assert "no evidence against a confounding explanation" not in caveat


def test_g16_caveat_all_confound_like() -> None:
    atoms = [
        {"atom_index": 1, "feature": "a", "classification": "confound_like"},
        {"atom_index": 2, "feature": "b", "classification": "confound_like"},
    ]
    caveat = g16_composition_caveat(atoms)
    assert caveat is not None
    assert (
        "2 of 2 conditions in this rule show no evidence against a confounding explanation"
        in caveat
    )
    assert "could not rule out confounding" not in caveat


def test_non_identifiability_statement_is_always_present_and_unconditional() -> None:
    # Present verbatim whether or not G16 ran (k == 1 candidate) -- §5.3's "Always, explicitly".
    disclosure_no_g16 = build_exposure_disclosure([])
    disclosure_with_g16 = build_exposure_disclosure(
        [{"atom_index": 1, "feature": "x", "classification": "confound_like"}]
    )
    assert disclosure_no_g16.non_identifiability_statement == NON_IDENTIFIABILITY_STATEMENT
    assert disclosure_with_g16.non_identifiability_statement == NON_IDENTIFIABILITY_STATEMENT
    assert disclosure_no_g16.g16_caveat is None
    assert disclosure_with_g16.g16_caveat is not None
    # Plain disclosure of non-identifiability, not a hedge ("is small"/"is being refined").
    assert "cannot currently be estimated from this data" in NON_IDENTIFIABILITY_STATEMENT
    assert "is small" not in NON_IDENTIFIABILITY_STATEMENT
    assert "being refined" not in NON_IDENTIFIABILITY_STATEMENT
