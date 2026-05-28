"""POST /ingest/{source} — webhook ingestion endpoint.

Contract:

  - 401 if signature/timestamp headers are missing or invalid.
  - 404 if `{source}` doesn't match a registered connector.
  - 400 if the body isn't JSON.
  - 200 with `{accepted: true, alert_id, workflow_run_id, duplicate: bool}`
    on success. Duplicate ingestions (same `source + source_event_id`)
    return the original alert/workflow run rather than creating new rows —
    safe to retry.

We do NOT run AI triage inline. The endpoint returns as fast as it can —
webhooks expect snappy 200s. The actual work happens in a Celery task
submitted via the `WorkflowEngine` interface.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Path, Request, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.core.audit import Actor, get_audit_logger
from app.core.ingestion import (
    HMACVerificationError,
    get_connector_registry,
    verify_hmac,
)
from app.core.workflow import get_workflow_engine
from app.logging import get_logger
from app.models.alert import Alert, AlertSeverity, AlertStatus
from app.schemas.ingest import IngestAccepted

log = get_logger("api.ingest")

router = APIRouter()


@router.post(
    "/ingest/{source}",
    response_model=IngestAccepted,
    status_code=status.HTTP_200_OK,
)
async def ingest(
    request: Request,
    session: SessionDep,
    source: str = Path(..., max_length=64, pattern=r"^[a-z0-9_-]+$"),
) -> IngestAccepted:
    registry = get_connector_registry()
    connector = registry.get(source)
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown source: {source!r}",
        )

    raw_body = await request.body()

    try:
        verify_hmac(
            secret=connector.secret(),
            raw_body=raw_body,
            signature_header=request.headers.get("X-Aegis-Signature"),
            timestamp_header=request.headers.get("X-Aegis-Timestamp"),
        )
    except HMACVerificationError as exc:
        log.warning("ingest.hmac_failed", source=source, reason=str(exc))
        # Audit the rejection so brute-force attempts show up in the chain.
        await get_audit_logger().record(
            session,
            actor=Actor(type=Actor.system().type, label=f"ingest.{source}"),
            action="ingest.rejected",
            resource_type="alert",
            resource_id=None,
            payload={"source": source, "reason": str(exc)},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="signature verification failed",
        ) from exc

    try:
        raw_event: dict = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid JSON body",
        ) from exc

    if not isinstance(raw_event, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="body must be a JSON object",
        )

    normalized = connector.normalize(raw_event)

    # Idempotency: dedupe on (source, source_event_id).
    existing = (
        await session.execute(
            select(Alert).where(
                Alert.source == normalized.source,
                Alert.source_event_id == normalized.source_event_id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        log.info(
            "ingest.duplicate",
            source=source,
            source_event_id=normalized.source_event_id,
            alert_id=str(existing.id),
        )
        # Return the existing alert + any existing workflow_run that was
        # spawned for it. We don't resubmit.
        engine = get_workflow_engine()
        existing_run_id = await engine.submit(
            "triage_alert",
            payload={"alert_id": str(existing.id)},
            idempotency_key=f"triage_alert:{existing.id}",
        )
        return IngestAccepted(
            alert_id=existing.id,
            workflow_run_id=existing_run_id,
            duplicate=True,
        )

    severity = _severity_from_hint(normalized.severity_hint)
    alert = Alert(
        source=normalized.source,
        source_event_id=normalized.source_event_id,
        correlation_key=normalized.correlation_key,
        severity=severity,
        status=AlertStatus.NEW,
        raw_event=raw_event,
        normalized={
            "title": normalized.title,
            "category": normalized.category,
            "severity_hint": normalized.severity_hint,
            "occurred_at": normalized.occurred_at,
            "affected_entities": normalized.affected_entities,
            "indicators": normalized.indicators,
            "raw_event_excerpt": normalized.raw_event_excerpt,
        },
    )
    session.add(alert)
    await session.flush()

    await get_audit_logger().record(
        session,
        actor=Actor(type=Actor.system().type, label=f"ingest.{source}"),
        action="alert.ingested",
        resource_type="alert",
        resource_id=alert.id,
        payload={
            "source": source,
            "source_event_id": normalized.source_event_id,
            "correlation_key": normalized.correlation_key,
            "severity_hint": normalized.severity_hint,
        },
    )
    await session.commit()

    # Submit triage. The engine's submit() is idempotent on
    # idempotency_key so duplicate webhook deliveries can't double-trigger.
    engine = get_workflow_engine()
    run_id = await engine.submit(
        "triage_alert",
        payload={"alert_id": str(alert.id)},
        idempotency_key=f"triage_alert:{alert.id}",
    )

    return IngestAccepted(
        alert_id=alert.id,
        workflow_run_id=run_id,
        duplicate=False,
    )


def _severity_from_hint(hint: str) -> AlertSeverity:
    try:
        return AlertSeverity(hint)
    except ValueError:
        return AlertSeverity.MEDIUM
