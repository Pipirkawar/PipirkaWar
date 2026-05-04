"""Unit-тесты `RegisterClan` (Спринт 1.1.4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.clan import RegisterClan
from pipirik_wars.application.dto.inputs import RegisterClanInput
from pipirik_wars.domain.clan import ChatKind, ClanStatus, ClanTitle
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeClanRepository,
    FakeClock,
    FakeUnitOfWork,
)


def _build() -> tuple[
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
    return (
        RegisterClan(uow=uow, clans=clans, audit=audit, clock=clock),
        clans,
        audit,
        uow,
        clock,
    )


class TestRegisterClan:
    @pytest.mark.asyncio
    async def test_creates_new_clan(self) -> None:
        use_case, clans, audit, uow, clock = _build()

        result = await use_case.execute(
            RegisterClanInput(
                chat_id=-1001234,
                chat_kind="supergroup",
                title="Pipirik Warriors",
                added_by_tg_id=42,
            )
        )

        assert result.outcome == "created"
        assert result.clan.id == 1
        assert result.clan.chat_id == -1001234
        assert result.clan.chat_kind is ChatKind.SUPERGROUP
        assert result.clan.title == ClanTitle(value="Pipirik Warriors")
        assert result.clan.status is ClanStatus.ACTIVE
        assert len(clans.rows) == 1
        assert uow.commits == 1

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.CLAN_REGISTER
        assert entry.actor_id == 42
        assert entry.target_id == "-1001234"
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["chat_kind"] == "supergroup"
        assert entry.idempotency_key == "register_clan:-1001234"
        assert entry.occurred_at == clock.now()

    @pytest.mark.asyncio
    async def test_unfreezes_existing_frozen_clan(self) -> None:
        use_case, clans, audit, uow, clock = _build()

        # Сначала регистрируем и замораживаем (через сам же RegisterClan +
        # ручную манипуляцию в репозитории).
        await use_case.execute(
            RegisterClanInput(
                chat_id=100,
                chat_kind="group",
                title="Old Group",
                added_by_tg_id=1,
            )
        )
        clans.rows[0] = clans.rows[0].freeze(now=clock.now())

        clock.advance(hours=1)
        result = await use_case.execute(
            RegisterClanInput(
                chat_id=100,
                chat_kind="group",
                title="Old Group",
                added_by_tg_id=2,
            )
        )

        assert result.outcome == "unfrozen"
        assert result.clan.status is ClanStatus.ACTIVE
        # 2 commits: first create + this unfreeze.
        assert uow.commits == 2
        # 2 audit entries: CLAN_REGISTER + CLAN_UNFREEZE.
        assert {e.action for e in audit.entries} == {
            AuditAction.CLAN_REGISTER,
            AuditAction.CLAN_UNFREEZE,
        }

    @pytest.mark.asyncio
    async def test_idempotent_for_already_active(self) -> None:
        use_case, clans, audit, uow, _ = _build()

        first = await use_case.execute(
            RegisterClanInput(
                chat_id=100,
                chat_kind="group",
                title="Title",
                added_by_tg_id=1,
            )
        )
        second = await use_case.execute(
            RegisterClanInput(
                chat_id=100,
                chat_kind="group",
                title="Title",
                added_by_tg_id=2,
            )
        )

        assert first.outcome == "created"
        assert second.outcome == "already_active"
        assert second.clan == first.clan  # без модификации
        assert len(clans.rows) == 1
        # Audit пишется только при реальном изменении.
        assert len(audit.entries) == 1
        assert uow.commits == 2
