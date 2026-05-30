"""Add `aegis_audit_writer` Postgres role with INSERT-only grant on audit_logs.

Revision ID: 0002_audit_writer_role
Revises: 0001_initial
Create Date: 2026-05-27 (Sprint 02)

Closes Sprint 0 D-1 / ADR-006. The role is created if it does not already
exist, password set to a placeholder that operators MUST rotate before
production. Application code uses this role via `AEGIS_AUDIT_WRITER_DATABASE_URL`;
when that env var is unset the migration is still safe — the role just sits
unused, and the audit logger continues to use the main pool.

Note: the migration is intentionally idempotent and avoids dropping the role
on downgrade. If the role has been customized by an operator, a downgrade
shouldn't blow it away.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002_audit_writer_role"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ROLE = "aegis_audit_writer"
# Placeholder password. Operators MUST rotate via:
#   ALTER ROLE aegis_audit_writer WITH PASSWORD '<long random>';
# This is logged at app startup if the role's DSN is configured but the
# placeholder is detected.
_DEFAULT_PASSWORD = "REPLACE_ME_BEFORE_PRODUCTION"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                CREATE ROLE {_ROLE}
                    LOGIN PASSWORD '{_DEFAULT_PASSWORD}'
                    NOINHERIT NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$;
        """
    )
    # Grant connect on the current database + usage on schema public.
    # CURRENT_DATABASE() is a function, not an identifier — use a DO block
    # with EXECUTE format() so the migration runs against whichever DB it's
    # applied to (aegis locally, aegis_test in CI).
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO {_ROLE}', current_database());
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_ROLE};")

    # INSERT only on audit_logs. No SELECT (Phase 2 doesn't surface audit
    # queries through this role; the regular app role retains SELECT).
    op.execute(f"GRANT INSERT ON TABLE audit_logs TO {_ROLE};")

    # Also grant on the implicit sequence behind the id default. With our
    # UUID PK the id is generated app-side, but if a future migration adds
    # a sequence-backed column we want this grant pattern documented.
    # (No sequences exist on audit_logs in Phase 0; this is a no-op.)


def downgrade() -> None:
    # Conservative: revoke grants, but leave the role alive in case operators
    # have customized it. Operators can `DROP ROLE` manually.
    op.execute(f"REVOKE INSERT ON TABLE audit_logs FROM {_ROLE};")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {_ROLE};")
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM {_ROLE}', current_database());
        END
        $$;
        """
    )
