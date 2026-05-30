"""Risk Analytics endpoint tests (Sprint 11)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.risk import _score_at, _summary, _window_bounds
from app.core.audit import Actor, get_audit_logger
from app.core.identity.local_jwt import LocalJWTIdentityProvider, hash_password
from app.models.alert import AlertSeverity
from app.models.incident import Incident, IncidentStatus
from app.models.policy import Policy, PolicyEffect
from app.models.remediation_action import (
    RemediationAction,
    RemediationActionClass,
    RemediationStatus,
)
from app.models.user import AuthProvider, User, UserRole


def test_window_bounds_24h() -> None:
    now = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
    start, prior, bucket = _window_bounds("24h", now)
    assert (now - start).total_seconds() == 24 * 3600
    assert (now - prior).total_seconds() == 48 * 3600
    assert bucket.total_seconds() == 2 * 3600


def test_window_bounds_7d_and_30d() -> None:
    now = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
    _, _, b7 = _window_bounds("7d", now)
    _, _, b30 = _window_bounds("30d", now)
    assert b7.total_seconds() == 12 * 3600
    assert b30.days == 1


def test_summary_handles_zero_prior() -> None:
    from app.api.v1.risk import RiskHistoryPoint

    now = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
    summary_no_data = _summary("7d", [], [])
    assert summary_no_data.current_score == 0
    assert summary_no_data.delta_pct is None

    summary_zero_prior = _summary(
        "7d",
        [RiskHistoryPoint(t=now, score=15)],
        [RiskHistoryPoint(t=now, score=0)],
    )
    assert summary_zero_prior.current_score == 15
    assert summary_zero_prior.delta_pct == 100.0


def test_summary_labels_by_band() -> None:
    from app.api.v1.risk import RiskHistoryPoint

    now = datetime(2026, 5, 30, tzinfo=UTC)
    for score, label in [(10, "Low"), (45, "Medium"), (70, "High"), (95, "Critical")]:
        s = _summary(
            "7d",
            [RiskHistoryPoint(t=now, score=score)],
            [RiskHistoryPoint(t=now, score=score)],
        )
        assert s.label == label, f"score={score} → expected {label}, got {s.label}"


async def test_score_at_counts_open_incidents_weighted(
    db_session: AsyncSession,
) -> None:
    """An OPEN HIGH incident contributes 5; a Critical contributes 12."""
    db_session.add(
        Incident(
            title="open-high",
            summary="",
            severity=AlertSeverity.HIGH,
            status=IncidentStatus.OPEN,
            ai_confidence=0.8,
            mitre_techniques=[],
            affected_entities={},
        )
    )
    db_session.add(
        Incident(
            title="open-critical",
            summary="",
            severity=AlertSeverity.CRITICAL,
            status=IncidentStatus.OPEN,
            ai_confidence=0.9,
            mitre_techniques=[],
            affected_entities={},
        )
    )
    await db_session.flush()
    score = await _score_at(db_session, datetime.now(UTC))
    # 5 (HIGH) + 12 (CRITICAL) = 17
    assert score == 17


async def test_score_at_excludes_closed_incidents(db_session: AsyncSession) -> None:
    incident = Incident(
        title="resolved",
        summary="",
        severity=AlertSeverity.HIGH,
        status=IncidentStatus.CLOSED_RESOLVED,
        ai_confidence=0.5,
        mitre_techniques=[],
        affected_entities={},
    )
    db_session.add(incident)
    await db_session.flush()
    # updated_at is set by ORM; use far-future t to ensure updated_at < t
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    score = await _score_at(db_session, far_future)
    assert score == 0


async def test_risk_analytics_endpoint_smoke(client, db_session) -> None:
    """Full HTTP round-trip — endpoint returns the documented shape."""
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
    await db_session.commit()

    response = await client.get(
        "/api/v1/risk/analytics?window=7d",
        headers={"Authorization": f"Bearer {token.access_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["window"] == "7d"
    assert "current_score" in body["summary"]
    assert isinstance(body["score_history"], list)
    assert isinstance(body["categories"], list)
    assert isinstance(body["top_reducing"], list)


async def test_top_reducing_picks_up_policy_evaluated_audit(client, db_session) -> None:
    """An EXECUTED action with a policy.evaluated audit entry shows up
    in the top_reducing list — keyed on winning_policy_id."""
    incident = Incident(
        title="for-top-reducing",
        summary="",
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
        action_class=RemediationActionClass.ISOLATE_HOST,
        status=RemediationStatus.EXECUTED,
        parameters={},
        rollback_plan={"action_class": "stub_undo", "parameters": {}},
        blast_radius=1,
        ai_confidence=0.91,
        idempotency_key=f"test-{uuid.uuid4()}",
        execution_result={"ok": True},
    )
    db_session.add(action)

    policy = Policy(
        name=f"isolate-{uuid.uuid4().hex[:6]}",
        description="test",
        priority=100,
        effect=PolicyEffect.ALLOW,
        match={"eq": [{"var": "action_class"}, "isolate_host"]},
        constraints={},
        is_active=True,
    )
    db_session.add(policy)
    await db_session.flush()

    await get_audit_logger().record(
        db_session,
        actor=Actor.system(label="test"),
        action="policy.evaluated",
        resource_type="remediation_action",
        resource_id=action.id,
        payload={
            "effect": "allow",
            "winning_policy_id": str(policy.id),
            "matched_policy_ids": [str(policy.id)],
            "reasons": ["matched:test"],
        },
    )

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
    await db_session.commit()

    response = await client.get(
        "/api/v1/risk/analytics?window=7d",
        headers={"Authorization": f"Bearer {token.access_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    top_policy_ids = {p["policy_id"] for p in body["top_reducing"]}
    assert str(policy.id) in top_policy_ids
