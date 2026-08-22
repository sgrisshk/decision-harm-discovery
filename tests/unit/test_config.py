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


def test_rejects_non_https_cors_origin_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://real:real@db:5432/policy",
            cors_origins=["http://app.example.com"],
        )


def test_rejects_wildcard_cors_origin_in_production() -> None:
    # With SameSite=None cookies (`app.auth.routes._cookie_security`), a wildcard origin
    # combined with `allow_credentials=True` (`app.main`) would be a real CSRF hole, not
    # just a spec violation — must stay impossible to configure outside development/test.
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://real:real@db:5432/policy",
            cors_origins=["*"],
        )


def test_accepts_https_cors_origin_in_production() -> None:
    settings = Settings(
        app_env="production",
        database_url="postgresql+psycopg://real:real@db:5432/policy",
        cors_origins=["https://app.example.com"],
    )
    assert settings.cors_origins == ["https://app.example.com"]
