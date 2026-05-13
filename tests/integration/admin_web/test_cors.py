"""Integration tests for CORS configuration (Sprint 4.5-H)."""

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
async def test_cors_disabled_by_default() -> None:
    env = _make_env()
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.options(
            "/healthz",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in resp.headers


@pytest.mark.asyncio()
async def test_cors_allows_configured_origin() -> None:
    env = _make_env(
        ADMIN_WEB_CORS_ALLOWED_ORIGINS="https://admin.pipirik.example.com",
    )
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.options(
            "/healthz",
            headers={
                "Origin": "https://admin.pipirik.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert (
            resp.headers.get("access-control-allow-origin") == "https://admin.pipirik.example.com"
        )


@pytest.mark.asyncio()
async def test_cors_rejects_unknown_origin() -> None:
    env = _make_env(
        ADMIN_WEB_CORS_ALLOWED_ORIGINS="https://admin.pipirik.example.com",
    )
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.options(
            "/healthz",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"
