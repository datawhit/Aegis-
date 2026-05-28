"""Alert-facing schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    source_event_id: str
    correlation_key: str | None
    severity: str
    status: str
    incident_id: uuid.UUID | None
    created_at: datetime
    normalized: dict = Field(default_factory=dict)
