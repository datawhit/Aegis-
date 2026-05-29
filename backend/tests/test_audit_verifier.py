"""HashChainVerifier — happy-path + tampering detection."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, get_audit_logger, get_audit_verifier
from app.models.alert import Alert, AlertSeverity, AlertStatus


@pytest.fixture
async def some_alert(db_session: AsyncSession) -> Alert:
    alert = Alert(
        source="test",
        source_event_id=f"evt-{uuid.uuid4()}",
        severity=AlertSeverity.LOW,
        status=AlertStatus.NEW,
        raw_event={},
        normalized={},
    )
    db_session.add(alert)
    await db_session.flush()
    return alert


async def test_verifier_passes_on_clean_chain(db_session: AsyncSession, some_alert: Alert) -> None:
    logger = get_audit_logger()
    for action in ["test.created", "test.updated", "test.archived"]:
        await logger.record(
            db_session,
            actor=Actor.system(label="test"),
            action=action,
            resource_type="alert",
            resource_id=some_alert.id,
            payload={"step": action},
        )
    await db_session.flush()

    verifier = get_audit_verifier()
    report = await verifier.verify(db_session)
    assert report.ok
    assert report.rows_checked >= 3


async def test_verifier_detects_payload_tampering(
    db_session: AsyncSession, some_alert: Alert
) -> None:
    logger = get_audit_logger()
    entry = await logger.record(
        db_session,
        actor=Actor.system(label="test"),
        action="test.victim",
        resource_type="alert",
        resource_id=some_alert.id,
        payload={"original": "value"},
    )
    await db_session.flush()

    # Tamper: change the payload after the hash was computed.
    entry.payload = {"original": "TAMPERED"}
    await db_session.flush()

    verifier = get_audit_verifier()
    report = await verifier.verify(db_session)
    assert not report.ok
    assert entry.id in report.hash_mismatches


async def test_verifier_detects_link_break(db_session: AsyncSession, some_alert: Alert) -> None:
    logger = get_audit_logger()
    a = await logger.record(
        db_session,
        actor=Actor.system(label="test"),
        action="test.first",
        resource_type="alert",
        resource_id=some_alert.id,
        payload={"i": 1},
    )
    b = await logger.record(
        db_session,
        actor=Actor.system(label="test"),
        action="test.second",
        resource_type="alert",
        resource_id=some_alert.id,
        payload={"i": 2},
    )
    await db_session.flush()

    # Break the link: rewrite b.prev_hash to something stale.
    b.prev_hash = "0" * 64
    await db_session.flush()

    verifier = get_audit_verifier()
    report = await verifier.verify(db_session)
    assert b.id in report.link_breaks
    _ = a
