"""Integration tests for auth flow (Sprint 4.5-A)."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_login_page_returns_200(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio()
async def test_login_page_contains_bot_username(client: AsyncClient) -> None:
    response = await client.get("/")
    assert "testbot" in response.text


@pytest.mark.asyncio()
async def test_telegram_callback_invalid_hash(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/telegram/callback",
        json={
            "id": 12345,
            "first_name": "Test",
            "auth_date": 1000000000,
            "hash": "invalid" * 8,
        },
    )
    assert response.status_code == 401
    assert "Invalid login hash" in response.json()["detail"]


@pytest.mark.asyncio()
async def test_telegram_callback_stale_date(client: AsyncClient) -> None:
    bot_token = "123456:FAKE-TOKEN-FOR-TESTS"
    data: dict[str, str | int] = {
        "id": 12345,
        "first_name": "Test",
        "auth_date": int(time.time()) - 200000,
    }
    check_pairs = [f"{k}={data[k]}" for k in sorted(data)]
    check_string = "\n".join(check_pairs)
    secret = hashlib.sha256(bot_token.encode()).digest()
    h = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    data["hash"] = h

    response = await client.post("/auth/telegram/callback", json=data)
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio()
async def test_logout_requires_csrf(client: AsyncClient) -> None:
    response = await client.post(
        "/logout",
        follow_redirects=False,
    )
    assert response.status_code == 403


@pytest.mark.asyncio()
async def test_security_headers_present(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Content-Security-Policy" in response.headers
