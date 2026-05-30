"""Aegis Assistant endpoints (Sprint 10 + Sprint 13 persistence).

POST   /api/v1/assistant/chat                     — send a turn
GET    /api/v1/assistant/conversations            — list user's threads
GET    /api/v1/assistant/conversations/{id}       — full transcript

Sprint 13: server-side conversation history (D-59 / D-64). Each user
turn + assistant reply persists into `assistant_messages` under an
`assistant_conversations` row scoped to the authenticated user. The
chat endpoint accepts an optional `conversation_id` — when given, the
prior transcript is loaded as context; when absent, a new conversation
is created and its id is returned for the client to remember.

The Assistant is still strictly read-only (ADR-023). The transcript is
a record of the conversation, not state that drives action.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, SessionDep
from app.core.ai.assistant import (
    AssistantNotConfigured,
    AssistantResponse,
    get_assistant_service,
)
from app.models.assistant import AssistantConversation, AssistantMessage

router = APIRouter()


# ─── chat ───────────────────────────────────────────────────────────


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


class AssistantSourceOut(BaseModel):
    kind: str
    id: str
    label: str


class AssistantChatResponse(BaseModel):
    conversation_id: uuid.UUID
    answer: str
    sources: list[AssistantSourceOut]
    tool_calls: list[str]
    model: str


def _to_response(r: AssistantResponse, conversation_id: uuid.UUID) -> AssistantChatResponse:
    return AssistantChatResponse(
        conversation_id=conversation_id,
        answer=r.answer,
        sources=[AssistantSourceOut(kind=s.kind, id=s.id, label=s.label) for s in r.sources],
        tool_calls=r.tool_calls,
        model=r.model,
    )


@router.post("/assistant/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    body: AssistantChatRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> AssistantChatResponse:
    # Resolve / create the conversation.
    conversation = await _resolve_conversation(
        session,
        user_id=current_user.id,
        conversation_id=body.conversation_id,
        first_message=body.message,
    )

    # Load history (text-only, prior turns in order).
    history_rows = (
        (
            await session.execute(
                select(AssistantMessage)
                .where(AssistantMessage.conversation_id == conversation.id)
                .order_by(AssistantMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in history_rows if m.content]

    # Persist the user turn before calling the model so a model error
    # doesn't lose the question.
    session.add(
        AssistantMessage(
            conversation_id=conversation.id,
            role="user",
            content=body.message,
            sources=[],
            tool_calls=[],
        )
    )
    await session.flush()

    service = get_assistant_service()
    try:
        result = await service.chat(session, body.message, history=history)
    except AssistantNotConfigured as exc:
        # Roll back the user-turn insert by relying on the test-time
        # transaction. In prod, leaving the question recorded is fine —
        # operator can retry once the key is configured.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    # Persist the assistant turn.
    session.add(
        AssistantMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=result.answer,
            sources=[{"kind": s.kind, "id": s.id, "label": s.label} for s in result.sources],
            tool_calls=list(result.tool_calls),
            model=result.model,
        )
    )
    conversation.updated_at = datetime.now(tz=conversation.updated_at.tzinfo)
    await session.commit()

    return _to_response(result, conversation.id)


async def _resolve_conversation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    first_message: str,
) -> AssistantConversation:
    if conversation_id is not None:
        existing = (
            await session.execute(
                select(AssistantConversation).where(
                    AssistantConversation.id == conversation_id,
                    AssistantConversation.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="conversation not found",
            )
        return existing

    # Auto-derive a short title from the first user message.
    title = first_message.strip().splitlines()[0]
    if len(title) > 80:
        title = title[:77] + "…"
    conversation = AssistantConversation(user_id=user_id, title=title)
    session.add(conversation)
    await session.flush()
    return conversation


# ─── list + transcript ─────────────────────────────────────────────


class ConversationRow(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationListResponse(BaseModel):
    items: list[ConversationRow]


@router.get("/assistant/conversations", response_model=ConversationListResponse)
async def list_conversations(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ConversationListResponse:
    rows = (
        (
            await session.execute(
                select(AssistantConversation)
                .where(AssistantConversation.user_id == current_user.id)
                .order_by(AssistantConversation.updated_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )

    items: list[ConversationRow] = []
    for c in rows:
        count = (
            await session.execute(
                select(AssistantMessage.id).where(AssistantMessage.conversation_id == c.id)
            )
        ).all()
        items.append(
            ConversationRow(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=len(count),
            )
        )
    return ConversationListResponse(items=items)


class MessageRow(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sources: list[AssistantSourceOut]
    tool_calls: list[str]
    model: str | None
    created_at: datetime


class TranscriptResponse(BaseModel):
    conversation_id: uuid.UUID
    title: str | None
    messages: list[MessageRow]


@router.get(
    "/assistant/conversations/{conversation_id}",
    response_model=TranscriptResponse,
)
async def get_transcript(
    conversation_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> TranscriptResponse:
    conversation = (
        await session.execute(
            select(AssistantConversation).where(
                AssistantConversation.id == conversation_id,
                AssistantConversation.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="conversation not found",
        )
    rows = (
        (
            await session.execute(
                select(AssistantMessage)
                .where(AssistantMessage.conversation_id == conversation_id)
                .order_by(AssistantMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return TranscriptResponse(
        conversation_id=conversation.id,
        title=conversation.title,
        messages=[
            MessageRow(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=[AssistantSourceOut(**s) for s in (m.sources or [])],
                tool_calls=list(m.tool_calls or []),
                model=m.model,
                created_at=m.created_at,
            )
            for m in rows
        ],
    )
