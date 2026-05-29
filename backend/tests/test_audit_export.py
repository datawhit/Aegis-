"""Test the signed audit export endpoint."""

from __future__ import annotations

import json

from app.config import settings
from app.core.audit import Actor, get_audit_logger
from app.core.audit.export_signer import (
    RECEIPT_MARKER_KEY,
    entries_digest,
    generate_keypair_pem,
    verify_receipt,
)
from app.core.identity.local_jwt import LocalJWTIdentityProvider, hash_password
from app.models.user import AuthProvider, User, UserRole


async def _make_user(db_session, role: UserRole, email: str) -> tuple[User, str]:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        hashed_password=hash_password("secret"),
        role=role,
        auth_provider=AuthProvider.LOCAL,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = await LocalJWTIdentityProvider().issue_token(user)
    return user, token.access_token


async def test_audit_export_unsigned_when_require_signature_false(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.ADMIN, "admin@example.com")

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
        "/api/v1/audit/export?require_signature=false",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.strip()]
    # 2 entries + 1 receipt line
    assert len(lines) == 3

    entries = [json.loads(line) for line in lines[:-1]]
    receipt = json.loads(lines[-1])

    assert entries[0]["action"] == "audit.test1"
    assert entries[1]["action"] == "audit.test2"
    assert receipt[RECEIPT_MARKER_KEY] is True
    assert receipt["range"]["count"] == 2
    assert receipt["signature"] is None
    assert receipt["head_entry_hash"] == entries[-1]["entry_hash"]
    assert receipt["content_hash"] == entries_digest([e["entry_hash"] for e in entries])


async def test_audit_export_requires_signature_503_when_no_key(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.ADMIN, "admin@example.com")
    await db_session.commit()

    response = await client.get(
        "/api/v1/audit/export",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 503
    assert "signing key" in response.json()["detail"].lower()


async def test_audit_export_signed_receipt_verifies(client, db_session, monkeypatch) -> None:
    priv_pem, pub_pem = generate_keypair_pem()
    monkeypatch.setattr(settings, "audit_export_signing_key", priv_pem)
    monkeypatch.setattr(settings, "audit_export_signing_key_id", "test-key-1")

    _, access = await _make_user(db_session, UserRole.ADMIN, "admin@example.com")
    await get_audit_logger().record(
        db_session,
        actor=Actor.system(label="test"),
        action="audit.signed.test",
        resource_type="test",
        resource_id=None,
        payload={"hello": "world"},
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/audit/export",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200

    lines = [line for line in response.text.splitlines() if line.strip()]
    receipt = json.loads(lines[-1])
    assert receipt[RECEIPT_MARKER_KEY] is True
    assert receipt["signature"] is not None
    assert receipt["signing_key_id"] == "test-key-1"

    # The receipt verifies against the matching public key.
    assert verify_receipt(receipt, pub_pem) is True

    # And a tampered receipt does NOT verify.
    tampered = dict(receipt)
    tampered["range"] = {**tampered["range"], "count": tampered["range"]["count"] + 1}
    assert verify_receipt(tampered, pub_pem) is False


async def test_audit_export_allows_reviewer(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.REVIEWER, "reviewer@example.com")
    await db_session.commit()

    response = await client.get(
        "/api/v1/audit/export?require_signature=false",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200


async def test_audit_export_rejects_operator(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.OPERATOR, "operator@example.com")
    await db_session.commit()

    response = await client.get(
        "/api/v1/audit/export?require_signature=false",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 403
    detail = response.json()["detail"].lower()
    assert "admin" in detail and "reviewer" in detail


async def test_audit_export_rejects_viewer(client, db_session) -> None:
    _, access = await _make_user(db_session, UserRole.VIEWER, "viewer@example.com")
    await db_session.commit()

    response = await client.get(
        "/api/v1/audit/export?require_signature=false",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 403
