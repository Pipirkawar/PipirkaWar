"""Порт `IItemRepository` для инвентарного слоя (Спринт 3.4-B).

Контракт чистый: репозиторий **не** видит ORM, не видит SQL —
он принимает доменные значения (`player_id: int`, `item_id: str`,
`new_level: int`, `now: datetime`) и возвращает доменный агрегат
`Item`. Категория предмета (`weapon` / `armor` / `jewelry`) внутри
импла выводится из `Slot` каталожной записи через
`ItemCategory.from_slot(...)`, поэтому в БД хранятся только
`(player_id, item_id, enchant_level, acquired_at)` — без
денормализованной `category`.

Use-case `EnchantItem` (Спринт 3.4-C) пользуется только этим
портом и не знает про SQLAlchemy / Alembic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pipirik_wars.domain.inventory.entities import Item

__all__ = ["IItemRepository"]


class IItemRepository(Protocol):
    """Репозиторий инвентарных предметов (Спринт 3.4-B).

    Все методы — асинхронные, выполняются в открытой `IUnitOfWork`-сессии.
    Композиционный root (`bot/main.py`) пробрасывает SQLAlchemy-impl;
    тесты use-case-ов используют `FakeItemRepository`.
    """

    async def get(self, *, player_id: int, item_id: str) -> Item:
        """Прочитать предмет из инвентаря игрока.

        Поднимает `ItemNotFoundError(player_id, item_id)`, если строки
        в `items` с такой парой ключей нет.
        """
        ...

    async def add(self, *, player_id: int, item_id: str, now: datetime) -> Item:
        """Добавить предмет в инвентарь игрока (`enchant_level=0`).

        Используется при дропах из активностей (forest / mountain /
        dungeon / boss). Если у игрока уже есть предмет с тем же
        `item_id` (composite PK `(player_id, item_id)`), импл
        бросит `pipirik_wars.shared.errors.IntegrityError` —
        политика «что делать с дубликатом» (заменить / отказать /
        вернуть существующий) — задача 3.4-D или будущего sprint-а.

        `item_id` должен присутствовать в `IBalanceConfig.items_catalog` —
        иначе категория не выводится; импл бросит
        `pipirik_wars.shared.errors.IntegrityError`.

        Возвращает свежесозданный `Item(id=item_id, category, enchant_level=0)`.
        """
        ...

    async def update_enchant_level(
        self,
        *,
        player_id: int,
        item_id: str,
        new_level: int,
    ) -> Item:
        """Обновить уровень заточки предмета.

        Поднимает `ItemNotFoundError(player_id, item_id)`, если строки
        в `items` нет (0 rows affected).

        Возвращает обновлённый `Item` (после re-`get`-а), чтобы
        вызывающий код получил актуальное состояние одним вызовом
        и не делал дополнительный round-trip.
        """
        ...
