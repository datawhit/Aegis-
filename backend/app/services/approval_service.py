"""ApprovalService — request / approve / reject / expire state machine.

State machine:

    PENDING ─approve──► APPROVED   (then RemediationExecutor dispatches)
            ─reject───► REJECTED
            ─expire───► EXPIRED    (escalation; UI surfaces these)

Transitions out of PENDING audit-log the actor and the decision note.
A pending approval past `expires_at` is moved to EXPIRED by the Celery
beat task `workflows.expire_stale_approvals`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit import Actor, get_audit_logger
from app.core.notifications import ApprovalNotification, get_notifier
from app.logging import get_logger
from app.models.approval import Approval, ApprovalState
from app.models.incident import Incident
from app.models.remediation_action import RemediationAction, RemediationStatus
from app.models.user import User, UserRole

log = get_logger("services.approval")


class ApprovalNotFoundError(LookupError):
    pass


class ApprovalNotPendingError(RuntimeError):
    pass


class ApprovalUnauthorizedError(PermissionError):
    pass


@dataclass
class ApprovalDecision:
    approval_id: uuid.UUID
    remediation_action_id: uuid.UUID
    incident_id: uuid.UUID
    new_state: ApprovalState
    decided_by_user_id: uuid.UUID
    note: str | None


class ApprovalService:
    def __init__(self) -> None:
        self._audit = get_audit_logger()
        self._notifier = get_notifier()

    async def request(
        self,
        session: AsyncSession,
        *,
        remediation: RemediationAction,
        incident: Incident,
        ai_summary: str,
        ai_reasoning: str,
        ttl_seconds: int | None = None,
    ) -> Approval:
        ttl = ttl_seconds or settings.approval_default_ttl_seconds
        approval = Approval(
            remediation_action_id=remediation.id,
            state=ApprovalState.PENDING,
            requested_role=settings.approval_required_role,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
        )
        session.add(approval)
        await session.flush()

        remediation.status = RemediationStatus.AWAITING_APPROVAL

        await self._audit.record(
            session,
            actor=Actor.system(label="services.approval"),
            action="approval.requested",
            resource_type="approval",
            resource_id=approval.id,
            payload={
                "remediation_action_id": str(remediation.id),
                "incident_id": str(incident.id),
                "action_class": remediation.action_class.value,
                "blast_radius": remediation.blast_radius,
                "requested_role": approval.requested_role,
                "expires_at": approval.expires_at.isoformat(),
            },
        )

        # Fire-and-forget on the notifier — Slack failure doesn't roll back
        # the approval (it's still visible in the UI inbox).
        await self._notifier.request_approval(
            ApprovalNotification(
                approval_id=approval.id,
                incident_id=incident.id,
                remediation_action_id=remediation.id,
                action_class=remediation.action_class.value,
                blast_radius=remediation.blast_radius,
                ai_confidence=remediation.ai_confidence,
                ai_summary=ai_summary,
                ai_reasoning=ai_reasoning,
                expires_at=approval.expires_at.isoformat(),
                requested_role=approval.requested_role,
            )
        )

        log.info(
            "approval.requested",
            approval_id=str(approval.id),
            remediation_action_id=str(remediation.id),
            ttl_seconds=ttl,
        )
        return approval

    async def decide(
        self,
        session: AsyncSession,
        *,
        approval_id: uuid.UUID,
        approve: bool,
        actor: User,
        note: str | None = None,
    ) -> ApprovalDecision:
        approval = (
            await session.execute(
                select(Approval).where(Approval.id == approval_id)
            )
        ).scalar_one_or_none()
        if approval is None:
            raise ApprovalNotFoundError(str(approval_id))
        if approval.state is not ApprovalState.PENDING:
            raise ApprovalNotPendingError(
                f"approval {approval_id} is in state {approval.state.value!r}"
            )

        remediation = (
            await session.execute(
                select(RemediationAction).where(
                    RemediationAction.id == approval.remediation_action_id
                )
            )
        ).scalar_one()

        if actor.role != UserRole.ADMIN and actor.role.value != approval.requested_role:
            raise ApprovalUnauthorizedError(
                "user role is not permitted to decide this approval"
            )

        approval.state = ApprovalState.APPROVED if approve else ApprovalState.REJECTED
        approval.decided_by_user_id = actor.id
        approval.decided_at = datetime.now(UTC)
        approval.decision_note = note

        if approve:
            remediation.status = RemediationStatus.APPROVED
        else:
            remediation.status = RemediationStatus.CANCELLED

        await self._audit.record(
            session,
            actor=Actor.user(actor.id, label=actor.email),
            action="approval.approved" if approve else "approval.rejected",
            resource_type="approval",
            resource_id=approval.id,
            payload={
                "remediation_action_id": str(remediation.id),
                "incident_id": str(remediation.incident_id),
                "note": note,
            },
        )

        log.info(
            "approval.decided",
            approval_id=str(approval.id),
            approved=approve,
            actor_id=str(actor.id),
        )
        return ApprovalDecision(
            approval_id=approval.id,
            remediation_action_id=remediation.id,
            incident_id=remediation.incident_id,
            new_state=approval.state,
            decided_by_user_id=actor.id,
            note=note,
        )

    async def expire_stale(self, session: AsyncSession) -> int:
        """Move PENDING approvals past expires_at to EXPIRED. Returns count."""
        now = datetime.now(UTC)
        stale = (
            await session.execute(
                select(Approval).where(
                    Approval.state == ApprovalState.PENDING,
                    Approval.expires_at < now,
                )
            )
        ).scalars().all()

        for approval in stale:
            approval.state = ApprovalState.EXPIRED
            approval.decided_at = now

            remediation = (
                await session.execute(
                    select(RemediationAction).where(
                        RemediationAction.id == approval.remediation_action_id
                    )
                )
            ).scalar_one()
            remediation.status = RemediationStatus.CANCELLED

            await self._audit.record(
                session,
                actor=Actor.system(label="services.approval.expire_stale"),
                action="approval.expired",
                resource_type="approval",
                resource_id=approval.id,
                payload={
                    "remediation_action_id": str(remediation.id),
                    "incident_id": str(remediation.incident_id),
                },
            )

        if stale:
            log.info("approval.expired_batch", count=len(stale))
        return len(stale)


_singleton: ApprovalService | None = None


def get_approval_service() -> ApprovalService:
    global _singleton
    if _singleton is None:
        _singleton = ApprovalService()
    return _singleton
