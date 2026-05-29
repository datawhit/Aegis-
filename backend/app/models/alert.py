"""Alert model — normalized signal ingested from a source system."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    NEW = "new"
    TRIAGED = "triaged"
    LINKED = "linked"  # rolled into an incident
    SUPPRESSED = "suppressed"
    DUPLICATE = "duplicate"


class Alert(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "alerts"

    # Origin (source = "defender" | "okta" | etc.)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(256), nullable=False)
    correlation_key: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

    # Classification
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alert_severity", native_enum=False),
        default=AlertSeverity.LOW,
        nullable=False,
    )
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status", native_enum=False),
        default=AlertStatus.NEW,
        nullable=False,
        index=True,
    )

    # Linkage
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Payload — the raw + normalized event. Kept as JSONB for query flexibility
    # while we learn what fields actually matter.
    raw_event: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    normalized: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        Index(
            "uq_alerts_source_event",
            "source",
            "source_event_id",
            unique=True,
        ),
    )
