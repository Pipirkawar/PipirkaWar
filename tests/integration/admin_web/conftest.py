"""Shared fixtures for admin_web integration tests."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from unittest import mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from pipirik_wars.admin_web.main import create_app
from pipirik_wars.admin_web.settings import AdminWebSettings

_TEST_ENV = {
    "ADMIN_WEB_SECRET_KEY": "x" * 32,
    "ADMIN_WEB_BOT_USERNAME": "testbot",
    "ADMIN_WEB_BOT_TOKEN": "123456:FAKE-TOKEN-FOR-TESTS",
    "ADMIN_WEB_ALLOWED_IPS": "*",
    "ADMIN_WEB_COOKIE_INSECURE_DEV": "true",
    "ADMIN_WEB_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
}


@pytest.fixture()
def admin_web_settings() -> AdminWebSettings:
    with mock.patch.dict(os.environ, _TEST_ENV, clear=False):
        return AdminWebSettings()  # type: ignore[call-arg]


@pytest_asyncio.fixture()
async def client(admin_web_settings: AdminWebSettings) -> AsyncGenerator[AsyncClient]:
    app = create_app(admin_web_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
