"""Tests for /.well-known/aegis-audit-public-key (Sprint 6, D-28)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings
from app.core.audit.export_signer import generate_keypair_pem


async def test_well_known_returns_public_keys(
    client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    priv_active, pub_active = generate_keypair_pem()
    _priv_retired, pub_retired = generate_keypair_pem()
    registry_file = tmp_path / "keys.json"
    registry_file.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "key_id": "active-key",
                        "status": "active",
                        "private_pem": priv_active,
                        "public_pem": pub_active,
                    },
                    {
                        "key_id": "retired-key",
                        "status": "retired",
                        "public_pem": pub_retired,
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(settings, "audit_key_registry_path", str(registry_file))

    response = await client.get("/.well-known/aegis-audit-public-key")
    assert response.status_code == 200
    body = response.json()
    assert len(body["keys"]) == 2
    ids = {k["key_id"]: k for k in body["keys"]}
    assert ids["active-key"]["status"] == "active"
    assert ids["active-key"]["public_pem"] == pub_active
    assert "private_pem" not in ids["active-key"]
    assert "private_pem" not in ids["retired-key"]


async def test_well_known_requires_no_auth(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint must be unauthenticated — auditors fetch without a token."""
    priv, _ = generate_keypair_pem()
    monkeypatch.setattr(settings, "audit_key_registry_path", "")
    monkeypatch.setattr(settings, "audit_export_signing_key", priv)
    monkeypatch.setattr(settings, "audit_export_signing_key_id", "single-key")

    response = await client.get("/.well-known/aegis-audit-public-key")
    assert response.status_code == 200
    assert response.json()["keys"][0]["key_id"] == "single-key"


async def test_well_known_503_when_no_key_configured(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "audit_key_registry_path", "")
    monkeypatch.setattr(settings, "audit_export_signing_key", "")
    response = await client.get("/.well-known/aegis-audit-public-key")
    assert response.status_code == 503
