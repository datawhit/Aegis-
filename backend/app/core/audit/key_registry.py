"""Multi-key signing-key registry (Sprint 6, D-26/D-27).

The Sprint 4 design had one private key in `AEGIS_AUDIT_EXPORT_SIGNING_KEY`.
Rotation in that world means: stop signing with key K, start signing with
K+1 — but then every prior export verifies only against K's public key,
which is no longer in any config. Auditors need to keep a stash of
public keys around indexed by `signing_key_id`.

The registry solves this by letting more than one key exist at once:

- Exactly one entry is `status: "active"`. That's the key the signer uses.
- Any number of entries are `status: "retired"`. Their public PEMs are
  still served by the well-known endpoint and used by the verifier when
  a receipt's `signing_key_id` matches a retired entry.

Storage is a JSON file at `AEGIS_AUDIT_KEY_REGISTRY_PATH`. Single-key
mode (Sprint 4 behavior) is preserved as a fallback: if the path is
unset, a one-entry registry is synthesized from
`AEGIS_AUDIT_EXPORT_SIGNING_KEY` + `AEGIS_AUDIT_EXPORT_SIGNING_KEY_ID`.

File format:

    {
      "keys": [
        {
          "key_id": "aegis-audit-2026-05",
          "status": "active",
          "public_pem": "-----BEGIN PUBLIC KEY-----\\n...\\n-----END PUBLIC KEY-----\\n",
          "private_pem": "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
        },
        {
          "key_id": "aegis-audit-2026-04",
          "status": "retired",
          "public_pem": "-----BEGIN PUBLIC KEY-----\\n...\\n-----END PUBLIC KEY-----\\n"
        }
      ]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.config import settings

KeyStatus = Literal["active", "retired"]


class KeyRegistryError(ValueError):
    """Raised when the registry is missing/malformed/inconsistent."""


@dataclass(frozen=True)
class KeyEntry:
    key_id: str
    public_pem: str
    status: KeyStatus
    private_pem: str | None = None  # active key always has one; retired may not


@dataclass(frozen=True)
class KeyRegistry:
    entries: tuple[KeyEntry, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        active_count = 0
        for e in self.entries:
            if e.key_id in seen:
                raise KeyRegistryError(f"duplicate key_id: {e.key_id}")
            seen.add(e.key_id)
            if e.status == "active":
                active_count += 1
                if not e.private_pem:
                    raise KeyRegistryError(f"active key {e.key_id} must have a private_pem")
        if active_count != 1:
            raise KeyRegistryError(
                f"registry must have exactly one active key, found {active_count}"
            )

    def active(self) -> KeyEntry:
        for e in self.entries:
            if e.status == "active":
                return e
        raise KeyRegistryError("no active key (validation should have caught this)")

    def by_id(self, key_id: str) -> KeyEntry | None:
        for e in self.entries:
            if e.key_id == key_id:
                return e
        return None

    def active_private_key(self) -> Ed25519PrivateKey:
        active = self.active()
        assert active.private_pem is not None
        key = serialization.load_pem_private_key(active.private_pem.encode("utf-8"), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise KeyRegistryError(f"active key {active.key_id} is not Ed25519")
        return key

    def public_view(self) -> list[dict]:
        """Strip private material — safe to serve from /.well-known."""
        return [
            {"key_id": e.key_id, "status": e.status, "public_pem": e.public_pem}
            for e in self.entries
        ]


def load_registry() -> KeyRegistry:
    """Load the active registry, with single-key fallback.

    Resolution order:
      1. AEGIS_AUDIT_KEY_REGISTRY_PATH → JSON file
      2. AEGIS_AUDIT_EXPORT_SIGNING_KEY → one-entry registry
      3. Raise KeyRegistryError (caller surfaces 503 / unsigned mode)
    """
    if settings.audit_key_registry_path:
        return _load_from_path(Path(settings.audit_key_registry_path))

    if settings.audit_export_signing_key:
        # Synthesize a single-key registry from legacy env vars. Compute
        # the public PEM from the private one so the well-known endpoint
        # still has something to publish.
        priv_key = serialization.load_pem_private_key(
            settings.audit_export_signing_key.encode("utf-8"), password=None
        )
        if not isinstance(priv_key, Ed25519PrivateKey):
            raise KeyRegistryError("AEGIS_AUDIT_EXPORT_SIGNING_KEY is not an Ed25519 PEM")
        pub_pem = (
            priv_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )
        entry = KeyEntry(
            key_id=settings.audit_export_signing_key_id,
            status="active",
            public_pem=pub_pem,
            private_pem=settings.audit_export_signing_key,
        )
        return KeyRegistry(entries=(entry,))

    raise KeyRegistryError(
        "No audit signing key configured. Set AEGIS_AUDIT_KEY_REGISTRY_PATH "
        "or AEGIS_AUDIT_EXPORT_SIGNING_KEY."
    )


def _load_from_path(path: Path) -> KeyRegistry:
    if not path.exists():
        raise KeyRegistryError(f"registry file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    keys_raw = raw.get("keys", [])
    if not isinstance(keys_raw, list):
        raise KeyRegistryError("'keys' must be a list")
    entries = tuple(
        KeyEntry(
            key_id=k["key_id"],
            public_pem=k["public_pem"],
            status=k.get("status", "retired"),
            private_pem=k.get("private_pem"),
        )
        for k in keys_raw
    )
    return KeyRegistry(entries=entries)


__all__ = [
    "KeyEntry",
    "KeyRegistry",
    "KeyRegistryError",
    "KeyStatus",
    "load_registry",
]
