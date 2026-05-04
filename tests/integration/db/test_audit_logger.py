"""Integration-тесты `SqlAlchemyAuditLogger`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from pipirik_wars.domain.shared.ports import AuditAction, AuditEntry
from pipirik_wars.infrastructure.db.models import AuditLogORM
from pipirik_wars.infrastructure.db.services import SqlAlchemyAuditLogger
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class TestSqlAlchemyAuditLogger:
    @pytest.mark.asyncio
    async def test_record_persists_row(self, uow: SqlAlchemyUnitOfWork) -> None:
        logger = SqlAlchemyAuditLogger(uow=uow)
        entry = AuditEntry(
            action=AuditAction.LENGTH_GRANT,
            actor_id=1001,
            target_kind="player",
            target_id="42",
            before={"length_cm": 5},
            after={"length_cm": 15},
            reason="forest run reward",
            idempotency_key="forest:42:2026-05-04",
            occurred_at=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        )
        async with uow:
            await logger.record(entry)

        async with uow:
            res = await uow.session.execute(select(AuditLogORM))
            rows = res.scalars().all()
            assert len(rows) == 1
            row = rows[0]
            assert row.action == "length_grant"
            assert row.target_kind == "player"
            assert row.target_id == "42"
            assert row.actor_id == 1001
            assert row.before == {"length_cm": 5}
            assert row.after == {"length_cm": 15}
            assert row.reason == "forest run reward"
            assert row.idempotency_key == "forest:42:2026-05-04"

    @pytest.mark.asyncio
    async def test_record_rolls_back_on_exception(self, uow: SqlAlchemyUnitOfWork) -> None:
        logger = SqlAlchemyAuditLogger(uow=uow)
        entry = AuditEntry(
            action=AuditAction.LENGTH_GRANT,
            actor_id=None,
            target_kind="player",
            target_id="999",
            before=None,
            after={"length_cm": 10},
            reason="test",
            idempotency_key=None,
            occurred_at=datetime(2026, 5, 4, tzinfo=UTC),
        )
        with pytest.raises(RuntimeError, match="boom"):
            async with uow:
                await logger.record(entry)
                raise RuntimeError("boom")

        async with uow:
            res = await uow.session.execute(select(AuditLogORM))
            assert res.scalars().all() == []
