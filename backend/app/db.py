"""Async SQLAlchemy engine + session factory.

The application talks to Postgres exclusively through `get_session()` (FastAPI
dependency) or `session_scope()` (workers / scripts). Direct engine use is
discouraged so we have one place to add tracing, query timing, or read/write
splitting later.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)

audit_writer_engine: AsyncEngine | None = None
AuditWriterSessionLocal: async_sessionmaker[AsyncSession] | None = None
if settings.audit_writer_database_url:
    audit_writer_engine = create_async_engine(
        settings.audit_writer_database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
    AuditWriterSessionLocal = async_sessionmaker(
        bind=audit_writer_engine,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an async session per request."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_audit_writer_session() -> AsyncIterator[AsyncSession]:
    if AuditWriterSessionLocal is None:
        raise RuntimeError(
            "AEGIS_AUDIT_WRITER_DATABASE_URL must be set to use the audit writer pool"
        )
    async with AuditWriterSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context manager for workers and scripts."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
