"""Integration tests for audit-log route (Sprint 4.5-F)."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from pipirik_wars.admin_web.auth.session import AdminSession
from pipirik_wars.admin_web.settings import AdminWebSettings
from tests.integration.admin_web.conftest import _create_schema_and_client


def _encode_session(
    client: AsyncClient,
    *,
    totp_verified: bool = True,
) -> str:
    transport = client._transport
    app = transport.app  # type: ignore[attr-defined]
    container = app.state.container
    session = AdminSession(
        admin_id=123456,
        tg_username="testadmin",
        csrf_token="test-csrf-token",
        totp_verified_at=time.time() if totp_verified else None,
    )
    result: str = container.session_manager.encode(session)
    return result


@pytest_asyncio.fixture()
async def authed_client(
    admin_web_settings: AdminWebSettings,
) -> AsyncGenerator[AsyncClient]:
    c = await _create_schema_and_client(admin_web_settings)
    cookie_value = _encode_session(c)
    c.cookies.set("session", cookie_value)
    yield c
    await c.aclose()


@pytest.mark.asyncio()
async def test_audit_page_without_session_returns_401(client: AsyncClient) -> None:
    response = await client.get("/audit", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_audit_page_without_totp_redirects(
    admin_web_settings: AdminWebSettings,
) -> None:
    c = await _create_schema_and_client(admin_web_settings)
    cookie_value = _encode_session(c, totp_verified=False)
    c.cookies.set("session", cookie_value)
    async with c:
        response = await c.get("/audit", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_audit_page_with_session_returns_200(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/audit", follow_redirects=False)
    assert response.status_code == 200
    assert "Audit Log" in response.text


@pytest.mark.asyncio()
async def test_audit_table_partial_returns_200(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/audit/table", follow_redirects=False)
    assert response.status_code == 200
    assert "No audit records found" in response.text


@pytest.mark.asyncio()
async def test_audit_page_with_filters(authed_client: AsyncClient) -> None:
    response = await authed_client.get(
        "/audit?source=bot&log_type=bot&page=1",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio()
async def test_audit_page_with_date_filter(authed_client: AsyncClient) -> None:
    response = await authed_client.get(
        "/audit?date_from=2026-01-01T00:00&date_to=2026-12-31T23:59",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio()
async def test_audit_page_with_invalid_page(authed_client: AsyncClient) -> None:
    response = await authed_client.get(
        "/audit?page=abc",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio()
async def test_audit_page_with_actor_filter(authed_client: AsyncClient) -> None:
    response = await authed_client.get(
        "/audit?actor_id=12345",
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.asyncio()
async def test_audit_page_admin_log_type(authed_client: AsyncClient) -> None:
    response = await authed_client.get(
        "/audit?log_type=admin",
        follow_redirects=False,
    )
    assert response.status_code == 200
