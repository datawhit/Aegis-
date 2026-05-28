"""Initial schema — Phase 0 foundation.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-27

Tables created (in FK-safe order):
  users, incidents, alerts, policies, workflow_runs, remediation_actions,
  approvals, audit_logs, ai_reasoning_snapshots.

Also enables the pgvector extension. No vector columns are added yet — they
arrive in Sprint 1 with the RAG layer — but flipping the extension on in
Phase 0 avoids a migration-time surprise.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- users ---------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("auth_provider", sa.String(32), nullable=False, server_default="local"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # --- incidents -----------------------------------------------------------
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("mitre_techniques", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("affected_entities", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_status_severity", "incidents", ["status", "severity"])

    # --- alerts --------------------------------------------------------------
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_event_id", sa.String(256), nullable=False),
        sa.Column("correlation_key", sa.String(256), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False, server_default="low"),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_event", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("normalized", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"],
            name="fk_alerts_incident_id_incidents",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("source", "source_event_id", name="uq_alerts_source_event"),
    )
    op.create_index("ix_alerts_correlation_key", "alerts", ["correlation_key"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_incident_id", "alerts", ["incident_id"])

    # --- policies ------------------------------------------------------------
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("effect", sa.String(16), nullable=False, server_default="escalate"),
        sa.Column("match", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("constraints", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("name", name="uq_policies_name"),
    )

    # --- workflow_runs -------------------------------------------------------
    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("engine", sa.String(32), nullable=False, server_default="celery"),
        sa.Column("workflow_name", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("engine_run_id", sa.String(256), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rollback_of_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"], ["users.id"],
            name="fk_workflow_runs_submitted_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rollback_of_run_id"], ["workflow_runs.id"],
            name="fk_workflow_runs_rollback_of_run_id_workflow_runs",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_workflow_runs_idempotency_key"),
    )
    op.create_index("ix_workflow_runs_workflow_name", "workflow_runs", ["workflow_name"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    # --- remediation_actions -------------------------------------------------
    op.create_table(
        "remediation_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_class", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("rollback_plan", postgresql.JSONB(), nullable=True),
        sa.Column("blast_radius", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_result", postgresql.JSONB(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"],
            name="fk_remediation_actions_incident_id_incidents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"],
            name="fk_remediation_actions_workflow_run_id_workflow_runs",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_remediation_actions_idempotency_key"),
    )
    op.create_index("ix_remediation_actions_incident_id", "remediation_actions", ["incident_id"])
    op.create_index("ix_remediation_actions_status", "remediation_actions", ["status"])

    # --- approvals -----------------------------------------------------------
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("remediation_action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("requested_role", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["remediation_action_id"], ["remediation_actions.id"],
            name="fk_approvals_remediation_action_id_remediation_actions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"],
            name="fk_approvals_decided_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "remediation_action_id", name="uq_approvals_remediation_action_id"
        ),
    )
    op.create_index("ix_approvals_state", "approvals", ["state"])

    # --- ai_reasoning_snapshots ---------------------------------------------
    op.create_table(
        "ai_reasoning_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_template_id", sa.String(128), nullable=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("structured_output", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("raw_response", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.id"],
            name="fk_ai_reasoning_snapshots_incident_id_incidents",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_ai_reasoning_snapshots_incident_id", "ai_reasoning_snapshots", ["incident_id"])

    # --- audit_logs (last; references several tables logically) -------------
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_label", sa.String(256), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("reasoning_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("entry_hash", name="uq_audit_logs_entry_hash"),
    )
    op.create_index("ix_audit_actor", "audit_logs", ["actor_type", "actor_id"])
    op.create_index("ix_audit_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_created_desc", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("ai_reasoning_snapshots")
    op.drop_table("approvals")
    op.drop_table("remediation_actions")
    op.drop_table("workflow_runs")
    op.drop_table("policies")
    op.drop_table("alerts")
    op.drop_table("incidents")
    op.drop_table("users")
    # Leave the `vector` extension in place — other databases on the cluster
    # may rely on it.
