"""Shared, domain-agnostic machinery for TASK-061's multi-domain benchmark family.

Deliberately independent of `policy_analytics.synthetic_benchmark` (the `TASK-003` travel
benchmark) — zero coupling, zero risk to that already-frozen artifact, per explicit instruction.
Each domain module in `policy_analytics.domain_benchmarks` plugs its own row generator, schema,
feature-timing metadata, and pattern/trap library into the generic engine here
(`run_domain_benchmark`), the same way every domain in this family gets identical leakage-safety,
reproducibility, and ground-truth-consistency guarantees by construction rather than by
6-independent-times discipline.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

Row = dict[str, object]

#: `(index, rng, config, disabled_pattern_id) -> (row, matched_pattern_ids)`. `disabled_pattern_id`
#: is `None` for the real (factual) generation and one pattern id per counterfactual replay pass —
#: implementations must draw exactly the same `rng.*()` sequence regardless of which pattern (if
#: any) is disabled, only the *use* of a draw may differ (see `synthetic_benchmark._generate_row`'s
#: own docstring precedent for this exact discipline).
GenerateRowFn = Callable[
    [int, "random.Random", "DomainRunConfig", "str | None"], tuple[Row, list[str]]
]

DeclaredType = Literal[
    "string", "integer", "decimal", "boolean", "date", "nullable_date", "nullable_boolean"
]


@dataclass(frozen=True, slots=True)
class DomainRunConfig:
    """One generation run's parameters. `active_patterns`/`active_traps` select which mechanisms
    are switched on — this is how the four required diversity variants (0 patterns/0 traps; 0
    patterns/traps only; dominant+weak; comparable-strength) are expressed, not separate code
    paths. `pattern_scale` lets a variant make some active patterns weaker than others (the
    dominant+weak variant) without touching `effect_scale`-style global scaling."""

    seed: int
    row_count: int
    active_patterns: frozenset[str]
    active_traps: frozenset[str] = frozenset()
    pattern_scale: dict[str, float] = field(default_factory=lambda: {})
    dirty_duplicate_rows: int = 30

    def scale_for(self, pattern_id: str) -> float:
        return self.pattern_scale.get(pattern_id, 1.0)

    def is_active(self, pattern_id: str) -> bool:
        return pattern_id in self.active_patterns

    def trap_active(self, trap_id: str) -> bool:
        return trap_id in self.active_traps


@dataclass(frozen=True, slots=True)
class PatternDefinition:
    id: str
    name: str
    rule: str
    behavior: Literal["stable", "seasonal", "drift", "heterogeneous"]
    configured_effect: dict[str, Any]
    valid_interval: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TrapDefinition:
    """A main-effect artifact that looks like a pattern but isn't: `apparent_feature` is
    statistically associated with the outcome only because it is non-randomly assigned in a way
    correlated with `confounded_by`, which does the real (or no) work. `direct_effect` is always
    `0` by construction — see each domain's `generate_row` for the actual non-random-assignment
    mechanism this describes."""

    id: str
    apparent_feature: str
    confounded_by: tuple[str, ...]
    direct_effect: float = 0
    note: str | None = None


@dataclass(frozen=True, slots=True)
class CorruptionOp:
    """One dirty-data corruption operation: mutates `count` sampled rows in place."""

    name: str
    count: int
    apply: Callable[[Row], None]


@dataclass(frozen=True, slots=True)
class DomainSpec:
    domain_id: str
    schema_version: str
    primary_id_column: str
    clustering_key: str
    decision_timestamp_column: str
    outcome_columns: tuple[str, ...]
    primary_outcome_column: str
    feature_timing: dict[str, tuple[str, str]]
    declared_types: dict[str, DeclaredType]
    patterns: tuple[PatternDefinition, ...]
    traps: tuple[TrapDefinition, ...]
    generate_row: GenerateRowFn
    corruption_ops: Callable[[DomainRunConfig], tuple[CorruptionOp, ...]]
    development_end: str
    validation_end: str
    future_holdout_end: str
    harm_direction: Literal["decrease_is_harm", "increase_is_harm"] = "decrease_is_harm"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def apply_corruptions(
    rows: list[Row], ops: tuple[CorruptionOp, ...], seed: int
) -> tuple[list[Row], dict[str, Any]]:
    """Apply `ops` to a copy of `rows` plus append `config.dirty_duplicate_rows`-worth of exact
    duplicate rows (the last, implicit corruption, sized by whichever op is named
    `"duplicate_source_rows"` — its `apply` is ignored, only its `count` is used)."""
    dirty = [row.copy() for row in rows]
    corruption_rng = random.Random(seed)
    changes: dict[str, list[int]] = {}

    def take(count: int) -> list[int]:
        return corruption_rng.sample(range(len(dirty)), count)

    duplicate_count = 0
    for op in ops:
        if op.name == "duplicate_source_rows":
            duplicate_count = op.count
            continue
        indices = take(op.count)
        for index in indices:
            op.apply(dirty[index])
        changes[op.name] = indices

    duplicate_indices = take(duplicate_count) if duplicate_count else []
    for index in duplicate_indices:
        dirty.append(dirty[index].copy())
    changes["duplicate_source_rows"] = duplicate_indices

    return dirty, {
        "seed": seed,
        "operations": {
            name: {"count": len(indices), "zero_based_source_rows": indices}
            for name, indices in changes.items()
        },
    }


def realized_pattern_effects(
    spec: DomainSpec,
    config: DomainRunConfig,
    factual_rows: list[Row],
    memberships: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    """Paired factual-minus-disabled effects under identical random draws — the exact replay
    methodology `HANDOFF-030` independently verified for the travel benchmark, generalized to any
    `DomainSpec`."""
    effects: dict[str, dict[str, Any]] = {}
    for pattern_id, affected_ids in memberships.items():
        affected = set(affected_ids)
        counterfactual_rng = random.Random(config.seed)
        counterfactual_rows = [
            spec.generate_row(index, counterfactual_rng, config, pattern_id)[0]
            for index in range(config.row_count)
        ]
        outcome_effects: dict[str, Any] = {}
        for column in spec.outcome_columns:
            paired_differences: list[float] = []
            for factual, counterfactual in zip(factual_rows, counterfactual_rows, strict=True):
                if factual[spec.primary_id_column] not in affected:
                    continue
                factual_value = factual[column]
                counterfactual_value = counterfactual[column]
                if factual_value == "" or counterfactual_value == "":
                    continue
                if isinstance(factual_value, bool) and isinstance(counterfactual_value, bool):
                    paired_differences.append(float(int(factual_value) - int(counterfactual_value)))
                    continue
                paired_differences.append(
                    float(str(factual_value)) - float(str(counterfactual_value))
                )
            outcome_effects[column] = {
                "estimand": "mean(factual - counterfactual_with_only_this_pattern_disabled)",
                "mean_effect": (
                    round(sum(paired_differences) / len(paired_differences), 6)
                    if paired_differences
                    else None
                ),
                "paired_record_count": len(paired_differences),
            }
        effects[pattern_id] = {
            "affected_record_count": len(affected),
            "outcomes": outcome_effects,
        }
    return effects


@dataclass(frozen=True, slots=True)
class MarginalEffect:
    diff: float
    standard_error: float
    n_matching: int
    n_other: int

    @property
    def z_score(self) -> float:
        return self.diff / self.standard_error if self.standard_error else float("nan")


def _parse_apparent_feature(apparent_feature: str) -> tuple[str, str]:
    """`"warehouse_id=WH1"` -> `("warehouse_id", "WH1")`. Every `TrapDefinition.apparent_feature`
    in every domain must use this exact `column=value` shape — enforced by
    `tests/analytics/test_domain_benchmarks.py` — so this parser stays domain-agnostic."""
    column, _, value = apparent_feature.partition("=")
    if not _:
        raise ValueError(f"apparent_feature must be 'column=value', got {apparent_feature!r}")
    return column.strip(), value.strip()


def raw_marginal_effect(
    rows: list[Row], apparent_feature: str, outcome_column: str
) -> MarginalEffect:
    """The empirical check `HANDOFF-053` asked for: the raw (unadjusted) difference in
    `outcome_column` between rows matching `apparent_feature` ("column=value") and rows that
    don't, with its standard error — computed directly from generated data, never from a
    domain's own declared metadata. Used both to confirm a trap is genuinely "live" when active
    and genuinely silent when inactive (`test_domain_benchmarks.py`)."""
    column, value = _parse_apparent_feature(apparent_feature)
    lowered_value = value.lower()

    def matches(row: Row) -> bool:
        return str(row[column]).lower() == lowered_value

    matching = [float(str(row[outcome_column])) for row in rows if matches(row)]
    other = [float(str(row[outcome_column])) for row in rows if not matches(row)]
    if not matching or not other:
        return MarginalEffect(
            diff=0.0, standard_error=0.0, n_matching=len(matching), n_other=len(other)
        )
    mean_matching = sum(matching) / len(matching)
    mean_other = sum(other) / len(other)
    var_matching = sum((v - mean_matching) ** 2 for v in matching) / len(matching)
    var_other = sum((v - mean_other) ** 2 for v in other) / len(other)
    standard_error = (var_matching / len(matching) + var_other / len(other)) ** 0.5
    return MarginalEffect(
        diff=mean_matching - mean_other,
        standard_error=standard_error,
        n_matching=len(matching),
        n_other=len(other),
    )


def _schema_profile(spec: DomainSpec, rows: list[Row]) -> dict[str, Any]:
    columns: list[dict[str, Any]] = []
    for name in rows[0]:
        declared_type = spec.declared_types[name]
        values = [row[name] for row in rows]
        present = [value for value in values if value != "" and value is not None]
        profile: dict[str, Any] = {
            "name": name,
            "declared_type": declared_type,
            "missing_count": len(values) - len(present),
            "missing_percentage": round(100 * (len(values) - len(present)) / len(values), 4),
            "distinct_count": len({str(value) for value in present}),
            "suspicious_values": [],
        }
        if present and declared_type in {"decimal", "integer"}:
            numeric_values = [float(str(value)) for value in present]
            profile["min"] = min(numeric_values)
            profile["max"] = max(numeric_values)
        elif present and declared_type in {"date", "nullable_date"}:
            date_values = [str(value) for value in present]
            profile["min"] = min(date_values)
            profile["max"] = max(date_values)
        columns.append(profile)
    return {
        "schema_version": spec.schema_version,
        "record_count": len(rows),
        "column_count": len(rows[0]),
        "columns": columns,
    }


def _feature_metadata(spec: DomainSpec) -> dict[str, Any]:
    return {
        "schema_version": spec.schema_version,
        "columns": [
            {
                "name": name,
                "classification": classification,
                "semantic_meaning": meaning,
                "discovery_feature_allowed": classification == "DECISION_TIME",
                "leakage_risk": "HIGH"
                if classification in {"POST_DECISION", "OUTCOME"}
                else "NONE",
            }
            for name, (classification, meaning) in spec.feature_timing.items()
        ],
    }


def _split_label(spec: DomainSpec, timestamp: str) -> str:
    if timestamp <= spec.development_end:
        return "development"
    if timestamp <= spec.validation_end:
        return "validation"
    if timestamp <= spec.future_holdout_end:
        return "future_holdout"
    return "outside_supported_window"


def _ground_truth(
    spec: DomainSpec,
    config: DomainRunConfig,
    memberships: dict[str, list[str]],
    realized_effects: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sign = -1 if spec.harm_direction == "decrease_is_harm" else 1

    def true_effect(pattern_id: str) -> dict[str, Any]:
        pattern = next(p for p in spec.patterns if p.id == pattern_id)
        realized = realized_effects[pattern_id]["outcomes"][spec.primary_outcome_column]
        realized_value = realized["mean_effect"]
        affected_n = realized_effects[pattern_id]["affected_record_count"]
        scale = config.scale_for(pattern_id)
        return {
            "pattern_id": pattern_id,
            "configured_effect": _scale_leaves(pattern.configured_effect, scale),
            "realized_effect": realized_value,
            "direction": spec.harm_direction,
            "affected_n": affected_n,
            "affected_support": round(affected_n / config.row_count, 8) if config.row_count else 0,
            "realized_economic_impact": (
                round(sign * realized_value * affected_n, 2) if realized_value is not None else None
            ),
            "valid_time_interval": pattern.valid_interval,
            "relevant_outcome": spec.primary_outcome_column,
            "economic_impact_sign_convention": (
                f"positive means realized harm; harm_multiplier={sign} from domain harm_direction"
            ),
            "estimand": realized["estimand"],
        }

    active_traps = tuple(trap for trap in spec.traps if config.trap_active(trap.id))
    return {
        "benchmark_version": "1.0.0",
        "domain": spec.domain_id,
        "seed": config.seed,
        "warning": "RESTRICTED: do not expose to ML Discovery before candidate persistence.",
        "active_patterns": sorted(config.active_patterns),
        "active_traps": sorted(config.active_traps),
        "patterns": [
            {
                "id": pattern.id,
                "name": pattern.name,
                "rule": pattern.rule,
                "behavior": pattern.behavior,
                "affected_record_ids": memberships[pattern.id],
                "realized_counterfactual_effects": realized_effects[pattern.id],
                "true_effect": true_effect(pattern.id),
            }
            for pattern in spec.patterns
            if config.is_active(pattern.id)
        ],
        "confounding_traps": [
            {
                "id": trap.id,
                "apparent_feature": trap.apparent_feature,
                "confounded_by": list(trap.confounded_by),
                "direct_effect": trap.direct_effect,
                **({"note": trap.note} if trap.note else {}),
            }
            for trap in active_traps
        ],
    }


def _scale_leaves(value: object, scale: float) -> object:
    if scale == 1.0:
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value * scale
    if isinstance(value, dict):
        typed_value = cast(dict[str, object], value)
        return {key: _scale_leaves(item, scale) for key, item in typed_value.items()}
    return value


def run_domain_benchmark(
    spec: DomainSpec, config: DomainRunConfig, output_root: Path
) -> dict[str, str]:
    """Generate every artifact for one domain/config combination and return checksums. Directory
    shape mirrors `synthetic_benchmark.generate_benchmark`'s exactly: `raw/`, `reference/`,
    `metadata/` are public; `evaluation/` is restricted and never checksummed alongside the public
    tree."""
    if config.row_count < 180:
        raise ValueError("domain benchmark requires at least 180 rows")
    if not (0 <= config.dirty_duplicate_rows <= config.row_count):
        raise ValueError("dirty_duplicate_rows must be between 0 and row_count")
    unknown_patterns = config.active_patterns - {p.id for p in spec.patterns}
    if unknown_patterns:
        raise ValueError(f"unknown active_patterns: {sorted(unknown_patterns)}")
    unknown_traps = config.active_traps - {t.id for t in spec.traps}
    if unknown_traps:
        raise ValueError(f"unknown active_traps: {sorted(unknown_traps)}")

    rng = random.Random(config.seed)
    clean_rows: list[Row] = []
    memberships: dict[str, list[str]] = {p.id: [] for p in spec.patterns}
    for index in range(config.row_count):
        row, matched_patterns = spec.generate_row(index, rng, config, None)
        clean_rows.append(row)
        for pattern_id in matched_patterns:
            memberships[pattern_id].append(str(row[spec.primary_id_column]))

    split_labels = [
        _split_label(spec, str(row[spec.decision_timestamp_column])) for row in clean_rows
    ]
    if "outside_supported_window" in split_labels:
        raise ValueError("records exist outside the configured temporal split window")

    dirty_rows, corruption_manifest = apply_corruptions(
        clean_rows, spec.corruption_ops(config), config.seed + 1
    )
    realized_effects = realized_pattern_effects(spec, config, clean_rows, memberships)

    clean_path = output_root / "reference" / f"{spec.domain_id}_clean.csv"
    dirty_path = output_root / "raw" / f"{spec.domain_id}_dirty.csv"
    write_csv(clean_path, clean_rows)
    write_csv(dirty_path, dirty_rows)
    write_json(output_root / "metadata" / "feature_timing.json", _feature_metadata(spec))
    write_json(output_root / "metadata" / "schema_profile.json", _schema_profile(spec, clean_rows))
    write_json(output_root / "metadata" / "corruption_manifest.json", corruption_manifest)
    write_json(
        output_root / "metadata" / "temporal_splits.json",
        {
            "strategy": (
                f"{spec.decision_timestamp_column} chronological boundaries; no random shuffling"
            ),
            "development": {"end_inclusive": spec.development_end},
            "validation": {"end_inclusive": spec.validation_end},
            "future_holdout": {"end_inclusive": spec.future_holdout_end},
        },
    )
    write_json(
        output_root / "metadata" / "generation_config.json",
        {
            "domain": spec.domain_id,
            "seed": config.seed,
            "row_count": config.row_count,
            "active_patterns": sorted(config.active_patterns),
            "active_traps": sorted(config.active_traps),
            "pattern_scale": config.pattern_scale,
            "dirty_duplicate_rows": config.dirty_duplicate_rows,
            "generator_version": "1.0.0",
        },
    )
    write_json(
        output_root / "evaluation" / "hidden_ground_truth.json",
        _ground_truth(spec, config, memberships, realized_effects),
    )

    checksums_path = output_root / "metadata" / "checksums.json"
    public_dirs = ("raw", "reference", "metadata")
    artifact_paths = sorted(
        path
        for directory in public_dirs
        for path in (output_root / directory).rglob("*")
        if path.is_file() and path != checksums_path
    )
    checksums = {str(path.relative_to(output_root)): sha256_file(path) for path in artifact_paths}
    write_json(checksums_path, checksums)
    write_json(
        output_root / "evaluation" / "checksums.json",
        {
            "hidden_ground_truth.json": sha256_file(
                output_root / "evaluation" / "hidden_ground_truth.json"
            )
        },
    )
    return checksums


Variant = Literal["noise", "traps_only", "dominant_weak", "comparable"]

#: Effect multiplier for the "weaker" patterns in the `dominant_weak` variant — clearly
#: subordinate to the dominant pattern's untouched (`1.0`) magnitude without being negligible.
WEAK_PATTERN_SCALE = 0.35
#: How many of the dominant pattern's structurally distinct followers get activated.
WEAK_PATTERN_COUNT = 5
#: How many traps activate in `traps_only` — within the 2-3 the task requires.
TRAPS_ONLY_COUNT = 3


def standard_variant_config(
    spec: DomainSpec, variant: Variant, *, seed: int, row_count: int
) -> DomainRunConfig:
    """Build one of TASK-061's four required diversity variants generically from any
    `DomainSpec`, using only its declared pattern/trap order — no per-domain special-casing.
    `spec.patterns[0]` is each domain's designated "flagship" pattern by convention (documented in
    the domain module itself); `dominant_weak` pairs it with the next `WEAK_PATTERN_COUNT`
    structurally distinct patterns at `WEAK_PATTERN_SCALE`."""
    if variant == "noise":
        return DomainRunConfig(
            seed=seed, row_count=row_count, active_patterns=frozenset(), active_traps=frozenset()
        )
    if variant == "traps_only":
        trap_ids = frozenset(trap.id for trap in spec.traps[:TRAPS_ONLY_COUNT])
        return DomainRunConfig(
            seed=seed, row_count=row_count, active_patterns=frozenset(), active_traps=trap_ids
        )
    if variant == "dominant_weak":
        dominant = spec.patterns[0].id
        weak = tuple(p.id for p in spec.patterns[1 : 1 + WEAK_PATTERN_COUNT])
        return DomainRunConfig(
            seed=seed,
            row_count=row_count,
            active_patterns=frozenset((dominant, *weak)),
            active_traps=frozenset(),
            pattern_scale={pattern_id: WEAK_PATTERN_SCALE for pattern_id in weak},
        )
    if variant == "comparable":
        return DomainRunConfig(
            seed=seed,
            row_count=row_count,
            active_patterns=frozenset(p.id for p in spec.patterns),
            active_traps=frozenset(t.id for t in spec.traps),
        )
    raise ValueError(f"unknown variant: {variant!r}")
