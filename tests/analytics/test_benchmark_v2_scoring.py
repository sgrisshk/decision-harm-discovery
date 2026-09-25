"""TASK-107 Phase 2a: regression and mutation tests for the v2 scorer core.

Real fixtures (tracked files): the committed v1 analytical dataset and ground truth, the TASK-108
vacuous/bare/confounder shapes, the historical precise `P06` (J 0.705) and dilute `P01` (J 0.504)
rules, and the v0.6.2 broad candidates of the TASK-103 evidence. Synthetic populations cover the
ADR-106 pair, vacuity, Exact-bijection and invariant edge cases. Each rule component has a test that
mutates that component (a constant or a function) and asserts a verdict flips.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import functools
import json
import random
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from policy_analytics import benchmark_v2_scoring as S
from policy_analytics.discovery.engine import DiscoveryConfig
from policy_analytics.validation.apply import load_analytical_frame
from policy_analytics.validation.contract import DEFAULT_THRESHOLDS

pytestmark = pytest.mark.analytics

REPOSITORY = Path(__file__).resolve().parents[2]
V1_ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
V1_GT = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
C = S.CondSpec
OK = "predictive_association"

# v1 patterns used as a stand-in v2 target set for the regression fixtures (strata are assigned
# here for the test only: v2 core targets are designed in Phase 2b).
_V1_STRATA = {
    "P01": "core",
    "P02": "out_of_language",
    "P08": "core",
    "P09": "out_of_language",
    "P07": "core",
    "P03": "declared_overlap",
    "P04": "declared_overlap",
    "P05": "declared_overlap",
    "P06": "declared_overlap",
}


@dataclass
class Ctx:
    space: S.RowSpace
    targets: list[S.Target]
    traps: list[S.Trap]


@functools.cache
def real_ctx() -> Ctx:
    frame = load_analytical_frame(V1_ROOT)
    gt = json.loads(V1_GT.read_text(encoding="utf-8"))
    cols: dict[str, list[Any]] = {
        c: frame[c].to_list() for c in frame.columns if c not in ("booking_date", "travel_date")
    }
    cols["booking_month"] = [date.fromisoformat(str(d)).month for d in frame["booking_date"]]
    dev = 0
    for i, label in enumerate(frame["split_label"].to_list()):
        if label == "development":
            dev |= 1 << i
    space = S.RowSpace(cols, dev)
    index_of = {b: i for i, b in enumerate(frame["booking_id"].to_list())}
    targets: list[S.Target] = []
    for p in gt["patterns"]:
        conds = S.parse_rule(p["rule"])
        in_lang = len(conds) <= 3 and all(c.operator != "in" for c in conds)
        targets.append(
            S.Target(
                p["id"],
                _V1_STRATA[p["id"]],
                conds,
                space.ids_to_mask(index_of, p["affected_booking_ids"]),
                conds if in_lang else None,
            )
        )
    traps: list[S.Trap] = []
    for t in gt["confounding_traps"]:
        feature, _, raw = str(t["apparent_feature"]).partition("=")
        value: Any = True if raw == "true" else raw
        traps.append(S.Trap(str(t["id"]), C(feature, "eq", value)))
    return Ctx(space, targets, traps)


def cand(
    cid: str,
    conds: list[S.CondSpec],
    level: str | None = OK,
    readiness: str = "hold",
) -> S.Candidate:
    return S.Candidate(cid, tuple(conds), level, readiness)


def run(
    conds: list[S.CondSpec],
    level: str | None = OK,
    ctx: Ctx | None = None,
    const: S.Constants = S.CONSTANTS,
    readiness: str = "hold",
) -> dict[str, Any]:
    c = ctx or real_ctx()
    return S.score(c.space, c.targets, c.traps, [cand("X", conds, level, readiness)], const)


def only(res: dict[str, Any]) -> dict[str, Any]:
    return res["candidates"][0]


# ---- the ten TASK-108 vacuous / bare / confounder shapes (real exposure counts asserted) --------
TEN_SHAPES: dict[str, tuple[list[S.CondSpec], int, str]] = {
    "bank_transfer AND lead<400": (
        [C("payment_method", "eq", "bank_transfer"), C("booking_lead_days", "lt", 400.0)],
        3077,
        "T04",
    ),
    "bank_transfer AND lead<60": (
        [C("payment_method", "eq", "bank_transfer"), C("booking_lead_days", "lt", 60.0)],
        1825,
        "T04",
    ),
    "paid_search AND installments>=1": (
        [C("acquisition_channel", "eq", "paid_search"), C("installments", "ge", 1.0)],
        2726,
        "T03",
    ),
    "paid_search AND customer_type=new": (
        [C("acquisition_channel", "eq", "paid_search"), C("customer_type", "eq", "new")],
        1706,
        "T03",
    ),
    "paid_search AND installments>=3 AND discount>=0.03": (
        [
            C("acquisition_channel", "eq", "paid_search"),
            C("installments", "ge", 3.0),
            C("discount_rate", "ge", 0.03),
        ],
        431,
        "T03",
    ),
    "Atlas AND trip_duration>=1": (
        [C("supplier", "eq", "Atlas"), C("trip_duration_days", "ge", 1.0)],
        2530,
        "T02",
    ),
    "manual_exception AND price>=0": (
        [C("manual_exception", "eq", True), C("customer_price_eur", "ge", 0.0)],
        688,
        "T05",
    ),
    "bare bank_transfer": ([C("payment_method", "eq", "bank_transfer")], 3077, "T04"),
    "bare paid_search": ([C("acquisition_channel", "eq", "paid_search")], 2726, "T03"),
    "bare Atlas": ([C("supplier", "eq", "Atlas")], 2530, "T02"),
}


@pytest.mark.parametrize("label", list(TEN_SHAPES))
@pytest.mark.parametrize("level", [OK, "descriptive", None])
def test_ten_task108_shapes_are_never_specific_and_stay_traps(
    label: str, level: str | None
) -> None:
    conds, exposure, trap = TEN_SHAPES[label]
    rec = only(run(conds, level))
    assert rec["n_exposed"] == exposure
    assert trap in rec["trap_hits"]
    assert rec["in_pool"] is False
    assert rec["covers_targets"] == []
    assert all(v is None for v in rec["specific_targets_by_theta"].values())
    assert rec["exact_targets"] == []


def test_vacuous_shapes_reduce_to_the_bare_literal() -> None:
    for label in ("bank_transfer AND lead<400", "paid_search AND installments>=1"):
        rec = only(run(TEN_SHAPES[label][0]))
        assert len(rec["effective_conditions"]) == 1
        assert len(rec["vacuous_dropped"]) == 1


def test_confounder_shape_has_borderline_j_but_fails_condition_precision() -> None:
    conds = TEN_SHAPES["paid_search AND installments>=3 AND discount>=0.03"][0]
    rec = only(run(conds))
    m = rec["per_target"]["P03"]
    assert m["j_e"] == pytest.approx(0.5069, abs=1e-3)
    assert m["cp"] == pytest.approx(2 / 3)
    assert rec["specific_targets_by_theta"]["0.50"] is None
    # the theta_p = 0.67 alternative would have made it a recovery (spec D2): mutation
    mutated = only(run(conds, const=replace(S.CONSTANTS, theta_p=0.66)))
    assert mutated["specific_targets_by_theta"]["0.50"] == "P03"


# ---- historical rules -------------------------------------------------------------------------
P06_PRECISE = [
    C("booking_lead_days", "lt", 23.0),
    C("destination", "eq", "Tokyo"),
    C("payment_method", "eq", "bank_transfer"),
]
P01_DILUTE = [
    C("booking_lead_days", "lt", 23.0),
    C("discount_rate", "ge", 0.08),
    C("supplier", "eq", "BlueWing"),
]


def test_historical_precise_p06_is_specific_and_exempt_when_validated() -> None:
    rec = only(run(P06_PRECISE))
    assert rec["per_target"]["P06"]["j_e"] == pytest.approx(0.7053, abs=1e-3)
    assert rec["per_target"]["P06"]["cp"] == 1.0
    assert rec["credited_target"] == "P06"
    assert rec["trap_hits"] == []
    assert rec["exempted_traps"] == [{"trap": "T04", "pattern": "P06"}]
    assert rec["specific_targets_by_theta"] == {"0.30": "P06", "0.50": "P06", "0.70": "P06"}


def test_historical_precise_p06_unvalidated_stays_a_trap_under_the_strict_reading() -> None:
    for level in (None, "descriptive"):
        rec = only(run(P06_PRECISE, level))
        assert rec["trap_hits"] == ["T04"]
        assert rec["in_pool"] is False
        assert all(v is None for v in rec["specific_targets_by_theta"].values())


def test_historical_p01_knife_edge_rule_is_specific_at_half_not_at_seven_tenths() -> None:
    rec = only(run(P01_DILUTE))
    assert rec["per_target"]["P01"]["j_e"] == pytest.approx(0.5035, abs=1e-3)
    assert rec["specific_targets_by_theta"] == {"0.30": "P01", "0.50": "P01", "0.70": None}


def test_p06_precise_is_specific_at_the_knife_edge_seven_tenths_by_005() -> None:
    m = only(run(P06_PRECISE))["per_target"]["P06"]["j_e"]
    assert 0.70 < m < 0.71


def test_vacuous_extra_condition_on_a_precise_rule_does_not_break_specific() -> None:
    conds = [*P06_PRECISE, C("customer_price_eur", "ge", 0.0)]
    rec = only(run(conds))
    assert rec["vacuous_dropped"] == ["customer_price_eur ge 0.0"]
    assert rec["specific_targets_by_theta"]["0.50"] == "P06"


# ---- v0.6.2 broad candidates -------------------------------------------------------------------
@pytest.mark.parametrize("run_name", ["run1", "run2"])
def test_v062_broad_candidates_are_never_specific(run_name: str) -> None:
    path = REPOSITORY / f"docs/benchmark/task-103-evidence/{run_name}/candidates.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    ctx = real_ctx()
    cands = [
        cand(
            str(c["candidate_id"]),
            [C(str(x["feature"]), str(x["operator"]), x["value"]) for x in c["conditions"]],
        )
        for c in payload["candidates"]
    ]
    assert len(cands) == 15
    res = S.score(ctx.space, ctx.targets, ctx.traps, cands)
    for name, stratum in res["strata"].items():
        for key, hit in stratum["specific_targets"].items():
            assert hit == [], (name, key)
    assert all(c["credited_target"] is None or c["best_j"] < 0.3 for c in res["candidates"])
    assert any(c["broad"] for c in res["candidates"])  # lenient coverage still fires
    text = S.render_report(res)
    assert "0/" in text and "reached predictive_association" in text
    assert "broad candidates present" in text


# ---- ADR-106 pair shapes (synthetic population; exposure metrics differ from condition-set J) ----
def _adr_space() -> tuple[S.RowSpace, S.Target]:
    rng = random.Random(20260925)
    n = 4000
    cols: dict[str, list[Any]] = {k: [] for k in "abcdxy"}
    for _ in range(n):
        cols["a"].append(int(rng.random() < 0.35))
        cols["b"].append(int(rng.random() < 0.35))
        cols["c"].append(int(rng.random() < 0.8))
        cols["d"].append(int(rng.random() < 0.8))
        cols["x"].append(int(rng.random() < 0.9))
        cols["y"].append(int(rng.random() < 0.9))
    space = S.RowSpace(cols)
    truth = tuple(C(k, "eq", 1) for k in "abcd")
    return space, S.Target("T1", "core", truth, space.rule_mask(truth), truth)


def _adr_run(conds: list[S.CondSpec], const: S.Constants = S.CONSTANTS) -> dict[str, Any]:
    space, target = _adr_space()
    return only(S.score(space, [target], [], [cand("A", conds)], const))


def test_adr_pair_shapes_share_condition_set_jaccard_but_not_the_specific_verdict() -> None:
    shape_a = [C("a", "eq", 1), C("b", "eq", 1)]  # 2 of 4 true, nothing extra
    shape_b = [C("a", "eq", 1), C("b", "eq", 1), C("c", "eq", 1), C("x", "eq", 1), C("y", "eq", 1)]
    assert 2 / (2 + 0 + 4 - 2) == 3 / (3 + 2 + 4 - 3) == 0.5  # ADR-106 arithmetic
    a, b = _adr_run(shape_a), _adr_run(shape_b)
    assert a["per_target"]["T1"]["j_e"] >= 0.5 and b["per_target"]["T1"]["j_e"] >= 0.5
    assert a["per_target"]["T1"]["cp"] == 1.0
    assert b["per_target"]["T1"]["cp"] == pytest.approx(3 / 5)
    assert a["specific_targets_by_theta"]["0.50"] == "T1"
    assert b["specific_targets_by_theta"]["0.50"] is None
    # mutating the precision floor is what separates them
    loose = _adr_run(shape_b, replace(S.CONSTANTS, theta_p=0.6))
    assert loose["specific_targets_by_theta"]["0.50"] == "T1"


# ---- vacuity edge cases -------------------------------------------------------------------------
def _vac_space() -> S.RowSpace:
    rng = random.Random(7)
    n = 3000
    cols: dict[str, list[Any]] = {k: [] for k in ("u", "v", "w", "a", "b", "weak", "z", "n")}
    for _ in range(n):
        u = int(rng.random() < 0.6)
        cols["u"].append(u)
        cols["v"].append(u)  # identical to u: mutually redundant
        cols["w"].append(int(rng.random() < 0.7))
        cols["a"].append(int(rng.random() < 0.3))
        cols["b"].append(int(rng.random() < 0.3))
        cols["weak"].append(int(rng.random() < 0.97))
        cols["z"].append(int(rng.random() < 0.98))
        cols["n"].append(rng.randrange(100))
    return S.RowSpace(cols)


def test_redundant_conditions_drop_exactly_one_sequentially_and_deterministically() -> None:
    space = _vac_space()
    rule = [C("u", "eq", 1), C("v", "eq", 1), C("w", "eq", 1)]
    eff = S.effective_rule(space, rule)
    assert eff.conditions == (C("v", "eq", 1), C("w", "eq", 1))  # tie-break drops `u`, keeps `v`
    assert eff.dropped == (C("u", "eq", 1),)
    assert S.effective_rule(space, rule[::-1]) == eff  # order independent


def test_simultaneous_vacuity_would_empty_the_rule_mutation() -> None:
    space = _vac_space()
    rule = [C("u", "eq", 1), C("v", "eq", 1)]

    def simultaneous(
        sp: S.RowSpace, conds: list[S.CondSpec], nu: float = S.CONSTANTS.nu
    ) -> tuple[S.CondSpec, ...]:
        exposed = S.popcount(sp.rule_mask(conds))
        keep = [
            c
            for i, c in enumerate(conds)
            if S.popcount(sp.rule_mask(conds[:i] + conds[i + 1 :])) / exposed - 1.0 >= nu
        ]
        return tuple(keep)

    assert simultaneous(space, rule) == ()  # the flaw the pinned sequential rule avoids
    assert len(S.effective_rule(space, rule).conditions) == 1


def test_single_condition_covering_nearly_everyone_is_vacuous_and_gives_empty_k() -> None:
    space = _vac_space()
    eff = S.effective_rule(space, [C("weak", "eq", 1)])
    assert eff.conditions == ()
    truth = (C("weak", "eq", 1),)
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    res = only(S.score(space, [target], [], [cand("A", [C("weak", "eq", 1)])]))
    assert res["effective_conditions"] == []
    assert res["specific_targets_by_theta"]["0.50"] is None  # K empty: never Specific


def test_weak_true_condition_is_dropped_from_k_but_exact_uses_the_raw_bijection() -> None:
    space = _vac_space()
    truth = (C("a", "eq", 1), C("b", "eq", 1), C("weak", "eq", 1))
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    both = only(S.score(space, [target], [], [cand("A", list(truth))]))
    assert C("weak", "eq", 1).render() in both["vacuous_dropped"]
    assert both["exact_targets"] == ["T1"]  # raw bijection holds; K is only for condition checks
    assert both["per_target"]["T1"]["cp"] == 1.0  # dropping a true condition cannot lower Cp
    # candidate that LACKS the weak true condition: near-exact must never silently become exact
    near = only(S.score(space, [target], [], [cand("B", [C("a", "eq", 1), C("b", "eq", 1)])]))
    assert near["exact_targets"] == []
    assert near["exact_after_vacuity_targets"] == []


def test_candidate_equal_to_truth_plus_vacuous_extra_is_flagged_exact_after_vacuity() -> None:
    space = _vac_space()
    truth = (C("a", "eq", 1), C("b", "eq", 1))
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    res = only(S.score(space, [target], [], [cand("A", [*truth, C("z", "eq", 1)])]))
    assert res["exact_targets"] == []
    assert res["exact_after_vacuity_targets"] == ["T1"]
    assert res["specific_targets_by_theta"]["0.50"] == "T1"  # still Specific (headline is separate)
    payload = S.score(space, [target], [], [cand("A", [*truth, C("z", "eq", 1)])])
    assert payload["strata"]["core"]["exact_targets"] == []
    assert payload["strata"]["core"]["exact_after_vacuity_targets"] == ["T1"]
    assert "exact_after_vacuity (not counted): T1" in S.render_report(payload)


# ---- Exact bijection cases ----------------------------------------------------------------------
def _exact(cands_conds: list[S.CondSpec], truth: tuple[S.CondSpec, ...], **kw: float) -> bool:
    space = _vac_space()
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    const = replace(S.CONSTANTS, **kw)
    res = only(S.score(space, [target], [], [cand("A", cands_conds)], const))
    return res["exact_targets"] == ["T1"]


def test_exact_bijection_and_numeric_tolerance() -> None:
    truth = (C("a", "eq", 1), C("n", "ge", 50))
    assert _exact([C("a", "eq", 1), C("n", "ge", 50)], truth)
    assert _exact([C("n", "ge", 50), C("a", "eq", 1)], truth)  # order free
    assert _exact([C("a", "eq", 1), C("n", "ge", 54)], truth)  # ~4% of rows(t) <= eta
    assert not _exact([C("a", "eq", 1), C("n", "ge", 70)], truth)  # ~20% > eta = 0.15
    assert not _exact([C("a", "eq", 1), C("n", "lt", 50)], truth)  # wrong direction
    assert not _exact([C("a", "eq", 0), C("n", "ge", 50)], truth)  # wrong categorical value
    assert not _exact([C("a", "eq", 1)], truth)  # missing a true condition
    assert not _exact([C("a", "eq", 1), C("n", "ge", 50), C("b", "eq", 1)], truth)  # extra


def test_exact_mutation_eta_and_eps_flip_the_verdict() -> None:
    truth = (C("a", "eq", 1), C("n", "ge", 50))
    shifted = [C("a", "eq", 1), C("n", "ge", 54)]
    assert _exact(shifted, truth)
    assert not _exact(shifted, truth, eta=0.0)  # numeric tolerance component
    assert not _exact(shifted, truth, eps_x=0.0)  # exposure-equivalence component


def test_exact_is_undefined_for_targets_without_an_in_language_form() -> None:
    space = _vac_space()
    truth = (C("a", "eq", 1),)
    target = S.Target("L1", "out_of_language", truth, space.rule_mask(truth), None)
    res = S.score(space, [target], [], [cand("A", list(truth))])
    assert res["strata"]["out_of_language"]["exact_defined_targets"] == []
    assert "Exact (strict diagnostic)" not in S.render_report(res)


# ---- trap must stay trap ------------------------------------------------------------------------
def test_promoted_genuine_t03_stays_a_promoted_trap() -> None:
    conds = [C("acquisition_channel", "eq", "paid_search"), C("discount_rate", "ge", 0.03)]
    res = run(conds, OK, readiness="shadow_policy")
    assert only(res)["trap_hits"] == ["T03"]
    assert res["safety"]["any_trap_promoted"] is True
    assert res["safety"]["trap_promoted"]["T03"] is True


@pytest.mark.parametrize(
    "conds",
    [
        [C("manager", "eq", "Manager 2"), C("destination", "eq", "Tokyo")],
        [C("payment_method", "eq", "bank_transfer"), C("supplier", "eq", "BlueWing")],
        [C("acquisition_channel", "eq", "paid_search"), C("discount_rate", "ge", 0.05)],
        [C("supplier", "eq", "Atlas"), C("manager", "eq", "Manager 2")],
    ],
)
def test_literal_plus_non_pattern_feature_stays_a_trap(conds: list[S.CondSpec]) -> None:
    rec = only(run(conds))
    assert rec["trap_hits"] != []
    assert rec["in_pool"] is False


def test_exposure_equivalent_reformulation_is_a_trap_hit() -> None:
    rng = random.Random(3)
    n = 3000
    t = [int(rng.random() < 0.3) for _ in range(n)]
    f = [x if rng.random() > 0.02 else 1 - x for x in t]  # ~2% disagreement: J >= 0.9
    space = S.RowSpace({"t": t, "f": f})
    trap = S.Trap("TX", C("t", "eq", 1))
    res = only(S.score(space, [], [trap], [cand("A", [C("f", "eq", 1)])]))
    assert res["trap_literal_hits"] == []
    assert res["trap_equivalence_hits"] == ["TX"]
    assert res["trap_hits"] == ["TX"]
    mutated = only(
        S.score(
            space, [], [trap], [cand("A", [C("f", "eq", 1)])], replace(S.CONSTANTS, theta_t=0.999)
        )
    )
    assert mutated["trap_hits"] == []  # the theta_T component matters


def test_exemption_needs_a_target_that_contains_the_literal() -> None:
    # exact P01 rule is Specific but has no trap literal: nothing to exempt, nothing flagged
    rec = only(
        run(
            [
                C("booking_lead_days", "lt", 23.0),
                C("discount_rate", "ge", 0.12),
                C("supplier", "eq", "BlueWing"),
            ]
        )
    )
    assert rec["trap_hits"] == [] and rec["exempted_traps"] == []
    assert rec["specific_targets_by_theta"]["0.50"] == "P01"


def test_exemption_covers_unscoreable_targets_p05_exact_rule() -> None:
    conds = [
        C("manager", "eq", "Manager 4"),
        C("manual_exception", "eq", True),
        C("customer_price_eur", "ge", 3500),
    ]
    rec = only(run(conds))
    assert rec["exempted_traps"] == [{"trap": "T05", "pattern": "P05"}]
    # P05 is unscoreable (n=23): it can exempt the trap but is never credited in the headline
    assert "P05" not in rec["covers_targets"]
    assert rec["specific_targets_by_theta"]["0.50"] is None


def test_exact_p04_rule_with_calendar_month_is_not_exempt_when_exposure_is_too_small() -> None:
    conds = [
        C("supplier", "eq", "Atlas"),
        C("trip_duration_days", "ge", 14),
        C("booking_month", "eq", 12),
    ]
    rec = only(run(conds))
    assert rec["per_target"]["P04"]["j_e"] < 0.5  # one month of three: recall about a third
    assert rec["trap_hits"] == ["T02"]  # strict: geometric closeness never cancels trap semantics


# ---- mutation checks, one per rule component ----------------------------------------------------
def test_mutation_theta_j_component() -> None:
    assert only(run(P01_DILUTE))["specific_targets_by_theta"]["0.50"] == "P01"  # J 0.5035
    strict = only(run(P01_DILUTE, const=replace(S.CONSTANTS, theta_j=0.51)))
    assert strict["specific_targets_by_theta"]["0.51"] is None  # primary threshold moved to 0.51
    assert strict["specific_targets_by_theta"]["0.50"] == "P01"  # the 0.50 sensitivity column
    # J 0.5035 is not enough at 0.7: sensitivity column, independent of the constant
    assert only(run(P01_DILUTE))["specific_targets_by_theta"]["0.70"] is None


def test_mutation_validation_clause_component(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = only(run(P01_DILUTE, "descriptive"))
    assert rec["specific_targets_by_theta"]["0.50"] is None
    monkeypatch.setattr(S.Candidate, "validated", property(lambda self: True))
    assert only(run(P01_DILUTE, "descriptive"))["specific_targets_by_theta"]["0.50"] == "P01"
    # ... and the strict trap exemption reads the same clause
    assert only(run(P06_PRECISE, "descriptive"))["trap_hits"] == []


def test_mutation_nu_component() -> None:
    conds = [
        C("installments", "ge", 3),
        C("customer_type", "eq", "new"),
        C("acquisition_channel", "eq", "paid_search"),
        C("booking_lead_days", "lt", 400.0),
    ]
    base = only(run(conds))
    assert base["vacuous_dropped"] == ["booking_lead_days lt 400.0"]
    assert base["per_target"]["P03"]["cp"] == 1.0
    assert base["specific_targets_by_theta"]["0.50"] == "P03"
    off = only(run(conds, const=replace(S.CONSTANTS, nu=0.0)))
    assert off["vacuous_dropped"] == []
    # `booking_lead_days` is not a P03 feature: kept as effective it is a spurious condition
    assert off["per_target"]["P03"]["cp"] == 0.75
    assert off["specific_targets_by_theta"]["0.50"] is None


def test_mutation_metric_specific_component_breaks_the_exemption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert only(run(P06_PRECISE))["trap_hits"] == []
    monkeypatch.setattr(S, "metric_specific", lambda pm, tj, tp: False)
    assert only(run(P06_PRECISE))["trap_hits"] == ["T04"]


def test_mutation_credit_rule_ties_go_to_the_lowest_target_id() -> None:
    space = S.RowSpace({"f": [1] * 80 + [0] * 20})
    truth = (C("f", "eq", 1),)
    mask = space.rule_mask(truth)
    targets = [
        S.Target("T2", "core", truth, mask, truth),
        S.Target("T1", "core", truth, mask, truth),
    ]
    rec = only(S.score(space, targets, [], [cand("A", list(truth))]))
    assert rec["credited_target"] == "T1"
    assert rec["specific_metric_also_holds_for"] == ["T2"]  # reported, never double credited
    assert sum(v is not None for v in rec["specific_targets_by_theta"].values()) == 3


def test_scoreability_thresholds_are_the_contract_and_engine_floors() -> None:
    assert S.CONSTANTS.min_exposed_records == DEFAULT_THRESHOLDS.min_exposed_records
    assert S.CONSTANTS.min_dev_n == DiscoveryConfig().min_n
    space = S.RowSpace({"f": [1] * 49 + [0] * 951})
    truth = (C("f", "eq", 1),)
    small = S.Target("S", "core", truth, space.rule_mask(truth), truth)
    res = S.score(space, [small], [], [cand("A", list(truth))])
    assert res["strata"]["core"]["scoreable"] == []
    assert res["strata"]["core"]["unscoreable"] == ["S"]


def test_adr107_constants_are_frozen() -> None:
    c = S.CONSTANTS
    assert (c.theta_j, c.theta_p, c.nu, c.eta, c.eps_x, c.theta_t, c.coverage_recall) == (
        0.50,
        1.00,
        0.05,
        0.15,
        0.10,
        0.90,
        0.5,
    )
    assert S.SENSITIVITY_THETAS == (0.3, 0.5, 0.7)


# ---- invariants ---------------------------------------------------------------------------------
def test_specific_may_exceed_coverage_at_theta_03_and_is_reported_not_stopped() -> None:
    f = [10.0] * 40 + [5.0] * 60 + [0.0] * 900
    space = S.RowSpace({"f": f})
    truth = (C("f", "ge", 5.0),)
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    res = S.score(space, [target], [], [cand("A", [C("f", "ge", 10.0)])])
    core = res["strata"]["core"]
    assert core["coverage_targets"] == []  # recall 0.4
    assert core["specific_targets"]["0.30"] == ["T1"]  # J 0.4 >= 0.3
    assert core["specific_targets"]["0.50"] == []
    assert core["specific_not_in_coverage"]["0.30"] == ["T1"]


def test_specific_subset_of_coverage_is_enforced_only_from_theta_half() -> None:
    def stratum(key: str) -> S.StratumResult:
        return S.StratumResult("core", ["T"], [], [], {key: ["T"]}, [], [], [])

    with pytest.raises(S.InvariantViolation):
        S._check_invariants({"core": stratum("0.50")}, [], (0.5,))
    with pytest.raises(S.InvariantViolation):
        S._check_invariants({"core": stratum("0.70")}, [], (0.7,))
    S._check_invariants({"core": stratum("0.30")}, [], (0.3,))  # legitimate arithmetic


def test_a_candidate_credited_twice_is_a_scorer_bug() -> None:
    rec = S.CandidateRecord(
        "X",
        [],
        OK,
        "hold",
        True,
        1,
        [],
        [],
        [],
        [],
        [],
        [],
        True,
        ["T1"],
        False,
        "T1",
        0.6,
        {},
        {"0.30": "T2"},
        [],
        [],
        [],
    )
    with pytest.raises(S.InvariantViolation):
        S._check_invariants({}, [rec], (0.3,))


def test_trap_excluded_candidates_are_never_credited() -> None:
    rec = only(run(TEN_SHAPES["bare Atlas"][0]))
    assert rec["in_pool"] is False and rec["covers_targets"] == []


# ---- strata and output --------------------------------------------------------------------------
def test_strata_are_reported_separately_and_never_blended() -> None:
    res = run(
        [
            C("installments", "ge", 3),
            C("customer_type", "eq", "new"),
            C("acquisition_channel", "eq", "paid_search"),
        ]
    )
    strata = res["strata"]
    assert strata["declared_overlap"]["specific_targets"]["0.50"] == ["P03"]
    assert strata["core"]["specific_targets"]["0.50"] == []  # a declared-overlap hit never leaks
    assert set(strata) == {"core", "declared_overlap", "out_of_language"}
    assert "specific_targets" not in res  # no top-level blended headline
    text = S.render_report(res)
    assert "/ core / Specific" in text and "/ declared_overlap / Specific" in text


def test_rendered_output_uses_the_adr107_wording_and_never_a_bare_ratio() -> None:
    res = run(P06_PRECISE)
    text = S.render_report(res)
    assert "benchmark targets reached predictive_association under the v2 recovery contract" in text
    assert "recovered by the product" not in text
    assert "not promotion" in text
    S.assert_no_bare_ratio(text)


@pytest.mark.parametrize("bad", ["7/7", "recall 2/7 done", "Specific: 3/3 recovered"])
def test_bare_ratios_are_rejected(bad: str) -> None:
    with pytest.raises(S.InvariantViolation):
        S.assert_no_bare_ratio(bad)
    S.assert_no_bare_ratio("7/7 benchmark targets are covered (soft)")


def test_all_covered_headline_is_still_labelled_and_warns_on_broad_candidates() -> None:
    ctx = real_ctx()
    broad = cand("BROAD", [C("booking_lead_days", "lt", 240.0), C("discount_rate", "ge", 0.0)])
    res = S.score(ctx.space, ctx.targets, ctx.traps, [broad])
    text = S.render_report(res)
    assert "BROAD" in text and "broad candidates present" in text
    assert "Specific: 0/" in text


def test_parse_rule_and_row_semantics() -> None:
    assert S.parse_rule("a=x AND b>=3 AND c<23.5 AND m IN [1,2,12] AND e=true") == (
        C("a", "eq", "x"),
        C("b", "ge", 3),
        C("c", "lt", 23.5),
        C("m", "in", (1, 2, 12)),
        C("e", "eq", True),
    )
    with pytest.raises(ValueError, match="unparsable"):
        S.parse_rule("a ~ 3")
    space = S.RowSpace({"v": [None, 1, True, 5.0, "s"]})
    assert space.cond_mask(C("v", "ge", 1)) == 0b01010  # bool and str never match numerics
    assert space.cond_mask(C("v", "eq", True)) == 0b00100
    assert space.cond_mask(C("v", "in", (1, 5.0))) == 0b01010
