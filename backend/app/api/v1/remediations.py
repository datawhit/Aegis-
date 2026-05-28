"""Remediation actions: rollback endpoint.

Authorization (Sprint 4):

- Reversible action classes (e.g. ISOLATE_HOST, BLOCK_IP) — OPERATOR
  or ADMIN may roll back.
- Non-reversible action classes (e.g. REVOKE_USER_SESSIONS,
  FORCE_PASSWORD_RESET) — ADMIN only. The "rollback" of a non-reversible
  action is at best a compensating control; we want a senior actor on
  record. See `RemediationActionClass.is_reversible`.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.logging import get_logger
from app.models.remediation_action import RemediationAction
from app.models.user import UserRole
from app.schemas.remediation import RollbackRequest
from app.services.remediation_executor import (
    RemediationNotExecutableError,
    RemediationNotFoundError,
    get_remediation_executor,
)

router = APIRouter()
log = get_logger("remediation.rollback")


@router.post("/remediations/{action_id}/rollback")
async def rollback_remediation(
    action_id: uuid.UUID,
    body: RollbackRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> dict:
    if current_user.role not in {UserRole.ADMIN, UserRole.OPERATOR}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="operator or admin role required to rollback remediations",
        )

    action = (
        await session.execute(
            select(RemediationAction).where(RemediationAction.id == action_id)
        )
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"action_class={action.action_class.value!r} is non-reversible; "
                "admin role required to record a rollback"
            ),
        )

    executor = get_remediation_executor()
    try:
        outcome = await executor.rollback(
            session,
            remediation_action_id=action_id,
            actor=current_user,
            reason=body.reason,
        )
    except RemediationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RemediationNotExecutableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    await session.commit()
    return {
        "remediation_action_id": str(outcome.remediation_action_id),
        "new_status": outcome.new_status.value,
        "ok": outcome.execution_result.ok,
        "error": outcome.execution_result.error,
        "dry_run": outcome.execution_result.dry_run,
    }
