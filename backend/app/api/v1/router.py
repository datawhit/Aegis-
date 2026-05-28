"""API v1 router aggregation."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    approvals,
    auth,
    health,
    incidents,
    ingest,
    policies,
    remediations,
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
api_router.include_router(slack.router, tags=["slack"])
