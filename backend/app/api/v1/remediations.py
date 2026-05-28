"""Remediation actions: rollback endpoint."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.remediation import RollbackRequest
from app.services.remediation_executor import (
    RemediationNotExecutableError,
    RemediationNotFoundError,
    get_remediation_executor,
)

router = APIRouter()


@router.post("/remediations/{action_id}/rollback")
async def rollback_remediation(
    action_id: uuid.UUID,
    body: RollbackRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> dict:
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
