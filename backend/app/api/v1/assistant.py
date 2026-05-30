"""Aegis Assistant endpoint (Sprint 10).

POST /api/v1/assistant/chat
  Body:   {"message": "What did you do overnight?"}
  Returns: {"answer": "...", "sources": [...], "tool_calls": [...]}

No conversation state on the server. Each request is independent;
multi-turn dialogue is a Sprint 11 question (and OQ-37 lower).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep
from app.core.ai.assistant import (
    AssistantNotConfigured,
    AssistantResponse,
    get_assistant_service,
)

router = APIRouter()


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class AssistantSourceOut(BaseModel):
    kind: str
    id: str
    label: str


class AssistantChatResponse(BaseModel):
    answer: str
    sources: list[AssistantSourceOut]
    tool_calls: list[str]
    model: str


def _to_response(r: AssistantResponse) -> AssistantChatResponse:
    return AssistantChatResponse(
        answer=r.answer,
        sources=[AssistantSourceOut(kind=s.kind, id=s.id, label=s.label) for s in r.sources],
        tool_calls=r.tool_calls,
        model=r.model,
    )


@router.post("/assistant/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    body: AssistantChatRequest,
    session: SessionDep,
    _user: CurrentUserDep,
) -> AssistantChatResponse:
    service = get_assistant_service()
    try:
        result = await service.chat(session, body.message)
    except AssistantNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return _to_response(result)
