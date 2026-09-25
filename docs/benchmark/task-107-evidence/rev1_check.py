"""TASK-107 Revision 1 read-only check (STATISTICS, 2026-09-25).

Reads only committed raw JSON. Compares the with-targets prototype draws (`oracle-raw/`) with the
no-target v1-only draws (`oracle-raw-v1only-no-targets/`) at the same seeds: number of seeds where
`n_affected` differs, and Fisher exact p for the cond-oracle pass-rate shift.
Predictions were committed first (`rev1-predictions.md`).
Run: `python3 docs/benchmark/task-107-evidence/rev1_check.py`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
WITH_T = HERE / "oracle-raw"
NO_T = HERE / "oracle-raw-v1only-no-targets"
FOUR = ["P01", "P02", "P03", "P06"]
ALL = ["P01", "P02", "P03", "P04", "P06", "P09"]


def fisher_two_sided(a: int, n1: int, b: int, n2: int) -> float:
    """Two-sided Fisher exact p for a/n1 vs b/n2 (sum of tables with prob <= observed)."""
    k = a + b
    lo, hi = max(0, k - n2), min(k, n1)

    def pmf(x: int) -> float:
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n1 + n2, k)

    p_obs = pmf(a)
    return min(1.0, sum(pmf(x) for x in range(lo, hi + 1) if pmf(x) <= p_obs * (1 + 1e-9)))


def main() -> None:
    diff = {p: 0 for p in ALL}
    total = {p: 0 for p in ALL}
    for f in sorted(WITH_T.glob("seed-*.json")):
        a = json.loads(f.read_text())
        b = json.loads((NO_T / f.name).read_text())
        for p in ALL:
            if p in a["info"] and p in b["info"]:
                total[p] += 1
                diff[p] += a["info"][p]["n_affected"] != b["info"][p]["n_affected"]
    four_d = sum(diff[p] for p in FOUR)
    four_t = sum(total[p] for p in FOUR)
    print(
        "n_affected differs (with targets vs no targets), per pattern:",
        {p: f"{diff[p]}/{total[p]}" for p in ALL},
    )
    print(
        f"four patterns {FOUR}: {four_d}/{four_t}; "
        f"all six: {sum(diff.values())}/{sum(total.values())}"
    )
    s1001 = {
        p: (
            json.loads((WITH_T / "seed-1001.json").read_text())["info"][p]["n_affected"],
            json.loads((NO_T / "seed-1001.json").read_text())["info"][p]["n_affected"],
        )
        for p in FOUR
    }
    print("seed 1001 n_affected (with targets, no targets):", s1001)

    rw = json.loads((HERE / "oracle-rates.json").read_text())
    rn = json.loads((HERE / "oracle-rates-v1only-no-targets.json").read_text())
    for p in ["P01", "P03", "P06"]:
        ew = next(v for k, v in _flat(rw, p, "cond@36791"))
        en = next(v for k, v in _flat(rn, p, "cond@36791"))
        pv = fisher_two_sided(en["k"], en["n"], ew["k"], ew["n"])
        print(
            f"{p} cond oracle @36791: no-targets {en['k']}/{en['n']} vs "
            f"with-targets {ew['k']}/{ew['n']}; Fisher two-sided p = {pv:.4f}"
        )


def _flat(rates: dict, pid: str, key: str):
    node = rates.get(pid) if pid in rates else rates.get("patterns", {}).get(pid)
    if node is None:
        for v in rates.values():
            if isinstance(v, dict) and pid in v:
                node = v[pid]
                break
    yield key, node[key]


if __name__ == "__main__":
    main()
