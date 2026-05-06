"""Aiogram-фильтр `IsAdminFilter` (Спринт 2.5-B.6).

Тихий игнор не-админских апдейтов на уровне router-а: `admin_support_router`
получает «к себе» только сообщения от активных админов. Это нужно по
ГДД §18.6.4 — мы не хотим, чтобы случайный пользователь, дёрнув
`/find_player`, узнал о факте существования команды («не отвечает» —
значит, такой команды нет).

Источник правды — `data["admin"]` (его кладёт `AdminGuard`-middleware
до того, как фильтр сработает). Если ключа нет (`AdminGuard` не подключён),
фильтр работает как «не-админ» — отказывает; это безопасный default.
"""

from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from pipirik_wars.bot.middlewares.admin_guard import DATA_KEY as ADMIN_DATA_KEY
from pipirik_wars.domain.admin import Admin


class IsAdminFilter(BaseFilter):
    """Пускает только активных админов (`data["admin"] is not None`)."""

    async def __call__(self, event: TelegramObject, **data: Any) -> bool:
        admin = data.get(ADMIN_DATA_KEY)
        return isinstance(admin, Admin)


__all__ = ["IsAdminFilter"]
