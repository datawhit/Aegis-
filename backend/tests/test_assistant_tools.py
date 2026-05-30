"""Tests for the Aegis Assistant tool layer (Sprint 10).

We test the tool implementations directly — no Anthropic API round trip,
no /assistant/chat HTTP path — because that's where the load-bearing
read-only logic lives. The chat endpoint is a thin wrapper that the
e2e tests will exercise once a live API key is part of CI (TBD).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.ai.assistant import (
    AssistantNotConfigured,
    AssistantService,
    _tool_get_action_detail,
    _tool_get_overview,
    _tool_get_recent_actions,
    _tool_get_top_policies,
)
from app.core.audit import Actor, get_audit_logger
from app.models.alert import AlertSeverity
from app.models.incident import Incident, IncidentStatus
from app.models.remediation_action import (
    RemediationAction,
    RemediationActionClass,
    RemediationStatus,
)


async def _make_executed_action(
    db_session: AsyncSession,
    *,
    action_class: RemediationActionClass,
    severity: AlertSeverity = AlertSeverity.HIGH,
) -> RemediationAction:
    incident = Incident(
        title=f"incident-{uuid.uuid4().hex[:6]}",
        summary="from test",
        severity=severity,
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
        ai_confidence=0.92,
        idempotency_key=f"test-{uuid.uuid4()}",
        execution_result={"ok": True, "dry_run": True},
    )
    db_session.add(action)
    await db_session.flush()
    return action


async def test_overview_tool_returns_full_shape(db_session: AsyncSession) -> None:
    await _make_executed_action(db_session, action_class=RemediationActionClass.ISOLATE_HOST)
    result = await _tool_get_overview(db_session, {})
    assert "overnight_summary" in result
    assert "trust_score" in result
    assert "risk_snapshot" in result
    assert "requires_attention" in result
    # ISOLATE_HOST is a stabilization → counted as such in the summary.
    assert result["overnight_summary"]["stabilized"] >= 1


async def test_recent_actions_filters_by_outcome(db_session: AsyncSession) -> None:
    # Build one resolved (notify_slack — non-stabilization), one stabilized.
    await _make_executed_action(db_session, action_class=RemediationActionClass.DISABLE_USER)
    await _make_executed_action(db_session, action_class=RemediationActionClass.ISOLATE_HOST)

    all_result = await _tool_get_recent_actions(db_session, {"outcome": "all"})
    assert all_result["count"] >= 2

    stab_result = await _tool_get_recent_actions(db_session, {"outcome": "stabilized"})
    assert all(item["outcome"] == "stabilized" for item in stab_result["items"])
    assert stab_result["count"] >= 1

    resolved_result = await _tool_get_recent_actions(db_session, {"outcome": "resolved"})
    assert all(item["outcome"] == "resolved" for item in resolved_result["items"])


async def test_action_detail_reports_unknown_id(db_session: AsyncSession) -> None:
    result = await _tool_get_action_detail(db_session, {"action_id": "not-a-uuid"})
    assert "error" in result

    missing_id = str(uuid.uuid4())
    result = await _tool_get_action_detail(db_session, {"action_id": missing_id})
    assert "error" in result


async def test_action_detail_returns_real_record(db_session: AsyncSession) -> None:
    action = await _make_executed_action(
        db_session, action_class=RemediationActionClass.ISOLATE_HOST
    )
    result = await _tool_get_action_detail(db_session, {"action_id": str(action.id)})
    assert result["action_id"] == str(action.id)
    assert result["is_stabilization"] is True
    assert result["is_reversible"] is True
    assert result["action_class"] == "isolate_host"
    assert result["status"] == "executed"
    assert result["incident_id"] is not None


async def test_top_policies_falls_back_when_no_evaluations(
    db_session: AsyncSession,
) -> None:
    # No `policy.evaluated` audit entries yet → empty list is acceptable.
    result = await _tool_get_top_policies(db_session, {"limit": 5})
    assert "items" in result


async def test_top_policies_reads_winning_policy_id_from_audit(
    db_session: AsyncSession,
) -> None:
    # Write a fake `policy.evaluated` entry referencing a synthetic policy id.
    action = await _make_executed_action(db_session, action_class=RemediationActionClass.BLOCK_IP)
    fake_policy_id = str(uuid.uuid4())
    await get_audit_logger().record(
        db_session,
        actor=Actor.system(label="test"),
        action="policy.evaluated",
        resource_type="remediation_action",
        resource_id=action.id,
        payload={
            "effect": "allow",
            "winning_policy_id": fake_policy_id,
            "matched_policy_ids": [fake_policy_id],
            "reasons": ["matched:test"],
        },
    )
    await db_session.flush()

    result = await _tool_get_top_policies(db_session, {"limit": 5})
    # Synthetic policy isn't in the policies table — but it shows up in
    # the counts with "(unknown policy)" name.
    assert any(item["policy_id"] == fake_policy_id for item in result["items"])


async def test_assistant_service_raises_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    service = AssistantService()
    with pytest.raises(AssistantNotConfigured):
        await service.chat(None, "anything")  # type: ignore[arg-type]
