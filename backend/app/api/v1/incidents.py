"""GET /incidents, GET /incidents/{id} — incident list + detail."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, SessionDep
from app.models.ai_reasoning import AIReasoningSnapshot
from app.models.alert import Alert
from app.models.incident import Incident
from app.models.remediation_action import RemediationAction
from app.schemas.ai_reasoning import AIReasoningRead
from app.schemas.alert import AlertRead
from app.schemas.incident import (
    IncidentDetail,
    IncidentList,
    IncidentSummary,
    RemediationActionRead,
)

router = APIRouter()


@router.get("/incidents", response_model=IncidentList)
async def list_incidents(
    session: SessionDep,
    _user: CurrentUserDep,
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> IncidentList:
    base = select(Incident)
    if status_filter:
        base = base.where(Incident.status == status_filter)
    if severity:
        base = base.where(Incident.severity == severity)

    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    items = (
        await session.execute(
            base.order_by(Incident.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return IncidentList(
        items=[IncidentSummary.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(
    incident_id: uuid.UUID,
    session: SessionDep,
    _user: CurrentUserDep,
) -> IncidentDetail:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="incident not found"
        )

    alerts = (
        await session.execute(
            select(Alert)
            .where(Alert.incident_id == incident_id)
            .order_by(Alert.created_at.asc())
        )
    ).scalars().all()

    remediations = (
        await session.execute(
            select(RemediationAction)
            .where(RemediationAction.incident_id == incident_id)
            .order_by(RemediationAction.created_at.asc())
        )
    ).scalars().all()

    reasonings = (
        await session.execute(
            select(AIReasoningSnapshot)
            .where(AIReasoningSnapshot.incident_id == incident_id)
            .order_by(AIReasoningSnapshot.created_at.asc())
        )
    ).scalars().all()

    return IncidentDetail(
        id=incident.id,
        title=incident.title,
        severity=incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
        status=incident.status.value if hasattr(incident.status, "value") else str(incident.status),
        ai_confidence=incident.ai_confidence,
        mitre_techniques=incident.mitre_techniques,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        summary=incident.summary,
        affected_entities=incident.affected_entities,
        alerts=[AlertRead.model_validate(a) for a in alerts],
        remediation_actions=[RemediationActionRead.model_validate(r) for r in remediations],
        reasoning_snapshots=[AIReasoningRead.model_validate(s) for s in reasonings],
    )


