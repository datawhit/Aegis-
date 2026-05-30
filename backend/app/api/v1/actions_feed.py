"""Aegis Actions Feed (Sprint 9).

The centerpiece data source for the operator-first Overview. Each row is
one `RemediationAction` joined with its `Incident` and, opportunistically,
the policy that decided it.

Outcome labels collapse the internal state machine into the three
operator-facing buckets the UI tabs through:

- "resolved"   — EXECUTED, and the action class is not a stabilization
- "stabilized" — EXECUTED, and the action class IS a containment
                 (isolate_host, revoke_user_sessions, block_ip,
                  block_domain, quarantine_file). Threat bounded but root
                 cause still wants a permanent fix.
- "escalated"  — POLICY_ESCALATED or the incident itself is ESCALATED.

PROPOSED / POLICY_DENIED / AWAITING_APPROVAL never reach the feed today;
the feed is "what Aegis did," not "what Aegis is thinking."
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.api.deps import CurrentUserDep, SessionDep
from app.models.incident import Incident, IncidentStatus
from app.models.remediation_action import RemediationAction, RemediationStatus

router = APIRouter()

# Mirrors overview.py — keep these aligned. (If we end up needing the set
# in three places, move into the model file.)
_STABILIZATION_ACTION_CLASSES = {
    "isolate_host",
    "revoke_user_sessions",
    "block_ip",
    "block_domain",
    "quarantine_file",
}

OutcomeLabel = Literal["resolved", "stabilized", "escalated"]


class ActionFeedItem(BaseModel):
    action_id: str
    incident_id: str
    incident_title: str
    incident_severity: str
    action_class: str
    action_category: str
    outcome: OutcomeLabel
    ai_confidence: float | None
    created_at: datetime
    executed_at: datetime | None
    policy_id: str | None


class ActionFeedResponse(BaseModel):
    items: list[ActionFeedItem]
    counts: dict[str, int]  # {"all": ..., "resolved": ..., "stabilized": ..., "escalated": ...}


# Lightweight grouping for UI category badges (AUTHENTICATION / IDENTITY /
# ENDPOINT / NETWORK / INFRASTRUCTURE / NOTIFICATION / OTHER).
_CATEGORY_BY_ACTION_CLASS: dict[str, str] = {
    "revoke_user_sessions": "AUTHENTICATION",
    "force_password_reset": "AUTHENTICATION",
    "disable_user": "IDENTITY",
    "isolate_host": "ENDPOINT",
    "quarantine_file": "ENDPOINT",
    "block_ip": "NETWORK",
    "block_domain": "NETWORK",
    "notify_slack": "NOTIFICATION",
    "open_jira_ticket": "NOTIFICATION",
    "custom": "OTHER",
}


def _outcome_for(action: RemediationAction, incident: Incident) -> OutcomeLabel | None:
    status = action.status.value if hasattr(action.status, "value") else str(action.status)
    if status == RemediationStatus.POLICY_ESCALATED.value:
        return "escalated"
    if status == RemediationStatus.EXECUTED.value:
        action_class = (
            action.action_class.value
            if hasattr(action.action_class, "value")
            else str(action.action_class)
        )
        return "stabilized" if action_class in _STABILIZATION_ACTION_CLASSES else "resolved"
    incident_status = (
        incident.status.value if hasattr(incident.status, "value") else str(incident.status)
    )
    if incident_status == IncidentStatus.ESCALATED.value:
        return "escalated"
    return None  # PROPOSED / AWAITING_APPROVAL / DENIED — not feed-eligible


@router.get("/actions/feed", response_model=ActionFeedResponse)
async def list_actions_feed(
    session: SessionDep,
    _user: CurrentUserDep,
    status: Literal["all", "resolved", "stabilized", "escalated"] = Query("all"),
    limit: int = Query(50, ge=1, le=200),
) -> ActionFeedResponse:
    stmt = (
        select(RemediationAction, Incident)
        .join(Incident, Incident.id == RemediationAction.incident_id)
        .where(
            or_(
                RemediationAction.status == RemediationStatus.EXECUTED.value,
                RemediationAction.status == RemediationStatus.POLICY_ESCALATED.value,
                Incident.status == IncidentStatus.ESCALATED.value,
            )
        )
        .order_by(RemediationAction.created_at.desc())
        .limit(limit * 4)  # over-fetch — we filter by outcome in Python
    )
    rows = (await session.execute(stmt)).all()

    items: list[ActionFeedItem] = []
    counts: dict[str, int] = {"all": 0, "resolved": 0, "stabilized": 0, "escalated": 0}
    for action, incident in rows:
        outcome = _outcome_for(action, incident)
        if outcome is None:
            continue
        counts["all"] += 1
        counts[outcome] += 1
        if status != "all" and outcome != status:
            continue
        if len(items) >= limit:
            continue
        action_class = (
            action.action_class.value
            if hasattr(action.action_class, "value")
            else str(action.action_class)
        )
        severity = (
            incident.severity.value
            if hasattr(incident.severity, "value")
            else str(incident.severity)
        )
        executed_at = None
        if action.execution_result:
            ts = action.execution_result.get("executed_at")
            executed_at = datetime.fromisoformat(ts) if isinstance(ts, str) else None
        items.append(
            ActionFeedItem(
                action_id=str(action.id),
                incident_id=str(incident.id),
                incident_title=incident.title,
                incident_severity=severity,
                action_class=action_class,
                action_category=_CATEGORY_BY_ACTION_CLASS.get(action_class, "OTHER"),
                outcome=outcome,
                ai_confidence=action.ai_confidence,
                created_at=action.created_at,
                executed_at=executed_at,
                policy_id=None,  # join to policy.evaluated audit entry — Sprint 10
            )
        )

    return ActionFeedResponse(items=items, counts=counts)
