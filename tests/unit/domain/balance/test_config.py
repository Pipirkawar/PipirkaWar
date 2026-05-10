"""Юнит-тесты `BalanceConfig` и подсхем (Спринт 0.2.9)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from pydantic import ValidationError

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    DisplayNameRange,
    ForestDropConfig,
    ForestOutcome,
    ForestRarityWeights,
    ItemEntry,
    Rarity,
    Slot,
)
from tests.unit.domain.balance.factories import (
    build_valid_balance,
    valid_balance_payload,
)

_VALID_DROP_PAYLOAD: dict[str, Any] = {
    "probability_percent": 50,
    "name_share_percent": 5,
    "rarity_weights": {"common": 70, "rare": 25, "epic": 5},
    "slot_weights": {
        "hat": 20,
        "body": 20,
        "legs": 20,
        "boots": 15,
        "ring": 12,
        "chain": 13,
        "right_hand": 0,
        "left_hand": 0,
    },
}
"""Минимальный валидный `forest.drop` для подстановки в `forest`-патчи."""


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
        assert cfg.forest.drop.probability_percent == 50
        assert cfg.forest.drop.rarity_weights.common == 70
        assert cfg.oracle.bonus_max == 20
        assert cfg.referral.on_signup.newbie_bonus_cm == 5
        assert cfg.thickness.cost_base == 1000
        assert cfg.dau_gate.max_dau == 200
        assert cfg.daily_head.schedule_mode == "hybrid"
        assert cfg.content_policy.clan_quotes.mild_profanity is True
        assert len(cfg.items_catalog) == 40
        assert len(cfg.names_catalog) == 30

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
                "drop": _VALID_DROP_PAYLOAD,
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
                "drop": _VALID_DROP_PAYLOAD,
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
                "drop": _VALID_DROP_PAYLOAD,
            }
        )
        with pytest.raises(ValidationError, match="cooldown_min_minutes"):
            BalanceConfig.model_validate(payload)

    def test_drop_field_required(self) -> None:
        payload = _payload_with(
            forest={
                "outcomes": [{"name": "x", "weight": 1, "min": 1, "max": 5}],
                "cooldown_min_minutes": 10,
                "cooldown_max_minutes": 20,
            }
        )
        with pytest.raises(ValidationError):
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


class TestOracleTribeBonusConfig:
    """Бонус-за-племена в `/oracle` (ГДД §11.1, Спринт 3.6-A)."""

    def _oracle_with_tribe(self, **tribe_overrides: Any) -> dict[str, Any]:
        return {
            "cooldown_tz": "Europe/Moscow",
            "bonus_min": 1,
            "bonus_max": 20,
            "distribution": "uniform",
            "tribe_bonus": {
                "enabled": True,
                "cm_per_tribe": 1,
                "cap_cm": 131,
                "min_tribe_size": 4,
            }
            | tribe_overrides,
        }

    def test_defaults_applied_when_section_missing(self) -> None:
        cfg = build_valid_balance()
        assert cfg.oracle.tribe_bonus.enabled is True
        assert cfg.oracle.tribe_bonus.cm_per_tribe == 1
        assert cfg.oracle.tribe_bonus.cap_cm == 131
        assert cfg.oracle.tribe_bonus.min_tribe_size == 4

    def test_full_section_parses(self) -> None:
        payload = _payload_with(oracle=self._oracle_with_tribe())
        cfg = BalanceConfig.model_validate(payload)
        assert cfg.oracle.tribe_bonus.enabled is True
        assert cfg.oracle.tribe_bonus.cm_per_tribe == 1
        assert cfg.oracle.tribe_bonus.cap_cm == 131
        assert cfg.oracle.tribe_bonus.min_tribe_size == 4

    def test_disabled_flag_accepted(self) -> None:
        payload = _payload_with(oracle=self._oracle_with_tribe(enabled=False))
        cfg = BalanceConfig.model_validate(payload)
        assert cfg.oracle.tribe_bonus.enabled is False

    def test_zero_cm_per_tribe_allowed(self) -> None:
        # Допустимо «обнулить» бонус на ивент, не выключая весь модуль.
        payload = _payload_with(oracle=self._oracle_with_tribe(cm_per_tribe=0))
        cfg = BalanceConfig.model_validate(payload)
        assert cfg.oracle.tribe_bonus.cm_per_tribe == 0

    def test_negative_cm_per_tribe_rejected(self) -> None:
        payload = _payload_with(oracle=self._oracle_with_tribe(cm_per_tribe=-1))
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_negative_cap_cm_rejected(self) -> None:
        payload = _payload_with(oracle=self._oracle_with_tribe(cap_cm=-1))
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_min_tribe_size_zero_rejected(self) -> None:
        payload = _payload_with(oracle=self._oracle_with_tribe(min_tribe_size=0))
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_extra_field_rejected(self) -> None:
        oracle = self._oracle_with_tribe()
        oracle["tribe_bonus"]["bogus"] = 1
        payload = _payload_with(oracle=oracle)
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_frozen_cannot_mutate(self) -> None:
        cfg = build_valid_balance()
        with pytest.raises(ValidationError):
            cfg.oracle.tribe_bonus.cm_per_tribe = 999

    def test_total_at_contract_limit_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        # 20 + 131 = 151 — ровно на границе ГДД §11.1, warning не нужен.
        caplog.set_level("WARNING", logger="pipirik_wars.domain.balance.config")
        payload = _payload_with(oracle=self._oracle_with_tribe(cap_cm=131))
        BalanceConfig.model_validate(payload)
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert all("exceeds GDD" not in r.getMessage() for r in warnings)

    def test_total_above_contract_limit_warns(self) -> None:
        # 20 + 200 = 220 > 151 — warning ожидаем (не падаем).
        # Патчим logger напрямую, чтобы не зависеть от состояния propagate-цепочки
        # после других тестов в полном прогоне.
        with patch("pipirik_wars.domain.balance.config._logger.warning") as mock_warning:
            payload = _payload_with(oracle=self._oracle_with_tribe(cap_cm=200))
            BalanceConfig.model_validate(payload)
        assert any(
            "exceeds GDD §11.1 contract" in str(call.args[0])
            for call in mock_warning.call_args_list
        )


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


class TestAnticheatConfig:
    """Юнит-тесты `AnticheatConfig` (Спринт 1.6.B / ГДД §3.3.5)."""

    @staticmethod
    def _valid_payload() -> dict[str, Any]:
        return {
            "daily_cap_cm": 3000,
            "weekly_cap_cm": 14000,
            "soft_ban_duration_days": 14,
            "organic_sources": [
                "forest",
                "oracle",
                "referral_signup",
                "referral_thickness",
                "pvp_reward",
                "caravan_reward",
                "raid_reward",
                "admin_grant",
            ],
            "donate_sources": ["stars_payment", "ton_payment", "usdt_payment"],
        }

    def test_valid(self) -> None:
        cfg = BalanceConfig.model_validate(_payload_with(anticheat=self._valid_payload()))
        assert cfg.anticheat.daily_cap_cm == 3000
        assert cfg.anticheat.weekly_cap_cm == 14000
        assert cfg.anticheat.soft_ban_duration_days == 14
        assert "forest" in {s.value for s in cfg.anticheat.organic_sources}
        assert "stars_payment" in {s.value for s in cfg.anticheat.donate_sources}

    def test_real_balance_yaml_has_anticheat(self) -> None:
        """Реальный `config/balance.yaml` валиден и содержит `anticheat`."""
        path = Path("config/balance.yaml")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cfg = BalanceConfig.model_validate(raw)
        assert cfg.anticheat.daily_cap_cm == 3000
        assert cfg.anticheat.weekly_cap_cm == 14000
        assert cfg.anticheat.soft_ban_duration_days == 14

    def test_zero_daily_cap_rejected(self) -> None:
        payload = self._valid_payload() | {"daily_cap_cm": 0}
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_negative_weekly_cap_rejected(self) -> None:
        payload = self._valid_payload() | {"weekly_cap_cm": -1}
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_zero_soft_ban_duration_rejected(self) -> None:
        payload = self._valid_payload() | {"soft_ban_duration_days": 0}
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_daily_gt_weekly_rejected(self) -> None:
        """Суточный лимит не может быть больше недельного."""
        payload = self._valid_payload() | {
            "daily_cap_cm": 20000,
            "weekly_cap_cm": 14000,
        }
        with pytest.raises(ValidationError, match="daily_cap_cm"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_daily_eq_weekly_allowed(self) -> None:
        """`daily == weekly` — допустимая конфигурация (например, для тестов)."""
        payload = self._valid_payload() | {
            "daily_cap_cm": 14000,
            "weekly_cap_cm": 14000,
        }
        cfg = BalanceConfig.model_validate(_payload_with(anticheat=payload))
        assert cfg.anticheat.daily_cap_cm == cfg.anticheat.weekly_cap_cm

    def test_unknown_source_rejected(self) -> None:
        """Опечатка в имени источника — `forst` вместо `forest`."""
        payload = self._valid_payload() | {
            "organic_sources": ["forst", "oracle"],
        }
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_empty_organic_sources_rejected(self) -> None:
        payload = self._valid_payload() | {"organic_sources": []}
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_empty_donate_sources_rejected(self) -> None:
        payload = self._valid_payload() | {"donate_sources": []}
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_organic_donate_intersection_rejected(self) -> None:
        """Источник не может быть одновременно organic и donate."""
        payload = self._valid_payload() | {
            "organic_sources": ["forest", "oracle", "stars_payment"],
            "donate_sources": ["stars_payment", "ton_payment", "usdt_payment"],
        }
        with pytest.raises(ValidationError, match="disjoint"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_organic_duplicates_rejected(self) -> None:
        payload = self._valid_payload() | {
            "organic_sources": ["forest", "forest", "oracle"],
        }
        with pytest.raises(ValidationError, match="organic_sources contains duplicates"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_donate_duplicates_rejected(self) -> None:
        payload = self._valid_payload() | {
            "donate_sources": ["stars_payment", "stars_payment", "ton_payment"],
        }
        with pytest.raises(ValidationError, match="donate_sources contains duplicates"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_unknown_in_organic_rejected(self) -> None:
        """`unknown` — backfill-маркер, не реальный источник."""
        payload = self._valid_payload() | {
            "organic_sources": ["forest", "unknown"],
        }
        with pytest.raises(ValidationError, match="UNKNOWN"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_unknown_in_donate_rejected(self) -> None:
        payload = self._valid_payload() | {
            "donate_sources": ["stars_payment", "unknown"],
        }
        with pytest.raises(ValidationError, match="UNKNOWN"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_admin_refund_in_organic_rejected(self) -> None:
        """`admin_refund` — отрицательная дельта, не агрегируется."""
        payload = self._valid_payload() | {
            "organic_sources": ["forest", "admin_refund"],
        }
        with pytest.raises(ValidationError, match="ADMIN_REFUND"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_anticheat_section_required(self) -> None:
        """`anticheat` — обязательная секция в `BalanceConfig`."""
        payload = copy.deepcopy(valid_balance_payload())
        del payload["anticheat"]
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_extra_field_in_anticheat_rejected(self) -> None:
        payload = self._valid_payload() | {"unknown_field": 42}
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    # ── Спринт 3.6-A: anticheat.tribe_bonus_sources ──

    def test_tribe_bonus_sources_default_empty_when_omitted(self) -> None:
        """Поле опциональное; отсутствие → пустой tuple, не падаем."""
        payload = self._valid_payload()
        cfg = BalanceConfig.model_validate(_payload_with(anticheat=payload))
        assert cfg.anticheat.tribe_bonus_sources == ()

    def test_tribe_bonus_sources_real_balance_yaml(self) -> None:
        """`config/balance.yaml` декларирует `oracle_tribe_bonus` как audit-only."""
        path = Path("config/balance.yaml")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cfg = BalanceConfig.model_validate(raw)
        values = {s.value for s in cfg.anticheat.tribe_bonus_sources}
        assert "oracle_tribe_bonus" in values

    def test_tribe_bonus_sources_disjoint_from_organic(self) -> None:
        """`tribe_bonus_sources` не пересекается с `organic_sources`."""
        payload = self._valid_payload() | {
            "organic_sources": ["forest", "oracle", "oracle_tribe_bonus"],
            "tribe_bonus_sources": ["oracle_tribe_bonus"],
        }
        with pytest.raises(ValidationError, match="organic_sources and tribe_bonus_sources"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_tribe_bonus_sources_disjoint_from_donate(self) -> None:
        """`tribe_bonus_sources` не пересекается с `donate_sources`."""
        payload = self._valid_payload() | {
            "donate_sources": [
                "stars_payment",
                "ton_payment",
                "usdt_payment",
                "oracle_tribe_bonus",
            ],
            "tribe_bonus_sources": ["oracle_tribe_bonus"],
        }
        with pytest.raises(ValidationError, match="donate_sources and tribe_bonus_sources"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_tribe_bonus_sources_duplicates_rejected(self) -> None:
        payload = self._valid_payload() | {
            "tribe_bonus_sources": ["oracle_tribe_bonus", "oracle_tribe_bonus"],
        }
        with pytest.raises(ValidationError, match="tribe_bonus_sources contains duplicates"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))

    def test_unknown_in_tribe_bonus_sources_rejected(self) -> None:
        payload = self._valid_payload() | {
            "tribe_bonus_sources": ["unknown"],
        }
        with pytest.raises(ValidationError, match="UNKNOWN"):
            BalanceConfig.model_validate(_payload_with(anticheat=payload))


class TestExtraForbid:
    def test_extra_top_level_field_rejected(self) -> None:
        payload = _payload_with(unknown_section={"foo": 1})
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)


class TestForestRarityWeights:
    def test_valid(self) -> None:
        w = ForestRarityWeights.model_validate({"common": 70, "rare": 25, "epic": 5})
        assert w.common == 70
        assert w.rare == 25
        assert w.epic == 5

    @pytest.mark.parametrize("rarity", ["common", "rare", "epic"])
    def test_zero_weight_rejected(self, rarity: str) -> None:
        payload = {"common": 70, "rare": 25, "epic": 5}
        payload[rarity] = 0
        with pytest.raises(ValidationError):
            ForestRarityWeights.model_validate(payload)

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ForestRarityWeights.model_validate({"common": -1, "rare": 25, "epic": 5})

    def test_missing_rarity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ForestRarityWeights.model_validate({"common": 70, "rare": 25})


class TestForestDropConfig:
    def test_valid(self) -> None:
        d = ForestDropConfig.model_validate(_VALID_DROP_PAYLOAD)
        assert d.probability_percent == 50
        assert d.name_share_percent == 5
        assert d.rarity_weights.epic == 5

    @pytest.mark.parametrize("value", [-1, 101])
    def test_probability_out_of_range_rejected(self, value: int) -> None:
        payload = {**_VALID_DROP_PAYLOAD, "probability_percent": value}
        with pytest.raises(ValidationError):
            ForestDropConfig.model_validate(payload)

    @pytest.mark.parametrize("value", [-1, 101])
    def test_name_share_out_of_range_rejected(self, value: int) -> None:
        payload = {**_VALID_DROP_PAYLOAD, "name_share_percent": value}
        with pytest.raises(ValidationError):
            ForestDropConfig.model_validate(payload)

    def test_zero_probability_allowed(self) -> None:
        # 0% — лес временно отключённый по дропу. Это валидное состояние
        # для админ-панели (Phase 2.5+).
        payload = {**_VALID_DROP_PAYLOAD, "probability_percent": 0}
        d = ForestDropConfig.model_validate(payload)
        assert d.probability_percent == 0

    def test_zero_name_share_allowed(self) -> None:
        payload = {**_VALID_DROP_PAYLOAD, "name_share_percent": 0}
        d = ForestDropConfig.model_validate(payload)
        assert d.name_share_percent == 0


class TestItemEntry:
    def test_valid(self) -> None:
        e = ItemEntry.model_validate(
            {"id": "item.hat.x", "slot": "hat", "display_name": "X", "rarity": "common"},
        )
        assert e.id == "item.hat.x"
        assert e.slot is Slot.HAT
        assert e.rarity is Rarity.COMMON

    def test_unknown_slot_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemEntry.model_validate(
                {"id": "item.x", "slot": "shoulder", "display_name": "X", "rarity": "common"},
            )

    def test_unknown_rarity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemEntry.model_validate(
                {"id": "item.x", "slot": "hat", "display_name": "X", "rarity": "legendary"},
            )

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemEntry.model_validate(
                {"id": "", "slot": "hat", "display_name": "X", "rarity": "common"},
            )

    def test_empty_display_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemEntry.model_validate(
                {"id": "item.x", "slot": "hat", "display_name": "", "rarity": "common"},
            )


class TestItemsCatalog:
    def test_below_min_size_rejected(self) -> None:
        # 39 валидных записей — ниже нового минимума (Спринт 3.1-C: ≥ 40).
        items = [
            {
                "id": f"item.hat.test_{i}",
                "slot": "hat",
                "display_name": f"X{i}",
                "rarity": "common" if i < 35 else ("rare" if i < 38 else "epic"),
            }
            for i in range(39)
        ]
        payload = _payload_with(items_catalog=items)
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_duplicate_ids_rejected(self) -> None:
        base = copy.deepcopy(valid_balance_payload())
        base["items_catalog"][0] = {**base["items_catalog"][0], "id": "dup.id"}
        base["items_catalog"][1] = {**base["items_catalog"][1], "id": "dup.id"}
        with pytest.raises(ValidationError, match="duplicate item ids"):
            BalanceConfig.model_validate(base)

    def test_missing_rarity_rejected(self) -> None:
        # Все 40 предметов — common; ни одного rare/epic не остаётся.
        items = [
            {
                "id": f"item.hat.test_{i}",
                "slot": "hat",
                "display_name": f"X{i}",
                "rarity": "common",
            }
            for i in range(40)
        ]
        payload = _payload_with(items_catalog=items)
        with pytest.raises(ValidationError, match="at least one item per rarity"):
            BalanceConfig.model_validate(payload)

    def test_missing_slot_rejected(self) -> None:
        # 40 предметов, покрывают все 3 редкости, но все в одном слоте (`hat`):
        # остальные 7 слотов пусты → валидатор должен отклонить.
        rarities = ["common"] * 30 + ["rare"] * 7 + ["epic"] * 3
        items = [
            {
                "id": f"item.hat.test_{i}",
                "slot": "hat",
                "display_name": f"X{i}",
                "rarity": rarities[i],
            }
            for i in range(40)
        ]
        payload = _payload_with(items_catalog=items)
        with pytest.raises(ValidationError, match="at least one item per slot"):
            BalanceConfig.model_validate(payload)


class TestNamesCatalog:
    def test_below_30_rejected(self) -> None:
        names = [f"Имя-{i}" for i in range(29)]
        payload = _payload_with(names_catalog=names)
        with pytest.raises(ValidationError):
            BalanceConfig.model_validate(payload)

    def test_empty_string_rejected(self) -> None:
        names = [f"Имя-{i}" for i in range(30)]
        names[0] = ""
        payload = _payload_with(names_catalog=names)
        with pytest.raises(ValidationError, match="empty or whitespace"):
            BalanceConfig.model_validate(payload)

    def test_whitespace_only_rejected(self) -> None:
        names = [f"Имя-{i}" for i in range(30)]
        names[5] = "   "
        payload = _payload_with(names_catalog=names)
        with pytest.raises(ValidationError, match="empty or whitespace"):
            BalanceConfig.model_validate(payload)

    def test_duplicates_rejected(self) -> None:
        names = [f"Имя-{i}" for i in range(30)]
        names[10] = names[1]
        payload = _payload_with(names_catalog=names)
        with pytest.raises(ValidationError, match="duplicate names"):
            BalanceConfig.model_validate(payload)
