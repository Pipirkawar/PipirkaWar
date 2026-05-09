"""Integration-тесты `SqlAlchemyItemRepository` (Спринт 3.4-B, B.4).

Покрытие:
* round-trip `add → get` для всех 8 слотов × 3 категорий
  (`weapon`/`armor`/`jewelry`) с `enchant_level=0` по умолчанию;
* `update_enchant_level(...)` — успех + промах (`ItemNotFoundError`);
* `get(...)` — промах (`ItemNotFoundError`);
* legacy-record (прямой SQL без `enchant_level`) → `get` отдаёт
  `Item(enchant_level=0)` (доказывает `server_default`-backfill);
* idempotency повторного `update_enchant_level(...)` × 2;
* `add(...)` дважды на одну пару `(player_id, item_id)` →
  `DomainIntegrityError` (composite PK conflict);
* `add(...)` с неизвестным `item_id` → `DomainIntegrityError`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from pipirik_wars.domain.balance.config import Slot
from pipirik_wars.domain.inventory import (
    ItemCategory,
    ItemNotFoundError,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyItemRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError
from tests.fakes import FakeBalanceConfig
from tests.unit.domain.balance.factories import build_valid_balance

NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)

# 8 слотов × 1 запись на слот — для round-trip-теста.
_SLOT_TO_CATEGORY: dict[Slot, ItemCategory] = {
    Slot.HAT: ItemCategory.ARMOR,
    Slot.BODY: ItemCategory.ARMOR,
    Slot.LEGS: ItemCategory.ARMOR,
    Slot.BOOTS: ItemCategory.ARMOR,
    Slot.RING: ItemCategory.JEWELRY,
    Slot.CHAIN: ItemCategory.JEWELRY,
    Slot.RIGHT_HAND: ItemCategory.WEAPON,
    Slot.LEFT_HAND: ItemCategory.WEAPON,
}


def _item_id_for(slot: Slot) -> str:
    """Каталожный id из `_build_valid_items_catalog` (всегда `_test_1` есть)."""
    return f"item.{slot.value}.test_1"


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _make_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyItemRepository:
    return SqlAlchemyItemRepository(
        uow=uow,
        balance=FakeBalanceConfig(build_valid_balance()),
    )


class TestSqlAlchemyItemRepositoryRoundTrip:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("slot", list(Slot))
    async def test_add_then_get_roundtrip_for_all_slots(
        self,
        uow: SqlAlchemyUnitOfWork,
        slot: Slot,
    ) -> None:
        """`add → get` восстанавливает агрегат с правильной категорией."""
        player = await _seed_player(uow, tg_id=hash(slot) & 0xFFFF)
        assert player.id is not None
        repo = _make_repo(uow)
        item_id = _item_id_for(slot)
        expected_category = _SLOT_TO_CATEGORY[slot]

        async with uow:
            added = await repo.add(player_id=player.id, item_id=item_id, now=NOW)
        assert added.id == item_id
        assert added.category is expected_category
        assert added.enchant_level == 0

        async with uow:
            loaded = await repo.get(player_id=player.id, item_id=item_id)
        assert loaded.id == item_id
        assert loaded.category is expected_category
        assert loaded.enchant_level == 0
        assert loaded == added

    @pytest.mark.asyncio
    async def test_default_enchant_level_zero(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Только что добавленный предмет имеет `enchant_level = 0`."""
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(player_id=player.id, item_id="item.hat.test_1", now=NOW)
            loaded = await repo.get(player_id=player.id, item_id="item.hat.test_1")
        assert loaded.enchant_level == 0


class TestSqlAlchemyItemRepositoryUpdate:
    @pytest.mark.asyncio
    async def test_update_enchant_level_persists(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=43)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                item_id="item.right_hand.test_1",
                now=NOW,
            )
            updated = await repo.update_enchant_level(
                player_id=player.id,
                item_id="item.right_hand.test_1",
                new_level=15,
            )
        assert updated.enchant_level == 15
        assert updated.category is ItemCategory.WEAPON

        async with uow:
            loaded = await repo.get(
                player_id=player.id,
                item_id="item.right_hand.test_1",
            )
        assert loaded.enchant_level == 15

    @pytest.mark.asyncio
    async def test_update_enchant_level_idempotent_same_value(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Повторный `update(level=5)` × 2 → `enchant_level == 5`, без ошибки."""
        player = await _seed_player(uow, tg_id=44)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(player_id=player.id, item_id="item.body.test_1", now=NOW)

        async with uow:
            await repo.update_enchant_level(
                player_id=player.id,
                item_id="item.body.test_1",
                new_level=5,
            )
        async with uow:
            again = await repo.update_enchant_level(
                player_id=player.id,
                item_id="item.body.test_1",
                new_level=5,
            )
        assert again.enchant_level == 5

    @pytest.mark.asyncio
    async def test_update_enchant_level_not_found(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=45)
        assert player.id is not None
        repo = _make_repo(uow)

        with pytest.raises(ItemNotFoundError) as exc_info:
            async with uow:
                await repo.update_enchant_level(
                    player_id=player.id,
                    item_id="item.hat.test_1",
                    new_level=5,
                )
        assert exc_info.value.player_id == player.id
        assert exc_info.value.item_id == "item.hat.test_1"


class TestSqlAlchemyItemRepositoryGetMiss:
    @pytest.mark.asyncio
    async def test_get_raises_item_not_found(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=46)
        assert player.id is not None
        repo = _make_repo(uow)

        with pytest.raises(ItemNotFoundError) as exc_info:
            async with uow:
                await repo.get(player_id=player.id, item_id="item.hat.test_1")
        assert exc_info.value.player_id == player.id
        assert exc_info.value.item_id == "item.hat.test_1"

    @pytest.mark.asyncio
    async def test_get_other_players_item_raises_not_found(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Изоляция: предмет игрока A не виден игроку B."""
        player_a = await _seed_player(uow, tg_id=100)
        player_b = await _seed_player(uow, tg_id=101)
        assert player_a.id is not None
        assert player_b.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player_a.id,
                item_id="item.hat.test_1",
                now=NOW,
            )

        with pytest.raises(ItemNotFoundError):
            async with uow:
                await repo.get(player_id=player_b.id, item_id="item.hat.test_1")


class TestSqlAlchemyItemRepositoryAddErrors:
    @pytest.mark.asyncio
    async def test_add_unknown_item_id_raises_integrity_error(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`item_id` вне каталога → `DomainIntegrityError`."""
        player = await _seed_player(uow, tg_id=47)
        assert player.id is not None
        repo = _make_repo(uow)

        with pytest.raises(DomainIntegrityError):
            async with uow:
                await repo.add(
                    player_id=player.id,
                    item_id="item.unknown.fake_999",
                    now=NOW,
                )

    @pytest.mark.asyncio
    async def test_add_duplicate_pk_raises_integrity_error(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Повторный `add` той же `(player_id, item_id)` → `DomainIntegrityError` (PK conflict)."""
        player = await _seed_player(uow, tg_id=48)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                item_id="item.hat.test_1",
                now=NOW,
            )

        with pytest.raises(DomainIntegrityError):
            async with uow:
                await repo.add(
                    player_id=player.id,
                    item_id="item.hat.test_1",
                    now=NOW,
                )


class TestSqlAlchemyItemRepositoryServerDefault:
    @pytest.mark.asyncio
    async def test_legacy_record_without_enchant_level_reads_zero(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Прямой `INSERT` без `enchant_level` → `get` отдаёт `Item(enchant_level=0)`.

        Доказывает, что `server_default='0'` корректно заполняет
        backfill для legacy-предметов (т.е. для строк, добавленных
        в обход ORM-а — например, миграциями или админскими скриптами).
        """
        player = await _seed_player(uow, tg_id=49)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await uow.session.execute(
                text(
                    "INSERT INTO items (player_id, item_id, acquired_at) "
                    "VALUES (:player_id, :item_id, :acquired_at)"
                ),
                {
                    "player_id": player.id,
                    "item_id": "item.legs.test_1",
                    "acquired_at": NOW.isoformat(),
                },
            )

        async with uow:
            loaded = await repo.get(player_id=player.id, item_id="item.legs.test_1")
        assert loaded.enchant_level == 0
        assert loaded.category is ItemCategory.ARMOR


class TestSqlAlchemyItemRepositoryListByPlayer:
    """Тесты `list_by_player` (Спринт 3.4-D, D.½)."""

    @pytest.mark.asyncio
    async def test_list_by_player_returns_empty_for_no_items(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Игрок без предметов → пустой кортеж, без ошибки."""
        player = await _seed_player(uow, tg_id=50)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            items = await repo.list_by_player(player_id=player.id)
        assert items == ()

    @pytest.mark.asyncio
    async def test_list_by_player_returns_all_items(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`add` 3 предметов → `list_by_player` возвращает их все."""
        player = await _seed_player(uow, tg_id=51)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(
                player_id=player.id,
                item_id="item.right_hand.test_1",
                now=datetime(2026, 1, 1, tzinfo=UTC),
            )
            await repo.add(
                player_id=player.id,
                item_id="item.body.test_1",
                now=datetime(2026, 1, 2, tzinfo=UTC),
            )
            await repo.add(
                player_id=player.id,
                item_id="item.ring.test_1",
                now=datetime(2026, 1, 3, tzinfo=UTC),
            )
            await repo.update_enchant_level(
                player_id=player.id,
                item_id="item.body.test_1",
                new_level=7,
            )

        async with uow:
            items = await repo.list_by_player(player_id=player.id)

        # ASC по acquired_at: weapon → armor → jewelry.
        assert len(items) == 3
        assert items[0].id == "item.right_hand.test_1"
        assert items[0].category is ItemCategory.WEAPON
        assert items[0].enchant_level == 0
        assert items[1].id == "item.body.test_1"
        assert items[1].category is ItemCategory.ARMOR
        assert items[1].enchant_level == 7
        assert items[2].id == "item.ring.test_1"
        assert items[2].category is ItemCategory.JEWELRY
        assert items[2].enchant_level == 0

    @pytest.mark.asyncio
    async def test_list_by_player_isolates_between_players(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Предметы одного игрока не попадают в листинг другого."""
        alice = await _seed_player(uow, tg_id=52)
        bob = await _seed_player(uow, tg_id=53)
        assert alice.id is not None and bob.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(player_id=alice.id, item_id="item.hat.test_1", now=NOW)
            await repo.add(player_id=bob.id, item_id="item.body.test_1", now=NOW)

        async with uow:
            alice_items = await repo.list_by_player(player_id=alice.id)
            bob_items = await repo.list_by_player(player_id=bob.id)

        assert len(alice_items) == 1
        assert alice_items[0].id == "item.hat.test_1"
        assert len(bob_items) == 1
        assert bob_items[0].id == "item.body.test_1"

    @pytest.mark.asyncio
    async def test_list_by_player_deterministic_order(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """При равных `acquired_at` сортировка по `item_id ASC`."""
        player = await _seed_player(uow, tg_id=54)
        assert player.id is not None
        repo = _make_repo(uow)
        same_ts = datetime(2026, 1, 1, tzinfo=UTC)

        async with uow:
            # Добавляем «не в алфавитном порядке».
            await repo.add(player_id=player.id, item_id="item.ring.test_1", now=same_ts)
            await repo.add(player_id=player.id, item_id="item.body.test_1", now=same_ts)
            await repo.add(player_id=player.id, item_id="item.hat.test_1", now=same_ts)

        async with uow:
            items = await repo.list_by_player(player_id=player.id)

        # ASC по item_id при равном acquired_at: body < hat < ring.
        item_ids = [i.id for i in items]
        assert item_ids == ["item.body.test_1", "item.hat.test_1", "item.ring.test_1"]
