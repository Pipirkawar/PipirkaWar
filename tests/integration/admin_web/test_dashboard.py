"""Integration tests for dashboard route (Sprint 4.5-C).

Tests cover:
- Dashboard auth guard (only logged-in + TOTP-verified users)
- Dashboard page rendering with real data widgets
- Empty data rendering
- HTMX partial endpoint
- Data correctness with seeded DB records
"""

from __future__ import annotations

import dataclasses
import os
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pipirik_wars.admin_web.auth.session import AdminSession, SessionManager
from pipirik_wars.admin_web.main import create_app
from pipirik_wars.admin_web.settings import AdminWebSettings
from pipirik_wars.infrastructure.db.base import Base
from pipirik_wars.infrastructure.db.models import (  # noqa: F401
    AdminAuditLogORM,
    AdminORM,
    BossFightORM,
    CaravanORM,
    ClanMemberORM,
    ClanORM,
    PayoutFreezeORM,
    PrizePoolBalanceORM,
    SignupQueueORM,
    UserORM,
)

_TEST_SECRET = "x" * 32

_TEST_ENV = {
    "ADMIN_WEB_SECRET_KEY": _TEST_SECRET,
    "ADMIN_WEB_BOT_USERNAME": "testbot",
    "ADMIN_WEB_BOT_TOKEN": "123456:FAKE-TOKEN-FOR-TESTS",
    "ADMIN_WEB_ALLOWED_IPS": "*",
    "ADMIN_WEB_COOKIE_INSECURE_DEV": "true",
    "ADMIN_WEB_DATABASE_URL": "sqlite+aiosqlite://",
}

_PRIZE_POOL_SEED_AT = datetime(2026, 5, 10, 0, 0, tzinfo=UTC)


def _make_session_cookie(
    admin_id: int = 12345,
    tg_username: str = "testadmin",
) -> str:
    mgr = SessionManager(secret_key=_TEST_SECRET, max_age=3600)
    session = AdminSession(
        admin_id=admin_id,
        tg_username=tg_username,
        totp_verified_at=time.time(),
        csrf_token="test-csrf",
    )
    return mgr.encode(session)


@pytest_asyncio.fixture()
async def _db_engine() -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            insert(PrizePoolBalanceORM),
            [
                {"currency": c, "balance_native": 0, "updated_at": _PRIZE_POOL_SEED_AT}
                for c in ("stars", "ton_nano", "usdt_decimal")
            ],
        )
        await conn.execute(
            insert(PayoutFreezeORM),
            [
                {
                    "id": 1,
                    "is_frozen": False,
                    "frozen_by_admin_id": None,
                    "frozen_at": None,
                    "reason": None,
                }
            ],
        )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def _session_factory(
    _db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=_db_engine, expire_on_commit=False)


def _build_app(
    session_factory: async_sessionmaker[AsyncSession],
) -> FastAPI:
    with mock.patch.dict(os.environ, _TEST_ENV, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]
    app = create_app(settings)
    container = app.state.container
    app.state.container = dataclasses.replace(container, session_factory=session_factory)
    return app


@pytest_asyncio.fixture()
async def anon_client(
    _session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    app = _build_app(_session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture()
async def auth_client(
    _session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    app = _build_app(_session_factory)
    transport = ASGITransport(app=app)
    cookie_value = _make_session_cookie()
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"session": cookie_value},
    ) as c:
        yield c


async def _seed_data(sf: async_sessionmaker[AsyncSession]) -> None:
    """Seed test data: players, caravans, raids, signup queue, audit log."""
    now = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)
    async with sf() as session:
        # Players
        session.add(
            UserORM(
                tg_id=1001,
                length_cm=10,
                thickness_level=1,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            UserORM(
                tg_id=1002,
                length_cm=20,
                thickness_level=2,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            UserORM(
                tg_id=1003,
                length_cm=5,
                thickness_level=1,
                status="frozen",
                created_at=now,
                updated_at=now,
            )
        )

        # Clans (needed for caravan FK)
        session.add(
            ClanORM(
                chat_id=-100,
                chat_kind="supergroup",
                title="Clan A",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            ClanORM(
                chat_id=-200,
                chat_kind="supergroup",
                title="Clan B",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()

        # Signup queue
        session.add(SignupQueueORM(tg_id=2001, enqueued_at=now))
        session.add(SignupQueueORM(tg_id=2002, enqueued_at=now))

        # Active caravan
        session.add(
            CaravanORM(
                sender_clan_id=1,
                receiver_clan_id=2,
                leader_player_id=1,
                status="lobby",
                started_at=now,
                lobby_ends_at=datetime(2026, 5, 13, 13, 0, tzinfo=UTC),
                battle_ends_at=datetime(2026, 5, 13, 14, 0, tzinfo=UTC),
                random_seed=42,
            )
        )

        # Active raid (boss fight)
        session.add(
            BossFightORM(
                kind="raid",
                summoner_player_id=1,
                boss_player_id=2,
                status="in_battle",
                started_at=now,
                lobby_ends_at=datetime(2026, 5, 13, 13, 0, tzinfo=UTC),
                random_seed=99,
                initial_boss_length_cm=100,
                current_boss_length_cm=50,
                current_round=2,
            )
        )

        # Admin + audit log entry
        session.add(AdminORM(tg_id=12345, role="super_admin", is_active=True))
        await session.flush()

        session.add(
            AdminAuditLogORM(
                admin_id=1,
                action="ban_player",
                target_kind="player",
                target_id="42",
                reason="cheating",
                source="bot",
                occurred_at=now,
            )
        )

        await session.commit()


@pytest.mark.asyncio()
async def test_dashboard_without_session_returns_401(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_dashboard_stats_partial_without_session_returns_401(
    anon_client: AsyncClient,
) -> None:
    response = await anon_client.get("/dashboard/stats", follow_redirects=False)
    assert response.status_code in (302, 401)


@pytest.mark.asyncio()
async def test_dashboard_empty_data(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "DAU" in response.text


@pytest.mark.asyncio()
async def test_dashboard_with_seeded_data(
    auth_client: AsyncClient,
    _session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_data(_session_factory)
    response = await auth_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 200
    text = response.text
    assert "Active Caravans" in text
    assert "Active Raids" in text
    assert "Signup Queue" in text
    assert "Total Players" in text


@pytest.mark.asyncio()
async def test_dashboard_stats_partial_with_seeded_data(
    auth_client: AsyncClient,
    _session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_data(_session_factory)
    response = await auth_client.get("/dashboard/stats", follow_redirects=False)
    assert response.status_code == 200
    text = response.text
    assert "Active Caravans" in text
    assert "Active Raids" in text


@pytest.mark.asyncio()
async def test_dashboard_shows_audit_entries(
    auth_client: AsyncClient,
    _session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_data(_session_factory)
    response = await auth_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 200
    assert "ban_player" in response.text


@pytest.mark.asyncio()
async def test_dashboard_htmx_trigger_present(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 200
    assert 'hx-get="/dashboard/stats"' in response.text
    assert "every 30s" in response.text
