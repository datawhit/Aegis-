"""User model — local identity store.

After Okta/SSO lands (Sprint 3+), this table continues to back service
accounts and break-glass admins. SSO users are mirrored here on first login
with `auth_provider = 'okta'`.
"""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"  # can approve / act
    REVIEWER = "reviewer"  # compliance / audit read-only (incl. signed export)
    VIEWER = "viewer"  # read-only
    SERVICE = "service"  # programmatic actor (e.g. ingestion connector)


class AuthProvider(str, enum.Enum):
    LOCAL = "local"
    OKTA = "okta"


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(256), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        default=UserRole.VIEWER,
        nullable=False,
    )
    auth_provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, name="auth_provider", native_enum=False),
        default=AuthProvider.LOCAL,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
