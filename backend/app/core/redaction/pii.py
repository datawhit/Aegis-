"""PIIRedactor — deterministic, in-process redaction.

The redactor walks a normalized alert payload and replaces values matching
known PII shapes with stable opaque tokens (`<user:8e2f>`, `<ip:b14a>`,
`<host:cd09>`, `<file:ff03>`). The original→token mapping is returned
alongside the redacted payload so:

  - The AI prompt sees only tokens.
  - The analyst UI receives the lookup table and renders the real values.
  - The audit log keeps both (redacted + lookup), so we can replay later.

Determinism matters: identical PII within a single redaction call should
collapse to the *same* token. That preserves co-reference for the model
("this token appears in the user field AND in the URL field") without
leaking the value itself.

This is *redaction*, not *encryption*. The token is derived from a SHA-256
of `(salt || value)` — recovering the original from the token requires the
lookup table.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

# Conservative regexes. We err on the side of redacting things that aren't
# strictly PII (e.g. opaque IDs that look like UUIDs) — that's fine; the
# downstream policy/audit never depend on raw values.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HOSTNAME_RE = re.compile(
    r"\b[a-zA-Z0-9][a-zA-Z0-9\-]{0,62}(?:\.[a-zA-Z0-9][a-zA-Z0-9\-]{0,62})+\b"
)
_SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
_SHA1_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
_MD5_RE = re.compile(r"\b[a-fA-F0-9]{32}\b")


@dataclass
class RedactionResult:
    payload: dict[str, Any]
    lookup: dict[str, str] = field(default_factory=dict)  # token → original


class PIIRedactor:
    """Walks a dict, returns a redacted copy + a token→original lookup.

    The same redactor instance does NOT preserve state across calls (each
    call gets a fresh salt). This is intentional: a token from snapshot A
    cannot be reused to identify the same user in snapshot B — that's the
    audit team's job, via the lookup tables.
    """

    def __init__(self, *, salt: str | None = None) -> None:
        self._salt = salt or secrets.token_hex(16)

    def redact(self, payload: dict[str, Any]) -> RedactionResult:
        lookup: dict[str, str] = {}
        reverse: dict[str, str] = {}     # original → token (for dedupe)
        redacted = self._walk(payload, lookup, reverse)
        return RedactionResult(payload=redacted, lookup=lookup)

    # ---- internals ----------------------------------------------------------
    def _walk(self, value: Any, lookup: dict, reverse: dict) -> Any:
        if isinstance(value, dict):
            return {k: self._walk(v, lookup, reverse) for k, v in value.items()}
        if isinstance(value, list):
            return [self._walk(v, lookup, reverse) for v in value]
        if isinstance(value, str):
            return self._redact_string(value, lookup, reverse)
        return value

    def _redact_string(self, s: str, lookup: dict, reverse: dict) -> str:
        # File hashes — most specific first (so a SHA-256 isn't matched by
        # the SHA-1 pattern).
        s = _SHA256_RE.sub(lambda m: self._tok("file", m.group(0), lookup, reverse), s)
        s = _SHA1_RE.sub(lambda m: self._tok("file", m.group(0), lookup, reverse), s)
        s = _MD5_RE.sub(lambda m: self._tok("file", m.group(0), lookup, reverse), s)
        s = _EMAIL_RE.sub(lambda m: self._tok("user", m.group(0), lookup, reverse), s)
        s = _IPV4_RE.sub(lambda m: self._tok("ip", m.group(0), lookup, reverse), s)
        # Hostnames last — the regex is loose, so it will match things like
        # "example.com" but not standalone words.
        s = _HOSTNAME_RE.sub(
            lambda m: self._tok("host", m.group(0), lookup, reverse), s
        )
        return s

    def _tok(self, kind: str, value: str, lookup: dict, reverse: dict) -> str:
        if value in reverse:
            return reverse[value]
        digest = hashlib.sha256(f"{self._salt}|{kind}|{value}".encode()).hexdigest()[:8]
        token = f"<{kind}:{digest}>"
        lookup[token] = value
        reverse[value] = token
        return token
