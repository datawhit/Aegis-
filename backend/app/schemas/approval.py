"""Approval schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    remediation_action_id: uuid.UUID
    state: str
    requested_role: str
    expires_at: datetime
    decided_by_user_id: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime


class ApprovalListItem(BaseModel):
    """Inbox row — joins enough fields to render without N+1 fetches."""

    approval: ApprovalRead
    incident_id: uuid.UUID
    incident_title: str
    incident_severity: str
    action_class: str
    blast_radius: int
    ai_confidence: float | None
    ai_summary: str | None


class ApprovalList(BaseModel):
    items: list[ApprovalListItem]


class ApprovalDecisionRequest(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=1024)
