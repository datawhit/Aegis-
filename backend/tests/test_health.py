"""Smoke tests for the health endpoints."""
from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


async def test_readiness_runs_db_check(client: AsyncClient) -> None:
    response = await client.get("/api/v1/ready")
    # In CI with Postgres available this is 200; with no DB it should be 503.
    assert response.status_code in (200, 503)
    body = response.json()
    if response.status_code == 200:
        assert body["status"] == "ready"
        assert body["checks"]["postgres"] == "ok"
