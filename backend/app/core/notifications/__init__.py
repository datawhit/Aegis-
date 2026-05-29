"""Notification abstraction — outbound human-facing messages.

Phase 2 ships Slack. Phase 3 adds Email + PagerDuty. The interface is
deliberately small (`notify` + `request_approval`) so each channel can
swap in without rewriting senders.
"""

from app.core.notifications.base import (
    ApprovalNotification,
    Notification,
    Notifier,
    StubNotifier,
)
from app.core.notifications.slack import SlackNotifier

__all__ = [
    "ApprovalNotification",
    "Notification",
    "Notifier",
    "SlackNotifier",
    "StubNotifier",
    "get_notifier",
]


_singleton: Notifier | None = None


def get_notifier() -> Notifier:
    global _singleton
    if _singleton is None:
        _singleton = SlackNotifier()
    return _singleton
