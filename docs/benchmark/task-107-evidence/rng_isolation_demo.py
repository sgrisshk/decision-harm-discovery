"""TASK-107 Phase 2a - RNG isolation demonstration (FC2/FC3 prerequisite; no engine, no validation).

Full-size (10,000 rows) draws from `policy_analytics.synthetic_benchmark_v2` with (a) no targets,
(b) one TEST-ONLY target, (c) three TEST-ONLY targets (one very broad and strong). The targets are
fixtures for this demonstration, NOT v2 targets (those are designed in Phase 2b). Reports sha256 of
the covariate columns per (seed, target set), equality with the v1 generator's covariates, and how
many rows' outcomes changed (expected: only rows that satisfy a target predicate).
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics import synthetic_benchmark as v1  # noqa: E402
from policy_analytics import synthetic_benchmark_v2 as v2  # noqa: E402

SEEDS = (1001, 1002, 1003, 1004, 1005, 20260813)


def _t1(cov: v2.Covariates) -> bool:
    return bool(cov["customer_segment"] == "corporate" and cov["destination"] == "Lisbon")


def _t2(cov: v2.Covariates) -> bool:
    return bool(cov["booking_month"] in (1, 2, 12) and cov["installments"] >= 2)


def _t3(cov: v2.Covariates) -> bool:
    return bool(cov["acquisition_channel"] == "referral")


ONE = (v2.TargetSpec("X1", "test", _t1, v2.TargetDose(410.0, 1.05, 0.75)),)
THREE = (
    *ONE,
    v2.TargetSpec("X2", "test", _t2, v2.TargetDose(300.0, 0.75, 0.5)),
    v2.TargetSpec("X3", "test", _t3, v2.TargetDose(600.0, 2.5, 1.5)),
)


def cov_hash(draw: v2.V2Draw) -> str:
    h = hashlib.sha256()
    for row in draw.rows:
        h.update("|".join(repr(row[c]) for c in v2.COVARIATE_COLUMNS).encode())
        h.update(b"\n")
    return h.hexdigest()


def main() -> None:
    out: dict[str, object] = {"row_count": v1.ROW_COUNT, "seeds": {}}
    for seed in SEEDS:
        cfg = v2.V2Config(seed=seed)
        none, one, three = (v2.generate_v2(cfg, t) for t in ((), ONE, THREE))
        rng = random.Random(seed)
        v1_rows = [v1._generate_row(i, rng, cfg.v1_config())[0] for i in range(cfg.row_count)]  # pyright: ignore[reportPrivateUsage]
        v1_hash = hashlib.sha256()
        for row in v1_rows:
            v1_hash.update("|".join(repr(row[c]) for c in v2.COVARIATE_COLUMNS).encode())
            v1_hash.update(b"\n")
        touched = {i for ids in three.memberships.values() for i in ids}
        changed = sum(
            any(a[c] != b[c] for c in v2.OUTCOME_COLUMNS)
            for a, b in zip(none.rows, three.rows, strict=True)
        )
        unaffected_identical = all(
            a == b
            for a, b in zip(none.rows, three.rows, strict=True)
            if str(a["booking_id"]) not in touched
        )
        out["seeds"][str(seed)] = {  # type: ignore[index]
            "covariate_sha256_v1_generator": v1_hash.hexdigest(),
            "covariate_sha256_v2_no_targets": cov_hash(none),
            "covariate_sha256_v2_one_target": cov_hash(one),
            "covariate_sha256_v2_three_targets": cov_hash(three),
            "all_equal": len({v1_hash.hexdigest(), cov_hash(none), cov_hash(one), cov_hash(three)}) == 1,
            "target_members": {k: len(v) for k, v in three.memberships.items()},
            "rows_with_changed_outcome_columns": changed,
            "rows_touched_by_a_target": len(touched),
            "rows_untouched_are_fully_identical_to_no_target_run": unaffected_identical,
        }
    path = Path(__file__).resolve().parent / "rng-isolation-demo.json"
    path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for seed, e in out["seeds"].items():  # type: ignore[union-attr]
        print(seed, e["all_equal"], e["rows_with_changed_outcome_columns"], "/", e["rows_touched_by_a_target"], e["rows_untouched_are_fully_identical_to_no_target_run"])  # type: ignore[index]


if __name__ == "__main__":
    main()
