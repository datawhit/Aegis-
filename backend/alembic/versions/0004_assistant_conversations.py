"""Add assistant_conversations + assistant_messages tables.

Revision ID: 0004_assistant_conversations
Revises: 0003_audit_logs_clock_timestamp
Create Date: 2026-05-30 (Sprint 13)

Backs the conversational Aegis Assistant — per-user chat threads
with their full turn-by-turn transcript. Read-only-by-design (ADR-023)
still holds: this is transcript persistence, not state that drives
action.

`assistant_messages.created_at` uses `clock_timestamp()` for the same
reason `audit_logs.created_at` does (see migration 0003): NOW() is
transaction-fixed, so multiple inserts in one txn would share an
instant and break chronological replay.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_assistant_conversations"
down_revision: Union[str, None] = "0003_audit_logs_clock_timestamp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_assistant_conv_user_updated",
        "assistant_conversations",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "assistant_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "tool_calls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("model", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_assistant_msg_conv_created",
        "assistant_messages",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_msg_conv_created", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_conv_user_updated", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
