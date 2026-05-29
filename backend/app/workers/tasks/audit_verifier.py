"""Scheduled audit-chain verifier — Celery beat task."""

from __future__ import annotations

import asyncio

from app.core.audit import get_audit_verifier
from app.core.notifications import get_notifier
from app.db import session_scope
from app.logging import configure_logging, get_logger
from app.workers.celery_app import celery_app

configure_logging()
log = get_logger("workers.audit_verifier")


@celery_app.task(name="workflows.verify_audit_chain", acks_late=True)
def verify_audit_chain() -> dict:
    return asyncio.run(_run())


async def _run() -> dict:
    verifier = get_audit_verifier()
    async with session_scope() as session:
        report = await verifier.verify(session)

    if not report.ok:
        # P0 — chain has been tampered with (or, more likely, the
        # canonicalization changed without bumping the verifier).
        notifier = get_notifier()
        await notifier.notify(
            title="Audit chain verification FAILED",
            body=(
                f"Checked {report.rows_checked} rows. "
                f"{len(report.hash_mismatches)} hash mismatch(es), "
                f"{len(report.link_breaks)} link break(s). "
                "Investigate immediately."
            ),
            severity="critical",
        )

    return {
        "ok": report.ok,
        "rows_checked": report.rows_checked,
        "hash_mismatches": [str(i) for i in report.hash_mismatches],
        "link_breaks": [str(i) for i in report.link_breaks],
    }
