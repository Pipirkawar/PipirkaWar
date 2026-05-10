"""Unit-тесты `FakeClanRepository.count_active_for_player` (Спринт 3.6-A)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanMember,
    ClanMemberRole,
    ClanStatus,
    ClanTitle,
)
from tests.fakes.clan_repo import FakeClanRepository

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _seed_clan(
    repo: FakeClanRepository,
    *,
    clan_id: int,
    chat_id: int,
    status: ClanStatus = ClanStatus.ACTIVE,
) -> Clan:
    clan = Clan(
        id=clan_id,
        chat_id=chat_id,
        chat_kind=ChatKind.GROUP,
        title=ClanTitle(value=f"Clan {clan_id}"),
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )
    repo.rows.append(clan)
    return clan


def _seed_membership(
    repo: FakeClanRepository,
    *,
    clan_id: int,
    player_id: int,
) -> None:
    repo.members.append(
        ClanMember(
            clan_id=clan_id,
            player_id=player_id,
            role=ClanMemberRole.MEMBER,
            joined_at=_NOW,
        )
    )


@pytest.mark.asyncio
class TestFakeClanRepositoryCountActiveForPlayer:
    async def test_no_clans_returns_zero(self) -> None:
        repo = FakeClanRepository()
        n = await repo.count_active_for_player(player_id=42, min_tribe_size=4)
        assert n == 0

    async def test_player_not_member_returns_zero(self) -> None:
        """Клан большой и активный, но игрок не в `clan_members`."""
        repo = FakeClanRepository()
        _seed_clan(repo, clan_id=1, chat_id=-100)
        for pid in (1, 2, 3, 4, 5):
            _seed_membership(repo, clan_id=1, player_id=pid)
        n = await repo.count_active_for_player(player_id=42, min_tribe_size=4)
        assert n == 0

    async def test_below_min_tribe_size_returns_zero(self) -> None:
        """Размер 3 при `min_tribe_size=4` — не считается."""
        repo = FakeClanRepository()
        _seed_clan(repo, clan_id=1, chat_id=-100)
        for pid in (1, 2, 42):
            _seed_membership(repo, clan_id=1, player_id=pid)
        n = await repo.count_active_for_player(player_id=42, min_tribe_size=4)
        assert n == 0

    async def test_at_min_tribe_size_returns_one(self) -> None:
        """Размер 4 при `min_tribe_size=4` — считается (`>=`-семантика)."""
        repo = FakeClanRepository()
        _seed_clan(repo, clan_id=1, chat_id=-100)
        for pid in (1, 2, 3, 42):
            _seed_membership(repo, clan_id=1, player_id=pid)
        n = await repo.count_active_for_player(player_id=42, min_tribe_size=4)
        assert n == 1

    async def test_above_min_tribe_size_returns_one(self) -> None:
        """Размер 7 при `min_tribe_size=4` — считается, и всё равно `1`."""
        repo = FakeClanRepository()
        _seed_clan(repo, clan_id=1, chat_id=-100)
        for pid in (1, 2, 3, 4, 5, 6, 42):
            _seed_membership(repo, clan_id=1, player_id=pid)
        n = await repo.count_active_for_player(player_id=42, min_tribe_size=4)
        assert n == 1

    async def test_frozen_clan_returns_zero(self) -> None:
        """Frozen-клан большой и игрок в нём — но статус выводит из агрегации."""
        repo = FakeClanRepository()
        _seed_clan(repo, clan_id=1, chat_id=-100, status=ClanStatus.FROZEN)
        for pid in (1, 2, 3, 4, 42):
            _seed_membership(repo, clan_id=1, player_id=pid)
        n = await repo.count_active_for_player(player_id=42, min_tribe_size=4)
        assert n == 0

    async def test_min_tribe_size_one_counts_solo_membership(self) -> None:
        """При `min_tribe_size=1` любое непустое племя с игроком — считается."""
        repo = FakeClanRepository()
        _seed_clan(repo, clan_id=1, chat_id=-100)
        _seed_membership(repo, clan_id=1, player_id=42)
        n = await repo.count_active_for_player(player_id=42, min_tribe_size=1)
        assert n == 1

    async def test_min_tribe_size_below_one_raises(self) -> None:
        repo = FakeClanRepository()
        with pytest.raises(ValueError, match="min_tribe_size must be >= 1"):
            await repo.count_active_for_player(player_id=42, min_tribe_size=0)

    async def test_multiple_clans_only_qualifying_count(self) -> None:
        """Заглядываем вперёд (Phase 4+, multi-membership): из 3 кланов только
        2 квалифицированы (`>= min_tribe_size`, `ACTIVE`, игрок есть).
        В Phase 3 модель `UNIQUE(player_id)` не позволит создать 3 членства;
        тест проверяет логику метода в общем виде.
        """
        repo = FakeClanRepository()
        _seed_clan(repo, clan_id=1, chat_id=-100)  # ACTIVE, 4 members → counts
        for pid in (1, 2, 3, 42):
            _seed_membership(repo, clan_id=1, player_id=pid)

        _seed_clan(repo, clan_id=2, chat_id=-200)  # ACTIVE, 4 members → counts
        for pid in (10, 11, 12, 42):
            _seed_membership(repo, clan_id=2, player_id=pid)

        _seed_clan(repo, clan_id=3, chat_id=-300, status=ClanStatus.FROZEN)
        for pid in (20, 21, 22, 42):  # FROZEN — выпадает
            _seed_membership(repo, clan_id=3, player_id=pid)

        _seed_clan(repo, clan_id=4, chat_id=-400)  # ACTIVE, 3 members → too small
        for pid in (30, 31, 42):
            _seed_membership(repo, clan_id=4, player_id=pid)

        _seed_clan(repo, clan_id=5, chat_id=-500)  # ACTIVE, 4 members, без игрока 42
        for pid in (40, 41, 51, 43):
            _seed_membership(repo, clan_id=5, player_id=pid)

        n = await repo.count_active_for_player(player_id=42, min_tribe_size=4)
        assert n == 2
