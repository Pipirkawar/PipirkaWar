"""Реализация `IDungeonRunRepository` поверх таблицы `dungeon_runs`.

Зеркало `SqlAlchemyMountainRunRepository`. Различия — только имя
таблицы (`dungeon_runs`), доменные типы (`DungeonRun`,
`DungeonRunStatus`) и ORM (`DungeonRunORM`). Семантика partial-unique
индекса, JSON-сериализация дропов, CHECK-инварианты, восстановление
`Item` через каталог — идентичные. См. docstring `mountain_run.py`
для подробностей.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError

from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.dungeon import (
    DungeonRun,
    DungeonRunStatus,
    IDungeonRunRepository,
    PveItemDrop,
)
from pipirik_wars.domain.forest import Item
from pipirik_wars.infrastructure.db.models import DungeonRunORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.db.utils import ensure_utc
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError


def _drops_to_json(drops: tuple[PveItemDrop, ...]) -> list[dict[str, str]]:
    return [{"item_id": d.item.id} for d in drops]


def _json_to_drops(
    raw: list[dict[str, str]] | None,
    *,
    balance: IBalanceConfig,
) -> tuple[PveItemDrop, ...]:
    if not raw:
        return ()
    catalog = balance.get().items_catalog
    items_by_id = {entry.id: entry for entry in catalog}
    out: list[PveItemDrop] = []
    for record in raw:
        item_id = record.get("item_id")
        if not item_id:
            raise DomainIntegrityError(
                f"dungeon_runs row: drops entry missing item_id, got {record!r}"
            )
        entry = items_by_id.get(item_id)
        if entry is None:
            raise DomainIntegrityError(f"dungeon_runs row references unknown item id={item_id}")
        out.append(
            PveItemDrop(
                item=Item(
                    id=entry.id,
                    slot=entry.slot,
                    display_name=entry.display_name,
                    rarity=entry.rarity,
                )
            )
        )
    return tuple(out)


def _row_to_entity(row: DungeonRunORM, *, balance: IBalanceConfig) -> DungeonRun:
    return DungeonRun(
        id=row.id,
        player_id=row.player_id,
        status=DungeonRunStatus(row.status),
        started_at=ensure_utc(row.started_at),
        ends_at=ensure_utc(row.ends_at),
        branch_name=row.branch_name,
        length_delta_cm=row.length_delta_cm,
        drops=_json_to_drops(row.drops, balance=balance),
        finished_at=ensure_utc(row.finished_at) if row.finished_at is not None else None,
    )


def _branch_sign(length_delta_cm: int) -> str:
    return "loss" if length_delta_cm < 0 else "gain"


class SqlAlchemyDungeonRunRepository(IDungeonRunRepository):
    """`(player_id, status='in_progress')` — partial unique-индекс."""

    __slots__ = ("_balance", "_uow")

    def __init__(
        self,
        *,
        uow: SqlAlchemyUnitOfWork,
        balance: IBalanceConfig,
    ) -> None:
        self._uow = uow
        self._balance = balance

    async def add(self, run: DungeonRun) -> DungeonRun:
        if run.id is not None:
            raise DomainIntegrityError(
                f"DungeonRun with pre-set id={run.id} cannot be added; use save()"
            )
        row = DungeonRunORM(
            player_id=run.player_id,
            status=run.status.value,
            started_at=run.started_at,
            ends_at=run.ends_at,
            branch_name=run.branch_name,
            branch_sign=_branch_sign(run.length_delta_cm),
            length_delta_cm=run.length_delta_cm,
            drops=_drops_to_json(run.drops),
            finished_at=run.finished_at,
        )
        self._uow.session.add(row)
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to add dungeon_run for player_id={run.player_id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row, balance=self._balance)

    async def get_by_id(self, *, run_id: int) -> DungeonRun | None:
        row = await self._uow.session.get(DungeonRunORM, run_id)
        if row is None:
            return None
        return _row_to_entity(row, balance=self._balance)

    async def get_active_by_player(self, *, player_id: int) -> DungeonRun | None:
        result = await self._uow.session.execute(
            select(DungeonRunORM).where(
                DungeonRunORM.player_id == player_id,
                DungeonRunORM.status == DungeonRunStatus.IN_PROGRESS.value,
            ),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_entity(row, balance=self._balance)

    async def save(self, run: DungeonRun) -> DungeonRun:
        if run.id is None:
            raise DomainIntegrityError("DungeonRun.save requires id; use add() for new runs")
        result = await self._uow.session.execute(
            select(DungeonRunORM).where(DungeonRunORM.id == run.id),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise DomainIntegrityError(f"DungeonRun id={run.id} not found")
        row.status = run.status.value
        row.started_at = run.started_at
        row.ends_at = run.ends_at
        row.branch_name = run.branch_name
        row.branch_sign = _branch_sign(run.length_delta_cm)
        row.length_delta_cm = run.length_delta_cm
        row.drops = _drops_to_json(run.drops)
        row.finished_at = run.finished_at
        try:
            await self._uow.session.flush()
        except SqlAlchemyIntegrityError as exc:
            raise DomainIntegrityError(
                f"failed to save dungeon_run id={run.id}: {exc.orig}"
            ) from exc
        return _row_to_entity(row, balance=self._balance)
