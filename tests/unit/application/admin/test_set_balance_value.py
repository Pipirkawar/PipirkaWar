"""Unit-тесты `SetBalanceValue` (Спринт 2.5-C.4)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import pytest

from pipirik_wars.application.admin import (
    SetBalanceValue,
    SetBalanceValueInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import AdminAuditAction, AdminAuditSource, AdminRole
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.balance.errors import BalanceKeyError
from pipirik_wars.domain.balance.ports import IBalanceWriter
from pipirik_wars.shared.errors import ConfigError
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.balance import FakeBalanceConfig
from tests.fakes.clock import FakeClock
from tests.fakes.idempotency import FakeIdempotencyKey
from tests.fakes.uow import FakeUnitOfWork
from tests.unit.domain.balance.factories import valid_balance_payload

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


@dataclass
class _FakeWriterCall:
    key: str
    raw_value: Any


@dataclass
class _FakeWriter(IBalanceWriter):
    """Minimal fake — записывает значение в shared `FakeBalanceConfig`."""

    balance: FakeBalanceConfig
    calls: list[_FakeWriterCall] = field(default_factory=list)
    next_error: Exception | None = None

    def write_value(self, *, key: str, raw_value: Any) -> BalanceConfig:
        self.calls.append(_FakeWriterCall(key=key, raw_value=raw_value))
        if self.next_error is not None:
            raise self.next_error
        # Имитируем запись + reload через подмену snapshot-а.
        # `key` парсим только для top-level ключей в тесте — этого достаточно.
        payload = valid_balance_payload()
        payload[key] = raw_value
        new_snapshot = BalanceConfig.model_validate(payload)
        self.balance.set(new_snapshot)
        return new_snapshot


def _balance(version: int = 1) -> BalanceConfig:
    payload = valid_balance_payload()
    payload["version"] = version
    return BalanceConfig.model_validate(payload)


def _build() -> tuple[
    SetBalanceValue,
    FakeAdminRepository,
    FakeBalanceConfig,
    _FakeWriter,
    FakeIdempotencyKey,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    balance = FakeBalanceConfig(_balance())
    writer = _FakeWriter(balance=balance)
    idempotency = FakeIdempotencyKey()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        SetBalanceValue(
            uow=uow,
            admins=admins,
            balance=balance,
            writer=writer,
            idempotency=idempotency,
            audit=audit,
            clock=FakeClock(_NOW),
        ),
        admins,
        balance,
        writer,
        idempotency,
        audit,
        uow,
    )


@pytest.mark.asyncio
class TestSetBalanceValue:
    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _, _, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        admins.rows[0] = replace(admins.rows[0], is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                SetBalanceValueInput(
                    actor_tg_id=42,
                    key="version",
                    raw_value=2,
                    reason="r",
                    idempotency_key="k",
                ),
            )

    async def test_unknown_actor_raises(self) -> None:
        uc, _, _, _, _, _, _ = _build()
        with pytest.raises(AuthorizationError):
            await uc.execute(
                SetBalanceValueInput(
                    actor_tg_id=42,
                    key="version",
                    raw_value=2,
                    reason="r",
                    idempotency_key="k",
                ),
            )

    async def test_empty_reason_rejected(self) -> None:
        uc, admins, _, _, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)

        with pytest.raises(ValueError, match="reason must be a non-empty string"):
            await uc.execute(
                SetBalanceValueInput(
                    actor_tg_id=42,
                    key="version",
                    raw_value=2,
                    reason="   ",
                    idempotency_key="k",
                ),
            )

    async def test_unknown_key_raises_balance_key_error(self) -> None:
        uc, admins, _, writer, _, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)

        with pytest.raises(BalanceKeyError):
            await uc.execute(
                SetBalanceValueInput(
                    actor_tg_id=42,
                    key="unknown",
                    raw_value=42,
                    reason="r",
                    idempotency_key="k",
                ),
            )
        # Ни писатель, ни аудит не должны быть вызваны.
        assert writer.calls == []
        assert audit.entries == []

    async def test_happy_path_writes_audit_then_file(self) -> None:
        uc, admins, _, writer, idempotency, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)

        out = await uc.execute(
            SetBalanceValueInput(
                actor_tg_id=42,
                key="version",
                raw_value=2,
                reason="bump version",
                idempotency_key="admin_balance_set:42|version|202605081200",
                tg_chat_id=12345,
            ),
        )

        assert out.previous_raw_value == 1
        assert out.new_raw_value == 2
        assert out.new_balance_version == 2
        assert out.was_already_at_value is False
        assert out.was_idempotent_replay is False

        # Audit + writer вызваны (audit ДО writer-а).
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_BALANCE_SET
        assert entry.target_kind == "balance_key"
        assert entry.target_id == "version"
        assert entry.before == {"value": 1}
        assert entry.after == {"value": 2}
        assert entry.reason == "bump version"
        assert entry.source is AdminAuditSource.BOT
        assert entry.tg_chat_id == 12345

        assert len(writer.calls) == 1
        assert writer.calls[0].key == "version"
        assert writer.calls[0].raw_value == 2

        assert await idempotency.is_seen("admin_balance_set:42|version|202605081200")

    async def test_writer_failure_does_not_rollback_audit(self) -> None:
        # Audit пишется ДО write_value — это spec. Если writer упал,
        # audit-запись «попытка» остаётся в БД, что и нужно.
        uc, admins, _, writer, _, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        writer.next_error = ConfigError("disk full")

        with pytest.raises(ConfigError):
            await uc.execute(
                SetBalanceValueInput(
                    actor_tg_id=42,
                    key="version",
                    raw_value=2,
                    reason="r",
                    idempotency_key="admin_balance_set:42|version|202605081200",
                ),
            )
        assert len(audit.entries) == 1

    async def test_already_at_value_no_op(self) -> None:
        uc, admins, _, writer, idempotency, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)

        out = await uc.execute(
            SetBalanceValueInput(
                actor_tg_id=42,
                key="version",
                raw_value=1,  # уже 1
                reason="r",
                idempotency_key="admin_balance_set:42|version|202605081200",
            ),
        )

        assert out.was_already_at_value is True
        assert out.was_idempotent_replay is False
        assert out.previous_raw_value == 1
        assert out.new_raw_value == 1
        # Без вызова writer-а и без audit-записи.
        assert writer.calls == []
        assert audit.entries == []
        # Но idempotency-ключ зафиксирован.
        assert await idempotency.is_seen("admin_balance_set:42|version|202605081200")

    async def test_idempotent_replay(self) -> None:
        uc, admins, _, writer, idempotency, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        await idempotency.mark(
            "admin_balance_set:42|version|202605081200",
            namespace="admin_balance_set",
        )

        out = await uc.execute(
            SetBalanceValueInput(
                actor_tg_id=42,
                key="version",
                raw_value=2,
                reason="r",
                idempotency_key="admin_balance_set:42|version|202605081200",
            ),
        )

        assert out.was_idempotent_replay is True
        assert out.previous_raw_value == 1
        assert out.new_raw_value == 1  # writer не звали → версия не сменилась
        # Без вызова writer-а и без audit-записи.
        assert writer.calls == []
        assert audit.entries == []
