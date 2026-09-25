"""TASK-107 Phase 2b design stage: sd of `contribution_margin_eur` on a design-check seed with no
targets vs. all designs (contract-free, engine-free). Usage: margin_sd_check.py SEED"""

from __future__ import annotations

import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_common as vc  # noqa: E402

tg = vc.tg
seed = int(sys.argv[1])
for label, designs in (("no targets", ()), ("all designs", tg.DESIGNS)):
    with tempfile.TemporaryDirectory() as tmp:
        draw = vc.build_draw(seed, Path(tmp), designs)
        y = draw.frame["contribution_margin_eur"].to_list()
        canc = draw.frame["cancellation"].to_list()
        print(
            label,
            "sd margin",
            round(statistics.pstdev(y)),
            "mean",
            round(statistics.fmean(y)),
            "cancel rate",
            round(sum(map(bool, canc)) / len(canc), 3),
        )
