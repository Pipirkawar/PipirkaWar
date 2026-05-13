"""Integration tests for CSRF middleware (Sprint 4.5-A)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_post_without_session_returns_403(client: AsyncClient) -> None:
    response = await client.post("/totp/verify", content="code=123456")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio()
async def test_get_requests_bypass_csrf(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200


@pytest.mark.asyncio()
async def test_post_to_exempt_path_no_csrf_needed(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/telegram/callback",
        json={"id": 1, "first_name": "x", "auth_date": 0, "hash": "bad"},
    )
    assert response.status_code in (401, 403)
    assert response.status_code != 403 or "CSRF" not in response.json().get("detail", "")
