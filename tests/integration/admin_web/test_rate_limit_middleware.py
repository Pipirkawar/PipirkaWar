"""Integration tests for rate-limit middleware (Sprint 4.5-H)."""

from __future__ import annotations

import os
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient

from pipirik_wars.admin_web.main import create_app
from pipirik_wars.admin_web.settings import AdminWebSettings


def _make_env(**overrides: str) -> dict[str, str]:
    base = {
        "ADMIN_WEB_SECRET_KEY": "x" * 32,
        "ADMIN_WEB_BOT_USERNAME": "testbot",
        "ADMIN_WEB_BOT_TOKEN": "123456:FAKE-TOKEN-FOR-TESTS",
        "ADMIN_WEB_ALLOWED_IPS": "*",
        "ADMIN_WEB_COOKIE_INSECURE_DEV": "true",
        "ADMIN_WEB_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio()
async def test_rate_limit_allows_normal_traffic() -> None:
    env = _make_env(
        ADMIN_WEB_RATE_LIMIT_MAX_REQUESTS="5",
        ADMIN_WEB_RATE_LIMIT_WINDOW_SECONDS="60",
    )
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(5):
            resp = await c.post(
                "/auth/telegram/callback",
                json={"id": 1},
            )
            assert resp.status_code != 429


@pytest.mark.asyncio()
async def test_rate_limit_blocks_excessive_requests() -> None:
    env = _make_env(
        ADMIN_WEB_RATE_LIMIT_MAX_REQUESTS="3",
        ADMIN_WEB_RATE_LIMIT_WINDOW_SECONDS="60",
    )
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(3):
            await c.post("/auth/telegram/callback", json={"id": 1})
        resp = await c.post("/auth/telegram/callback", json={"id": 1})
        assert resp.status_code == 429
        assert resp.json()["detail"] == "Too many requests"
        assert "Retry-After" in resp.headers


@pytest.mark.asyncio()
async def test_rate_limit_does_not_affect_non_auth_paths() -> None:
    env = _make_env(
        ADMIN_WEB_RATE_LIMIT_MAX_REQUESTS="1",
        ADMIN_WEB_RATE_LIMIT_WINDOW_SECONDS="60",
    )
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for _ in range(5):
            resp = await c.get("/healthz")
            assert resp.status_code == 200
        for _ in range(5):
            resp = await c.get("/")
            assert resp.status_code == 200
