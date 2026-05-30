"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.api.well_known import router as well_known_router
from app.config import settings
from app.logging import configure_logging, get_logger
from app.telemetry import configure_telemetry


@asynccontextmanager
async def lifespan(app_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    configure_telemetry(app_)
    log = get_logger("app.startup")

    # D-38: boot-time validation of the audit signing key registry. Catches
    # a malformed registry file before the first audit-export request
    # would surface it as a 503. In non-production, log + continue so
    # local dev can still run without any signing key configured.
    from app.core.audit.key_registry import KeyRegistryError, load_registry

    try:
        reg = load_registry()
        log.info(
            "audit.key_registry.loaded",
            active_key_id=reg.active().key_id,
            total_keys=len(reg.entries),
        )
    except KeyRegistryError as exc:
        if settings.is_production:
            log.error("audit.key_registry.invalid", error=str(exc))
            raise RuntimeError(
                f"Refusing to start in {settings.env}: audit signing key not configured ({exc})"
            ) from exc
        log.warning("audit.key_registry.unconfigured", error=str(exc))

    log.info(
        "aegis.startup",
        env=settings.env,
        version=__version__,
        identity_provider=settings.identity_provider,
        otel_enabled=settings.otel_enabled,
    )
    yield
    log.info("aegis.shutdown")


app = FastAPI(
    title="Aegis API",
    version=__version__,
    description="Autonomous Security Operations Governance Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
# Well-known endpoints live at the root, not under /api/v1, per RFC 5785.
app.include_router(well_known_router, tags=["well-known"])
