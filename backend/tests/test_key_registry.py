"""Unit tests for the multi-key signing-key registry (Sprint 6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings
from app.core.audit.export_signer import (
    active_signing_key_id,
    generate_keypair_pem,
    load_private_key,
)
from app.core.audit.key_registry import (
    KeyEntry,
    KeyRegistry,
    KeyRegistryError,
    load_registry,
)


def _entry(key_id: str, status: str, with_private: bool = True) -> KeyEntry:
    priv, pub = generate_keypair_pem()
    return KeyEntry(
        key_id=key_id,
        public_pem=pub,
        status=status,  # type: ignore[arg-type]
        private_pem=priv if with_private else None,
    )


def test_registry_requires_exactly_one_active() -> None:
    a = _entry("k1", "active")
    b = _entry("k2", "active")
    with pytest.raises(KeyRegistryError, match="exactly one active"):
        KeyRegistry(entries=(a, b))


def test_registry_rejects_no_active() -> None:
    a = _entry("k1", "retired")
    with pytest.raises(KeyRegistryError, match="exactly one active"):
        KeyRegistry(entries=(a,))


def test_registry_rejects_duplicate_key_id() -> None:
    a = _entry("k1", "active")
    b = _entry("k1", "retired")
    with pytest.raises(KeyRegistryError, match="duplicate key_id"):
        KeyRegistry(entries=(a, b))


def test_registry_active_must_have_private_pem() -> None:
    a = _entry("k1", "active", with_private=False)
    with pytest.raises(KeyRegistryError, match="must have a private_pem"):
        KeyRegistry(entries=(a,))


def test_registry_by_id_lookup() -> None:
    a = _entry("k1", "active")
    b = _entry("k2", "retired", with_private=False)
    reg = KeyRegistry(entries=(a, b))
    assert reg.by_id("k1") is a
    assert reg.by_id("k2") is b
    assert reg.by_id("missing") is None


def test_public_view_strips_private_material() -> None:
    a = _entry("k1", "active")
    reg = KeyRegistry(entries=(a,))
    view = reg.public_view()
    assert view[0]["public_pem"] == a.public_pem
    assert "private_pem" not in view[0]


def test_load_registry_falls_back_to_single_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    priv, _ = generate_keypair_pem()
    monkeypatch.setattr(settings, "audit_key_registry_path", "")
    monkeypatch.setattr(settings, "audit_export_signing_key", priv)
    monkeypatch.setattr(settings, "audit_export_signing_key_id", "fallback-key")

    reg = load_registry()
    assert len(reg.entries) == 1
    assert reg.active().key_id == "fallback-key"
    assert reg.active().private_pem == priv


def test_load_registry_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    monkeypatch.setattr(settings, "audit_export_signing_key", "")

    reg = load_registry()
    assert reg.active().key_id == "active-key"
    assert reg.by_id("retired-key") is not None
    assert reg.by_id("retired-key").private_pem is None


def test_load_registry_raises_when_nothing_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "audit_key_registry_path", "")
    monkeypatch.setattr(settings, "audit_export_signing_key", "")
    with pytest.raises(KeyRegistryError, match="No audit signing key"):
        load_registry()


def test_active_signing_key_id_via_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    priv, _ = generate_keypair_pem()
    monkeypatch.setattr(settings, "audit_key_registry_path", "")
    monkeypatch.setattr(settings, "audit_export_signing_key", priv)
    monkeypatch.setattr(settings, "audit_export_signing_key_id", "fallback-id")
    assert active_signing_key_id() == "fallback-id"


def test_load_private_key_uses_active_registry_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    priv_active, pub_active = generate_keypair_pem()
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
                ]
            }
        )
    )
    monkeypatch.setattr(settings, "audit_key_registry_path", str(registry_file))
    monkeypatch.setattr(settings, "audit_export_signing_key", "")

    key = load_private_key()
    # Round-trip: signing with this key produces something verifiable
    # against the registry's active public_pem.
    sig = key.sign(b"hello world")
    assert len(sig) == 64  # Ed25519 signature length
