"""Unit-тесты `JoinClan` (Спринт 1.1.5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.clan import JoinClan, RegisterClan
from pipirik_wars.application.dto.inputs import (
    JoinClanInput,
    RegisterClanInput,
    RegisterPlayerInput,
)
from pipirik_wars.application.player import RegisterPlayer
from pipirik_wars.domain.clan import ClanMembershipExistsError
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.shared.errors import IntegrityError
from tests.fakes import (
    FakeAuditLogger,
    FakeClanMembershipRepository,
    FakeClanRepository,
    FakeClock,
    FakePlayerRepository,
    FakeUnitOfWork,
)


def _build() -> tuple[
    JoinClan,
    RegisterClan,
    RegisterPlayer,
    FakeClanRepository,
    FakeClanMembershipRepository,
    FakePlayerRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    clans = FakeClanRepository()
    members = FakeClanMembershipRepository()
    players = FakePlayerRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, tzinfo=UTC))
    join = JoinClan(
        uow=uow,
        clans=clans,
        clan_members=members,
        players=players,
        audit=audit,
        clock=clock,
    )
    register_clan = RegisterClan(uow=uow, clans=clans, audit=audit, clock=clock)
    register_player = RegisterPlayer(
        uow=uow,
        players=players,
        audit=audit,
        clock=clock,
    )
    return (
        join,
        register_clan,
        register_player,
        clans,
        members,
        players,
        audit,
        uow,
        clock,
    )


class TestJoinClan:
    @pytest.mark.asyncio
    async def test_creates_membership_when_player_registered(self) -> None:
        (
            join,
            register_clan,
            register_player,
            _,
            members,
            _,
            audit,
            uow,
            _,
        ) = _build()
        await register_clan.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="Clan",
                added_by_tg_id=1,
            )
        )
        await register_player.execute(RegisterPlayerInput(tg_id=42))
        # Сбрасываем audit, чтобы тест проверял только JoinClan-запись.
        audit.entries.clear()

        result = await join.execute(JoinClanInput(chat_id=-100, tg_id=42))

        assert result.outcome == "joined"
        assert result.clan is not None
        assert result.member is not None
        assert result.member.player_id == 1  # serial id игрока
        assert result.member.clan_id == 1
        assert len(members.rows) == 1
        assert len(audit.entries) == 1
        assert audit.entries[0].action is AuditAction.CLAN_MEMBER_JOIN
        assert audit.entries[0].after is not None
        assert audit.entries[0].after["tg_id"] == 42
        # 1 регистрация клана + 1 регистрация игрока + 1 джойн = 3 коммита.
        assert uow.commits == 3

    @pytest.mark.asyncio
    async def test_returns_not_registered_when_player_missing(self) -> None:
        (
            join,
            register_clan,
            _,
            _,
            members,
            _,
            audit,
            _,
            _,
        ) = _build()
        await register_clan.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="Clan",
                added_by_tg_id=1,
            )
        )
        audit.entries.clear()

        result = await join.execute(JoinClanInput(chat_id=-100, tg_id=42))

        assert result.outcome == "not_registered"
        assert result.member is None
        assert result.clan is not None
        assert len(members.rows) == 0
        assert len(audit.entries) == 0

    @pytest.mark.asyncio
    async def test_already_member_is_idempotent(self) -> None:
        (
            join,
            register_clan,
            register_player,
            _,
            members,
            _,
            audit,
            uow,
            _,
        ) = _build()
        await register_clan.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="Clan",
                added_by_tg_id=1,
            )
        )
        await register_player.execute(RegisterPlayerInput(tg_id=42))
        await join.execute(JoinClanInput(chat_id=-100, tg_id=42))
        audit.entries.clear()
        commits_before = uow.commits

        result = await join.execute(JoinClanInput(chat_id=-100, tg_id=42))

        assert result.outcome == "already_member"
        assert result.member is not None
        assert len(members.rows) == 1
        assert len(audit.entries) == 0  # без новых аудит-записей
        assert uow.commits == commits_before + 1  # коммит-no-op всё равно

    @pytest.mark.asyncio
    async def test_player_already_in_other_clan_raises(self) -> None:
        """ГДД §4: один игрок — один клан одновременно. БД-инвариант."""
        (
            join,
            register_clan,
            register_player,
            _,
            _,
            _,
            _,
            _,
            _,
        ) = _build()
        await register_clan.execute(
            RegisterClanInput(
                chat_id=-100,
                chat_kind="group",
                title="A",
                added_by_tg_id=1,
            )
        )
        await register_clan.execute(
            RegisterClanInput(
                chat_id=-200,
                chat_kind="group",
                title="B",
                added_by_tg_id=1,
            )
        )
        await register_player.execute(RegisterPlayerInput(tg_id=42))
        await join.execute(JoinClanInput(chat_id=-100, tg_id=42))

        with pytest.raises(ClanMembershipExistsError):
            await join.execute(JoinClanInput(chat_id=-200, tg_id=42))

    @pytest.mark.asyncio
    async def test_unknown_chat_id_raises_integrity(self) -> None:
        join, *_ = _build()
        with pytest.raises(IntegrityError):
            await join.execute(JoinClanInput(chat_id=-999, tg_id=42))
