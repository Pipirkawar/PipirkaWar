"""Integration-тесты `SqlAlchemyAdminAuditQuery` (Спринт 2.5-D.5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminRole,
)
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyAdminRepository
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAdminAuditLogger,
    SqlAlchemyAdminAuditQuery,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


async def _create_admin(
    uow: SqlAlchemyUnitOfWork,
    *,
    tg_id: int,
    role: AdminRole = AdminRole.SUPER_ADMIN,
) -> int:
    repo = SqlAlchemyAdminRepository(uow=uow)
    async with uow:
        admin = await repo.add(
            tg_id=tg_id,
            role=role,
            created_by_admin_id=None,
            note="bootstrap",
        )
    assert admin.id is not None
    return admin.id


async def _record(
    uow: SqlAlchemyUnitOfWork,
    *,
    admin_id: int,
    action: AdminAuditAction,
    occurred_at: datetime,
    target_id: str = "1",
) -> None:
    logger = SqlAlchemyAdminAuditLogger(uow=uow)
    async with uow:
        await logger.record(
            AdminAuditEntry(
                admin_id=admin_id,
                action=action,
                target_kind="player",
                target_id=target_id,
                before=None,
                after=None,
                reason="x",
                idempotency_key=None,
                source=AdminAuditSource.BOT,
                tg_chat_id=None,
                ip=None,
                occurred_at=occurred_at,
            ),
        )


class TestSqlAlchemyAdminAuditQuery:
    @pytest.mark.asyncio
    async def test_returns_actor_tg_id_via_join(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        admin_id = await _create_admin(uow, tg_id=10101)
        await _record(
            uow,
            admin_id=admin_id,
            action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
            occurred_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
        query = SqlAlchemyAdminAuditQuery(uow=uow)
        async with uow:
            recs = await query.list_recent(limit=10)
        assert len(recs) == 1
        rec = recs[0]
        assert rec.actor_admin_id == admin_id
        assert rec.actor_tg_id == 10101
        assert rec.action is AdminAuditAction.ADMIN_PLAYER_FROZEN
        assert rec.source is AdminAuditSource.BOT

    @pytest.mark.asyncio
    async def test_orders_by_occurred_at_desc_with_limit(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        admin_id = await _create_admin(uow, tg_id=20202)
        # Три записи, разные timestamps.
        await _record(
            uow,
            admin_id=admin_id,
            action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
            occurred_at=datetime(2026, 5, 7, 11, 0, tzinfo=UTC),
            target_id="A",
        )
        await _record(
            uow,
            admin_id=admin_id,
            action=AdminAuditAction.ADMIN_PLAYER_BANNED,
            occurred_at=datetime(2026, 5, 7, 13, 0, tzinfo=UTC),
            target_id="B",
        )
        await _record(
            uow,
            admin_id=admin_id,
            action=AdminAuditAction.ADMIN_PLAYER_UNFROZEN,
            occurred_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
            target_id="C",
        )
        query = SqlAlchemyAdminAuditQuery(uow=uow)
        async with uow:
            recs = await query.list_recent(limit=2)
        assert [r.target_id for r in recs] == ["B", "C"]

    @pytest.mark.asyncio
    async def test_filters_by_target_admin_id(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        a = await _create_admin(uow, tg_id=30303)
        b = await _create_admin(uow, tg_id=40404)
        await _record(
            uow,
            admin_id=a,
            action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
            occurred_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
        await _record(
            uow,
            admin_id=b,
            action=AdminAuditAction.ADMIN_PLAYER_BANNED,
            occurred_at=datetime(2026, 5, 7, 12, 30, tzinfo=UTC),
        )
        query = SqlAlchemyAdminAuditQuery(uow=uow)
        async with uow:
            only_a = await query.list_recent(limit=10, target_admin_id=a)
        assert len(only_a) == 1
        assert only_a[0].actor_admin_id == a
        assert only_a[0].actor_tg_id == 30303

    @pytest.mark.asyncio
    async def test_filters_by_action(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        admin_id = await _create_admin(uow, tg_id=50505)
        await _record(
            uow,
            admin_id=admin_id,
            action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
            occurred_at=datetime(2026, 5, 7, 11, 0, tzinfo=UTC),
        )
        await _record(
            uow,
            admin_id=admin_id,
            action=AdminAuditAction.ADMIN_PLAYER_BANNED,
            occurred_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
        query = SqlAlchemyAdminAuditQuery(uow=uow)
        async with uow:
            recs = await query.list_recent(
                limit=10,
                action=AdminAuditAction.ADMIN_PLAYER_BANNED,
            )
        assert len(recs) == 1
        assert recs[0].action is AdminAuditAction.ADMIN_PLAYER_BANNED

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_match(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        await _create_admin(uow, tg_id=60606)
        query = SqlAlchemyAdminAuditQuery(uow=uow)
        async with uow:
            recs = await query.list_recent(limit=10)
        assert recs == ()
