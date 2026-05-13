"""Integration tests for clan admin routes (Sprint 4.5-E)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_clans_list_without_session_returns_401(client: AsyncClient) -> None:
    response = await client.get("/clans", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_clan_card_without_session_returns_401(client: AsyncClient) -> None:
    response = await client.get("/clans/1", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_freeze_without_session_returns_401(client: AsyncClient) -> None:
    response = await client.post("/clans/1/freeze", follow_redirects=False)
    assert response.status_code in (302, 401, 403)


@pytest.mark.asyncio()
async def test_unfreeze_without_session_returns_401(client: AsyncClient) -> None:
    response = await client.post("/clans/1/unfreeze", follow_redirects=False)
    assert response.status_code in (302, 401, 403)


@pytest.mark.asyncio()
async def test_clans_list_with_status_filter_without_session(
    client: AsyncClient,
) -> None:
    response = await client.get("/clans?status=frozen", follow_redirects=False)
    assert response.status_code in (302, 401)
