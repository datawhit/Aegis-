"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    actions_feed,
    approvals,
    assistant,
    audit,
    auth,
    health,
    incidents,
    ingest,
    overview,
    policies,
    remediations,
    risk,
    slack,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(ingest.router, tags=["ingest"])
api_router.include_router(incidents.router, tags=["incidents"])
api_router.include_router(approvals.router, tags=["approvals"])
api_router.include_router(remediations.router, tags=["remediations"])
api_router.include_router(policies.router, tags=["policies"])
api_router.include_router(audit.router, tags=["audit"])
api_router.include_router(slack.router, tags=["slack"])
# Sprint 9: operator-first surface area.
api_router.include_router(overview.router, tags=["overview"])
api_router.include_router(actions_feed.router, tags=["actions"])
# Sprint 10: Aegis Assistant chat.
api_router.include_router(assistant.router, tags=["assistant"])
# Sprint 11: Risk Analytics (Pillar 3).
api_router.include_router(risk.router, tags=["risk"])
