"""RemediationExecutor — dispatches APPROVED actions through ExecutionConnector.

Two entrypoints:
  - `execute(action_id, actor_id)` — runs an APPROVED action.
  - `rollback(action_id, reason, actor)` — runs the action's
    rollback plan (if any), via the same connector.

Both write audit chain entries at every state transition.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, get_audit_logger
from app.core.execution import ExecutionResult, UnsupportedActionError, get_execution_registry
from app.logging import get_logger
from app.models.incident import Incident, IncidentStatus
from app.models.remediation_action import RemediationAction, RemediationStatus
from app.models.user import User

log = get_logger("services.executor")


class RemediationNotFoundError(LookupError):
    pass


class RemediationNotExecutableError(RuntimeError):
    pass


@dataclass
class ExecutionOutcome:
    remediation_action_id: uuid.UUID
    new_status: RemediationStatus
    execution_result: ExecutionResult


class RemediationExecutor:
    def __init__(self) -> None:
        self._registry = get_execution_registry()
        self._audit = get_audit_logger()

    async def execute(
        self,
        session: AsyncSession,
        *,
        remediation_action_id: uuid.UUID,
        actor_id: uuid.UUID | None,
    ) -> ExecutionOutcome:
        action = (
            await session.execute(
                select(RemediationAction).where(
                    RemediationAction.id == remediation_action_id
                )
            )
        ).scalar_one_or_none()
        if action is None:
            raise RemediationNotFoundError(str(remediation_action_id))

        if action.status not in {
            RemediationStatus.APPROVED,
            RemediationStatus.POLICY_ALLOWED,
        }:
            raise RemediationNotExecutableError(
                f"action {action.id} is in state {action.status.value!r} "
                "— cannot execute"
            )

        try:
            connector = self._registry.for_action(action.action_class.value)
        except UnsupportedActionError as exc:
            action.status = RemediationStatus.FAILED
            action.failure_reason = str(exc)
            await self._audit.record(
                session,
                actor=_actor(actor_id, "services.executor"),
                action="remediation.failed",
                resource_type="remediation_action",
                resource_id=action.id,
                payload={"reason": str(exc)},
            )
            raise

        action.status = RemediationStatus.EXECUTING
        await session.flush()
        await self._audit.record(
            session,
            actor=_actor(actor_id, "services.executor"),
            action="remediation.executing",
            resource_type="remediation_action",
            resource_id=action.id,
            payload={
                "action_class": action.action_class.value,
                "connector": connector.name,
                "dry_run_candidate": True,
            },
        )

        result = await connector.execute(
            action.action_class.value,
            action.parameters,
            idempotency_key=action.idempotency_key,
        )

        if result.ok:
            action.status = RemediationStatus.EXECUTED
            action.execution_result = {
                "targets_affected": result.targets_affected,
                "provider_run_id": result.provider_run_id,
                "dry_run": result.dry_run,
            }
        else:
            action.status = RemediationStatus.FAILED
            action.failure_reason = result.error or "unknown execution failure"

        await self._audit.record(
            session,
            actor=_actor(actor_id, "services.executor"),
            action="remediation.executed" if result.ok else "remediation.failed",
            resource_type="remediation_action",
            resource_id=action.id,
            payload={
                "action_class": action.action_class.value,
                "connector": connector.name,
                "ok": result.ok,
                "dry_run": result.dry_run,
                "targets_affected": result.targets_affected,
                "error": result.error,
            },
        )

        # Roll up to incident status. CONTAINED only on a real (non dry-run)
        # success — dry-run leaves us in REMEDIATING so the demo state is
        # honest about what actually happened.
        if result.ok and not result.dry_run:
            incident = await session.get(Incident, action.incident_id)
            if incident is not None:
                incident.status = IncidentStatus.CONTAINED

        log.info(
            "remediation.executed",
            action_id=str(action.id),
            ok=result.ok,
            dry_run=result.dry_run,
        )

        return ExecutionOutcome(
            remediation_action_id=action.id,
            new_status=action.status,
            execution_result=result,
        )

    async def rollback(
        self,
        session: AsyncSession,
        *,
        remediation_action_id: uuid.UUID,
        actor: User,
        reason: str,
    ) -> ExecutionOutcome:
        action = (
            await session.execute(
                select(RemediationAction).where(
                    RemediationAction.id == remediation_action_id
                )
            )
        ).scalar_one_or_none()
        if action is None:
            raise RemediationNotFoundError(str(remediation_action_id))

        if action.status is not RemediationStatus.EXECUTED:
            raise RemediationNotExecutableError(
                f"action {action.id} is in state {action.status.value!r} "
                "— only EXECUTED actions can be rolled back"
            )
        if not action.rollback_plan:
            raise RemediationNotExecutableError(
                f"action {action.id} has no rollback_plan defined"
            )

        rollback_action_class = action.rollback_plan["action_class"]
        rollback_params = action.rollback_plan.get("parameters") or {}

        try:
            connector = self._registry.for_action(action.action_class.value)
        except UnsupportedActionError as exc:
            raise RemediationNotExecutableError(str(exc)) from exc

        if not connector.supports_rollback(action.action_class.value):
            raise RemediationNotExecutableError(
                f"connector {connector.name} cannot rollback "
                f"{action.action_class.value!r}"
            )

        await self._audit.record(
            session,
            actor=Actor.user(actor.id, label=actor.email),
            action="remediation.rollback_requested",
            resource_type="remediation_action",
            resource_id=action.id,
            payload={"reason": reason, "rollback_action_class": rollback_action_class},
        )

        result = await connector.rollback(
            action.action_class.value,
            rollback_params,
            action.execution_result,
            idempotency_key=f"rollback:{action.idempotency_key}",
        )

        if result.ok:
            action.status = RemediationStatus.ROLLED_BACK
        else:
            action.failure_reason = (
                action.failure_reason or ""
            ) + f"\nrollback_error: {result.error}"

        await self._audit.record(
            session,
            actor=Actor.user(actor.id, label=actor.email),
            action="remediation.rolled_back" if result.ok else "remediation.rollback_failed",
            resource_type="remediation_action",
            resource_id=action.id,
            payload={"ok": result.ok, "error": result.error, "dry_run": result.dry_run},
        )

        log.info(
            "remediation.rollback",
            action_id=str(action.id),
            ok=result.ok,
            reason=reason,
        )
        return ExecutionOutcome(
            remediation_action_id=action.id,
            new_status=action.status,
            execution_result=result,
        )


def _actor(actor_id: uuid.UUID | None, label: str) -> Actor:
    if actor_id is None:
        return Actor.system(label=label)
    return Actor.user(actor_id, label=label)


_singleton: RemediationExecutor | None = None


def get_remediation_executor() -> RemediationExecutor:
    global _singleton
    if _singleton is None:
        _singleton = RemediationExecutor()
    return _singleton
