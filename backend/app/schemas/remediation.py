"""Remediation request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RollbackRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1024)
