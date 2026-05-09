"""Порты инвентарного слоя: `IItemRepository` (3.4-B) + `IScrollRepository` (3.4-C).

Контракты чистые: репозитории **не** видят ORM, не видят SQL —
они принимают доменные значения (`player_id: int`, `item_id: str`,
`scroll_id: str`, `qty: int`, `now: datetime`) и возвращают доменные
агрегаты (`Item`, `Scroll`). Use-case `EnchantItem` (Спринт 3.4-C)
пользуется только этими портами и не знает про SQLAlchemy / Alembic.

`IItemRepository` (3.4-B):
- `get` / `add` / `update_enchant_level` / `delete` (последний — для
  исхода `DESTROY`, добавлен в 3.4-C).
- Категория предмета (`weapon` / `armor` / `jewelry`) внутри импла
  выводится из `Slot` каталожной записи через
  `ItemCategory.from_slot(...)`, поэтому в БД хранятся только
  `(player_id, item_id, enchant_level, acquired_at)` — без
  денормализованной `category`.

`IScrollRepository` (3.4-C):
- `get` / `add` / `consume` — стэкабельный счётчик `qty` на каждую
  `(player_id, scroll_id)`-пару (где `scroll_id` =
  `{category.value}:{regular|blessed}`, см. `Scroll.scroll_id`).
- `consume(qty)` — атомарный декремент с проверкой `qty >= requested`;
  `ScrollOutOfStockError`, если в стэке меньше; `ScrollNotFoundError`,
  если строки нет вообще.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pipirik_wars.domain.enchantment.entities import Scroll
from pipirik_wars.domain.inventory.entities import Item

__all__ = [
    "IEnchantHistoryReader",
    "IItemRepository",
    "IScrollRepository",
    "ScrollStack",
]


@dataclass(frozen=True, slots=True)
class ScrollStack:
    """Стэк скроллов одного типа в инвентаре игрока (Спринт 3.4-D).

    Доменное представление одной строки `scrolls`-таблицы для
    UI-листинга `/inventory`: VO-скролл + текущее `qty`. Не входит
    в `Item`-агрегат, не пересекается с `Scroll`-VO (тот идентичен
    по `(category, blessed)` и не содержит количество).

    Используется только `IScrollRepository.list_by_player` и
    application use-case-ом `GetInventory`.
    """

    scroll: Scroll
    qty: int


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

    async def delete(self, *, player_id: int, item_id: str) -> None:
        """Удалить предмет из инвентаря игрока (исход `DESTROY`, ГДД §2.8.3).

        Используется use-case-ом `EnchantItem` (3.4-C) при выпадении
        исхода `RegularEnchantOutcome.DESTROY`: предмет уничтожается
        физически (DELETE row), а не помечается soft-delete-флагом —
        ГДД §2.8.3 разрешает повторное «приобретение того же каталожного
        item_id» дропом (предмет — каталожный шаблон, не уникальная инстанция).

        Поднимает `ItemNotFoundError(player_id, item_id)`, если строки
        в `items` нет (0 rows affected). Это защита от двойного DELETE
        при race-condition use-case-ов.
        """
        ...

    async def list_by_player(self, *, player_id: int) -> tuple[Item, ...]:
        """Прочитать все предметы игрока (Спринт 3.4-D).

        Используется UI-командой `/inventory` (через application
        use-case `GetInventory`). Сортировка — детерминированная
        (по `acquired_at ASC, item_id ASC`), чтобы snapshot-тесты
        UI давали стабильный порядок.

        Возвращает пустой кортеж, если у игрока нет предметов.
        Никогда не бросает: «инвентарь пуст» — валидное состояние.
        """
        ...


class IScrollRepository(Protocol):
    """Репозиторий стэкабельных скроллов заточки (Спринт 3.4-C).

    Скролл — VO `Scroll(category, blessed)` без owner-id. В таблице
    `scrolls` стэкается на `(player_id, scroll_id)` с колонкой
    `qty INT NOT NULL CHECK qty >= 0`. `scroll_id` — стабильный
    string-id формата `{category.value}:{regular|blessed}` (см.
    `Scroll.scroll_id`-property).

    Все методы — асинхронные, выполняются в открытой `IUnitOfWork`-сессии.
    """

    async def get(self, *, player_id: int, scroll_id: str) -> Scroll:
        """Прочитать VO скролла из инвентаря.

        Возвращает `Scroll(category, blessed)`, восстановленный из
        `scroll_id` (один и тот же `Scroll` — для любого `qty > 0`;
        количество **не** входит в VO). Это — отражение того, что VO
        идентичен по `(category, blessed)`-паре.

        Поднимает `ScrollNotFoundError(player_id, scroll_id)`, если
        строки нет (никогда не имели этот скролл, либо `qty=0`-строки
        были удалены).
        """
        ...

    async def add(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int,
        now: datetime,
    ) -> None:
        """Добавить `qty` скроллов в стэк игрока (UPSERT).

        Используется при дропах из активностей (mountains / dungeon /
        boss-fights). Если у игрока уже есть запись с таким `scroll_id`
        — `qty` инкрементится; иначе создаётся новая запись с
        `acquired_at=now`.

        `qty` должен быть `> 0`; иначе `ValueError` (вызывающий код —
        бажный).
        """
        ...

    async def consume(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int = 1,
    ) -> None:
        """Атомарно списать `qty` скроллов из стэка (декремент `qty`-колонки).

        Используется use-case-ом `EnchantItem` (3.4-C) перед роллом
        исхода — скролл «расходуется» в любом исходе кроме
        `WrongScrollCategoryError` (там скролл не списывается).

        Поднимает:
        - `ScrollNotFoundError(player_id, scroll_id)` — если строки
          в `scrolls` нет вообще;
        - `ScrollOutOfStockError(player_id, scroll_id, requested_qty,
          available_qty)` — если строка есть, но `qty < requested`.

        Реализация атомарная: один `UPDATE qty = qty - :n WHERE
        player_id = :p AND scroll_id = :s AND qty >= :n` —
        `rowcount == 0` означает, что либо нет записи, либо
        `qty < n` (различие выявляется отдельным `SELECT`-ом перед
        падением, чтобы дать точную ошибку).
        """
        ...

    async def list_by_player(self, *, player_id: int) -> tuple[ScrollStack, ...]:
        """Прочитать все стэки скроллов игрока (Спринт 3.4-D).

        Возвращает кортеж `ScrollStack(scroll, qty)`-DTO для каждой
        строки `scrolls` с `qty > 0`. `qty == 0`-строки пропускаются
        (теоретически могут существовать после consume → 0; UI их
        прячет).

        Сортировка — детерминированная (по `scroll_id ASC`), для
        стабильности snapshot-тестов. Возвращает пустой кортеж,
        если у игрока нет скроллов.
        """
        ...


class IEnchantHistoryReader(Protocol):
    """Чтение истории попыток заточки игрока (Спринт 3.4-C, C.5).

    Используется trip-wire-ом анти-чита `EnchantItem`-use-case-а
    для детекции аномальных серий успехов на высоких тирах
    (`+18 → +25`, ГДД §2.8 + §3.3.4).

    Имплементация — поверх таблицы `audit_log`, чтение событий
    `ITEM_ENCHANT_ATTEMPT` отфильтрованных по `target_id=player_id`.
    Источник правды — те же audit-записи, что use-case **сам** пишет
    после каждой попытки; это значит, для актуальности
    последнего события нужно вызывать `get_recent_high_tier_outcomes`
    **после** `audit.record(...)` + `flush()` текущей попытки.

    Все методы — асинхронные, в открытой `IUnitOfWork`-сессии.
    """

    async def get_recent_high_tier_outcomes(
        self,
        *,
        player_id: int,
        tier_min: int,
        tier_max: int,
        limit: int,
    ) -> tuple[bool, ...]:
        """Получить успех/неуспех последних `limit` попыток заточки
        игрока на тирах `[tier_min, tier_max]` (по `enchant_level`-у
        **до** попытки).

        Возвращает кортеж длины `<= limit` с success-флагами в DESC-порядке
        (самая свежая попытка — первая). `success` / `success_1` /
        `success_2` → True; всё остальное (`no_effect` / `drop` /
        `drop_1` / `drop_2` / `destroy`) → False.

        Если у игрока меньше `limit` попыток на этих тирах — возвращается
        кортеж длины `< limit` (анти-чит сам решит, считать ли это
        достаточным для алерта).
        """
        ...
