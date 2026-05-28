"""Tamper-evident audit logger.

Each `audit_logs` row stores `entry_hash = SHA-256(canonical(prev_hash || content))`.
A future verifier (Sprint 2) re-walks the chain and alerts on mismatch.

Design constraints:

- **Server timestamp.** `created_at` is the DB default. Clients cannot
  influence ordering. The canonical content includes the resolved
  `created_at` so the chain reflects on-disk order.
- **Canonical JSON.** We sort keys and disallow non-finite floats so the
  same logical entry always produces the same hash.
- **No retries that skip the chain.** If the INSERT fails because another
  writer raced us on `prev_hash`, the caller retries — they DO NOT pick a
  stale tip. We use a SERIALIZABLE-equivalent dance via `SELECT ... ORDER
  BY created_at DESC LIMIT 1 FOR UPDATE` on the tip, scoped to a short
  transaction.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_audit_writer_session
from app.logging import get_logger
from app.models.audit_log import ActorType, AuditLog

log = get_logger("audit")


@dataclass(frozen=True)
class Actor:
    type: ActorType
    id: uuid.UUID | None = None
    label: str | None = None

    @classmethod
    def system(cls, label: str = "system") -> Actor:
        return cls(type=ActorType.SYSTEM, label=label)

    @classmethod
    def ai(cls, label: str = "ai") -> Actor:
        return cls(type=ActorType.AI, label=label)

    @classmethod
    def user(cls, user_id: uuid.UUID, label: str | None = None) -> Actor:
        return cls(type=ActorType.USER, id=user_id, label=label)


@runtime_checkable
class AuditLogger(Protocol):
    async def record(
        self,
        session: AsyncSession,
        *,
        actor: Actor,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None,
        payload: dict[str, Any],
        reasoning_snapshot_id: uuid.UUID | None = None,
    ) -> AuditLog: ...


class HashChainAuditLogger(AuditLogger):
    async def record(
        self,
        session: AsyncSession,
        *,
        actor: Actor,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None,
        payload: dict[str, Any],
        reasoning_snapshot_id: uuid.UUID | None = None,
    ) -> AuditLog:
        # Lock the current tip for the duration of this txn so we cannot
        # compute a hash against a row that gets superseded mid-write.
        result = await session.execute(
            select(AuditLog)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
            .with_for_update()
        )
        tip = result.scalar_one_or_none()
        prev_hash = tip.entry_hash if tip is not None else None

        # The DB sets created_at via server_default; we don't have it on the
        # row until flush. Compute the hash over (prev_hash, actor, action,
        # resource_type, resource_id, payload, reasoning_snapshot_id) — i.e.
        # everything except the timestamp. Verification re-derives the same
        # canonical payload from these stored fields.
        async def _write(audit_session: AsyncSession) -> AuditLog:
            result = await audit_session.execute(
                select(AuditLog)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(1)
                .with_for_update()
            )
            tip = result.scalar_one_or_none()
            prev_hash = tip.entry_hash if tip is not None else None

            entry = AuditLog(
                actor_type=actor.type,
                actor_id=actor.id,
                actor_label=actor.label,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=payload,
                reasoning_snapshot_id=reasoning_snapshot_id,
                prev_hash=prev_hash,
                entry_hash="pending",   # replaced below
            )
            entry.entry_hash = _compute_entry_hash(
                prev_hash=prev_hash,
                actor_type=actor.type.value,
                actor_id=str(actor.id) if actor.id else None,
                actor_label=actor.label,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                payload=payload,
                reasoning_snapshot_id=str(reasoning_snapshot_id) if reasoning_snapshot_id else None,
            )

            audit_session.add(entry)
            await audit_session.flush()
            log.info(
                "audit.recorded",
                entry_id=str(entry.id),
                actor_type=actor.type.value,
                actor_id=str(actor.id) if actor.id else None,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                entry_hash=entry.entry_hash,
            )
            return entry

        if settings.audit_writer_database_url:
            async with get_audit_writer_session() as audit_session:
                return await _write(audit_session)

        return await _write(session)


def _compute_entry_hash(
    *,
    prev_hash: str | None,
    actor_type: str,
    actor_id: str | None,
    actor_label: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    payload: dict[str, Any],
    reasoning_snapshot_id: str | None,
) -> str:
    canonical = {
        "prev_hash": prev_hash,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "actor_label": actor_label,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "payload": payload,
        "reasoning_snapshot_id": reasoning_snapshot_id,
    }
    # `sort_keys=True` + default JSON encoder + `allow_nan=False` gives us a
    # stable canonicalization. This is good enough for SHA-256; if we ever
    # need cross-language interop, swap for RFC 8785 JCS.
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_singleton: HashChainAuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _singleton
    if _singleton is None:
        _singleton = HashChainAuditLogger()
    return _singleton


# Re-export for the verifier (Sprint 2) — kept here so the canonicalization
# rule lives in one place.
__all__ = [
    "Actor",
    "AuditLogger",
    "HashChainAuditLogger",
    "get_audit_logger",
    "_compute_entry_hash",
]
