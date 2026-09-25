"""TASK-107 Phase 2b: the PRE-DECLARED, BOUNDED dose-selection procedure (design stage only).

Runs on the design-check seeds ONLY (never on calibration, acceptance or final seeds), with the
contract-free Welch-t power proxy of `design_checks.py`; no contract function, no engine.
For each design (fixed rule, fixed ladder = effect structure), starting at the lowest rung:
  core_candidate / declared_overlap: keep the FIRST rung with proxy t_mean >= T_MEAN and t_min >= T_MIN
  challenge_candidate:               keep the FIRST rung with proxy t_mean >= T_BORDER
Composite effects couple targets, so the whole composite is re-evaluated after every change, for at
most MAX_ROUNDS rounds; a design still failing at its top rung is reported `unreachable` (kept out
of the Core list by the pre-registration, never re-tuned by hand).
Usage: design_dose_select.py SPEC_JSON SEED_LO SEED_HI OUT_JSON
SPEC_JSON: [{"id", "rule", "ladder", "class", "trap_literal"?}]
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_common as vc  # noqa: E402
from design_checks import welch_t  # noqa: E402

import polars as pl  # noqa: E402

tg = vc.tg
T_MEAN, T_MIN, T_BORDER, MAX_ROUNDS = 7.0, 5.8, 5.0, 12


def proxies(designs: tuple[Any, ...], seeds: range) -> dict[str, list[float]]:
    tg.DESIGNS = designs
    out: dict[str, list[float]] = {d.target_id: [] for d in designs}
    for seed in seeds:
        with tempfile.TemporaryDirectory(prefix=f"ds-{seed}-") as tmp:
            draw = vc.build_draw(seed, Path(tmp), designs)
            y = draw.frame["contribution_margin_eur"].cast(pl.Float64).to_list()
            dev_idx = [i for i in range(len(y)) if draw.space.dev_mask >> i & 1]
            for d in designs:
                mask = draw.masks[d.target_id]
                member = {i for i in dev_idx if mask >> i & 1}
                out[d.target_id].append(
                    welch_t([y[i] for i in member], [y[i] for i in dev_idx if i not in member])
                )
    return out


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text())
    seeds = range(int(sys.argv[2]), int(sys.argv[3]) + 1)
    rung = {s["id"]: 0 for s in spec}
    log: list[dict[str, Any]] = []
    for round_no in range(1, MAX_ROUNDS + 1):
        designs = tuple(
            tg.TargetDesign(
                s["id"], s["rule"], tg.LADDERS[s["ladder"]][rung[s["id"]]], s["class"],
                s.get("trap_literal"),
            )
            for s in spec
        )
        ts = proxies(designs, seeds)
        changed: list[str] = []
        row: dict[str, Any] = {"round": round_no, "targets": {}}
        for s in spec:
            t = ts[s["id"]]
            mean, low = statistics.fmean(t), min(t)
            ok = mean >= T_BORDER if s["class"] == "challenge_candidate" else (
                mean >= T_MEAN and low >= T_MIN
            )
            top = rung[s["id"]] == len(tg.LADDERS[s["ladder"]]) - 1
            row["targets"][s["id"]] = {
                "dose": tg.LADDERS[s["ladder"]][rung[s["id"]]],
                "t_mean": round(mean, 2),
                "t_min": round(low, 2),
                "ok": ok,
                "unreachable": (not ok) and top,
            }
            if not ok and not top:
                rung[s["id"]] += 1
                changed.append(s["id"])
        log.append(row)
        print(
            f"round {round_no}:",
            {k: (v["dose"], v["t_mean"], v["t_min"], "ok" if v["ok"] else "BUMP") for k, v in row["targets"].items()},
            flush=True,
        )
        if not changed:
            break
    final = [
        {**s, "dose": tg.LADDERS[s["ladder"]][rung[s["id"]]]} for s in spec
    ]
    Path(sys.argv[4]).write_text(json.dumps({"final": final, "log": log}, indent=1) + "\n")


if __name__ == "__main__":
    main()
