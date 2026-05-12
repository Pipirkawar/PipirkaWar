"""Тесты `FakePrizeLotRepository` для шага E.6 — winner-tracking + rolling-window.

Покрывают:

* `record_winner` — happy-path / error-paths (lot не существует / lot не CLAIMED
  / `player_id <= 0`).
* `sum_claimed_in_window` — пустой repo, без winner-registration, фильтрация
  по `claimed_at >= since`, по статусу `CLAIMED`, по `currency`, по
  `winner_id == player_id`.
* `oldest_claimed_at_in_window` — выбирает минимальный `claimed_at` в окне,
  возвращает `None` для пустого результата.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.monetization.entities import PrizeLot, PrizeLotStatus
from pipirik_wars.domain.monetization.errors import PrizeLotNotFoundError
from pipirik_wars.domain.monetization.value_objects import Currency, FeeBufferAmount
from tests.fakes import FakePrizeLotRepository

_NOW = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)


def _claimed(
    *,
    lot_id: int,
    currency: Currency,
    amount_native: int,
    claimed_at: datetime,
) -> PrizeLot:
    return PrizeLot(
        id=lot_id,
        currency=currency,
        amount_native=amount_native,
        fee_buffer_native=FeeBufferAmount(0),
        status=PrizeLotStatus.CLAIMED,
        created_at=claimed_at - timedelta(hours=1),
        reserved_at=claimed_at - timedelta(minutes=10),
        claimed_at=claimed_at,
    )


def _active(*, lot_id: int, currency: Currency, amount_native: int) -> PrizeLot:
    return PrizeLot(
        id=lot_id,
        currency=currency,
        amount_native=amount_native,
        fee_buffer_native=FeeBufferAmount(0),
        status=PrizeLotStatus.ACTIVE,
        created_at=_NOW - timedelta(days=10),
    )


class TestRecordWinner:
    def test_happy_path(self) -> None:
        repo = FakePrizeLotRepository()
        lot = _claimed(
            lot_id=1,
            currency=Currency.USDT_DECIMAL,
            amount_native=100,
            claimed_at=_NOW,
        )
        repo._storage[1] = lot

        repo.record_winner(lot_id=1, player_id=42)

        assert repo.winners == {1: 42}

    def test_lot_not_found_raises(self) -> None:
        repo = FakePrizeLotRepository()
        with pytest.raises(PrizeLotNotFoundError):
            repo.record_winner(lot_id=999, player_id=42)

    def test_lot_not_claimed_raises(self) -> None:
        repo = FakePrizeLotRepository()
        lot = _active(lot_id=1, currency=Currency.USDT_DECIMAL, amount_native=100)
        repo._storage[1] = lot
        with pytest.raises(ValueError, match="status is 'active'"):
            repo.record_winner(lot_id=1, player_id=42)

    def test_zero_player_id_raises(self) -> None:
        repo = FakePrizeLotRepository()
        with pytest.raises(ValueError, match="player_id must be > 0"):
            repo.record_winner(lot_id=1, player_id=0)

    def test_negative_player_id_raises(self) -> None:
        repo = FakePrizeLotRepository()
        with pytest.raises(ValueError, match="player_id must be > 0"):
            repo.record_winner(lot_id=1, player_id=-5)


@pytest.mark.asyncio
class TestSumClaimedInWindow:
    async def test_empty_repo_returns_zero(self) -> None:
        repo = FakePrizeLotRepository()
        result = await repo.sum_claimed_in_window(
            player_id=42,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        assert result == 0

    async def test_lot_without_winner_record_not_counted(self) -> None:
        """Без `record_winner(...)` лот не привязан к игроку → не суммируется."""
        repo = FakePrizeLotRepository()
        lot = _claimed(
            lot_id=1,
            currency=Currency.USDT_DECIMAL,
            amount_native=100,
            claimed_at=_NOW,
        )
        repo._storage[1] = lot
        # `record_winner` НЕ вызван.

        result = await repo.sum_claimed_in_window(
            player_id=42,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        assert result == 0

    async def test_filters_by_winner(self) -> None:
        repo = FakePrizeLotRepository()
        lot_a = _claimed(
            lot_id=1,
            currency=Currency.USDT_DECIMAL,
            amount_native=100,
            claimed_at=_NOW,
        )
        lot_b = _claimed(
            lot_id=2,
            currency=Currency.USDT_DECIMAL,
            amount_native=200,
            claimed_at=_NOW,
        )
        repo._storage[1] = lot_a
        repo._storage[2] = lot_b
        repo.record_winner(lot_id=1, player_id=42)
        repo.record_winner(lot_id=2, player_id=99)

        result_42 = await repo.sum_claimed_in_window(
            player_id=42,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        assert result_42 == 100

        result_99 = await repo.sum_claimed_in_window(
            player_id=99,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        assert result_99 == 200

    async def test_filters_by_currency(self) -> None:
        repo = FakePrizeLotRepository()
        lot_usdt = _claimed(
            lot_id=1,
            currency=Currency.USDT_DECIMAL,
            amount_native=100,
            claimed_at=_NOW,
        )
        lot_ton = _claimed(
            lot_id=2,
            currency=Currency.TON_NANO,
            amount_native=999,
            claimed_at=_NOW,
        )
        repo._storage[1] = lot_usdt
        repo._storage[2] = lot_ton
        repo.record_winner(lot_id=1, player_id=42)
        repo.record_winner(lot_id=2, player_id=42)

        result_usdt = await repo.sum_claimed_in_window(
            player_id=42,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        assert result_usdt == 100

    async def test_filters_by_claimed_at_window(self) -> None:
        repo = FakePrizeLotRepository()
        old = _claimed(
            lot_id=1,
            currency=Currency.USDT_DECIMAL,
            amount_native=100,
            claimed_at=_NOW - timedelta(days=40),
        )
        recent = _claimed(
            lot_id=2,
            currency=Currency.USDT_DECIMAL,
            amount_native=50,
            claimed_at=_NOW - timedelta(days=10),
        )
        repo._storage[1] = old
        repo._storage[2] = recent
        repo.record_winner(lot_id=1, player_id=42)
        repo.record_winner(lot_id=2, player_id=42)

        result = await repo.sum_claimed_in_window(
            player_id=42,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        # Только `recent` (10 дней) укладывается в 30-дневное окно.
        assert result == 50

    async def test_ignores_non_claimed_status(self) -> None:
        repo = FakePrizeLotRepository()
        # Игрок может «иметь» ACTIVE-лот (например, через `add_winner` для
        # будущего CLAIMED-лота — но в fake `record_winner` это запрещает).
        # Здесь проверяем что даже если в `winners` присутствует не-CLAIMED
        # лот, он не суммируется.
        lot = _active(lot_id=1, currency=Currency.USDT_DECIMAL, amount_native=100)
        repo._storage[1] = lot
        # Обходим валидацию `record_winner` для теста filter-по-status.
        repo.winners[1] = 42

        result = await repo.sum_claimed_in_window(
            player_id=42,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        assert result == 0


@pytest.mark.asyncio
class TestOldestClaimedAtInWindow:
    async def test_empty_returns_none(self) -> None:
        repo = FakePrizeLotRepository()
        result = await repo.oldest_claimed_at_in_window(
            player_id=42,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        assert result is None

    async def test_picks_minimum_claimed_at_in_window(self) -> None:
        repo = FakePrizeLotRepository()
        oldest_in_window = _NOW - timedelta(days=20)
        later = _NOW - timedelta(days=5)
        out_of_window = _NOW - timedelta(days=40)

        for i, claimed_at in enumerate(
            [oldest_in_window, later, out_of_window],
            start=1,
        ):
            lot = _claimed(
                lot_id=i,
                currency=Currency.USDT_DECIMAL,
                amount_native=100,
                claimed_at=claimed_at,
            )
            repo._storage[i] = lot
            repo.record_winner(lot_id=i, player_id=42)

        result = await repo.oldest_claimed_at_in_window(
            player_id=42,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        assert result == oldest_in_window

    async def test_no_match_returns_none(self) -> None:
        """Если winner не зарегистрирован — None."""
        repo = FakePrizeLotRepository()
        lot = _claimed(
            lot_id=1,
            currency=Currency.USDT_DECIMAL,
            amount_native=100,
            claimed_at=_NOW,
        )
        repo._storage[1] = lot
        # `record_winner` НЕ вызван → проверка для player_id=42 вернёт None.

        result = await repo.oldest_claimed_at_in_window(
            player_id=42,
            currency=Currency.USDT_DECIMAL,
            since=_NOW - timedelta(days=30),
        )
        assert result is None
