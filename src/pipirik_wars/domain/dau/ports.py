"""Порты подсистемы DAU Gate (ГДД §18)."""

from __future__ import annotations

import abc


class IDauCounter(abc.ABC):
    """Счётчик уникальных активных игроков за сегодня (по `Europe/Moscow`).

    Семантика «активный»:
    - При успешном `RegisterPlayer` use-case зовёт `record_active(tg_user_id)`.
    - При любом игровом действии (`/forest`, `/profile`, `/oracle`, ...)
      handler зовёт `record_active(tg_user_id)`.

    «Сегодня» — игровой день по таймзоне `Europe/Moscow` (соответствует
    `oracle.cooldown_tz` из `balance.yaml`). Сброс множества — при
    первом обращении после полуночи МСК.

    Реализация по умолчанию — in-memory (см. `InMemoryDauCounter`).
    Может быть заменена на Redis-backend в будущем без изменения use-case-ов.
    """

    @abc.abstractmethod
    async def record_active(self, *, tg_user_id: int) -> None:
        """Зарегистрировать актора как активного сегодня. Идемпотентно."""

    @abc.abstractmethod
    async def current(self) -> int:
        """Сколько уникальных активных за сегодня. Никогда не отрицательное."""


class IDauLimit(abc.ABC):
    """Runtime-управляемый `MAX_DAU` (ГДД §18.2).

    Стартовое значение приходит из `Settings.bot.max_dau` (env / `.env`),
    но админ может менять «на горячую» через `/set_max_dau N`. Изменение
    логируется в `audit_log` (`DAU_LIMIT_CHANGE`).

    Реализация — in-memory (см. `InMemoryDauLimit`). Простой класс
    с одним int-полем; разделена с `IDauCounter` намеренно (ISP):
    одни callsite-ы пишут лимит, другие читают для решения «пропускать
    регистрацию или ставить в очередь».
    """

    @abc.abstractmethod
    async def get(self) -> int:
        """Текущий `MAX_DAU` (всегда `>= 1`)."""

    @abc.abstractmethod
    async def set(self, *, max_dau: int) -> int:
        """Заменить `MAX_DAU` и вернуть прежнее значение.

        Бросает `ValueError`, если `max_dau < 1`.
        """
