"""TASK-107 Phase 2b: write the DESIGNS tuple of `synthetic_benchmark_v2_targets.py` from a design
JSON (the `final` list of `design_dose_select.py` output, or a hand-edited list with a `dose`
field). Rewrites only the `DESIGNS: ... = (...)` block. Usage: design_emit.py DESIGNS_JSON"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "packages/analytics/src/policy_analytics/synthetic_benchmark_v2_targets.py"


def render(items: list[dict[str, str]]) -> str:
    lines = ["DESIGNS: tuple[TargetDesign, ...] = ("]
    for it in items:
        trap = f', "{it["trap_literal"]}"' if it.get("trap_literal") else ""
        lines.append(
            f'    TargetDesign("{it["id"]}", "{it["rule"]}", "{it["dose"]}", "{it["class"]}"{trap}),'
        )
    lines.append(")")
    return "\n".join(lines)


def main() -> None:
    data = json.loads(Path(sys.argv[1]).read_text())
    items = data["final"] if isinstance(data, dict) else data
    text = MODULE.read_text()
    head, sep, rest = text.partition("DESIGNS: tuple[TargetDesign, ...] = ")
    _, sep2, tail = rest.partition("\n\n\ndef rule_predicate")
    if not sep or not sep2:
        raise SystemExit("DESIGNS block markers not found")
    MODULE.write_text(head + render(items) + sep2 + tail)
    print(f"wrote {len(items)} designs")


if __name__ == "__main__":
    main()
