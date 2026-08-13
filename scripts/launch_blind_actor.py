"""Launch an isolated shell with only the issued blind workspace mounted."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--image", default="python:3.12.11-slim")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not (workspace / "BLIND_MANIFEST.json").is_file():
        raise SystemExit("workspace must contain an issued BLIND_MANIFEST.json")
    repository = Path(__file__).resolve().parents[1]
    if workspace == repository or repository in workspace.parents:
        raise SystemExit("blind workspace must be outside the repository")
    command = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--tty",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--volume",
        f"{workspace}:/workspace:rw",
        "--workdir",
        "/workspace",
        "--env",
        "HOME=/tmp",
        args.image,
        "/bin/sh",
    ]
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
