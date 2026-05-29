"""Microsoft Defender XDR connector.

Real Defender webhooks (Defender for Endpoint, Defender for Cloud Apps,
M365 Defender unified portal) emit different shapes. Phase 1 supports the
**Defender XDR alert** shape — the canonical "unified" format. Per-product
shapes get their own normalizers in later sprints.

What we extract:

  - `source_event_id`     ← Defender's `alertId`
  - `correlation_key`     ← `incidentId` if present, else hash of category +
                            primary affected entity. Defender already
                            does some grouping; we ride on it where we
                            can.
  - `severity_hint`       ← Defender's `severity` (Informational/Low/...)
                            mapped to our scale (info/low/medium/high/critical)
  - `affected_entities`   ← user / device / file / IP / URL entities
  - `indicators`          ← IOCs (hashes, IPs, domains)

References (current as of Defender XDR docs):
  https://learn.microsoft.com/en-us/defender-xdr/api-incidents
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.core.ingestion.base import Connector, NormalizedAlert

_DEFENDER_SEVERITY_MAP = {
    "informational": "info",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
}


class DefenderConnector(Connector):
    source = "defender"

    def secret(self) -> str:
        return settings.ingest_secret_defender

    def normalize(self, raw_event: dict[str, Any]) -> NormalizedAlert:
        alert_id = str(
            raw_event.get("alertId")
            or raw_event.get("id")
            or raw_event.get("alert_id")
            or _derive_id(raw_event)
        )

        severity_raw = (raw_event.get("severity") or "medium").lower()
        severity_hint = _DEFENDER_SEVERITY_MAP.get(severity_raw, "medium")

        category = str(raw_event.get("category") or "uncategorized")
        title = str(raw_event.get("title") or category or "Defender alert")

        occurred_at = _coerce_iso(
            raw_event.get("createdDateTime")
            or raw_event.get("firstActivityDateTime")
            or raw_event.get("eventTime")
        )

        affected = _extract_entities(raw_event)
        indicators = _extract_indicators(raw_event)
        correlation_key = _correlation_key(raw_event, category=category, affected=affected)

        return NormalizedAlert(
            source=self.source,
            source_event_id=alert_id,
            correlation_key=correlation_key,
            severity_hint=severity_hint,
            category=category,
            title=title,
            occurred_at=occurred_at,
            affected_entities=affected,
            indicators=indicators,
            raw_event_excerpt=_excerpt(raw_event),
        )


def _coerce_iso(value: Any) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    # Microsoft Graph emits ISO 8601 with `Z`; assume it's already correct.
    return str(value)


def _extract_entities(raw: dict[str, Any]) -> dict[str, Any]:
    entities: dict[str, list[Any]] = {
        "users": [],
        "devices": [],
        "files": [],
        "ips": [],
        "urls": [],
    }

    # Defender XDR puts entities under `evidence` (list of typed records).
    for ev in raw.get("evidence") or []:
        kind = (ev.get("@odata.type") or ev.get("entityType") or "").lower()
        if "user" in kind:
            upn = ev.get("userPrincipalName") or ev.get("accountName") or ev.get("name")
            if upn:
                entities["users"].append(upn)
        elif "device" in kind:
            dev = ev.get("deviceDnsName") or ev.get("hostName") or ev.get("deviceId")
            if dev:
                entities["devices"].append(dev)
        elif "file" in kind:
            fh = ev.get("sha256") or ev.get("fileHash") or ev.get("fileName")
            if fh:
                entities["files"].append(fh)
        elif "ip" in kind:
            ip = ev.get("ipAddress") or ev.get("address")
            if ip:
                entities["ips"].append(ip)
        elif "url" in kind:
            url = ev.get("url")
            if url:
                entities["urls"].append(url)

    # Strip empty lists so the payload is tight.
    return {k: v for k, v in entities.items() if v}


def _extract_indicators(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, list[Any]] = {"hashes": [], "ips": [], "domains": []}
    for ev in raw.get("evidence") or []:
        if h := ev.get("sha256") or ev.get("sha1") or ev.get("md5"):
            out["hashes"].append(h)
        if ip := ev.get("ipAddress"):
            out["ips"].append(ip)
        if dom := ev.get("domainName") or ev.get("url"):
            out["domains"].append(dom)
    return {k: v for k, v in out.items() if v}


def _correlation_key(raw: dict[str, Any], *, category: str, affected: dict[str, Any]) -> str | None:
    # Prefer Defender's own incidentId — we ride on their grouping.
    if incident_id := raw.get("incidentId"):
        return f"defender:incident:{incident_id}"

    # Fallback: category + first affected entity (user > device > ip).
    pivot: str | None = None
    if users := affected.get("users"):
        pivot = f"user:{users[0]}"
    elif devices := affected.get("devices"):
        pivot = f"device:{devices[0]}"
    elif ips := affected.get("ips"):
        pivot = f"ip:{ips[0]}"

    if pivot is None:
        return None
    payload = f"defender:{category}:{pivot}".lower()
    # SHA-1 here is a non-cryptographic clustering key (correlation_key);
    # we just need a stable 32-char hex digest of the canonical pivot.
    return hashlib.sha1(payload.encode(), usedforsecurity=False).hexdigest()[:32]


def _excerpt(raw: dict[str, Any]) -> dict[str, Any]:
    """Trim the raw event to keys an analyst (or the model) actually needs.

    Full payload is still on `alerts.raw_event`. The excerpt is what goes
    into the AI prompt; keeping it tight controls token cost.
    """
    keep = {
        "alertId",
        "incidentId",
        "title",
        "category",
        "severity",
        "status",
        "determination",
        "classification",
        "createdDateTime",
        "lastActivityDateTime",
        "description",
        "mitreTechniques",
        "detectorId",
        "productName",
    }
    return {k: raw[k] for k in keep if k in raw}


def _derive_id(raw: dict[str, Any]) -> str:
    """When the source omits its own ID — derive a stable one so we still dedup."""
    blob = repr(sorted(raw.items()))[:4096]
    return "derived:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]
