"""Реализация `IItemRepository` поверх таблицы `items` (Спринт 3.4-B).

Категория предмета (`weapon`/`armor`/`jewelry`) **не** хранится в БД —
выводится из `Slot` каталожной записи через
`ItemCategory.from_slot(...)`. Источник правды — `IBalanceConfig`-каталог
(см. `forest_run`-репо: тот же приём `_columns_to_drop` + `IBalanceConfig`).

Если админ выпилил предмет из `items_catalog` между сохранением и
чтением, репо вернёт `DomainIntegrityError("unknown item id=…")` —
эта проблема всплывёт в use-case-ах 3.4-C / 3.4-D, где её можно
осознанно обработать (показать игроку «предмет более не доступен в
каталоге», списать в `audit_log` для админа).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.inventory import (
    IItemRepository,
    Item,
    ItemCategory,
    ItemNotFoundError,
)
from pipirik_wars.infrastructure.db.models import ItemORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError


def _category_for_item_id(item_id: str, *, balance: IBalanceConfig) -> ItemCategory:
    """Найти каталожную запись и вывести категорию из её `slot`.

    Если `item_id` нет в каталоге — `DomainIntegrityError`. Это значит,
    что либо БД-запись pred-ает каталогу (например, кто-то удалил предмет
    из `balance.yaml`), либо это бага вызывающего кода (`add()` без
    каталога-валидации).
    """
    catalog = balance.get().items_catalog
    for entry in catalog:
        if entry.id == item_id:
            return ItemCategory.from_slot(entry.slot)
    raise DomainIntegrityError(f"items row references unknown item id={item_id!r}")


def _row_to_entity(row: ItemORM, *, balance: IBalanceConfig) -> Item:
    """Восстановить доменный `Item` из ORM-строки + каталога."""
    category = _category_for_item_id(row.item_id, balance=balance)
    return Item(
        id=row.item_id,
        category=category,
        enchant_level=row.enchant_level,
    )


class SqlAlchemyItemRepository(IItemRepository):
    """Репозиторий инвентаря поверх `items`-таблицы.

    Зависит от `IBalanceConfig` ради `ItemCategory.from_slot(...)` —
    БД хранит только `(player_id, item_id, enchant_level, acquired_at)`,
    а агрегат `Item` требует `category`. Каталог + слот — единый
    источник правды; БД остаётся минимальной.
    """

    __slots__ = ("_balance", "_uow")

    def __init__(
        self,
        *,
        uow: SqlAlchemyUnitOfWork,
        balance: IBalanceConfig,
    ) -> None:
        self._uow = uow
        self._balance = balance

    async def get(self, *, player_id: int, item_id: str) -> Item:
        stmt = select(ItemORM).where(
            ItemORM.player_id == player_id,
            ItemORM.item_id == item_id,
        )
        result = await self._uow.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise ItemNotFoundError(player_id=player_id, item_id=item_id)
        return _row_to_entity(row, balance=self._balance)

    async def add(self, *, player_id: int, item_id: str, now: datetime) -> Item:
        # Валидируем item_id заранее — иначе при чтении после INSERT-а
        # _row_to_entity всё равно бросит DomainIntegrityError, но уже
        # после реального INSERT-а (это попало бы в БД и при rollback-е
        # «осиротело» по семантике). Сразу падаем на «item_id вне каталога».
        category = _category_for_item_id(item_id, balance=self._balance)

        row = ItemORM(
            player_id=player_id,
            item_id=item_id,
            enchant_level=0,
            acquired_at=now,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add item ({player_id=}, {item_id=}): {exc.orig}"
            ) from exc

        return Item(id=item_id, category=category, enchant_level=0)

    async def update_enchant_level(
        self,
        *,
        player_id: int,
        item_id: str,
        new_level: int,
    ) -> Item:
        stmt = (
            update(ItemORM)
            .where(
                ItemORM.player_id == player_id,
                ItemORM.item_id == item_id,
            )
            .values(enchant_level=new_level)
        )
        result = await self._uow.session.execute(stmt)
        if not isinstance(result, CursorResult):  # pragma: no cover  (защита от изменений API)
            raise RuntimeError("UPDATE must return CursorResult")
        if not (result.rowcount and result.rowcount > 0):
            raise ItemNotFoundError(player_id=player_id, item_id=item_id)

        # re-get, чтобы вернуть актуальный агрегат — `enchant_level` известен,
        # но `category` всё равно требует каталог-lookup.
        return await self.get(player_id=player_id, item_id=item_id)

    async def delete(self, *, player_id: int, item_id: str) -> None:
        stmt = delete(ItemORM).where(
            ItemORM.player_id == player_id,
            ItemORM.item_id == item_id,
        )
        result = await self._uow.session.execute(stmt)
        if not isinstance(result, CursorResult):  # pragma: no cover  (защита от изменений API)
            raise RuntimeError("DELETE must return CursorResult")
        if not (result.rowcount and result.rowcount > 0):
            raise ItemNotFoundError(player_id=player_id, item_id=item_id)

    async def list_by_player(self, *, player_id: int) -> tuple[Item, ...]:
        # Сортировка `acquired_at ASC, item_id ASC` — детерминированный
        # порядок для стабильности snapshot-тестов и предсказуемого
        # UI («сверху — что первее всего получил»).
        stmt = (
            select(ItemORM)
            .where(ItemORM.player_id == player_id)
            .order_by(ItemORM.acquired_at.asc(), ItemORM.item_id.asc())
        )
        result = await self._uow.session.execute(stmt)
        rows = result.scalars().all()
        return tuple(_row_to_entity(row, balance=self._balance) for row in rows)
