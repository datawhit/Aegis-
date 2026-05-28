"""Celery application — Phase 0 skeleton.

No tasks defined yet. The worker boots clean against the broker so that
Sprint 1 can land its first real task (alert ingestion) without infra
changes.

Naming convention: every workflow registers under `workflows.<name>` so
`CeleryWorkflowEngine.submit()` can dispatch by name without a separate
registry.
"""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "aegis",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    # Lazy import so failures in app submodules don't crash the worker
    # before it can log them.
    include=[],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Aegis workflows are long-running by nature (waiting on approvals,
    # integration roundtrips). Don't let prefetch hide work from
    # concurrent workers.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Hard cap of 15 min per task. Any workflow approaching this threshold
    # is the trigger for Temporal migration (ADR-002, trigger #2).
    task_time_limit=900,
    task_soft_time_limit=840,
)


@celery_app.task(name="workflows.__ping__")
def ping() -> str:
    """Liveness task. Useful for `celery -A app.workers.celery_app inspect ping`."""
    return "pong"
