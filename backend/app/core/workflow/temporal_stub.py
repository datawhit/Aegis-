"""Temporal-backed WorkflowEngine — stub.

Implementation arrives when any of the ADR-002 migration triggers are met.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.core.workflow.base import WorkflowEngine, WorkflowRunSnapshot


class TemporalWorkflowEngine(WorkflowEngine):
    async def submit(
        self,
        workflow_name: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        actor_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        raise NotImplementedError("Temporal engine not yet implemented; see ADR-002.")

    async def get_status(self, run_id: uuid.UUID) -> WorkflowRunSnapshot:
        raise NotImplementedError("Temporal engine not yet implemented; see ADR-002.")

    async def cancel(self, run_id: uuid.UUID, reason: str) -> None:
        raise NotImplementedError("Temporal engine not yet implemented; see ADR-002.")

    async def request_rollback(
        self,
        run_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
    ) -> uuid.UUID:
        raise NotImplementedError("Temporal engine not yet implemented; see ADR-002.")
