"""Render markdown tables from oracle-rates.json (and the v1-only replication). Read-only."""

from __future__ import annotations

import json
from pathlib import Path

D = Path(__file__).resolve().parent


def cell(e: dict, key: str) -> str:
    v = e.get(key)
    if not v:
        return "n/a"
    lo, hi = v["wilson95"]
    return f"{v['k']}/{v['n']} [{lo:.2f}-{hi:.2f}]"


def table(path: Path, ids: list[str]) -> str:
    r = json.loads(path.read_text())
    rows = ["| id | n_aff (median) | n_dev (median) | exact-cond oracle @36,791 | ideal-atom oracle @36,791 | grid-projection oracle @36,791 | proj. J (median) | cond oracle @60,000 | cond oracle @26,213 |", "|---|---|---|---|---|---|---|---|---|"]
    for pid in ids:
        e = r[pid]
        pj = e.get("projection_jaccard_median")
        rows.append(
            f"| {pid} | {e.get('n_affected_median', '-')} | {e.get('n_dev_median', '-')} | {cell(e, 'cond@36791')} | {cell(e, 'atom@36791')} | {cell(e, 'proj@36791')} | {'-' if pj is None else f'{pj:.2f}'} | {cell(e, 'cond@60000')} | {cell(e, 'cond@26213')} |"
        )
    return "\n".join(rows)


def traps(path: Path) -> str:
    r = json.loads(path.read_text())
    rows = ["| trap (bare literal) | reaches predictive @36,791 | level-2 gate failures (of 30) |", "|---|---|---|"]
    for t in ("T01", "T02", "T03", "T04", "T05"):
        e = r[t]["trap@36791"]
        rows.append(f"| {t} | {e['k']}/{e['n']} | {e['gate_failures']} |")
    return "\n".join(rows)


ids_v2 = ["P01", "P02", "P03", "P04", "P06", "P08", "P09", "N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "O1", "O2"]
out = "### v2 prototype (with candidate targets), seeds 1001-1030\n\n" + table(D / "oracle-rates.json", ids_v2)
out += "\n\n### v1-only replication (prototype with NO v2 targets), same seeds\n\n" + table(
    D / "oracle-rates-v1only-no-targets.json", ["P01", "P02", "P03", "P04", "P06", "P08", "P09"]
)
out += "\n\n### Bare-literal trap rules (prototype with targets)\n\n" + traps(D / "oracle-rates.json")
(D / "oracle-tables.md").write_text(out + "\n")
print(out)
