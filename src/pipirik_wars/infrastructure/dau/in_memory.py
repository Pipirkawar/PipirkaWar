"""In-memory реализации `IDauCounter` / `IDauLimit` (ГДД §18.3).

Простейшие, потокобезопасные через `asyncio.Lock`. Состояние теряется
на рестарте бота — это намеренно: для MVP DAU-счётчик в памяти
достаточно, а пик за неделю и долгая статистика будут строиться
из `audit_log` (исторические записи `PLAYER_REGISTER` и любые активности).

Когда понадобится горизонтальное масштабирование (несколько подов
бота) — заменим на Redis-backend без правки use-case-ов
(`IDauCounter` / `IDauLimit` — публичный контракт).
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta, timezone

from pipirik_wars.domain.dau import IDauCounter, IDauLimit
from pipirik_wars.domain.shared.ports import IClock

_MOSCOW_TZ = timezone(timedelta(hours=3), name="Europe/Moscow")


class InMemoryDauCounter(IDauCounter):
    """Счётчик активных за сегодня по `Europe/Moscow`.

    Сброс множества — при первом обращении после полуночи МСК
    (lazy-reset, не нужен внешний scheduler). Тред-сэйф через
    `asyncio.Lock` — параллельные `record_active(...)` из разных
    handler-ов корректно мёржатся в одно множество.
    """

    __slots__ = ("_actors", "_clock", "_current_date", "_lock")

    def __init__(self, *, clock: IClock) -> None:
        self._clock = clock
        self._lock = asyncio.Lock()
        self._current_date: date | None = None
        self._actors: set[int] = set()

    def _moscow_today(self) -> date:
        return self._clock.now().astimezone(_MOSCOW_TZ).date()

    def _maybe_reset_locked(self) -> None:
        """Под `_lock`-ом: сбросить set, если день сменился."""
        today = self._moscow_today()
        if self._current_date != today:
            self._current_date = today
            self._actors = set()

    async def record_active(self, *, tg_user_id: int) -> None:
        async with self._lock:
            self._maybe_reset_locked()
            self._actors.add(tg_user_id)

    async def current(self) -> int:
        async with self._lock:
            self._maybe_reset_locked()
            return len(self._actors)


class InMemoryDauLimit(IDauLimit):
    """In-memory `MAX_DAU`. Переживает только в процессе бота.

    На старте — забирается из `Settings.bot.max_dau`. После
    `/set_max_dau N` — обновляется. На рестарте бота снова берётся
    из env (`BOT_MAX_DAU`) — поэтому persistent-изменение **MAX_DAU**
    делается через env, а runtime-команда — для оперативной реакции
    на пиковую нагрузку.
    """

    __slots__ = ("_lock", "_max_dau")

    def __init__(self, *, initial: int) -> None:
        if initial < 1:
            raise ValueError(f"initial MAX_DAU must be >= 1, got {initial}")
        self._lock = asyncio.Lock()
        self._max_dau = initial

    async def get(self) -> int:
        async with self._lock:
            return self._max_dau

    async def set(self, *, max_dau: int) -> int:
        if max_dau < 1:
            raise ValueError(f"max_dau must be >= 1, got {max_dau}")
        async with self._lock:
            previous = self._max_dau
            self._max_dau = max_dau
            return previous
