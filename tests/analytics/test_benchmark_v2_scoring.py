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


# ---- [Rev 3] trap literal matching is by row set, not CondSpec equality --------------------------
_T03_EQ = C("acquisition_channel", "eq", "paid_search")
_T03_IN = C("acquisition_channel", "in", ("paid_search",))
_T03_COMPOSITE_TAIL = [C("installments", "ge", 3.0), C("discount_rate", "ge", 0.03)]


def test_in_form_bare_literal_is_the_same_trap_hit_as_its_eq_twin() -> None:
    eq_rec, in_rec = only(run([_T03_EQ])), only(run([_T03_IN]))
    assert eq_rec["trap_hits"] == ["T03"] and in_rec["trap_hits"] == ["T03"]
    assert in_rec["trap_literal_hits"] == ["T03"]
    assert in_rec["in_pool"] is False and in_rec["covers_targets"] == []


def test_in_form_composite_is_the_same_trap_hit_as_its_eq_twin() -> None:
    eq_rec = only(run([_T03_EQ, *_T03_COMPOSITE_TAIL]))
    in_rec = only(run([_T03_IN, *_T03_COMPOSITE_TAIL]))
    assert eq_rec["trap_hits"] == ["T03"]
    assert in_rec["trap_hits"] == eq_rec["trap_hits"]  # was [] under CondSpec equality
    for key in ("trap_literal_hits", "trap_equivalence_hits", "in_pool", "n_exposed"):
        assert in_rec[key] == eq_rec[key]


def test_in_and_eq_forms_agree_on_the_exemption_and_the_promotion_flag() -> None:
    promoted = run([_T03_IN, C("discount_rate", "ge", 0.03)], OK, readiness="shadow_policy")
    assert only(promoted)["trap_hits"] == ["T03"]
    assert promoted["safety"]["trap_promoted"]["T03"] is True
    assert only(run(P06_PRECISE))["trap_hits"] == []  # exempt stays exempt (existing verdict)
    p06_in = [C("booking_lead_days", "lt", 23.0), C("destination", "eq", "Tokyo")]
    assert only(run([*p06_in, C("payment_method", "in", ("bank_transfer",))]))["trap_hits"] == []


def test_in_condition_with_a_different_row_set_is_not_the_literal() -> None:
    wider = C("acquisition_channel", "in", ("paid_search", "partner"))
    rec = only(run([wider, C("customer_type", "eq", "new"), C("installments", "ge", 3.0)]))
    assert rec["trap_literal_hits"] == []  # a strictly wider set is not the trap literal


def test_literal_match_needs_the_same_feature_and_a_non_empty_row_set() -> None:
    space = S.RowSpace({"a": [1, 1, 0, 0] * 50, "b": [1, 1, 0, 0] * 50})  # identical row sets
    trap = S.Trap("TX", C("a", "eq", 1))
    res = only(S.score(space, [], [trap], [cand("A", [C("b", "eq", 1)])]))
    assert res["trap_literal_hits"] == []  # same rows, other feature: equivalence path only
    assert res["trap_equivalence_hits"] == ["TX"]
    empty = S.RowSpace({"a": [0] * 100})
    res = only(S.score(empty, [], [S.Trap("TE", C("a", "eq", 1))], [cand("A", [C("a", "eq", 1)])]))
    assert res["trap_literal_hits"] == []  # an empty literal matches nothing


# ---- [Rev 3] mutation tests for components that previously survived ------------------------------
def _grid_space() -> S.RowSpace:
    return S.RowSpace({"n": list(range(100)) * 10, "f": [i % 4 for i in range(1000)]})


def _nested_rows(space: S.RowSpace, a: S.CondSpec, b: S.CondSpec) -> bool:
    return S.nested(space.cond_mask(a), space.cond_mask(b))


def test_direction_compatibility_pin_kills_the_always_compatible_mutant() -> None:
    space = _grid_space()
    ge0, lt50 = C("n", "ge", 0), C("n", "lt", 50)
    assert _nested_rows(space, ge0, lt50)  # marginals ARE nested (ge 0 covers everything) ...
    assert S.conditions_match(space, ge0, lt50) is False  # ... yet the directions are incompatible
    assert S._compatible(ge0, lt50) is False
    assert S._compatible(C("f", "eq", 1), C("f", "in", (1, 2))) is True
    assert S._compatible(C("n", "ge", 1), C("f", "ge", 1)) is False  # different features
    target = S.Target("T", "core", (lt50,), space.rule_mask((lt50,)), (lt50,))
    rec = only(S.score(space, [target], [], [cand("A", [ge0, C("f", "eq", 1)])]))
    assert rec["per_target"]["T"]["cr"] == 0.0  # ge 0 never counts as matching `n < 50`


def test_nested_marginals_pin_kills_the_intersects_mutant() -> None:
    space = _grid_space()
    a, b = C("f", "in", (0, 1)), C("f", "in", (1, 2))  # overlap but neither contains the other
    assert S.popcount(space.cond_mask(a) & space.cond_mask(b)) > 0
    assert S.nested(space.cond_mask(a), space.cond_mask(b)) is False
    assert S.conditions_match(space, a, b) is False
    assert S.conditions_match(space, C("f", "eq", 1), b) is True  # nested: eq inside the in-set
    assert S.conditions_match(space, C("f", "eq", 3), C("f", "eq", 3)) is True
    assert S.conditions_match(space, C("f", "eq", 9), C("f", "eq", 9)) is False  # empty: no match
    truth = (a,)
    target = S.Target("T", "core", truth, space.rule_mask(truth), truth)
    rec = only(S.score(space, [target], [], [cand("A", [b])]))
    assert rec["per_target"]["T"]["cp"] == 0.0 and rec["per_target"]["T"]["cr"] == 0.0


def test_exact_is_restricted_to_the_trap_free_pool() -> None:
    space = _vac_space()
    truth = (C("a", "eq", 1), C("b", "eq", 1))
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    trap = S.Trap("TA", C("a", "eq", 1))
    unvalidated = S.score(space, [target], [trap], [cand("A", list(truth), None)])
    rec = only(unvalidated)
    assert rec["trap_hits"] == ["TA"] and rec["in_pool"] is False
    assert rec["exact_targets"] == [] and rec["exact_after_vacuity_targets"] == []
    assert unvalidated["strata"]["core"]["exact_targets"] == []
    exempt = only(S.score(space, [target], [trap], [cand("A", list(truth), OK)]))
    assert exempt["in_pool"] is True and exempt["exact_targets"] == ["T1"]  # exempt: in the pool


def test_exact_and_coverage_need_no_validation_so_exact_can_exceed_specific() -> None:
    space = _vac_space()
    truth = (C("a", "eq", 1), C("b", "eq", 1))
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    res = S.score(space, [target], [], [cand("A", list(truth), "descriptive")])
    core = res["strata"]["core"]
    assert core["exact_targets"] == ["T1"] and core["coverage_targets"] == ["T1"]
    assert core["specific_targets"]["0.50"] == []
    assert "can exceed Specific" in S.render_report(res)


def _dev_space(dev_rows: int, affected_rows: int = 60) -> tuple[S.RowSpace, S.Target]:
    columns = {"f": [1] * affected_rows + [0] * (1000 - affected_rows)}
    space = S.RowSpace(columns, (1 << dev_rows) - 1)
    truth = (C("f", "eq", 1),)
    return space, S.Target("T", "core", truth, space.rule_mask(truth), truth)


def test_dev_affected_floor_is_enforced_at_its_boundary() -> None:
    assert S.CONSTANTS.min_dev_n == 40
    for dev_rows, expected in ((39, False), (40, True)):
        space, target = _dev_space(dev_rows)
        res = S.score(space, [target], [], [cand("A", list(target.conditions))])
        assert (res["strata"]["core"]["scoreable"] == ["T"]) is expected, dev_rows
        assert (res["unscoreable_targets"] == []) is expected
    space, target = _dev_space(39)  # the constant is what moves the floor
    relaxed = replace(S.CONSTANTS, min_dev_n=39)
    assert S.score(space, [target], [], [], relaxed)["strata"]["core"]["scoreable"] == ["T"]
    # the exposed-records floor is independent: 49 affected rows, all in development
    space, target = _dev_space(1000, 49)
    assert S.score(space, [target], [], [])["strata"]["core"]["scoreable"] == []
    space, target = _dev_space(1000, 50)
    assert S.score(space, [target], [], [])["strata"]["core"]["scoreable"] == ["T"]


def _broad_result(n_targets: int, const: S.Constants = S.CONSTANTS) -> dict[str, Any]:
    space = S.RowSpace({"f": [1] * 100 + [0] * 900})
    truth = (C("f", "eq", 1),)
    targets = [
        S.Target(f"T{i}", "core", truth, space.rule_mask(truth) >> (i * 5) << (i * 5), truth)
        for i in range(n_targets)
    ]
    return S.score(space, targets, [], [cand("A", list(truth))], const)


def test_broad_candidate_flag_needs_broad_min_targets_covered_targets() -> None:
    assert S.CONSTANTS.broad_min_targets == 3
    assert only(_broad_result(3))["covers_targets"] == ["T0", "T1", "T2"]
    assert only(_broad_result(3))["broad"] is True
    assert only(_broad_result(2))["broad"] is False  # boundary: two covered targets are not broad
    assert only(_broad_result(2, replace(S.CONSTANTS, broad_min_targets=2)))["broad"] is True
    assert only(_broad_result(3, replace(S.CONSTANTS, broad_min_targets=4)))["broad"] is False


def test_score_runs_the_invariant_check(monkeypatch: pytest.MonkeyPatch) -> None:
    space = _vac_space()
    truth = (C("a", "eq", 1),)
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    real = S._aggregate

    def corrupt(*args: Any, **kwargs: Any) -> dict[str, S.StratumResult]:
        strata = real(*args, **kwargs)
        strata["core"].specific_targets["0.50"] = ["T1"]  # Specific outside Coverage: a bug
        strata["core"].coverage_targets = []
        return strata

    monkeypatch.setattr(S, "_aggregate", corrupt)
    with pytest.raises(S.InvariantViolation):
        S.score(space, [target], [], [cand("A", list(truth))])


# ---- [Rev 3] second mutation batch: boundaries, undefined cases and reporting ---------------------
def _stepped_space() -> S.RowSpace:
    """100 rows at n=10, 16 rows at n=5, 84 rows at n=0."""
    return S.RowSpace({"n": [10] * 100 + [5] * 16 + [0] * 84})


def test_jaccard_and_pair_metric_arithmetic_is_pinned() -> None:
    assert S.jaccard(0, 0) == 0.0  # two empty sets are not "identical"
    assert S.jaccard(0b1100, 0b0110) == pytest.approx(1 / 3)
    space = S.RowSpace({"a": [1, 1, 1, 1, 0, 0, 0, 0], "b": [1, 1, 0, 0, 1, 1, 0, 0]})
    truth = (C("a", "eq", 1), C("b", "eq", 1))
    target = S.Target("T", "core", truth, 0b00001111, truth)  # rows 0-3 affected
    eff = [C("a", "eq", 1), C("b", "eq", 0)]  # exposes rows 2, 3 : half of the target
    pm = S.pair_metrics(space, eff, space.rule_mask(eff), target)
    assert (pm.recall, pm.precision, pm.j_e) == (0.5, 1.0, 0.5)
    assert pm.cp == 0.5 and pm.cr == 0.5  # `b eq 0` is not nested with the true `b eq 1`
    assert pm.n_effective == 2 and pm.n_exposed == 2
    wide = S.pair_metrics(space, [C("a", "eq", 1)], space.rule_mask([C("a", "eq", 1)]), target)
    assert wide.cp == 1.0 and wide.cr == 0.5  # cp and cr use different denominators
    twice = [C("a", "eq", 1), C("a", "in", (1,))]  # two candidate conditions, one true condition
    dup = S.pair_metrics(space, twice, space.rule_mask(twice), target)
    assert dup.cp == 1.0 and dup.cr == 0.5  # cp = matched candidate conditions / |K|
    none = S.pair_metrics(space, [], space.full, target)
    assert none.cp == 0.0  # an empty effective rule has no condition precision


def test_metric_specific_boundaries_and_non_empty_effective_rule() -> None:
    pm = S.PairMetrics(0.6, 0.6, 0.5, 1.0, 1.0, 2, 10)
    assert S.metric_specific(pm, 0.5, 1.0)  # J exactly at theta_J counts
    assert not S.metric_specific(replace(pm, j_e=0.499), 0.5, 1.0)
    assert not S.metric_specific(replace(pm, cp=0.99), 0.5, 1.0)
    assert not S.metric_specific(replace(pm, n_effective=0, cp=0.0), 0.5, 0.0)  # K empty never
    assert S.metric_specific(replace(pm, cp=0.7), 0.5, 0.7)  # cp exactly at theta_p counts


def test_exact_bijection_pins_feature_operator_rows_and_tolerance_denominator() -> None:
    space = _stepped_space()
    ge10, ge5 = C("n", "ge", 10), C("n", "ge", 5)
    assert S.bijection_exists(space, [ge10], [ge5], 0.15)  # 16 <= 0.15 * 116, denominator is truth
    assert not S.bijection_exists(space, [ge10], [ge5], 0.13)
    twin = S.RowSpace({"a": [1, 0] * 60, "b": [1, 0] * 60, "c": [1, 1, 0, 0] * 30})
    assert not S.bijection_exists(twin, [C("b", "eq", 1)], [C("a", "eq", 1)], 0.15)  # feature
    assert not S.bijection_exists(twin, [C("a", "in", (1,))], [C("a", "eq", 1)], 0.15)  # operator
    assert not S.bijection_exists(twin, [C("a", "eq", 9)], [C("a", "eq", 9)], 0.15)  # empty truth
    wide, narrow = C("c", "in", (0, 1)), C("c", "in", (1,))
    assert not S.bijection_exists(twin, [wide], [narrow], 0.15)  # a superset is not equal rows
    assert S.bijection_exists(twin, [narrow], [narrow], 0.15)
    edge = S.RowSpace({"n": [10] * 100 + [5] * 15 + [0] * 85})
    assert S.bijection_exists(edge, [ge5], [ge10], 0.15)  # exactly eta * |rows(truth)|


def test_exact_categorical_superset_is_not_exact_even_when_exposure_is_equivalent() -> None:
    space = _vac_space()
    truth = (C("a", "eq", 1), C("b", "eq", 1), C("weak", "in", (1,)))
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    loose = [C("a", "eq", 1), C("b", "eq", 1), C("weak", "in", (0, 1))]
    assert S.popcount(space.rule_mask(loose) ^ target.affected) <= 0.1 * S.popcount(target.affected)
    rec = only(S.score(space, [target], [], [cand("A", loose)]))
    assert rec["exact_targets"] == []


def test_exact_exposure_equivalence_boundary_and_relaxed_needs_equivalence() -> None:
    truth = (C("n", "ge", 10),)
    space = _stepped_space()
    target = S.Target("T", "core", truth, space.rule_mask(truth), truth)
    over = only(S.score(space, [target], [], [cand("A", [C("n", "ge", 5)])]))
    assert over["n_exposed"] == 116 and over["exact_targets"] == []  # 16 > 0.1 * 100
    space2 = S.RowSpace({"n": [10] * 100 + [5] * 10 + [0] * 90})
    target2 = S.Target("T", "core", truth, space2.rule_mask(truth), truth)
    edge = only(S.score(space2, [target2], [], [cand("A", [C("n", "ge", 5)])]))
    assert edge["exact_targets"] == ["T"]  # exposure differs by exactly eps_x * |A|: equivalent
    vspace = _vac_space()
    vtruth = (C("a", "eq", 1), C("b", "eq", 1))
    vtarget = S.Target("T1", "core", vtruth, vspace.rule_mask(vtruth), vtruth)
    extra = [*vtruth, C("z", "eq", 1)]
    tight = replace(S.CONSTANTS, eps_x=0.0)
    rec = only(S.score(vspace, [vtarget], [], [cand("A", extra)], tight))
    assert rec["vacuous_dropped"] != [] and rec["exact_after_vacuity_targets"] == []
    assert only(S.score(vspace, [vtarget], [], [cand("A", extra)]))["exact_after_vacuity_targets"]


def test_trap_equivalence_boundary_and_literal_hits_are_not_double_reported() -> None:
    space = S.RowSpace({"t": [1] * 100 + [0] * 900, "f": [1] * 90 + [0] * 910})
    trap = S.Trap("TX", C("t", "eq", 1))
    edge = only(S.score(space, [], [trap], [cand("A", [C("f", "eq", 1)])]))
    assert edge["trap_equivalence_hits"] == ["TX"]  # J = 0.90 exactly, threshold is inclusive
    bare = only(S.score(space, [], [trap], [cand("A", [C("t", "eq", 1)])]))
    assert bare["trap_literal_hits"] == ["TX"] and bare["trap_equivalence_hits"] == []


def test_exemption_needs_the_trap_literal_inside_a_metric_matching_target() -> None:
    n = 1000
    g = [1] * 100 + [0] * (n - 100)
    t = [1] * 95 + [0] * 5 + [1] * 5 + [0] * (n - 105)  # exposure-equivalent to g AND h, J >= 0.9
    space = S.RowSpace({"g": g, "h": list(g), "t": t})
    truth = (C("g", "eq", 1), C("h", "eq", 1))
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    trap = S.Trap("TX", C("t", "eq", 1))
    rec = only(S.score(space, [target], [trap], [cand("A", list(truth), OK)]))
    assert rec["trap_equivalence_hits"] == ["TX"]
    assert rec["trap_hits"] == ["TX"]  # T1 is metric-matched but does not contain the literal
    assert rec["exempted_traps"] == [] and rec["in_pool"] is False


def test_coverage_boundary_and_unscoreable_targets_are_never_credited() -> None:
    space = S.RowSpace({"f": [1] * 100 + [0] * 900, "s": [1] * 30 + [0] * 970})
    big, small = (C("f", "eq", 1),), (C("s", "eq", 1),)
    upper_half = space.rule_mask(big) >> 50 << 50  # rows 50-99: candidate covers all of them
    assert S.popcount(upper_half) == 50
    # recall exactly 0.5: the target's 100 affected rows, of which the candidate exposes 50
    half = S.RowSpace({"f": [1] * 50 + [0] * 950})
    affected = (1 << 100) - 1
    target = S.Target("TH", "core", big, affected, big)
    assert only(S.score(half, [target], [], [cand("A", list(big))]))["covers_targets"] == ["TH"]
    below = S.RowSpace({"f": [1] * 49 + [0] * 951})
    assert only(S.score(below, [target], [], [cand("A", list(big))]))["covers_targets"] == []
    # an unscoreable target (30 rows) is neither covered, credited, also-Specific nor Exact
    t_small = S.Target("TS", "core", small, space.rule_mask(small), small)
    same = only(S.score(space, [t_small], [], [cand("A", list(small))]))
    assert same["covers_targets"] == [] and same["credited_target"] is None
    assert same["specific_metric_also_holds_for"] == [] and same["exact_targets"] == []
    assert same["per_target"]["TS"]["j_e"] == 1.0  # still measured, never counted


def test_broad_counts_covered_targets_not_scoreable_targets() -> None:
    space = S.RowSpace({"f": [1] * 100 + [0] * 900, "g": [0] * 500 + [1] * 100 + [0] * 400})
    truth_f, truth_g = (C("f", "eq", 1),), (C("g", "eq", 1),)
    fm, gm = space.rule_mask(truth_f), space.rule_mask(truth_g)
    targets = [
        S.Target("T0", "core", truth_f, fm, truth_f),
        S.Target("T1", "core", truth_f, fm >> 5 << 5, truth_f),
        S.Target("T2", "core", truth_g, gm, truth_g),
    ]
    rec = only(S.score(space, targets, [], [cand("A", list(truth_f))]))
    assert rec["covers_targets"] == ["T0", "T1"] and rec["broad"] is False


def test_strata_split_coverage_and_exact_after_vacuity_never_lists_exact_targets() -> None:
    space = S.RowSpace({"f": [1] * 100 + [0] * 900, "g": [0] * 200 + [1] * 100 + [0] * 700})
    tf, tg = (C("f", "eq", 1),), (C("g", "eq", 1),)
    targets = [
        S.Target("C1", "core", tf, space.rule_mask(tf), tf),
        S.Target("H1", "challenge", tg, space.rule_mask(tg), tg),
    ]
    both = S.score(space, targets, [], [cand("A", list(tf)), cand("B", list(tg))])
    assert both["strata"]["core"]["coverage_targets"] == ["C1"]
    assert both["strata"]["challenge"]["coverage_targets"] == ["H1"]
    # one candidate reaches T1 exactly, another only after vacuity: only the exact one is listed
    vspace = _vac_space()
    truth = (C("a", "eq", 1), C("b", "eq", 1))
    vt = S.Target("T1", "core", truth, vspace.rule_mask(truth), truth)
    res = S.score(vspace, [vt], [], [cand("A", list(truth)), cand("B", [*truth, C("z", "eq", 1)])])
    assert res["strata"]["core"]["exact_targets"] == ["T1"]
    assert res["strata"]["core"]["exact_after_vacuity_targets"] == []
    assert res["candidates"][1]["exact_after_vacuity_targets"] == ["T1"]


def test_remaining_invariants_are_enforced_by_the_check() -> None:
    def record(**over: Any) -> S.CandidateRecord:
        base: dict[str, Any] = {
            "candidate_id": "X",
            "conditions": [],
            "evidence_level": OK,
            "policy_readiness": "hold",
            "validated": True,
            "n_exposed": 1,
            "effective_conditions": [],
            "vacuous_dropped": [],
            "trap_literal_hits": [],
            "trap_equivalence_hits": [],
            "trap_hits": [],
            "exempted_traps": [],
            "in_pool": True,
            "covers_targets": [],
            "broad": False,
            "credited_target": None,
            "best_j": 0.0,
            "per_target": {},
            "specific_targets_by_theta": {"0.30": None},
            "specific_metric_also_holds_for": [],
            "exact_targets": [],
            "exact_after_vacuity_targets": [],
        }
        return S.CandidateRecord(**{**base, **over})

    S._check_invariants({}, [record()], (0.3,))
    with pytest.raises(S.InvariantViolation, match="outside"):
        S._check_invariants({}, [record(per_target={"T": {"j_e": 1.5}})], (0.3,))
    with pytest.raises(S.InvariantViolation, match="trap-excluded"):
        S._check_invariants({}, [record(in_pool=False, covers_targets=["T"])], (0.3,))
    with pytest.raises(S.InvariantViolation, match="trap-excluded"):
        S._check_invariants(
            {},
            [record(in_pool=False, specific_targets_by_theta={"0.30": "T"}, credited_target="T")],
            (0.3,),
        )
    stray = S.StratumResult("core", ["T"], [], [], {"0.99": []}, [], [], [])
    with pytest.raises(S.InvariantViolation, match="sensitivity"):
        S._check_invariants({"core": stray}, [], (0.3,))


def test_safety_flags_appeared_promoted_and_exempted_separately() -> None:
    conds = [C("acquisition_channel", "eq", "paid_search"), C("discount_rate", "ge", 0.03)]
    held = run(conds, OK, readiness="hold")
    assert held["safety"]["trap_appeared"]["T03"] is True
    assert held["safety"]["trap_promoted"]["T03"] is False  # appeared but not promoted
    assert held["safety"]["any_trap_promoted"] is False
    assert run(conds, OK, readiness="high_confidence")["safety"]["any_trap_promoted"] is True
    assert run(conds, OK, readiness="shadow_policy")["safety"]["any_trap_promoted"] is True
    exempt = run(P06_PRECISE)
    listed = exempt["safety"]["exempted_candidates_to_verify_manually"]
    assert [row["candidate_id"] for row in listed] == ["X"]
    assert exempt["safety"]["trap_appeared"]["T04"] is False  # exempt is not a genuine hit


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("predictive_association", True),
        ("adjusted_observational_association", True),
        ("quasi_causal_evidence", True),
        ("experimental_evidence", True),
        ("descriptive", False),
        ("hypothesis", False),
        (None, False),
    ],
)
def test_validated_means_predictive_association_or_above(level: str | None, expected: bool) -> None:
    assert S.Candidate("X", (), level).validated is expected


def test_render_uses_the_primary_theta_and_refuses_a_bare_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = [10.0] * 40 + [5.0] * 60 + [0.0] * 900
    space = S.RowSpace({"f": f})
    truth = (C("f", "ge", 5.0),)
    target = S.Target("T1", "core", truth, space.rule_mask(truth), truth)
    res = S.score(space, [target], [], [cand("A", [C("f", "ge", 10.0)])])
    text = S.render_report(res)
    assert "Specific: 0/1 benchmark targets" in text  # J 0.4: not Specific at the primary 0.50
    assert "theta_J=0.30: 1/1 benchmark targets" in text
    monkeypatch.setattr(S, "_ratio", lambda hit, scoreable: f"{len(hit)}/{len(scoreable)}")
    with pytest.raises(S.InvariantViolation):
        S.render_report(res)
