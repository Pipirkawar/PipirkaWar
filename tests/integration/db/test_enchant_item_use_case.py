"""Integration-тесты `EnchantItem` use-case через realDB (Спринт 3.4-C, C.7).

Сценарии:
* round-trip success (`+0 → +1`) — `Item.enchant_level` обновлён в БД,
  скролл списан (`qty -= 1`), audit-запись `ITEM_ENCHANT_ATTEMPT` есть;
* destroy-исход (`+10 → DESTROY`) — строка `items` удалена физически;
* idempotency через realDB — повторный вызов с тем же ключом → no-op
  (qty скролла не меняется, audit-записи не дублируются);
* trip-wire через realDB — после 10 ITEM_ENCHANT_ATTEMPT-записей с
  `success=True` на тире `+18 → +25`, 11-й success на `+22` → запись
  `ENCHANT_ANOMALY`.

Используются реальные SqlAlchemy-репозитории
(`SqlAlchemyItemRepository`, `SqlAlchemyScrollRepository`,
`SqlAlchemyEnchantHistoryReader`), реальный
`SqlAlchemyAuditLogger` и `SqlAlchemyIdempotencyService`. Балансовый
конфиг — `FakeBalanceConfig(build_valid_balance())`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypeVar

import pytest
from sqlalchemy import select

from pipirik_wars.application.inventory import EnchantItem
from pipirik_wars.domain.inventory import (
    BlessedEnchantOutcome,
    ItemNotFoundError,
    RegularEnchantOutcome,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.domain.shared.ports import AuditEntry, AuditSource, IRandom
from pipirik_wars.domain.shared.ports.audit import AuditAction
from pipirik_wars.infrastructure.db.models import AuditLogORM, ScrollORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyEnchantHistoryReader,
    SqlAlchemyItemRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemyScrollRepository,
)
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from tests.fakes import FakeBalanceConfig, FakeClock
from tests.unit.domain.balance.factories import build_valid_balance

NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
_ITEM_ID = "item.right_hand.test_1"
_SCROLL_REGULAR = "weapon_scroll:regular"
_SCROLL_BLESSED = "weapon_scroll:blessed"


T = TypeVar("T")


class _RiggedRandom(IRandom):
    """Тот же RNG, что в юнит-тестах: возвращает заранее поставленные исходы."""

    __slots__ = ("_queue",)

    def __init__(self, *, outcomes: Sequence[object]) -> None:
        self._queue: list[object] = list(outcomes)

    def randint(self, low: int, high: int) -> int:
        raise AssertionError("RiggedRandom.randint not expected")

    def uniform(self, low: float, high: float) -> float:
        raise AssertionError("RiggedRandom.uniform not expected")

    def choice(self, items: Sequence[T]) -> T:
        raise AssertionError("RiggedRandom.choice not expected")

    def weighted_choice(self, items: Sequence[T], weights: Sequence[int]) -> T:
        if not self._queue:
            raise AssertionError("RiggedRandom: queue exhausted")
        item = self._queue.pop(0)
        return item  # type: ignore[return-value]

    def deterministic_uint(self, seed: str, modulo: int) -> int:
        raise AssertionError("RiggedRandom.deterministic_uint not expected")

    def shuffle(self, items: Sequence[T]) -> tuple[T, ...]:
        raise AssertionError("RiggedRandom.shuffle not expected")


# ────────────────────────────── builders ──────────────────────────────


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _make_use_case(
    uow: SqlAlchemyUnitOfWork,
    *,
    rigged_outcomes: Sequence[object] = (),
) -> EnchantItem:
    balance = FakeBalanceConfig(build_valid_balance())
    return EnchantItem(
        uow=uow,
        item_repo=SqlAlchemyItemRepository(uow=uow, balance=balance),
        scroll_repo=SqlAlchemyScrollRepository(uow=uow),
        balance=balance,
        random=_RiggedRandom(outcomes=rigged_outcomes),
        audit=SqlAlchemyAuditLogger(uow=uow),
        idempotency=SqlAlchemyIdempotencyService(uow=uow),
        clock=FakeClock(NOW),
        enchant_history=SqlAlchemyEnchantHistoryReader(uow=uow),
    )


async def _seed_item_at_level(
    uow: SqlAlchemyUnitOfWork,
    *,
    player_id: int,
    item_id: str,
    level: int,
) -> None:
    """Положить предмет в БД на нужном уровне (через repo + update)."""
    balance = FakeBalanceConfig(build_valid_balance())
    repo = SqlAlchemyItemRepository(uow=uow, balance=balance)
    async with uow:
        await repo.add(player_id=player_id, item_id=item_id, now=NOW)
        if level != 0:
            await repo.update_enchant_level(
                player_id=player_id,
                item_id=item_id,
                new_level=level,
            )


async def _seed_scroll(
    uow: SqlAlchemyUnitOfWork,
    *,
    player_id: int,
    scroll_id: str,
    qty: int,
) -> None:
    repo = SqlAlchemyScrollRepository(uow=uow)
    async with uow:
        await repo.add(player_id=player_id, scroll_id=scroll_id, qty=qty, now=NOW)


# ────────────────────────────── tests ──────────────────────────────


@pytest.mark.asyncio
async def test_round_trip_success_at_level_0(uow: SqlAlchemyUnitOfWork) -> None:
    """`+0 → +1`: предмет в БД обновлён, скролл списан, audit-запись есть."""
    player = await _seed_player(uow, tg_id=1001)
    assert player.id is not None
    await _seed_item_at_level(uow, player_id=player.id, item_id=_ITEM_ID, level=0)
    await _seed_scroll(uow, player_id=player.id, scroll_id=_SCROLL_REGULAR, qty=3)

    use_case = _make_use_case(uow)
    async with uow:
        result = await use_case(
            player_id=player.id,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR,
            idempotency_key="run-1",
        )

    assert result.outcome is RegularEnchantOutcome.SUCCESS
    assert result.old_level == 0
    assert result.new_level == 1
    assert result.idempotent is False
    assert result.item_destroyed is False

    # Item обновлён в БД.
    repo = SqlAlchemyItemRepository(
        uow=uow,
        balance=FakeBalanceConfig(build_valid_balance()),
    )
    async with uow:
        item = await repo.get(player_id=player.id, item_id=_ITEM_ID)
    assert item.enchant_level == 1

    # Скролл списан.
    async with uow:
        stmt = select(ScrollORM.qty).where(
            ScrollORM.player_id == player.id,
            ScrollORM.scroll_id == _SCROLL_REGULAR,
        )
        qty = (await uow.session.execute(stmt)).scalar_one()
    assert qty == 2

    # Audit-запись есть.
    async with uow:
        stmt2 = select(AuditLogORM).where(
            AuditLogORM.action == AuditAction.ITEM_ENCHANT_ATTEMPT.value,
            AuditLogORM.target_id == str(player.id),
        )
        rows = list((await uow.session.execute(stmt2)).scalars().all())
    assert len(rows) == 1
    assert rows[0].after is not None
    assert rows[0].after["outcome"] == "success"
    assert rows[0].after["new_level"] == 1


@pytest.mark.asyncio
async def test_destroy_outcome_deletes_item_row(uow: SqlAlchemyUnitOfWork) -> None:
    """`+10 → DESTROY`: строка `items` физически удалена."""
    player = await _seed_player(uow, tg_id=1002)
    assert player.id is not None
    await _seed_item_at_level(uow, player_id=player.id, item_id=_ITEM_ID, level=10)
    await _seed_scroll(uow, player_id=player.id, scroll_id=_SCROLL_REGULAR, qty=1)

    use_case = _make_use_case(
        uow,
        rigged_outcomes=[RegularEnchantOutcome.DESTROY],
    )
    async with uow:
        result = await use_case(
            player_id=player.id,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR,
            idempotency_key="destroy-1",
        )

    assert result.outcome is RegularEnchantOutcome.DESTROY
    assert result.item_destroyed is True
    assert result.new_level == 0

    # Item удалён.
    repo = SqlAlchemyItemRepository(
        uow=uow,
        balance=FakeBalanceConfig(build_valid_balance()),
    )
    with pytest.raises(ItemNotFoundError):
        async with uow:
            await repo.get(player_id=player.id, item_id=_ITEM_ID)


@pytest.mark.asyncio
async def test_idempotent_repeat_does_not_duplicate_side_effects(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    """Повторный вызов с тем же ключом → no-op: qty не меняется, аудит один."""
    player = await _seed_player(uow, tg_id=1003)
    assert player.id is not None
    await _seed_item_at_level(uow, player_id=player.id, item_id=_ITEM_ID, level=0)
    await _seed_scroll(uow, player_id=player.id, scroll_id=_SCROLL_REGULAR, qty=2)

    use_case = _make_use_case(uow)

    async with uow:
        result1 = await use_case(
            player_id=player.id,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR,
            idempotency_key="repeat-key",
        )
    assert result1.idempotent is False

    # qty после первого вызова.
    async with uow:
        stmt = select(ScrollORM.qty).where(
            ScrollORM.player_id == player.id,
            ScrollORM.scroll_id == _SCROLL_REGULAR,
        )
        qty_after_1 = (await uow.session.execute(stmt)).scalar_one()
    assert qty_after_1 == 1

    # Второй вызов — тот же ключ, no-op.
    async with uow:
        result2 = await use_case(
            player_id=player.id,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR,
            idempotency_key="repeat-key",
        )
    assert result2.idempotent is True

    # qty не изменилась — скролл НЕ списан повторно.
    async with uow:
        qty_after_2 = (await uow.session.execute(stmt)).scalar_one()
    assert qty_after_2 == 1

    # Audit-записей ровно одна (на первую попытку).
    async with uow:
        stmt2 = select(AuditLogORM).where(
            AuditLogORM.action == AuditAction.ITEM_ENCHANT_ATTEMPT.value,
            AuditLogORM.target_id == str(player.id),
        )
        rows = list((await uow.session.execute(stmt2)).scalars().all())
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_trip_wire_fires_after_10_consecutive_high_tier_successes(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    """11-я попытка-успех на `+22` после 10 успехов на `+18 → +25` →
    `ENCHANT_ANOMALY`-audit."""
    player = await _seed_player(uow, tg_id=1004)
    assert player.id is not None
    # Засеиваем предмет на +22 и blessed-скролл на +2 → +24 для каждой
    # из 11 попыток. (Полностью real-flow: 11 раз вызываем use-case.)
    await _seed_item_at_level(uow, player_id=player.id, item_id=_ITEM_ID, level=22)
    await _seed_scroll(uow, player_id=player.id, scroll_id=_SCROLL_BLESSED, qty=11)

    # 11 раз blessed успех с rigged SUCCESS_1 (всегда +1, не выходит за 25),
    # после чего возвращается на +22 для следующей попытки. Чтобы держать
    # уровень в [22, 25], после успеха каждый раз сбрасываем уровень.
    # Простоты ради — делаем 10 одиночных «фейковых» вызовов, которые
    # садят аудит-записи прямо в таблицу (имитация прошлых попыток),
    # затем 11-й — реальный use-case-вызов.
    audit = SqlAlchemyAuditLogger(uow=uow)

    async with uow:
        for i in range(10):
            await audit.record(
                AuditEntry(
                    occurred_at=NOW,
                    action=AuditAction.ITEM_ENCHANT_ATTEMPT,
                    actor_id=player.id,
                    target_kind="player",
                    target_id=str(player.id),
                    before=None,
                    after={
                        "item_id": _ITEM_ID,
                        "scroll_id": _SCROLL_BLESSED,
                        "outcome": "success_1",
                        "old_level": 22,
                        "new_level": 23,
                        "blessed": True,
                        "item_destroyed": False,
                        "item_dropped": False,
                        "success": True,
                    },
                    reason="",
                    source=AuditSource.UNKNOWN,
                    idempotency_key=f"seed:{i}",
                ),
            )

    # 11-я попытка через use-case — должна задетектить аномалию.
    use_case = _make_use_case(
        uow,
        rigged_outcomes=[BlessedEnchantOutcome.SUCCESS_1],
    )
    async with uow:
        result = await use_case(
            player_id=player.id,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_BLESSED,
            idempotency_key="anomaly-trigger",
        )

    assert result.anomaly_detected is True
    assert result.outcome is BlessedEnchantOutcome.SUCCESS_1

    # ENCHANT_ANOMALY-запись в БД.
    async with uow:
        stmt = select(AuditLogORM).where(
            AuditLogORM.action == AuditAction.ENCHANT_ANOMALY.value,
            AuditLogORM.target_id == str(player.id),
        )
        rows = list((await uow.session.execute(stmt)).scalars().all())
    assert len(rows) == 1
    assert rows[0].after == {
        "tier_min": 18,
        "tier_max": 25,
        "window_size": 10,
        "trigger_old_level": 22,
    }
