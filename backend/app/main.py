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


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("app.startup")
    log.info(
        "aegis.startup",
        env=settings.env,
        version=__version__,
        identity_provider=settings.identity_provider,
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
