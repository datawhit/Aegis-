"""OpenAI AIProvider — stub.

Phase 1 ships Claude-only (ADR-007). The stub raises explicitly so a misconfig
(`AEGIS_DEFAULT_AI_PROVIDER=openai`) fails fast rather than silently dropping
alerts on the floor.
"""
from __future__ import annotations

from app.core.ai.base import AIProvider, TriageRequest, TriageResult


class OpenAIAIProvider(AIProvider):
    async def triage_alert(self, request: TriageRequest) -> TriageResult:
        raise NotImplementedError(
            "OpenAI provider is not implemented in Phase 1. "
            "Set AEGIS_DEFAULT_AI_PROVIDER=anthropic."
        )
