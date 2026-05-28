"""Signed audit-export receipt (Sprint 4).

A signed export is an NDJSON stream:

    {"id": ..., "entry_hash": ..., ...}            # audit entry
    {"id": ..., "entry_hash": ..., ...}            # audit entry
    ...
    {                                              # final receipt line
      "receipt": true,
      "range": {"since": ..., "until": ..., "count": ...},
      "head_entry_hash": "...",
      "tip_entry_hash": "...",
      "content_hash": "...",
      "exported_at": "...",
      "exported_by": "...",
      "signing_key_id": "...",
      "signature": "<hex>"
    }

The final "receipt" line binds the export's range, the last entry hash in
the export, and the chain tip at export time. The signature is Ed25519
over the canonical JSON of the receipt minus the `signature` field.

Why bind both `head_entry_hash` and `tip_entry_hash`:

- `head_entry_hash` proves the export was a prefix of the chain that
  ended at that hash — a compliance officer can re-derive it from the
  exported entries.
- `tip_entry_hash` is the chain's current tip; if the verifier later
  asks the server for the audit chain, this is the hash to look for to
  prove no rows were retroactively inserted *before* the exported range.

The canonicalization rule is the same shape used by `_compute_entry_hash`
in `logger.py`: `json.dumps(..., sort_keys=True, separators=(",", ":"),
allow_nan=False, ensure_ascii=False)`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.config import settings

RECEIPT_MARKER_KEY = "receipt"


class SigningKeyUnavailable(RuntimeError):
    """Signing was requested but no key is configured."""


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def load_private_key(pem: str | None = None) -> Ed25519PrivateKey:
    pem_text = pem if pem is not None else settings.audit_export_signing_key
    if not pem_text:
        raise SigningKeyUnavailable("audit_export_signing_key is not configured")
    key = serialization.load_pem_private_key(pem_text.encode("utf-8"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningKeyUnavailable("audit_export_signing_key is not an Ed25519 key")
    return key


def public_key_pem(private_key: Ed25519PrivateKey) -> str:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def generate_keypair_pem() -> tuple[str, str]:
    """Mint a fresh Ed25519 keypair as (private_pem, public_pem)."""
    private_key = Ed25519PrivateKey.generate()
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = public_key_pem(private_key)
    return priv_pem, pub_pem


def build_receipt(
    *,
    range_since: datetime | None,
    range_until: datetime,
    count: int,
    head_entry_hash: str | None,
    tip_entry_hash: str | None,
    content_hash: str,
    exported_by: str,
    signing_key_id: str,
) -> dict[str, Any]:
    """Return the receipt dict in canonical shape, without `signature`."""
    return {
        RECEIPT_MARKER_KEY: True,
        "range": {
            "since": range_since.isoformat() if range_since else None,
            "until": range_until.isoformat(),
            "count": count,
        },
        "head_entry_hash": head_entry_hash,
        "tip_entry_hash": tip_entry_hash,
        "content_hash": content_hash,
        "exported_at": datetime.now(UTC).isoformat(),
        "exported_by": exported_by,
        "signing_key_id": signing_key_id,
    }


def entries_digest(entry_hashes: list[str]) -> str:
    """SHA-256 over the concatenated entry_hashes in export order.

    Lets a verifier confirm an exported file was not partially truncated
    without re-hashing every entry's payload.
    """
    h = hashlib.sha256()
    for entry_hash in entry_hashes:
        h.update(entry_hash.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def sign_receipt(
    receipt: dict[str, Any],
    private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    """Return the receipt with a `signature` field appended.

    The signature covers the canonical JSON of the receipt as passed in
    (which MUST NOT already contain a `signature` key).
    """
    if "signature" in receipt:
        raise ValueError("receipt already has a signature field")
    signed_payload = _canonical_bytes(receipt)
    signature = private_key.sign(signed_payload).hex()
    return {**receipt, "signature": signature}


def verify_receipt(
    receipt: dict[str, Any],
    public_key_pem_str: str,
) -> bool:
    if "signature" not in receipt:
        return False
    signature_hex = receipt["signature"]
    payload = {k: v for k, v in receipt.items() if k != "signature"}
    pub = serialization.load_pem_public_key(public_key_pem_str.encode("utf-8"))
    if not isinstance(pub, Ed25519PublicKey):
        return False
    try:
        pub.verify(bytes.fromhex(signature_hex), _canonical_bytes(payload))
    except InvalidSignature:
        return False
    return True


__all__ = [
    "RECEIPT_MARKER_KEY",
    "SigningKeyUnavailable",
    "build_receipt",
    "entries_digest",
    "generate_keypair_pem",
    "load_private_key",
    "public_key_pem",
    "sign_receipt",
    "verify_receipt",
]
