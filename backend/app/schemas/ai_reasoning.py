"""AI reasoning snapshot — read schema."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AIReasoningRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    provider: str
    model: str
    prompt_template_id: str | None
    structured_output: dict = Field(default_factory=dict)
    confidence: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    # Full rendered prompt (post-PII redaction). Surfaced behind a UI
    # disclosure — the operator should be able to inspect what the model
    # actually saw (Q11).
    prompt: str | None = None
