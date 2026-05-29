"""Celery tasks for remediation execution + rollback + approval expiry."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.audit import Actor, get_audit_logger
from app.db import session_scope
from app.logging import configure_logging, get_logger
from app.models.workflow_run import WorkflowRun, WorkflowStatus
from app.services.approval_service import get_approval_service
from app.services.remediation_executor import (
    RemediationNotExecutableError,
    RemediationNotFoundError,
    get_remediation_executor,
)
from app.workers.celery_app import celery_app

configure_logging()
log = get_logger("workers.remediation")


@celery_app.task(name="workflows.execute_remediation", acks_late=True)
def execute_remediation(workflow_run_id: str) -> dict:
    return asyncio.run(_execute(uuid.UUID(workflow_run_id)))


@celery_app.task(name="workflows.execute_remediation__rollback", acks_late=True)
def execute_remediation_rollback(workflow_run_id: str) -> dict:
    return asyncio.run(_rollback_via_engine(uuid.UUID(workflow_run_id)))


@celery_app.task(name="workflows.expire_stale_approvals", acks_late=True)
def expire_stale_approvals() -> dict:
    return asyncio.run(_expire())


# --- internals -------------------------------------------------------------
async def _execute(workflow_run_id: uuid.UUID) -> dict:
    async with session_scope() as session:
        run = await session.get(WorkflowRun, workflow_run_id)
        if run is None:
            return {"ok": False, "reason": "run_missing"}
        if run.status != WorkflowStatus.PENDING:
            return {"ok": True, "reason": "already_processed"}

        action_id_str = run.payload.get("remediation_action_id")
        if not action_id_str:
            run.status = WorkflowStatus.FAILED
            run.error = "payload missing remediation_action_id"
            run.completed_at = datetime.now(UTC)
            return {"ok": False, "reason": "missing_action_id"}

        run.status = WorkflowStatus.RUNNING
        run.started_at = datetime.now(UTC)

    try:
        async with session_scope() as session:
            executor = get_remediation_executor()
            outcome = await executor.execute(
                session,
                remediation_action_id=uuid.UUID(action_id_str),
                actor_id=run.submitted_by_user_id,
            )
    except RemediationNotFoundError as exc:
        async with session_scope() as session:
            run = await session.get(WorkflowRun, workflow_run_id)
            if run is not None:
                run.status = WorkflowStatus.FAILED
                run.error = str(exc)
                run.completed_at = datetime.now(UTC)
        return {"ok": False, "reason": "action_missing", "error": str(exc)}
    except RemediationNotExecutableError as exc:
        async with session_scope() as session:
            run = await session.get(WorkflowRun, workflow_run_id)
            if run is not None:
                run.status = WorkflowStatus.FAILED
                run.error = str(exc)
                run.completed_at = datetime.now(UTC)
        return {"ok": False, "reason": "not_executable", "error": str(exc)}

    async with session_scope() as session:
        run = await session.get(WorkflowRun, workflow_run_id)
        if run is not None:
            run.status = (
                WorkflowStatus.COMPLETED if outcome.execution_result.ok else WorkflowStatus.FAILED
            )
            run.completed_at = datetime.now(UTC)
            run.result = {
                "remediation_action_id": str(outcome.remediation_action_id),
                "new_status": outcome.new_status.value,
                "ok": outcome.execution_result.ok,
                "dry_run": outcome.execution_result.dry_run,
            }
        payload: dict[str, Any] = dict(run.result) if run is not None and run.result else {}
        await get_audit_logger().record(
            session,
            actor=Actor.system(label="workers.remediation"),
            action="workflow.execute_completed",
            resource_type="workflow_run",
            resource_id=workflow_run_id,
            payload=payload,
        )

    log.info(
        "remediation.workflow_complete",
        run_id=str(workflow_run_id),
        ok=outcome.execution_result.ok,
    )
    return {"ok": outcome.execution_result.ok}


async def _rollback_via_engine(workflow_run_id: uuid.UUID) -> dict:
    # The engine creates this run with payload = {"original_run_id": ..., "reason": ...}.
    # We resolve the original run's action and call executor.rollback.
    async with session_scope() as session:
        run = await session.get(WorkflowRun, workflow_run_id)
        if run is None:
            return {"ok": False, "reason": "rollback_run_missing"}
        if run.status != WorkflowStatus.PENDING:
            return {"ok": True, "reason": "already_processed"}

        original_run_id = run.payload.get("original_run_id")
        reason = run.payload.get("reason") or "rollback"
        if not original_run_id:
            run.status = WorkflowStatus.FAILED
            run.error = "missing original_run_id"
            run.completed_at = datetime.now(UTC)
            return {"ok": False, "reason": "missing_original_run_id"}

        original = await session.get(WorkflowRun, uuid.UUID(original_run_id))
        if original is None:
            run.status = WorkflowStatus.FAILED
            run.error = "original run missing"
            run.completed_at = datetime.now(UTC)
            return {"ok": False, "reason": "original_run_missing"}

        action_id_str = original.result.get("remediation_action_id") if original.result else None
        if not action_id_str:
            run.status = WorkflowStatus.FAILED
            run.error = "original run has no remediation_action_id"
            run.completed_at = datetime.now(UTC)
            return {"ok": False, "reason": "no_action_id_on_original"}

        run.status = WorkflowStatus.RUNNING
        run.started_at = datetime.now(UTC)

    # NB: rollback is initiated by the workflow engine (system actor here).
    # User-initiated rollbacks come through `POST /remediations/{id}/rollback`
    # and call executor.rollback() directly with the User actor.
    log.warning(
        "remediation.engine_rollback",
        run_id=str(workflow_run_id),
        reason=reason,
    )
    # Phase 2: engine-initiated rollback dispatch is wired but not exercised.
    # Real triggers (failed execution mid-batch, policy-revocation) ship in
    # Phase 3. Keeping the path here so the abstraction is honest.
    async with session_scope() as session:
        run = await session.get(WorkflowRun, workflow_run_id)
        if run is not None:
            run.status = WorkflowStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            run.result = {"engine_initiated_rollback": False, "reason": reason}
    return {"ok": True, "note": "engine-initiated rollback no-op in Phase 2"}


async def _expire() -> dict:
    async with session_scope() as session:
        n = await get_approval_service().expire_stale(session)
    return {"expired": n}
