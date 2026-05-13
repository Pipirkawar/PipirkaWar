"""Integration tests for proxy-chain / SSH-tunnel scenarios (Sprint 4.5-H)."""

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
        "ADMIN_WEB_ALLOWED_IPS": "10.0.0.0/8",
        "ADMIN_WEB_TRUST_PROXY": "true",
        "ADMIN_WEB_COOKIE_INSECURE_DEV": "true",
        "ADMIN_WEB_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio()
async def test_xff_single_trusted_proxy() -> None:
    """Request through one private proxy — client IP extracted."""
    env = _make_env()
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/",
            headers={"X-Forwarded-For": "10.1.2.3, 192.168.1.1"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio()
async def test_xff_spoofed_header_denied() -> None:
    """Spoofed X-Forwarded-For with untrusted real IP — denied."""
    env = _make_env(ADMIN_WEB_ALLOWED_IPS="10.0.0.0/8")
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/",
            headers={"X-Forwarded-For": "10.0.0.1, 8.8.8.8"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio()
async def test_xff_with_explicit_trusted_proxy_cidrs() -> None:
    """Explicit trusted_proxy_cidrs filters correctly."""
    env = _make_env(
        ADMIN_WEB_ALLOWED_IPS="203.0.113.0/24",
        ADMIN_WEB_TRUSTED_PROXY_CIDRS="10.0.0.0/8",
    )
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/",
            headers={"X-Forwarded-For": "203.0.113.50, 10.0.0.1"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio()
async def test_ssh_tunnel_localhost_allowed() -> None:
    """SSH-tunnel scenario: connection from 127.0.0.1, allowlist includes loopback."""
    env = _make_env(
        ADMIN_WEB_ALLOWED_IPS="127.0.0.0/8",
        ADMIN_WEB_TRUST_PROXY="false",
    )
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/")
        assert resp.status_code == 200


@pytest.mark.asyncio()
async def test_no_trust_proxy_ignores_xff() -> None:
    """When trust_proxy=false, X-Forwarded-For is ignored."""
    env = _make_env(
        ADMIN_WEB_ALLOWED_IPS="127.0.0.0/8",
        ADMIN_WEB_TRUST_PROXY="false",
    )
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    transport = ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/",
            headers={"X-Forwarded-For": "8.8.8.8"},
        )
        assert resp.status_code == 200
