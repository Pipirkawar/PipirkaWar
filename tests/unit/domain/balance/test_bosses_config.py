"""Тесты `BossesConfig` (Спринт 3.3-A)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    BossesConfig,
    BossScrollDropConfig,
)
from tests.unit.domain.balance.factories import valid_balance_payload


class TestBossesConfig:
    def _payload(self) -> dict[str, Any]:
        return {
            "min_thickness_level_summoner": 9,
            "min_thickness_level_raider": 4,
            "min_length_cm": 20,
            "lobby_minutes": 20,
            "summon_cooldown_hours": 4,
            "top_n_pool": 30,
            "victory_threshold_cm": 10,
            "round_min_seconds": 20,
            "round_max_seconds": 60,
            "base_damage_cm": 5,
            "bot_play_chance": 1.0,
            "scroll_drop": {"regular": 0.05, "blessed": 0.005},
        }

    def test_valid_payload_parses(self) -> None:
        cfg = BossesConfig.model_validate(self._payload())
        assert cfg.min_thickness_level_summoner == 9
        assert cfg.min_thickness_level_raider == 4
        assert cfg.min_length_cm == 20
        assert cfg.lobby_minutes == 20
        assert cfg.summon_cooldown_hours == 4
        assert cfg.top_n_pool == 30
        assert cfg.victory_threshold_cm == 10
        assert cfg.round_min_seconds == 20
        assert cfg.round_max_seconds == 60
        assert cfg.base_damage_cm == 5
        assert cfg.bot_play_chance == 1.0
        assert cfg.scroll_drop.regular == 0.05
        assert cfg.scroll_drop.blessed == 0.005

    def test_frozen(self) -> None:
        cfg = BossesConfig.model_validate(self._payload())
        with pytest.raises(ValidationError):
            cfg.min_length_cm = 30

    def test_extra_field_rejected(self) -> None:
        payload = {**self._payload(), "extra_field": "bad"}
        with pytest.raises(ValidationError, match="extra"):
            BossesConfig.model_validate(payload)

    @pytest.mark.parametrize(
        "field",
        [
            "min_thickness_level_summoner",
            "min_thickness_level_raider",
            "min_length_cm",
            "lobby_minutes",
            "top_n_pool",
            "victory_threshold_cm",
            "round_min_seconds",
            "round_max_seconds",
        ],
    )
    def test_strictly_positive_fields_reject_zero(self, field: str) -> None:
        payload = self._payload()
        payload[field] = 0
        with pytest.raises(ValidationError):
            BossesConfig.model_validate(payload)

    @pytest.mark.parametrize(
        "field",
        [
            "min_thickness_level_summoner",
            "min_thickness_level_raider",
            "min_length_cm",
            "lobby_minutes",
            "top_n_pool",
            "victory_threshold_cm",
            "round_min_seconds",
            "round_max_seconds",
        ],
    )
    def test_strictly_positive_fields_reject_negative(self, field: str) -> None:
        payload = self._payload()
        payload[field] = -1
        with pytest.raises(ValidationError):
            BossesConfig.model_validate(payload)

    @pytest.mark.parametrize(
        "field",
        ["summon_cooldown_hours", "base_damage_cm"],
    )
    def test_non_negative_fields_accept_zero(self, field: str) -> None:
        payload = self._payload()
        payload[field] = 0
        cfg = BossesConfig.model_validate(payload)
        assert getattr(cfg, field) == 0

    @pytest.mark.parametrize(
        "field",
        ["summon_cooldown_hours", "base_damage_cm"],
    )
    def test_non_negative_fields_reject_negative(self, field: str) -> None:
        payload = self._payload()
        payload[field] = -1
        with pytest.raises(ValidationError):
            BossesConfig.model_validate(payload)

    def test_round_min_must_not_exceed_max(self) -> None:
        payload = self._payload()
        payload["round_min_seconds"] = 60
        payload["round_max_seconds"] = 30
        with pytest.raises(ValidationError, match="round_min_seconds"):
            BossesConfig.model_validate(payload)

    def test_round_min_equals_max_allowed(self) -> None:
        payload = self._payload()
        payload["round_min_seconds"] = 30
        payload["round_max_seconds"] = 30
        cfg = BossesConfig.model_validate(payload)
        assert cfg.round_min_seconds == 30
        assert cfg.round_max_seconds == 30

    def test_summoner_threshold_must_not_be_below_raider(self) -> None:
        payload = self._payload()
        payload["min_thickness_level_summoner"] = 3
        payload["min_thickness_level_raider"] = 4
        with pytest.raises(ValidationError, match="min_thickness_level_summoner"):
            BossesConfig.model_validate(payload)

    def test_bot_play_chance_above_one_rejected(self) -> None:
        payload = self._payload()
        payload["bot_play_chance"] = 1.5
        with pytest.raises(ValidationError):
            BossesConfig.model_validate(payload)

    def test_bot_play_chance_negative_rejected(self) -> None:
        payload = self._payload()
        payload["bot_play_chance"] = -0.1
        with pytest.raises(ValidationError):
            BossesConfig.model_validate(payload)


class TestBossScrollDropConfig:
    def test_valid(self) -> None:
        cfg = BossScrollDropConfig(regular=0.05, blessed=0.005)
        assert cfg.regular == 0.05
        assert cfg.blessed == 0.005

    def test_zero_allowed(self) -> None:
        cfg = BossScrollDropConfig(regular=0.0, blessed=0.0)
        assert cfg.regular == 0.0
        assert cfg.blessed == 0.0

    def test_one_allowed(self) -> None:
        cfg = BossScrollDropConfig(regular=1.0, blessed=1.0)
        assert cfg.regular == 1.0

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BossScrollDropConfig(regular=-0.01, blessed=0.005)

    def test_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BossScrollDropConfig(regular=0.05, blessed=1.5)

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            BossScrollDropConfig.model_validate({"regular": 0.05, "blessed": 0.005, "epic": 0.0001})


class TestBalanceConfigIntegration:
    def test_bosses_required_in_balance_config(self) -> None:
        payload = valid_balance_payload()
        del payload["bosses"]
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_bosses_section_loads_with_balance(self) -> None:
        payload = valid_balance_payload()
        cfg = BalanceConfig.model_validate(payload)
        assert cfg.bosses.min_thickness_level_summoner == 9
        assert cfg.bosses.lobby_minutes == 20
        assert cfg.bosses.summon_cooldown_hours == 4
        assert cfg.bosses.scroll_drop.regular == 0.05

    def test_full_balance_yaml_loads(self) -> None:
        """Smoke: фактический config/balance.yaml после добавления bosses."""
        yaml_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "balance.yaml"
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        cfg = BalanceConfig.model_validate(raw)
        assert cfg.bosses.min_thickness_level_summoner == 9
        assert cfg.bosses.lobby_minutes == 20
        assert cfg.bosses.summon_cooldown_hours == 4
        assert cfg.bosses.top_n_pool == 30
        assert cfg.bosses.scroll_drop.regular == 0.05
        assert cfg.bosses.scroll_drop.blessed == 0.005

    def test_independent_bosses_clone(self) -> None:
        payload = valid_balance_payload()
        cloned = copy.deepcopy(payload)
        cfg = BalanceConfig.model_validate(cloned)
        assert cfg.bosses.base_damage_cm == 5
