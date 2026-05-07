"""Unit-тесты `GetBalanceValue` (Спринт 2.5-C.3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    BalanceKeyError,
    GetBalanceValue,
    GetBalanceValueInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import AdminAuditAction, AdminAuditSource, AdminRole
from pipirik_wars.domain.balance.config import BalanceConfig
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.balance import FakeBalanceConfig
from tests.fakes.clock import FakeClock
from tests.fakes.uow import FakeUnitOfWork
from tests.unit.domain.balance.factories import valid_balance_payload

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _balance() -> BalanceConfig:
    return BalanceConfig.model_validate(valid_balance_payload())


def _build() -> tuple[
    GetBalanceValue,
    FakeAdminRepository,
    FakeBalanceConfig,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    balance = FakeBalanceConfig(_balance())
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        GetBalanceValue(
            uow=uow,
            admins=admins,
            balance=balance,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        ),
        admins,
        balance,
        audit,
        uow,
    )


@pytest.mark.asyncio
class TestGetBalanceValue:
    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        admins.rows[0] = replace(admins.rows[0], is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(GetBalanceValueInput(actor_tg_id=42, key="version"))

    async def test_unknown_actor_raises(self) -> None:
        uc, _, _, _, _ = _build()
        with pytest.raises(AuthorizationError):
            await uc.execute(GetBalanceValueInput(actor_tg_id=42, key="version"))

    async def test_returns_scalar_value(self) -> None:
        uc, admins, _, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)

        out = await uc.execute(
            GetBalanceValueInput(actor_tg_id=42, key="version", tg_chat_id=12345),
        )
        assert out.key == "version"
        assert out.raw_value == 1
        assert out.balance_version == 1

        # Audit пишется.
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_BALANCE_GET
        assert entry.target_kind == "balance_key"
        assert entry.target_id == "version"
        assert entry.before is None
        assert entry.after is None
        assert entry.source is AdminAuditSource.BOT
        assert entry.tg_chat_id == 12345

    async def test_returns_dict_value(self) -> None:
        uc, admins, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)

        out = await uc.execute(
            GetBalanceValueInput(actor_tg_id=42, key="thickness.unlock_levels"),
        )
        assert out.raw_value == {"forest": 1, "pvp_chat": 2, "mountains": 3}

    async def test_unknown_key_raises_key_error(self) -> None:
        uc, admins, _, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)

        with pytest.raises(BalanceKeyError):
            await uc.execute(GetBalanceValueInput(actor_tg_id=42, key="unknown"))
        # Audit НЕ пишется при ошибке — мы ничего не «прочитали».
        assert audit.entries == []
