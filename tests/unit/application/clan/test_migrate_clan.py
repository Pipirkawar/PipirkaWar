"""Unit-тесты `MigrateClanChatId` (Спринт 1.1.4 — обработка
group → supergroup миграции)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.clan import (
    ClanNotFoundError,
    MigrateClanChatId,
    RegisterClan,
)
from pipirik_wars.application.dto.inputs import (
    MigrateClanChatIdInput,
    RegisterClanInput,
)
from pipirik_wars.domain.clan import ChatKind
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeClanRepository,
    FakeClock,
    FakeUnitOfWork,
)


def _build() -> tuple[
    MigrateClanChatId,
    RegisterClan,
    FakeClanRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    clans = FakeClanRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, tzinfo=UTC))
    register = RegisterClan(uow=uow, clans=clans, audit=audit, clock=clock)
    migrate = MigrateClanChatId(uow=uow, clans=clans, audit=audit, clock=clock)
    return migrate, register, clans, audit, uow, clock


class TestMigrateClanChatId:
    @pytest.mark.asyncio
    async def test_migrates_group_to_supergroup(self) -> None:
        migrate, register, clans, audit, uow, clock = _build()

        await register.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="My Group",
                added_by_tg_id=1,
            )
        )
        clock.advance(hours=1)
        result = await migrate.execute(
            MigrateClanChatIdInput(
                old_chat_id=-100,
                new_chat_id=-1001000,
                new_chat_kind="supergroup",
            )
        )

        assert result.outcome == "migrated"
        assert result.clan.chat_id == -1001000
        assert result.clan.chat_kind is ChatKind.SUPERGROUP
        # Внутренний id должен сохраниться.
        assert result.clan.id == 1
        assert len(clans.rows) == 1
        assert uow.commits == 2
        assert any(e.action is AuditAction.CLAN_MIGRATE for e in audit.entries)

    @pytest.mark.asyncio
    async def test_already_migrated_when_new_chat_present(self) -> None:
        migrate, register, _, audit, uow, _ = _build()

        # Сразу регистрируем «новый» chat_id.
        await register.execute(
            RegisterClanInput(
                chat_id=-1001000,
                chat_kind="supergroup",
                title="Already Super",
                added_by_tg_id=1,
            )
        )
        # Старого нет, но новый — есть → outcome = already_migrated, без аудита.
        result = await migrate.execute(
            MigrateClanChatIdInput(
                old_chat_id=-100,
                new_chat_id=-1001000,
                new_chat_kind="supergroup",
            )
        )
        assert result.outcome == "already_migrated"
        assert result.clan.chat_id == -1001000
        assert not any(e.action is AuditAction.CLAN_MIGRATE for e in audit.entries)
        assert uow.commits == 2  # register + migrate (no-op)

    @pytest.mark.asyncio
    async def test_raises_when_neither_old_nor_new_exists(self) -> None:
        migrate, *_ = _build()

        with pytest.raises(ClanNotFoundError) as exc_info:
            await migrate.execute(
                MigrateClanChatIdInput(
                    old_chat_id=-999,
                    new_chat_id=-1009999,
                    new_chat_kind="supergroup",
                )
            )
        assert exc_info.value.old_chat_id == -999

    @pytest.mark.asyncio
    async def test_idempotent_no_op_for_same_chat_ids(self) -> None:
        migrate, register, _, audit, _, _ = _build()
        await register.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="G",
                added_by_tg_id=1,
            )
        )
        # «Миграция» в тот же chat_id с тем же kind — Clan.with_chat_id no-op.
        result = await migrate.execute(
            MigrateClanChatIdInput(
                old_chat_id=-100,
                new_chat_id=-100,
                new_chat_kind="group",
            )
        )
        assert result.outcome == "already_migrated"
        assert not any(e.action is AuditAction.CLAN_MIGRATE for e in audit.entries)
