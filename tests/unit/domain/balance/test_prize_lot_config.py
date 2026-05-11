"""Тесты pydantic-инвариантов `PrizeLotConfig` (Спринт 4.1-D, D.9.a).

Структурно копия `test_enchantment_config.py` / `test_roulette_config.py`:
сначала smoke-тест на парсинг реального `config/balance.yaml::prize_lot`,
затем точечные тесты на каждое поле / границу.

Покрытие (ГДД §12.6.3-§12.6.4):

* реальный `config/balance.yaml::prize_lot` парсится без ошибок;
* `reserved_ttl_seconds`:
  * нижняя граница `60` (`1 min`) — `<60` отклоняется;
  * верхняя граница `30 d` (`2_592_000`) — `>` отклоняется;
  * валидные значения внутри `[60, 30 d]` парсятся;
  * `float` / `str` / `bool` отклоняются (тип `int`);
  * отсутствие поля → ValidationError;
* `extra="forbid"` — лишние поля отвергаются (защита от опечаток).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pipirik_wars.domain.balance.config import BalanceConfig, PrizeLotConfig

_REAL_BALANCE_YAML = Path(__file__).resolve().parents[4] / "config" / "balance.yaml"

_MIN_TTL_SECONDS: int = 60
_MAX_TTL_SECONDS: int = 30 * 24 * 3600  # 30 d, см. config.py


class TestRealBalanceYamlParses:
    """Реальный `config/balance.yaml::prize_lot` парсится без ошибок (smoke)."""

    def test_balance_yaml_parses(self) -> None:
        raw = yaml.safe_load(_REAL_BALANCE_YAML.read_text(encoding="utf-8"))
        cfg = BalanceConfig.model_validate(raw)
        # Стартовая гипотеза 48 h = 172 800 — пусть будет лёгкая
        # «гранд-инвариант»-проверка, чтобы случайные правки в yaml
        # не уехали ниже минуты или выше 30 д. без правки этого теста.
        assert _MIN_TTL_SECONDS <= cfg.prize_lot.reserved_ttl_seconds <= _MAX_TTL_SECONDS
        # На момент 4.1-D в balance.yaml — 48 h (172 800 s).
        assert cfg.prize_lot.reserved_ttl_seconds == 172_800

    def test_prize_lot_block_alone_parses(self) -> None:
        cfg = PrizeLotConfig.model_validate({"reserved_ttl_seconds": 172_800})
        assert cfg.reserved_ttl_seconds == 172_800


class TestReservedTtlBounds:
    @staticmethod
    def _payload(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {"reserved_ttl_seconds": 172_800}
        base.update(overrides)
        return base

    def test_min_bound_passes(self) -> None:
        cfg = PrizeLotConfig.model_validate(self._payload(reserved_ttl_seconds=60))
        assert cfg.reserved_ttl_seconds == 60

    def test_below_min_bound_rejected(self) -> None:
        with pytest.raises(ValidationError, match="reserved_ttl_seconds"):
            PrizeLotConfig.model_validate(self._payload(reserved_ttl_seconds=59))

    def test_zero_rejected(self) -> None:
        # «foot-gun» 0 — лот сразу же возвращался бы cron-ом → блокируем.
        with pytest.raises(ValidationError, match="reserved_ttl_seconds"):
            PrizeLotConfig.model_validate(self._payload(reserved_ttl_seconds=0))

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="reserved_ttl_seconds"):
            PrizeLotConfig.model_validate(self._payload(reserved_ttl_seconds=-1))

    def test_max_bound_passes(self) -> None:
        cfg = PrizeLotConfig.model_validate(
            self._payload(reserved_ttl_seconds=_MAX_TTL_SECONDS),
        )
        assert cfg.reserved_ttl_seconds == _MAX_TTL_SECONDS

    def test_above_max_bound_rejected(self) -> None:
        with pytest.raises(ValidationError, match="reserved_ttl_seconds"):
            PrizeLotConfig.model_validate(
                self._payload(reserved_ttl_seconds=_MAX_TTL_SECONDS + 1),
            )

    @pytest.mark.parametrize(
        "value",
        [
            60,
            3600,  # 1 h
            86_400,  # 1 d
            172_800,  # 48 h — дефолт
            604_800,  # 7 d
            _MAX_TTL_SECONDS,  # 30 d — верхняя граница
        ],
    )
    def test_valid_values_pass(self, value: int) -> None:
        cfg = PrizeLotConfig.model_validate(self._payload(reserved_ttl_seconds=value))
        assert cfg.reserved_ttl_seconds == value


class TestReservedTtlTypeStrict:
    def test_float_rejected(self) -> None:
        # Pydantic по умолчанию строгая типизация для int полей: float с
        # дробной частью отклоняется (`60.5` → ValidationError); целочисленный
        # float (`60.0`) Pydantic V2 в strict-моделях принимает как int —
        # это поведение по умолчанию, не пишем тест на него, чтобы не
        # переучивать pydantic.
        with pytest.raises(ValidationError, match="reserved_ttl_seconds"):
            PrizeLotConfig.model_validate({"reserved_ttl_seconds": 172_800.5})

    def test_string_rejected(self) -> None:
        # Pydantic V2 по умолчанию НЕ кастит `str → int` (без `coerce_numbers_to_str`).
        # Но "172800"-вид может проходить, проверим явно.
        with pytest.raises(ValidationError, match="reserved_ttl_seconds"):
            PrizeLotConfig.model_validate({"reserved_ttl_seconds": "not-a-number"})

    def test_bool_rejected(self) -> None:
        # `True / False` — это `int` в Python, но Pydantic V2 в strict-режиме
        # не кастит `bool → int`. Подтверждаем для надёжности конфига.
        with pytest.raises(ValidationError, match="reserved_ttl_seconds"):
            PrizeLotConfig.model_validate({"reserved_ttl_seconds": True})

    def test_none_rejected(self) -> None:
        with pytest.raises(ValidationError, match="reserved_ttl_seconds"):
            PrizeLotConfig.model_validate({"reserved_ttl_seconds": None})


class TestRequiredAndExtraForbidden:
    def test_missing_field_rejected(self) -> None:
        with pytest.raises(ValidationError, match="reserved_ttl_seconds"):
            PrizeLotConfig.model_validate({})

    def test_extra_field_rejected(self) -> None:
        # `extra="forbid"` — защита от опечаток / устаревших ключей
        # в `balance.yaml` (например, `reserved_ttl_secondz`).
        with pytest.raises(ValidationError, match="reserved_ttl_secondz"):
            PrizeLotConfig.model_validate(
                {
                    "reserved_ttl_seconds": 172_800,
                    "reserved_ttl_secondz": 1,
                },
            )


class TestFrozen:
    def test_instance_is_frozen(self) -> None:
        cfg = PrizeLotConfig.model_validate({"reserved_ttl_seconds": 172_800})
        with pytest.raises(ValidationError, match="frozen"):
            cfg.reserved_ttl_seconds = 1
