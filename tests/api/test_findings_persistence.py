from __future__ import annotations

import pytest
from app.findings.contracts import PatternCondition
from app.findings.summary import TITLE_TEMPLATE_VERSION, generate_summary, generate_title


def test_generate_title_single_condition() -> None:
    conditions = (PatternCondition(feature="discount_rate", operator="ge", value=0.12),)
    title = generate_title("Contribution margin drops", conditions)
    assert title == "Contribution margin drops when Discount Rate is at least 0.12"


def test_generate_title_boolean_true_drops_verb() -> None:
    conditions = (PatternCondition(feature="manual_exception", operator="eq", value=True),)
    title = generate_title("Contribution margin drops", conditions)
    assert title == "Contribution margin drops when Manual Exception"


def test_generate_title_boolean_false_is_negated() -> None:
    conditions = (PatternCondition(feature="manual_exception", operator="eq", value=False),)
    title = generate_title("Contribution margin drops", conditions)
    assert title == "Contribution margin drops when not Manual Exception"


def test_generate_title_non_boolean_eq() -> None:
    conditions = (PatternCondition(feature="customer_segment", operator="eq", value="premium"),)
    title = generate_title("Contribution margin drops", conditions)
    assert title == "Contribution margin drops when Customer Segment is premium"


@pytest.mark.parametrize(
    ("operator", "phrase"),
    [("le", "is at most"), ("gt", "is more than"), ("lt", "is less than")],
)
def test_generate_title_operator_phrases(operator: str, phrase: str) -> None:
    conditions = (PatternCondition(feature="discount_rate", operator=operator, value=0.1),)  # type: ignore[arg-type]
    title = generate_title("X drops", conditions)
    assert f"Discount Rate {phrase} 0.1" in title


def test_generate_title_joins_multiple_conditions() -> None:
    conditions = (
        PatternCondition(feature="discount_rate", operator="ge", value=0.12),
        PatternCondition(feature="manual_exception", operator="eq", value=False),
    )
    title = generate_title("Contribution margin drops", conditions)
    assert title == (
        "Contribution margin drops when Discount Rate is at least 0.12 and not Manual Exception"
    )


def test_generate_title_truncates_and_discloses() -> None:
    conditions = tuple(
        PatternCondition(feature=f"feature_{i}", operator="eq", value=i) for i in range(5)
    )
    title = generate_title("X drops", conditions)
    assert "and 2 more conditions" in title
    assert title.count(" and ") == 3  # 2 joins between the 3 shown + the trailing disclosure


def test_generate_title_singular_more_condition() -> None:
    conditions = tuple(
        PatternCondition(feature=f"feature_{i}", operator="eq", value=i) for i in range(4)
    )
    title = generate_title("X drops", conditions)
    assert title.endswith("and 1 more condition")


def test_generate_title_rejects_empty_conditions() -> None:
    with pytest.raises(ValueError, match="at least one condition"):
        generate_title("X drops", ())


def test_generate_summary_lists_every_condition_untruncated() -> None:
    conditions = tuple(
        PatternCondition(feature=f"feature_{i}", operator="eq", value=i) for i in range(5)
    )
    summary = generate_summary("X drops", conditions)
    assert "more condition" not in summary
    for i in range(5):
        assert f"Feature {i} is {i}" in summary
    assert summary.endswith(".")


def test_generate_summary_rejects_empty_conditions() -> None:
    with pytest.raises(ValueError, match="at least one condition"):
        generate_summary("X drops", ())


def test_title_template_version_is_v0_mechanical() -> None:
    assert TITLE_TEMPLATE_VERSION == "v0-mechanical"
