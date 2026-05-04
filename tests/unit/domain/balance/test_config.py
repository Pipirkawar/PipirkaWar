"""Юнит-тесты `BalanceConfig` и подсхем (Спринт 0.2.9)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    DisplayNameRange,
    ForestOutcome,
)
from tests.unit.domain.balance.factories import (
    build_valid_balance,
    valid_balance_payload,
)


def _payload_with(**overrides: Any) -> dict[str, Any]:
    """Скопировать валидный payload и наложить partial-патч."""
    base = copy.deepcopy(valid_balance_payload())
    for key, value in overrides.items():
        base[key] = value
    return base


class TestValidBalance:
    def test_full_yaml_parses(self) -> None:
        cfg = build_valid_balance()
        assert cfg.version == 1
        assert len(cfg.display_names) == 3
        assert cfg.forest.outcomes[0].name == "scarce"
        assert cfg.oracle.bonus_max == 20
        assert cfg.referral.on_signup.newbie_bonus_cm == 5
        assert cfg.thickness.cost_base == 1000
        assert cfg.dau_gate.max_dau == 200
        assert cfg.daily_head.schedule_mode == "hybrid"
        assert cfg.content_policy.clan_quotes.mild_profanity is True

    def test_real_balance_yaml_parses(self) -> None:
        """Реальный `config/balance.yaml` валидируется без ошибок."""
        path = Path(__file__).resolve().parents[4] / "config" / "balance.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cfg = BalanceConfig.model_validate(raw)
        assert cfg.version >= 1
        # display_names покрывают всю шкалу — вырожденный smoke-test:
        assert cfg.display_names[0].from_cm == 0
        assert cfg.display_names[-1].to_cm is None

    def test_frozen_cannot_mutate(self) -> None:
        cfg = build_valid_balance()
        with pytest.raises(ValidationError):
            cfg.version = 99


class TestDisplayNameRange:
    def test_from_must_be_less_than_to(self) -> None:
        with pytest.raises(ValidationError):
            DisplayNameRange.model_validate({"from": 10, "to": 5, "name": "X"})

    def test_from_eq_to_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DisplayNameRange.model_validate({"from": 10, "to": 10, "name": "X"})

    def test_negative_from_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DisplayNameRange.model_validate({"from": -1, "to": 5, "name": "X"})

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DisplayNameRange.model_validate({"from": 0, "to": 5, "name": ""})

    def test_to_can_be_null_for_open_tail(self) -> None:
        r = DisplayNameRange.model_validate({"from": 500, "to": None, "name": "X"})
        assert r.to_cm is None

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            DisplayNameRange.model_validate({"from": 0, "to": 5, "name": "X", "extra": True})

    def test_can_construct_with_field_name_too(self) -> None:
        # populate_by_name=True позволяет использовать имя поля,
        # а не только алиас YAML.
        r = DisplayNameRange.model_validate({"from_cm": 0, "to_cm": 10, "name": "X"})
        assert r.from_cm == 0
        assert r.to_cm == 10


class TestDisplayNamesAxisCoverage:
    def test_must_start_at_zero(self) -> None:
        payload = _payload_with(
            display_names=[
                {"from": 5, "to": 10, "name": "A"},
                {"from": 10, "to": None, "name": "B"},
            ]
        )
        with pytest.raises(ValidationError, match="must start at 0"):
            BalanceConfig.model_validate(payload)

    def test_hole_between_ranges_rejected(self) -> None:
        payload = _payload_with(
            display_names=[
                {"from": 0, "to": 10, "name": "A"},
                {"from": 20, "to": None, "name": "B"},
            ]
        )
        with pytest.raises(ValidationError, match="hole/overlap"):
            BalanceConfig.model_validate(payload)

    def test_overlap_between_ranges_rejected(self) -> None:
        payload = _payload_with(
            display_names=[
                {"from": 0, "to": 15, "name": "A"},
                {"from": 10, "to": None, "name": "B"},
            ]
        )
        with pytest.raises(ValidationError, match="hole/overlap"):
            BalanceConfig.model_validate(payload)

    def test_middle_range_with_null_to_rejected(self) -> None:
        payload = _payload_with(
            display_names=[
                {"from": 0, "to": 10, "name": "A"},
                {"from": 10, "to": None, "name": "Mid"},
                {"from": 20, "to": None, "name": "Tail"},
            ]
        )
        with pytest.raises(ValidationError, match="only the last range"):
            BalanceConfig.model_validate(payload)

    def test_last_range_must_have_null_to(self) -> None:
        payload = _payload_with(
            display_names=[
                {"from": 0, "to": 10, "name": "A"},
                {"from": 10, "to": 100, "name": "B"},
            ]
        )
        with pytest.raises(ValidationError, match="last range"):
            BalanceConfig.model_validate(payload)

    def test_empty_display_names_rejected(self) -> None:
        payload = _payload_with(display_names=[])
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)


class TestDisplayNameFor:
    def test_lookup_at_boundaries(self) -> None:
        cfg = build_valid_balance()
        assert cfg.display_name_for(0) == "Пипирик"
        assert cfg.display_name_for(9) == "Пипирик"
        # граница: 10 уже принадлежит следующему ряду (интервал полуоткрытый)
        assert cfg.display_name_for(10) == "Писюнчик"
        assert cfg.display_name_for(29) == "Писюнчик"
        assert cfg.display_name_for(30) == "Батон"
        # хвост to=null: любая большая длина попадает в последний ряд
        assert cfg.display_name_for(10_000) == "Батон"

    def test_negative_length_rejected(self) -> None:
        cfg = build_valid_balance()
        with pytest.raises(ValueError, match="must be >= 0"):
            cfg.display_name_for(-1)


class TestForestOutcome:
    def test_min_must_be_le_max(self) -> None:
        with pytest.raises(ValidationError):
            ForestOutcome.model_validate({"name": "x", "weight": 1, "min": 5, "max": 1})

    def test_zero_weight_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ForestOutcome.model_validate({"name": "x", "weight": 0, "min": 1, "max": 5})

    def test_negative_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ForestOutcome.model_validate({"name": "x", "weight": 1, "min": -1, "max": 5})


class TestForestConfig:
    def test_empty_outcomes_rejected(self) -> None:
        payload = _payload_with(
            forest={
                "outcomes": [],
                "cooldown_min_minutes": 10,
                "cooldown_max_minutes": 20,
            }
        )
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_duplicate_outcome_names_rejected(self) -> None:
        payload = _payload_with(
            forest={
                "outcomes": [
                    {"name": "x", "weight": 1, "min": 1, "max": 5},
                    {"name": "x", "weight": 1, "min": 1, "max": 5},
                ],
                "cooldown_min_minutes": 10,
                "cooldown_max_minutes": 20,
            }
        )
        with pytest.raises(ValidationError, match="duplicate names"):
            BalanceConfig.model_validate(payload)

    def test_cooldown_min_gt_max_rejected(self) -> None:
        payload = _payload_with(
            forest={
                "outcomes": [{"name": "x", "weight": 1, "min": 1, "max": 5}],
                "cooldown_min_minutes": 30,
                "cooldown_max_minutes": 10,
            }
        )
        with pytest.raises(ValidationError, match="cooldown_min_minutes"):
            BalanceConfig.model_validate(payload)


class TestOracleConfig:
    def test_bonus_min_gt_max_rejected(self) -> None:
        payload = _payload_with(
            oracle={
                "cooldown_tz": "Europe/Moscow",
                "bonus_min": 25,
                "bonus_max": 5,
                "distribution": "uniform",
            }
        )
        with pytest.raises(ValidationError, match="bonus_min"):
            BalanceConfig.model_validate(payload)

    def test_zero_bonus_min_rejected(self) -> None:
        payload = _payload_with(
            oracle={
                "cooldown_tz": "Europe/Moscow",
                "bonus_min": 0,
                "bonus_max": 5,
                "distribution": "uniform",
            }
        )
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_unknown_distribution_rejected(self) -> None:
        payload = _payload_with(
            oracle={
                "cooldown_tz": "Europe/Moscow",
                "bonus_min": 1,
                "bonus_max": 5,
                "distribution": "weighted",
            }
        )
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)


class TestReferralConfig:
    def test_milestones_must_be_sorted(self) -> None:
        payload = _payload_with(
            referral={
                "on_signup": {"newbie_bonus_cm": 5, "referrer_bonus_cm": 1},
                "on_thickness_milestones": [
                    {"thickness": 5, "referrer_bonus_cm": 30},
                    {"thickness": 3, "referrer_bonus_cm": 10},
                ],
            }
        )
        with pytest.raises(ValidationError, match="sorted"):
            BalanceConfig.model_validate(payload)

    def test_milestones_no_duplicate_thickness(self) -> None:
        payload = _payload_with(
            referral={
                "on_signup": {"newbie_bonus_cm": 5, "referrer_bonus_cm": 1},
                "on_thickness_milestones": [
                    {"thickness": 3, "referrer_bonus_cm": 10},
                    {"thickness": 3, "referrer_bonus_cm": 30},
                ],
            }
        )
        with pytest.raises(ValidationError, match="duplicate"):
            BalanceConfig.model_validate(payload)

    def test_milestones_can_be_empty(self) -> None:
        payload = _payload_with(
            referral={
                "on_signup": {"newbie_bonus_cm": 0, "referrer_bonus_cm": 0},
                "on_thickness_milestones": [],
            }
        )
        cfg = BalanceConfig.model_validate(payload)
        assert cfg.referral.on_thickness_milestones == ()


class TestThicknessConfig:
    def test_zero_cost_base_rejected(self) -> None:
        payload = _payload_with(
            thickness={
                "cost_base": 0,
                "cost_exponent": 2,
                "unlock_levels": {"forest": 1},
            }
        )
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_empty_unlock_levels_rejected(self) -> None:
        payload = _payload_with(
            thickness={
                "cost_base": 1000,
                "cost_exponent": 2,
                "unlock_levels": {},
            }
        )
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_zero_unlock_level_rejected(self) -> None:
        payload = _payload_with(
            thickness={
                "cost_base": 1000,
                "cost_exponent": 2,
                "unlock_levels": {"forest": 0},
            }
        )
        with pytest.raises(ValidationError, match=">= 1"):
            BalanceConfig.model_validate(payload)


class TestDauGateConfig:
    def test_alert_threshold_above_one_rejected(self) -> None:
        payload = _payload_with(dau_gate={"max_dau": 100, "alert_threshold": 1.5})
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_alert_threshold_zero_rejected(self) -> None:
        payload = _payload_with(dau_gate={"max_dau": 100, "alert_threshold": 0.0})
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)


class TestDailyHeadConfig:
    def test_bonus_min_gt_max_rejected(self) -> None:
        payload = _payload_with(
            daily_head={
                "bonus_min": 30,
                "bonus_max": 5,
                "cooldown_tz": "Europe/Moscow",
                "schedule_mode": "hybrid",
                "cron_random_offset_hours": 24,
                "min_active_members": 5,
                "active_within_days": 7,
                "avoid_last_n": 3,
            }
        )
        with pytest.raises(ValidationError, match="daily_head.bonus_min"):
            BalanceConfig.model_validate(payload)

    def test_unknown_schedule_mode_rejected(self) -> None:
        payload = _payload_with(
            daily_head={
                "bonus_min": 1,
                "bonus_max": 5,
                "cooldown_tz": "Europe/Moscow",
                "schedule_mode": "weird",
                "cron_random_offset_hours": 24,
                "min_active_members": 5,
                "active_within_days": 7,
                "avoid_last_n": 3,
            }
        )
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_cron_offset_above_48_rejected(self) -> None:
        payload = _payload_with(
            daily_head={
                "bonus_min": 1,
                "bonus_max": 5,
                "cooldown_tz": "Europe/Moscow",
                "schedule_mode": "cron",
                "cron_random_offset_hours": 49,
                "min_active_members": 5,
                "active_within_days": 7,
                "avoid_last_n": 3,
            }
        )
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)


class TestExtraForbid:
    def test_extra_top_level_field_rejected(self) -> None:
        payload = _payload_with(unknown_section={"foo": 1})
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)
