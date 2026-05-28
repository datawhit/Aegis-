"""Anthropic Claude AIProvider.

Phase 1 model: `claude-sonnet-4-6`. Rationale (ADR-007):

- Sonnet 4.6 is structured-output capable via tool_use.
- Cost profile is right for high-volume per-alert classification —
  Opus is over-spec here. We can upgrade for low-frequency / high-stakes
  flows (e.g., remediation-decision review in Phase 2).
- Anthropic SDK is async-first; matches the rest of the stack.
"""
from __future__ import annotations

import time

import anthropic
from pydantic import ValidationError

from app.config import settings
from app.core.ai.base import (
    AIProvider,
    AIProviderError,
    TriageOutput,
    TriageRequest,
    TriageResult,
)
from app.logging import get_logger
from app.prompts.triage import (
    TRIAGE_PROMPT_VERSION,
    TRIAGE_SYSTEM_PROMPT,
    TRIAGE_TOOL_SCHEMA,
    render_user_prompt,
)

log = get_logger("ai.anthropic")

_DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1024


class AnthropicAIProvider(AIProvider):
    def __init__(self, *, model: str = _DEFAULT_MODEL) -> None:
        if not settings.anthropic_api_key:
            # Don't fail at construction time — the provider may be
            # instantiated by the DI selector in environments where it
            # won't actually be called (e.g., tests using FakeAIProvider).
            # We only error in `triage_alert`.
            self._client: anthropic.AsyncAnthropic | None = None
        else:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model

    async def triage_alert(self, request: TriageRequest) -> TriageResult:
        if self._client is None:
            raise AIProviderError(
                "Anthropic API key is not configured. Set ANTHROPIC_API_KEY."
            )

        user_prompt = render_user_prompt(
            source=request.source,
            normalized=request.normalized,
            raw_excerpt=request.raw_event_excerpt,
        )

        started = time.monotonic()
        try:
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=TRIAGE_SYSTEM_PROMPT,
                tools=[TRIAGE_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "triage_alert"},
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            log.exception("ai.anthropic.api_error", error=str(exc))
            raise AIProviderError(f"anthropic API call failed: {exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)

        # Find the `tool_use` block. Anthropic returns a list of content
        # blocks; with `tool_choice` set, the model is constrained to call
        # the tool, but defensive parsing is still required (the model may
        # return mixed content or refuse).
        tool_input: dict | None = None
        raw_response_blocks: list[str] = []
        for block in message.content:
            if block.type == "tool_use" and block.name == "triage_alert":
                tool_input = block.input  # type: ignore[assignment]
            elif block.type == "text":
                raw_response_blocks.append(block.text)

        raw_response = "\n".join(raw_response_blocks) if raw_response_blocks else None

        if tool_input is None:
            log.error(
                "ai.anthropic.no_tool_use",
                stop_reason=message.stop_reason,
                content_types=[b.type for b in message.content],
            )
            raise AIProviderError("model did not invoke the triage_alert tool")

        try:
            output = TriageOutput.model_validate(tool_input)
        except ValidationError as exc:
            log.error("ai.anthropic.schema_violation", errors=exc.errors())
            raise AIProviderError(f"model output failed schema validation: {exc}") from exc

        return TriageResult(
            output=output,
            prompt=user_prompt,
            raw_response=raw_response,
            provider="anthropic",
            model=self._model,
            prompt_tokens=message.usage.input_tokens,
            completion_tokens=message.usage.output_tokens,
            latency_ms=latency_ms,
        )

    # Expose the prompt version so callers can persist it on the reasoning
    # snapshot without importing from the prompts package directly.
    @property
    def prompt_template_id(self) -> str:
        return TRIAGE_PROMPT_VERSION
