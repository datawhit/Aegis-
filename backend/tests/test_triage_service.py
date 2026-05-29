"""TriageService — verifies the contract:

- reasoning snapshot is persisted before the function returns
- confidence is reflected in the snapshot
- AI failure → fallback output + null confidence + ai_failed=True
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.base import TriageOutput, TriageRequest
from app.core.ai.triage import TriageService
from app.models.ai_reasoning import AIReasoningSnapshot
from app.models.alert import AlertSeverity
from app.prompts.triage import TRIAGE_PROMPT_VERSION
from tests.fakes import FakeAIProvider


@pytest.fixture
def triage_request() -> TriageRequest:
    return TriageRequest(
        alert_id=uuid.uuid4(),
        source="defender",
        normalized={"category": "InitialAccess", "severity_hint": "high"},
        raw_event_excerpt={"alertId": "x"},
    )


async def test_persists_snapshot_with_expected_fields(
    db_session: AsyncSession, triage_request: TriageRequest
) -> None:
    provider = FakeAIProvider(
        next_output=TriageOutput(
            severity=AlertSeverity.HIGH,
            category="initial_access",
            mitre_techniques=["T1078"],
            summary="test",
            suggested_action_class="revoke_user_sessions",
            confidence=0.91,
            reasoning="ok",
        )
    )
    service = TriageService(provider=provider)
    decision = await service.triage(db_session, triage_request)

    snapshot = (
        await db_session.execute(
            select(AIReasoningSnapshot).where(
                AIReasoningSnapshot.id == decision.reasoning_snapshot_id
            )
        )
    ).scalar_one()

    assert snapshot.provider == "fake"
    assert snapshot.model == "fake-1"
    assert snapshot.prompt_template_id == TRIAGE_PROMPT_VERSION
    assert snapshot.confidence == pytest.approx(0.91)
    assert snapshot.structured_output["severity"] == "high"
    assert decision.ai_failed is False


async def test_ai_failure_yields_safe_fallback(
    db_session: AsyncSession, triage_request: TriageRequest
) -> None:
    provider = FakeAIProvider(fail_with="network timeout")
    service = TriageService(provider=provider)
    decision = await service.triage(db_session, triage_request)

    snapshot = (
        await db_session.execute(
            select(AIReasoningSnapshot).where(
                AIReasoningSnapshot.id == decision.reasoning_snapshot_id
            )
        )
    ).scalar_one()

    assert decision.ai_failed is True
    assert decision.output.suggested_action_class is None
    # Fallback severity is MEDIUM by design (don't escalate severity on
    # AI failure; that's the policy engine's job via ESCALATE).
    assert decision.output.severity == AlertSeverity.MEDIUM
    # Confidence is null on the snapshot when AI failed (policy engine's
    # ai_confidence_missing invariant then escalates).
    assert snapshot.confidence is None
    assert snapshot.structured_output["category"] == "ai_failed"
