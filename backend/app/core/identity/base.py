"""IdentityProvider protocol + transport types.

Every authentication flow in Aegis routes through this interface. The audit
log's `actor_id` is populated from `TokenClaims.user_id` — so any provider
must produce stable, comparable user IDs.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@dataclass(frozen=True)
class Credentials:
    """Authentication input. Discriminated by `kind`."""

    kind: str       # "password" | "oidc_code" | "service_token"
    email: str | None = None
    password: str | None = None
    code: str | None = None
    state: str | None = None


@dataclass(frozen=True)
class Token:
    access_token: str
    refresh_token: str | None
    token_type: str = "bearer"
    expires_at: datetime | None = None


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    email: str
    role: str
    auth_provider: str
    issued_at: datetime
    expires_at: datetime


@runtime_checkable
class IdentityProvider(Protocol):
    """Pluggable identity backend.

    Methods are async to allow remote providers (Okta) without changing
    callers. Local impls can `return await` over sync work.
    """

    async def authenticate(
        self, session: AsyncSession, credentials: Credentials
    ) -> User | None:
        """Verify credentials and return the corresponding User, or None.

        Must NOT throw on wrong-password — return None so callers can render
        a generic "invalid credentials" without leaking which field failed.
        """
        ...

    async def issue_token(self, user: User) -> Token: ...

    async def verify_token(self, token: str) -> TokenClaims:
        """Verify and decode a token. Raises `InvalidTokenError` on failure."""
        ...


class InvalidTokenError(Exception):
    """Raised by `IdentityProvider.verify_token` for any failure mode.

    Deliberately one error class — callers should not branch on subtypes
    when deciding whether to 401, and we don't want providers leaking which
    check failed."""
