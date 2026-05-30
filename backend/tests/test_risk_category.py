"""Tests for the per-category drill-down endpoint (Sprint 12)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity.local_jwt import LocalJWTIdentityProvider, hash_password
from app.models.alert import AlertSeverity
from app.models.incident import Incident, IncidentStatus
from app.models.remediation_action import (
    RemediationAction,
    RemediationActionClass,
    RemediationStatus,
)
from app.models.user import AuthProvider, User, UserRole


async def _make_user(db_session: AsyncSession) -> str:
    user = User(
        email=f"op-{uuid.uuid4()}@example.com",
        display_name="Op",
        hashed_password=hash_password("secret"),
        role=UserRole.OPERATOR,
        auth_provider=AuthProvider.LOCAL,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = await LocalJWTIdentityProvider().issue_token(user)
    return token.access_token


async def _make_executed_action(
    db_session: AsyncSession, action_class: RemediationActionClass
) -> RemediationAction:
    incident = Incident(
        title=f"incident-{uuid.uuid4().hex[:6]}",
        summary="",
        severity=AlertSeverity.HIGH,
        status=IncidentStatus.OPEN,
        ai_confidence=0.92,
        mitre_techniques=[],
        affected_entities={},
    )
    db_session.add(incident)
    await db_session.flush()
    action = RemediationAction(
        incident_id=incident.id,
        action_class=action_class,
        status=RemediationStatus.EXECUTED,
        parameters={},
        rollback_plan={"action_class": "stub_undo", "parameters": {}},
        blast_radius=1,
        ai_confidence=0.92,
        idempotency_key=f"test-{uuid.uuid4()}",
        execution_result={"ok": True},
    )
    db_session.add(action)
    await db_session.flush()
    return action


async def test_drilldown_returns_actions_for_known_category(client, db_session) -> None:
    await _make_executed_action(db_session, RemediationActionClass.ISOLATE_HOST)
    await _make_executed_action(db_session, RemediationActionClass.QUARANTINE_FILE)
    token = await _make_user(db_session)
    await db_session.commit()

    response = await client.get(
        "/api/v1/risk/category/Endpoint?window=7d",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"] == "Endpoint"
    assert body["summary"]["actions_count"] >= 2
    action_classes = {row["action_class"] for row in body["recent_actions"]}
    assert "isolate_host" in action_classes
    assert "quarantine_file" in action_classes


async def test_drilldown_empty_for_unknown_category(client, db_session) -> None:
    token = await _make_user(db_session)
    await db_session.commit()

    response = await client.get(
        "/api/v1/risk/category/MadeUp?window=7d",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "MadeUp"
    assert body["summary"]["actions_count"] == 0
    assert body["recent_actions"] == []
    assert body["contributing_classes"] == []


async def test_drilldown_outcome_labels(client, db_session) -> None:
    await _make_executed_action(db_session, RemediationActionClass.DISABLE_USER)
    token = await _make_user(db_session)
    await db_session.commit()

    response = await client.get(
        "/api/v1/risk/category/Identity?window=7d",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    outcomes = {row["outcome"] for row in body["recent_actions"]}
    # disable_user is NOT a stabilization → it labels as "resolved".
    assert "resolved" in outcomes
