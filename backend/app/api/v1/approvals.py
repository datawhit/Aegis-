"""Approvals endpoints: GET /approvals (inbox), POST /approvals/{id}/decision."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.core.workflow import get_workflow_engine
from app.models.approval import Approval, ApprovalState
from app.models.incident import Incident
from app.models.remediation_action import RemediationAction
from app.schemas.approval import (
    ApprovalDecisionRequest,
    ApprovalList,
    ApprovalListItem,
    ApprovalRead,
)
from app.services.approval_service import (
    ApprovalNotFoundError,
    ApprovalNotPendingError,
    get_approval_service,
)

router = APIRouter()


@router.get("/approvals", response_model=ApprovalList)
async def list_approvals(
    session: SessionDep,
    _user: CurrentUserDep,
    pending_only: bool = True,
) -> ApprovalList:
    stmt = (
        select(Approval, RemediationAction, Incident)
        .join(RemediationAction, RemediationAction.id == Approval.remediation_action_id)
        .join(Incident, Incident.id == RemediationAction.incident_id)
        .order_by(Approval.created_at.desc())
    )
    if pending_only:
        stmt = stmt.where(Approval.state == ApprovalState.PENDING)

    rows = (await session.execute(stmt)).all()

    return ApprovalList(
        items=[
            ApprovalListItem(
                approval=ApprovalRead.model_validate(approval),
                incident_id=incident.id,
                incident_title=incident.title,
                incident_severity=incident.severity.value
                if hasattr(incident.severity, "value")
                else str(incident.severity),
                action_class=action.action_class.value
                if hasattr(action.action_class, "value")
                else str(action.action_class),
                blast_radius=action.blast_radius,
                ai_confidence=action.ai_confidence,
                ai_summary=incident.summary,
            )
            for approval, action, incident in rows
        ]
    )


@router.post(
    "/approvals/{approval_id}/decision",
    response_model=ApprovalRead,
)
async def decide_approval(
    approval_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ApprovalRead:
    service = get_approval_service()
    try:
        decision = await service.decide(
            session,
            approval_id=approval_id,
            approve=body.approve,
            actor=current_user,
            note=body.note,
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="approval not found",
        ) from exc
    except ApprovalNotPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    await session.commit()

    # If approved, kick off the executor. Commit before submit so the
    # workflow_run row's FK targets are visible.
    if decision.new_state is ApprovalState.APPROVED:
        engine = get_workflow_engine()
        await engine.submit(
            "execute_remediation",
            payload={"remediation_action_id": str(decision.remediation_action_id)},
            idempotency_key=f"execute_remediation:{decision.remediation_action_id}",
            actor_id=current_user.id,
        )

    approval = (
        await session.execute(
            select(Approval).where(Approval.id == approval_id)
        )
    ).scalar_one()
    return ApprovalRead.model_validate(approval)
