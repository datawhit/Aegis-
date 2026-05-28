"""Celery task modules.

Import each task module here so Celery's autodiscovery picks them up when
the worker boots. The names must match `workflows.<workflow_name>` —
see CeleryWorkflowEngine for the dispatch contract.
"""
from app.workers.tasks import triage  # noqa: F401

__all__ = ["triage"]
