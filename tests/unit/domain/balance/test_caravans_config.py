"""Тесты `CaravansConfig` (Спринт 3.2-A)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    CaravanRewardMultipliers,
    CaravansConfig,
)
from tests.unit.domain.balance.factories import valid_balance_payload


class TestCaravansConfig:
    def _payload(self) -> dict[str, Any]:
        return {
            "min_thickness_level_leader": 7,
            "min_thickness_level_raider": 5,
            "min_length_cm": 20,
            "min_length_after_contribution_cm": 20,
            "lobby_minutes": 20,
            "battle_minutes": 60,
            "clan_cooldown_hours": 12,
            "max_raiders_per_caravaneer": 4,
            "max_defenders_per_caravaneer": 2,
            "base_reward_cm": 5,
            "reward_multipliers": {
                "leader": 4,
                "caravaneer": 3,
                "defender": 1,
                "raider": 0,
            },
            "clan_bonus_cm": 1,
        }

    def test_valid_payload_parses(self) -> None:
        cfg = CaravansConfig.model_validate(self._payload())
        assert cfg.min_thickness_level_leader == 7
        assert cfg.lobby_minutes == 20
        assert cfg.battle_minutes == 60
        assert cfg.reward_multipliers.leader == 4
        assert cfg.reward_multipliers.caravaneer == 3
        assert cfg.reward_multipliers.defender == 1
        assert cfg.reward_multipliers.raider == 0
        assert cfg.clan_bonus_cm == 1

    def test_frozen(self) -> None:
        cfg = CaravansConfig.model_validate(self._payload())
        with pytest.raises(ValidationError):
            cfg.min_length_cm = 30

    def test_extra_field_rejected(self) -> None:
        payload = {**self._payload(), "extra_field": "bad"}
        with pytest.raises(ValidationError, match="extra"):
            CaravansConfig.model_validate(payload)

    @pytest.mark.parametrize(
        "field",
        [
            "min_thickness_level_leader",
            "min_thickness_level_raider",
            "min_length_cm",
            "min_length_after_contribution_cm",
            "lobby_minutes",
            "battle_minutes",
        ],
    )
    def test_strictly_positive_fields_reject_zero(self, field: str) -> None:
        payload = self._payload()
        payload[field] = 0
        with pytest.raises(ValidationError):
            CaravansConfig.model_validate(payload)

    @pytest.mark.parametrize(
        "field",
        [
            "min_thickness_level_leader",
            "min_thickness_level_raider",
            "min_length_cm",
            "min_length_after_contribution_cm",
            "lobby_minutes",
            "battle_minutes",
        ],
    )
    def test_strictly_positive_fields_reject_negative(self, field: str) -> None:
        payload = self._payload()
        payload[field] = -1
        with pytest.raises(ValidationError):
            CaravansConfig.model_validate(payload)

    @pytest.mark.parametrize(
        "field",
        [
            "clan_cooldown_hours",
            "max_raiders_per_caravaneer",
            "max_defenders_per_caravaneer",
            "base_reward_cm",
            "clan_bonus_cm",
        ],
    )
    def test_non_negative_fields_accept_zero(self, field: str) -> None:
        payload = self._payload()
        payload[field] = 0
        cfg = CaravansConfig.model_validate(payload)
        assert getattr(cfg, field) == 0

    @pytest.mark.parametrize(
        "field",
        [
            "clan_cooldown_hours",
            "max_raiders_per_caravaneer",
            "max_defenders_per_caravaneer",
            "base_reward_cm",
            "clan_bonus_cm",
        ],
    )
    def test_non_negative_fields_reject_negative(self, field: str) -> None:
        payload = self._payload()
        payload[field] = -1
        with pytest.raises(ValidationError):
            CaravansConfig.model_validate(payload)


class TestCaravanRewardMultipliers:
    def test_all_multipliers_can_be_zero(self) -> None:
        m = CaravanRewardMultipliers(leader=0, caravaneer=0, defender=0, raider=0)
        assert m.leader == 0

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CaravanRewardMultipliers(leader=-1, caravaneer=3, defender=1, raider=0)

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            CaravanRewardMultipliers.model_validate(
                {
                    "leader": 4,
                    "caravaneer": 3,
                    "defender": 1,
                    "raider": 0,
                    "ataman_bonus": 5,
                }
            )


class TestBalanceConfigIntegration:
    def test_caravans_required_in_balance_config(self) -> None:
        payload = valid_balance_payload()
        del payload["caravans"]
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_caravans_section_loads_with_balance(self) -> None:
        payload = valid_balance_payload()
        cfg = BalanceConfig.model_validate(payload)
        assert cfg.caravans.min_thickness_level_leader == 7
        assert cfg.caravans.lobby_minutes == 20
        assert cfg.caravans.battle_minutes == 60
        assert cfg.caravans.reward_multipliers.leader == 4

    def test_full_balance_yaml_loads(self) -> None:
        """Smoke: фактический config/balance.yaml после добавления caravans."""
        yaml_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "balance.yaml"
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        cfg = BalanceConfig.model_validate(raw)
        assert cfg.caravans.lobby_minutes == 20
        assert cfg.caravans.battle_minutes == 60
        assert cfg.caravans.clan_cooldown_hours == 12

    def test_independent_caravans_clone(self) -> None:
        """`copy.deepcopy(payload)` не должен ломать валидацию."""
        payload = valid_balance_payload()
        cloned = copy.deepcopy(payload)
        cfg = BalanceConfig.model_validate(cloned)
        assert cfg.caravans.base_reward_cm == 5
