"""Unit-тесты доменного порта `IAdminAuditLogger` (Спринт 2.5-A.1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger


class TestAdminAuditAction:
    def test_string_values_match_enum_names(self) -> None:
        """Значения enum должны быть в snake_case (попадают в БД-колонку `action`)."""
        assert AdminAuditAction.ADMIN_CONFIRM_REQUESTED.value == "admin_confirm_requested"
        assert AdminAuditAction.ADMIN_CONFIRM_VERIFIED.value == "admin_confirm_verified"
        assert AdminAuditAction.ADMIN_CONFIRM_FAILED.value == "admin_confirm_failed"

    def test_action_is_str_subclass(self) -> None:
        """Чтобы можно было сериализовать без `.value`."""
        assert isinstance(AdminAuditAction.ADMIN_CONFIRM_REQUESTED, str)

    def test_economy_actions_present(self) -> None:
        """Спринт 2.5-C: команды экономики (`/grant_*`, `/balance_*`)."""
        assert AdminAuditAction.ADMIN_GRANT_LENGTH.value == "admin_grant_length"
        assert AdminAuditAction.ADMIN_GRANT_THICKNESS.value == "admin_grant_thickness"
        assert AdminAuditAction.ADMIN_BALANCE_GET.value == "admin_balance_get"
        assert AdminAuditAction.ADMIN_BALANCE_SET.value == "admin_balance_set"


class TestAdminAuditSource:
    def test_only_bot_and_web_allowed(self) -> None:
        """Whitelist соответствует БД-CHECK-инварианту."""
        assert {s.value for s in AdminAuditSource} == {"bot", "web"}


class TestAdminAuditEntry:
    def test_entry_is_immutable(self) -> None:
        entry = self._sample_entry()
        with pytest.raises(AttributeError):
            entry.reason = "tampered"

    def test_entry_carries_all_fields(self) -> None:
        entry = self._sample_entry()
        assert entry.admin_id == 7
        assert entry.action is AdminAuditAction.ADMIN_CONFIRM_REQUESTED
        assert entry.target_kind == "player"
        assert entry.target_id == "42"
        assert entry.source is AdminAuditSource.BOT

    @staticmethod
    def _sample_entry() -> AdminAuditEntry:
        return AdminAuditEntry(
            admin_id=7,
            action=AdminAuditAction.ADMIN_CONFIRM_REQUESTED,
            target_kind="player",
            target_id="42",
            before=None,
            after={"length_cm": 10},
            reason="manual length grant",
            idempotency_key=None,
            source=AdminAuditSource.BOT,
            tg_chat_id=999,
            ip=None,
            occurred_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )


class TestFakeAdminAuditLogger:
    @pytest.mark.asyncio
    async def test_records_appended_in_order(self) -> None:
        logger = FakeAdminAuditLogger()
        e1 = AdminAuditEntry(
            admin_id=1,
            action=AdminAuditAction.ADMIN_CONFIRM_REQUESTED,
            target_kind="player",
            target_id="1",
            before=None,
            after=None,
            reason="r1",
            idempotency_key=None,
            source=AdminAuditSource.BOT,
            tg_chat_id=1,
            ip=None,
            occurred_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
        e2 = AdminAuditEntry(
            admin_id=1,
            action=AdminAuditAction.ADMIN_CONFIRM_VERIFIED,
            target_kind="player",
            target_id="1",
            before=None,
            after={"ok": True},
            reason="r2",
            idempotency_key="k1",
            source=AdminAuditSource.WEB,
            tg_chat_id=None,
            ip="203.0.113.7",
            occurred_at=datetime(2026, 5, 7, 12, 1, tzinfo=UTC),
        )
        await logger.record(e1)
        await logger.record(e2)
        assert logger.entries == [e1, e2]
