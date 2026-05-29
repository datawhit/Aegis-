"""End-to-end Sprint 2 test: ESCALATE → approve → execute (stub) → rollback.

Exercises:
  - ApprovalService.request + Slack StubNotifier (records approval request)
  - ApprovalService.decide (approve)
  - RemediationExecutor.execute via StubExecutionConnector
  - RemediationExecutor.rollback
  - Audit chain has every transition

We bypass the policy engine here (set up the action in POLICY_ESCALATED
state directly) — policy is tested separately. This test focuses on the
state machine + executor wiring.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.execution import ExecutionRegistry
from app.core.execution.stub import StubExecutionConnector
from app.core.notifications.base import StubNotifier
from app.models.alert import AlertSeverity
from app.models.approval import ApprovalState
from app.models.audit_log import AuditLog
from app.models.incident import Incident, IncidentStatus
from app.models.remediation_action import (
    RemediationAction,
    RemediationActionClass,
    RemediationStatus,
)
from app.models.user import AuthProvider, User, UserRole
from app.services.approval_service import ApprovalService
from app.services.remediation_executor import RemediationExecutor


@pytest_asyncio.fixture
async def operator(db_session: AsyncSession) -> User:
    u = User(
        email=f"op-{uuid.uuid4()}@aegis.local",
        display_name="Operator",
        role=UserRole.OPERATOR,
        auth_provider=AuthProvider.LOCAL,
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def incident_with_action(
    db_session: AsyncSession,
) -> tuple[Incident, RemediationAction]:
    incident = Incident(
        title="impossible-travel suspected",
        summary="ai reasoning here",
        severity=AlertSeverity.HIGH,
        status=IncidentStatus.OPEN,
        ai_confidence=0.92,
        mitre_techniques=["T1078"],
        affected_entities={"users": ["kara.lin@aegis.test"]},
    )
    db_session.add(incident)
    await db_session.flush()

    action = RemediationAction(
        incident_id=incident.id,
        action_class=RemediationActionClass.REVOKE_USER_SESSIONS,
        status=RemediationStatus.POLICY_ESCALATED,
        parameters={"users": ["kara.lin@aegis.test"]},
        rollback_plan=None,  # revoke is non-reversible
        blast_radius=1,
        ai_confidence=0.92,
        idempotency_key=f"test-{uuid.uuid4()}",
    )
    db_session.add(action)
    await db_session.flush()
    return incident, action


async def test_full_closed_loop(
    db_session: AsyncSession,
    operator: User,
    incident_with_action: tuple[Incident, RemediationAction],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident, action = incident_with_action

    # Wire stub notifier + stub execution registry into the services.
    stub_notifier = StubNotifier()
    stub_connector = StubExecutionConnector()

    approval_svc = ApprovalService()
    approval_svc._notifier = stub_notifier  # type: ignore[attr-defined]

    registry = ExecutionRegistry()
    registry.register(stub_connector)
    executor = RemediationExecutor()
    executor._registry = registry  # type: ignore[attr-defined]

    # --- request approval ---
    approval = await approval_svc.request(
        db_session,
        remediation=action,
        incident=incident,
        ai_summary="suspected ATO",
        ai_reasoning="impossible-travel + forwarding rule",
    )
    assert approval.state is ApprovalState.PENDING
    assert action.status is RemediationStatus.AWAITING_APPROVAL
    assert len(stub_notifier.approval_requests) == 1
    assert stub_notifier.approval_requests[0].approval_id == approval.id

    # --- approve ---
    decision = await approval_svc.decide(
        db_session,
        approval_id=approval.id,
        approve=True,
        actor=operator,
        note="confirmed compromise",
    )
    assert decision.new_state is ApprovalState.APPROVED
    assert action.status is RemediationStatus.APPROVED

    # --- execute via stub ---
    outcome = await executor.execute(
        db_session,
        remediation_action_id=action.id,
        actor_id=operator.id,
    )
    assert outcome.execution_result.ok
    assert action.status is RemediationStatus.EXECUTED
    # Stub records the call.
    assert any(c.kind == "execute" for c in stub_connector.calls)

    # --- rollback ---
    # Stub supports rollback even though MS Graph wouldn't — that's the
    # point of the test: state machine + audit chain, not the connector
    # semantics.
    action.rollback_plan = {"action_class": "stub_undo", "parameters": {}}
    await db_session.flush()
    rb = await executor.rollback(
        db_session,
        remediation_action_id=action.id,
        actor=operator,
        reason="incident reclassified as false-positive",
    )
    assert rb.execution_result.ok
    assert action.status is RemediationStatus.ROLLED_BACK

    # --- audit chain has every transition ---
    # Approvals are audited against approval.id; remediations against
    # remediation_action.id. Check the union of both resource scopes.
    actions_seen = (
        (
            await db_session.execute(
                select(AuditLog.action).where(AuditLog.resource_id.in_([action.id, approval.id]))
            )
        )
        .scalars()
        .all()
    )
    expected = {
        "approval.requested",
        "approval.approved",
        "remediation.executing",
        "remediation.executed",
        "remediation.rollback_requested",
        "remediation.rolled_back",
    }
    assert expected.issubset(set(actions_seen))

    _ = monkeypatch  # silence unused
