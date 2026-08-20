"""Generic bridge from any registered `TASK-061` domain to `build_analytical_dataset`'s input shape.

Closes the same gap between "raw benchmark generator" and "real analytical-dataset input" that
`TASK-011` closed for travel (`TASK-003` -> `TASK-011`) — just for all six `TASK-061` domains at
once via one function, not six copies of `build_analytical_dataset`. Every domain-specific value
these functions need already lives on the domain's own registered `DomainSpec`
(`domain_benchmarks.registry.DOMAIN_REGISTRY`), so no per-domain analytical-dataset module exists
or is needed — the "one common function + thin per-domain config" split the task asked for is
achieved by deriving the config entirely from data that already exists, rather than by hand-writing
six near-identical config objects.

**What this deliberately does not do:** author a `TASK-013`-grade, STATISTICS-reviewed outcome
contract (empirically-pinned `valid_range`, product-reviewed `harm_direction_phrase`,
`aggregation_rule`/`missing_data_policy` per outcome) for six domains.
`provisional_outcome_contract` produces the much thinner shape
`policy_analytics.discovery.engine.discover_candidates` actually needs to run (its
`OutcomeDefinition` Protocol) and marks itself `status="PROVISIONAL"` throughout so a manifest
reader never mistakes it for a reviewed contract. See `docs/benchmark/multi-domain-benchmarks.md`
for the full write-up.
"""

from __future__ import annotations

from dataclasses import dataclass

from policy_analytics.analytical_dataset import AnalyticalDatasetConfig, OutcomeContractInputs
from policy_analytics.domain_benchmarks.common import DomainSpec

#: `DomainSpec` version this bridge was written against — every `TASK-061` domain's
#: `dataset_version` is derived from `domain_id`, not restated per domain.
PROVISIONAL_CONTRACT_VERSION = "0.1.0-provisional"


def _currency_column(spec: DomainSpec) -> str | None:
    """Every `TASK-061` domain (verified by inspection of all six `FEATURE_TIMING` tables, not
    assumed) marks a METADATA column literally named `currency`. Looked up rather than hardcoded so
    a future domain without one degrades to `None` (no currency rename) instead of raising."""
    for name, (classification, _description) in spec.feature_timing.items():
        if classification == "METADATA" and name == "currency":
            return name
    return None


def _outcome_unit(spec: DomainSpec, column: str) -> str:
    declared_type = spec.declared_types.get(column)
    if declared_type in ("decimal", "integer"):
        return "USD (nominal; single currency; no inflation or FX adjustment)"
    return "rate, proportion in [0, 1]"


def analytical_dataset_config(spec: DomainSpec) -> AnalyticalDatasetConfig:
    """The `AnalyticalDatasetConfig` for any registered `TASK-061` domain, derived entirely from
    its own `DomainSpec` — no per-domain analytical-dataset code."""
    return AnalyticalDatasetConfig(
        dataset_version=f"{spec.domain_id}-analytical-v1.0.0",
        canonical_schema_version=spec.schema_version,
        decision_timestamp_column=spec.decision_timestamp_column,
        identifier_column=spec.primary_id_column,
        clustering_key=spec.clustering_key,
        currency_column=_currency_column(spec),
        development_end=spec.development_end,
        validation_end=spec.validation_end,
        future_holdout_end=spec.future_holdout_end,
    )


def provisional_outcome_contract(spec: DomainSpec) -> OutcomeContractInputs:
    """A minimal, mechanically-generated `OutcomeContractInputs` for any registered domain.

    Only the primary outcome gets a full definition — secondary outcome columns are already listed
    in the manifest's `available_columns` (via `build_analytical_dataset`, dataset-derived) but are
    not individually characterized here, so this function never states a `higher_is_worse`
    judgment it has not actually made for a column nobody has reviewed.
    """
    primary = spec.primary_outcome_column
    higher_is_worse = spec.harm_direction == "increase_is_harm"
    return OutcomeContractInputs(
        status="PROVISIONAL",
        owner="DATA_ENGINEER",
        task="TASK-061",
        version=PROVISIONAL_CONTRACT_VERSION,
        dataset_scope=f"{spec.domain_id}-analytical-v1.0.0",
        primary_outcome_id=primary,
        eligible_cohort_rule=(
            f"{spec.decision_timestamp_column} within the domain's configured temporal window; "
            "no filter on any POST_DECISION or OUTCOME column."
        ),
        default_comparison_rule="complement of the candidate condition within the eligible cohort",
        definitions=(
            {
                "outcome_id": primary,
                "role": "primary",
                "column": primary,
                "unit": _outcome_unit(spec, primary),
                "higher_is_worse": higher_is_worse,
                "missing_data_policy": "not_yet_classified",
                "decomposition_of": None,
                "status": "PROVISIONAL",
            },
        ),
    )


@dataclass(frozen=True, slots=True)
class ProvisionalPrimaryOutcome:
    """Satisfies `policy_analytics.discovery.engine.discover_candidates`'s `OutcomeDefinition`
    Protocol (`outcome_id`/`column`/`unit`/`higher_is_worse`/`harm_multiplier`) for a `TASK-061`
    domain's primary outcome — the minimal object discovery actually needs at runtime, distinct
    from `OutcomeContractInputs` (which describes the manifest, not the discovery-engine call)."""

    outcome_id: str
    column: str
    unit: str
    higher_is_worse: bool

    @property
    def harm_multiplier(self) -> int:
        return 1 if self.higher_is_worse else -1


def provisional_primary_outcome(spec: DomainSpec) -> ProvisionalPrimaryOutcome:
    """The `discover_candidates`-ready outcome object for any registered domain's primary
    outcome."""
    return ProvisionalPrimaryOutcome(
        outcome_id=spec.primary_outcome_column,
        column=spec.primary_outcome_column,
        unit=_outcome_unit(spec, spec.primary_outcome_column),
        higher_is_worse=spec.harm_direction == "increase_is_harm",
    )
