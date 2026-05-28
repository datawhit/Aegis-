"""Local JWT identity provider — HS256, users table, bcrypt passwords."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.identity.base import (
    Credentials,
    IdentityProvider,
    InvalidTokenError,
    Token,
    TokenClaims,
)
from app.models.user import User

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plaintext: str) -> str:
    return _pwd.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    return _pwd.verify(plaintext, hashed)


class LocalJWTIdentityProvider(IdentityProvider):
    async def authenticate(
        self, session: AsyncSession, credentials: Credentials
    ) -> User | None:
        if credentials.kind != "password":
            return None
        if not credentials.email or not credentials.password:
            return None

        result = await session.execute(
            select(User).where(User.email == credentials.email.lower())
        )
        user = result.scalar_one_or_none()
        if user is None or not user.is_active or not user.hashed_password:
            return None
        if not verify_password(credentials.password, user.hashed_password):
            return None
        return user

    async def issue_token(self, user: User) -> Token:
        now = datetime.now(UTC)
        access_exp = now + timedelta(seconds=settings.jwt_access_ttl_seconds)
        refresh_exp = now + timedelta(seconds=settings.jwt_refresh_ttl_seconds)

        access_payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "auth_provider": user.auth_provider.value
            if hasattr(user.auth_provider, "value")
            else str(user.auth_provider),
            "iat": int(now.timestamp()),
            "exp": int(access_exp.timestamp()),
            "type": "access",
        }
        refresh_payload = {
            "sub": str(user.id),
            "iat": int(now.timestamp()),
            "exp": int(refresh_exp.timestamp()),
            "type": "refresh",
        }

        access = jwt.encode(access_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        refresh = jwt.encode(refresh_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return Token(
            access_token=access,
            refresh_token=refresh,
            expires_at=access_exp,
        )

    async def verify_token(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
        except JWTError as exc:
            raise InvalidTokenError("invalid or expired token") from exc

        if payload.get("type") != "access":
            raise InvalidTokenError("not an access token")

        try:
            return TokenClaims(
                user_id=uuid.UUID(payload["sub"]),
                email=payload["email"],
                role=payload["role"],
                auth_provider=payload["auth_provider"],
                issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
            )
        except (KeyError, ValueError) as exc:
            raise InvalidTokenError("malformed token claims") from exc
