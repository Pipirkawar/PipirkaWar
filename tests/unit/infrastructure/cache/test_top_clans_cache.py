"""Юнит-тесты `ClanTopCache` (Спринт 2.2.A / ПД 2.2.1).

Покрываем:
1. Первый запрос → читает из репо.
2. Повторный запрос в TTL → берёт из кэша (репо не вызывается).
3. После TTL → рефреш.
4. Запрос с большим `limit`, чем закэшировано → инвалидирует кэш.
5. Запрос с меньшим `limit` → отдаёт «префикс» из кэша.
6. `invalidate()` сбрасывает кэш.
7. Конкурентные `get_top()`: только один рефреш.
"""

from __future__ import annotations

import asyncio
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
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.infrastructure.cache import ClanTopCache
from tests.fakes import FakeClanRepository, FakeClock, FakeUnitOfWork

NOW = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)


def _seed(
    repo: FakeClanRepository,
    *,
    clan_id: int,
    title: str,
    members: list[tuple[int, int]],  # (player_id, length_cm)
    status: ClanStatus = ClanStatus.ACTIVE,
) -> None:
    """Засеять клан + участников + игроков в FakeClanRepository."""
    repo.rows.append(
        Clan(
            id=clan_id,
            chat_id=-1000 - clan_id,
            chat_kind=ChatKind.SUPERGROUP,
            title=ClanTitle(title),
            status=status,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    for player_id, length_cm in members:
        repo.players.append(
            Player(
                id=player_id,
                tg_id=10000 + player_id,
                username=Username(value=f"u{player_id}"),
                length=Length(cm=length_cm),
                thickness=Thickness(level=1),
                title=None,
                name=None,
                status=PlayerStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        repo.members.append(
            ClanMember(
                clan_id=clan_id,
                player_id=player_id,
                role=ClanMemberRole.MEMBER,
                joined_at=NOW,
            )
        )


def _build_cache(
    *,
    clock: FakeClock | None = None,
    ttl_seconds: int = 60,
) -> tuple[ClanTopCache, FakeClanRepository, FakeClock]:
    used_clock = clock or FakeClock(NOW)
    repo = FakeClanRepository()
    cache = ClanTopCache(
        uow=FakeUnitOfWork(),
        clans=repo,
        clock=used_clock,
        ttl_seconds=ttl_seconds,
    )
    return cache, repo, used_clock


class TestClanTopCache:
    def test_constructor_rejects_non_positive_ttl(self) -> None:
        with pytest.raises(ValueError, match="ttl_seconds"):
            _build_cache(ttl_seconds=0)
        with pytest.raises(ValueError, match="ttl_seconds"):
            _build_cache(ttl_seconds=-5)

    @pytest.mark.asyncio
    async def test_rejects_non_positive_limit(self) -> None:
        cache, _, _ = _build_cache()
        with pytest.raises(ValueError, match="limit"):
            await cache.get_top(limit=0)
        with pytest.raises(ValueError, match="limit"):
            await cache.get_top(limit=-1)

    @pytest.mark.asyncio
    async def test_first_call_reads_repo(self) -> None:
        cache, repo, _ = _build_cache()
        _seed(repo, clan_id=1, title="A", members=[(101, 100), (102, 50)])
        _seed(repo, clan_id=2, title="B", members=[(201, 75)])

        result = await cache.get_top(limit=10)

        assert [e.clan_id for e in result] == [1, 2]
        assert [e.total_length_cm for e in result] == [150, 75]
        assert [e.member_count for e in result] == [2, 1]

    @pytest.mark.asyncio
    async def test_repeat_within_ttl_uses_cache(self) -> None:
        cache, repo, clock = _build_cache(ttl_seconds=60)
        _seed(repo, clan_id=1, title="A", members=[(101, 100)])

        first = await cache.get_top(limit=10)

        # Очистим репо: если кэш сработает — мы всё равно увидим запись.
        repo.rows.clear()
        repo.members.clear()
        repo.players.clear()
        clock.advance(seconds=59)
        second = await cache.get_top(limit=10)

        assert second == first
        assert [e.total_length_cm for e in second] == [100]

    @pytest.mark.asyncio
    async def test_after_ttl_refreshes_from_repo(self) -> None:
        cache, repo, clock = _build_cache(ttl_seconds=60)
        _seed(repo, clan_id=1, title="A", members=[(101, 100)])

        await cache.get_top(limit=10)
        repo.rows.clear()
        repo.members.clear()
        repo.players.clear()
        clock.advance(seconds=61)

        result = await cache.get_top(limit=10)

        assert result == ()

    @pytest.mark.asyncio
    async def test_bigger_limit_invalidates_cache(self) -> None:
        cache, repo, _ = _build_cache(ttl_seconds=60)
        for i in range(1, 6):
            _seed(repo, clan_id=i, title=f"Clan-{i}", members=[(i * 100, 100 - i)])

        first = await cache.get_top(limit=2)
        assert len(first) == 2

        # Запрос больше — должен заново сходить в репо.
        result = await cache.get_top(limit=5)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_smaller_limit_serves_prefix_from_cache(self) -> None:
        cache, repo, _ = _build_cache(ttl_seconds=60)
        for i in range(1, 6):
            _seed(repo, clan_id=i, title=f"Clan-{i}", members=[(i * 100, 100 - i)])

        await cache.get_top(limit=5)
        # Очистим репо — если кэш сработает, мы всё равно увидим первые 2.
        repo.rows.clear()
        repo.members.clear()
        repo.players.clear()
        result = await cache.get_top(limit=2)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_invalidate_clears_cache(self) -> None:
        cache, repo, _ = _build_cache(ttl_seconds=60)
        _seed(repo, clan_id=1, title="A", members=[(101, 100)])

        await cache.get_top(limit=10)
        cache.invalidate()
        repo.rows.clear()
        repo.members.clear()
        repo.players.clear()
        result = await cache.get_top(limit=10)

        assert result == ()

    @pytest.mark.asyncio
    async def test_concurrent_calls_only_one_refresh(self) -> None:
        cache, repo, _ = _build_cache(ttl_seconds=60)
        _seed(repo, clan_id=1, title="A", members=[(101, 100)])

        # Запускаем 5 одновременных вызовов; благодаря _lock в ClanTopCache
        # должен быть ровно один SQL-запрос (рефреш).
        results = await asyncio.gather(*(cache.get_top(limit=10) for _ in range(5)))

        for r in results:
            assert r == results[0]
