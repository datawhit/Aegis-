"""Policy engine — Phase 0 stub.

Phase 0 ships the **contract** and a safe default implementation. The real
DSL + matching engine lands in Sprint 2. Until then, the stub returns
`ESCALATE` for every proposed action — which is correct: by ADR-005,
"no policy matches" must mean "ask a human".

The stub still walks the `policies` table so we get integration-level
exercise of the model, even if no rule will ever match in this phase.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.policy import Policy

log = get_logger("policy")


class PolicyEffect(str, enum.Enum):
    ALLOW = "allow"
    ESCALATE = "escalate"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyEvalRequest:
    action_class: str
    parameters: dict[str, Any]
    blast_radius: int
    ai_confidence: float | None
    incident_severity: str
    has_rollback_plan: bool


@dataclass
class PolicyDecision:
    effect: PolicyEffect
    matched_policy_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@runtime_checkable
class PolicyEngine(Protocol):
    async def evaluate(
        self, session: AsyncSession, request: PolicyEvalRequest
    ) -> PolicyDecision: ...


class StubPolicyEngine(PolicyEngine):
    """Default-deny / escalate-on-uncertainty stub.

    Even though we return ESCALATE for everything, we still encode the
    invariants documented in ADR-005 so that real rules added later cannot
    bypass them:
      - rollback plan required for ALLOW
      - AI confidence required for ALLOW
      - eval errors → ESCALATE
    """

    async def evaluate(
        self, session: AsyncSession, request: PolicyEvalRequest
    ) -> PolicyDecision:
        try:
            # Exercise the policies table even though we won't match.
            result = await session.execute(
                select(Policy).where(Policy.is_active.is_(True))
            )
            active_policies = result.scalars().all()
        except Exception as exc:  # pragma: no cover — defensive
            log.exception("policy.eval.failed", error=str(exc))
            return PolicyDecision(
                effect=PolicyEffect.ESCALATE,
                reasons=["policy_evaluation_error"],
            )

        # Hard invariants (apply before any potential rule match).
        if not request.has_rollback_plan:
            return PolicyDecision(
                effect=PolicyEffect.ESCALATE,
                reasons=["no_rollback_plan_defined"],
            )
        if request.ai_confidence is None:
            return PolicyDecision(
                effect=PolicyEffect.ESCALATE,
                reasons=["ai_confidence_missing"],
            )

        log.info(
            "policy.eval.no_rules_matched",
            action_class=request.action_class,
            active_policy_count=len(active_policies),
        )
        return PolicyDecision(
            effect=PolicyEffect.ESCALATE,
            reasons=["no_policy_matched_default_escalate"],
        )


_singleton: StubPolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    global _singleton
    if _singleton is None:
        _singleton = StubPolicyEngine()
    return _singleton
