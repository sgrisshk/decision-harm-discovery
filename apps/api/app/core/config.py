from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql+psycopg://policy:policy@localhost:5432/policy"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_upload_bytes: int = 10 * 1024 * 1024
    ingestion_storage_root: Path = Path("data/raw")

    @field_validator("database_url")
    @classmethod
    def require_postgres(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use PostgreSQL")
        return value

    @model_validator(mode="after")
    def production_safety(self) -> "Settings":
        if self.app_env in {"staging", "production"}:
            if "policy:policy@" in self.database_url:
                raise ValueError(
                    "default database credentials are forbidden outside development/test"
                )
            if any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("CORS_ORIGINS must use HTTPS outside development/test")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
