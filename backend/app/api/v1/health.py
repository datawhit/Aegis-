"""Health endpoints.

Two flavors:
- `/health` — liveness. Always returns 200 if the process is up.
- `/ready`  — readiness. Verifies dependencies (DB ping). 503 on failure.
"""
from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import SessionDep

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from app import __version__

    return HealthResponse(status="ok", version=__version__)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def ready(session: SessionDep) -> ReadinessResponse:
    checks: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
        return ReadinessResponse(status="ready", checks=checks)
    except Exception as exc:  # pragma: no cover — defensive
        checks["postgres"] = f"fail: {exc.__class__.__name__}"
        # FastAPI doesn't let us return a non-2xx via response_model directly
        # without raising; use HTTPException for the 503.
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "checks": checks},
        ) from exc
