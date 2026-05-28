"""Policy model — governance rules evaluated by the PolicyEngine."""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class PolicyEffect(str, enum.Enum):
    ALLOW = "allow"
    ESCALATE = "escalate"
    DENY = "deny"


class Policy(Base, UUIDPKMixin, TimestampMixin):
    """A declarative policy rule.

    `match` and `constraints` are JSONB so we can iterate on the DSL without
    schema churn. A formal CEL-like DSL ships in Sprint 2 (see
    docs/DECISIONS.md ADR-005).
    """

    __tablename__ = "policies"

    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Higher priority wins on conflict; conflicts at equal priority → ESCALATE.
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    effect: Mapped[PolicyEffect] = mapped_column(
        Enum(PolicyEffect, name="policy_effect", native_enum=False),
        default=PolicyEffect.ESCALATE,
        nullable=False,
    )

    # Match expression. Phase 0 supports simple key/value equality;
    # Sprint 2 adds the real DSL.
    match: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Action-class-specific constraints: confidence threshold, blast radius cap,
    # required approver role, rollback-required flag, etc.
    constraints: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
