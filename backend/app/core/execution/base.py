"""ExecutionConnector protocol + registry.

The contract is deliberately narrow:

  - `execute(action_class, parameters, idempotency_key)` → ExecutionResult
  - `rollback(action_class, parameters, original_result, idempotency_key)` → ExecutionResult

Connectors MUST be:

  - **Idempotent.** Same idempotency_key + same parameters → same result.
    Retries are handled by Celery; double-execution is on the connector.
  - **Honest about reversibility.** If `supports_rollback(action_class)`
    returns `False`, the executor refuses to dispatch the action
    autonomously — the policy engine's rollback-required invariant kicks
    in upstream.
  - **Side-effect contained.** No DB writes; no logging that mutates
    state. The remediation executor owns persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class UnsupportedActionError(LookupError):
    """Raised when no connector handles the requested action_class."""


@dataclass
class ExecutionResult:
    ok: bool
    targets_affected: dict[str, Any] = field(default_factory=dict)
    provider_run_id: str | None = None
    error: str | None = None
    dry_run: bool = False


@runtime_checkable
class ExecutionConnector(Protocol):
    name: str

    def supports(self, action_class: str) -> bool: ...

    def supports_rollback(self, action_class: str) -> bool: ...

    async def execute(
        self,
        action_class: str,
        parameters: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> ExecutionResult: ...

    async def rollback(
        self,
        action_class: str,
        parameters: dict[str, Any],
        original_result: dict[str, Any] | None,
        *,
        idempotency_key: str,
    ) -> ExecutionResult: ...


class ExecutionRegistry:
    def __init__(self) -> None:
        self._connectors: list[ExecutionConnector] = []

    def register(self, connector: ExecutionConnector) -> None:
        self._connectors.append(connector)

    def for_action(self, action_class: str) -> ExecutionConnector:
        for c in self._connectors:
            if c.supports(action_class):
                return c
        raise UnsupportedActionError(
            f"no execution connector supports action_class={action_class!r}"
        )

    def supported_actions(self) -> list[str]:
        actions: list[str] = []
        for c in self._connectors:
            for ac in _COMMON_ACTION_CLASSES:
                if c.supports(ac):
                    actions.append(f"{c.name}:{ac}")
        return sorted(actions)


# Enumerated for introspection; the connectors themselves are the source
# of truth via `supports()`.
_COMMON_ACTION_CLASSES = [
    "revoke_user_sessions",
    "disable_user",
    "force_password_reset",
    "isolate_host",
    "quarantine_file",
    "block_ip",
    "block_domain",
    "notify_slack",
    "open_jira_ticket",
]
