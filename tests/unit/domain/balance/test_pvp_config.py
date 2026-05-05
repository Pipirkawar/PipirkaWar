"""Тесты pydantic-схемы `PvpDuel1v1Config` / `PvpConfig` (Спринт 2.1.A).

Покрытие:

* Валидный default-payload → ок.
* Поля-границы (`rounds`/`hit_pct`/`min_length_cm`/`min_thickness_level`).
* Frozen/extra=forbid: попытка мутации и неизвестных ключей — ошибка.
* `BalanceConfig.pvp` — обязательное поле (без него `BalanceConfig` не валидируется).
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    PvpConfig,
    PvpDuel1v1Config,
)
from tests.unit.domain.balance.factories import valid_balance_payload


class TestPvpDuel1v1Config:
    """Поля и валидаторы duel_1v1."""

    def test_valid_default(self) -> None:
        cfg = PvpDuel1v1Config(rounds=3, hit_pct=10, min_length_cm=20, min_thickness_level=2)
        assert cfg.rounds == 3
        assert cfg.hit_pct == 10
        assert cfg.min_length_cm == 20
        assert cfg.min_thickness_level == 2

    @pytest.mark.parametrize("rounds", [0, -1, 11])
    def test_rounds_out_of_range(self, rounds: int) -> None:
        with pytest.raises(ValidationError):
            PvpDuel1v1Config(rounds=rounds, hit_pct=10, min_length_cm=20, min_thickness_level=2)

    @pytest.mark.parametrize("rounds", [1, 3, 5, 10])
    def test_rounds_in_range(self, rounds: int) -> None:
        cfg = PvpDuel1v1Config(rounds=rounds, hit_pct=10, min_length_cm=20, min_thickness_level=2)
        assert cfg.rounds == rounds

    @pytest.mark.parametrize("hit_pct", [-1, 101, 200])
    def test_hit_pct_out_of_range(self, hit_pct: int) -> None:
        with pytest.raises(ValidationError):
            PvpDuel1v1Config(rounds=3, hit_pct=hit_pct, min_length_cm=20, min_thickness_level=2)

    @pytest.mark.parametrize("hit_pct", [0, 10, 50, 100])
    def test_hit_pct_in_range(self, hit_pct: int) -> None:
        cfg = PvpDuel1v1Config(rounds=3, hit_pct=hit_pct, min_length_cm=20, min_thickness_level=2)
        assert cfg.hit_pct == hit_pct

    def test_min_length_cm_negative(self) -> None:
        with pytest.raises(ValidationError):
            PvpDuel1v1Config(rounds=3, hit_pct=10, min_length_cm=-1, min_thickness_level=2)

    def test_min_thickness_level_zero(self) -> None:
        with pytest.raises(ValidationError):
            PvpDuel1v1Config(rounds=3, hit_pct=10, min_length_cm=20, min_thickness_level=0)

    def test_frozen(self) -> None:
        cfg = PvpDuel1v1Config(rounds=3, hit_pct=10, min_length_cm=20, min_thickness_level=2)
        with pytest.raises(ValidationError):
            cfg.rounds = 5

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            PvpDuel1v1Config.model_validate(
                {
                    "rounds": 3,
                    "hit_pct": 10,
                    "min_length_cm": 20,
                    "min_thickness_level": 2,
                    "unknown_field": 42,
                }
            )


class TestPvpConfig:
    """Wrapper-конфиг."""

    def test_valid_with_duel_1v1(self) -> None:
        cfg = PvpConfig(
            duel_1v1=PvpDuel1v1Config(rounds=3, hit_pct=10, min_length_cm=20, min_thickness_level=2)
        )
        assert cfg.duel_1v1.rounds == 3

    def test_missing_duel_1v1(self) -> None:
        with pytest.raises(ValidationError):
            PvpConfig.model_validate({})


class TestBalanceConfigPvpRequired:
    """`BalanceConfig` требует секцию `pvp`."""

    def test_default_payload_includes_pvp(self) -> None:
        cfg = BalanceConfig.model_validate(valid_balance_payload())
        assert cfg.pvp.duel_1v1.rounds == 3
        assert cfg.pvp.duel_1v1.hit_pct == 10
        assert cfg.pvp.duel_1v1.min_length_cm == 20
        assert cfg.pvp.duel_1v1.min_thickness_level == 2

    def test_balance_config_rejects_missing_pvp(self) -> None:
        payload = copy.deepcopy(valid_balance_payload())
        del payload["pvp"]
        with pytest.raises(ValidationError) as exc_info:
            BalanceConfig.model_validate(payload)
        assert "pvp" in str(exc_info.value)

    def test_balance_config_rejects_invalid_pvp(self) -> None:
        payload = copy.deepcopy(valid_balance_payload())
        payload["pvp"]["duel_1v1"]["hit_pct"] = 150  # > 100
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)
