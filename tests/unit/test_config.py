import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_rejects_non_postgres_database() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite:///local.db")


def test_rejects_default_credentials_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://policy:policy@db:5432/policy",
            cors_origins=["https://app.example.com"],
        )
