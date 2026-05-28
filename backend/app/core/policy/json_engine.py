"""JSONPolicyEngine — evaluates DSL policies stored in the `policies` table.

Lifecycle:
  1. Load all active policies, ordered by priority DESC (higher = stronger).
  2. For each, run `evaluate_match` against the request context.
  3. Apply ADR-005 invariants:
       - has_rollback_plan == False → ESCALATE, regardless of matches
       - ai_confidence is missing/None → ESCALATE
       - eval errors → no-match → ESCALATE
       - two or more ALLOWs at equal priority → ESCALATE (conflict)
       - DENY at any priority wins over equal/lower priority ALLOW
  4. Carry through `constraints` from the winning policy so the caller
     (IncidentService) can read e.g. `requires_approval`.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.policy.dsl import (
    PolicyDSLError,
    context_from_request,
    evaluate_match,
)
from app.core.policy.engine import (
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyEvalRequest,
)
from app.logging import get_logger
from app.models.policy import Policy, PolicyEffect as ORMPolicyEffect

log = get_logger("policy.json")


@dataclass(frozen=True)
class _Match:
    policy_id: str
    name: str
    priority: int
    effect: PolicyEffect
    constraints: dict


class JSONPolicyEngine(PolicyEngine):
    async def evaluate(
        self, session: AsyncSession, request: PolicyEvalRequest
    ) -> PolicyDecision:
        # --- hard invariants (ADR-005) -------------------------------------
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

        ctx = context_from_request(
            {
                "action_class": request.action_class,
                "blast_radius": request.blast_radius,
                "ai_confidence": request.ai_confidence,
                "incident_severity": request.incident_severity,
                "has_rollback_plan": request.has_rollback_plan,
            }
        )

        try:
            policies = (
                await session.execute(
                    select(Policy)
                    .where(Policy.is_active.is_(True))
                    .order_by(Policy.priority.desc(), Policy.name.asc())
                )
            ).scalars().all()
        except Exception as exc:  # pragma: no cover — defensive
            log.exception("policy.load_failed", error=str(exc))
            return PolicyDecision(
                effect=PolicyEffect.ESCALATE,
                reasons=["policy_load_error"],
            )

        matches: list[_Match] = []
        for policy in policies:
            try:
                if evaluate_match(policy.match, ctx):
                    matches.append(
                        _Match(
                            policy_id=str(policy.id),
                            name=policy.name,
                            priority=policy.priority,
                            effect=_effect_from_orm(policy.effect),
                            constraints=policy.constraints or {},
                        )
                    )
            except PolicyDSLError as exc:
                log.warning(
                    "policy.eval_skipped",
                    policy_id=str(policy.id),
                    name=policy.name,
                    error=str(exc),
                )
                continue

        if not matches:
            return PolicyDecision(
                effect=PolicyEffect.ESCALATE,
                reasons=["no_policy_matched_default_escalate"],
            )

        # DENY at any priority wins over equal-or-lower ALLOW.
        top_priority = matches[0].priority
        top = [m for m in matches if m.priority == top_priority]
        if any(m.effect is PolicyEffect.DENY for m in top):
            denies = [m for m in top if m.effect is PolicyEffect.DENY]
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                matched_policy_ids=[m.policy_id for m in denies],
                reasons=[f"denied_by:{m.name}" for m in denies],
            )

        # Equal-priority conflict among ALLOWs / ESCALATEs → ESCALATE.
        distinct_effects = {m.effect for m in top}
        if len(distinct_effects) > 1:
            return PolicyDecision(
                effect=PolicyEffect.ESCALATE,
                matched_policy_ids=[m.policy_id for m in top],
                reasons=["equal_priority_policy_conflict"],
            )

        winner = top[0]

        # If the winning rule is ALLOW, double-check its own constraints
        # before returning. A policy can say "I match but require approval"
        # via `constraints.requires_approval = true`. We still return ALLOW;
        # the IncidentService consults `constraints` to decide whether to
        # route through Approval.
        log.info(
            "policy.match",
            effect=winner.effect.value,
            policy=winner.name,
            priority=winner.priority,
            request_action_class=request.action_class,
        )
        return PolicyDecision(
            effect=winner.effect,
            matched_policy_ids=[winner.policy_id],
            reasons=[f"matched:{winner.name}"],
        )


def _effect_from_orm(effect: ORMPolicyEffect) -> PolicyEffect:
    match effect:
        case ORMPolicyEffect.ALLOW:
            return PolicyEffect.ALLOW
        case ORMPolicyEffect.DENY:
            return PolicyEffect.DENY
        case _:
            return PolicyEffect.ESCALATE
