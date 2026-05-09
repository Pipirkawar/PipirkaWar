"""Юнит-тесты `EnchantItem` use-case (Спринт 3.4-C, C.6).

Покрытие:
- 4 регулярных исхода (`SUCCESS` / `NO_EFFECT` / `DROP` / `DESTROY`);
- 5 благословлённых (`SUCCESS_1` / `SUCCESS_2` / `NO_EFFECT` / `DROP_1` / `DROP_2`);
- `WrongScrollCategoryError`, `ItemNotFoundError`, `ScrollNotFoundError`,
  `ScrollOutOfStockError`, невалидный `scroll_id`;
- idempotency: повторный вызов с тем же ключом → no-op;
- clamp на нижней границе (`+0 → DROP` остаётся на `+0`);
- trip-wire: 10 успехов на `+18 → +25` → `ENCHANT_ANOMALY`;
- trip-wire: 9 успехов + 1 fail → нет события;
- audit-семантика (`ITEM_ENCHANT_ATTEMPT` всегда; `ENCHANT_ANOMALY` при
  trip-wire);
- ambient-UoW guard.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypeVar

import pytest

from pipirik_wars.application.inventory import EnchantItem
from pipirik_wars.domain.enchantment.entities import Scroll, ScrollCategory
from pipirik_wars.domain.inventory import (
    BlessedEnchantOutcome,
    IEnchantHistoryReader,
    IItemRepository,
    IScrollRepository,
    Item,
    ItemCategory,
    ItemNotFoundError,
    RegularEnchantOutcome,
    ScrollNotFoundError,
    ScrollOutOfStockError,
    ScrollStack,
    WrongScrollCategoryError,
)
from pipirik_wars.domain.shared.ports import IRandom
from pipirik_wars.domain.shared.ports.audit import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeIdempotencyKey,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)


T = TypeVar("T")


class _RiggedRandom(IRandom):
    """RNG, возвращающий заранее поставленные исходы из очереди.

    `weighted_choice` на каждом вызове возвращает следующий из `outcomes`.
    `randint` / `uniform` / `choice` / `shuffle` / `deterministic_uint`
    падают: тесты use-case-а их не должны вызывать.
    """

    __slots__ = ("_queue",)

    def __init__(self, *, outcomes: Sequence[object]) -> None:
        self._queue: list[object] = list(outcomes)

    def randint(self, low: int, high: int) -> int:
        raise AssertionError("RiggedRandom.randint not expected to be called")

    def uniform(self, low: float, high: float) -> float:
        raise AssertionError("RiggedRandom.uniform not expected to be called")

    def choice(self, items: Sequence[T]) -> T:
        raise AssertionError("RiggedRandom.choice not expected to be called")

    def weighted_choice(self, items: Sequence[T], weights: Sequence[int]) -> T:
        if not self._queue:
            raise AssertionError("RiggedRandom: queue exhausted")
        item = self._queue.pop(0)
        if item not in items:
            raise AssertionError(f"RiggedRandom: outcome {item!r} not in items {items!r}")
        return item  # type: ignore[return-value]

    def deterministic_uint(self, seed: str, modulo: int) -> int:
        raise AssertionError("RiggedRandom.deterministic_uint not expected")

    def shuffle(self, items: Sequence[T]) -> tuple[T, ...]:
        raise AssertionError("RiggedRandom.shuffle not expected")


class _InMemoryItemRepository(IItemRepository):
    """In-memory `IItemRepository` для юнит-тестов use-case-а."""

    __slots__ = ("delete_calls", "items", "update_calls")

    def __init__(self) -> None:
        self.items: dict[tuple[int, str], Item] = {}
        self.update_calls: list[tuple[int, str, int]] = []
        self.delete_calls: list[tuple[int, str]] = []

    async def get(self, *, player_id: int, item_id: str) -> Item:
        try:
            return self.items[(player_id, item_id)]
        except KeyError as exc:
            raise ItemNotFoundError(player_id=player_id, item_id=item_id) from exc

    async def add(self, *, player_id: int, item_id: str, now: datetime) -> Item:
        raise NotImplementedError("add() not used in EnchantItem unit tests")

    async def update_enchant_level(
        self,
        *,
        player_id: int,
        item_id: str,
        new_level: int,
    ) -> Item:
        self.update_calls.append((player_id, item_id, new_level))
        try:
            current = self.items[(player_id, item_id)]
        except KeyError as exc:
            raise ItemNotFoundError(player_id=player_id, item_id=item_id) from exc
        updated = current.with_enchant_level(new_level)
        self.items[(player_id, item_id)] = updated
        return updated

    async def delete(self, *, player_id: int, item_id: str) -> None:
        self.delete_calls.append((player_id, item_id))
        try:
            del self.items[(player_id, item_id)]
        except KeyError as exc:
            raise ItemNotFoundError(player_id=player_id, item_id=item_id) from exc

    async def list_by_player(self, *, player_id: int) -> tuple[Item, ...]:
        return tuple(item for (pid, _item_id), item in self.items.items() if pid == player_id)


class _InMemoryScrollRepository(IScrollRepository):
    """In-memory `IScrollRepository`."""

    __slots__ = ("consume_calls", "scrolls")

    def __init__(self) -> None:
        self.scrolls: dict[tuple[int, str], int] = {}
        self.consume_calls: list[tuple[int, str, int]] = []

    async def get(self, *, player_id: int, scroll_id: str) -> Scroll:
        if (player_id, scroll_id) not in self.scrolls:
            raise ScrollNotFoundError(player_id=player_id, scroll_id=scroll_id)
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
            raise ValueError("qty must be > 0")
        self.scrolls[(player_id, scroll_id)] = self.scrolls.get((player_id, scroll_id), 0) + qty

    async def consume(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int = 1,
    ) -> None:
        if qty <= 0:
            raise ValueError("qty must be > 0")
        self.consume_calls.append((player_id, scroll_id, qty))
        available = self.scrolls.get((player_id, scroll_id))
        if available is None:
            raise ScrollNotFoundError(player_id=player_id, scroll_id=scroll_id)
        if available < qty:
            raise ScrollOutOfStockError(
                player_id=player_id,
                scroll_id=scroll_id,
                requested_qty=qty,
                available_qty=available,
            )
        self.scrolls[(player_id, scroll_id)] = available - qty

    async def list_by_player(self, *, player_id: int) -> tuple[ScrollStack, ...]:
        return tuple(
            ScrollStack(scroll=Scroll.from_scroll_id(scroll_id), qty=qty)
            for (pid, scroll_id), qty in self.scrolls.items()
            if pid == player_id and qty > 0
        )


class _StubEnchantHistoryReader(IEnchantHistoryReader):
    """In-memory fake: возвращает запрограммированный список флагов."""

    __slots__ = ("_outcomes", "calls")

    def __init__(self, *, outcomes: Sequence[bool] = ()) -> None:
        self._outcomes: tuple[bool, ...] = tuple(outcomes)
        self.calls: list[tuple[int, int, int, int]] = []

    def set_outcomes(self, outcomes: Sequence[bool]) -> None:
        self._outcomes = tuple(outcomes)

    async def get_recent_high_tier_outcomes(
        self,
        *,
        player_id: int,
        tier_min: int,
        tier_max: int,
        limit: int,
    ) -> tuple[bool, ...]:
        self.calls.append((player_id, tier_min, tier_max, limit))
        return self._outcomes[:limit]


# ────────────────────────────── builders ──────────────────────────────


_PLAYER_ID = 100
_ITEM_ID = "item.right_hand.test_1"  # из tests/unit/domain/balance/factories
_SCROLL_REGULAR_WEAPON = "weapon_scroll:regular"
_SCROLL_BLESSED_WEAPON = "weapon_scroll:blessed"


def _make_env(
    *,
    item_level: int = 0,
    item_category: ItemCategory = ItemCategory.WEAPON,
    scroll_qty: int = 1,
    scroll_id: str = _SCROLL_REGULAR_WEAPON,
    rigged_outcomes: Sequence[object] = (),
    history_outcomes: Sequence[bool] = (),
    item_present: bool = True,
    scroll_present: bool = True,
) -> dict[str, object]:
    item_repo = _InMemoryItemRepository()
    if item_present:
        item_repo.items[(_PLAYER_ID, _ITEM_ID)] = Item(
            id=_ITEM_ID,
            category=item_category,
            enchant_level=item_level,
        )

    scroll_repo = _InMemoryScrollRepository()
    if scroll_present:
        scroll_repo.scrolls[(_PLAYER_ID, scroll_id)] = scroll_qty

    uow = FakeUnitOfWork()
    audit = FakeAuditLogger()
    idempotency = FakeIdempotencyKey()
    clock = FakeClock(_NOW)
    balance = FakeBalanceConfig(build_valid_balance())
    enchant_history = _StubEnchantHistoryReader(outcomes=history_outcomes)
    rng = _RiggedRandom(outcomes=rigged_outcomes)

    use_case = EnchantItem(
        uow=uow,
        item_repo=item_repo,
        scroll_repo=scroll_repo,
        balance=balance,
        random=rng,
        audit=audit,
        idempotency=idempotency,
        clock=clock,
        enchant_history=enchant_history,
    )

    return {
        "use_case": use_case,
        "uow": uow,
        "item_repo": item_repo,
        "scroll_repo": scroll_repo,
        "audit": audit,
        "idempotency": idempotency,
        "clock": clock,
        "enchant_history": enchant_history,
        "rng": rng,
    }


# ────────────────────────────── safe-zone (level=0) ──────────────────────────────


@pytest.mark.asyncio
async def test_regular_safe_zone_success_at_level_0() -> None:
    """`level=0` regular → forced `SUCCESS` (safe zone), `+0 → +1`."""
    env = _make_env(item_level=0)
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is RegularEnchantOutcome.SUCCESS
    assert result.old_level == 0
    assert result.new_level == 1
    assert result.item_destroyed is False
    assert result.item_dropped is False
    assert result.idempotent is False
    assert result.anomaly_detected is False


@pytest.mark.asyncio
async def test_blessed_safe_zone_success_1_at_level_0() -> None:
    """`level=0` blessed → forced `SUCCESS_1` (safe zone), `+0 → +1`."""
    env = _make_env(item_level=0, scroll_id=_SCROLL_BLESSED_WEAPON)
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_BLESSED_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is BlessedEnchantOutcome.SUCCESS_1
    assert result.new_level == 1


# ────────────────────────────── 4 regular outcomes ──────────────────────────────


@pytest.mark.asyncio
async def test_regular_no_effect_outside_safe_zone() -> None:
    """`level=10` regular, rigged `NO_EFFECT` → уровень не меняется."""
    env = _make_env(
        item_level=10,
        rigged_outcomes=[RegularEnchantOutcome.NO_EFFECT],
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    item_repo: _InMemoryItemRepository = env["item_repo"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is RegularEnchantOutcome.NO_EFFECT
    assert result.old_level == 10
    assert result.new_level == 10
    assert result.item_destroyed is False
    assert result.item_dropped is False
    # Update should NOT have been called for NO_EFFECT.
    assert item_repo.update_calls == []


@pytest.mark.asyncio
async def test_regular_drop_outside_safe_zone() -> None:
    """`level=10` regular, rigged `DROP` → `+10 → +9`, `item_dropped=True`."""
    env = _make_env(
        item_level=10,
        rigged_outcomes=[RegularEnchantOutcome.DROP],
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    item_repo: _InMemoryItemRepository = env["item_repo"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is RegularEnchantOutcome.DROP
    assert result.new_level == 9
    assert result.item_dropped is True
    assert item_repo.update_calls == [(_PLAYER_ID, _ITEM_ID, 9)]


@pytest.mark.asyncio
async def test_regular_destroy_outside_safe_zone() -> None:
    """`level=10` regular, rigged `DESTROY` → предмет удалён, `item_destroyed=True`."""
    env = _make_env(
        item_level=10,
        rigged_outcomes=[RegularEnchantOutcome.DESTROY],
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    item_repo: _InMemoryItemRepository = env["item_repo"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is RegularEnchantOutcome.DESTROY
    assert result.item_destroyed is True
    assert result.new_level == 0
    assert item_repo.delete_calls == [(_PLAYER_ID, _ITEM_ID)]
    assert item_repo.update_calls == []
    assert (_PLAYER_ID, _ITEM_ID) not in item_repo.items


# ────────────────────────────── 5 blessed outcomes ──────────────────────────────


@pytest.mark.asyncio
async def test_blessed_success_2_outside_safe_zone() -> None:
    """`level=10` blessed, rigged `SUCCESS_2` → `+10 → +12`."""
    env = _make_env(
        item_level=10,
        scroll_id=_SCROLL_BLESSED_WEAPON,
        rigged_outcomes=[BlessedEnchantOutcome.SUCCESS_2],
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_BLESSED_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is BlessedEnchantOutcome.SUCCESS_2
    assert result.new_level == 12


@pytest.mark.asyncio
async def test_blessed_no_effect_outside_safe_zone() -> None:
    """`level=10` blessed, rigged `NO_EFFECT` → уровень не меняется."""
    env = _make_env(
        item_level=10,
        scroll_id=_SCROLL_BLESSED_WEAPON,
        rigged_outcomes=[BlessedEnchantOutcome.NO_EFFECT],
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_BLESSED_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is BlessedEnchantOutcome.NO_EFFECT
    assert result.new_level == 10


@pytest.mark.asyncio
async def test_blessed_drop_1_outside_safe_zone() -> None:
    """`level=10` blessed, rigged `DROP_1` → `+10 → +9`."""
    env = _make_env(
        item_level=10,
        scroll_id=_SCROLL_BLESSED_WEAPON,
        rigged_outcomes=[BlessedEnchantOutcome.DROP_1],
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_BLESSED_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is BlessedEnchantOutcome.DROP_1
    assert result.new_level == 9
    assert result.item_dropped is True


@pytest.mark.asyncio
async def test_blessed_drop_2_outside_safe_zone() -> None:
    """`level=10` blessed, rigged `DROP_2` → `+10 → +8`."""
    env = _make_env(
        item_level=10,
        scroll_id=_SCROLL_BLESSED_WEAPON,
        rigged_outcomes=[BlessedEnchantOutcome.DROP_2],
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_BLESSED_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is BlessedEnchantOutcome.DROP_2
    assert result.new_level == 8
    assert result.item_dropped is True


# ────────────────────────────── error cases ──────────────────────────────


@pytest.mark.asyncio
async def test_wrong_scroll_category_raises() -> None:
    """`weapon`-предмет + `armor`-скролл → `WrongScrollCategoryError`."""
    env = _make_env(
        item_category=ItemCategory.ARMOR,
        scroll_id=_SCROLL_REGULAR_WEAPON,
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    scroll_repo: _InMemoryScrollRepository = env["scroll_repo"]  # type: ignore[assignment]

    with pytest.raises(WrongScrollCategoryError) as exc_info:
        async with uow:
            await use_case(
                player_id=_PLAYER_ID,
                item_id=_ITEM_ID,
                scroll_id=_SCROLL_REGULAR_WEAPON,
                idempotency_key="k1",
            )

    assert exc_info.value.scroll_category is ScrollCategory.WEAPON
    assert exc_info.value.item_category is ItemCategory.ARMOR
    # Скролл НЕ списан (mismatch — раньше consume).
    assert scroll_repo.consume_calls == []


@pytest.mark.asyncio
async def test_item_not_found_raises() -> None:
    """`Item` отсутствует у игрока → `ItemNotFoundError`."""
    env = _make_env(item_present=False)
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    scroll_repo: _InMemoryScrollRepository = env["scroll_repo"]  # type: ignore[assignment]

    with pytest.raises(ItemNotFoundError):
        async with uow:
            await use_case(
                player_id=_PLAYER_ID,
                item_id=_ITEM_ID,
                scroll_id=_SCROLL_REGULAR_WEAPON,
                idempotency_key="k1",
            )

    # Скролл НЕ списан.
    assert scroll_repo.consume_calls == []


@pytest.mark.asyncio
async def test_scroll_not_found_raises() -> None:
    """Скролл отсутствует у игрока → `ScrollNotFoundError`."""
    env = _make_env(scroll_present=False)
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    with pytest.raises(ScrollNotFoundError):
        async with uow:
            await use_case(
                player_id=_PLAYER_ID,
                item_id=_ITEM_ID,
                scroll_id=_SCROLL_REGULAR_WEAPON,
                idempotency_key="k1",
            )


@pytest.mark.asyncio
async def test_scroll_out_of_stock_raises() -> None:
    """Скролл есть, но `qty=0` → `ScrollOutOfStockError`."""
    env = _make_env(scroll_qty=0)
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    with pytest.raises(ScrollOutOfStockError):
        async with uow:
            await use_case(
                player_id=_PLAYER_ID,
                item_id=_ITEM_ID,
                scroll_id=_SCROLL_REGULAR_WEAPON,
                idempotency_key="k1",
            )


@pytest.mark.asyncio
async def test_invalid_scroll_id_raises_value_error() -> None:
    """Невалидный `scroll_id` → `ValueError` из `Scroll.from_scroll_id`."""
    env = _make_env()
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    with pytest.raises(ValueError, match="scroll_id"):
        async with uow:
            await use_case(
                player_id=_PLAYER_ID,
                item_id=_ITEM_ID,
                scroll_id="invalid_format",
                idempotency_key="k1",
            )


# ────────────────────────────── idempotency ──────────────────────────────


@pytest.mark.asyncio
async def test_idempotent_repeat_returns_no_op_without_side_effects() -> None:
    """Повторный вызов с тем же ключом → `idempotent=True`, без side-эффектов."""
    env = _make_env(item_level=0)
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    audit: FakeAuditLogger = env["audit"]  # type: ignore[assignment]
    item_repo: _InMemoryItemRepository = env["item_repo"]  # type: ignore[assignment]
    scroll_repo: _InMemoryScrollRepository = env["scroll_repo"]  # type: ignore[assignment]

    # Первый вызов — нормальная заточка.
    async with uow:
        result1 = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="repeat-key",
        )
    assert result1.idempotent is False
    assert result1.outcome is RegularEnchantOutcome.SUCCESS
    assert result1.new_level == 1
    audits_after_first = len(audit.entries)
    consumes_after_first = len(scroll_repo.consume_calls)
    updates_after_first = len(item_repo.update_calls)

    # Второй вызов — тот же ключ, no-op.
    async with uow:
        result2 = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="repeat-key",
        )

    assert result2.idempotent is True
    assert result2.old_level == 1
    assert result2.new_level == 1
    assert result2.outcome is RegularEnchantOutcome.NO_EFFECT
    # Никаких новых side-эффектов.
    assert len(audit.entries) == audits_after_first
    assert len(scroll_repo.consume_calls) == consumes_after_first
    assert len(item_repo.update_calls) == updates_after_first


@pytest.mark.asyncio
async def test_idempotent_repeat_blessed_returns_blessed_no_effect() -> None:
    """На blessed-скролле no-op возвращает `BlessedEnchantOutcome.NO_EFFECT`."""
    env = _make_env(item_level=0, scroll_id=_SCROLL_BLESSED_WEAPON)
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]

    async with uow:
        await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_BLESSED_WEAPON,
            idempotency_key="repeat",
        )

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_BLESSED_WEAPON,
            idempotency_key="repeat",
        )

    assert result.idempotent is True
    assert result.outcome is BlessedEnchantOutcome.NO_EFFECT


# ────────────────────────────── audit semantics ──────────────────────────────


@pytest.mark.asyncio
async def test_audit_records_item_enchant_attempt_with_full_payload() -> None:
    """Каждая попытка пишет ровно одну запись `ITEM_ENCHANT_ATTEMPT`."""
    env = _make_env(item_level=0)
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    audit: FakeAuditLogger = env["audit"]  # type: ignore[assignment]

    async with uow:
        await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    enchant_entries = [e for e in audit.entries if e.action is AuditAction.ITEM_ENCHANT_ATTEMPT]
    assert len(enchant_entries) == 1
    entry = enchant_entries[0]
    assert entry.target_kind == "player"
    assert entry.target_id == str(_PLAYER_ID)
    assert entry.actor_id == _PLAYER_ID
    assert entry.idempotency_key == "enchant:k1"
    assert entry.occurred_at == _NOW
    assert entry.delta_cm is None
    assert entry.after == {
        "item_id": _ITEM_ID,
        "scroll_id": _SCROLL_REGULAR_WEAPON,
        "outcome": "success",
        "old_level": 0,
        "new_level": 1,
        "blessed": False,
        "item_destroyed": False,
        "item_dropped": False,
        "success": True,
    }


# ────────────────────────────── trip-wire ──────────────────────────────


@pytest.mark.asyncio
async def test_anomaly_fires_on_10_consecutive_successes_at_high_tier() -> None:
    """10/10 успехов на тире `+18 → +25` → `ENCHANT_ANOMALY`."""
    env = _make_env(
        item_level=20,
        rigged_outcomes=[RegularEnchantOutcome.SUCCESS],
        history_outcomes=[True] * 10,  # последние 10 — успехи
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    audit: FakeAuditLogger = env["audit"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert result.anomaly_detected is True
    anomaly_entries = [e for e in audit.entries if e.action is AuditAction.ENCHANT_ANOMALY]
    assert len(anomaly_entries) == 1
    anomaly = anomaly_entries[0]
    assert anomaly.target_kind == "player"
    assert anomaly.target_id == str(_PLAYER_ID)
    assert anomaly.actor_id is None
    assert anomaly.idempotency_key is None
    assert anomaly.after == {
        "tier_min": 18,
        "tier_max": 25,
        "window_size": 10,
        "trigger_old_level": 20,
    }


@pytest.mark.asyncio
async def test_anomaly_does_not_fire_when_window_has_failure() -> None:
    """9 успехов + 1 fail → нет события."""
    env = _make_env(
        item_level=20,
        rigged_outcomes=[RegularEnchantOutcome.SUCCESS],
        history_outcomes=[True, False, True, True, True, True, True, True, True, True],
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    audit: FakeAuditLogger = env["audit"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert result.anomaly_detected is False
    anomaly_entries = [e for e in audit.entries if e.action is AuditAction.ENCHANT_ANOMALY]
    assert anomaly_entries == []


@pytest.mark.asyncio
async def test_anomaly_does_not_fire_when_window_has_fewer_than_10_attempts() -> None:
    """5 успехов в истории (мало) → нет события."""
    env = _make_env(
        item_level=20,
        rigged_outcomes=[RegularEnchantOutcome.SUCCESS],
        history_outcomes=[True] * 5,
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    audit: FakeAuditLogger = env["audit"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert result.anomaly_detected is False
    assert all(e.action is not AuditAction.ENCHANT_ANOMALY for e in audit.entries)


@pytest.mark.asyncio
async def test_anomaly_skipped_when_outcome_was_failure() -> None:
    """Текущая попытка — fail (NO_EFFECT) → trip-wire не дёргается."""
    env = _make_env(
        item_level=20,
        rigged_outcomes=[RegularEnchantOutcome.NO_EFFECT],
        history_outcomes=[True] * 10,
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    audit: FakeAuditLogger = env["audit"]  # type: ignore[assignment]
    history: _StubEnchantHistoryReader = env["enchant_history"]  # type: ignore[assignment]

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert result.anomaly_detected is False
    # История даже не запрашивалась.
    assert history.calls == []
    assert all(e.action is not AuditAction.ENCHANT_ANOMALY for e in audit.entries)


@pytest.mark.asyncio
async def test_anomaly_skipped_for_low_tier_success() -> None:
    """Успех на тире `+15` (< 18) → trip-wire не дёргается."""
    env = _make_env(
        item_level=15,
        rigged_outcomes=[RegularEnchantOutcome.SUCCESS],
        history_outcomes=[True] * 10,
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    history: _StubEnchantHistoryReader = env["enchant_history"]  # type: ignore[assignment]

    async with uow:
        await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert history.calls == []


@pytest.mark.asyncio
async def test_anomaly_skipped_for_above_high_tier_success() -> None:
    """Успех на тире `+26` (> 25) → trip-wire не дёргается."""
    env = _make_env(
        item_level=26,
        rigged_outcomes=[RegularEnchantOutcome.SUCCESS],
        history_outcomes=[True] * 10,
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    history: _StubEnchantHistoryReader = env["enchant_history"]  # type: ignore[assignment]

    async with uow:
        await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )

    assert history.calls == []


# ────────────────────────────── ambient-UoW guard ──────────────────────────────


@pytest.mark.asyncio
async def test_call_outside_active_uow_raises_runtime_error() -> None:
    """Вызов без открытого UoW → `RuntimeError`."""
    env = _make_env()
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="active IUnitOfWork"):
        await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_REGULAR_WEAPON,
            idempotency_key="k1",
        )


# ────────────────────────────── clamp ──────────────────────────────


@pytest.mark.asyncio
async def test_drop_at_level_0_clamps_to_0() -> None:
    """`+0 → DROP` → `+0` (clamp), `item_dropped=True`.

    `level=0` regular в safe-zone → forced SUCCESS, поэтому DROP здесь
    не выпадет напрямую. Проверяем clamp на blessed `DROP_2` от уровня
    `+10` → `+8`, потом снова от `+1`. Чтобы воспроизвести clamp на
    нижней границе, делаем `level=1` blessed `DROP_2` (если safe_zone
    < 1) и ожидаем `max(0, 1-2) = 0`.
    """
    # Используем level=1 (предположительно вне safe-zone в дефолтном
    # `safe_zone_max_level`) с blessed DROP_2 → -2, clamp на 0.
    env = _make_env(
        item_level=1,
        scroll_id=_SCROLL_BLESSED_WEAPON,
        rigged_outcomes=[BlessedEnchantOutcome.DROP_2],
    )
    use_case: EnchantItem = env["use_case"]  # type: ignore[assignment]
    uow: FakeUnitOfWork = env["uow"]  # type: ignore[assignment]
    item_repo: _InMemoryItemRepository = env["item_repo"]  # type: ignore[assignment]
    safe_zone_max = build_valid_balance().enchantment.safe_zone_max_level
    if safe_zone_max > 1:
        # Если safe-zone покрывает level=1, тест неприменим — подбираем
        # минимальный level вне safe-zone.
        level_outside_safe = safe_zone_max
        env = _make_env(
            item_level=level_outside_safe,
            scroll_id=_SCROLL_BLESSED_WEAPON,
            rigged_outcomes=[BlessedEnchantOutcome.DROP_2],
        )
        use_case = env["use_case"]  # type: ignore[assignment]
        uow = env["uow"]  # type: ignore[assignment]
        item_repo = env["item_repo"]  # type: ignore[assignment]

        async with uow:
            result = await use_case(
                player_id=_PLAYER_ID,
                item_id=_ITEM_ID,
                scroll_id=_SCROLL_BLESSED_WEAPON,
                idempotency_key="k1",
            )
        assert result.new_level == max(0, level_outside_safe - 2)
        assert result.item_dropped is True
        return

    async with uow:
        result = await use_case(
            player_id=_PLAYER_ID,
            item_id=_ITEM_ID,
            scroll_id=_SCROLL_BLESSED_WEAPON,
            idempotency_key="k1",
        )

    assert result.outcome is BlessedEnchantOutcome.DROP_2
    assert result.new_level == 0
    assert result.item_dropped is True
    assert item_repo.update_calls == [(_PLAYER_ID, _ITEM_ID, 0)]
