"""End-to-end ingest test.

POST /api/v1/ingest/defender with a signed Defender fixture →
  - Alert row exists, linked to a workflow_run
  - Audit chain has `alert.ingested` entry
  - Replay (same body) is treated as duplicate

We do NOT exercise the Celery task in this test — Celery dispatch is
mocked at the `send_task` boundary so the test runs without a broker.
The triage pipeline itself is covered by `test_triage_service.py`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.workflow_run import WorkflowRun

FIXTURE = Path(__file__).parent / "fixtures" / "defender_alert.json"


def _signed_headers(body: bytes) -> dict[str, str]:
    ts = int(time.time())
    message = f"{ts}.".encode("utf-8") + body
    sig = hmac.new(
        settings.ingest_secret_defender.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Aegis-Timestamp": str(ts),
        "X-Aegis-Signature": f"sha256={sig}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def defender_body() -> bytes:
    return FIXTURE.read_bytes()


async def test_ingest_rejects_missing_signature(
    client: AsyncClient, defender_body: bytes
) -> None:
    r = await client.post("/api/v1/ingest/defender", content=defender_body)
    assert r.status_code == 401


async def test_ingest_rejects_unknown_source(
    client: AsyncClient, defender_body: bytes
) -> None:
    r = await client.post(
        "/api/v1/ingest/nope",
        content=defender_body,
        headers=_signed_headers(defender_body),
    )
    # Source check happens before signature check (so we 404 not 401).
    assert r.status_code == 404


async def test_ingest_persists_alert_and_submits_workflow(
    client: AsyncClient,
    db_session: AsyncSession,
    defender_body: bytes,
) -> None:
    with patch("app.workers.celery_app.celery_app.send_task") as send_task:
        r = await client.post(
            "/api/v1/ingest/defender",
            content=defender_body,
            headers=_signed_headers(defender_body),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] is True
    assert body["duplicate"] is False
    assert send_task.called

    alert_id = body["alert_id"]
    workflow_run_id = body["workflow_run_id"]

    # The /ingest endpoint commits its own transaction, so the rows are
    # visible from a fresh session. (db_session is rolled back at test end,
    # but the rows persisted by the request are independent — we need to
    # clean them up.)
    alert = (
        await db_session.execute(
            select(Alert).where(Alert.id == alert_id)
        )
    ).scalar_one_or_none()
    assert alert is not None
    assert alert.source == "defender"
    assert alert.source_event_id == json.loads(defender_body)["alertId"]

    run = (
        await db_session.execute(
            select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        )
    ).scalar_one_or_none()
    assert run is not None
    assert run.workflow_name == "triage_alert"
    assert run.payload["alert_id"] == alert_id

    # Audit chain has an ingest entry.
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "alert.ingested",
                AuditLog.resource_id == alert.id,
            )
        )
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.entry_hash and len(audit.entry_hash) == 64

    # --- cleanup (since /ingest committed independently) ---
    await db_session.delete(audit)
    await db_session.delete(run)
    await db_session.delete(alert)
    await db_session.flush()


async def test_ingest_dedupes_on_replay(
    client: AsyncClient,
    db_session: AsyncSession,
    defender_body: bytes,
) -> None:
    with patch("app.workers.celery_app.celery_app.send_task"):
        first = await client.post(
            "/api/v1/ingest/defender",
            content=defender_body,
            headers=_signed_headers(defender_body),
        )
        second = await client.post(
            "/api/v1/ingest/defender",
            content=defender_body,
            headers=_signed_headers(defender_body),
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["alert_id"] == second.json()["alert_id"]
    assert second.json()["duplicate"] is True

    # cleanup
    alert_id = first.json()["alert_id"]
    workflow_id = first.json()["workflow_run_id"]
    for audit in (
        await db_session.execute(
            select(AuditLog).where(AuditLog.resource_id == alert_id)
        )
    ).scalars():
        await db_session.delete(audit)
    if (
        run := (
            await db_session.execute(
                select(WorkflowRun).where(WorkflowRun.id == workflow_id)
            )
        ).scalar_one_or_none()
    ) is not None:
        await db_session.delete(run)
    if (
        alert := (
            await db_session.execute(select(Alert).where(Alert.id == alert_id))
        ).scalar_one_or_none()
    ) is not None:
        await db_session.delete(alert)
    await db_session.flush()
