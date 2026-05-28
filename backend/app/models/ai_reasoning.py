"""AI reasoning snapshot — frozen at decision time, referenced by audit log.

Captures *everything* needed to explain why the AI made a decision: the
model, the prompt, the evidence it considered, the policies it referenced,
its confidence, and the structured output. This is the foundation of the
"explainability" leg of the product.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class AIReasoningSnapshot(Base, UUIDPKMixin):
    __tablename__ = "ai_reasoning_snapshots"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Provenance
    provider: Mapped[str] = mapped_column(String(32), nullable=False)         # "anthropic", "openai"
    model: Mapped[str] = mapped_column(String(128), nullable=False)           # exact model ID
    prompt_template_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Subject of the reasoning
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Inputs
    # `evidence` is the structured set of alert/incident data shown to the model.
    # `prompt` is the rendered prompt text (or a content-addressed pointer if
    # we move to S3 in Sprint 3+ for cost reasons).
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    prompt: Mapped[str] = mapped_column(String, nullable=False)

    # Outputs
    structured_output: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    raw_response: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Cost / latency telemetry
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
