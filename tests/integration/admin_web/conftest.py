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
from pipirik_wars.infrastructure.db.base import Base
from pipirik_wars.infrastructure.db.models import (  # noqa: F401
    AdminAuditLogORM,
    AdminORM,
    AuditLogORM,
)

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


async def _create_schema_and_client(
    settings: AdminWebSettings,
) -> AsyncClient:
    app = create_app(settings)
    transport = ASGITransport(app=app)
    engine = app.state.container.session_factory.kw["bind"]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest_asyncio.fixture()
async def client(admin_web_settings: AdminWebSettings) -> AsyncGenerator[AsyncClient]:
    c = await _create_schema_and_client(admin_web_settings)
    async with c:
        yield c
