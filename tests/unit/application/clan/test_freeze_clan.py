"""Unit-тесты `FreezeClan` (Спринт 1.1.6)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.clan import FreezeClan, RegisterClan
from pipirik_wars.application.dto.inputs import (
    FreezeClanInput,
    RegisterClanInput,
)
from pipirik_wars.domain.clan import ClanStatus
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeClanRepository,
    FakeClock,
    FakeUnitOfWork,
)


def _build() -> tuple[
    FreezeClan,
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
        FreezeClan(uow=uow, clans=clans, audit=audit, clock=clock),
        RegisterClan(uow=uow, clans=clans, audit=audit, clock=clock),
        clans,
        audit,
        uow,
        clock,
    )


class TestFreezeClan:
    @pytest.mark.asyncio
    async def test_freezes_active_clan(self) -> None:
        freeze, register, clans, audit, uow, _ = _build()
        await register.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="C",
                added_by_tg_id=1,
            )
        )
        audit.entries.clear()

        result = await freeze.execute(
            FreezeClanInput(chat_id=-100, reason="bot_kicked"),
        )

        assert result.outcome == "frozen"
        assert result.clan is not None
        assert result.clan.status is ClanStatus.FROZEN
        assert clans.rows[0].status is ClanStatus.FROZEN
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.CLAN_FREEZE
        assert entry.before == {"status": "active"}
        assert entry.after == {"status": "frozen"}
        assert entry.reason == "bot_kicked"
        assert uow.commits == 2  # register + freeze

    @pytest.mark.asyncio
    async def test_already_frozen_idempotent(self) -> None:
        freeze, register, _, audit, _, _ = _build()
        await register.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="C",
                added_by_tg_id=1,
            )
        )
        await freeze.execute(FreezeClanInput(chat_id=-100))
        audit.entries.clear()

        result = await freeze.execute(FreezeClanInput(chat_id=-100))

        assert result.outcome == "already_frozen"
        assert result.clan is not None
        assert result.clan.status is ClanStatus.FROZEN
        assert len(audit.entries) == 0  # повторный freeze без аудита

    @pytest.mark.asyncio
    async def test_not_found_returns_outcome(self) -> None:
        freeze, *_ = _build()

        result = await freeze.execute(FreezeClanInput(chat_id=-999))

        assert result.outcome == "not_found"
        assert result.clan is None

    @pytest.mark.asyncio
    async def test_unfreeze_via_register_clan_round_trip(self) -> None:
        """1.1.6 acceptance: повторное добавление → status='active'."""
        freeze, register, clans, _, _, _ = _build()
        await register.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="C",
                added_by_tg_id=1,
            )
        )
        await freeze.execute(FreezeClanInput(chat_id=-100))
        assert clans.rows[0].status is ClanStatus.FROZEN

        result = await register.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="C",
                added_by_tg_id=1,
            )
        )

        assert result.outcome == "unfrozen"
        assert result.clan.status is ClanStatus.ACTIVE
