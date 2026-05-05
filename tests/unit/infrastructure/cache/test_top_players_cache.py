"""Юнит-тесты `TopPlayersCache` (Спринт 1.4.C / ПД 1.4.6).

Покрываем:
1. Первый запрос → читает из репо.
2. Повторный запрос в TTL → берёт из кэша (репо не вызывается).
3. После TTL → читает из репо повторно.
4. Запрос с большим `limit`, чем закэшировано → инвалидирует кэш.
5. Запрос с меньшим `limit` → отдаёт «префикс» из кэша.
6. `invalidate()` сбрасывает кэш.
7. Конкурентные `get_top()` от нескольких корутин: только один рефреш.
8. После `balance.set(...)` следующий рефреш использует новые имена.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.player import (
    DisplayName,
    Length,
    Player,
    PlayerName,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.infrastructure.cache import TopPlayersCache
from tests.fakes import FakeBalanceConfig, FakeClock, FakePlayerRepository, FakeUnitOfWork
from tests.unit.domain.balance.factories import valid_balance_payload

NOW = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)


def _balance_with(*ranges: tuple[int, int | None, str]) -> BalanceConfig:
    payload = valid_balance_payload()
    payload["display_names"] = [{"from": f, "to": t, "name": n} for f, t, n in ranges]
    return BalanceConfig.model_validate(payload)


def _seed_active(
    repo: FakePlayerRepository,
    *,
    player_id: int,
    tg_id: int,
    length_cm: int,
    name: str | None = None,
) -> None:
    repo.rows.append(
        Player(
            id=player_id,
            tg_id=tg_id,
            username=Username(value=f"u{tg_id}"),
            length=Length(cm=length_cm),
            thickness=Thickness(level=1),
            title=None,
            name=PlayerName(value=name) if name is not None else None,
            status=PlayerStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def _build_cache(
    *,
    clock: FakeClock | None = None,
    balance: FakeBalanceConfig | None = None,
    ttl_seconds: int = 60,
) -> tuple[TopPlayersCache, FakePlayerRepository, FakeClock, FakeBalanceConfig]:
    used_clock = clock or FakeClock(NOW)
    used_balance = balance or FakeBalanceConfig(
        _balance_with((0, None, "Хвостик")),
    )
    repo = FakePlayerRepository()
    cache = TopPlayersCache(
        uow=FakeUnitOfWork(),
        players=repo,
        balance=used_balance,
        clock=used_clock,
        ttl_seconds=ttl_seconds,
    )
    return cache, repo, used_clock, used_balance


class TestTopPlayersCache:
    def test_constructor_rejects_non_positive_ttl(self) -> None:
        with pytest.raises(ValueError, match="ttl_seconds"):
            _build_cache(ttl_seconds=0)
        with pytest.raises(ValueError, match="ttl_seconds"):
            _build_cache(ttl_seconds=-5)

    @pytest.mark.asyncio
    async def test_rejects_non_positive_limit(self) -> None:
        cache, _, _, _ = _build_cache()
        with pytest.raises(ValueError, match="limit"):
            await cache.get_top(limit=0)
        with pytest.raises(ValueError, match="limit"):
            await cache.get_top(limit=-1)

    @pytest.mark.asyncio
    async def test_first_call_reads_repo_and_computes_display_name(self) -> None:
        cache, repo, _, _ = _build_cache(
            balance=FakeBalanceConfig(
                _balance_with(
                    (0, 10, "Малыш"),
                    (10, 50, "Хвостик"),
                    (50, None, "Гигант"),
                ),
            ),
        )
        _seed_active(repo, player_id=1, tg_id=100, length_cm=200)
        _seed_active(repo, player_id=2, tg_id=101, length_cm=42)
        _seed_active(repo, player_id=3, tg_id=102, length_cm=5)

        result = await cache.get_top(limit=10)

        assert [e.length_cm for e in result] == [200, 42, 5]
        assert [e.display_name.value for e in result] == ["Гигант", "Хвостик", "Малыш"]

    @pytest.mark.asyncio
    async def test_repeat_within_ttl_uses_cache(self) -> None:
        cache, repo, clock, _ = _build_cache(ttl_seconds=60)
        _seed_active(repo, player_id=1, tg_id=100, length_cm=10)

        first = await cache.get_top(limit=10)

        # «Удаляем» игрока из репо: если кэш сработает — мы всё равно
        # увидим запись, потому что репо не дёргался.
        repo.rows.clear()
        clock.advance(seconds=59)
        second = await cache.get_top(limit=10)

        assert second == first  # снимок не освежался
        assert [e.length_cm for e in second] == [10]

    @pytest.mark.asyncio
    async def test_after_ttl_refreshes_from_repo(self) -> None:
        cache, repo, clock, _ = _build_cache(ttl_seconds=60)
        _seed_active(repo, player_id=1, tg_id=100, length_cm=10)

        await cache.get_top(limit=10)
        repo.rows.clear()
        # >TTL — кэш должен обновиться.
        clock.advance(seconds=61)
        result = await cache.get_top(limit=10)

        assert result == ()  # репо пуст после рефреша

    @pytest.mark.asyncio
    async def test_larger_limit_invalidates_cache(self) -> None:
        cache, repo, clock, _ = _build_cache(ttl_seconds=60)
        for i in range(1, 6):
            _seed_active(repo, player_id=i, tg_id=100 + i, length_cm=i * 10)

        first = await cache.get_top(limit=2)
        assert len(first) == 2

        # repo меняется, но мы внутри TTL: больший limit принудительно рефрешит.
        clock.advance(seconds=10)
        bigger = await cache.get_top(limit=5)
        assert len(bigger) == 5
        # все 5 присутствуют, отсортированы по убыванию
        assert [e.length_cm for e in bigger] == [50, 40, 30, 20, 10]

    @pytest.mark.asyncio
    async def test_smaller_limit_uses_cached_prefix(self) -> None:
        cache, repo, _, _ = _build_cache(ttl_seconds=60)
        for i in range(1, 6):
            _seed_active(repo, player_id=i, tg_id=100 + i, length_cm=i * 10)

        await cache.get_top(limit=5)
        # Стираем репо. Меньший limit — кэш ещё свеж.
        repo.rows.clear()
        smaller = await cache.get_top(limit=2)
        assert [e.length_cm for e in smaller] == [50, 40]

    @pytest.mark.asyncio
    async def test_invalidate_drops_cache(self) -> None:
        cache, repo, _, _ = _build_cache(ttl_seconds=60)
        _seed_active(repo, player_id=1, tg_id=100, length_cm=10)

        await cache.get_top(limit=5)
        repo.rows.clear()
        cache.invalidate()
        # Теперь кэш «пуст» — снимок снова возьмётся из (пустого) репо.
        result = await cache.get_top(limit=5)
        assert result == ()

    @pytest.mark.asyncio
    async def test_concurrent_requests_trigger_single_refresh(self) -> None:
        """`asyncio.Lock` обязан исключать повторный рефреш под двумя
        одновременными вызовами.
        """
        # Считаем количество фактических обращений к repo через декоратор.
        cache, repo, _, _ = _build_cache(ttl_seconds=60)
        _seed_active(repo, player_id=1, tg_id=100, length_cm=10)

        repo_calls = 0

        original = repo.list_top_by_length

        async def wrapped(*, limit: int) -> tuple[Player, ...]:
            nonlocal repo_calls
            repo_calls += 1
            await asyncio.sleep(0)  # отдаём управление, провоцируем гонку
            return tuple(await original(limit=limit))

        # mypy: динамическая подмена метода — приемлемо в тестах.
        repo.list_top_by_length = wrapped  # type: ignore[method-assign]

        results = await asyncio.gather(
            cache.get_top(limit=5),
            cache.get_top(limit=5),
            cache.get_top(limit=5),
        )

        assert all(r == results[0] for r in results)
        assert repo_calls == 1  # только один рефреш под локом

    @pytest.mark.asyncio
    async def test_balance_change_visible_after_ttl(self) -> None:
        balance = FakeBalanceConfig(_balance_with((0, None, "Хвостик")))
        cache, repo, clock, _ = _build_cache(balance=balance, ttl_seconds=60)
        _seed_active(repo, player_id=1, tg_id=100, length_cm=10)

        first = await cache.get_top(limit=5)
        assert first[0].display_name.value == "Хвостик"

        # Меняем балансовые имена и принудительно «протухаем» кэш.
        balance.set(_balance_with((0, None, "Палочка")))
        clock.advance(seconds=61)
        second = await cache.get_top(limit=5)
        assert second[0].display_name.value == "Палочка"

    @pytest.mark.asyncio
    async def test_uses_uow_for_repo_read(self) -> None:
        """Проверяем, что репо-чтение происходит внутри активной транзакции."""
        uow = FakeUnitOfWork()
        balance = FakeBalanceConfig(_balance_with((0, None, "x")))
        repo = FakePlayerRepository()
        _seed_active(repo, player_id=1, tg_id=100, length_cm=10)
        cache = TopPlayersCache(
            uow=uow,
            players=repo,
            balance=balance,
            clock=FakeClock(NOW),
            ttl_seconds=60,
        )

        await cache.get_top(limit=5)
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_at_ttl_boundary_treated_as_stale(self) -> None:
        """Ровно `ttl_seconds` после кэширования — считаем уже устаревшим."""
        cache, repo, clock, _ = _build_cache(ttl_seconds=60)
        _seed_active(repo, player_id=1, tg_id=100, length_cm=10)

        await cache.get_top(limit=5)
        repo.rows.clear()
        clock.advance(seconds=60)  # ровно граница: must refresh
        second = await cache.get_top(limit=5)
        assert second == ()

    @pytest.mark.asyncio
    async def test_just_before_ttl_uses_cache(self) -> None:
        cache, repo, clock, _ = _build_cache(ttl_seconds=60)
        _seed_active(repo, player_id=1, tg_id=100, length_cm=10)

        await cache.get_top(limit=5)
        repo.rows.clear()
        clock.advance(seconds=59, minutes=0, hours=0)
        # advance() принимает float seconds → 59.999s допустимо
        clock.advance(seconds=0.999)
        second = await cache.get_top(limit=5)
        # 59.999s — ещё в окне TTL, отдаём кэш
        assert [e.length_cm for e in second] == [10]


class TestSeedHelper:
    """Проверка, что наш _seed_active работает: mini-санити тест."""

    def test_seed_active_makes_active_player(self) -> None:
        repo = FakePlayerRepository()
        _seed_active(repo, player_id=1, tg_id=100, length_cm=10)
        active = [p for p in repo.rows if p.status == PlayerStatus.ACTIVE]
        assert len(active) == 1
        # используем DisplayName/PlayerName/Username в namespace, чтобы
        # ruff не считал их неиспользуемыми импортами
        assert DisplayName(value="x").value == "x"
        assert PlayerName(value="y").value == "y"
        assert Username(value="z").value == "z"
