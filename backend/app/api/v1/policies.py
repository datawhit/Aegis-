"""Policy CRUD (admin only).

Phase 2: list + create are sufficient for demo + tests. Update / delete
ship in Phase 3 alongside the policy UI.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.core.policy.dsl import PolicyDSLError, context_from_request, evaluate_match
from app.models.policy import Policy, PolicyEffect as ORMPolicyEffect
from app.models.user import UserRole
from app.schemas.policy import PolicyCreate, PolicyList, PolicyRead

router = APIRouter()


def _require_admin(user) -> None:  # type: ignore[no-untyped-def]
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )


@router.get("/policies", response_model=PolicyList)
async def list_policies(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> PolicyList:
    _require_admin(current_user)
    rows = (
        await session.execute(
            select(Policy).order_by(Policy.priority.desc(), Policy.name.asc())
        )
    ).scalars().all()
    return PolicyList(items=[PolicyRead.model_validate(p) for p in rows])


@router.post("/policies", response_model=PolicyRead, status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: PolicyCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> PolicyRead:
    _require_admin(current_user)

    # Sanity-check the DSL by running it against a stub context. If the
    # expression can't even evaluate, reject at write time — we don't want
    # a broken policy entering the priority chain.
    try:
        evaluate_match(
            body.match,
            context_from_request(
                {
                    "action_class": "revoke_user_sessions",
                    "blast_radius": 1,
                    "ai_confidence": 0.9,
                    "incident_severity": "high",
                    "has_rollback_plan": True,
                }
            ),
        )
    except PolicyDSLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid DSL: {exc}",
        ) from exc

    existing = (
        await session.execute(select(Policy).where(Policy.name == body.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"policy with name {body.name!r} already exists",
        )

    policy = Policy(
        name=body.name,
        description=body.description,
        priority=body.priority,
        effect=ORMPolicyEffect(body.effect),
        match=body.match,
        constraints=body.constraints,
        is_active=body.is_active,
    )
    session.add(policy)
    await session.flush()
    await session.commit()
    return PolicyRead.model_validate(policy)
