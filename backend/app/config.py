"""Centralized configuration via Pydantic Settings.

All env access lives here. Modules elsewhere import `settings`; nothing else
should read `os.environ` directly. This keeps the surface for misconfiguration
small and gives us one place to add validation, secret loading, or Vault.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AEGIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    env: Literal["local", "ci", "dev", "staging", "prod"] = "local"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # --- DB ---
    database_url: str = Field(
        default="postgresql+asyncpg://aegis:aegis@postgres:5432/aegis"
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://aegis:aegis@postgres:5432/aegis"
    )

    # --- Redis / Celery ---
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # --- Identity ---
    identity_provider: Literal["local_jwt", "okta"] = "local_jwt"
    jwt_secret: str = "dev-only-replace-me"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 3600
    jwt_refresh_ttl_seconds: int = 60 * 60 * 24 * 30

    # --- Okta (stub) ---
    okta_domain: str = ""
    okta_client_id: str = ""
    okta_client_secret: str = ""

    # --- AI providers (unused in Phase 0) ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_ai_provider: Literal["anthropic", "openai"] = "anthropic"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env in {"staging", "prod"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
