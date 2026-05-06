"""Integration-тесты `SqlAlchemyAdminAuditLogger` (Спринт 2.5-A.1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminRole,
)
from pipirik_wars.infrastructure.db.models import AdminAuditLogORM
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyAdminRepository
from pipirik_wars.infrastructure.db.services import SqlAlchemyAdminAuditLogger
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


async def _create_admin(uow: SqlAlchemyUnitOfWork, *, tg_id: int = 12345) -> int:
    """Создаёт активного `super_admin` и возвращает его внутренний `id`."""
    repo = SqlAlchemyAdminRepository(uow=uow)
    async with uow:
        admin = await repo.add(
            tg_id=tg_id,
            role=AdminRole.SUPER_ADMIN,
            created_by_admin_id=None,
            note="bootstrap",
        )
    assert admin.id is not None
    return admin.id


class TestSqlAlchemyAdminAuditLogger:
    @pytest.mark.asyncio
    async def test_record_persists_row_bot_source(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        admin_id = await _create_admin(uow)
        logger = SqlAlchemyAdminAuditLogger(uow=uow)
        entry = AdminAuditEntry(
            admin_id=admin_id,
            action=AdminAuditAction.ADMIN_CONFIRM_REQUESTED,
            target_kind="player",
            target_id="42",
            before={"length_cm": 5},
            after={"length_cm": 15},
            reason="manual length grant",
            idempotency_key="admin:grant_length:42:2026-05-07T12:00",
            source=AdminAuditSource.BOT,
            tg_chat_id=999_888,
            ip=None,
            occurred_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
        async with uow:
            await logger.record(entry)

        async with uow:
            res = await uow.session.execute(select(AdminAuditLogORM))
            rows = res.scalars().all()
            assert len(rows) == 1
            row = rows[0]
            assert row.admin_id == admin_id
            assert row.action == "admin_confirm_requested"
            assert row.target_kind == "player"
            assert row.target_id == "42"
            assert row.before == {"length_cm": 5}
            assert row.after == {"length_cm": 15}
            assert row.reason == "manual length grant"
            assert row.idempotency_key == "admin:grant_length:42:2026-05-07T12:00"
            assert row.source == "bot"
            assert row.tg_chat_id == 999_888
            assert row.ip is None

    @pytest.mark.asyncio
    async def test_record_persists_row_web_source(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        admin_id = await _create_admin(uow)
        logger = SqlAlchemyAdminAuditLogger(uow=uow)
        entry = AdminAuditEntry(
            admin_id=admin_id,
            action=AdminAuditAction.ADMIN_CONFIRM_VERIFIED,
            target_kind="balance_key",
            target_id="forest_run_base_reward_cm",
            before=None,
            after={"value": 12},
            reason="quarterly tuning",
            idempotency_key=None,
            source=AdminAuditSource.WEB,
            tg_chat_id=None,
            ip="203.0.113.7",
            occurred_at=datetime(2026, 5, 7, 12, 30, tzinfo=UTC),
        )
        async with uow:
            await logger.record(entry)

        async with uow:
            row = (await uow.session.execute(select(AdminAuditLogORM))).scalar_one()
            assert row.source == "web"
            assert row.ip == "203.0.113.7"
            assert row.tg_chat_id is None
            assert row.before is None
            assert row.after == {"value": 12}

    @pytest.mark.asyncio
    async def test_record_rejects_invalid_source(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """CHECK-инвариант whitelist source-ов в БД (защита от опечаток)."""
        admin_id = await _create_admin(uow)
        with pytest.raises(IntegrityError):
            async with uow:
                row = AdminAuditLogORM(
                    admin_id=admin_id,
                    action="admin_confirm_requested",
                    target_kind="player",
                    target_id="1",
                    before=None,
                    after=None,
                    reason="x",
                    idempotency_key=None,
                    source="cli",  # вне whitelist-а
                    tg_chat_id=None,
                    ip=None,
                    occurred_at=datetime(2026, 5, 7, tzinfo=UTC),
                )
                uow.session.add(row)
                await uow.session.flush()

    @pytest.mark.asyncio
    async def test_record_rolls_back_on_exception(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Аудит-запись должна откатиться вместе с бизнес-ошибкой в транзакции."""
        admin_id = await _create_admin(uow)
        logger = SqlAlchemyAdminAuditLogger(uow=uow)
        entry = AdminAuditEntry(
            admin_id=admin_id,
            action=AdminAuditAction.ADMIN_CONFIRM_FAILED,
            target_kind="player",
            target_id="1",
            before=None,
            after=None,
            reason="will be rolled back",
            idempotency_key=None,
            source=AdminAuditSource.BOT,
            tg_chat_id=999,
            ip=None,
            occurred_at=datetime(2026, 5, 7, tzinfo=UTC),
        )
        with pytest.raises(RuntimeError, match="boom"):
            async with uow:
                await logger.record(entry)
                raise RuntimeError("boom")

        async with uow:
            res = await uow.session.execute(select(AdminAuditLogORM))
            assert res.scalars().all() == []

    @pytest.mark.asyncio
    async def test_multiple_records_persist_in_order(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        admin_id = await _create_admin(uow)
        logger = SqlAlchemyAdminAuditLogger(uow=uow)

        async with uow:
            for i in range(3):
                await logger.record(
                    AdminAuditEntry(
                        admin_id=admin_id,
                        action=AdminAuditAction.ADMIN_CONFIRM_REQUESTED,
                        target_kind="player",
                        target_id=str(i),
                        before=None,
                        after={"step": i},
                        reason=f"reason {i}",
                        idempotency_key=None,
                        source=AdminAuditSource.BOT,
                        tg_chat_id=1,
                        ip=None,
                        occurred_at=datetime(2026, 5, 7, 12, i, tzinfo=UTC),
                    ),
                )

        async with uow:
            rows = (
                (await uow.session.execute(select(AdminAuditLogORM).order_by(AdminAuditLogORM.id)))
                .scalars()
                .all()
            )
            assert [r.target_id for r in rows] == ["0", "1", "2"]
            assert [r.after for r in rows] == [
                {"step": 0},
                {"step": 1},
                {"step": 2},
            ]
