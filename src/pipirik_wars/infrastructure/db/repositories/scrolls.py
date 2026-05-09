"""Реализация `IScrollRepository` поверх таблицы `scrolls` (Спринт 3.4-C).

Скролл — VO `Scroll(category, blessed)` без owner-id. В таблице
`scrolls` стэкается на `(player_id, scroll_id)` с колонкой
`qty INT NOT NULL CHECK qty >= 0`. Репо делает три операции:

* `get(player_id, scroll_id)` — возвращает `Scroll`-VO,
  восстановленный из `scroll_id` через `Scroll.from_scroll_id(...)`
  (количество **не** входит в VO; запрос смотрит только на наличие
  строки). `ScrollNotFoundError`, если строки нет.
* `add(player_id, scroll_id, qty, now)` — UPSERT-семантика: если
  у игрока уже есть запись с таким `scroll_id`, инкрементит `qty`;
  иначе создаёт новую с `acquired_at=now`. `qty <= 0` → `ValueError`.
* `consume(player_id, scroll_id, qty=1)` — атомарный декремент:
  `UPDATE scrolls SET qty = qty - :n WHERE player_id = :p AND
  scroll_id = :s AND qty >= :n` — `rowcount == 0` означает, что
  либо нет записи, либо `qty < n`. Различие выявляется отдельным
  `SELECT`-ом, чтобы дать точную ошибку
  (`ScrollNotFoundError` vs `ScrollOutOfStockError`).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult

from pipirik_wars.domain.enchantment.entities import Scroll
from pipirik_wars.domain.inventory import (
    IScrollRepository,
    ScrollNotFoundError,
    ScrollOutOfStockError,
)
from pipirik_wars.infrastructure.db.models import ScrollORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyScrollRepository(IScrollRepository):
    """Репозиторий стэкабельных скроллов поверх `scrolls`-таблицы."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def get(self, *, player_id: int, scroll_id: str) -> Scroll:
        stmt = select(ScrollORM).where(
            ScrollORM.player_id == player_id,
            ScrollORM.scroll_id == scroll_id,
        )
        result = await self._uow.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise ScrollNotFoundError(player_id=player_id, scroll_id=scroll_id)
        # VO не зависит от `qty` — восстанавливаем из стабильного scroll_id.
        return Scroll.from_scroll_id(scroll_id)

    async def add(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int,
        now: datetime,
    ) -> None:
        if qty <= 0:
            raise ValueError(f"qty must be > 0, got {qty}")

        # UPSERT: SELECT ... FOR UPDATE → INSERT or UPDATE qty += :n.
        # Используем portable-подход (без INSERT ... ON CONFLICT),
        # чтобы и SQLite, и PostgreSQL работали одинаково.
        stmt = select(ScrollORM).where(
            ScrollORM.player_id == player_id,
            ScrollORM.scroll_id == scroll_id,
        )
        result = await self._uow.session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            new_row = ScrollORM(
                player_id=player_id,
                scroll_id=scroll_id,
                qty=qty,
                acquired_at=now,
            )
            self._uow.session.add(new_row)
            await self._uow.session.flush()
        else:
            inc_stmt = (
                update(ScrollORM)
                .where(
                    ScrollORM.player_id == player_id,
                    ScrollORM.scroll_id == scroll_id,
                )
                .values(qty=ScrollORM.qty + qty)
            )
            await self._uow.session.execute(inc_stmt)

    async def consume(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int = 1,
    ) -> None:
        if qty <= 0:
            raise ValueError(f"qty must be > 0, got {qty}")

        # Атомарный декремент: WHERE qty >= :n гарантирует, что мы не
        # уйдём в отрицательные числа даже при race-condition между
        # параллельными use-case-ами одного игрока.
        stmt = (
            update(ScrollORM)
            .where(
                ScrollORM.player_id == player_id,
                ScrollORM.scroll_id == scroll_id,
                ScrollORM.qty >= qty,
            )
            .values(qty=ScrollORM.qty - qty)
        )
        result = await self._uow.session.execute(stmt)
        if not isinstance(result, CursorResult):  # pragma: no cover  (защита от изменений API)
            raise RuntimeError("UPDATE must return CursorResult")

        if result.rowcount and result.rowcount > 0:
            return

        # rowcount=0 — либо нет записи, либо qty < requested.
        # Делаем дополнительный SELECT для точной ошибки.
        check_stmt = select(ScrollORM.qty).where(
            ScrollORM.player_id == player_id,
            ScrollORM.scroll_id == scroll_id,
        )
        check_result = await self._uow.session.execute(check_stmt)
        available = check_result.scalar_one_or_none()
        if available is None:
            raise ScrollNotFoundError(player_id=player_id, scroll_id=scroll_id)
        raise ScrollOutOfStockError(
            player_id=player_id,
            scroll_id=scroll_id,
            requested_qty=qty,
            available_qty=int(available),
        )
