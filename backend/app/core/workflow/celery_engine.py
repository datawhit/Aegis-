"""Celery-backed WorkflowEngine.

Design notes:

- Workflow state is the **DB row**, not Celery's result. Celery is just the
  dispatcher. This means we keep one place to query "what is run X doing"
  and we don't depend on the Celery result backend for correctness.
- The actual task functions live in `app.workers` and are registered by
  workflow name on a registry. Phase 0 has no real tasks yet — Sprint 1
  introduces the first one (alert ingestion).
- Rollback in Celery is a *separately submitted workflow* that runs a
  `<name>__rollback` task. This is one of the seams that makes the
  Temporal migration mechanical: Temporal natively models compensations,
  so the rollback dispatch collapses into the workflow definition itself.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.workflow.base import (
    WorkflowEngine,
    WorkflowNotFoundError,
    WorkflowRunSnapshot,
    WorkflowStatus,
)
from app.db import session_scope
from app.logging import get_logger
from app.models.workflow_run import WorkflowEngineKind, WorkflowRun
from app.models.workflow_run import WorkflowStatus as ORMWorkflowStatus

log = get_logger("workflow.celery")


class CeleryWorkflowEngine(WorkflowEngine):
    async def submit(
        self,
        workflow_name: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        actor_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        async with session_scope() as session:
            # Idempotency check: return the existing run's ID rather than
            # creating a duplicate.
            existing = await session.execute(
                select(WorkflowRun).where(WorkflowRun.idempotency_key == idempotency_key)
            )
            existing_run = existing.scalar_one_or_none()
            if existing_run is not None:
                log.info(
                    "workflow.submit.idempotent_hit",
                    run_id=str(existing_run.id),
                    workflow_name=workflow_name,
                )
                return existing_run.id

            run = WorkflowRun(
                engine=WorkflowEngineKind.CELERY,
                workflow_name=workflow_name,
                idempotency_key=idempotency_key,
                payload=payload,
                status=ORMWorkflowStatus.PENDING,
                submitted_by_user_id=actor_id,
            )
            session.add(run)
            await session.flush()
            run_id = run.id

        # Dispatch *after* the DB commit. If the dispatch fails, the run sits
        # in PENDING and a reconciler (Sprint 2) will pick it up. We do not
        # want the row missing when the worker tries to update status.
        from app.workers.celery_app import celery_app  # local import to avoid cycle

        celery_app.send_task(
            f"workflows.{workflow_name}",
            args=[str(run_id)],
            task_id=str(run_id),
        )
        log.info(
            "workflow.submit",
            run_id=str(run_id),
            workflow_name=workflow_name,
        )
        return run_id

    async def get_status(self, run_id: uuid.UUID) -> WorkflowRunSnapshot:
        async with session_scope() as session:
            run = await session.get(WorkflowRun, run_id)
            if run is None:
                raise WorkflowNotFoundError(str(run_id))
            return WorkflowRunSnapshot(
                id=run.id,
                workflow_name=run.workflow_name,
                status=WorkflowStatus(run.status.value),
                payload=run.payload,
                result=run.result,
                error=run.error,
                started_at=run.started_at,
                completed_at=run.completed_at,
                engine_run_id=run.engine_run_id,
            )

    async def cancel(self, run_id: uuid.UUID, reason: str) -> None:
        from app.workers.celery_app import celery_app

        async with session_scope() as session:
            run = await session.get(WorkflowRun, run_id)
            if run is None:
                raise WorkflowNotFoundError(str(run_id))

            # Only cancel from non-terminal states.
            if run.status in {
                ORMWorkflowStatus.COMPLETED,
                ORMWorkflowStatus.FAILED,
                ORMWorkflowStatus.CANCELLED,
                ORMWorkflowStatus.ROLLED_BACK,
            }:
                log.info(
                    "workflow.cancel.skip_terminal",
                    run_id=str(run_id),
                    status=run.status.value,
                )
                return

            run.status = ORMWorkflowStatus.CANCELLED
            run.error = f"cancelled: {reason}"
            run.completed_at = datetime.now(UTC)

        celery_app.control.revoke(str(run_id), terminate=True)
        log.info("workflow.cancel", run_id=str(run_id), reason=reason)

    async def request_rollback(
        self,
        run_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
    ) -> uuid.UUID:
        async with session_scope() as session:
            original = await session.get(WorkflowRun, run_id)
            if original is None:
                raise WorkflowNotFoundError(str(run_id))

            rollback_run = WorkflowRun(
                engine=WorkflowEngineKind.CELERY,
                workflow_name=f"{original.workflow_name}__rollback",
                idempotency_key=f"rollback:{run_id}",
                payload={"original_run_id": str(run_id), "reason": reason},
                status=ORMWorkflowStatus.PENDING,
                submitted_by_user_id=actor_id,
                rollback_of_run_id=original.id,
            )
            session.add(rollback_run)
            await session.flush()
            rollback_id = rollback_run.id

        from app.workers.celery_app import celery_app

        celery_app.send_task(
            f"workflows.{original.workflow_name}__rollback",
            args=[str(rollback_id)],
            task_id=str(rollback_id),
        )
        log.info(
            "workflow.rollback.submit",
            original_run_id=str(run_id),
            rollback_run_id=str(rollback_id),
            reason=reason,
        )
        return rollback_id
