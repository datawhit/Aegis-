"""Audit export endpoint for compliance receipts."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.models.audit_log import AuditLog
from app.models.user import UserRole

router = APIRouter()


def _require_admin(user) -> None:  # type: ignore[no-untyped-def]
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )


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
    current_user: CurrentUserDep,
    since: datetime | None = Query(
        None,
        description="Only export audit entries created at or after this timestamp.",
    ),
) -> StreamingResponse:
    _require_admin(current_user)

    stmt = select(AuditLog).order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    if since is not None:
        stmt = stmt.where(AuditLog.created_at >= since)

    async def stream_rows() -> str:
        result = await session.stream(stmt)
        async for row in result.scalars():
            yield json.dumps(_serialize_audit_log(row), ensure_ascii=False) + "\n"

    headers = {
        "Content-Disposition": "attachment; filename=audits_export.ndjson"
    }
    return StreamingResponse(
        stream_rows(),
        media_type="application/x-ndjson",
        headers=headers,
    )
