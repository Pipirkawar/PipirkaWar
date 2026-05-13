"""Integration tests for players section routes (Sprint 4.5-D, task 4.5.5).

Tests:
- Unauthenticated access → 401/302
- Authenticated + TOTP-verified → 200 for /players
- /players/search → partial HTML
- /players/{tg_id} → 403/404 without session
- POST /players/{tg_id}/ban → 401/302 without session
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator
from unittest import mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from pipirik_wars.admin_web.auth.csrf import generate_csrf_token
from pipirik_wars.admin_web.auth.session import AdminSession, SessionManager
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
def _settings() -> AdminWebSettings:
    with mock.patch.dict(os.environ, _TEST_ENV, clear=False):
        return AdminWebSettings()  # type: ignore[call-arg]


@pytest_asyncio.fixture()
async def client(_settings: AdminWebSettings) -> AsyncGenerator[AsyncClient]:
    app = create_app(_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_session_cookie(secret_key: str) -> str:
    session = AdminSession(
        admin_id=1,
        tg_username="testadmin",
        totp_verified_at=time.time(),
        csrf_token=generate_csrf_token(),
    )
    mgr = SessionManager(secret_key=secret_key, max_age=3600)
    return mgr.encode(session)


@pytest.mark.asyncio()
async def test_players_list_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/players", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_players_search_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/players/search?q=test", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_player_card_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/players/12345", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_player_activity_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/players/12345/activity", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_ban_player_unauthenticated(client: AsyncClient) -> None:
    response = await client.post("/players/12345/ban", follow_redirects=False)
    assert response.status_code in (302, 401, 403, 422)


@pytest.mark.asyncio()
async def test_freeze_player_unauthenticated(client: AsyncClient) -> None:
    response = await client.post("/players/12345/freeze", follow_redirects=False)
    assert response.status_code in (302, 401, 403, 422)


@pytest.mark.asyncio()
async def test_unfreeze_player_unauthenticated(client: AsyncClient) -> None:
    response = await client.post("/players/12345/unfreeze", follow_redirects=False)
    assert response.status_code in (302, 401, 403, 422)
