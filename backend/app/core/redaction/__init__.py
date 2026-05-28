"""PII redaction for AI prompts.

Threat model: an alert payload contains identifiers (emails, UPNs, IPs,
device names) that we'd rather not ship to a third-party LLM verbatim. The
redactor replaces those with stable tokens (e.g. `<user:8e2f>`) before the
prompt is sent. A per-snapshot lookup table maps token → original so the UI
can de-redact for the analyst.

Trade-off: the LLM may classify slightly less accurately without raw
identifiers. The cost of *exposing* those identifiers — especially for
self-hosted enterprise customers under GDPR/SOC2 — is much higher.
"""
from app.core.redaction.pii import (
    PIIRedactor,
    RedactionResult,
)

__all__ = ["PIIRedactor", "RedactionResult"]
