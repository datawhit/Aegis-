"""AIProvider protocol + triage I/O types.

Constraints encoded here that all providers must honor:

- **Structured output is mandatory.** Providers MUST return a `TriageOutput`
  that has been validated against the schema. Free-text responses are a bug,
  not a feature.
- **Confidence is required.** No `None` for confidence. If the provider
  can't produce one, it must say so by returning low confidence + a reason,
  not by omitting the field.
- **No side effects.** Providers do not write to the audit log or the DB —
  the `TriageService` does that, *after* the response is in hand. This
  keeps the provider trivially replaceable and easy to mock.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.models.alert import AlertSeverity


class TriageOutput(BaseModel):
    """Structured response the AI MUST return.

    Validated server-side; if the provider returns anything that doesn't fit
    this schema, we treat it as an `AIProviderError` and the triage service
    creates the incident anyway with severity=medium / confidence=null so
    the policy engine escalates to a human.
    """

    severity: AlertSeverity = Field(
        ..., description="Severity classification — based on impact + exploitability."
    )
    category: str = Field(..., max_length=128)
    mitre_techniques: list[str] = Field(
        default_factory=list,
        description="MITRE ATT&CK technique IDs, e.g. ['T1078', 'T1059.003'].",
    )
    summary: str = Field(..., max_length=512, description="One-sentence summary.")
    suggested_action_class: str | None = Field(
        default=None,
        description=(
            "Recommended remediation action class, or null if ambiguous / "
            "information-only. MUST be one of the values in "
            "RemediationActionClass."
        ),
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., max_length=4096)


@dataclass(frozen=True)
class TriageRequest:
    alert_id: uuid.UUID
    source: str
    normalized: dict  # the canonical alert payload
    raw_event_excerpt: dict  # a trimmed view of the raw event (for context)


@dataclass
class TriageResult:
    output: TriageOutput
    prompt: str
    raw_response: str | None
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None


class AIProviderError(Exception):
    """Raised when the provider call fails (network, schema, refusal, …)."""


@runtime_checkable
class AIProvider(Protocol):
    async def triage_alert(self, request: TriageRequest) -> TriageResult: ...
