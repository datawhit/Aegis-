"""Ingest endpoint response schemas."""
from __future__ import annotations

import uuid

from pydantic import BaseModel


class IngestAccepted(BaseModel):
    accepted: bool = True
    alert_id: uuid.UUID
    workflow_run_id: uuid.UUID
    duplicate: bool = False
