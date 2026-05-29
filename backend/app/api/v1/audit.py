"""Audit export endpoint for compliance receipts.

Sprint 4: the export now ends with a cryptographically-signed receipt
line that binds (a) the exported range, (b) the SHA-256 of all exported
entry hashes, (c) the chain tip at export time. See
`app.core.audit.export_signer` for the format and verification path.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import AdminOrReviewerDep, SessionDep
from app.config import settings
from app.core.audit.export_signer import (
    SigningKeyUnavailable,
    build_receipt,
    entries_digest,
    load_private_key,
    sign_receipt,
)
from app.core.audit.logger import Actor, get_audit_logger
from app.logging import get_logger
from app.models.audit_log import AuditLog

router = APIRouter()
log = get_logger("audit.export")


def _serialize_audit_log(row: AuditLog) -> dict:
    return {
        "id": str(row.id),
        "created_at": row.created_at.isoformat(),
        "actor_type": row.actor_type.value
        if hasattr(row.actor_type, "value")
        else str(row.actor_type),
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "actor_label": row.actor_label,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": str(row.resource_id) if row.resource_id else None,
        "payload": row.payload,
        "reasoning_snapshot_id": str(row.reasoning_snapshot_id)
        if row.reasoning_snapshot_id
        else None,
        "prev_hash": row.prev_hash,
        "entry_hash": row.entry_hash,
    }


@router.get("/audit/export")
async def export_audit(
    session: SessionDep,
    current_user: AdminOrReviewerDep,
    since: datetime | None = Query(
        None,
        description="Only export audit entries created at or after this timestamp.",
    ),
    require_signature: bool = Query(
        True,
        description="When true (default), refuse to export if no signing key is configured.",
    ),
) -> StreamingResponse:
    # Snapshot the chain tip BEFORE recording the export. This way the
    # receipt's tip_entry_hash refers to state immediately prior to this
    # export, and the "audit.exported" entry we write next is *not*
    # included in this export — preventing the circular case where the
    # export references its own request.
    tip_row = (
        await session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    snapshot_until = tip_row.created_at if tip_row is not None else None
    tip_entry_hash = tip_row.entry_hash if tip_row is not None else None

    try:
        private_key = load_private_key()
        signing_available = True
    except SigningKeyUnavailable:
        if require_signature:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="audit export signing key not configured",
            ) from None
        private_key = None
        signing_available = False

    # Record the export request on the chain. This audit entry will land
    # AFTER snapshot_until, so it's not in this export — but it IS in
    # any future export, which is the point.
    await get_audit_logger().record(
        session,
        actor=Actor.user(current_user.id, label=current_user.email),
        action="audit.exported",
        resource_type="audit_log",
        resource_id=None,
        payload={
            "since": since.isoformat() if since else None,
            "snapshot_until": snapshot_until.isoformat() if snapshot_until else None,
            "tip_entry_hash": tip_entry_hash,
            "signing_key_id": settings.audit_export_signing_key_id,
            "signed": signing_available,
        },
    )
    await session.commit()

    stmt = select(AuditLog).order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    if since is not None:
        stmt = stmt.where(AuditLog.created_at >= since)
    if snapshot_until is not None:
        stmt = stmt.where(AuditLog.created_at <= snapshot_until)

    async def stream_rows() -> AsyncIterator[str]:
        entry_hashes: list[str] = []
        head_entry_hash: str | None = None
        count = 0
        result = await session.stream(stmt)
        async for row in result.scalars():
            yield json.dumps(_serialize_audit_log(row), ensure_ascii=False) + "\n"
            entry_hashes.append(row.entry_hash)
            head_entry_hash = row.entry_hash
            count += 1

        receipt = build_receipt(
            range_since=since,
            range_until=snapshot_until or datetime.now(UTC),
            count=count,
            head_entry_hash=head_entry_hash,
            tip_entry_hash=tip_entry_hash,
            content_hash=entries_digest(entry_hashes),
            exported_by=current_user.email,
            signing_key_id=settings.audit_export_signing_key_id,
        )
        if private_key is not None:
            receipt = sign_receipt(receipt, private_key)
        else:
            receipt = {**receipt, "signature": None}
        log.info(
            "audit.export.completed",
            count=count,
            signed=signing_available,
            actor=current_user.email,
        )
        yield json.dumps(receipt, ensure_ascii=False) + "\n"

    headers = {"Content-Disposition": "attachment; filename=audits_export.ndjson"}
    return StreamingResponse(
        stream_rows(),
        media_type="application/x-ndjson",
        headers=headers,
    )
