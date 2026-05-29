"""Execution connectors — call out to remediation systems and undo on rollback.

Mirrors the ingestion connector pattern: an `ExecutionConnector` exposes
`execute()` + `rollback()` for one or more remediation action classes.
The registry maps action_class → connector so the executor can dispatch
without a switch statement.

Phase 2 ships the Microsoft Graph connector for `revoke_user_sessions` —
the natural pairing with the Defender ingestion shipped in Sprint 1.
Real outbound calls require `AEGIS_MS_GRAPH_LIVE=true`. Default is
**dry-run** — the connector logs what it WOULD do and returns a
successful result, so the demo loop works without real Azure credentials.
"""

from app.core.execution.base import (
    ExecutionConnector,
    ExecutionRegistry,
    ExecutionResult,
    UnsupportedActionError,
)
from app.core.execution.microsoft_graph import MicrosoftGraphConnector
from app.core.execution.stub import StubExecutionConnector

__all__ = [
    "ExecutionConnector",
    "ExecutionRegistry",
    "ExecutionResult",
    "MicrosoftGraphConnector",
    "StubExecutionConnector",
    "UnsupportedActionError",
    "get_execution_registry",
]


def get_execution_registry() -> ExecutionRegistry:
    registry = ExecutionRegistry()
    registry.register(MicrosoftGraphConnector())
    return registry
