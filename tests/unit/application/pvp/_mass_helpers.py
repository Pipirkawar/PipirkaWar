"""Общие фикстуры для unit-тестов use-cases mass-PvP (Спринт 2.2.E)."""

from __future__ import annotations

from datetime import UTC, datetime

from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanMember,
    ClanMemberRole,
    ClanTitle,
)
from tests.fakes import FakeClanMembershipRepository, FakeClanRepository, FakePlayerRepository
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player

__all__ = [
    "MASS_NOW",
    "seed_clan",
    "seed_clan_member",
    "seed_eligible_clan_member",
]

MASS_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


async def seed_clan(
    clans: FakeClanRepository,
    *,
    chat_id: int,
    title: str = "Clan",
) -> Clan:
    """Создать активный клан с указанным `chat_id` и `title`."""

    fresh = Clan.new(
        chat_id=chat_id,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value=title),
        now=MASS_NOW,
    )
    return await clans.add(fresh)


async def seed_clan_member(
    clan_members: FakeClanMembershipRepository,
    *,
    clan_id: int,
    player_id: int,
    role: ClanMemberRole = ClanMemberRole.MEMBER,
) -> ClanMember:
    """Зарегистрировать членство игрока в клане."""

    member = ClanMember.new(
        clan_id=clan_id,
        player_id=player_id,
        role=role,
        now=MASS_NOW,
    )
    return await clan_members.add(member)


async def seed_eligible_clan_member(
    *,
    players: FakePlayerRepository,
    clan_members: FakeClanMembershipRepository,
    clan_id: int,
    tg_id: int,
    username: str = "alice",
    length_cm: int = 50,
    thickness_level: int = 2,
    role: ClanMemberRole = ClanMemberRole.MEMBER,
) -> int:
    """Создать PvP-eligible игрока + зарегистрировать его в клане. Возвращает `player.id`."""

    player = await seed_pvp_eligible_player(
        players,
        tg_id=tg_id,
        username=username,
        length_cm=length_cm,
        thickness_level=thickness_level,
    )
    assert player.id is not None
    await seed_clan_member(
        clan_members,
        clan_id=clan_id,
        player_id=player.id,
        role=role,
    )
    return player.id
