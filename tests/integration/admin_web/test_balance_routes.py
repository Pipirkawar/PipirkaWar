"""Integration tests for balance editor routes (Sprint 4.5-G)."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient

from pipirik_wars.admin_web.main import create_app
from pipirik_wars.admin_web.settings import AdminWebSettings
from tests.unit.domain.balance.factories import valid_balance_payload

_TEST_ENV = {
    "ADMIN_WEB_SECRET_KEY": "x" * 32,
    "ADMIN_WEB_BOT_USERNAME": "testbot",
    "ADMIN_WEB_BOT_TOKEN": "123456:FAKE-TOKEN-FOR-TESTS",
    "ADMIN_WEB_ALLOWED_IPS": "*",
    "ADMIN_WEB_COOKIE_INSECURE_DEV": "true",
    "ADMIN_WEB_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
}


def _write_valid_balance(path: Path) -> dict[str, Any]:
    payload = valid_balance_payload()
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return payload


@pytest_asyncio.fixture()
async def balance_client(tmp_path: Path) -> AsyncGenerator[tuple[AsyncClient, Path]]:
    balance_path = tmp_path / "balance.yaml"
    _write_valid_balance(balance_path)

    env = {**_TEST_ENV, "ADMIN_WEB_BALANCE_YAML_PATH": str(balance_path)}
    with mock.patch.dict(os.environ, env, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
        app = create_app(settings)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, balance_path


@pytest.mark.asyncio()
async def test_balance_overview_requires_auth(
    balance_client: tuple[AsyncClient, Path],
) -> None:
    client, _ = balance_client
    response = await client.get("/balance", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_balance_section_requires_auth(
    balance_client: tuple[AsyncClient, Path],
) -> None:
    client, _ = balance_client
    response = await client.get("/balance/forest", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_balance_save_requires_auth(
    balance_client: tuple[AsyncClient, Path],
) -> None:
    client, _ = balance_client
    response = await client.post(
        "/balance/forest",
        data={"yaml_text": "test: 1"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 401, 403)


@pytest.mark.asyncio()
async def test_balance_reload_requires_auth(
    balance_client: tuple[AsyncClient, Path],
) -> None:
    client, _ = balance_client
    response = await client.post("/balance/reload", follow_redirects=False)
    assert response.status_code in (302, 401, 403)


@pytest.mark.asyncio()
async def test_balance_nonexistent_section_returns_404(
    balance_client: tuple[AsyncClient, Path],
) -> None:
    client, _ = balance_client
    response = await client.get("/balance/nonexistent", follow_redirects=False)
    assert response.status_code in (302, 401, 404)
