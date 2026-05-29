"""StubExecutionConnector — supports every action class, records calls, returns success.

Used in tests to assert the executor dispatches correctly without
touching real integrations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.execution.base import ExecutionConnector, ExecutionResult


@dataclass
class _Call:
    kind: str  # "execute" | "rollback"
    action_class: str
    parameters: dict[str, Any]
    idempotency_key: str


class StubExecutionConnector(ExecutionConnector):
    name = "stub"

    def __init__(self, *, fail_with: str | None = None) -> None:
        self._fail_with = fail_with
        self.calls: list[_Call] = []

    def supports(self, action_class: str) -> bool:
        return True

    def supports_rollback(self, action_class: str) -> bool:
        return True

    async def execute(
        self,
        action_class: str,
        parameters: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> ExecutionResult:
        self.calls.append(_Call("execute", action_class, parameters, idempotency_key))
        if self._fail_with:
            return ExecutionResult(ok=False, error=self._fail_with)
        return ExecutionResult(
            ok=True,
            targets_affected={"stub": list(parameters.keys())},
            provider_run_id=f"stub:{idempotency_key}",
        )

    async def rollback(
        self,
        action_class: str,
        parameters: dict[str, Any],
        original_result: dict[str, Any] | None,
        *,
        idempotency_key: str,
    ) -> ExecutionResult:
        self.calls.append(_Call("rollback", action_class, parameters, idempotency_key))
        if self._fail_with:
            return ExecutionResult(ok=False, error=self._fail_with)
        return ExecutionResult(
            ok=True,
            targets_affected={"stub_rollback": True},
            provider_run_id=f"stub-rollback:{idempotency_key}",
        )
