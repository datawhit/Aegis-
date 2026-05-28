"""WorkflowRun model — engine-agnostic workflow execution state.

Tracked in Postgres so the API can answer status queries without depending
on the engine's internal state store. The engine itself (Celery in Phase 0)
writes lifecycle transitions here.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class WorkflowStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class WorkflowEngineKind(str, enum.Enum):
    CELERY = "celery"
    TEMPORAL = "temporal"


class WorkflowRun(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "workflow_runs"

    engine: Mapped[WorkflowEngineKind] = mapped_column(
        Enum(WorkflowEngineKind, name="workflow_engine_kind", native_enum=False),
        default=WorkflowEngineKind.CELERY,
        nullable=False,
    )
    workflow_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Idempotency: callers pass this to dedupe submissions. Unique.
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, name="workflow_status", native_enum=False),
        default=WorkflowStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Engine-side identifier (Celery task ID, Temporal workflow ID).
    engine_run_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # If this run is a rollback for another run, this points at the original.
    rollback_of_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
