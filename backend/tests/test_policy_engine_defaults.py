"""Stub policy engine — invariants from ADR-005.

Even though the stub never returns ALLOW yet, these tests pin the invariants
the real engine MUST honor when it lands in Sprint 2.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.policy import PolicyEffect, PolicyEvalRequest, StubPolicyEngine


@pytest.fixture
def session() -> MagicMock:
    sess = MagicMock()
    # session.execute → awaitable returning an object with .scalars().all() == []
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    sess.execute = AsyncMock(return_value=result)
    return sess


async def test_missing_rollback_plan_escalates(session: MagicMock) -> None:
    engine = StubPolicyEngine()
    decision = await engine.evaluate(
        session,
        PolicyEvalRequest(
            action_class="revoke_user_sessions",
            parameters={},
            blast_radius=1,
            ai_confidence=0.95,
            incident_severity="high",
            has_rollback_plan=False,
        ),
    )
    assert decision.effect is PolicyEffect.ESCALATE
    assert "no_rollback_plan_defined" in decision.reasons


async def test_missing_confidence_escalates(session: MagicMock) -> None:
    engine = StubPolicyEngine()
    decision = await engine.evaluate(
        session,
        PolicyEvalRequest(
            action_class="revoke_user_sessions",
            parameters={},
            blast_radius=1,
            ai_confidence=None,
            incident_severity="high",
            has_rollback_plan=True,
        ),
    )
    assert decision.effect is PolicyEffect.ESCALATE
    assert "ai_confidence_missing" in decision.reasons


async def test_no_rule_match_escalates_by_default(session: MagicMock) -> None:
    engine = StubPolicyEngine()
    decision = await engine.evaluate(
        session,
        PolicyEvalRequest(
            action_class="revoke_user_sessions",
            parameters={},
            blast_radius=1,
            ai_confidence=0.99,
            incident_severity="critical",
            has_rollback_plan=True,
        ),
    )
    # Stub has no rules — must default to ESCALATE, never ALLOW.
    assert decision.effect is PolicyEffect.ESCALATE
