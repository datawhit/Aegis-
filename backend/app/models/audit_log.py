"""Audit log — append-only, SHA-256 hash chained.

See [docs/DECISIONS.md](../../../docs/DECISIONS.md) ADR-004 for the integrity
model and ADR-006 for the DB-role enforcement plan.

Two invariants this model enforces structurally:
  1. `entry_hash` is NOT NULL — every row is hashed.
  2. `created_at` is server-set so client clocks can't lie about ordering.

The hash chain itself (prev_hash + canonical content → entry_hash) is computed
by `app.core.audit.logger.HashChainAuditLogger`. Computing it in the model
would create a hidden ORM side-effect; computing it in the logger keeps the
contract explicit.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class ActorType(str, enum.Enum):
    USER = "user"           # a human, identified by users.id
    SYSTEM = "system"       # internal scheduler/cron
    AI = "ai"               # AI triage / decision engine
    INTEGRATION = "integration"   # inbound webhook from an external system
    SERVICE = "service"     # service-account user


class AuditLog(Base, UUIDPKMixin):
    __tablename__ = "audit_logs"

    # Server-side timestamp — clients cannot reorder history.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Who acted
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type", native_enum=False),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    actor_label: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # What happened
    action: Mapped[str] = mapped_column(String(128), nullable=False)             # e.g. "incident.created"
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)      # e.g. "incident"
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

    # Why / how (free-form structured payload + optional AI reasoning ref)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    reasoning_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

    # Hash chain
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    __table_args__ = (
        Index("ix_audit_actor", "actor_type", "actor_id"),
        Index("ix_audit_resource", "resource_type", "resource_id"),
        Index("ix_audit_created_desc", "created_at"),
    )
