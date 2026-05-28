"""Test fakes — kept here so multiple test modules share one definition."""
from __future__ import annotations

from app.core.ai.base import (
    AIProvider,
    AIProviderError,
    TriageOutput,
    TriageRequest,
    TriageResult,
)
from app.models.alert import AlertSeverity


class FakeAIProvider(AIProvider):
    """Configurable in-process AI provider for tests.

    `next_output` controls the next `triage_alert` response. Set
    `fail_with` to raise an `AIProviderError` instead — used to exercise
    the TriageService fallback path.
    """

    def __init__(
        self,
        *,
        next_output: TriageOutput | None = None,
        fail_with: str | None = None,
    ) -> None:
        self.next_output = next_output or TriageOutput(
            severity=AlertSeverity.HIGH,
            category="initial_access",
            mitre_techniques=["T1078"],
            summary="Suspicious sign-in test.",
            suggested_action_class="revoke_user_sessions",
            confidence=0.92,
            reasoning="fake reasoning for tests",
        )
        self.fail_with = fail_with
        self.calls: list[TriageRequest] = []

    async def triage_alert(self, request: TriageRequest) -> TriageResult:
        self.calls.append(request)
        if self.fail_with is not None:
            raise AIProviderError(self.fail_with)
        return TriageResult(
            output=replace_output(self.next_output),
            prompt="test prompt",
            raw_response=None,
            provider="fake",
            model="fake-1",
            prompt_tokens=10,
            completion_tokens=20,
            latency_ms=5,
        )


def replace_output(out: TriageOutput) -> TriageOutput:
    """Return a copy so tests can mutate the fake's `next_output` between
    calls without aliasing the previous result."""
    return out.model_copy(deep=True)
