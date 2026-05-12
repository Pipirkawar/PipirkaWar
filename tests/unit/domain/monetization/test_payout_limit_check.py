"""Тесты VO результата ``IPayoutLimitChecker.check(...)`` (Спринт 4.1-E, E.5).

Покрывают:

* ``PayoutLimitWithin``:
  - ``remaining_native`` обязан быть ``int >= 0``;
  - ``bool`` запрещён (защита от случайного ``True``/``False`` вместо `int`);
  - immutability frozen-VO;
* ``PayoutLimitOverLimit``:
  - ``retry_after`` обязан быть TZ-aware ``datetime``;
  - ``exceeded_by_native`` обязан быть ``int >= 1``;
  - immutability frozen-VO;
* ``PayoutLimitCheckResult`` — sum-type из двух variant-ов, использование
  в ``match`` сохраняет статическую типизацию.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.monetization import (
    PayoutLimitCheckResult,
    PayoutLimitOverLimit,
    PayoutLimitWithin,
)


class TestPayoutLimitWithin:
    def test_zero_remaining_is_valid(self) -> None:
        # Семантика: «уложился ровно в копейку», следующий же claim — over-limit.
        result = PayoutLimitWithin(remaining_native=0)
        assert result.remaining_native == 0

    def test_positive_remaining_is_valid(self) -> None:
        result = PayoutLimitWithin(remaining_native=12_345)
        assert result.remaining_native == 12_345

    def test_large_remaining_is_valid(self) -> None:
        # unlimited-семантика: реализация чекера возвращает sys.maxsize.
        result = PayoutLimitWithin(remaining_native=2**63 - 1)
        assert result.remaining_native == 2**63 - 1

    def test_negative_remaining_rejected(self) -> None:
        with pytest.raises(ValueError, match="remaining_native"):
            PayoutLimitWithin(remaining_native=-1)

    def test_float_rejected(self) -> None:
        with pytest.raises(TypeError, match="remaining_native"):
            PayoutLimitWithin(remaining_native=1.5)  # type: ignore[arg-type]

    def test_bool_rejected(self) -> None:
        # `True` равен `1` через `int`, но семантически это «остаток в bool-е».
        with pytest.raises(TypeError, match="remaining_native"):
            PayoutLimitWithin(remaining_native=True)

    def test_is_frozen(self) -> None:
        result = PayoutLimitWithin(remaining_native=10)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.remaining_native = 20

    def test_equality_by_value(self) -> None:
        assert PayoutLimitWithin(remaining_native=10) == PayoutLimitWithin(
            remaining_native=10,
        )
        assert PayoutLimitWithin(remaining_native=10) != PayoutLimitWithin(
            remaining_native=11,
        )


class TestPayoutLimitOverLimit:
    _NOW = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)

    def test_canonical_construction(self) -> None:
        result = PayoutLimitOverLimit(retry_after=self._NOW, exceeded_by_native=42)
        assert result.retry_after == self._NOW
        assert result.exceeded_by_native == 42

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            PayoutLimitOverLimit(
                retry_after=datetime(2026, 5, 12, 12, 0),  # naïve
                exceeded_by_native=1,
            )

    def test_non_datetime_retry_after_rejected(self) -> None:
        with pytest.raises(TypeError, match="retry_after"):
            PayoutLimitOverLimit(
                retry_after="2026-05-12T12:00:00+00:00",  # type: ignore[arg-type]
                exceeded_by_native=1,
            )

    def test_zero_exceeded_by_rejected(self) -> None:
        # «exceeded на 0» бессмысленно — если на 0, это `Within(0)`.
        with pytest.raises(ValueError, match="exceeded_by_native"):
            PayoutLimitOverLimit(retry_after=self._NOW, exceeded_by_native=0)

    def test_negative_exceeded_by_rejected(self) -> None:
        with pytest.raises(ValueError, match="exceeded_by_native"):
            PayoutLimitOverLimit(retry_after=self._NOW, exceeded_by_native=-1)

    def test_float_exceeded_by_rejected(self) -> None:
        with pytest.raises(TypeError, match="exceeded_by_native"):
            PayoutLimitOverLimit(
                retry_after=self._NOW,
                exceeded_by_native=1.0,  # type: ignore[arg-type]
            )

    def test_bool_exceeded_by_rejected(self) -> None:
        with pytest.raises(TypeError, match="exceeded_by_native"):
            PayoutLimitOverLimit(
                retry_after=self._NOW,
                exceeded_by_native=True,
            )

    def test_is_frozen(self) -> None:
        result = PayoutLimitOverLimit(retry_after=self._NOW, exceeded_by_native=1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.exceeded_by_native = 2

    def test_equality_by_value(self) -> None:
        a = PayoutLimitOverLimit(retry_after=self._NOW, exceeded_by_native=5)
        b = PayoutLimitOverLimit(retry_after=self._NOW, exceeded_by_native=5)
        c = PayoutLimitOverLimit(retry_after=self._NOW, exceeded_by_native=6)
        assert a == b
        assert a != c


class TestPayoutLimitCheckResultDispatch:
    """Проверяем, что sum-type корректно работает в ``match``-операторе.

    Это критично для use-case-а ``ClaimPrize.execute(...)`` (E.10), который
    различает Within / OverLimit через ``match`` и не должен сваливаться
    в ``isinstance``-ад.
    """

    _NOW = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)

    @staticmethod
    def _route(result: PayoutLimitCheckResult) -> str:
        match result:
            case PayoutLimitWithin(remaining_native=remaining):
                return f"within:{remaining}"
            case PayoutLimitOverLimit(
                retry_after=retry,
                exceeded_by_native=excess,
            ):
                return f"over:{retry.isoformat()}:{excess}"

    def test_within_dispatch(self) -> None:
        assert self._route(PayoutLimitWithin(remaining_native=7)) == "within:7"

    def test_over_limit_dispatch(self) -> None:
        result = PayoutLimitOverLimit(retry_after=self._NOW, exceeded_by_native=3)
        assert self._route(result) == f"over:{self._NOW.isoformat()}:3"
