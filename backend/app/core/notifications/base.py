"""Notifier protocol + simple message types + stub impl for tests."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Severity = Literal["info", "warning", "critical"]


@dataclass
class Notification:
    title: str
    body: str
    severity: Severity = "info"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalNotification:
    approval_id: uuid.UUID
    incident_id: uuid.UUID
    remediation_action_id: uuid.UUID
    action_class: str
    blast_radius: int
    ai_confidence: float | None
    ai_summary: str
    ai_reasoning: str
    expires_at: str
    requested_role: str


@runtime_checkable
class Notifier(Protocol):
    async def notify(self, *, title: str, body: str, severity: Severity = "info") -> bool: ...

    async def request_approval(self, approval: ApprovalNotification) -> bool: ...


class StubNotifier(Notifier):
    """Records calls. Used in tests."""

    def __init__(self) -> None:
        self.notifications: list[Notification] = []
        self.approval_requests: list[ApprovalNotification] = []

    async def notify(
        self, *, title: str, body: str, severity: Severity = "info"
    ) -> bool:
        self.notifications.append(Notification(title=title, body=body, severity=severity))
        return True

    async def request_approval(self, approval: ApprovalNotification) -> bool:
        self.approval_requests.append(approval)
        return True
