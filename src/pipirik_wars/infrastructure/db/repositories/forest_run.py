"""Реализация `IForestRunRepository` поверх таблицы `forest_runs`.

Сериализация ADT `Drop` — три колонки `drop_kind` / `drop_item_id` /
`drop_name`. На выходе из репо мы восстанавливаем `Item` по `drop_item_id`
**через `IBalanceConfig`** — каталог предметов и есть источник правды.
Это значит, что если админ убрал предмет из каталога между стартом и
финишем похода, репо вернёт ошибку «item not in catalog» и `FinishForestRun`
сможет её осознанно обработать (Спринт 1.3.C). На уровне 1.3.B этой
ошибки не возникает: мы пишем дроп, который только что выбрал
`compute_forest_outcome` из текущего `IBalanceConfig`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.forest import (
    Drop,
    ForestRun,
    ForestRunStatus,
    IForestRunRepository,
    Item,
    ItemDrop,
    Name,
    NameDrop,
    NoDrop,
)
from pipirik_wars.infrastructure.db.models import ForestRunORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError


def _drop_to_columns(drop: Drop) -> tuple[str, str | None, str | None]:
    """Сериализовать `Drop` в три колонки БД."""
    match drop:
        case NoDrop():
            return ("none", None, None)
        case ItemDrop(item=item):
            return ("item", item.id, None)
        case NameDrop(name=name):
            return ("name", None, name.value)


def _columns_to_drop(
    *,
    drop_kind: str,
    drop_item_id: str | None,
    drop_name: str | None,
    balance: IBalanceConfig,
) -> Drop:
    """Восстановить `Drop` из трёх колонок + текущего каталога."""
    if drop_kind == "none":
        return NoDrop()
    if drop_kind == "item":
        if drop_item_id is None:  # CHECK на БД это запрещает; защита от ручных правок
            raise DomainIntegrityError("forest_runs row: drop_kind=item without drop_item_id")
        catalog = balance.get().items_catalog
        for entry in catalog:
            if entry.id == drop_item_id:
                return ItemDrop(
                    item=Item(
                        id=entry.id,
                        slot=entry.slot,
                        display_name=entry.display_name,
                        rarity=entry.rarity,
                    )
                )
        raise DomainIntegrityError(f"forest_runs row references unknown item id={drop_item_id}")
    if drop_kind == "name":
        if drop_name is None:
            raise DomainIntegrityError("forest_runs row: drop_kind=name without drop_name")
        return NameDrop(name=Name(value=drop_name))
    raise DomainIntegrityError(f"forest_runs row: unknown drop_kind={drop_kind!r}")


def _row_to_entity(row: ForestRunORM, *, balance: IBalanceConfig) -> ForestRun:
    drop = _columns_to_drop(
        drop_kind=row.drop_kind,
        drop_item_id=row.drop_item_id,
        drop_name=row.drop_name,
        balance=balance,
    )
    return ForestRun(
        id=row.id,
        player_id=row.player_id,
        status=ForestRunStatus(row.status),
        started_at=ensure_utc(row.started_at),
        ends_at=ensure_utc(row.ends_at),
        branch_name=row.branch_name,
        length_delta_cm=row.length_delta_cm,
        drop=drop,
        finished_at=ensure_utc(row.finished_at) if row.finished_at is not None else None,
    )


class SqlAlchemyForestRunRepository(IForestRunRepository):
    """`(player_id, status='in_progress')` — partial unique-индекс.

    Повторный INSERT с активным походом падает на `IntegrityError`
    БД-уровня и преобразуется в доменный `IntegrityError`. Use-case
    `StartForestRun` дополнительно охраняет инвариант через
    `ActivityLockService`, поэтому БД-эксепшен — last-line-of-defense
    на случай, если кто-то обходит use-case (миграции, ручные SQL).
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

    async def add(self, run: ForestRun) -> ForestRun:
        if run.id is not None:
            raise DomainIntegrityError(
                f"ForestRun with pre-set id={run.id} cannot be added; use save()"
            )
        drop_kind, drop_item_id, drop_name = _drop_to_columns(run.drop)
        row = ForestRunORM(
            player_id=run.player_id,
            status=run.status.value,
            started_at=run.started_at,
            ends_at=run.ends_at,
            branch_name=run.branch_name,
            length_delta_cm=run.length_delta_cm,
            drop_kind=drop_kind,
            drop_item_id=drop_item_id,
            drop_name=drop_name,
            finished_at=run.finished_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add forest_run for player_id={run.player_id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row, balance=self._balance)

    async def get_by_id(self, *, run_id: int) -> ForestRun | None:
        row = await self._uow.session.get(ForestRunORM, run_id)
        if row is None:
            return None
        return _row_to_entity(row, balance=self._balance)

    async def get_active_by_player(self, *, player_id: int) -> ForestRun | None:
        result = await self._uow.session.execute(
            select(ForestRunORM).where(
                ForestRunORM.player_id == player_id,
                ForestRunORM.status == ForestRunStatus.IN_PROGRESS.value,
            ),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_entity(row, balance=self._balance)

    async def save(self, run: ForestRun) -> ForestRun:
        if run.id is None:
            raise DomainIntegrityError("ForestRun.save requires id; use add() for new runs")
        result = await self._uow.session.execute(
            select(ForestRunORM).where(ForestRunORM.id == run.id),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise DomainIntegrityError(f"ForestRun id={run.id} not found")
        drop_kind, drop_item_id, drop_name = _drop_to_columns(run.drop)
        row.status = run.status.value
        row.started_at = run.started_at
        row.ends_at = run.ends_at
        row.branch_name = run.branch_name
        row.length_delta_cm = run.length_delta_cm
        row.drop_kind = drop_kind
        row.drop_item_id = drop_item_id
        row.drop_name = drop_name
        row.finished_at = run.finished_at
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to save forest_run id={run.id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row, balance=self._balance)
