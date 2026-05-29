"""RBAC tests for the rollback endpoint (Sprint 4).

Reversible action classes: operator OR admin may roll back.
Non-reversible action classes: admin only.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.execution import ExecutionRegistry
from app.core.execution.stub import StubExecutionConnector
from app.core.identity.local_jwt import LocalJWTIdentityProvider, hash_password
from app.models.alert import AlertSeverity
from app.models.incident import Incident, IncidentStatus
from app.models.remediation_action import (
    RemediationAction,
    RemediationActionClass,
    RemediationStatus,
)
from app.models.user import AuthProvider, User, UserRole
from app.services.remediation_executor import get_remediation_executor


async def _make_user(db_session, role: UserRole) -> tuple[User, str]:
    user = User(
        email=f"{role.value}-{uuid.uuid4()}@example.com",
        display_name=role.value,
        hashed_password=hash_password("secret"),
        role=role,
        auth_provider=AuthProvider.LOCAL,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = await LocalJWTIdentityProvider().issue_token(user)
    return user, token.access_token


async def _make_executed_action(
    db_session: AsyncSession,
    action_class: RemediationActionClass,
) -> RemediationAction:
    incident = Incident(
        title="test incident",
        summary="...",
        severity=AlertSeverity.HIGH,
        status=IncidentStatus.OPEN,
        ai_confidence=0.9,
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
        ai_confidence=0.9,
        idempotency_key=f"test-{uuid.uuid4()}",
        execution_result={"ok": True, "dry_run": True},
    )
    db_session.add(action)
    await db_session.flush()
    return action


@pytest_asyncio.fixture(autouse=True)
def _wire_stub_executor() -> None:
    """Make the global executor use the stub connector for these tests."""
    registry = ExecutionRegistry()
    registry.register(StubExecutionConnector())
    get_remediation_executor()._registry = registry  # type: ignore[attr-defined]


def test_reversibility_classifications() -> None:
    """Sanity-check the static reversibility map — it backs the auth gate."""
    assert RemediationActionClass.ISOLATE_HOST.is_reversible
    assert RemediationActionClass.DISABLE_USER.is_reversible
    assert RemediationActionClass.BLOCK_IP.is_reversible
    assert RemediationActionClass.OPEN_JIRA_TICKET.is_reversible

    assert not RemediationActionClass.REVOKE_USER_SESSIONS.is_reversible
    assert not RemediationActionClass.FORCE_PASSWORD_RESET.is_reversible
    assert not RemediationActionClass.NOTIFY_SLACK.is_reversible
    assert not RemediationActionClass.CUSTOM.is_reversible


async def test_operator_can_rollback_reversible_action(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.OPERATOR)
    action = await _make_executed_action(db_session, RemediationActionClass.ISOLATE_HOST)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/remediations/{action.id}/rollback",
        headers={"Authorization": f"Bearer {access}"},
        json={"reason": "false positive"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["new_status"] == RemediationStatus.ROLLED_BACK.value


async def test_operator_cannot_rollback_non_reversible_action(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.OPERATOR)
    action = await _make_executed_action(db_session, RemediationActionClass.REVOKE_USER_SESSIONS)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/remediations/{action.id}/rollback",
        headers={"Authorization": f"Bearer {access}"},
        json={"reason": "false positive"},
    )
    assert response.status_code == 403
    assert "non-reversible" in response.json()["detail"]


async def test_admin_can_rollback_non_reversible_action(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.ADMIN)
    action = await _make_executed_action(db_session, RemediationActionClass.REVOKE_USER_SESSIONS)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/remediations/{action.id}/rollback",
        headers={"Authorization": f"Bearer {access}"},
        json={"reason": "compensating control: forced re-auth complete"},
    )
    assert response.status_code == 200, response.text


async def test_viewer_cannot_rollback_anything(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.VIEWER)
    action = await _make_executed_action(db_session, RemediationActionClass.ISOLATE_HOST)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/remediations/{action.id}/rollback",
        headers={"Authorization": f"Bearer {access}"},
        json={"reason": "no"},
    )
    assert response.status_code == 403


async def test_reviewer_cannot_rollback_anything(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.REVIEWER)
    action = await _make_executed_action(db_session, RemediationActionClass.ISOLATE_HOST)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/remediations/{action.id}/rollback",
        headers={"Authorization": f"Bearer {access}"},
        json={"reason": "no"},
    )
    assert response.status_code == 403
