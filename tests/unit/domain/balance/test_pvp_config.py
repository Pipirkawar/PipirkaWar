"""Тесты pydantic-схемы `PvpDuel1v1Config` / `PvpConfig` (Спринт 2.1.A + 2.1.F).

Покрытие:

* Валидный default-payload → ок.
* Поля-границы (`rounds`/`hit_pct`/`min_length_cm`/`min_thickness_level`).
* Спринт 2.1.F: `global_lobby_ttl_minutes` / `chat_to_global_promotion_minutes` —
  целочисленные, в диапазоне `[1, 60]`.
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
    PvpMassDuelConfig,
)
from tests.unit.domain.balance.factories import valid_balance_payload


def _build(**overrides: int) -> PvpDuel1v1Config:
    """Хелпер: собирает дефолтный валидный `PvpDuel1v1Config` с возможностью переопределить поля."""

    base: dict[str, int] = {
        "rounds": 3,
        "hit_pct": 10,
        "min_length_cm": 20,
        "min_thickness_level": 2,
        "global_lobby_ttl_minutes": 10,
        "chat_to_global_promotion_minutes": 3,
        "round_timer_seconds": 45,
    }
    base.update(overrides)
    return PvpDuel1v1Config(**base)


class TestPvpDuel1v1Config:
    """Поля и валидаторы duel_1v1."""

    def test_valid_default(self) -> None:
        cfg = PvpDuel1v1Config(
            rounds=3,
            hit_pct=10,
            min_length_cm=20,
            min_thickness_level=2,
            global_lobby_ttl_minutes=10,
            chat_to_global_promotion_minutes=3,
            round_timer_seconds=45,
        )
        assert cfg.rounds == 3
        assert cfg.hit_pct == 10
        assert cfg.min_length_cm == 20
        assert cfg.min_thickness_level == 2
        assert cfg.global_lobby_ttl_minutes == 10
        assert cfg.chat_to_global_promotion_minutes == 3
        assert cfg.round_timer_seconds == 45

    @pytest.mark.parametrize("rounds", [0, -1, 11])
    def test_rounds_out_of_range(self, rounds: int) -> None:
        with pytest.raises(ValidationError):
            _build(rounds=rounds)

    @pytest.mark.parametrize("rounds", [1, 3, 5, 10])
    def test_rounds_in_range(self, rounds: int) -> None:
        cfg = _build(rounds=rounds)
        assert cfg.rounds == rounds

    @pytest.mark.parametrize("hit_pct", [-1, 101, 200])
    def test_hit_pct_out_of_range(self, hit_pct: int) -> None:
        with pytest.raises(ValidationError):
            _build(hit_pct=hit_pct)

    @pytest.mark.parametrize("hit_pct", [0, 10, 50, 100])
    def test_hit_pct_in_range(self, hit_pct: int) -> None:
        cfg = _build(hit_pct=hit_pct)
        assert cfg.hit_pct == hit_pct

    def test_min_length_cm_negative(self) -> None:
        with pytest.raises(ValidationError):
            _build(min_length_cm=-1)

    def test_min_thickness_level_zero(self) -> None:
        with pytest.raises(ValidationError):
            _build(min_thickness_level=0)

    @pytest.mark.parametrize("value", [0, -1, 61, 100])
    def test_global_lobby_ttl_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            _build(global_lobby_ttl_minutes=value)

    @pytest.mark.parametrize("value", [1, 5, 10, 60])
    def test_global_lobby_ttl_in_range(self, value: int) -> None:
        cfg = _build(global_lobby_ttl_minutes=value)
        assert cfg.global_lobby_ttl_minutes == value

    @pytest.mark.parametrize("value", [0, -1, 61, 100])
    def test_chat_to_global_promotion_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            _build(chat_to_global_promotion_minutes=value)

    @pytest.mark.parametrize("value", [1, 3, 30, 60])
    def test_chat_to_global_promotion_in_range(self, value: int) -> None:
        cfg = _build(chat_to_global_promotion_minutes=value)
        assert cfg.chat_to_global_promotion_minutes == value

    @pytest.mark.parametrize("value", [29, 0, -1, 61, 100])
    def test_round_timer_seconds_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            _build(round_timer_seconds=value)

    @pytest.mark.parametrize("value", [30, 45, 60])
    def test_round_timer_seconds_in_range(self, value: int) -> None:
        cfg = _build(round_timer_seconds=value)
        assert cfg.round_timer_seconds == value

    def test_frozen(self) -> None:
        cfg = _build()
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
                    "global_lobby_ttl_minutes": 10,
                    "chat_to_global_promotion_minutes": 3,
                    "round_timer_seconds": 45,
                    "unknown_field": 42,
                }
            )

    def test_global_lobby_ttl_required(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PvpDuel1v1Config.model_validate(
                {
                    "rounds": 3,
                    "hit_pct": 10,
                    "min_length_cm": 20,
                    "min_thickness_level": 2,
                    "chat_to_global_promotion_minutes": 3,
                    "round_timer_seconds": 45,
                }
            )
        assert "global_lobby_ttl_minutes" in str(exc_info.value)

    def test_chat_to_global_promotion_required(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PvpDuel1v1Config.model_validate(
                {
                    "rounds": 3,
                    "hit_pct": 10,
                    "min_length_cm": 20,
                    "min_thickness_level": 2,
                    "global_lobby_ttl_minutes": 10,
                }
            )
        assert "chat_to_global_promotion_minutes" in str(exc_info.value)


def _build_mass(**overrides: int) -> PvpMassDuelConfig:
    """Хелпер: собирает валидный `PvpMassDuelConfig`."""

    base: dict[str, int] = {
        "cooldown_hours": 6,
        "min_length_cm": 20,
        "min_thickness_level": 2,
        "min_clan_members": 1,
        "move_timer_seconds": 180,
    }
    base.update(overrides)
    return PvpMassDuelConfig(**base)


class TestPvpMassDuelConfig:
    """Поля и валидаторы массового PvP (Спринт 2.2.B, ГДД §7.2)."""

    def test_valid_default(self) -> None:
        cfg = _build_mass()
        assert cfg.cooldown_hours == 6
        assert cfg.min_length_cm == 20
        assert cfg.min_thickness_level == 2
        assert cfg.min_clan_members == 1
        assert cfg.move_timer_seconds == 180

    @pytest.mark.parametrize("value", [59, 0, -1, 601, 1000])
    def test_move_timer_seconds_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            _build_mass(move_timer_seconds=value)

    @pytest.mark.parametrize("value", [60, 180, 300, 600])
    def test_move_timer_seconds_in_range(self, value: int) -> None:
        cfg = _build_mass(move_timer_seconds=value)
        assert cfg.move_timer_seconds == value

    @pytest.mark.parametrize("value", [0, -1, 73, 200])
    def test_cooldown_hours_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            _build_mass(cooldown_hours=value)

    @pytest.mark.parametrize("value", [1, 6, 24, 72])
    def test_cooldown_hours_in_range(self, value: int) -> None:
        cfg = _build_mass(cooldown_hours=value)
        assert cfg.cooldown_hours == value

    def test_min_length_cm_negative(self) -> None:
        with pytest.raises(ValidationError):
            _build_mass(min_length_cm=-1)

    @pytest.mark.parametrize("value", [0, 20, 100])
    def test_min_length_cm_in_range(self, value: int) -> None:
        cfg = _build_mass(min_length_cm=value)
        assert cfg.min_length_cm == value

    def test_min_thickness_level_zero(self) -> None:
        with pytest.raises(ValidationError):
            _build_mass(min_thickness_level=0)

    @pytest.mark.parametrize("value", [0, -1, 101, 200])
    def test_min_clan_members_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            _build_mass(min_clan_members=value)

    @pytest.mark.parametrize("value", [1, 5, 20, 100])
    def test_min_clan_members_in_range(self, value: int) -> None:
        cfg = _build_mass(min_clan_members=value)
        assert cfg.min_clan_members == value

    def test_frozen(self) -> None:
        cfg = _build_mass()
        with pytest.raises(ValidationError):
            cfg.cooldown_hours = 12

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            PvpMassDuelConfig.model_validate(
                {
                    "cooldown_hours": 6,
                    "min_length_cm": 20,
                    "min_thickness_level": 2,
                    "min_clan_members": 1,
                    "move_timer_seconds": 180,
                    "unknown_field": 42,
                }
            )


class TestPvpConfig:
    """Wrapper-конфиг."""

    def test_valid_with_duel_1v1_and_mass_duel(self) -> None:
        cfg = PvpConfig(duel_1v1=_build(), mass_duel=_build_mass())
        assert cfg.duel_1v1.rounds == 3
        assert cfg.mass_duel.cooldown_hours == 6

    def test_missing_duel_1v1(self) -> None:
        with pytest.raises(ValidationError):
            PvpConfig.model_validate({"mass_duel": _build_mass().model_dump()})

    def test_missing_mass_duel(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PvpConfig.model_validate({"duel_1v1": _build().model_dump()})
        assert "mass_duel" in str(exc_info.value)


class TestBalanceConfigPvpRequired:
    """`BalanceConfig` требует секцию `pvp`."""

    def test_default_payload_includes_pvp(self) -> None:
        cfg = BalanceConfig.model_validate(valid_balance_payload())
        assert cfg.pvp.duel_1v1.rounds == 3
        assert cfg.pvp.duel_1v1.hit_pct == 10
        assert cfg.pvp.duel_1v1.min_length_cm == 20
        assert cfg.pvp.duel_1v1.min_thickness_level == 2
        assert cfg.pvp.duel_1v1.global_lobby_ttl_minutes == 10
        assert cfg.pvp.duel_1v1.chat_to_global_promotion_minutes == 3
        assert cfg.pvp.duel_1v1.round_timer_seconds == 45
        assert cfg.pvp.mass_duel.cooldown_hours == 6
        assert cfg.pvp.mass_duel.min_length_cm == 20
        assert cfg.pvp.mass_duel.min_thickness_level == 2
        assert cfg.pvp.mass_duel.min_clan_members == 1
        assert cfg.pvp.mass_duel.move_timer_seconds == 180

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
