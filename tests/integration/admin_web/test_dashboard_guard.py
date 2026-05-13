"""Integration tests for dashboard TOTP guard (Sprint 4.5-A)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_dashboard_without_session_returns_401(client: AsyncClient) -> None:
    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_totp_page_without_session_returns_401(client: AsyncClient) -> None:
    response = await client.get("/totp", follow_redirects=False)
    assert response.status_code in (302, 401)
