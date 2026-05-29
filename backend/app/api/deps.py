"""Shared FastAPI dependencies (DB session, current user)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import IdentityProvider, get_identity_provider
from app.core.identity.base import InvalidTokenError
from app.db import get_session
from app.models.user import User, UserRole

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdentityDep = Annotated[IdentityProvider, Depends(get_identity_provider)]


def _role_value(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


async def get_current_user(
    session: SessionDep,
    identity: IdentityDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    try:
        claims = await identity.verify_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = (
        await session.execute(select(User).where(User.id == claims.user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _enforce_roles(user: User, allowed: set[str]) -> User:
    if _role_value(user) not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"requires one of: {', '.join(sorted(allowed))}",
        )
    return user


async def require_admin(current_user: CurrentUserDep) -> User:
    return _enforce_roles(current_user, {UserRole.ADMIN.value})


async def require_admin_or_operator(current_user: CurrentUserDep) -> User:
    return _enforce_roles(current_user, {UserRole.ADMIN.value, UserRole.OPERATOR.value})


async def require_admin_or_reviewer(current_user: CurrentUserDep) -> User:
    return _enforce_roles(current_user, {UserRole.ADMIN.value, UserRole.REVIEWER.value})


AdminDep = Annotated[User, Depends(require_admin)]
AdminOrOperatorDep = Annotated[User, Depends(require_admin_or_operator)]
AdminOrReviewerDep = Annotated[User, Depends(require_admin_or_reviewer)]
