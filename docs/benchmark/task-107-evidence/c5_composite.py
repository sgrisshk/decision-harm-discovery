"""TASK-107 Phase 2b: C5 (literal-plus-confounder composites) re-run on the COMPOSITE v2 draw, for
reference only (ADR-108 Decision 2; not a gate). Same protocol as `c5_check.py` (imported, not
modified); only the draw builder is replaced by the composite (`synthetic_benchmark_v2_targets`).

  batch --seeds A B --dir DIR --procs N        (writes DIR/seed-S.json)
  rates --dir DIR --out FILE
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import c5_check as c5  # noqa: E402
import v2_common as vc  # noqa: E402


def _build_composite(seed: int, draw: str, work: Path) -> Path:
    del draw
    return vc.build_draw(seed, work, vc.tg.DESIGNS).root


def run_one(seed: int, out: Path) -> None:
    c5._build = _build_composite  # type: ignore[assignment]  # pyright: ignore[reportPrivateUsage]
    with tempfile.TemporaryDirectory():
        c5.run_seed(seed, "v2clean", out)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("batch")
    b.add_argument("--seeds", type=int, nargs=2, required=True)
    b.add_argument("--dir", type=Path, required=True)
    b.add_argument("--procs", type=int, default=10)
    r = sub.add_parser("rates")
    r.add_argument("--dir", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "batch":
        todo = [
            (s, a.dir / f"seed-{s}.json")
            for s in range(a.seeds[0], a.seeds[1] + 1)
            if not (a.dir / f"seed-{s}.json").exists()
        ]
        with Pool(a.procs) as pool:
            pool.starmap(run_one, todo)
    else:
        c5.rates(a.dir, a.out)


if __name__ == "__main__":
    main()
