import os
import subprocess

import pytest


def test_migrations_apply_to_empty_database() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for migration tests")
    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "base"],
        cwd="apps/api",
        check=True,
        env={**os.environ, "DATABASE_URL": database_url},
    )
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd="apps/api",
        check=True,
        env={**os.environ, "DATABASE_URL": database_url},
    )
