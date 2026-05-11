"""Тесты доменного агрегата `PrizeLot` (ГДД §12.6, Спринт 4.1-C).

Покрывают:
* `FeeBufferAmount` VO — `>= 0`-invariant + types + immutability;
* `PrizeLot.freshly_generated(...)` — фабрика свежего лота;
* invariants `__post_init__`:
  - `amount_native > fee_buffer_native >= 0` → `PrizeLotInvariantError`;
  - `created_at` / `claimed_at` TZ-aware;
  - `status == CLAIMED ⇔ claimed_at is not None`;
  - `id` либо `None`, либо положительный `int`;
* status-machine transitions (`reserve` / `claim` / `refund`):
  - валидные переходы → новый `PrizeLot`-VO;
  - невалидные переходы → `PrizeLotStatusTransitionError`;
* ошибки `PrizeLotInvariantError` / `PrizeLotStatusTransitionError` /
  `PrizeLotNotFoundError` — атрибуты + сообщение;
* immutability frozen-агрегата (нельзя мутировать поля).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.monetization import (
    Currency,
    FeeBufferAmount,
    PrizeLot,
    PrizeLotInvariantError,
    PrizeLotNotFoundError,
    PrizeLotStatus,
    PrizeLotStatusTransitionError,
)

_NOW = datetime(2025, 11, 1, 12, 0, 0, tzinfo=UTC)


def _make_active_lot(
    *,
    lot_id: int | None = None,
    currency: Currency = Currency.TON_NANO,
    amount_native: int = 1_000_000_000,
    fee_buffer_native: int = 5_000_000,
    created_at: datetime | None = None,
) -> PrizeLot:
    return PrizeLot(
        id=lot_id,
        currency=currency,
        amount_native=amount_native,
        fee_buffer_native=FeeBufferAmount(fee_buffer_native),
        status=PrizeLotStatus.ACTIVE,
        created_at=created_at or _NOW,
        claimed_at=None,
    )


class TestFeeBufferAmountPostInit:
    """`__post_init__` сторожит invariant `value >= 0`."""

    @pytest.mark.parametrize("good", [0, 1, 1_000, 10**18])
    def test_non_negative_int_ok(self, good: int) -> None:
        amount = FeeBufferAmount(good)
        assert amount.value == good

    @pytest.mark.parametrize("bad", [-1, -42, -(10**9)])
    def test_negative_int_raises(self, bad: int) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            FeeBufferAmount(bad)

    @pytest.mark.parametrize("bad", [1.5, "9", b"1", None, object()])
    def test_non_int_value_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="must be int"):
            FeeBufferAmount(bad)  # type: ignore[arg-type]

    def test_bool_value_raises(self) -> None:
        # `bool` — подкласс `int` в Python, но семантически это не размер буфера.
        with pytest.raises(TypeError, match="must be int"):
            FeeBufferAmount(True)


class TestFeeBufferAmountImmutability:
    """frozen-VO нельзя мутировать; сравнение по полю."""

    def test_is_frozen(self) -> None:
        amount = FeeBufferAmount(10)
        with pytest.raises(dataclasses.FrozenInstanceError):
            amount.value = 99

    def test_equality_by_value(self) -> None:
        assert FeeBufferAmount(0) == FeeBufferAmount(0)
        assert FeeBufferAmount(5_000_000) == FeeBufferAmount(5_000_000)
        assert FeeBufferAmount(0) != FeeBufferAmount(1)
        assert hash(FeeBufferAmount(0)) == hash(FeeBufferAmount(0))


class TestPrizeLotFreshlyGenerated:
    """`PrizeLot.freshly_generated(...)` — фабрика свежего ACTIVE-лота."""

    def test_freshly_generated_returns_active_lot_without_id(self) -> None:
        lot = PrizeLot.freshly_generated(
            currency=Currency.TON_NANO,
            amount_native=1_000_000_000,
            fee_buffer_native=FeeBufferAmount(5_000_000),
            created_at=_NOW,
        )
        assert lot.id is None
        assert lot.status is PrizeLotStatus.ACTIVE
        assert lot.claimed_at is None
        assert lot.currency is Currency.TON_NANO
        assert lot.amount_native == 1_000_000_000
        assert lot.fee_buffer_native.value == 5_000_000
        assert lot.created_at == _NOW

    def test_freshly_generated_stars_with_zero_fee_buffer(self) -> None:
        lot = PrizeLot.freshly_generated(
            currency=Currency.STARS,
            amount_native=100,
            fee_buffer_native=FeeBufferAmount(0),
            created_at=_NOW,
        )
        assert lot.fee_buffer_native.value == 0
        assert lot.net_amount_native == 100

    def test_freshly_generated_is_active_property(self) -> None:
        lot = _make_active_lot()
        assert lot.is_active is True
        assert lot.is_reserved is False
        assert lot.is_terminal is False


class TestPrizeLotInvariantAmountGreaterThanFeeBuffer:
    """`amount_native > fee_buffer_native >= 0`."""

    def test_equal_amount_and_fee_buffer_raises(self) -> None:
        with pytest.raises(PrizeLotInvariantError) as exc_info:
            _make_active_lot(amount_native=100, fee_buffer_native=100)
        err = exc_info.value
        assert err.currency is Currency.TON_NANO
        assert err.amount_native == 100
        assert err.fee_buffer_native == 100

    def test_amount_less_than_fee_buffer_raises(self) -> None:
        with pytest.raises(PrizeLotInvariantError):
            _make_active_lot(amount_native=99, fee_buffer_native=100)

    def test_amount_one_greater_than_fee_buffer_ok(self) -> None:
        lot = _make_active_lot(amount_native=101, fee_buffer_native=100)
        assert lot.net_amount_native == 1

    def test_amount_one_greater_than_zero_fee_buffer_ok(self) -> None:
        lot = _make_active_lot(amount_native=1, fee_buffer_native=0)
        assert lot.net_amount_native == 1

    @pytest.mark.parametrize("bad", [1.5, "100", None, object()])
    def test_non_int_amount_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="amount_native must be int"):
            _make_active_lot(amount_native=bad)  # type: ignore[arg-type]

    def test_bool_amount_raises(self) -> None:
        with pytest.raises(TypeError, match="amount_native must be int"):
            _make_active_lot(amount_native=True)


class TestPrizeLotCreatedAtAndClaimedAtTimezone:
    """`created_at` / `claimed_at` обязаны быть TZ-aware."""

    def test_naive_created_at_raises(self) -> None:
        naive = datetime(2025, 11, 1, 12, 0, 0)
        with pytest.raises(ValueError, match="created_at must be timezone-aware"):
            _make_active_lot(created_at=naive)

    def test_naive_claimed_at_raises(self) -> None:
        naive_claim = datetime(2025, 11, 1, 13, 0, 0)
        with pytest.raises(ValueError, match="claimed_at must be timezone-aware"):
            PrizeLot(
                id=1,
                currency=Currency.STARS,
                amount_native=100,
                fee_buffer_native=FeeBufferAmount(0),
                status=PrizeLotStatus.CLAIMED,
                created_at=_NOW,
                claimed_at=naive_claim,
            )


class TestPrizeLotClaimedAtStatusInvariant:
    """`status == CLAIMED ⇔ claimed_at is not None`."""

    def test_claimed_without_claimed_at_raises(self) -> None:
        with pytest.raises(ValueError, match="CLAIMED.*requires claimed_at"):
            PrizeLot(
                id=1,
                currency=Currency.STARS,
                amount_native=100,
                fee_buffer_native=FeeBufferAmount(0),
                status=PrizeLotStatus.CLAIMED,
                created_at=_NOW,
                claimed_at=None,
            )

    def test_non_claimed_with_claimed_at_raises(self) -> None:
        claimed_at = _NOW + timedelta(hours=1)
        for status in (
            PrizeLotStatus.ACTIVE,
            PrizeLotStatus.RESERVED,
            PrizeLotStatus.REFUNDED,
        ):
            with pytest.raises(ValueError, match="must have claimed_at=None"):
                PrizeLot(
                    id=1,
                    currency=Currency.STARS,
                    amount_native=100,
                    fee_buffer_native=FeeBufferAmount(0),
                    status=status,
                    created_at=_NOW,
                    claimed_at=claimed_at,
                )


class TestPrizeLotIdInvariant:
    """`id: int | None`, причём int должен быть положительным."""

    def test_id_none_ok(self) -> None:
        lot = _make_active_lot(lot_id=None)
        assert lot.id is None

    @pytest.mark.parametrize("good", [1, 42, 10**9])
    def test_id_positive_int_ok(self, good: int) -> None:
        lot = _make_active_lot(lot_id=good)
        assert lot.id == good

    @pytest.mark.parametrize("bad", [0, -1, -42])
    def test_id_non_positive_int_raises(self, bad: int) -> None:
        with pytest.raises(ValueError, match="id must be a positive int or None"):
            _make_active_lot(lot_id=bad)

    @pytest.mark.parametrize("bad", [1.5, "1", object()])
    def test_id_non_int_raises(self, bad: object) -> None:
        with pytest.raises(ValueError, match="id must be a positive int or None"):
            _make_active_lot(lot_id=bad)  # type: ignore[arg-type]

    def test_id_bool_raises(self) -> None:
        with pytest.raises(ValueError, match="id must be a positive int or None"):
            _make_active_lot(lot_id=True)


class TestPrizeLotReserveTransition:
    """`reserve()` — `ACTIVE → RESERVED`."""

    def test_active_can_reserve(self) -> None:
        lot = _make_active_lot(lot_id=1)
        reserved = lot.reserve()
        assert reserved.status is PrizeLotStatus.RESERVED
        assert reserved.is_reserved
        assert not reserved.is_active
        assert not reserved.is_terminal
        # Поля кроме status сохраняются.
        assert reserved.id == lot.id
        assert reserved.currency == lot.currency
        assert reserved.amount_native == lot.amount_native
        assert reserved.fee_buffer_native == lot.fee_buffer_native
        assert reserved.created_at == lot.created_at
        assert reserved.claimed_at is None
        # Иммутабельность исходного лота.
        assert lot.status is PrizeLotStatus.ACTIVE

    def test_reserved_cannot_reserve_again(self) -> None:
        lot = _make_active_lot(lot_id=42).reserve()
        with pytest.raises(PrizeLotStatusTransitionError) as exc_info:
            lot.reserve()
        err = exc_info.value
        assert err.lot_id == 42
        assert err.from_status is PrizeLotStatus.RESERVED
        assert err.to_status is PrizeLotStatus.RESERVED

    def test_claimed_cannot_reserve(self) -> None:
        lot = _make_active_lot(lot_id=1).reserve().claim(claimed_at=_NOW)
        with pytest.raises(PrizeLotStatusTransitionError):
            lot.reserve()

    def test_refunded_cannot_reserve(self) -> None:
        lot = _make_active_lot(lot_id=1).refund()
        with pytest.raises(PrizeLotStatusTransitionError):
            lot.reserve()


class TestPrizeLotClaimTransition:
    """`claim(claimed_at=...)` — `RESERVED → CLAIMED`."""

    def test_reserved_can_claim(self) -> None:
        claim_time = _NOW + timedelta(hours=1)
        lot = _make_active_lot(lot_id=7).reserve().claim(claimed_at=claim_time)
        assert lot.status is PrizeLotStatus.CLAIMED
        assert lot.claimed_at == claim_time
        assert lot.is_terminal
        assert not lot.is_active
        assert not lot.is_reserved

    def test_active_cannot_claim(self) -> None:
        with pytest.raises(PrizeLotStatusTransitionError) as exc_info:
            _make_active_lot(lot_id=1).claim(claimed_at=_NOW)
        err = exc_info.value
        assert err.from_status is PrizeLotStatus.ACTIVE
        assert err.to_status is PrizeLotStatus.CLAIMED

    def test_claimed_cannot_claim_again(self) -> None:
        lot = _make_active_lot(lot_id=1).reserve().claim(claimed_at=_NOW)
        with pytest.raises(PrizeLotStatusTransitionError):
            lot.claim(claimed_at=_NOW)

    def test_refunded_cannot_claim(self) -> None:
        lot = _make_active_lot(lot_id=1).refund()
        with pytest.raises(PrizeLotStatusTransitionError):
            lot.claim(claimed_at=_NOW)

    def test_claim_with_naive_datetime_raises(self) -> None:
        naive = datetime(2025, 11, 1, 13, 0, 0)
        lot = _make_active_lot(lot_id=1).reserve()
        with pytest.raises(ValueError, match="claim.*must be timezone-aware"):
            lot.claim(claimed_at=naive)


class TestPrizeLotRefundTransition:
    """`refund()` — `ACTIVE|RESERVED → REFUNDED`."""

    def test_active_can_refund(self) -> None:
        lot = _make_active_lot(lot_id=1).refund()
        assert lot.status is PrizeLotStatus.REFUNDED
        assert lot.is_terminal
        assert lot.claimed_at is None

    def test_reserved_can_refund(self) -> None:
        lot = _make_active_lot(lot_id=1).reserve().refund()
        assert lot.status is PrizeLotStatus.REFUNDED
        assert lot.is_terminal

    def test_claimed_cannot_refund(self) -> None:
        lot = _make_active_lot(lot_id=1).reserve().claim(claimed_at=_NOW)
        with pytest.raises(PrizeLotStatusTransitionError) as exc_info:
            lot.refund()
        err = exc_info.value
        assert err.from_status is PrizeLotStatus.CLAIMED
        assert err.to_status is PrizeLotStatus.REFUNDED

    def test_refunded_cannot_refund_again(self) -> None:
        lot = _make_active_lot(lot_id=1).refund()
        with pytest.raises(PrizeLotStatusTransitionError):
            lot.refund()


class TestPrizeLotImmutability:
    """frozen+slots-агрегат нельзя мутировать; transitions возвращают новый VO."""

    def test_lot_is_frozen(self) -> None:
        lot = _make_active_lot()
        with pytest.raises(dataclasses.FrozenInstanceError):
            lot.status = PrizeLotStatus.RESERVED

    def test_reserve_returns_new_instance(self) -> None:
        before = _make_active_lot(lot_id=1)
        after = before.reserve()
        assert after is not before
        # Исходный лот не мутирован.
        assert before.status is PrizeLotStatus.ACTIVE
        assert after.status is PrizeLotStatus.RESERVED

    def test_equality_by_fields(self) -> None:
        a = _make_active_lot(lot_id=1)
        b = _make_active_lot(lot_id=1)
        assert a == b
        assert hash(a) == hash(b)

    def test_different_id_compare_unequal(self) -> None:
        assert _make_active_lot(lot_id=1) != _make_active_lot(lot_id=2)


class TestPrizeLotStatusEnum:
    """Машинные id `PrizeLotStatus` — стабильные строки."""

    def test_active_value(self) -> None:
        assert PrizeLotStatus.ACTIVE.value == "active"

    def test_reserved_value(self) -> None:
        assert PrizeLotStatus.RESERVED.value == "reserved"

    def test_claimed_value(self) -> None:
        assert PrizeLotStatus.CLAIMED.value == "claimed"

    def test_refunded_value(self) -> None:
        assert PrizeLotStatus.REFUNDED.value == "refunded"


class TestPrizeLotInvariantErrorAttributes:
    """Атрибуты ошибки + сообщение."""

    def test_attributes_and_message(self) -> None:
        err = PrizeLotInvariantError(
            currency=Currency.TON_NANO,
            amount_native=100,
            fee_buffer_native=100,
        )
        assert err.currency is Currency.TON_NANO
        assert err.amount_native == 100
        assert err.fee_buffer_native == 100
        msg = str(err)
        assert "ton_nano" in msg
        assert "amount_native (100)" in msg
        assert "fee_buffer_native (100)" in msg


class TestPrizeLotStatusTransitionErrorAttributes:
    """Атрибуты ошибки + сообщение."""

    def test_attributes_with_known_id(self) -> None:
        err = PrizeLotStatusTransitionError(
            lot_id=42,
            from_status=PrizeLotStatus.CLAIMED,
            to_status=PrizeLotStatus.REFUNDED,
        )
        assert err.lot_id == 42
        assert err.from_status is PrizeLotStatus.CLAIMED
        assert err.to_status is PrizeLotStatus.REFUNDED
        msg = str(err)
        assert "id=42" in msg
        assert "'claimed'" in msg
        assert "'refunded'" in msg

    def test_attributes_with_unsaved_id(self) -> None:
        err = PrizeLotStatusTransitionError(
            lot_id=None,
            from_status=PrizeLotStatus.ACTIVE,
            to_status=PrizeLotStatus.CLAIMED,
        )
        assert err.lot_id is None
        msg = str(err)
        assert "id=<unsaved>" in msg


class TestPrizeLotNotFoundErrorAttributes:
    """Атрибуты ошибки + сообщение."""

    def test_attributes_and_message(self) -> None:
        err = PrizeLotNotFoundError(lot_id=999)
        assert err.lot_id == 999
        assert "id=999" in str(err)
