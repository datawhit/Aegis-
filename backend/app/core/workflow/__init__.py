"""Workflow engine abstraction (Celery in Phase 0; Temporal migration path)."""
from app.core.workflow.base import (
    WorkflowEngine,
    WorkflowNotFoundError,
    WorkflowRunSnapshot,
    WorkflowStatus,
)
from app.core.workflow.celery_engine import CeleryWorkflowEngine
from app.core.workflow.temporal_stub import TemporalWorkflowEngine

__all__ = [
    "WorkflowEngine",
    "WorkflowRunSnapshot",
    "WorkflowStatus",
    "WorkflowNotFoundError",
    "CeleryWorkflowEngine",
    "TemporalWorkflowEngine",
    "get_workflow_engine",
]


def get_workflow_engine() -> WorkflowEngine:
    """DI entrypoint.

    Phase 0 always returns the Celery implementation. The selector lives
    here so that wiring the eventual Temporal impl is a one-line change
    once ADR-002's migration triggers are met.
    """
    return CeleryWorkflowEngine()
