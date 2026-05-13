"""Integration tests for /healthz endpoint (Sprint 4.5-A)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_healthz_returns_200(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data


@pytest.mark.asyncio()
async def test_healthz_bypasses_ip_allowlist(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
