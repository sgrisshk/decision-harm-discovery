"""TASK-107 Phase 1 - Jaccard sanity analysis (READ-ONLY, DOCUMENT/SPEC SUPPORT).

Reads the committed v1 benchmark (dataset `travel-bookings-analytical-v1.1.0`, ground truth
`synthetic_data/evaluation/hidden_ground_truth.json`) and the committed `TASK-103` run1/run2
candidate files. Changes no generator, scorer, engine, gate, threshold or v1 artefact. Writes one
JSON file and prints a summary. It does NOT run the engine on anything.

Purpose (ADR-106 Decision 3): before a "specific recovery" definition is proposed, quantify what
Jaccard >= 0.5 does and does not distinguish, on the real ground-truth rules and on real candidate
shapes. Two different Jaccards are in circulation and BOTH are analysed:

  * condition-set Jaccard (the ADR-106 example: 2 of 4 true conditions and nothing extra vs 3
    correct + 2 spurious, both 0.5) - a syntactic measure over the sets of conditions;
  * exposure-set Jaccard (`TASK-106`'s "specific": Jaccard(candidate exposed rows, pattern affected
    rows) >= 0.5) - a semantic measure over rows.

Pre-declared parameters (fixed in the pre-registration commit BEFORE this script was first run):
  NU            = 0.05  a condition is VACUOUS in a rule if removing it grows the exposure by < 5%
  THETA_J       = 0.5   headline exposure-Jaccard threshold analysed (sensitivity 0.3, 0.7)
  Condition "match": same feature AND the two conditions' own row sets are nested (one contains the
  other) - i.e. same direction / same categorical value; thresholds are NOT compared (exposure
  Jaccard carries threshold sloppiness).
  Eligibility proxy for enumerated rules: 40 <= exposure <= 0.40 * rows (full cohort).
No candidate definition is selected by how it grades the v0.6.2 engine's candidates; those are
scored only AFTER, as illustration (invariant 5).
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import hashlib
import itertools
import json
import statistics
import sys
from pathlib import Path
from typing import Any, cast

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))

import polars as pl  # noqa: E402
from diagnose_oracle_decomposition import (  # noqa: E402
    TrueCondition,
    _frame_mask,
    _render_rule,
    _rule_expr_local,
    parse_true_rule,
    true_condition_expr,
)
from evaluate_benchmark import _scoreable_pattern_ids  # noqa: E402
from policy_analytics.discovery.engine import Condition, DiscoveryConfig, _atoms  # noqa: E402
from policy_analytics.validation.apply import load_analytical_frame  # noqa: E402

ROOT = REPOSITORY / "synthetic_data/analytical/travel-bookings-analytical-v1.1.0"
GT_PATH = REPOSITORY / "synthetic_data/evaluation/hidden_ground_truth.json"
RUN1 = REPOSITORY / "docs/benchmark/task-103-evidence/run1/candidates.json"
RUN2 = REPOSITORY / "docs/benchmark/task-103-evidence/run2/candidates.json"
OUT = Path(__file__).resolve().parent / "jaccard-sanity-raw.json"

NU = 0.05
THETAS = (0.3, 0.5, 0.7)
MIN_N = 40
MAX_SUPPORT = 0.40


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pc(x: int) -> int:
    return x.bit_count()


class Ctx:
    def __init__(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        frame = load_analytical_frame(ROOT)
        booking = frame["booking_date"]
        if booking.dtype == pl.String:
            booking = booking.str.to_date()
        frame = frame.with_columns(booking.dt.month().alias("booking_month"))
        self.frame = frame
        self.n = frame.height
        self.full = (1 << self.n) - 1
        self.gt = json.loads(GT_PATH.read_text(encoding="utf-8"))
        ids = cast("list[str]", frame["booking_id"].to_list())
        index_of = {b: i for i, b in enumerate(ids)}
        dev = frame.filter(pl.col("split_label") == "development")
        dev_ids = frozenset(cast("list[str]", dev["booking_id"].to_list()))
        self.scoreable = list(_scoreable_pattern_ids(self.gt, dev_ids))
        self.affected: dict[str, int] = {}
        self.true_conds: dict[str, tuple[TrueCondition, ...]] = {}
        self.true_rows: dict[str, list[int]] = {}
        for p in self.gt["patterns"]:
            pid = str(p["id"])
            packed = 0
            for b in p["affected_booking_ids"]:
                packed |= 1 << index_of[b]
            self.affected[pid] = packed
            tcs = parse_true_rule(str(p["rule"]))
            self.true_conds[pid] = tcs
            self.true_rows[pid] = [self.tc_mask(tc) for tc in tcs]
        timing = {n: str(m["classification"]) for n, m in manifest["feature_timing"].items()}
        feats = tuple(
            n
            for n in frame.columns
            if timing.get(n) == "DECISION_TIME" and n not in {"booking_date", "travel_date"}
        )
        self.atoms = _atoms(dev, feats, DiscoveryConfig())
        self._mask_cache: dict[Condition, int] = {}
        for a in self.atoms:
            self.cmask(a)

    def tc_mask(self, tc: TrueCondition) -> int:
        return _frame_mask(self.frame, true_condition_expr(tc))

    def cmask(self, c: Condition) -> int:
        if c not in self._mask_cache:
            self._mask_cache[c] = _frame_mask(self.frame, _rule_expr_local((c,)))
        return self._mask_cache[c]

    def rmask(self, rule: tuple[Condition, ...]) -> int:
        m = self.full
        for c in rule:
            m &= self.cmask(c)
        return m


def nested(a: int, b: int) -> bool:
    inter = a & b
    return inter == a or inter == b


def analyse(ctx: Ctx, pid: str, rule: tuple[Condition, ...]) -> dict[str, Any]:
    """Every metric for one (rule, pattern) pair. `rule` may be any conjunction (engine language
    or not). Vacuity is evaluated on the full cohort."""
    aff = ctx.affected[pid]
    tcs = ctx.true_conds[pid]
    e_full = ctx.rmask(rule)
    n_e = pc(e_full)
    inter = pc(e_full & aff)
    union = pc(e_full | aff)
    n_a = pc(aff)
    # vacuity / effective conditions
    effective: list[Condition] = []
    for i, c in enumerate(rule):
        rest = rule[:i] + rule[i + 1 :]
        e_rest = ctx.rmask(rest) if rest else ctx.full
        grow = pc(e_rest) / n_e if n_e else 1.0
        if grow - 1.0 >= NU:  # removing c grows exposure by >= NU  => c is load-bearing
            effective.append(c)
    matched_true: set[int] = set()
    matched_cand = 0
    for c in effective:
        cm = ctx.cmask(c)
        hit = False
        for ti, tc in enumerate(tcs):
            if tc.feature == c.feature and nested(cm, ctx.true_rows[pid][ti]):
                matched_true.add(ti)
                hit = True
        matched_cand += int(hit)
    k = len(effective)
    m_t = len(matched_true)
    cp = matched_cand / k if k else 0.0
    cr = m_t / len(tcs)
    cond_j = m_t / (k + len(tcs) - m_t) if (k + len(tcs) - m_t) else 0.0
    return {
        "n_exposed": n_e,
        "recall": inter / n_a if n_a else 0.0,
        "precision": inter / n_e if n_e else 0.0,
        "jaccard_exposure": inter / union if union else 0.0,
        "n_conditions": len(rule),
        "n_effective_conditions": k,
        "cond_precision": cp,
        "cond_recall": cr,
        "jaccard_conditions": cond_j,
        "vacuous_conditions": [
            _render_rule((c,)) for c in rule if c not in effective
        ],
    }


def quadrant(m: dict[str, Any]) -> str:
    r, p = m["recall"], m["precision"]
    if r >= 0.9 and p < 0.75:
        return "dilute (superset)"
    if p >= 0.9 and r < 0.75:
        return "partial (subset)"
    return "balanced"


# --- definitions compared (functions of the metric dict) ---------------------------------------
def d_lenient(m: dict[str, Any]) -> bool:
    return m["recall"] >= 0.5


def d_jexp(theta: float) -> Any:
    return lambda m: m["jaccard_exposure"] >= theta


def d_jcond(m: dict[str, Any]) -> bool:
    return m["jaccard_conditions"] >= 0.5


def d_condpr(m: dict[str, Any]) -> bool:
    return m["cond_precision"] >= 2 / 3 and m["cond_recall"] >= 2 / 3


def d_jexp_cp(theta: float) -> Any:
    return lambda m: m["jaccard_exposure"] >= theta and m["cond_precision"] >= 1.0


def d_recall_prec(m: dict[str, Any]) -> bool:
    return m["recall"] >= 0.5 and m["precision"] >= 0.3


DEFS: dict[str, Any] = {
    "lenient_recall>=0.5": d_lenient,
    "exposure_J>=0.3": d_jexp(0.3),
    "exposure_J>=0.5": d_jexp(0.5),
    "exposure_J>=0.7": d_jexp(0.7),
    "condition_set_J>=0.5": d_jcond,
    "cond_precision>=2/3_and_cond_recall>=2/3": d_condpr,
    "exposure_J>=0.5_and_cond_precision==1": d_jexp_cp(0.5),
    "exposure_J>=0.3_and_cond_precision==1": d_jexp_cp(0.3),
    "recall>=0.5_and_precision>=0.3": d_recall_prec,
}


def verdicts(m: dict[str, Any]) -> dict[str, bool]:
    return {name: bool(fn(m)) for name, fn in DEFS.items()}


def cond_from_true(tc: TrueCondition) -> Condition | None:
    """A true condition as an engine-typed Condition, only when it is a plain column condition."""
    op = {">=": "ge", "<": "lt", "=": "eq"}.get(tc.operator)
    if op is None or isinstance(tc.value, tuple):
        return None
    return Condition(tc.feature, cast(Any, op), cast(Any, tc.value))


def true_subset_mask(ctx: Ctx, pid: str, idx: tuple[int, ...]) -> int:
    m = ctx.full
    for i in idx:
        m &= ctx.true_rows[pid][i]
    return m


def metrics_for_mask(
    ctx: Ctx, pid: str, e: int, conds_desc: list[tuple[str, str]], spurious: int, n_true_kept: int
) -> dict[str, Any]:
    """Metrics for a fixture built from true-condition subsets (+ spurious atoms) where the
    condition semantics are known by construction (no vacuity pruning: fixtures are constructed
    load-bearing or reported as such)."""
    aff = ctx.affected[pid]
    inter, union, n_a, n_e = pc(e & aff), pc(e | aff), pc(aff), pc(e)
    k = n_true_kept + spurious
    tlen = len(ctx.true_conds[pid])
    return {
        "recall": inter / n_a,
        "precision": inter / n_e if n_e else 0.0,
        "jaccard_exposure": inter / union if union else 0.0,
        "n_exposed": n_e,
        "n_true_kept": n_true_kept,
        "n_spurious": spurious,
        "jaccard_conditions": n_true_kept / (k + tlen - n_true_kept),
        "cond_precision": n_true_kept / k if k else 0.0,
        "cond_recall": n_true_kept / tlen,
    }


def summarize(vals: list[float]) -> dict[str, float] | None:
    if not vals:
        return None
    s = sorted(vals)
    return {
        "n": len(s),
        "min": s[0],
        "p25": s[len(s) // 4],
        "median": statistics.median(s),
        "p75": s[(3 * len(s)) // 4],
        "max": s[-1],
    }


def main() -> None:
    ctx = Ctx()
    out: dict[str, Any] = {
        "inputs": {
            "dataset": str(ROOT.relative_to(REPOSITORY)),
            "ground_truth_sha256": sha256(GT_PATH),
            "run1_candidates_sha256": sha256(RUN1),
            "run2_candidates_sha256": sha256(RUN2),
            "n_rows": ctx.n,
            "n_atoms": len(ctx.atoms),
            "scoreable": ctx.scoreable,
        },
        "parameters": {"NU": NU, "THETAS": THETAS, "MIN_N": MIN_N, "MAX_SUPPORT": MAX_SUPPORT},
        "abstract_adr106_pair": {},
        "fixtures": {},
        "enumeration": {},
        "candidates": {},
        "trap_fixtures": {},
    }

    # ---- (0) the ADR-106 arithmetic, exactly ------------------------------------------------
    def cj(kept: int, extra: int, tlen: int) -> float:
        return kept / (kept + extra + tlen - kept)

    out["abstract_adr106_pair"] = {
        "true_conditions": 4,
        "shape_A": {"correct": 2, "spurious": 0, "condition_set_J": cj(2, 0, 4),
                    "cond_precision": 1.0, "cond_recall": 0.5},
        "shape_B": {"correct": 3, "spurious": 2, "condition_set_J": cj(3, 2, 4),
                    "cond_precision": 3 / 5, "cond_recall": 0.75},
    }

    # ---- (1) fixtures built from the real ground-truth rules ---------------------------------
    spurious_pool: dict[str, list[Condition]] = {}
    for pid in ctx.scoreable:
        tfeats = {tc.feature for tc in ctx.true_conds[pid]}
        spurious_pool[pid] = [a for a in ctx.atoms if a.feature not in tfeats]
    for pid in ctx.scoreable:
        tcs = ctx.true_conds[pid]
        tlen = len(tcs)
        aff = ctx.affected[pid]
        fx: dict[str, Any] = {
            "true_rule": str(next(p for p in ctx.gt["patterns"] if p["id"] == pid)["rule"]),
            "n_affected": pc(aff),
            "exact_rule_exposure_equals_affected": pc(true_subset_mask(ctx, pid, tuple(range(tlen))) ^ aff) == 0,
            "subsets": [],
            "subset_plus_one_spurious": {},
            "subset_plus_two_spurious": {},
        }
        by_cj: dict[str, list[float]] = {}
        # proper and full subsets of the true conditions, nothing extra
        for size in range(1, tlen + 1):
            for idx in itertools.combinations(range(tlen), size):
                e = true_subset_mask(ctx, pid, idx)
                m = metrics_for_mask(ctx, pid, e, [], 0, size)
                m["kept"] = [tcs[i].render() for i in idx]
                fx["subsets"].append(m)
                by_cj.setdefault(f"{m['jaccard_conditions']:.4f}", []).append(
                    m["jaccard_exposure"]
                )
        # subset + spurious atoms (spurious = grid atoms on features NOT in the rule)
        for n_spur in (1, 2):
            agg: dict[str, list[dict[str, Any]]] = {}
            for size in range(1, tlen + 1):
                for idx in itertools.combinations(range(tlen), size):
                    base = true_subset_mask(ctx, pid, idx)
                    pool = spurious_pool[pid]
                    if n_spur == 1:
                        combos = [(a,) for a in pool]
                    else:
                        combos = [
                            (a, b) for a, b in itertools.combinations(pool, 2) if a.feature != b.feature
                        ]
                    for combo in combos:
                        e = base
                        for a in combo:
                            e &= ctx.cmask(a)
                        if pc(e) == 0:
                            continue
                        m = metrics_for_mask(ctx, pid, e, [], n_spur, size)
                        key = f"kept={size}/spurious={n_spur}"
                        agg.setdefault(key, []).append(m)
                        by_cj.setdefault(f"{m['jaccard_conditions']:.4f}", []).append(
                            m["jaccard_exposure"]
                        )
            target = fx["subset_plus_one_spurious" if n_spur == 1 else "subset_plus_two_spurious"]
            for key, rows in agg.items():
                target[key] = {
                    "n_rules": len(rows),
                    "condition_set_J": rows[0]["jaccard_conditions"],
                    "exposure_J": summarize([r["jaccard_exposure"] for r in rows]),
                    "share_exposure_J>=0.5": sum(r["jaccard_exposure"] >= 0.5 for r in rows) / len(rows),
                }
        fx["exposure_J_spread_at_each_condition_set_J"] = {
            k: summarize(v) for k, v in sorted(by_cj.items())
        }
        out["fixtures"][pid] = fx

    # ---- (2) exhaustive enumeration of engine-expressible rules (depth <= 3) -----------------
    by_feature: dict[str, list[Condition]] = {}
    for a in ctx.atoms:
        by_feature.setdefault(a.feature, []).append(a)
    feats = sorted(by_feature)
    rules: list[tuple[Condition, ...]] = []
    for depth in (1, 2, 3):
        for fset in itertools.combinations(feats, depth):
            for combo in itertools.product(*(by_feature[f] for f in fset)):
                rules.append(tuple(combo))
    masks = [ctx.rmask(r) for r in rules]
    eligible = [
        i for i, m in enumerate(masks) if MIN_N <= pc(m) <= MAX_SUPPORT * ctx.n
    ]
    out["enumeration"]["n_rules_all"] = len(rules)
    out["enumeration"]["n_rules_eligible_proxy"] = len(eligible)
    per_pattern: dict[str, Any] = {}
    examples: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for pid in ctx.scoreable:
        aff = ctx.affected[pid]
        n_a = pc(aff)
        rows_hi: list[dict[str, Any]] = []
        n_theta = {str(t): 0 for t in THETAS}
        cj_hi = 0
        cj_hi_lowj = 0
        cj_hi_lowj_ex: list[dict[str, Any]] = []
        for i in eligible:
            e = masks[i]
            inter = pc(e & aff)
            if inter == 0:
                continue
            union = pc(e | aff)
            j = inter / union
            need_full = j >= min(THETAS) or inter / n_a >= 0.5
            if not need_full:
                # condition-set J needs the full analysis only if it could be >= 0.5; cheap prefilter
                continue
            m = analyse(ctx, pid, rules[i])
            for t in THETAS:
                if m["jaccard_exposure"] >= t:
                    n_theta[str(t)] += 1
            if m["jaccard_exposure"] >= 0.3:
                m["rule"] = _render_rule(rules[i])
                rows_hi.append(m)
            if m["jaccard_conditions"] >= 0.5:
                cj_hi += 1
                if m["jaccard_exposure"] < 0.1:
                    cj_hi_lowj += 1
                    if len(cj_hi_lowj_ex) < 3:
                        cj_hi_lowj_ex.append({"rule": _render_rule(rules[i]), **m})
        hi5 = [r for r in rows_hi if r["jaccard_exposure"] >= 0.5]
        quad: dict[str, int] = {}
        for r in hi5:
            quad[quadrant(r)] = quad.get(quadrant(r), 0) + 1
        per_pattern[pid] = {
            "n_true_conditions": len(ctx.true_conds[pid]),
            "rules_with_exposure_J>=theta": n_theta,
            "among_J>=0.5": {
                "n": len(hi5),
                "quadrant_counts": quad,
                "with_spurious_effective_condition(Cp<1)": sum(r["cond_precision"] < 1.0 for r in hi5),
                "missing_a_true_condition(Cr<1)": sum(r["cond_recall"] < 1.0 for r in hi5),
                "cond_recall_values": sorted({round(r["cond_recall"], 3) for r in hi5}),
            },
            "among_J>=0.3": {
                "n": len(rows_hi),
                "with_spurious_effective_condition(Cp<1)": sum(r["cond_precision"] < 1.0 for r in rows_hi),
                "quadrant_counts": {
                    q: sum(quadrant(r) == q for r in rows_hi)
                    for q in ("dilute (superset)", "partial (subset)", "balanced")
                },
            },
            "rules_with_condition_set_J>=0.5_and_exposure_J<0.1": cj_hi_lowj,
            "rules_with_condition_set_J>=0.5_total_among_recall_or_J_prefilter": cj_hi,
            "condition_set_J>=0.5_but_exposure_J<0.1_examples": cj_hi_lowj_ex,
        }
        # illustrative same-J different-failure-mode pair inside [0.5, 0.56]
        band = [r for r in hi5 if r["jaccard_exposure"] < 0.56]
        examples[pid] = {
            "dilute": sorted([r for r in band if quadrant(r) == "dilute (superset)"], key=lambda r: r["rule"])[:2],
            "partial": sorted([r for r in band if quadrant(r) == "partial (subset)"], key=lambda r: r["rule"])[:2],
            "best_by_exposure_J": sorted(rows_hi, key=lambda r: -r["jaccard_exposure"])[:5],
        }
    out["enumeration"]["per_pattern"] = per_pattern
    out["enumeration"]["examples"] = examples

    # ---- (3) real candidate shapes and named fixtures ----------------------------------------
    def score_rule(label: str, rule: tuple[Condition, ...], extra: dict[str, Any] | None = None) -> dict[str, Any]:
        per: dict[str, Any] = {}
        e = ctx.rmask(rule)
        for pid in ctx.scoreable:
            m = analyse(ctx, pid, rule)
            per[pid] = {**m, "verdicts": verdicts(m)}
        best = max(ctx.scoreable, key=lambda p: per[p]["jaccard_exposure"])
        return {
            "label": label,
            "rule": _render_rule(rule),
            "n_exposed": pc(e),
            "lenient_matches": [p for p in ctx.scoreable if per[p]["recall"] >= 0.5],
            "best_pattern_by_exposure_J": best,
            "per_pattern": per,
            **(extra or {}),
        }

    def cond(f: str, o: str, v: Any) -> Condition:
        return Condition(f, cast(Any, o), v)

    named = {
        "hist_P06_precise (v0.2-v0.5 shape, TASK-106 D2)": (
            cond("booking_lead_days", "lt", 23.0),
            cond("destination", "eq", "Tokyo"),
            cond("payment_method", "eq", "bank_transfer"),
        ),
        "P01_grid_projection (TASK-106 5.1)": (
            cond("booking_lead_days", "lt", 23.0),
            cond("discount_rate", "ge", 0.12),
            cond("supplier", "eq", "BlueWing"),
        ),
        "P01_two_of_three (v0.6.2 CAND-005 shape)": (
            cond("booking_lead_days", "lt", 23.0),
            cond("discount_rate", "ge", 0.12),
        ),
        "P06_broad_lenient (v0.2-v0.5 shape)": (
            cond("booking_lead_days", "lt", 23.0),
            cond("discount_rate", "ge", 0.05),
        ),
    }
    named_out = [score_rule(k, v) for k, v in named.items()]
    out["candidates"]["named_shapes"] = named_out

    def load_cands(path: Path, label: str) -> list[dict[str, Any]]:
        doc = json.loads(path.read_text(encoding="utf-8"))
        res = []
        for c in doc["candidates"]:
            rule = tuple(
                Condition(x["feature"], x["operator"], x["value"]) for x in c["conditions"]
            )
            res.append(score_rule(f"{label}:{c['candidate_id']}", rule))
        return res

    out["candidates"]["task103_run1_v0.6.2"] = load_cands(RUN1, "run1")
    out["candidates"]["task103_run2_v0.6.2"] = load_cands(RUN2, "run2")

    # historical P01 J~0.504 shape: search the enumeration for the P01 rules with J in [0.500, 0.508]
    p01 = ctx.affected["P01"]
    hist_p01: list[dict[str, Any]] = []
    for i in eligible:
        e = masks[i]
        inter = pc(e & p01)
        if inter == 0:
            continue
        j = inter / pc(e | p01)
        if 0.500 <= j <= 0.508:
            hist_p01.append({"rule": _render_rule(rules[i]), "jaccard_exposure": j})
    out["candidates"]["enumerated_P01_rules_with_exposure_J_0.500_to_0.508"] = hist_p01

    # TASK-108 section 3 vacuous-threshold shapes and bare traps
    t108 = {
        "bank_transfer AND lead<400": (cond("payment_method", "eq", "bank_transfer"), cond("booking_lead_days", "lt", 400.0)),
        "bank_transfer AND lead<60": (cond("payment_method", "eq", "bank_transfer"), cond("booking_lead_days", "lt", 60.0)),
        "paid_search AND installments>=1": (cond("acquisition_channel", "eq", "paid_search"), cond("installments", "ge", 1.0)),
        "paid_search AND customer_type=new": (cond("acquisition_channel", "eq", "paid_search"), cond("customer_type", "eq", "new")),
        "paid_search AND installments>=3 AND discount>=0.03": (
            cond("acquisition_channel", "eq", "paid_search"),
            cond("installments", "ge", 3.0),
            cond("discount_rate", "ge", 0.03),
        ),
        "Atlas AND trip_duration>=1": (cond("supplier", "eq", "Atlas"), cond("trip_duration_days", "ge", 1.0)),
        "manual_exception AND price>=0": (cond("manual_exception", "eq", True), cond("customer_price_eur", "ge", 0.0)),
        "bare bank_transfer": (cond("payment_method", "eq", "bank_transfer"),),
        "bare paid_search": (cond("acquisition_channel", "eq", "paid_search"),),
        "bare Atlas": (cond("supplier", "eq", "Atlas"),),
        "paid_search AND discount>=0.03 (TASK-073 genuine T03)": (
            cond("acquisition_channel", "eq", "paid_search"),
            cond("discount_rate", "ge", 0.03),
        ),
    }
    out["trap_fixtures"] = [score_rule(k, v) for k, v in t108.items()]

    # exact GT rules (real thresholds) as candidates, for the exact-form check
    exact_out = []
    for pid in ctx.scoreable:
        conds = [cond_from_true(tc) for tc in ctx.true_conds[pid]]
        if all(c is not None for c in conds):
            exact_out.append(score_rule(f"exact_{pid}", tuple(cast(list[Condition], conds))))
    out["candidates"]["exact_rules_column_expressible"] = exact_out

    OUT.write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print("enumerated rules:", out["enumeration"]["n_rules_all"], "eligible proxy:", out["enumeration"]["n_rules_eligible_proxy"])
    for pid, v in out["enumeration"]["per_pattern"].items():
        print(pid, v["rules_with_exposure_J>=theta"], v["among_J>=0.5"]["n"], v["among_J>=0.5"]["quadrant_counts"],
              "Cp<1:", v["among_J>=0.5"]["with_spurious_effective_condition(Cp<1)"],
              "Cr<1:", v["among_J>=0.5"]["missing_a_true_condition(Cr<1)"])


if __name__ == "__main__":
    main()
