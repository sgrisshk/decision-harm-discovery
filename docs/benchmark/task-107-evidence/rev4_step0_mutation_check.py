"""TASK-107 Phase 2b Step 0 (ADR-108 Decision 3): scripted mutation check of the new exemption logic.

Applies each single-site mutant to a scratch copy of `benchmark_v2_scoring.py` (the real file is
restored afterwards in a `finally`), runs the scorer tests, and reports killed / survived.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "packages/analytics/src/policy_analytics/benchmark_v2_scoring.py"
MUTANTS: list[tuple[str, str, str]] = [
    (
        "exemption ignores scoreability (Rev 2 behaviour)",
        "if target.target_id in scoreable and metric_specific(",
        "if metric_specific(",
    ),
    (
        "NOT ASSESSED flag ignored by scoreability",
        "        target.assessed\n        and popcount",
        "        popcount",
    ),
    (
        "unscoreable denial labelled confirmed trap",
        "        return PROV_UNSCOREABLE",
        "        return PROV_CONFIRMED",
    ),
    (
        "missing-validation denial labelled confirmed trap",
        "        return PROV_NOT_ASSESSED",
        "        return PROV_CONFIRMED",
    ),
    (
        "exemption no longer requires validation",
        "            if cand.validated:\n                for target in bearing:",
        "            if True:\n                for target in bearing:",
    ),
    (
        "safety list omits no-exemption hits",
        "if prov in (PROV_UNSCOREABLE, PROV_NOT_ASSESSED)",
        "if prov in ()",
    ),
]


def main() -> int:
    backup = TARGET.with_suffix(".py.bak")
    shutil.copy(TARGET, backup)
    original = TARGET.read_text(encoding="utf-8")
    results: list[str] = []
    try:
        for name, old, new in MUTANTS:
            if original.count(old) != 1:
                results.append(f"SKIP  {name}: site not found exactly once")
                continue
            TARGET.write_text(original.replace(old, new, 1), encoding="utf-8")
            proc = subprocess.run(
                [
                    "uv",
                    "run",
                    "pytest",
                    "tests/analytics/test_benchmark_v2_scoring.py",
                    "-q",
                    "-x",
                    "-p",
                    "no:cacheprovider",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            results.append(f"{'KILLED  ' if proc.returncode != 0 else 'SURVIVED'} {name}")
    finally:
        shutil.copy(backup, TARGET)
        backup.unlink()
    print("\n".join(results))
    return 0 if all(r.startswith("KILLED") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
