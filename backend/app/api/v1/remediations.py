"""Remediation actions: rollback endpoint.

Authorization (Sprint 4):

- Reversible action classes (e.g. ISOLATE_HOST, BLOCK_IP) — OPERATOR
  or ADMIN may roll back.
- Non-reversible action classes (e.g. REVOKE_USER_SESSIONS,
  FORCE_PASSWORD_RESET) — ADMIN only. The "rollback" of a non-reversible
  action is at best a compensating control; we want a senior actor on
  record. See `RemediationActionClass.is_reversible`.

Sprint 6 (R-21): every 403 denial now writes a `remediation.rollback_denied`
audit entry. The attempt itself is signal — a non-admin trying to undo a
session revocation is something a SOC manager wants to see.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, SessionDep
from app.core.audit.logger import Actor, get_audit_logger
from app.logging import get_logger
from app.models.remediation_action import RemediationAction
from app.models.user import User, UserRole
from app.schemas.remediation import RollbackRequest
from app.services.remediation_executor import (
    RemediationNotExecutableError,
    RemediationNotFoundError,
    get_remediation_executor,
)

router = APIRouter()
log = get_logger("remediation.rollback")


async def _audit_denial(
    session: AsyncSession,
    *,
    actor: User,
    action_id: uuid.UUID,
    reason_code: str,
    action_class: str | None,
    detail: str,
) -> None:
    """Record an attempted-but-denied rollback on the audit chain."""
    await get_audit_logger().record(
        session,
        actor=Actor.user(actor.id, label=actor.email),
        action="remediation.rollback_denied",
        resource_type="remediation_action",
        resource_id=action_id,
        payload={
            "reason_code": reason_code,
            "actor_role": actor.role.value if hasattr(actor.role, "value") else str(actor.role),
            "action_class": action_class,
            "detail": detail,
        },
    )
    await session.commit()


@router.post("/remediations/{action_id}/rollback")
async def rollback_remediation(
    action_id: uuid.UUID,
    body: RollbackRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> dict:
    if current_user.role not in {UserRole.ADMIN, UserRole.OPERATOR}:
        detail = "operator or admin role required to rollback remediations"
        await _audit_denial(
            session,
            actor=current_user,
            action_id=action_id,
            reason_code="role_insufficient",
            action_class=None,
            detail=detail,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    action = (
        await session.execute(select(RemediationAction).where(RemediationAction.id == action_id))
    ).scalar_one_or_none()
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"remediation action {action_id} not found",
        )

    if not action.action_class.is_reversible and current_user.role != UserRole.ADMIN:
        log.warning(
            "rollback.denied.non_reversible",
            action_id=str(action_id),
            action_class=action.action_class.value,
            actor=current_user.email,
            actor_role=current_user.role.value,
        )
        detail = (
            f"action_class={action.action_class.value!r} is non-reversible; "
            "admin role required to record a rollback"
        )
        await _audit_denial(
            session,
            actor=current_user,
            action_id=action_id,
            reason_code="non_reversible_requires_admin",
            action_class=action.action_class.value,
            detail=detail,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    executor = get_remediation_executor()
    try:
        outcome = await executor.rollback(
            session,
            remediation_action_id=action_id,
            actor=current_user,
            reason=body.reason,
        )
    except RemediationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RemediationNotExecutableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await session.commit()
    return {
        "remediation_action_id": str(outcome.remediation_action_id),
        "new_status": outcome.new_status.value,
        "ok": outcome.execution_result.ok,
        "error": outcome.execution_result.error,
        "dry_run": outcome.execution_result.dry_run,
    }
