"""HashChainVerifier — re-walks the audit chain and reports mismatches.

Runs as a Celery beat task on a configurable schedule. Reports are
emitted as structured log events (`audit.verifier.*`) and — when Slack is
wired (Sprint 2) — posted to the approval channel as a P0 alert.

Verification algorithm:
  1. SELECT all rows from `audit_logs` ORDER BY created_at, id ASC.
  2. For each row, re-derive the entry_hash from its stored fields using
     the same `_compute_entry_hash` the writer uses.
  3. If derived != stored → record a mismatch.
  4. If row N's `prev_hash` != row N-1's `entry_hash` → record a link break.

The walk is O(N) and reads only — no locks beyond the read snapshot. Safe
to run alongside live ingest.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.logger import _compute_entry_hash
from app.logging import get_logger
from app.models.audit_log import AuditLog

log = get_logger("audit.verifier")


@dataclass
class VerifierReport:
    started_at: datetime
    completed_at: datetime
    rows_checked: int
    hash_mismatches: list[uuid.UUID] = field(default_factory=list)
    link_breaks: list[uuid.UUID] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hash_mismatches and not self.link_breaks


class HashChainVerifier:
    async def verify(self, session: AsyncSession) -> VerifierReport:
        from datetime import UTC

        started = datetime.now(UTC)
        report = VerifierReport(
            started_at=started, completed_at=started, rows_checked=0
        )

        # Cursor-style scan would be friendlier for huge chains; Phase 2
        # uses a straight ORDER BY since expected volume (<10M rows) fits
        # comfortably in a server-side cursor. We page-load in 5k batches.
        last_entry_hash: str | None = None
        last_row_id: uuid.UUID | None = None
        offset = 0
        batch_size = 5000

        while True:
            rows = (
                await session.execute(
                    select(AuditLog)
                    .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
                    .limit(batch_size)
                    .offset(offset)
                )
            ).scalars().all()
            if not rows:
                break

            for row in rows:
                report.rows_checked += 1

                # 1) Link check: prev_hash must equal the prior row's entry_hash.
                if last_entry_hash is None:
                    # Genesis row: prev_hash must be NULL.
                    if row.prev_hash is not None:
                        report.link_breaks.append(row.id)
                else:
                    if row.prev_hash != last_entry_hash:
                        report.link_breaks.append(row.id)

                # 2) Hash recomputation.
                derived = _compute_entry_hash(
                    prev_hash=row.prev_hash,
                    actor_type=row.actor_type.value
                    if hasattr(row.actor_type, "value")
                    else str(row.actor_type),
                    actor_id=str(row.actor_id) if row.actor_id else None,
                    actor_label=row.actor_label,
                    action=row.action,
                    resource_type=row.resource_type,
                    resource_id=str(row.resource_id) if row.resource_id else None,
                    payload=row.payload,
                    reasoning_snapshot_id=str(row.reasoning_snapshot_id)
                    if row.reasoning_snapshot_id
                    else None,
                )
                if derived != row.entry_hash:
                    report.hash_mismatches.append(row.id)

                last_entry_hash = row.entry_hash
                last_row_id = row.id

            offset += batch_size

        report.completed_at = datetime.now(UTC)

        log_payload = {
            "rows_checked": report.rows_checked,
            "hash_mismatches": [str(i) for i in report.hash_mismatches],
            "link_breaks": [str(i) for i in report.link_breaks],
            "duration_ms": int(
                (report.completed_at - report.started_at).total_seconds() * 1000
            ),
            "ok": report.ok,
        }
        if report.ok:
            log.info("audit.verifier.ok", **log_payload)
        else:
            log.error("audit.verifier.MISMATCH", **log_payload)

        # `last_row_id` is captured for future scoping (verify-from-checkpoint).
        _ = last_row_id
        return report


_singleton: HashChainVerifier | None = None


def get_audit_verifier() -> HashChainVerifier:
    global _singleton
    if _singleton is None:
        _singleton = HashChainVerifier()
    return _singleton
