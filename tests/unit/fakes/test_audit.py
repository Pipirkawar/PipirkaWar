"""Тесты `FakeAuditLogger`."""

from __future__ import annotations

from datetime import UTC, datetime

from pipirik_wars.domain.shared.ports import AuditAction, AuditEntry
from tests.fakes import FakeAuditLogger


class TestFakeAuditLogger:
    async def test_record_appends_entry(self) -> None:
        logger = FakeAuditLogger()
        entry = AuditEntry(
            action=AuditAction.LENGTH_GRANT,
            actor_id=None,
            target_kind="player",
            target_id="42",
            before={"length": 2},
            after={"length": 7},
            reason="forest",
            idempotency_key="forest:42:1",
            occurred_at=datetime(2026, 5, 4, tzinfo=UTC),
        )
        await logger.record(entry)
        assert logger.entries == [entry]

    async def test_record_preserves_order(self) -> None:
        logger = FakeAuditLogger()
        for i in range(3):
            await logger.record(
                AuditEntry(
                    action=AuditAction.DAILY_HEAD_ASSIGN,
                    actor_id=None,
                    target_kind="clan",
                    target_id=str(i),
                    before=None,
                    after={"user_id": i, "bonus_cm": i + 1},
                    reason="daily_head_cron",
                    idempotency_key=f"daily_head:{i}",
                    occurred_at=datetime(2026, 5, 4, tzinfo=UTC),
                )
            )
        assert [e.target_id for e in logger.entries] == ["0", "1", "2"]
