"""Aegis Assistant conversation persistence (Sprint 13).

Two tables back the conversational Assistant:

- `assistant_conversations` — one row per chat thread. Owner is the
  user; title is auto-derived from the first user message (truncated).
- `assistant_messages` — every turn (user + assistant) in insertion
  order. Sources and tool_calls are JSONB so the UI can rebuild the
  source-link chips when loading a prior transcript.

Read-only-by-design (ADR-023) means we never persist server-side state
that drives action; this table is a transcript only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class AssistantConversation(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "assistant_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (Index("ix_assistant_conv_user_updated", "user_id", "updated_at"),)


class AssistantMessage(Base, UUIDPKMixin):
    __tablename__ = "assistant_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # clock_timestamp() — same reason as audit_logs (Sprint 3 migration
    # 0003): NOW() is transaction-fixed and turns within one txn would
    # share an instant, breaking chronological ordering.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(String, nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    tool_calls: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_assistant_msg_conv_created", "conversation_id", "created_at"),)
