"""Тесты pydantic-инвариантов ``PayoutLimitConfig`` / ``PayoutLimitsConfig``
/ ``MonetizationConfig`` (Спринт 4.1-E, шаг E.5).

Структурно копия `test_prize_lot_config.py`: smoke-тест на парсинг
реального `config/balance.yaml::monetization.payout_limit`, затем
точечные тесты на каждое поле / границу.

Покрытие (ГДД §12.6.5):

* реальный `config/balance.yaml::monetization.payout_limit` парсится;
* ``PayoutLimitConfig``:
  - ``currency`` принимает ``ton_nano`` / ``usdt_decimal``, отвергает ``stars``
    (Stars-выплаты не подпадают под крипто-лимит);
  - ``window_days`` в `[1, 365]`, иначе ``ValidationError``;
  - ``max_amount_native`` >= 0, отрицательное отвергается;
  - extra-поля отвергаются (`extra="forbid"`);
* ``PayoutLimitsConfig``:
  - дубликаты валют в ``per_currency`` отвергаются;
  - пустой ``per_currency`` валиден (= unlimited на все валюты);
  - ``get(currency)`` возвращает entry или ``None``;
* ``MonetizationConfig``:
  - требует поле ``payout_limit``;
  - extra-поля отвергаются.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml
from pydantic import ValidationError

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    MonetizationConfig,
    PayoutLimitConfig,
    PayoutLimitsConfig,
)
from pipirik_wars.domain.monetization.value_objects import Currency

_REAL_BALANCE_YAML = Path(__file__).resolve().parents[4] / "config" / "balance.yaml"


class TestRealBalanceYamlParses:
    """Реальный `config/balance.yaml::monetization` парсится без ошибок (smoke)."""

    def test_balance_yaml_parses_with_monetization(self) -> None:
        raw = yaml.safe_load(_REAL_BALANCE_YAML.read_text(encoding="utf-8"))
        cfg = BalanceConfig.model_validate(raw)
        per_currency = cfg.monetization.payout_limit.per_currency
        # Стартовая гипотеза 4.1-E: TON_NANO + USDT_DECIMAL, по одной записи.
        assert len(per_currency) == 2
        currencies = {entry.currency for entry in per_currency}
        assert currencies == {Currency.TON_NANO, Currency.USDT_DECIMAL}
        # Гранд-инвариант: все суммы — положительные, окно — в (1, 365).
        for entry in per_currency:
            assert entry.window_days >= 1
            assert entry.window_days <= 365
            assert entry.max_amount_native > 0


class TestPayoutLimitConfigCurrency:
    _BASE: ClassVar[dict[str, Any]] = {
        "currency": "ton_nano",
        "window_days": 30,
        "max_amount_native": 1_000_000_000,
    }

    def test_ton_nano_accepted(self) -> None:
        cfg = PayoutLimitConfig.model_validate({**self._BASE, "currency": "ton_nano"})
        assert cfg.currency == Currency.TON_NANO

    def test_usdt_decimal_accepted(self) -> None:
        cfg = PayoutLimitConfig.model_validate(
            {**self._BASE, "currency": "usdt_decimal"},
        )
        assert cfg.currency == Currency.USDT_DECIMAL

    def test_stars_rejected(self) -> None:
        # ГДД §12.6.5: Stars-выплаты идут через TG-refund-канал, не подпадают.
        with pytest.raises(ValidationError, match="STARS"):
            PayoutLimitConfig.model_validate({**self._BASE, "currency": "stars"})

    def test_unknown_currency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PayoutLimitConfig.model_validate({**self._BASE, "currency": "doge"})


class TestPayoutLimitConfigWindowDays:
    _BASE: ClassVar[dict[str, Any]] = {
        "currency": "ton_nano",
        "window_days": 30,
        "max_amount_native": 1_000_000_000,
    }

    def test_min_bound_passes(self) -> None:
        cfg = PayoutLimitConfig.model_validate({**self._BASE, "window_days": 1})
        assert cfg.window_days == 1

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="window_days"):
            PayoutLimitConfig.model_validate({**self._BASE, "window_days": 0})

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="window_days"):
            PayoutLimitConfig.model_validate({**self._BASE, "window_days": -1})

    def test_max_bound_passes(self) -> None:
        cfg = PayoutLimitConfig.model_validate({**self._BASE, "window_days": 365})
        assert cfg.window_days == 365

    def test_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError, match="window_days"):
            PayoutLimitConfig.model_validate({**self._BASE, "window_days": 366})

    @pytest.mark.parametrize("value", [1, 7, 30, 90, 180, 365])
    def test_valid_values_pass(self, value: int) -> None:
        cfg = PayoutLimitConfig.model_validate({**self._BASE, "window_days": value})
        assert cfg.window_days == value


class TestPayoutLimitConfigMaxAmount:
    _BASE: ClassVar[dict[str, Any]] = {
        "currency": "ton_nano",
        "window_days": 30,
        "max_amount_native": 1_000_000_000,
    }

    def test_zero_passes(self) -> None:
        # 0 = kill-switch на одну валюту (`/freeze_payouts` — нормальный путь).
        cfg = PayoutLimitConfig.model_validate({**self._BASE, "max_amount_native": 0})
        assert cfg.max_amount_native == 0

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="max_amount_native"):
            PayoutLimitConfig.model_validate({**self._BASE, "max_amount_native": -1})

    def test_large_value_passes(self) -> None:
        cfg = PayoutLimitConfig.model_validate(
            {**self._BASE, "max_amount_native": 10**18},
        )
        assert cfg.max_amount_native == 10**18


class TestPayoutLimitConfigStrict:
    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PayoutLimitConfig.model_validate(
                {
                    "currency": "ton_nano",
                    "window_days": 30,
                    "max_amount_native": 1,
                    "extra_typo": True,
                },
            )

    def test_missing_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PayoutLimitConfig.model_validate(
                {"currency": "ton_nano", "window_days": 30},
            )

    def test_is_frozen(self) -> None:
        cfg = PayoutLimitConfig.model_validate(
            {"currency": "ton_nano", "window_days": 30, "max_amount_native": 1},
        )
        with pytest.raises(ValidationError):
            cfg.window_days = 60


class TestPayoutLimitsConfigUniqueness:
    def test_unique_currencies_pass(self) -> None:
        cfg = PayoutLimitsConfig.model_validate(
            {
                "per_currency": [
                    {
                        "currency": "ton_nano",
                        "window_days": 30,
                        "max_amount_native": 1,
                    },
                    {
                        "currency": "usdt_decimal",
                        "window_days": 30,
                        "max_amount_native": 1,
                    },
                ],
            },
        )
        assert len(cfg.per_currency) == 2

    def test_duplicate_currencies_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            PayoutLimitsConfig.model_validate(
                {
                    "per_currency": [
                        {
                            "currency": "ton_nano",
                            "window_days": 30,
                            "max_amount_native": 1,
                        },
                        {
                            "currency": "ton_nano",
                            "window_days": 7,
                            "max_amount_native": 2,
                        },
                    ],
                },
            )

    def test_empty_per_currency_passes(self) -> None:
        # Пустой кортеж = unlimited на все валюты (валидный сценарий).
        cfg = PayoutLimitsConfig.model_validate({"per_currency": []})
        assert cfg.per_currency == ()

    def test_omitted_per_currency_defaults_to_empty(self) -> None:
        cfg = PayoutLimitsConfig.model_validate({})
        assert cfg.per_currency == ()


class TestPayoutLimitsConfigGet:
    @pytest.fixture
    def cfg(self) -> PayoutLimitsConfig:
        return PayoutLimitsConfig.model_validate(
            {
                "per_currency": [
                    {
                        "currency": "ton_nano",
                        "window_days": 30,
                        "max_amount_native": 10,
                    },
                    {
                        "currency": "usdt_decimal",
                        "window_days": 7,
                        "max_amount_native": 5,
                    },
                ],
            },
        )

    def test_get_returns_matching_entry(self, cfg: PayoutLimitsConfig) -> None:
        entry = cfg.get(Currency.USDT_DECIMAL)
        assert entry is not None
        assert entry.currency == Currency.USDT_DECIMAL
        assert entry.window_days == 7
        assert entry.max_amount_native == 5

    def test_get_returns_none_for_missing(self, cfg: PayoutLimitsConfig) -> None:
        # STARS никогда не лежит в per_currency (валидатор PayoutLimitConfig).
        assert cfg.get(Currency.STARS) is None

    def test_get_on_empty_returns_none(self) -> None:
        empty = PayoutLimitsConfig.model_validate({"per_currency": []})
        assert empty.get(Currency.TON_NANO) is None


class TestMonetizationConfig:
    def test_canonical_construction(self) -> None:
        cfg = MonetizationConfig.model_validate(
            {
                "payout_limit": {
                    "per_currency": [
                        {
                            "currency": "ton_nano",
                            "window_days": 30,
                            "max_amount_native": 1,
                        },
                    ],
                },
            },
        )
        assert cfg.payout_limit.per_currency[0].currency == Currency.TON_NANO

    def test_missing_payout_limit_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MonetizationConfig.model_validate({})

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MonetizationConfig.model_validate(
                {
                    "payout_limit": {"per_currency": []},
                    "extra_typo": True,
                },
            )
