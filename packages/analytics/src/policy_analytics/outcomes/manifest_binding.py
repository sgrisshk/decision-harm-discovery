"""Bind TASK-019 to whichever primary outcome the *selected* analytical dataset's own
`manifest.json` pins, instead of hardcoding the travel-global `primary_outcome()` (`HANDOFF-065`).

**Travel itself is untouched.** Its manifest is recognized by `dataset_version` and the real,
Product-reviewed `TASK-013` contract (`primary_outcome()`) is returned unchanged, byte-for-byte,
exactly as before every `HANDOFF-065` change — zero risk of drift for the historical, already-
frozen path. See `tests/analytics/test_manifest_binding.py`'s reproducibility test and
`scripts/validate_candidates.py`'s own default-behavior regression test.

**Any other dataset** (a `TASK-061` domain, or any future one) gets a real `OutcomeDefinition`
built from its manifest's own `outcome_contract` block — written by
`analytical_dataset.build_analytical_dataset` by way of `domain_benchmarks.analytical_bridge`
(`TASK-062`) — plus an empirically-computed `valid_range` (the same "observed [min, max] on the
pinned dataset instance" method `TASK-013` used for travel, just computed at read time instead of
hand-pinned once). This is genuinely provisional and says so in its own `description`: a mechanical
`harm_direction_phrase` (Title-Case column name + "increases"/"decreases"), not a Product-reviewed
one, and `aggregation_rule="arithmetic_mean_of_present_values"`, the same rule every currency-like
outcome in this codebase already uses — never invented, never silently upgraded to look
`TASK-013`-grade.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from policy_analytics.outcomes.contract import (
    DATASET_VERSION,
    MissingDataPolicy,
    OutcomeDefinition,
    OutcomeRole,
    primary_outcome,
)

_MISSING_DATA_POLICY_BY_MANIFEST_VALUE: dict[str, MissingDataPolicy] = {
    "complete_no_missingness_expected": MissingDataPolicy.COMPLETE,
    "missing_not_at_random_report_bounds": MissingDataPolicy.MNAR_BOUNDED,
}


def _mechanical_harm_direction_phrase(outcome_id: str, higher_is_worse: bool) -> str:
    """The same disclosed, non-Product-reviewed placeholder pattern already used for every travel
    secondary outcome (`docs/product/finding-product-contract.md` §12.2): Title-Case the outcome
    id, append "increases"/"decreases" from `higher_is_worse`. Never claims Product review.
    """
    title = outcome_id.replace("_", " ").title()
    return f"{title} {'increases' if higher_is_worse else 'decreases'}"


def _empirical_valid_range(dataset_root: Path, column: str) -> tuple[float, float]:
    """The same method `TASK-013` used to pin travel's own `valid_range` values — the observed
    [min, max] on the dataset instance actually being validated — computed at read time here
    instead of hand-pinned once, since a provisional per-domain contract has no equivalent
    manual-review step to pin it during.
    """
    outcomes = pl.read_csv(dataset_root / "outcomes.csv")
    values = [float(v) for v in outcomes[column].to_list() if v is not None]
    if not values:
        raise ValueError(f"{column} has no present values in {dataset_root}/outcomes.csv")
    return min(values), max(values)


def _primary_definition(outcome_contract: dict[str, Any]) -> dict[str, Any]:
    primary_id = outcome_contract["primary_outcome_id"]
    for definition in outcome_contract["definitions"]:
        if definition["outcome_id"] == primary_id:
            return definition
    raise ValueError(
        f"outcome_contract.primary_outcome_id={primary_id!r} has no matching entry in "
        "outcome_contract.definitions"
    )


def outcome_definition_from_manifest(
    manifest: dict[str, Any], dataset_root: Path
) -> tuple[OutcomeDefinition, str]:
    """The primary `OutcomeDefinition` for whatever dataset `manifest` describes, plus the
    contract version string that produced it (for `outcome_definition_version` provenance).

    Returns travel's real `primary_outcome()`/`OUTCOME_CONTRACT_VERSION` unchanged when `manifest`
    is travel's own (`dataset_version == DATASET_VERSION`) — this function is never the source of
    truth for travel, only a pass-through, so travel's grading can never silently drift by way of
    this binding logic. Raises `KeyError`/`ValueError` for any other dataset whose manifest lacks
    an `outcome_contract` block (i.e. was built before `TASK-062`) — a missing contract is a real
    gap to surface, not something to silently work around with another hardcoded default.
    """
    if manifest.get("dataset_version") == DATASET_VERSION:
        from policy_analytics.outcomes.contract import OUTCOME_CONTRACT_VERSION

        return primary_outcome(), OUTCOME_CONTRACT_VERSION

    outcome_contract = manifest["outcome_contract"]
    definition = _primary_definition(outcome_contract)
    outcome_id = definition["outcome_id"]
    higher_is_worse = bool(definition["higher_is_worse"])
    missing_data_policy = _MISSING_DATA_POLICY_BY_MANIFEST_VALUE.get(
        definition.get("missing_data_policy", ""), MissingDataPolicy.COMPLETE
    )
    status = outcome_contract.get("status", "PROVISIONAL")

    outcome = OutcomeDefinition(
        outcome_id=outcome_id,
        role=OutcomeRole.PRIMARY,
        column=definition["column"],
        unit=definition["unit"],
        higher_is_worse=higher_is_worse,
        missing_data_policy=missing_data_policy,
        description=(
            f"{status} primary outcome bound from {manifest.get('dataset_version', '?')}'s own "
            f"manifest.outcome_contract (owner={outcome_contract.get('owner', '?')}, "
            f"version={outcome_contract.get('version', '?')}) — not a TASK-013-grade, "
            "Statistics/Product-reviewed contract (HANDOFF-065)."
        ),
        valid_range=_empirical_valid_range(dataset_root, definition["column"]),
        aggregation_rule="arithmetic_mean_of_present_values",
        harm_direction_phrase=_mechanical_harm_direction_phrase(outcome_id, higher_is_worse),
        decomposition_of=definition.get("decomposition_of"),
        winsorization_allowed_at_discovery=False,
    )
    return outcome, str(outcome_contract.get("version", "unknown"))
