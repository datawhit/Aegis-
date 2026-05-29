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
    api_host: str = "0.0.0.0"  # noqa: S104 - intentional bind-all for container deployment
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # --- DB ---
    database_url: str = Field(default="postgresql+asyncpg://aegis:aegis@postgres:5432/aegis")
    database_url_sync: str = Field(default="postgresql+psycopg://aegis:aegis@postgres:5432/aegis")

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

    # --- AI providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_ai_provider: Literal["anthropic", "openai"] = "anthropic"

    # --- Ingestion secrets ---
    # Per-source HMAC secrets. Moves to DB/Vault in Phase 3 (D-10).
    ingest_secret_defender: str = "dev-defender-secret-change-me"
    ingest_replay_window_seconds: int = 300

    # --- Correlation ---
    # Sliding window for alert→incident clustering by correlation_key.
    incident_correlation_window_seconds: int = 1800

    # --- Policy ---
    # Emergency lockdown: force the always-escalate stub engine, ignoring
    # any policies in the DB. Set true if a bad policy ships to prod and
    # you need to revert to "ask a human for everything" immediately.
    policy_engine_force_stub: bool = False

    # --- Approval ---
    approval_default_ttl_seconds: int = 3600
    approval_required_role: str = "operator"

    # --- Slack ---
    slack_enabled: bool = False
    slack_webhook_url: str = ""
    slack_signing_secret: str = ""
    slack_approval_channel: str = "#aegis-approvals"

    # --- Microsoft Graph (execution connector) ---
    ms_graph_live: bool = False
    ms_graph_tenant_id: str = ""
    ms_graph_client_id: str = ""
    ms_graph_client_secret: str = ""

    # --- Audit log immutability ---
    # If set, the audit logger uses this DSN for INSERTs. The DB role
    # backing this DSN should have ONLY INSERT on audit_logs. When unset,
    # the app uses the regular pool (Phase 0 behavior).
    audit_writer_database_url: str = ""

    # --- Audit export signing (Sprint 4) ---
    # Ed25519 private key in PEM ("BEGIN PRIVATE KEY") form. When unset,
    # the export endpoint produces an unsigned receipt (a marker line with
    # `"signature": null`) — fine for local dev, fail-loud in prod via the
    # boot-time check in main.py.
    audit_export_signing_key: str = ""
    # Stable key identifier so verifiers can match the right public key
    # after rotation. Suggested format: "aegis-audit-vYYYY-MM" or a UUID.
    audit_export_signing_key_id: str = "dev-unsigned"

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
