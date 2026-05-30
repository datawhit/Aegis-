"""Tests for the conversational Assistant endpoints (Sprint 13).

These exercise the persistence + list + transcript paths against the
real DB. The /chat happy path needs Anthropic, which CI doesn't have —
covered indirectly via the 503 case below.
"""

from __future__ import annotations

import uuid

from app.core.identity.local_jwt import LocalJWTIdentityProvider, hash_password
from app.models.assistant import AssistantConversation, AssistantMessage
from app.models.user import AuthProvider, User, UserRole


async def _make_user(db_session) -> tuple[User, str]:
    user = User(
        email=f"op-{uuid.uuid4()}@example.com",
        display_name="Op",
        hashed_password=hash_password("secret"),
        role=UserRole.OPERATOR,
        auth_provider=AuthProvider.LOCAL,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = await LocalJWTIdentityProvider().issue_token(user)
    return user, token.access_token


async def test_chat_returns_503_when_no_api_key(client, db_session, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    # Also clear the cached singleton so it sees the new setting.
    import app.core.ai.assistant as a

    monkeypatch.setattr(a, "_singleton", None)

    _, token = await _make_user(db_session)
    await db_session.commit()
    response = await client.post(
        "/api/v1/assistant/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "anything"},
    )
    assert response.status_code == 503
    assert "key" in response.json()["detail"].lower()


async def test_list_conversations_is_user_scoped(client, db_session) -> None:
    user_a, token_a = await _make_user(db_session)
    user_b, _token_b = await _make_user(db_session)

    db_session.add_all(
        [
            AssistantConversation(user_id=user_a.id, title="A's first chat"),
            AssistantConversation(user_id=user_a.id, title="A's second"),
            AssistantConversation(user_id=user_b.id, title="B's chat"),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/assistant/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 200
    titles = {row["title"] for row in response.json()["items"]}
    assert "A's first chat" in titles
    assert "A's second" in titles
    assert "B's chat" not in titles


async def test_transcript_returns_messages_in_order(client, db_session) -> None:
    user, token = await _make_user(db_session)
    conversation = AssistantConversation(user_id=user.id, title="ordering test")
    db_session.add(conversation)
    await db_session.flush()
    for i, (role, text) in enumerate(
        [
            ("user", "first user msg"),
            ("assistant", "first assistant reply"),
            ("user", "second user msg"),
            ("assistant", "second assistant reply"),
        ]
    ):
        db_session.add(
            AssistantMessage(
                conversation_id=conversation.id,
                role=role,
                content=text,
                sources=[],
                tool_calls=[],
            )
        )
        await db_session.flush()  # flush each so created_at advances (clock_timestamp)
        _ = i
    await db_session.commit()

    response = await client.get(
        f"/api/v1/assistant/conversations/{conversation.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "ordering test"
    assert [m["content"] for m in body["messages"]] == [
        "first user msg",
        "first assistant reply",
        "second user msg",
        "second assistant reply",
    ]


async def test_transcript_404_for_other_users_conversation(client, db_session) -> None:
    user_a, _token_a = await _make_user(db_session)
    _user_b, token_b = await _make_user(db_session)
    conversation = AssistantConversation(user_id=user_a.id, title="not yours")
    db_session.add(conversation)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/assistant/conversations/{conversation.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


async def test_audit_logs_resource_id_filter(client, db_session) -> None:
    """Sprint 13 / D-72: audit-logs endpoint accepts ?resource_id=…"""
    from app.core.audit import Actor, get_audit_logger

    user = User(
        email=f"admin-{uuid.uuid4()}@example.com",
        display_name="A",
        hashed_password=hash_password("secret"),
        role=UserRole.ADMIN,
        auth_provider=AuthProvider.LOCAL,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = await LocalJWTIdentityProvider().issue_token(user)

    target_id = uuid.uuid4()
    await get_audit_logger().record(
        db_session,
        actor=Actor.system(label="test"),
        action="incident.touched",
        resource_type="incident",
        resource_id=target_id,
        payload={"x": 1},
    )
    # A second entry for a DIFFERENT resource_id so we can verify the
    # filter actually filters.
    await get_audit_logger().record(
        db_session,
        actor=Actor.system(label="test"),
        action="incident.touched",
        resource_type="incident",
        resource_id=uuid.uuid4(),
        payload={"x": 2},
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/audit/logs?resource_id={target_id}",
        headers={"Authorization": f"Bearer {token.access_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert all(row["resource_id"] == str(target_id) for row in body["items"])
    assert len(body["items"]) == 1
