"""Approval model — human-in-the-loop approval state machine."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ApprovalState(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "approvals"

    remediation_action_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("remediation_actions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    state: Mapped[ApprovalState] = mapped_column(
        Enum(ApprovalState, name="approval_state", native_enum=False),
        default=ApprovalState.PENDING,
        nullable=False,
        index=True,
    )

    requested_role: Mapped[str] = mapped_column(String(32), nullable=False)

    # When the approval request expires. If pending past expiry → state moves
    # to EXPIRED and the action is escalated to on-call.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String, nullable=True)
