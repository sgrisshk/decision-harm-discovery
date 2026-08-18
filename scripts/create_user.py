"""Create an internal staff account (`TASK-053`).

No self-serve signup endpoint exists on purpose — accounts are created only through this CLI, run
by someone who already has database access. Password is entered interactively via `getpass` so it
never lands in shell history or process listings.

Usage: `uv run python scripts/create_user.py <email> <display name>`
"""

from __future__ import annotations

import sys
from getpass import getpass
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "apps/api"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from app.auth.security import hash_password  # noqa: E402
from app.db.models import UserModel  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

MIN_PASSWORD_LENGTH = 12


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <email> <display name>", file=sys.stderr)
        raise SystemExit(2)
    email = sys.argv[1].strip().lower()
    display_name = sys.argv[2].strip()

    password = getpass("Password: ")
    confirm = getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        raise SystemExit(1)

    with SessionLocal() as session:
        user = UserModel(
            email=email, password_hash=hash_password(password), display_name=display_name
        )
        session.add(user)
        session.commit()
        print(f"Created user {user.email} ({user.id}).")


if __name__ == "__main__":
    main()
