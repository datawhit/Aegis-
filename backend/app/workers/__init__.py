"""Celery worker app + task registry.

Sprint 1+ tasks register on `celery_app` via the `@celery_app.task` decorator
using the name convention `workflows.<workflow_name>` (and
`workflows.<workflow_name>__rollback` for compensations).
"""
