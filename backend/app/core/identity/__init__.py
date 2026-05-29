"""Identity provider abstraction.

`get_identity_provider()` is the DI entrypoint — callers should depend on it
rather than instantiating providers directly. The concrete impl is chosen
by `AEGIS_IDENTITY_PROVIDER`.
"""

from app.config import settings
from app.core.identity.base import (
    Credentials,
    IdentityProvider,
    Token,
    TokenClaims,
)
from app.core.identity.local_jwt import LocalJWTIdentityProvider
from app.core.identity.okta_stub import OktaIdentityProvider

__all__ = [
    "Credentials",
    "IdentityProvider",
    "Token",
    "TokenClaims",
    "get_identity_provider",
]


def get_identity_provider() -> IdentityProvider:
    match settings.identity_provider:
        case "local_jwt":
            return LocalJWTIdentityProvider()
        case "okta":
            return OktaIdentityProvider()
        case other:
            raise ValueError(f"Unknown identity provider: {other!r}")
