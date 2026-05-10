"""Тесты VO монетизации (`Currency` / `StarsAmount` / `IdempotencyKey`).

Спринт 4.1-A. Покрывают invariant-проверки `__post_init__` и
неизменяемость VO. Сами machine-id-enum-значения (`Currency`)
не тестируются отдельно — они тривиальный StrEnum, их значения
проверяются интеграционным тестом `tests/integration/test_payments_migration.py`
(в Спринте 4.1-A через CHECK-constraint `payments_currency_whitelist`).
"""

from __future__ import annotations

import dataclasses

import pytest

from pipirik_wars.domain.monetization import (
    Currency,
    IdempotencyKey,
    StarsAmount,
)


class TestStarsAmountPostInit:
    """`__post_init__` сторожит invariant `value > 0`."""

    @pytest.mark.parametrize("good", [1, 9, 100, 1_000_000])
    def test_positive_int_ok(self, good: int) -> None:
        amount = StarsAmount(good)
        assert amount.value == good

    @pytest.mark.parametrize("bad", [0, -1, -42, -1_000_000])
    def test_non_positive_int_raises(self, bad: int) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            StarsAmount(bad)

    @pytest.mark.parametrize("bad", [1.5, "9", b"1", None, object()])
    def test_non_int_value_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="must be int"):
            StarsAmount(bad)  # type: ignore[arg-type]

    def test_bool_value_raises(self) -> None:
        # `bool` — подкласс `int` в Python, но семантически это не количество ⭐.
        with pytest.raises(TypeError, match="must be int"):
            StarsAmount(True)


class TestStarsAmountImmutability:
    """frozen-VO нельзя мутировать; сравнение по полю."""

    def test_amount_is_frozen(self) -> None:
        amount = StarsAmount(1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            amount.value = 9

    def test_amounts_with_same_value_compare_equal(self) -> None:
        a = StarsAmount(9)
        b = StarsAmount(9)
        assert a == b
        assert hash(a) == hash(b)

    def test_amounts_with_different_value_compare_unequal(self) -> None:
        assert StarsAmount(1) != StarsAmount(9)


class TestIdempotencyKeyPostInit:
    """`__post_init__` сторожит regex `[A-Za-z0-9_\\-:]{1,64}`."""

    @pytest.mark.parametrize(
        "good",
        [
            "a",
            "ABC",
            "paid_roulette:42:msg-101",
            "x" * 64,
            "snake_case",
            "kebab-case",
            "namespace:42:9-pack:abc",
            "0123456789",
        ],
    )
    def test_well_formed_value_ok(self, good: str) -> None:
        key = IdempotencyKey(good)
        assert key.value == good

    @pytest.mark.parametrize(
        "bad",
        [
            "",  # пустой
            "x" * 65,  # > 64
            "with space",
            "tab\tinside",
            "newline\ninside",
            "with/slash",
            "with;semicolon",
            "with'quote",
            'with"dquote',
            "with$dollar",
            "юникод",
            "emoji-😀",
            "DROP TABLE payments;--",
        ],
    )
    def test_malformed_value_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="must match"):
            IdempotencyKey(bad)

    @pytest.mark.parametrize("bad", [123, 1.5, b"abc", None, object()])
    def test_non_str_value_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="must be str"):
            IdempotencyKey(bad)  # type: ignore[arg-type]


class TestIdempotencyKeyImmutability:
    """frozen-VO нельзя мутировать; сравнение по полю."""

    def test_key_is_frozen(self) -> None:
        key = IdempotencyKey("a")
        with pytest.raises(dataclasses.FrozenInstanceError):
            key.value = "b"

    def test_keys_with_same_value_compare_equal(self) -> None:
        a = IdempotencyKey("paid_roulette:42:msg-1")
        b = IdempotencyKey("paid_roulette:42:msg-1")
        assert a == b
        assert hash(a) == hash(b)

    def test_keys_with_different_value_compare_unequal(self) -> None:
        a = IdempotencyKey("a")
        b = IdempotencyKey("b")
        assert a != b


class TestCurrencyEnum:
    """Стабильные машинные id валют (попадают в `payments.currency`)."""

    def test_stars_value(self) -> None:
        assert Currency.STARS.value == "stars"

    def test_ton_nano_value(self) -> None:
        assert Currency.TON_NANO.value == "ton_nano"

    def test_usdt_decimal_value(self) -> None:
        assert Currency.USDT_DECIMAL.value == "usdt_decimal"

    def test_three_currencies(self) -> None:
        assert {c.value for c in Currency} == {"stars", "ton_nano", "usdt_decimal"}
