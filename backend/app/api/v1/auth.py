"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, IdentityDep, SessionDep
from app.core.audit import Actor, get_audit_logger
from app.core.identity.base import Credentials
from app.schemas.token import TokenResponse
from app.schemas.user import LoginRequest, UserRead

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: SessionDep,
    identity: IdentityDep,
) -> TokenResponse:
    user = await identity.authenticate(
        session,
        Credentials(kind="password", email=body.email.lower(), password=body.password),
    )
    if user is None:
        # Audit failed attempts too. Actor is INTEGRATION because we don't
        # have an authenticated user — the attempted email lives in payload.
        await get_audit_logger().record(
            session,
            actor=Actor.system(label="auth.login"),
            action="auth.login_failed",
            resource_type="user",
            resource_id=None,
            payload={"email": body.email.lower()},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    token = await identity.issue_token(user)
    await get_audit_logger().record(
        session,
        actor=Actor.user(user.id, label=user.email),
        action="auth.login_succeeded",
        resource_type="user",
        resource_id=user.id,
        payload={"auth_provider": user.auth_provider.value
                 if hasattr(user.auth_provider, "value") else str(user.auth_provider)},
    )
    await session.commit()
    return TokenResponse(
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        token_type=token.token_type,
        expires_at=token.expires_at,
    )


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(current_user)
