"""Deterministic per-column schema profiling (TASK-007).

Feeds `TASK-008` (feature-timing classification) and `TASK-009` (data-quality report).
Deliberately separate from `packages.schemas.domain.DatasetColumn` (`name`/`data_type`/`timing`/
`nullable`) — that type is TASK-008's eventual output (a feature-*timing* classification), a
different pipeline stage with its own task; this module only structurally profiles a column,
never classifies its role in a decision.

No ML/black-box inference (`ADR-004`): every classification here is a plain, disclosed,
majority-vote rule over the column's own string values and its name — nothing invented, nothing
opaque. "Likely semantic type" and "safe examples" are explicitly heuristics, not validated facts
or a real PII detector; callers must not present them as more certain than that.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import polars as pl

#: A candidate structural type wins if at least this fraction of a column's non-null values match
#: it. Below this, the column falls back to "string" rather than forcing a bad fit.
TYPE_MATCH_THRESHOLD = 0.98

#: Values not matching the winning type are capped in the persisted/returned list — enough to
#: show a data engineer a real example without unbounded output on a genuinely messy column.
MAX_SUSPICIOUS_VALUES = 5
MAX_EXAMPLE_VALUES = 3
MAX_EXAMPLE_LENGTH = 80

#: Semantic-type guesses whose examples are suppressed when cardinality is also high — not a real
#: PII detector, a conservative floor (see module docstring).
_SUPPRESSED_SEMANTIC_TYPES = frozenset({"identifier", "free_text"})
_HIGH_CARDINALITY_RATIO = 0.9
_LOW_CARDINALITY_RATIO = 0.5

_INTEGER_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
_BOOLEAN_VALUES = frozenset({"true", "false"})
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Whole-token name hints (matched against `name.lower().split("_")`, never raw substring
#: containment — see `_guess_semantic_type`).
_CURRENCY_NAME_HINTS = frozenset({"price", "cost", "margin", "amount", "discount", "refund", "fee"})
_RATE_NAME_HINTS = frozenset({"rate", "pct", "percentage", "share", "ratio"})
_COUNT_NAME_HINTS = frozenset(
    {"count", "size", "duration", "cases", "changes", "installments", "party"}
)


def _matches_integer(value: str) -> bool:
    return bool(_INTEGER_RE.fullmatch(value))


def _matches_float(value: str) -> bool:
    return bool(_FLOAT_RE.fullmatch(value)) or _matches_integer(value)


def _matches_boolean(value: str) -> bool:
    return value.strip().lower() in _BOOLEAN_VALUES


def _matches_date(value: str) -> bool:
    return bool(_DATE_RE.fullmatch(value))


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    name: str
    inferred_type: str
    row_count: int
    missing_count: int
    missingness: float
    distinct_count: int
    min_value: str | None
    max_value: str | None
    semantic_type_guess: str
    examples: tuple[str, ...] = field(default_factory=tuple)
    examples_suppressed: bool = False
    suspicious_values: tuple[str, ...] = field(default_factory=tuple)
    suspicious_count: int = 0


def _infer_structural_type(values: list[str]) -> str:
    """Majority-vote structural type over non-null string values. Empty input -> "string".

    Order matters: the first candidate clearing `TYPE_MATCH_THRESHOLD` wins. A `"0"`/`"1"`-encoded
    boolean column matches `integer` before `boolean` is ever tried and is classified structurally
    as `integer` — a known, documented limitation, refined at the semantic-type layer instead
    (`_guess_semantic_type` recognizes an exactly-two-value `{"0", "1"}` integer column as
    `boolean_flag`).
    """
    if not values:
        return "string"
    for type_name, predicate in (
        ("integer", _matches_integer),
        ("float", _matches_float),
        ("boolean", _matches_boolean),
        ("date", _matches_date),
    ):
        match_rate = sum(1 for value in values if predicate(value)) / len(values)
        if match_rate >= TYPE_MATCH_THRESHOLD:
            return type_name
    return "string"


def _predicate_for(inferred_type: str) -> Callable[[str], bool] | None:
    return {
        "integer": _matches_integer,
        "float": _matches_float,
        "boolean": _matches_boolean,
        "date": _matches_date,
    }.get(inferred_type)


def _min_max(clean_values: list[str], inferred_type: str) -> tuple[str | None, str | None]:
    """`clean_values` must already be filtered to only the values matching `inferred_type`'s own
    predicate (see `profile_column`) — never re-filter more broadly here. A column typed
    "integer" must never report a min/max computed from a value that was itself excluded from
    that type and flagged as suspicious; a suspicious outlier silently laundered into the
    reported range is worse than not reporting a range at all (a real bug this docstring exists
    to prevent recurring: an earlier version filtered numeric ranges with the broader
    `_matches_float`, which also accepts integers, so a suspicious non-integer float value could
    still end up as an "integer" column's reported min/max).
    """
    if not clean_values:
        return None, None
    if inferred_type in ("integer", "float"):
        numeric = [float(v) for v in clean_values]
        return _format_number(min(numeric)), _format_number(max(numeric))
    if inferred_type == "date":
        return min(clean_values), max(clean_values)
    return None, None


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _guess_semantic_type(
    name: str,
    inferred_type: str,
    distinct_count: int,
    non_null_count: int,
    distinct_values: set[str],
) -> str:
    lower_name = name.lower()
    # Whole-token matching, never raw substring containment: "trip_duration" must not match a
    # "ratio" name hint just because "duration" happens to contain "ratio" as a substring (a real
    # false positive this module produced before this was fixed — verified live against
    # tests/fixtures/synthetic_travel_bookings.csv, not caught by unit tests with narrower
    # column-name coverage).
    name_tokens = frozenset(lower_name.split("_"))
    cardinality_ratio = distinct_count / non_null_count if non_null_count else 0.0
    is_high_cardinality = cardinality_ratio > _HIGH_CARDINALITY_RATIO
    is_numeric = inferred_type in ("integer", "float")

    if inferred_type == "integer" and distinct_count == 2 and distinct_values <= {"0", "1"}:
        return "boolean_flag"
    if inferred_type == "boolean":
        return "boolean_flag"
    if inferred_type == "date":
        return "date"
    if (lower_name.endswith("_id") or lower_name == "id") and is_high_cardinality:
        return "identifier"
    if is_numeric and name_tokens & _CURRENCY_NAME_HINTS:
        return "currency_amount"
    if is_numeric and name_tokens & _RATE_NAME_HINTS:
        return "percentage_rate"
    if inferred_type == "integer" and name_tokens & _COUNT_NAME_HINTS:
        return "count_or_quantity"
    if inferred_type == "string" and cardinality_ratio <= _LOW_CARDINALITY_RATIO:
        return "categorical"
    if inferred_type == "string" and is_high_cardinality:
        return "free_text"
    return "unclassified"


def _examples(
    values: list[str], semantic_type: str, cardinality_ratio: float
) -> tuple[tuple[str, ...], bool]:
    if semantic_type in _SUPPRESSED_SEMANTIC_TYPES and cardinality_ratio > _HIGH_CARDINALITY_RATIO:
        return (), True
    seen: list[str] = []
    for value in values:
        truncated = value if len(value) <= MAX_EXAMPLE_LENGTH else value[:MAX_EXAMPLE_LENGTH] + "…"
        if truncated not in seen:
            seen.append(truncated)
        if len(seen) >= MAX_EXAMPLE_VALUES:
            break
    return tuple(seen), False


def profile_column(name: str, values: list[str | None]) -> ColumnProfile:
    """Profile one column's raw string values (`None` = missing/empty CSV cell)."""
    row_count = len(values)
    non_null = [v for v in values if v is not None]
    missing_count = row_count - len(non_null)
    missingness = missing_count / row_count if row_count else 0.0

    inferred_type = _infer_structural_type(non_null)
    predicate = _predicate_for(inferred_type)
    if predicate is not None:
        clean = [v for v in non_null if predicate(v)]
        suspicious = [v for v in non_null if not predicate(v)]
    else:
        clean = non_null
        suspicious = []

    distinct_values = set(non_null)
    distinct_count = len(distinct_values)
    cardinality_ratio = distinct_count / len(non_null) if non_null else 0.0

    # Only ever computed from `clean` — see _min_max's own docstring for why a suspicious value
    # must never leak into the reported range.
    min_value, max_value = _min_max(clean, inferred_type)
    semantic_type = _guess_semantic_type(
        name, inferred_type, distinct_count, len(non_null), distinct_values
    )
    examples, suppressed = _examples(non_null, semantic_type, cardinality_ratio)

    return ColumnProfile(
        name=name,
        inferred_type=inferred_type,
        row_count=row_count,
        missing_count=missing_count,
        missingness=missingness,
        distinct_count=distinct_count,
        min_value=min_value,
        max_value=max_value,
        semantic_type_guess=semantic_type,
        examples=examples,
        examples_suppressed=suppressed,
        suspicious_values=tuple(suspicious[:MAX_SUSPICIOUS_VALUES]),
        suspicious_count=len(suspicious),
    )


def profile_columns(frame: pl.DataFrame) -> tuple[ColumnProfile, ...]:
    """Profile every column of `frame`.

    Precondition: every column must be `Utf8` (string) or null — classification is this module's
    job, not the caller's/Polars' schema inference (`ADR-004`: deterministic, disclosed rules
    only). An empty CSV cell must already be `None`, not `""` (this module treats a blank field as
    missing, not as a distinct empty-string value — the common data-engineering convention and
    Polars' own default `read_csv` behavior).
    """
    profiles: list[ColumnProfile] = []
    for column_name in frame.columns:
        values = frame[column_name].to_list()
        profiles.append(profile_column(column_name, values))
    return tuple(profiles)
