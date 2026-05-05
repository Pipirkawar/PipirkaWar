"""In-memory TTL-кэш для `ITopPlayersQuery` (Спринт 1.4.C / ПД 1.4.6).

ПД 1.4.6: «Кэш на 60 секунд». Реализация — лёгкий in-process
кэш на одном процессе бота. На рестарте — очищается. Этого
достаточно: `/top` — read-only публичный запрос, при росте
нагрузки замена на Redis-кэш потребует только смены адаптера.

Стампид-защита: одновременные `get_top(limit=N)` от разных
handler-ов разруливаются `asyncio.Lock` — рефрешит **только
один** воркер, остальные ждут результат.

Кэш строится на «снимке» из `IPlayerRepository.list_top_by_length`
+ посчитанном `DisplayName` через `IBalanceConfig`. Если перечитать
`balance.yaml` (`/balance_reload`) — следующий рефреш кэша вернёт
уже новые названия (старый снимок продолжает жить до истечения TTL,
это явно допустимо: `/top` не должен реагировать мгновенно на
смену таблицы названий).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from pipirik_wars.application.top.entries import TopPlayerEntry
from pipirik_wars.application.top.query import ITopPlayersQuery
from pipirik_wars.domain.balance import IBalanceConfig
from pipirik_wars.domain.player import DisplayName, IPlayerRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


class TopPlayersCache(ITopPlayersQuery):
    """In-memory TTL=60s кэш над `IPlayerRepository.list_top_by_length`.

    Хранит один срез `tuple[TopPlayerEntry, ...]` с фиксированным
    `cached_limit`. Если запросили больше элементов, чем закэшировано,
    — кэш считается недействительным и рефрешится. Если запросили
    меньше — отдаём первые `limit` элементов из кэша.
    """

    __slots__ = (
        "_balance",
        "_cache",
        "_cached_at",
        "_cached_limit",
        "_clock",
        "_lock",
        "_players",
        "_ttl_seconds",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        balance: IBalanceConfig,
        clock: IClock,
        ttl_seconds: int = 60,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")
        self._uow = uow
        self._players = players
        self._balance = balance
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._cache: tuple[TopPlayerEntry, ...] | None = None
        self._cached_at: datetime | None = None
        self._cached_limit: int | None = None

    async def get_top(self, *, limit: int) -> tuple[TopPlayerEntry, ...]:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        # Двойная проверка под локом, чтобы не было двух одновременных
        # рефрешей одного и того же снимка (cache stampede).
        async with self._lock:
            if self._is_fresh_for(limit, now=self._clock.now()):
                # mypy не выводит из `_is_fresh_for(...)` not-None для self._cache
                assert self._cache is not None
                return self._cache[:limit]
            return await self._refresh_locked(limit=limit)

    def _is_fresh_for(self, limit: int, *, now: datetime) -> bool:
        if self._cache is None or self._cached_at is None or self._cached_limit is None:
            return False
        if self._cached_limit < limit:
            return False
        return (now - self._cached_at).total_seconds() < self._ttl_seconds

    async def _refresh_locked(self, *, limit: int) -> tuple[TopPlayerEntry, ...]:
        """Перечитать снимок. Должен вызываться под `_lock`."""
        async with self._uow:
            players = await self._players.list_top_by_length(limit=limit)
        snapshot = self._balance.get()
        entries: tuple[TopPlayerEntry, ...] = tuple(
            TopPlayerEntry(
                title=p.title,
                display_name=DisplayName(
                    value=snapshot.display_name_for(p.length.cm),
                ),
                name=p.name,
                length_cm=p.length.cm,
            )
            for p in players
        )
        self._cache = entries
        self._cached_at = self._clock.now()
        self._cached_limit = limit
        return entries

    def invalidate(self) -> None:
        """Сбросить кэш. Полезно в админ-командах после массовых правок."""
        self._cache = None
        self._cached_at = None
        self._cached_limit = None
