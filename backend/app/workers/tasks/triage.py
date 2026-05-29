"""`workflows.triage_alert` — runs the triage pipeline for a single alert.

The Celery worker dispatches this when the ingest endpoint submits a new
workflow run. The task:

  1. Loads the `WorkflowRun` row, transitions PENDING → RUNNING.
  2. Loads the `Alert` (the run's payload carries `alert_id`).
  3. Calls `IncidentService.handle_new_alert()` — which triages, correlates,
     proposes remediation, and runs policy eval inside one transaction.
  4. Transitions the run to COMPLETED or FAILED.

The task itself is sync (Celery's `@celery_app.task` is sync); we use
`asyncio.run(...)` to drive the async pipeline. This is fine — each task
runs in its own worker process with no event loop above it.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.audit import Actor, get_audit_logger
from app.db import session_scope
from app.logging import configure_logging, get_logger
from app.models.alert import Alert
from app.models.workflow_run import WorkflowRun, WorkflowStatus
from app.services.incident_service import get_incident_service
from app.workers.celery_app import celery_app

configure_logging()
log = get_logger("workers.triage")


@celery_app.task(name="workflows.triage_alert", bind=True, acks_late=True)
def triage_alert(self: Any, workflow_run_id: str) -> dict:
    return asyncio.run(_run(uuid.UUID(workflow_run_id)))


async def _run(workflow_run_id: uuid.UUID) -> dict:
    async with session_scope() as session:
        run = await session.get(WorkflowRun, workflow_run_id)
        if run is None:
            log.error("triage.run_missing", run_id=str(workflow_run_id))
            return {"ok": False, "reason": "run_missing"}

        if run.status != WorkflowStatus.PENDING:
            # Re-delivery from the broker. Idempotency: don't redo work.
            log.info(
                "triage.run_not_pending",
                run_id=str(run.id),
                status=run.status.value,
            )
            return {"ok": True, "reason": "already_processed"}

        alert_id_str = run.payload.get("alert_id")
        if not alert_id_str:
            run.status = WorkflowStatus.FAILED
            run.error = "payload missing alert_id"
            run.completed_at = datetime.now(UTC)
            return {"ok": False, "reason": "missing_alert_id"}

        alert = await session.get(Alert, uuid.UUID(alert_id_str))
        if alert is None:
            run.status = WorkflowStatus.FAILED
            run.error = f"alert not found: {alert_id_str}"
            run.completed_at = datetime.now(UTC)
            return {"ok": False, "reason": "alert_missing"}

        run.status = WorkflowStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await session.flush()

    # Run the pipeline in its own transaction so partial failures are visible.
    try:
        async with session_scope() as session:
            service = get_incident_service()
            alert = await session.get(Alert, uuid.UUID(alert_id_str))
            assert alert is not None  # narrowing — checked above
            result = await service.handle_new_alert(session, alert)
    except Exception as exc:  # pragma: no cover — defensive
        log.exception("triage.pipeline_failed", run_id=str(workflow_run_id), error=str(exc))
        async with session_scope() as session:
            run = await session.get(WorkflowRun, workflow_run_id)
            if run is not None:
                run.status = WorkflowStatus.FAILED
                run.error = str(exc)[:4096]
                run.completed_at = datetime.now(UTC)
        return {"ok": False, "reason": "pipeline_failed", "error": str(exc)}

    async with session_scope() as session:
        run = await session.get(WorkflowRun, workflow_run_id)
        if run is not None:
            run.status = WorkflowStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            run.result = {
                "incident_id": str(result.incident_id),
                "remediation_action_id": str(result.remediation_action_id)
                if result.remediation_action_id
                else None,
                "policy_effect": result.policy_effect.value,
                "is_new_incident": result.is_new_incident,
                "ai_failed": result.triage_decision.ai_failed,
            }

        # Audit chain entry tying this workflow run to the resulting incident.
        await get_audit_logger().record(
            session,
            actor=Actor.system(label="workers.triage"),
            action="workflow.triage_completed",
            resource_type="workflow_run",
            resource_id=workflow_run_id,
            payload={
                "incident_id": str(result.incident_id),
                "policy_effect": result.policy_effect.value,
                "remediation_action_id": str(result.remediation_action_id)
                if result.remediation_action_id
                else None,
            },
            reasoning_snapshot_id=result.triage_decision.reasoning_snapshot_id,
        )

    log.info(
        "triage.completed",
        run_id=str(workflow_run_id),
        incident_id=str(result.incident_id),
        policy_effect=result.policy_effect.value,
    )
    return {
        "ok": True,
        "incident_id": str(result.incident_id),
        "policy_effect": result.policy_effect.value,
    }
