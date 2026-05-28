"""pytest fixtures.

- `client`: ASGI client against the live app (used for endpoint tests).
- `db_session`: an async SQLAlchemy session bound to the migrated Postgres
  used in CI. Each test is wrapped in a savepoint and rolled back so tests
  don't leak state.

Tests that need only the app (no DB) use `client`. Tests that exercise
services / SQL queries use `db_session`.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import engine
from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session that rolls back at the end of the test.

    Uses the app's actual engine (so we hit the same migrated schema CI
    set up). The `BEGIN`/`ROLLBACK` pattern means each test starts clean
    without per-test `truncate` calls.
    """
    connection = await engine.connect()
    transaction = await connection.begin()
    SessionLocal = async_sessionmaker(bind=connection, expire_on_commit=False)
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await transaction.rollback()
            await connection.close()
