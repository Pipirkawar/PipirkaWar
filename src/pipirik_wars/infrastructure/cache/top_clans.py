"""In-memory TTL-кэш для `IClanTopQuery` (Спринт 2.2.A / ПД 2.2.1).

Полный аналог `TopPlayersCache` (1.4.C): TTL=60s, in-process, на
рестарте бота — очищается. Под капотом дёргает
`IClanRepository.list_top_by_total_length`. Замена на Redis-кэш
потребует только смены адаптера: контракт `IClanTopQuery` остаётся.

Стампид-защита: одновременные `get_top(limit=N)` от разных
handler-ов разруливаются `asyncio.Lock` — рефрешит **только**
один воркер, остальные ждут результат.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from pipirik_wars.application.top import ClanTopEntry, IClanTopQuery
from pipirik_wars.domain.clan import IClanRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


class ClanTopCache(IClanTopQuery):
    """In-memory TTL=60s кэш над `IClanRepository.list_top_by_total_length`.

    Хранит один срез `tuple[ClanTopEntry, ...]` с фиксированным
    `cached_limit`. Если запросили больше, чем закэшировано — кэш
    считается недействительным и рефрешится. Если меньше — отдаём
    первые `limit` элементов из кэша.
    """

    __slots__ = (
        "_cache",
        "_cached_at",
        "_cached_limit",
        "_clans",
        "_clock",
        "_lock",
        "_ttl_seconds",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        clans: IClanRepository,
        clock: IClock,
        ttl_seconds: int = 60,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")
        self._uow = uow
        self._clans = clans
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._cache: tuple[ClanTopEntry, ...] | None = None
        self._cached_at: datetime | None = None
        self._cached_limit: int | None = None

    async def get_top(self, *, limit: int) -> tuple[ClanTopEntry, ...]:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        # Двойная проверка под локом, чтобы не было двух одновременных
        # рефрешей одного и того же снимка (cache stampede).
        async with self._lock:
            if self._is_fresh_for(limit, now=self._clock.now()):
                assert self._cache is not None
                return self._cache[:limit]
            return await self._refresh_locked(limit=limit)

    def _is_fresh_for(self, limit: int, *, now: datetime) -> bool:
        if self._cache is None or self._cached_at is None or self._cached_limit is None:
            return False
        if self._cached_limit < limit:
            return False
        return (now - self._cached_at).total_seconds() < self._ttl_seconds

    async def _refresh_locked(self, *, limit: int) -> tuple[ClanTopEntry, ...]:
        """Перечитать снимок. Должен вызываться под `_lock`."""
        async with self._uow:
            entries = tuple(await self._clans.list_top_by_total_length(limit=limit))
        self._cache = entries
        self._cached_at = self._clock.now()
        self._cached_limit = limit
        return entries

    def invalidate(self) -> None:
        """Сбросить кэш. Полезно в админ-командах после массовых правок."""
        self._cache = None
        self._cached_at = None
        self._cached_limit = None
