"""pytest fixtures.

Phase 0 keeps the test surface deliberately small: a single async HTTP
client that hits the in-process app. Real DB-backed integration tests
arrive in Sprint 1 with the first business logic.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
