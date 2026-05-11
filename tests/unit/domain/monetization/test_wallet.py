"""Тесты доменной сущности ``Wallet`` и VO ``TonAddress``/``UsdtJettonAddress``.

Спринт 4.1-D. Покрывают:
* ``TonAddress`` VO — raw и user-friendly форматы, невалидные строки;
* ``UsdtJettonAddress`` VO — аналогичные проверки, type-safety;
* ``Wallet`` entity — invariants ``__post_init__``:
  - ``player_id > 0``;
  - ``address`` непустой;
  - ``currency != STARS``;
  - адрес валидируется через соответствующий VO;
  - ``linked_at`` TZ-aware;
* immutability frozen-entity;
* ошибки ``WalletNotLinkedError`` / ``WalletAlreadyLinkedError``.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.monetization import (
    Currency,
    TonAddress,
    UsdtJettonAddress,
    Wallet,
    WalletAlreadyLinkedError,
    WalletNotLinkedError,
)

_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)
_VALID_RAW_ADDR = "0:" + "a1" * 32
_VALID_FRIENDLY_ADDR = "EQBvW8Z5huBkMJYdnfAEM5JqTNkuWX3diqYENkWsIL0XggGG"


# ---------------------------------------------------------------------------
# TonAddress
# ---------------------------------------------------------------------------
class TestTonAddressPostInit:
    """``__post_init__`` валидирует формат TON-адреса."""

    @pytest.mark.parametrize(
        "good",
        [
            _VALID_RAW_ADDR,
            "0:" + "0" * 64,
            "-1:" + "ff" * 32,
            _VALID_FRIENDLY_ADDR,
        ],
    )
    def test_valid_address_ok(self, good: str) -> None:
        addr = TonAddress(good)
        assert addr.value == good

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "not-an-address",
            "0:" + "gg" * 32,
            "0:" + "aa" * 31,
            "0:" + "aa" * 33,
            "12345",
        ],
    )
    def test_invalid_address_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="valid TON address"):
            TonAddress(bad)

    @pytest.mark.parametrize("bad", [123, None, b"bytes", object()])
    def test_non_str_raises_type_error(self, bad: object) -> None:
        with pytest.raises(TypeError, match="must be str"):
            TonAddress(bad)  # type: ignore[arg-type]


class TestTonAddressImmutability:
    """frozen VO нельзя мутировать."""

    def test_is_frozen(self) -> None:
        addr = TonAddress(_VALID_RAW_ADDR)
        with pytest.raises(dataclasses.FrozenInstanceError):
            addr.value = "other"

    def test_equality_by_value(self) -> None:
        a = TonAddress(_VALID_RAW_ADDR)
        b = TonAddress(_VALID_RAW_ADDR)
        assert a == b
        assert hash(a) == hash(b)


# ---------------------------------------------------------------------------
# UsdtJettonAddress
# ---------------------------------------------------------------------------
class TestUsdtJettonAddressPostInit:
    """``__post_init__`` валидирует формат (идентичный TonAddress)."""

    def test_valid_raw_ok(self) -> None:
        addr = UsdtJettonAddress(_VALID_RAW_ADDR)
        assert addr.value == _VALID_RAW_ADDR

    def test_valid_friendly_ok(self) -> None:
        addr = UsdtJettonAddress(_VALID_FRIENDLY_ADDR)
        assert addr.value == _VALID_FRIENDLY_ADDR

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="valid TON address"):
            UsdtJettonAddress("bad")

    def test_non_str_raises(self) -> None:
        with pytest.raises(TypeError, match="must be str"):
            UsdtJettonAddress(42)  # type: ignore[arg-type]


class TestUsdtJettonAddressTypeSafety:
    """``TonAddress != UsdtJettonAddress`` — разные типы."""

    def test_not_equal_to_ton_address(self) -> None:
        ton = TonAddress(_VALID_RAW_ADDR)
        usdt = UsdtJettonAddress(_VALID_RAW_ADDR)
        assert ton != usdt  # type: ignore[comparison-overlap]


# ---------------------------------------------------------------------------
# Wallet entity
# ---------------------------------------------------------------------------
def _make_wallet(
    *,
    player_id: int = 42,
    address: str = _VALID_RAW_ADDR,
    currency: Currency = Currency.TON_NANO,
    linked_at: datetime = _NOW,
) -> Wallet:
    return Wallet(
        player_id=player_id,
        address=address,
        currency=currency,
        linked_at=linked_at,
    )


class TestWalletHappyPath:
    """Конструирование валидного кошелька."""

    def test_ton_wallet(self) -> None:
        w = _make_wallet(currency=Currency.TON_NANO)
        assert w.player_id == 42
        assert w.address == _VALID_RAW_ADDR
        assert w.currency is Currency.TON_NANO
        assert w.linked_at == _NOW

    def test_usdt_wallet(self) -> None:
        w = _make_wallet(currency=Currency.USDT_DECIMAL)
        assert w.currency is Currency.USDT_DECIMAL

    def test_friendly_address(self) -> None:
        w = _make_wallet(address=_VALID_FRIENDLY_ADDR)
        assert w.address == _VALID_FRIENDLY_ADDR


class TestWalletInvariants:
    """``__post_init__`` invariants."""

    def test_player_id_must_be_positive_int(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            _make_wallet(player_id=0)

    def test_player_id_must_not_be_negative(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            _make_wallet(player_id=-1)

    def test_player_id_must_be_int(self) -> None:
        with pytest.raises(TypeError, match="must be int"):
            Wallet(
                player_id="42",  # type: ignore[arg-type]
                address=_VALID_RAW_ADDR,
                currency=Currency.TON_NANO,
                linked_at=_NOW,
            )

    def test_player_id_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be int"):
            Wallet(
                player_id=True,
                address=_VALID_RAW_ADDR,
                currency=Currency.TON_NANO,
                linked_at=_NOW,
            )

    def test_address_must_be_nonempty(self) -> None:
        with pytest.raises(ValueError, match="non-empty str"):
            _make_wallet(address="")

    def test_stars_currency_rejected(self) -> None:
        with pytest.raises(ValueError, match="Currency.STARS"):
            _make_wallet(currency=Currency.STARS)

    def test_invalid_ton_address_rejected(self) -> None:
        with pytest.raises(ValueError, match="valid TON address"):
            _make_wallet(currency=Currency.TON_NANO, address="bad-addr")

    def test_invalid_usdt_address_rejected(self) -> None:
        with pytest.raises(ValueError, match="valid TON address"):
            _make_wallet(currency=Currency.USDT_DECIMAL, address="bad-addr")

    def test_linked_at_must_be_tz_aware(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _make_wallet(linked_at=datetime(2026, 5, 11, 12, 0, 0))


class TestWalletImmutability:
    """frozen entity нельзя мутировать."""

    def test_is_frozen(self) -> None:
        w = _make_wallet()
        with pytest.raises(dataclasses.FrozenInstanceError):
            w.address = "other"

    def test_equality_by_fields(self) -> None:
        a = _make_wallet()
        b = _make_wallet()
        assert a == b
        assert hash(a) == hash(b)


# ---------------------------------------------------------------------------
# Wallet domain errors
# ---------------------------------------------------------------------------
class TestWalletNotLinkedError:
    """``WalletNotLinkedError`` — аттрибуты и сообщение."""

    def test_attributes(self) -> None:
        err = WalletNotLinkedError(player_id=42, currency=Currency.TON_NANO)
        assert err.player_id == 42
        assert err.currency is Currency.TON_NANO
        assert "42" in str(err)
        assert "ton_nano" in str(err)


class TestWalletAlreadyLinkedError:
    """``WalletAlreadyLinkedError`` — аттрибуты и сообщение."""

    def test_attributes(self) -> None:
        err = WalletAlreadyLinkedError(
            player_id=42,
            currency=Currency.TON_NANO,
            existing_address=_VALID_RAW_ADDR,
        )
        assert err.player_id == 42
        assert err.currency is Currency.TON_NANO
        assert err.existing_address == _VALID_RAW_ADDR
        assert "42" in str(err)
        assert "ton_nano" in str(err)
