"""RemediationAction model — proposed and/or executed response actions."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class RemediationActionClass(str, enum.Enum):
    # Identity
    REVOKE_USER_SESSIONS = "revoke_user_sessions"
    DISABLE_USER = "disable_user"
    FORCE_PASSWORD_RESET = "force_password_reset"  # noqa: S105 - enum value, not a credential
    # Endpoint
    ISOLATE_HOST = "isolate_host"
    QUARANTINE_FILE = "quarantine_file"
    # Network
    BLOCK_IP = "block_ip"
    BLOCK_DOMAIN = "block_domain"
    # Notification / orchestration
    NOTIFY_SLACK = "notify_slack"
    OPEN_JIRA_TICKET = "open_jira_ticket"
    # Other
    CUSTOM = "custom"

    @property
    def is_reversible(self) -> bool:
        """Whether a real (not no-op) rollback is possible.

        Used by the rollback RBAC check: non-reversible classes require
        admin to acknowledge that "rollback" is at best a compensating
        action (e.g. re-issuing credentials), not an undo.
        """
        return self not in _NON_REVERSIBLE_ACTIONS

    @property
    def is_stabilization(self) -> bool:
        """Whether a successful execution is best framed as containment
        rather than resolution.

        Stabilizations bound the threat but leave a follow-up for a human
        (re-image the host, rotate credentials, restore the file). The
        Aegis Actions Feed and the Overview's "Requires Your Attention"
        row use this to label outcomes as "stabilized" instead of
        "resolved". Sprint 9 had this set hard-coded in two endpoints
        (R-37); Sprint 10 moves the truth into the enum.
        """
        return self in _STABILIZATION_ACTIONS


_NON_REVERSIBLE_ACTIONS: frozenset[RemediationActionClass] = frozenset(
    {
        RemediationActionClass.REVOKE_USER_SESSIONS,
        RemediationActionClass.FORCE_PASSWORD_RESET,
        RemediationActionClass.NOTIFY_SLACK,
        RemediationActionClass.CUSTOM,  # unknown blast radius — fail closed
    }
)


_STABILIZATION_ACTIONS: frozenset[RemediationActionClass] = frozenset(
    {
        RemediationActionClass.ISOLATE_HOST,
        RemediationActionClass.REVOKE_USER_SESSIONS,
        RemediationActionClass.BLOCK_IP,
        RemediationActionClass.BLOCK_DOMAIN,
        RemediationActionClass.QUARANTINE_FILE,
    }
)


class RemediationStatus(str, enum.Enum):
    PROPOSED = "proposed"  # selected by AI, awaiting policy eval
    POLICY_ALLOWED = "policy_allowed"
    POLICY_ESCALATED = "policy_escalated"
    POLICY_DENIED = "policy_denied"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class RemediationAction(Base, UUIDPKMixin, TimestampMixin):
    """A bounded, reversible action proposed or taken in response to an
    incident.

    Every row that ever reaches `EXECUTING` MUST have a non-null
    `rollback_plan`. The Remediation Decision Engine enforces this; the
    constraint is documented here so future contributors don't relax it.
    """

    __tablename__ = "remediation_actions"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action_class: Mapped[RemediationActionClass] = mapped_column(
        Enum(RemediationActionClass, name="remediation_action_class", native_enum=False),
        nullable=False,
    )
    status: Mapped[RemediationStatus] = mapped_column(
        Enum(RemediationStatus, name="remediation_status", native_enum=False),
        default=RemediationStatus.PROPOSED,
        nullable=False,
        index=True,
    )

    # Parameters for the action (e.g. user_id, host_id, ip, ttl).
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # The rollback plan that will be executed if rollback is requested.
    # Encoded as: {"action_class": "...", "parameters": {...}}.
    # Required when status reaches EXECUTING (enforced in the engine).
    rollback_plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Blast radius (units depend on action_class — e.g. number of users,
    # hosts, sessions). Used by PolicyEngine caps.
    blast_radius: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # AI confidence at selection time.
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Idempotency key so retries don't double-execute against integrations.
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    # Linkage to the workflow run that executed (or is executing) this action.
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Result payload from the integration (target IDs touched, etc.).
    execution_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
