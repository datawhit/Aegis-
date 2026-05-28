"""Okta identity provider — stub.

Real implementation arrives in Sprint 3+. The stub raises explicitly so a
misconfiguration (`AEGIS_IDENTITY_PROVIDER=okta` in Phase 0) fails fast and
loud rather than silently degrading to "everyone is unauthenticated".
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity.base import (
    Credentials,
    IdentityProvider,
    Token,
    TokenClaims,
)
from app.models.user import User


class OktaIdentityProvider(IdentityProvider):
    async def authenticate(
        self, session: AsyncSession, credentials: Credentials
    ) -> User | None:
        raise NotImplementedError(
            "Okta identity provider is not implemented in Phase 0. "
            "Set AEGIS_IDENTITY_PROVIDER=local_jwt."
        )

    async def issue_token(self, user: User) -> Token:
        raise NotImplementedError("Okta identity provider is not implemented in Phase 0.")

    async def verify_token(self, token: str) -> TokenClaims:
        raise NotImplementedError("Okta identity provider is not implemented in Phase 0.")
