"""Unit tests for the audit-export signer."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.audit.export_signer import (
    SigningKeyUnavailable,
    build_receipt,
    entries_digest,
    generate_keypair_pem,
    load_private_key,
    sign_receipt,
    verify_receipt,
)


def test_entries_digest_is_deterministic() -> None:
    hashes = ["aa", "bb", "cc"]
    assert entries_digest(hashes) == entries_digest(hashes)


def test_entries_digest_is_order_sensitive() -> None:
    assert entries_digest(["aa", "bb"]) != entries_digest(["bb", "aa"])


def test_entries_digest_empty() -> None:
    # Empty input still produces a valid SHA-256 hex string (of nothing).
    digest = entries_digest([])
    assert len(digest) == 64


def test_sign_verify_roundtrip() -> None:
    priv_pem, pub_pem = generate_keypair_pem()
    private_key = load_private_key(priv_pem)

    receipt = build_receipt(
        range_since=None,
        range_until=datetime.now(UTC),
        count=3,
        head_entry_hash="dead",
        tip_entry_hash="beef",
        content_hash=entries_digest(["a", "b", "c"]),
        exported_by="test@example.com",
        signing_key_id="test-key",
    )
    signed = sign_receipt(receipt, private_key)
    assert signed["signature"]
    assert verify_receipt(signed, pub_pem) is True


def test_verify_rejects_tampered_payload() -> None:
    priv_pem, pub_pem = generate_keypair_pem()
    private_key = load_private_key(priv_pem)

    receipt = build_receipt(
        range_since=None,
        range_until=datetime.now(UTC),
        count=2,
        head_entry_hash="x",
        tip_entry_hash="y",
        content_hash=entries_digest(["a", "b"]),
        exported_by="u@example.com",
        signing_key_id="k",
    )
    signed = sign_receipt(receipt, private_key)

    tampered = dict(signed)
    tampered["exported_by"] = "attacker@example.com"
    assert verify_receipt(tampered, pub_pem) is False


def test_verify_rejects_wrong_public_key() -> None:
    priv_pem, _pub_pem = generate_keypair_pem()
    _other_priv_pem, other_pub_pem = generate_keypair_pem()

    private_key = load_private_key(priv_pem)
    receipt = build_receipt(
        range_since=None,
        range_until=datetime.now(UTC),
        count=0,
        head_entry_hash=None,
        tip_entry_hash=None,
        content_hash=entries_digest([]),
        exported_by="u@example.com",
        signing_key_id="k",
    )
    signed = sign_receipt(receipt, private_key)
    assert verify_receipt(signed, other_pub_pem) is False


def test_sign_receipt_rejects_existing_signature() -> None:
    priv_pem, _ = generate_keypair_pem()
    private_key = load_private_key(priv_pem)
    receipt = build_receipt(
        range_since=None,
        range_until=datetime.now(UTC),
        count=0,
        head_entry_hash=None,
        tip_entry_hash=None,
        content_hash=entries_digest([]),
        exported_by="u@example.com",
        signing_key_id="k",
    )
    once = sign_receipt(receipt, private_key)
    with pytest.raises(ValueError, match="already has a signature"):
        sign_receipt(once, private_key)


def test_load_private_key_unset_raises() -> None:
    with pytest.raises(SigningKeyUnavailable):
        load_private_key("")
