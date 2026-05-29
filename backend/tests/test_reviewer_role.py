"""Reviewer role access tests (Sprint 4).

Reviewer can READ audit, policies, incidents.
Reviewer CANNOT modify policies, decide approvals, or rollback actions.
(Audit-export specifics are covered in test_audit_export.py;
rollback in test_rollback_rbac.py.)
"""

from __future__ import annotations

import uuid

from app.core.identity.local_jwt import LocalJWTIdentityProvider, hash_password
from app.models.policy import Policy, PolicyEffect
from app.models.user import AuthProvider, User, UserRole


async def _make_user(db_session, role: UserRole) -> tuple[User, str]:
    user = User(
        email=f"{role.value}-{uuid.uuid4()}@example.com",
        display_name=role.value,
        hashed_password=hash_password("secret"),
        role=role,
        auth_provider=AuthProvider.LOCAL,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = await LocalJWTIdentityProvider().issue_token(user)
    return user, token.access_token


async def _make_policy(db_session) -> Policy:
    policy = Policy(
        name=f"test-policy-{uuid.uuid4().hex[:8]}",
        description="test",
        priority=10,
        effect=PolicyEffect.ESCALATE,
        match={"eq": [{"var": "action_class"}, "isolate_host"]},
        constraints={},
        is_active=True,
    )
    db_session.add(policy)
    await db_session.flush()
    return policy


async def test_reviewer_can_list_policies(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.REVIEWER)
    await _make_policy(db_session)
    await db_session.commit()

    response = await client.get(
        "/api/v1/policies",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    assert "items" in response.json()


async def test_reviewer_can_get_policy(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.REVIEWER)
    policy = await _make_policy(db_session)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/policies/{policy.id}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(policy.id)


async def test_reviewer_cannot_create_policy(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.REVIEWER)
    await db_session.commit()

    response = await client.post(
        "/api/v1/policies",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "name": "reviewer-tried-to-create",
            "description": "no",
            "priority": 100,
            "effect": "allow",
            "match": {"eq": [{"var": "action_class"}, "isolate_host"]},
            "constraints": {},
            "is_active": True,
        },
    )
    assert response.status_code == 403


async def test_reviewer_cannot_delete_policy(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.REVIEWER)
    policy = await _make_policy(db_session)
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/policies/{policy.id}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 403


async def test_reviewer_can_list_incidents(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.REVIEWER)
    await db_session.commit()

    response = await client.get(
        "/api/v1/incidents",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
