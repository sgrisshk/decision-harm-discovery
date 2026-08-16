from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .core import (
    create_signing_key,
    freeze,
    launch,
    load_signing_key,
    prepare,
    resolve_image,
    verify,
)

REPOSITORY = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(prog="blind-agent")
    parser.add_argument(
        "command",
        choices=("init-key", "issue", "prepare", "verify", "launch", "shell", "freeze", "status"),
    )
    parser.add_argument("--run", required=True)
    parser.add_argument(
        "--runs-root", type=Path, default=Path(tempfile.gettempdir()) / "policy-blind-runs"
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path(tempfile.gettempdir()) / "policy-blind-evaluator/signing.key",
    )
    parser.add_argument("--allowlist", type=Path, default=REPOSITORY / "blind/allowlist.yaml")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--agent", choices=("deterministic", "shell"), default="deterministic")
    parser.add_argument("--model")
    parser.add_argument("--image", default="policy-blind-agent:local")
    parser.add_argument("--network", choices=("none", "provider"), default="none")
    args = parser.parse_args()
    run_root = args.runs_root.resolve() / args.run
    if args.command == "init-key":
        print(create_signing_key(args.key_file, REPOSITORY, args.runs_root))
        return
    if args.command == "status":
        print(json.dumps(json.loads((run_root / "state.json").read_text()), indent=2))
        return
    signing_key = load_signing_key(args.key_file, REPOSITORY, args.runs_root)
    if args.command in {"issue", "prepare"}:
        if args.agent == "deterministic" and args.model:
            parser.error("--model is forbidden for deterministic blind runs")
        print(
            prepare(
                REPOSITORY,
                args.runs_root,
                args.run,
                args.allowlist,
                args.seed,
                signing_key,
                resolve_image(args.image),
                args.agent,
                args.model,
            )
        )
    elif args.command == "verify":
        verify(
            run_root,
            signing_key,
            repository=REPOSITORY,
            allowlist=args.allowlist,
            check_source=True,
        )
        print("BLIND_WORKSPACE_VALID")
    elif args.command in {"launch", "shell"}:
        launch(
            run_root,
            signing_key,
            "shell" if args.command == "shell" else args.agent,
            args.image,
            model=args.model,
            provider_network=args.network == "provider",
            repository=REPOSITORY,
            allowlist=args.allowlist,
        )
    elif args.command == "freeze":
        print(freeze(run_root, signing_key))


if __name__ == "__main__":
    try:
        main()
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"BLIND_RUN_ERROR: {exc}") from None
