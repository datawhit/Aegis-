"""pytest fixtures.

- `db_session`: an async SQLAlchemy session bound to a single connection
  with an outer transaction. Each test rolls back at teardown so state
  doesn't leak between tests.
- `client`: ASGI client against the live app. **Overrides `get_session`**
  to yield the same `db_session` connection. This is what lets a test
  add a row via `db_session`, flush it, and then have the FastAPI handler
  read it back through its own dependency injection. Without the override,
  the handler would open a fresh connection from the pool and see nothing
  (the outer transaction is uncommitted).

Tests that need only the app (no DB) just use `client`. Tests that
exercise services / SQL queries use `db_session`. Tests that need both
get them together — the fixtures share state by design.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import engine, get_session
from app.main import app


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session that rolls back at the end of the test.

    Uses the app's actual engine (so we hit the same migrated schema CI
    set up). The `BEGIN`/`ROLLBACK` pattern means each test starts clean
    without per-test `truncate` calls.

    Note: `engine.dispose()` runs at the top of every test. The app's
    async engine has a connection pool, but pytest-asyncio uses a fresh
    event loop per test function — a connection cached on the previous
    test's loop blows up with "Future attached to a different loop" when
    the next test tries to use it. Disposing here forces a clean pool
    bound to the current loop.
    """
    await engine.dispose()
    connection = await engine.connect()
    transaction = await connection.begin()
    # join_transaction_mode="create_savepoint" makes each session-level
    # commit a SAVEPOINT release instead of committing the outer txn,
    # so the final rollback below always wipes test state cleanly even
    # if the test (or handler) called `commit()` along the way.
    SessionLocal = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await transaction.rollback()
            await connection.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        # Yield the test's session directly so FastAPI handlers see the
        # same in-transaction state the test set up. We do NOT commit /
        # rollback here — the outer `db_session` fixture owns the txn.
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        async with LifespanManager(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
    finally:
        app.dependency_overrides.pop(get_session, None)
