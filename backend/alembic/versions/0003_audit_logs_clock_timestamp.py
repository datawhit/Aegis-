"""Switch audit_logs.created_at default from now() to clock_timestamp().

Revision ID: 0003_audit_logs_clock_timestamp
Revises: 0002_audit_writer_role
Create Date: 2026-05-29 (Sprint 04 follow-up)

NOW() (== `transaction_timestamp()`) is fixed at transaction start, so
multiple `audit_logs` inserts inside one transaction share a `created_at`.
The hash-chain writer locates the tip via `ORDER BY created_at DESC, id
DESC` and the verifier walks via `ORDER BY created_at ASC, id ASC`.
When created_at ties, the id tiebreaker (random UUIDv4) is not
consistent with insert order — the chain can fork between the writer
and the verifier reads back a different order than was written.

`clock_timestamp()` returns wall-clock time at the moment of the call,
giving microsecond-distinct values per insert and making the
(created_at, id) ordering reflect actual insertion order.

This migration is data-safe — only the column default changes. Existing
rows keep their stored timestamps.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_audit_logs_clock_timestamp"
down_revision: Union[str, None] = "0002_audit_writer_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "audit_logs",
        "created_at",
        server_default=sa.text("clock_timestamp()"),
    )


def downgrade() -> None:
    op.alter_column(
        "audit_logs",
        "created_at",
        server_default=sa.text("now()"),
    )
