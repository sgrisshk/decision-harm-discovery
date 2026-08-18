"""Apply a confirmed `ColumnMapping` to produce a canonically-shaped dataframe (TASK-010).

Pure computation, no I/O. Fails closed: any mapping validation problem
(`mapping.validate_mapping`) or any value that cannot be coerced to its canonical field's declared
type raises `CanonicalizationError` rather than silently dropping or coercing to a default. Source
columns not mapped to any canonical field are recorded, not silently discarded — see
`CanonicalizationResult.dropped_columns`.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from policy_analytics.cleaning.canonical_schema import CANONICAL_FIELDS_BY_NAME, CanonicalField
from policy_analytics.cleaning.mapping import ColumnMapping, validate_mapping
from policy_analytics.profiling.feature_timing import FeatureTimingClassification

_POLARS_DTYPE: dict[str, type[pl.DataType]] = {
    "string": pl.Utf8,
    "integer": pl.Int64,
    "float": pl.Float64,
    "boolean": pl.Boolean,
    "date": pl.Date,
}

_TRUE_VALUES = frozenset({"true", "1", "yes", "y"})
_FALSE_VALUES = frozenset({"false", "0", "no", "n"})


class CanonicalizationError(ValueError):
    """Raised for an invalid mapping or a value that cannot be safely coerced."""


@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    frame: pl.DataFrame
    schema_version: str
    mapped_columns: tuple[str, ...]
    dropped_columns: tuple[str, ...]


def _coerce_boolean(column: pl.Series) -> pl.Series:
    lowered = column.str.strip_chars().str.to_lowercase()
    is_true = lowered.is_in(list(_TRUE_VALUES))
    is_false = lowered.is_in(list(_FALSE_VALUES))
    is_null = column.is_null()
    unrecognized = (~is_true) & (~is_false) & (~is_null)
    if unrecognized.any():
        bad = column.filter(unrecognized).to_list()[:5]
        raise CanonicalizationError(
            f"column '{column.name}' has values not recognized as boolean: {bad}"
        )
    frame = pl.DataFrame({"is_true": is_true, "is_null": is_null})
    return frame.select(
        pl.when(pl.col("is_null")).then(None).otherwise(pl.col("is_true")).alias(column.name)
    ).to_series()


def _coerce_column(column: pl.Series, field: CanonicalField) -> pl.Series:
    if field.dtype == "boolean":
        return _coerce_boolean(column)
    target = _POLARS_DTYPE[field.dtype]
    try:
        return column.cast(target, strict=True)
    except pl.exceptions.PolarsError as exc:
        raise CanonicalizationError(
            f"column '{column.name}' could not be coerced to canonical type "
            f"'{field.dtype}' for field '{field.name}': {exc}"
        ) from exc


def canonicalize(
    frame: pl.DataFrame,
    mapping: ColumnMapping,
    classifications: tuple[FeatureTimingClassification, ...],
) -> CanonicalizationResult:
    """Apply `mapping` to `frame` and return a dataframe with exactly the mapped canonical
    columns, each cast to its declared type. Raises `CanonicalizationError` on any mapping
    validation problem or type-coercion failure — never partially canonicalizes."""
    errors = validate_mapping(mapping, classifications)
    if errors:
        raise CanonicalizationError("; ".join(errors))

    coerced: dict[str, pl.Series] = {}
    for field_mapping in mapping.fields:
        field = CANONICAL_FIELDS_BY_NAME[field_mapping.canonical_name]
        source = frame[field_mapping.source_column]
        coerced[field.name] = _coerce_column(source, field)

    mapped_source_columns = {fm.source_column for fm in mapping.fields}
    dropped = tuple(name for name in frame.columns if name not in mapped_source_columns)

    canonical_frame = pl.DataFrame(coerced)
    return CanonicalizationResult(
        frame=canonical_frame,
        schema_version=mapping.schema_version,
        mapped_columns=tuple(fm.canonical_name for fm in mapping.fields),
        dropped_columns=dropped,
    )
