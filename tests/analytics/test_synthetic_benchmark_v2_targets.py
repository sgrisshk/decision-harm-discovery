"""TASK-107 Phase 2b: structural tests of the frozen v2 target designs."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from policy_analytics import benchmark_v2_scoring as scoring
from policy_analytics import synthetic_benchmark_v2 as sb2
from policy_analytics import synthetic_benchmark_v2_targets as tg

pytestmark = pytest.mark.analytics

REPOSITORY = Path(__file__).resolve().parents[2]
V1_GT = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
TRAP_LITERALS = {
    ("manager", "Manager 2"),
    ("supplier", "Atlas"),
    ("acquisition_channel", "paid_search"),
    ("payment_method", "bank_transfer"),
    ("manual_exception", True),
}
ENGINE_FEATURES = {
    "destination",
    "supplier",
    "product_category",
    "discount_rate",
    "manager",
    "acquisition_channel",
    "customer_segment",
    "customer_type",
    "party_size",
    "trip_duration_days",
    "payment_method",
    "installments",
    "manual_exception",
}


def test_at_least_ten_core_candidates_and_declared_overlap_present() -> None:
    classes = [d.declared_class for d in tg.DESIGNS]
    assert classes.count("core_candidate") >= 10
    assert classes.count("declared_overlap") >= 1
    assert all(c in tg.DECLARED_CLASSES for c in classes)


def test_ids_unique_and_doses_on_declared_ladders() -> None:
    ids = [d.target_id for d in tg.DESIGNS]
    assert len(set(ids)) == len(ids)
    assert all(d.ladder in tg.LADDERS for d in tg.DESIGNS)


def test_engine_language_and_no_manager_literal_in_core() -> None:
    for d in tg.DESIGNS:
        feats = [c.feature for c in d.conditions]
        assert 1 <= len(feats) <= 3 and len(set(feats)) == len(feats)
        assert set(feats) <= ENGINE_FEATURES
        assert all(c.operator in ("eq", "ge", "lt") for c in d.conditions)
        if d.declared_class == "core_candidate":
            assert "manager" not in feats  # G12 leave-one-manager-out makes it undetectable


def test_trap_literals_only_in_declared_overlap() -> None:
    for d in tg.DESIGNS:
        has = [
            c for c in d.conditions if (c.feature, c.value) in TRAP_LITERALS and c.operator == "eq"
        ]
        assert bool(has) == (d.declared_class == "declared_overlap"), d.target_id
        if d.declared_class == "declared_overlap":
            assert d.trap_literal is not None


def test_no_v1_pattern_literal_is_reused() -> None:
    gt = json.loads(V1_GT.read_text(encoding="utf-8"))
    for p in gt["patterns"]:
        v1 = set(scoring.parse_rule(p["rule"]))
        for d in tg.DESIGNS:
            assert len(v1 & set(d.conditions)) < 2, (p["id"], d.target_id)


def test_at_most_one_shared_categorical_literal_per_pair() -> None:
    for i, a in enumerate(tg.DESIGNS):
        for b in tg.DESIGNS[i + 1 :]:
            shared = [c for c in a.conditions if c.operator == "eq" and c in b.conditions]
            assert len(shared) <= 1, (a.target_id, b.target_id)


def test_predicates_match_rule_strings_on_generated_rows() -> None:
    specs = tg.target_specs()
    draw = sb2.generate_v2(sb2.V2Config(seed=2, row_count=1500), specs)
    for spec in specs:
        conds = scoring.parse_rule(spec.rule)
        for row in draw.rows:
            cov = dict(row)
            cov["booking_month"] = date.fromisoformat(str(row["booking_date"])).month
            expected = all(scoring._row_matches(cov[c.feature], c) for c in conds)  # pyright: ignore[reportPrivateUsage]
            assert expected == spec.predicate(cov)
    assert all(draw.memberships[s.target_id] for s in specs[:5])


def test_covariates_do_not_depend_on_the_target_set() -> None:
    a = sb2.generate_v2(sb2.V2Config(seed=3, row_count=600), ())
    b = sb2.generate_v2(sb2.V2Config(seed=3, row_count=600), tg.target_specs())
    for ra, rb in zip(a.rows, b.rows, strict=True):
        assert all(ra[k] == rb[k] for k in sb2.COVARIATE_COLUMNS)
