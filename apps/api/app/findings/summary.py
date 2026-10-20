"""Deterministic Finding title/summary generation (TASK-024).

Implements `docs/product/finding-product-contract.md` §12.2's mechanical v0 template exactly: a pure
function of `CandidatePattern.conditions` plus the outcome contract's harm-direction phrase. Never
written by a generative model at render time (`ADR-004`) — this runs once, at promotion time, and
the result is stored (`Finding.title`/`Finding.summary`/`Finding.title_template_version`).
"""

from __future__ import annotations

from app.findings.contracts import PatternCondition

TITLE_TEMPLATE_VERSION = "v0-mechanical"

#: Readability limit for the list-row title (§12.2: "must never silently drop a condition without
#: saying so"). The summary is not limited — it has room for every condition.
_TITLE_MAX_CONDITIONS = 3

_OPERATOR_PHRASES: dict[str, str] = {
    "ge": "is at least",
    "le": "is at most",
    "gt": "is more than",
    "lt": "is less than",
}


def _title_case_feature(feature: str) -> str:
    """Mechanical `snake_case` -> `Title Case` — an explicit, disclosed simplification, not a
    curated business label (§12.2: no column carries a human-authored display label yet)."""
    return " ".join(word.capitalize() for word in feature.split("_") if word)


def _condition_phrase(condition: PatternCondition) -> str:
    label = _title_case_feature(condition.feature)
    if condition.operator == "eq" and isinstance(condition.value, bool):
        # Drop the verb and state the flag; negate for `eq: false`.
        return label if condition.value else f"not {label}"
    if condition.operator == "eq":
        return f"{label} is {condition.value}"
    phrase = _OPERATOR_PHRASES.get(condition.operator)
    if phrase is None:
        raise ValueError(f"unsupported condition operator: {condition.operator!r}")
    return f"{label} {phrase} {condition.value}"


def generate_title(harm_direction_phrase: str, conditions: tuple[PatternCondition, ...]) -> str:
    """Short, list-row-length sentence (target <= ~80 characters). Truncates past
    `_TITLE_MAX_CONDITIONS` conditions but always discloses the truncation."""
    if not conditions:
        raise ValueError("a Finding title requires at least one condition")
    shown = conditions[:_TITLE_MAX_CONDITIONS]
    joined = " and ".join(_condition_phrase(c) for c in shown)
    title = f"{harm_direction_phrase} when {joined}"
    remaining = len(conditions) - len(shown)
    if remaining > 0:
        title += f" and {remaining} more condition{'s' if remaining != 1 else ''}"
    return title


def generate_summary(harm_direction_phrase: str, conditions: tuple[PatternCondition, ...]) -> str:
    """One-paragraph version for the detail screen's "What we found" section. Every condition is
    named — the summary is not subject to the title's readability truncation."""
    if not conditions:
        raise ValueError("a Finding summary requires at least one condition")
    joined = " and ".join(_condition_phrase(c) for c in conditions)
    return f"{harm_direction_phrase} when {joined}."
