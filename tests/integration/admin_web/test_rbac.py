"""Integration-тесты RBAC enforcement для admin-web (Sprint 4.5-B, task 4.5.2).

Проверяет полную цепочку: HTTP-запрос → session cookie → TOTP verify →
Admin из БД → RBAC policy → 200 или 403.

Note: ``session.admin_id`` is matched against ``admins.tg_id`` via
``IAdminRepository.get_by_tg_id``, so cookies carry the ``tg_id`` value.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pipirik_wars.admin_web.auth.csrf import generate_csrf_token
from pipirik_wars.admin_web.auth.rbac import require_permission
from pipirik_wars.admin_web.auth.session import AdminSession, SessionManager
from pipirik_wars.admin_web.main import create_app
from pipirik_wars.admin_web.settings import AdminWebSettings
from pipirik_wars.domain.admin.authorization import AdminCommandKind
from pipirik_wars.domain.admin.entities import Admin
from pipirik_wars.infrastructure.db.base import Base
from pipirik_wars.infrastructure.db.models import AdminAuditLogORM, AdminORM

_dep_freeze = Depends(require_permission(AdminCommandKind.FREEZE_PLAYER))
_dep_broadcast = Depends(require_permission(AdminCommandKind.BROADCAST_ANNOUNCEMENT))
_dep_grant_length = Depends(require_permission(AdminCommandKind.GRANT_LENGTH))

_TEST_ENV = {
    "ADMIN_WEB_SECRET_KEY": "x" * 32,
    "ADMIN_WEB_BOT_USERNAME": "testbot",
    "ADMIN_WEB_BOT_TOKEN": "123456:FAKE-TOKEN-FOR-TESTS",
    "ADMIN_WEB_ALLOWED_IPS": "*",
    "ADMIN_WEB_COOKIE_INSECURE_DEV": "true",
    "ADMIN_WEB_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
}

_SECRET_KEY = "x" * 32


def _make_cookie_header(
    tg_id: int,
    *,
    totp_verified: bool = True,
    tg_username: str | None = "testadmin",
) -> dict[str, str]:
    """Build a Cookie header with ``session.admin_id`` set to *tg_id*."""
    mgr = SessionManager(secret_key=_SECRET_KEY, max_age=3600)
    session = AdminSession(
        admin_id=tg_id,
        tg_username=tg_username,
        totp_verified_at=time.time() if totp_verified else None,
        csrf_token=generate_csrf_token(),
    )
    cookie_val = mgr.encode(session)
    return {"Cookie": f"session={cookie_val}"}


@pytest_asyncio.fixture()
async def _app_with_db() -> AsyncGenerator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI]
]:
    with mock.patch.dict(os.environ, _TEST_ENV, clear=False):
        settings = AdminWebSettings()  # type: ignore[call-arg]

    app = create_app(settings)
    sf: async_sessionmaker[AsyncSession] = app.state.container.session_factory
    engine = sf.kw["bind"]

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, sf, app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _seed_admin(
    sf: async_sessionmaker[AsyncSession],
    *,
    tg_id: int,
    role: str,
    is_active: bool = True,
    totp_secret: str | None = "JBSWY3DPEHPK3PXP",
) -> None:
    async with sf() as session:
        await session.execute(
            insert(AdminORM).values(
                tg_id=tg_id,
                role=role,
                is_active=is_active,
                created_at=datetime.now(tz=UTC),
                created_by_admin_id=None,
                note=None,
                totp_secret=totp_secret,
            ),
        )
        await session.commit()


# ──────────────────────────────────────────────────────────────────────
# Tests: dashboard with RBAC
# ──────────────────────────────────────────────────────────────────────


class TestDashboardRBAC:
    """Dashboard requires ADMIN_STATS — available to all active admins."""

    @pytest.mark.asyncio()
    async def test_no_session_returns_401(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, _, _app = _app_with_db
        resp = await client.get("/dashboard", follow_redirects=False)
        assert resp.status_code in (302, 401)

    @pytest.mark.asyncio()
    async def test_no_totp_redirects_to_totp(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, _app = _app_with_db
        await _seed_admin(sf, tg_id=1001, role="super_admin")
        headers = _make_cookie_header(1001, totp_verified=False)
        resp = await client.get("/dashboard", headers=headers, follow_redirects=False)
        assert resp.status_code == 302

    @pytest.mark.asyncio()
    async def test_super_admin_can_access_dashboard(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, _app = _app_with_db
        await _seed_admin(sf, tg_id=2001, role="super_admin")
        headers = _make_cookie_header(2001)
        resp = await client.get("/dashboard", headers=headers, follow_redirects=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio()
    async def test_read_only_can_access_dashboard(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, _app = _app_with_db
        await _seed_admin(sf, tg_id=2002, role="read_only")
        headers = _make_cookie_header(2002)
        resp = await client.get("/dashboard", headers=headers, follow_redirects=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio()
    async def test_support_can_access_dashboard(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, _app = _app_with_db
        await _seed_admin(sf, tg_id=2003, role="support")
        headers = _make_cookie_header(2003)
        resp = await client.get("/dashboard", headers=headers, follow_redirects=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio()
    async def test_economist_can_access_dashboard(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, _app = _app_with_db
        await _seed_admin(sf, tg_id=2004, role="economist")
        headers = _make_cookie_header(2004)
        resp = await client.get("/dashboard", headers=headers, follow_redirects=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio()
    async def test_inactive_admin_gets_403(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, _app = _app_with_db
        await _seed_admin(sf, tg_id=2005, role="super_admin", is_active=False)
        headers = _make_cookie_header(2005)
        resp = await client.get("/dashboard", headers=headers, follow_redirects=False)
        assert resp.status_code == 403

    @pytest.mark.asyncio()
    async def test_nonexistent_admin_gets_403(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, _, _app = _app_with_db
        headers = _make_cookie_header(99999)
        resp = await client.get("/dashboard", headers=headers, follow_redirects=False)
        assert resp.status_code == 403

    @pytest.mark.asyncio()
    async def test_denied_access_writes_audit_log(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, _app = _app_with_db
        await _seed_admin(sf, tg_id=2006, role="super_admin", is_active=False)
        headers = _make_cookie_header(2006)
        await client.get("/dashboard", headers=headers, follow_redirects=False)

        async with sf() as session:
            result = await session.execute(select(AdminAuditLogORM))
            rows = result.scalars().all()
            assert len(rows) >= 1
            latest = rows[-1]
            assert latest.action == "admin_authorization_denied"
            assert latest.source == "web"


class TestRBACPermissionDenied:
    """Test that routes requiring specific permissions return 403 for wrong roles."""

    @pytest.mark.asyncio()
    async def test_read_only_cannot_access_support_route(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, app = _app_with_db
        await _seed_admin(sf, tg_id=3001, role="read_only")

        @app.get("/test-freeze")
        async def _test_freeze(admin: Admin = _dep_freeze) -> dict[str, str]:
            return {"ok": "true"}

        headers = _make_cookie_header(3001)
        resp = await client.get("/test-freeze", headers=headers, follow_redirects=False)
        assert resp.status_code == 403

    @pytest.mark.asyncio()
    async def test_support_can_access_support_route(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, app = _app_with_db
        await _seed_admin(sf, tg_id=3002, role="support")

        @app.get("/test-freeze-ok")
        async def _test_freeze_ok(admin: Admin = _dep_freeze) -> dict[str, str]:
            return {"ok": "true"}

        headers = _make_cookie_header(3002)
        resp = await client.get("/test-freeze-ok", headers=headers, follow_redirects=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio()
    async def test_economist_cannot_access_super_admin_route(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, app = _app_with_db
        await _seed_admin(sf, tg_id=3003, role="economist")

        @app.get("/test-broadcast")
        async def _test_broadcast(admin: Admin = _dep_broadcast) -> dict[str, str]:
            return {"ok": "true"}

        headers = _make_cookie_header(3003)
        resp = await client.get("/test-broadcast", headers=headers, follow_redirects=False)
        assert resp.status_code == 403

    @pytest.mark.asyncio()
    async def test_super_admin_can_access_broadcast_route(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, app = _app_with_db
        await _seed_admin(sf, tg_id=3004, role="super_admin")

        @app.get("/test-broadcast-ok")
        async def _test_broadcast_ok(admin: Admin = _dep_broadcast) -> dict[str, str]:
            return {"ok": "true"}

        headers = _make_cookie_header(3004)
        resp = await client.get("/test-broadcast-ok", headers=headers, follow_redirects=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio()
    async def test_economist_can_access_grant_length_route(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, app = _app_with_db
        await _seed_admin(sf, tg_id=3005, role="economist")

        @app.get("/test-grant-length")
        async def _test_grant_length(admin: Admin = _dep_grant_length) -> dict[str, str]:
            return {"ok": "true"}

        headers = _make_cookie_header(3005)
        resp = await client.get("/test-grant-length", headers=headers, follow_redirects=False)
        assert resp.status_code == 200

    @pytest.mark.asyncio()
    async def test_support_cannot_access_grant_length_route(
        self,
        _app_with_db: tuple[AsyncClient, async_sessionmaker[AsyncSession], FastAPI],
    ) -> None:
        client, sf, app = _app_with_db
        await _seed_admin(sf, tg_id=3006, role="support")

        @app.get("/test-grant-length-deny")
        async def _test_grant_length_deny(admin: Admin = _dep_grant_length) -> dict[str, str]:
            return {"ok": "true"}

        headers = _make_cookie_header(3006)
        resp = await client.get(
            "/test-grant-length-deny",
            headers=headers,
            follow_redirects=False,
        )
        assert resp.status_code == 403
