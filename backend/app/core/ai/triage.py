"""TriageService — composes an AIProvider with reasoning-snapshot persistence.

The split between `AIProvider` and `TriageService` matters:

- `AIProvider` is a pure function from request → response. No DB, no audit.
- `TriageService` is the integration: call the provider, persist the
  reasoning snapshot BEFORE returning, so the chain has the AI's evidence
  even if the next step crashes.

If the provider raises, the service synthesizes a low-confidence /
"unknown" `TriageOutput` so the downstream pipeline still produces an
incident (with reasoning="ai_failed") rather than silently dropping the
alert. The policy engine will ESCALATE that case — which is correct.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.anthropic_provider import AnthropicAIProvider
from app.core.ai.base import (
    AIProvider,
    AIProviderError,
    TriageOutput,
    TriageRequest,
    TriageResult,
)
from app.core.redaction import PIIRedactor
from app.logging import get_logger
from app.models.ai_reasoning import AIReasoningSnapshot
from app.models.alert import AlertSeverity
from app.prompts.triage import TRIAGE_PROMPT_VERSION

log = get_logger("triage")


@dataclass
class TriageDecision:
    output: TriageOutput
    reasoning_snapshot_id: uuid.UUID
    ai_failed: bool


class TriageService:
    def __init__(
        self,
        provider: AIProvider,
        *,
        redactor: PIIRedactor | None = None,
    ) -> None:
        self._provider = provider
        # `None` opts out of redaction — useful in fixture-driven tests
        # where the model never sees real PII anyway. Production callers
        # always pass one.
        self._redactor = redactor

    async def triage(
        self,
        session: AsyncSession,
        request: TriageRequest,
        *,
        incident_id: uuid.UUID | None = None,
    ) -> TriageDecision:
        # --- 1. PII redaction (ADR-013) -----------------------------------
        if self._redactor is not None:
            normalized_redaction = self._redactor.redact(request.normalized)
            excerpt_redaction = self._redactor.redact(request.raw_event_excerpt)
            sanitized_request = TriageRequest(
                alert_id=request.alert_id,
                source=request.source,
                normalized=normalized_redaction.payload,
                raw_event_excerpt=excerpt_redaction.payload,
            )
            redaction_lookup = {
                **normalized_redaction.lookup,
                **excerpt_redaction.lookup,
            }
        else:
            sanitized_request = request
            redaction_lookup = {}

        # --- 2. Provider call ---------------------------------------------
        try:
            result = await self._provider.triage_alert(sanitized_request)
            ai_failed = False
        except AIProviderError as exc:
            log.error("triage.ai_failed", alert_id=str(request.alert_id), error=str(exc))
            # Synthesize a safe "unknown" result. Confidence stays None so the
            # policy engine's hard invariant (ADR-005) escalates this.
            result = _fallback_result(request, error=str(exc))
            ai_failed = True

        # --- 3. Persist reasoning snapshot --------------------------------
        # We store both the redacted evidence (what the model saw) AND the
        # lookup table (so the UI can de-redact for the analyst). Raw,
        # un-redacted normalized data still lives on the `alerts` row.
        snapshot = AIReasoningSnapshot(
            provider=result.provider,
            model=result.model,
            prompt_template_id=TRIAGE_PROMPT_VERSION,
            incident_id=incident_id,
            evidence={
                "normalized_redacted": sanitized_request.normalized,
                "raw_excerpt_redacted": sanitized_request.raw_event_excerpt,
                "redaction_lookup": redaction_lookup,
                "alert_id": str(request.alert_id),
                "source": request.source,
            },
            prompt=result.prompt,
            structured_output=result.output.model_dump(mode="json"),
            raw_response=result.raw_response,
            confidence=None if ai_failed else result.output.confidence,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=result.latency_ms,
        )
        session.add(snapshot)
        await session.flush()

        log.info(
            "triage.recorded",
            snapshot_id=str(snapshot.id),
            alert_id=str(request.alert_id),
            severity=result.output.severity.value,
            confidence=result.output.confidence,
            ai_failed=ai_failed,
        )
        return TriageDecision(
            output=result.output,
            reasoning_snapshot_id=snapshot.id,
            ai_failed=ai_failed,
        )


def _fallback_result(request: TriageRequest, *, error: str) -> TriageResult:
    """Synthesize a safe fallback when the AI provider fails.

    Severity stays MEDIUM and confidence is 0.0 (which our service treats
    as "no signal"; the snapshot stores `confidence=NULL` and the policy
    engine ESCALATES). Reasoning captures the error string for debugging.
    """
    return TriageResult(
        output=TriageOutput(
            severity=AlertSeverity.MEDIUM,
            category="ai_failed",
            mitre_techniques=[],
            summary=f"AI triage failed for alert from {request.source}; escalating.",
            suggested_action_class=None,
            confidence=0.0,
            reasoning=f"AI provider error: {error}",
        ),
        prompt="",
        raw_response=None,
        provider="fallback",
        model="none",
        prompt_tokens=None,
        completion_tokens=None,
        latency_ms=None,
    )


_singleton: TriageService | None = None


def get_triage_service() -> TriageService:
    global _singleton
    if _singleton is None:
        # Construct via DI'd provider; AnthropicAIProvider is the default
        # in Phase 1 per ADR-007. Phase 2 always redacts in production.
        _singleton = TriageService(
            provider=AnthropicAIProvider(),
            redactor=PIIRedactor(),
        )
    return _singleton
