from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .core import freeze, launch, prepare, verify

REPOSITORY = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(prog="blind-agent")
    parser.add_argument(
        "command", choices=("prepare", "verify", "launch", "shell", "freeze", "status")
    )
    parser.add_argument("--run", required=True)
    parser.add_argument(
        "--runs-root", type=Path, default=Path(tempfile.gettempdir()) / "policy-blind-runs"
    )
    parser.add_argument("--allowlist", type=Path, default=REPOSITORY / "blind/allowlist.yaml")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--agent", choices=("external-cli", "assistant-cli", "shell"), default="external-cli")
    parser.add_argument("--image", default="policy-blind-agent:local")
    parser.add_argument("--network", choices=("none", "provider"), default="none")
    args = parser.parse_args()
    run_root = args.runs_root.resolve() / args.run
    if args.command == "prepare":
        print(prepare(REPOSITORY, args.runs_root, args.run, args.allowlist, args.seed))
    elif args.command == "verify":
        verify(run_root)
        print("BLIND_WORKSPACE_VALID")
    elif args.command in {"launch", "shell"}:
        launch(
            run_root,
            "shell" if args.command == "shell" else args.agent,
            args.image,
            provider_network=args.network == "provider",
        )
    elif args.command == "freeze":
        print(freeze(run_root))
    else:
        print(json.dumps(json.loads((run_root / "state.json").read_text()), indent=2))


if __name__ == "__main__":
    main()
