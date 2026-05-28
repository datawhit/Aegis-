"""Incident model — a correlated cluster of one or more alerts.

An incident is the unit that the AI triage engine reasons about. Remediation
actions, approvals, and audit history all hang off the incident.
"""
from __future__ import annotations

import enum

from sqlalchemy import Enum, Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.alert import AlertSeverity
from app.models.base import Base, TimestampMixin, UUIDPKMixin


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    AWAITING_APPROVAL = "awaiting_approval"
    REMEDIATING = "remediating"
    CONTAINED = "contained"
    CLOSED_RESOLVED = "closed_resolved"
    CLOSED_FALSE_POSITIVE = "closed_false_positive"
    ESCALATED = "escalated"


class Incident(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "incidents"

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)

    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alert_severity", native_enum=False, create_type=False),
        default=AlertSeverity.MEDIUM,
        nullable=False,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", native_enum=False),
        default=IncidentStatus.OPEN,
        nullable=False,
        index=True,
    )

    # AI-reported confidence in the classification (0.0 — 1.0). Nullable
    # because human-created incidents won't have one.
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # MITRE ATT&CK mapping (list of technique IDs like ["T1078", "T1059.003"])
    mitre_techniques: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    # Affected entities (users, hosts, services) — JSONB for flexibility while
    # we settle the schema.
    affected_entities: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_incidents_status_severity", "status", "severity"),
    )
