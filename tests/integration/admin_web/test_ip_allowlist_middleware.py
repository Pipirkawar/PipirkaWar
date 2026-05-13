"""Integration tests for IP allowlist middleware (Sprint 4.5-A)."""

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
        "ADMIN_WEB_ALLOWED_IPS": "",
        "ADMIN_WEB_COOKIE_INSECURE_DEV": "true",
        "ADMIN_WEB_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio()
async def test_deny_all_when_empty_allowlist() -> None:
    env = _make_env(ADMIN_WEB_ALLOWED_IPS="")
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/")
        assert response.status_code == 403


@pytest.mark.asyncio()
async def test_allow_all_with_wildcard() -> None:
    env = _make_env(ADMIN_WEB_ALLOWED_IPS="*")
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/")
        assert response.status_code == 200


@pytest.mark.asyncio()
async def test_healthz_always_allowed() -> None:
    env = _make_env(ADMIN_WEB_ALLOWED_IPS="")
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/healthz")
        assert response.status_code == 200
