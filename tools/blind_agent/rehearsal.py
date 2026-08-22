from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from tools.blind_agent.core import freeze, launch, prepare, resolve_image

REPOSITORY = Path(__file__).resolve().parents[2]
REHEARSAL_KEY = b"truth-free-rehearsal-key-material"


def rehearse(image: str, dataset_selector: str) -> None:
    with tempfile.TemporaryDirectory(prefix="policy-blind-rehearsal-") as raw_root:
        runs_root = Path(raw_root) / "runs"
        run_root = prepare(
            REPOSITORY,
            runs_root,
            "truth-free-rehearsal",
            REPOSITORY / "blind/allowlist.yaml",
            1729,
            REHEARSAL_KEY,
            resolve_image(image),
            "deterministic",
            None,
            dataset_selector,
        )
        launch(
            run_root,
            REHEARSAL_KEY,
            "deterministic",
            image,
            execute=True,
            provider_network=False,
            repository=REPOSITORY,
            allowlist=REPOSITORY / "blind/allowlist.yaml",
            dataset_selector=dataset_selector,
        )
        freeze(run_root, REHEARSAL_KEY)
    print("BLIND_REHEARSAL_VALID")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()
    rehearse(args.image, args.dataset)


if __name__ == "__main__":
    main()
