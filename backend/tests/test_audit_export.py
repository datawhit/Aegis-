"""Test audit export JSONL endpoint."""
from __future__ import annotations

import json
from datetime import datetime, UTC

from app.core.audit import Actor, get_audit_logger
from app.core.identity.local_jwt import LocalJWTIdentityProvider, hash_password
from app.models.audit_log import AuditLog
from app.models.user import AuthProvider, User, UserRole


async def test_audit_export_returns_ndjson(client, db_session) -> None:
    admin = User(
        email="admin@example.com",
        display_name="Admin",
        hashed_password=hash_password("secret"),
        role=UserRole.ADMIN,
        auth_provider=AuthProvider.LOCAL,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.flush()

    identity = LocalJWTIdentityProvider()
    token = await identity.issue_token(admin)

    await get_audit_logger().record(
        db_session,
        actor=Actor.system(label="test"),
        action="audit.test1",
        resource_type="test",
        resource_id=None,
        payload={"value": 1},
    )
    await get_audit_logger().record(
        db_session,
        actor=Actor.system(label="test"),
        action="audit.test2",
        resource_type="test",
        resource_id=None,
        payload={"value": 2},
    )

    await db_session.commit()

    response = await client.get(
        "/api/v1/audit/export",
        headers={"Authorization": f"Bearer {token.access_token}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert len(lines) == 2

    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["action"] == "audit.test1"
    assert second["action"] == "audit.test2"
    assert first["payload"]["value"] == 1
    assert second["payload"]["value"] == 2


async def test_audit_export_rejects_non_admin(client, db_session) -> None:
    user = User(
        email="user@example.com",
        display_name="User",
        hashed_password=hash_password("secret"),
        role=UserRole.OPERATOR,
        auth_provider=AuthProvider.LOCAL,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    identity = LocalJWTIdentityProvider()
    token = await identity.issue_token(user)

    response = await client.get(
        "/api/v1/audit/export",
        headers={"Authorization": f"Bearer {token.access_token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "admin role required"
