"""AI provider abstraction.

Triage and (future) summarization route through `AIProvider`. The concrete
impl is chosen via `AEGIS_DEFAULT_AI_PROVIDER`. The protocol is deliberately
narrow (one method: `triage_alert`) so we can swap providers without rewriting
the call sites — same play as the WorkflowEngine / IdentityProvider seams.
"""
from app.config import settings
from app.core.ai.anthropic_provider import AnthropicAIProvider
from app.core.ai.base import (
    AIProvider,
    AIProviderError,
    TriageOutput,
    TriageRequest,
    TriageResult,
)
from app.core.ai.openai_stub import OpenAIAIProvider

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AnthropicAIProvider",
    "OpenAIAIProvider",
    "TriageOutput",
    "TriageRequest",
    "TriageResult",
    "get_ai_provider",
]


def get_ai_provider() -> AIProvider:
    match settings.default_ai_provider:
        case "anthropic":
            return AnthropicAIProvider()
        case "openai":
            return OpenAIAIProvider()
        case other:
            raise ValueError(f"Unknown AI provider: {other!r}")
