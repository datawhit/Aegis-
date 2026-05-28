"""Incident schemas (list + detail)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai_reasoning import AIReasoningRead
from app.schemas.alert import AlertRead


class IncidentSummary(BaseModel):
    """List-view item: keep it light, no joined data."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    severity: str
    status: str
    ai_confidence: float | None
    mitre_techniques: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RemediationActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_class: str
    status: str
    parameters: dict = Field(default_factory=dict)
    rollback_plan: dict | None
    blast_radius: int
    ai_confidence: float | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class IncidentDetail(IncidentSummary):
    summary: str | None
    affected_entities: dict = Field(default_factory=dict)
    alerts: list[AlertRead] = Field(default_factory=list)
    remediation_actions: list[RemediationActionRead] = Field(default_factory=list)
    reasoning_snapshots: list[AIReasoningRead] = Field(default_factory=list)


class IncidentList(BaseModel):
    items: list[IncidentSummary]
    total: int
    limit: int
    offset: int
