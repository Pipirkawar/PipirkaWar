"""Integration-тесты `SqlAlchemyScrollRepository` (Спринт 3.4-C, C.3).

Покрытие:
* round-trip `add → get` для всех 6 (категория × blessed)-комбинаций;
* `add(qty)` дважды → стэк `qty` (UPSERT-семантика);
* `add(qty=0)` / `add(qty=-1)` → `ValueError` (доменный invariant);
* `consume(qty)` — успех (декремент), нет записи (`ScrollNotFoundError`),
  не хватает (`ScrollOutOfStockError`);
* `consume(qty=0)` → `ValueError`;
* атомарность `consume`-а: после полного расходования `qty=0`-строка
  остаётся в БД (отличаемая от «нет записи»);
* изоляция между игроками — `add` одного не виден другому.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from pipirik_wars.domain.enchantment.entities import Scroll, ScrollCategory
from pipirik_wars.domain.inventory import (
    ScrollNotFoundError,
    ScrollOutOfStockError,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.db.models import ScrollORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyPlayerRepository,
    SqlAlchemyScrollRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)

_ALL_SIX_SCROLLS: list[Scroll] = [
    Scroll(category=ScrollCategory.WEAPON, blessed=False),
    Scroll(category=ScrollCategory.WEAPON, blessed=True),
    Scroll(category=ScrollCategory.ARMOR, blessed=False),
    Scroll(category=ScrollCategory.ARMOR, blessed=True),
    Scroll(category=ScrollCategory.JEWELRY, blessed=False),
    Scroll(category=ScrollCategory.JEWELRY, blessed=True),
]


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _make_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyScrollRepository:
    return SqlAlchemyScrollRepository(uow=uow)


class TestSqlAlchemyScrollRepositoryRoundTrip:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("scroll", _ALL_SIX_SCROLLS)
    async def test_add_then_get_roundtrip_all_six(
        self,
        uow: SqlAlchemyUnitOfWork,
        scroll: Scroll,
    ) -> None:
        """Round-trip `add → get` восстанавливает VO для всех 6 вариантов."""
        player = await _seed_player(uow, tg_id=hash(scroll.scroll_id) & 0xFFFF)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                scroll_id=scroll.scroll_id,
                qty=3,
                now=NOW,
            )

        async with uow:
            loaded = await repo.get(player_id=player.id, scroll_id=scroll.scroll_id)
        assert loaded == scroll


class TestSqlAlchemyScrollRepositoryAddStacks:
    @pytest.mark.asyncio
    async def test_add_twice_stacks_qty(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Два `add(qty=N)` подряд → `qty == 2 * N` (UPSERT)."""
        player = await _seed_player(uow, tg_id=2001)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                scroll_id="weapon_scroll:regular",
                qty=2,
                now=NOW,
            )
        async with uow:
            await repo.add(
                player_id=player.id,
                scroll_id="weapon_scroll:regular",
                qty=3,
                now=LATER,
            )

        # Проверяем qty прямым запросом — VO не носит qty.
        async with uow:
            stmt = select(ScrollORM.qty).where(
                ScrollORM.player_id == player.id,
                ScrollORM.scroll_id == "weapon_scroll:regular",
            )
            result = await uow.session.execute(stmt)
            qty = result.scalar_one()
        assert qty == 5

    @pytest.mark.asyncio
    async def test_add_preserves_acquired_at_on_increment(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`acquired_at` фиксируется при первом `add`, не переписывается."""
        player = await _seed_player(uow, tg_id=2002)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                scroll_id="armor_scroll:blessed",
                qty=1,
                now=NOW,
            )
        async with uow:
            await repo.add(
                player_id=player.id,
                scroll_id="armor_scroll:blessed",
                qty=1,
                now=LATER,
            )

        async with uow:
            stmt = select(ScrollORM.acquired_at).where(
                ScrollORM.player_id == player.id,
                ScrollORM.scroll_id == "armor_scroll:blessed",
            )
            result = await uow.session.execute(stmt)
            acquired = result.scalar_one()
        # Сравниваем без timezone-info т.к. SQLite не сохраняет TZ.
        assert acquired.replace(tzinfo=UTC) == NOW

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_qty", [0, -1, -100])
    async def test_add_rejects_non_positive_qty(
        self,
        uow: SqlAlchemyUnitOfWork,
        bad_qty: int,
    ) -> None:
        player = await _seed_player(uow, tg_id=2003 + abs(bad_qty))
        assert player.id is not None
        repo = _make_repo(uow)

        with pytest.raises(ValueError, match="qty must be > 0"):
            async with uow:
                await repo.add(
                    player_id=player.id,
                    scroll_id="weapon_scroll:regular",
                    qty=bad_qty,
                    now=NOW,
                )


class TestSqlAlchemyScrollRepositoryConsume:
    @pytest.mark.asyncio
    async def test_consume_decrements_qty(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=3001)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                scroll_id="weapon_scroll:regular",
                qty=5,
                now=NOW,
            )
        async with uow:
            await repo.consume(
                player_id=player.id,
                scroll_id="weapon_scroll:regular",
                qty=2,
            )

        async with uow:
            stmt = select(ScrollORM.qty).where(
                ScrollORM.player_id == player.id,
                ScrollORM.scroll_id == "weapon_scroll:regular",
            )
            result = await uow.session.execute(stmt)
            qty = result.scalar_one()
        assert qty == 3

    @pytest.mark.asyncio
    async def test_consume_to_zero_keeps_row(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """После полного расходования (qty=0) строка не удаляется."""
        player = await _seed_player(uow, tg_id=3002)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                scroll_id="jewelry_scroll:blessed",
                qty=2,
                now=NOW,
            )
        async with uow:
            await repo.consume(
                player_id=player.id,
                scroll_id="jewelry_scroll:blessed",
                qty=2,
            )

        # `get` всё ещё возвращает Scroll (строка существует, qty=0).
        async with uow:
            loaded = await repo.get(
                player_id=player.id,
                scroll_id="jewelry_scroll:blessed",
            )
        assert loaded == Scroll(
            category=ScrollCategory.JEWELRY,
            blessed=True,
        )

        async with uow:
            stmt = select(ScrollORM.qty).where(
                ScrollORM.player_id == player.id,
                ScrollORM.scroll_id == "jewelry_scroll:blessed",
            )
            result = await uow.session.execute(stmt)
            qty = result.scalar_one()
        assert qty == 0

    @pytest.mark.asyncio
    async def test_consume_default_qty_one(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`consume(...)` без `qty` декрементит на 1."""
        player = await _seed_player(uow, tg_id=3003)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                scroll_id="armor_scroll:regular",
                qty=3,
                now=NOW,
            )
        async with uow:
            await repo.consume(
                player_id=player.id,
                scroll_id="armor_scroll:regular",
            )

        async with uow:
            stmt = select(ScrollORM.qty).where(
                ScrollORM.player_id == player.id,
                ScrollORM.scroll_id == "armor_scroll:regular",
            )
            result = await uow.session.execute(stmt)
            qty = result.scalar_one()
        assert qty == 2

    @pytest.mark.asyncio
    async def test_consume_no_row_raises_not_found(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=3004)
        assert player.id is not None
        repo = _make_repo(uow)

        with pytest.raises(ScrollNotFoundError) as exc_info:
            async with uow:
                await repo.consume(
                    player_id=player.id,
                    scroll_id="weapon_scroll:regular",
                )
        assert exc_info.value.player_id == player.id
        assert exc_info.value.scroll_id == "weapon_scroll:regular"

    @pytest.mark.asyncio
    async def test_consume_insufficient_raises_out_of_stock(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=3005)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                scroll_id="weapon_scroll:blessed",
                qty=2,
                now=NOW,
            )

        with pytest.raises(ScrollOutOfStockError) as exc_info:
            async with uow:
                await repo.consume(
                    player_id=player.id,
                    scroll_id="weapon_scroll:blessed",
                    qty=5,
                )
        assert exc_info.value.requested_qty == 5
        assert exc_info.value.available_qty == 2

        # qty не изменился (атомарный rollback в WHERE qty >= :n).
        async with uow:
            stmt = select(ScrollORM.qty).where(
                ScrollORM.player_id == player.id,
                ScrollORM.scroll_id == "weapon_scroll:blessed",
            )
            result = await uow.session.execute(stmt)
            qty = result.scalar_one()
        assert qty == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_qty", [0, -1, -50])
    async def test_consume_rejects_non_positive_qty(
        self,
        uow: SqlAlchemyUnitOfWork,
        bad_qty: int,
    ) -> None:
        player = await _seed_player(uow, tg_id=3010 + abs(bad_qty))
        assert player.id is not None
        repo = _make_repo(uow)

        with pytest.raises(ValueError, match="qty must be > 0"):
            async with uow:
                await repo.consume(
                    player_id=player.id,
                    scroll_id="weapon_scroll:regular",
                    qty=bad_qty,
                )


class TestSqlAlchemyScrollRepositoryGet:
    @pytest.mark.asyncio
    async def test_get_no_row_raises_not_found(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=4001)
        assert player.id is not None
        repo = _make_repo(uow)

        with pytest.raises(ScrollNotFoundError) as exc_info:
            async with uow:
                await repo.get(
                    player_id=player.id,
                    scroll_id="weapon_scroll:regular",
                )
        assert exc_info.value.player_id == player.id
        assert exc_info.value.scroll_id == "weapon_scroll:regular"


class TestSqlAlchemyScrollRepositoryIsolation:
    @pytest.mark.asyncio
    async def test_two_players_isolated(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Скролл одного игрока не виден другому."""
        p1 = await _seed_player(uow, tg_id=5001)
        p2 = await _seed_player(uow, tg_id=5002)
        assert p1.id is not None
        assert p2.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=p1.id,
                scroll_id="weapon_scroll:regular",
                qty=10,
                now=NOW,
            )

        # У p2 — нет скролла, хоть scroll_id и тот же.
        with pytest.raises(ScrollNotFoundError):
            async with uow:
                await repo.get(
                    player_id=p2.id,
                    scroll_id="weapon_scroll:regular",
                )

    @pytest.mark.asyncio
    async def test_consume_one_player_does_not_affect_other(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        p1 = await _seed_player(uow, tg_id=5003)
        p2 = await _seed_player(uow, tg_id=5004)
        assert p1.id is not None
        assert p2.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=p1.id,
                scroll_id="weapon_scroll:regular",
                qty=5,
                now=NOW,
            )
            await repo.add(
                player_id=p2.id,
                scroll_id="weapon_scroll:regular",
                qty=5,
                now=NOW,
            )
        async with uow:
            await repo.consume(
                player_id=p1.id,
                scroll_id="weapon_scroll:regular",
                qty=3,
            )

        async with uow:
            stmt_p1 = select(ScrollORM.qty).where(
                ScrollORM.player_id == p1.id,
                ScrollORM.scroll_id == "weapon_scroll:regular",
            )
            stmt_p2 = select(ScrollORM.qty).where(
                ScrollORM.player_id == p2.id,
                ScrollORM.scroll_id == "weapon_scroll:regular",
            )
            qty_p1 = (await uow.session.execute(stmt_p1)).scalar_one()
            qty_p2 = (await uow.session.execute(stmt_p2)).scalar_one()
        assert qty_p1 == 2
        assert qty_p2 == 5
