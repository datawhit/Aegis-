"""WorkflowEngine protocol — engine-neutral execution surface.

The surface is deliberately small (submit / get_status / cancel / rollback).
This is the constraint that lets us swap Celery for Temporal later without
rewriting callers — but it also means callers cannot reach for engine-
specific features (chord/group/replay). When a caller wants more, we widen
the protocol *here*, not in the implementation.

See [docs/DECISIONS.md](../../../../docs/DECISIONS.md) ADR-002.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


class WorkflowStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class WorkflowRunSnapshot:
    id: uuid.UUID
    workflow_name: str
    status: WorkflowStatus
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    engine_run_id: str | None


class WorkflowNotFoundError(LookupError):
    """Raised when a run_id is not present in the workflow_runs table."""


@runtime_checkable
class WorkflowEngine(Protocol):
    async def submit(
        self,
        workflow_name: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        actor_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Submit a workflow for execution.

        If a run with `idempotency_key` already exists, returns its ID instead
        of creating a new one. This is what makes retries safe at the engine
        boundary — callers (e.g., the Remediation Decision Engine) don't need
        their own dedup logic.
        """
        ...

    async def get_status(self, run_id: uuid.UUID) -> WorkflowRunSnapshot: ...

    async def cancel(self, run_id: uuid.UUID, reason: str) -> None: ...

    async def request_rollback(
        self,
        run_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
    ) -> uuid.UUID:
        """Submit the rollback workflow for `run_id`.

        Returns the new rollback run's ID. Implementations look up the
        original run's `payload` to determine the rollback plan; callers
        must not pass arbitrary rollback parameters here — the rollback
        must be the one declared by the original remediation action.
        """
        ...
