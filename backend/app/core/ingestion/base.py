"""Connector base — HMAC verifier + normalization protocol.

HMAC scheme (ADR-008):

  - Algorithm: HMAC-SHA-256 over `timestamp || "." || raw_body`.
  - Headers expected:
        X-Aegis-Timestamp: <unix-seconds>
        X-Aegis-Signature: sha256=<hex>
  - Replay window: ±5 minutes (configurable per connector).
  - Constant-time compare via `hmac.compare_digest`.

Real-world connector webhooks (Defender, Okta, Slack, …) all use slightly
different schemes. The strategy is to terminate the connector-native scheme
in the connector's `verify()` method and translate to a uniform internal
representation. For Phase 1 we use the Aegis-canonical scheme above for all
sources — sufficient for a self-managed deployment where customers
configure both ends. Connector-native verification (e.g., Defender's
`aud`-tied JWTs) ships in Phase 2 once we have a real customer to test against.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

DEFAULT_REPLAY_WINDOW_SECONDS = 300


class HMACVerificationError(Exception):
    """Webhook signature failed verification. Always 401."""


@dataclass
class NormalizedAlert:
    """Canonical alert payload produced by a connector's `normalize()`.

    Stored verbatim on `alerts.normalized`. Field names are deliberately
    flat + simple so the AI prompt isn't drowning in nested JSON.
    """

    source: str
    source_event_id: str
    correlation_key: str | None
    severity_hint: str        # source-reported severity, mapped to our scale
    category: str
    title: str
    occurred_at: str          # ISO 8601 UTC
    affected_entities: dict[str, Any] = field(default_factory=dict)
    indicators: dict[str, Any] = field(default_factory=dict)
    raw_event_excerpt: dict[str, Any] = field(default_factory=dict)


def verify_hmac(
    *,
    secret: str,
    raw_body: bytes,
    signature_header: str | None,
    timestamp_header: str | None,
    replay_window_seconds: int = DEFAULT_REPLAY_WINDOW_SECONDS,
    now_unix: int | None = None,
) -> None:
    """Verify Aegis-canonical HMAC. Raises `HMACVerificationError` on failure.

    Failure modes are deliberately not distinguished in the raised message —
    we don't want callers branching on "bad timestamp" vs "bad signature".
    Log the specific reason internally; return one error externally.
    """
    if not signature_header or not timestamp_header:
        raise HMACVerificationError("missing signature or timestamp header")

    try:
        ts = int(timestamp_header)
    except ValueError as exc:
        raise HMACVerificationError("malformed timestamp header") from exc

    now = now_unix if now_unix is not None else int(time.time())
    if abs(now - ts) > replay_window_seconds:
        raise HMACVerificationError("timestamp outside replay window")

    if not signature_header.startswith("sha256="):
        raise HMACVerificationError("unsupported signature algorithm")

    provided = signature_header.removeprefix("sha256=").strip()
    message = f"{ts}.".encode("utf-8") + raw_body
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(provided, expected):
        raise HMACVerificationError("signature mismatch")


@runtime_checkable
class Connector(Protocol):
    """Source-specific webhook handler.

    Each connector owns:
      - its source name (URL path segment)
      - HMAC secret lookup (from settings, or future DB row)
      - normalization from source-specific payload → `NormalizedAlert`
    """

    source: str

    def secret(self) -> str:
        """Return the HMAC secret to use for this connector.

        Implementations read from `app.config.settings` for now; Phase 3
        moves secrets to the DB / Vault.
        """
        ...

    def normalize(self, raw_event: dict[str, Any]) -> NormalizedAlert: ...


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        self._connectors[connector.source] = connector

    def get(self, source: str) -> Connector | None:
        return self._connectors.get(source)

    def sources(self) -> list[str]:
        return sorted(self._connectors.keys())
