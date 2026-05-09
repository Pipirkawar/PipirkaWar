"""Тесты `EnchantmentConfig` и его инвариантов (Спринт 3.4-A, A.7).

Покрытие (ГДД §2.8.6):

* реальный `config/balance.yaml` парсится без ошибок (smoke-тест на
  `enchantment`-секцию из 30 уровней + 6 тиров);
* `RegularLevelWeights._validate_sum_to_one` — сумма `success +
  no_effect + drop + destroy == 1.0 ± ε`;
* `BlessedLevelWeights._validate_sum_to_one` — сумма всех 5 = 1.0 ± ε;
* `EnchantmentConfig._validate_max_level_hard` — `max_level == 30` хардкод;
* `EnchantmentConfig._validate_safe_zone_within_max` — safe-zone ≤ max_level;
* `EnchantmentConfig._validate_outcomes_keys_full` — все ключи 0..29
  присутствуют в обеих картах (без дыр / лишних);
* `EnchantmentConfig._validate_safe_zone_zero_drops` — `drop`/`destroy`
  обязаны быть `0.0` на уровнях `< safe_zone_max_level` (для regular —
  `drop`/`destroy`; для blessed — `drop_1`/`drop_2`);
* `EnchantmentConfig._validate_blessed_last_level_no_success_2` —
  `blessed_outcomes_per_level[29].success_2 == 0.0` (запрет `+2 → +31`);
* `EnchantmentConfig._validate_tiers_cover_range` — тиры покрывают
  `[0, max_level]` без дыр / пересечений;
* `EnchantmentTier._validate_range` — `from < to`.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    BlessedLevelWeights,
    EnchantmentConfig,
    EnchantmentTier,
    RegularLevelWeights,
)
from tests.unit.domain.balance.factories import (
    _build_valid_enchantment,
    valid_balance_payload,
)

_REAL_BALANCE_YAML = Path(__file__).resolve().parents[4] / "config" / "balance.yaml"


class TestRealBalanceYamlParses:
    """Реальный `config/balance.yaml` парсится без ошибок (smoke)."""

    def test_balance_yaml_parses(self) -> None:
        raw = yaml.safe_load(_REAL_BALANCE_YAML.read_text(encoding="utf-8"))
        cfg = BalanceConfig.model_validate(raw)
        assert cfg.enchantment.max_level == 30
        assert cfg.enchantment.safe_zone_max_level == 3
        assert len(cfg.enchantment.tiers) == 6
        assert len(cfg.enchantment.regular_outcomes_per_level) == 30
        assert len(cfg.enchantment.blessed_outcomes_per_level) == 30

    def test_enchantment_block_alone_parses(self) -> None:
        cfg = EnchantmentConfig.model_validate(_build_valid_enchantment())
        assert cfg.max_level == 30


class TestRegularLevelWeightsSum:
    def _payload(self, **overrides: float) -> dict[str, float]:
        base = {"success": 0.85, "no_effect": 0.10, "drop": 0.04, "destroy": 0.01}
        return {**base, **overrides}

    def test_valid_sum_one_passes(self) -> None:
        weights = RegularLevelWeights.model_validate(self._payload())
        assert (
            abs(weights.success + weights.no_effect + weights.drop + weights.destroy - 1.0) <= 1e-9
        )

    def test_sum_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sum to 1.0"):
            RegularLevelWeights.model_validate(self._payload(success=0.5))

    def test_sum_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sum to 1.0"):
            RegularLevelWeights.model_validate(self._payload(success=1.0))

    def test_within_epsilon_passes(self) -> None:
        # 0.85 + 0.10 + 0.04 + 0.01 = 1.0 ровно, чуть-чуть отойдём в пределах ε
        # ε = 1e-6 → отклонение 1e-7 проходит, 1e-3 — нет
        weights = RegularLevelWeights.model_validate(
            {"success": 0.8500001, "no_effect": 0.10, "drop": 0.04, "destroy": 0.0099999},
        )
        assert weights.success > 0.85

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegularLevelWeights.model_validate(self._payload(success=-0.1))


class TestBlessedLevelWeightsSum:
    def _payload(self, **overrides: float) -> dict[str, float]:
        base = {
            "success_1": 0.65,
            "success_2": 0.20,
            "no_effect": 0.10,
            "drop_1": 0.04,
            "drop_2": 0.01,
        }
        return {**base, **overrides}

    def test_valid_sum_one_passes(self) -> None:
        weights = BlessedLevelWeights.model_validate(self._payload())
        total = (
            weights.success_1
            + weights.success_2
            + weights.no_effect
            + weights.drop_1
            + weights.drop_2
        )
        assert abs(total - 1.0) <= 1e-9

    def test_sum_not_one_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sum to 1.0"):
            BlessedLevelWeights.model_validate(self._payload(success_1=0.5))


class TestEnchantmentTierRange:
    def _payload(self, **overrides: Any) -> dict[str, Any]:
        base = {
            "name": "easy",
            "from": 3,
            "to": 7,
            "description_key": "tier-easy",
            "emoji": "🟢",
        }
        return {**base, **overrides}

    def test_valid_range_passes(self) -> None:
        tier = EnchantmentTier.model_validate(self._payload())
        assert tier.from_level == 3
        assert tier.to_level == 7

    def test_from_equals_to_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be"):
            EnchantmentTier.model_validate(self._payload(**{"from": 5, "to": 5}))

    def test_from_greater_than_to_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be"):
            EnchantmentTier.model_validate(self._payload(**{"from": 7, "to": 3}))

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EnchantmentTier.model_validate(self._payload(name=""))


class TestEnchantmentConfigInvariants:
    """Cross-row инварианты `EnchantmentConfig`."""

    def _payload(self) -> dict[str, Any]:
        # стартуем с валидного payload-а, ломаем точечно — короче и
        # устойчивее к балансовым правкам в `balance.yaml`.
        return copy.deepcopy(_build_valid_enchantment())

    # ------------ max_level хардкод --------------------------------------

    def test_max_level_must_be_30(self) -> None:
        payload = self._payload()
        payload["max_level"] = 25
        with pytest.raises(ValidationError, match="max_level must be 30"):
            EnchantmentConfig.model_validate(payload)

    def test_max_level_above_30_rejected(self) -> None:
        payload = self._payload()
        payload["max_level"] = 35
        with pytest.raises(ValidationError):
            EnchantmentConfig.model_validate(payload)

    # ------------ safe_zone_max_level --------------------------------------

    def test_safe_zone_above_max_rejected(self) -> None:
        payload = self._payload()
        payload["safe_zone_max_level"] = 31
        with pytest.raises(ValidationError):
            EnchantmentConfig.model_validate(payload)

    def test_safe_zone_zero_allowed(self) -> None:
        """Кроме default=3 по ГДД, safe_zone=0 (no safe-zone) тоже валиден."""
        payload = self._payload()
        payload["safe_zone_max_level"] = 0
        cfg = EnchantmentConfig.model_validate(payload)
        assert cfg.safe_zone_max_level == 0

    # ------------ outcomes_keys_full ---------------------------------------

    def test_missing_level_in_regular_rejected(self) -> None:
        payload = self._payload()
        del payload["regular_outcomes_per_level"]["15"]
        with pytest.raises(ValidationError, match="missing"):
            EnchantmentConfig.model_validate(payload)

    def test_extra_level_in_regular_rejected(self) -> None:
        payload = self._payload()
        payload["regular_outcomes_per_level"]["30"] = {
            "success": 1.0,
            "no_effect": 0.0,
            "drop": 0.0,
            "destroy": 0.0,
        }
        with pytest.raises(ValidationError, match="extra"):
            EnchantmentConfig.model_validate(payload)

    def test_missing_level_in_blessed_rejected(self) -> None:
        payload = self._payload()
        del payload["blessed_outcomes_per_level"]["20"]
        with pytest.raises(ValidationError, match="missing"):
            EnchantmentConfig.model_validate(payload)

    def test_string_keys_coerced_to_int(self) -> None:
        """YAML mapping-keys читаются как `str`, валидатор коэрсит в `int`."""
        cfg = EnchantmentConfig.model_validate(self._payload())
        assert all(isinstance(k, int) for k in cfg.regular_outcomes_per_level)
        assert all(isinstance(k, int) for k in cfg.blessed_outcomes_per_level)

    # ------------ safe-zone-zero -------------------------------------------

    def test_drop_in_safe_zone_rejected_regular(self) -> None:
        payload = self._payload()
        # level=2 в safe-zone (0..3), ставим ненулевой drop
        payload["regular_outcomes_per_level"]["2"] = {
            "success": 0.95,
            "no_effect": 0.0,
            "drop": 0.05,
            "destroy": 0.0,
        }
        with pytest.raises(ValidationError, match="drop/destroy must be 0.0 in safe zone"):
            EnchantmentConfig.model_validate(payload)

    def test_destroy_in_safe_zone_rejected_regular(self) -> None:
        payload = self._payload()
        payload["regular_outcomes_per_level"]["1"] = {
            "success": 0.99,
            "no_effect": 0.0,
            "drop": 0.0,
            "destroy": 0.01,
        }
        with pytest.raises(ValidationError, match="drop/destroy must be 0.0 in safe zone"):
            EnchantmentConfig.model_validate(payload)

    def test_drop_in_safe_zone_rejected_blessed(self) -> None:
        payload = self._payload()
        payload["blessed_outcomes_per_level"]["2"] = {
            "success_1": 0.85,
            "success_2": 0.05,
            "no_effect": 0.0,
            "drop_1": 0.07,
            "drop_2": 0.03,
        }
        with pytest.raises(ValidationError, match="drop_1/drop_2 must be 0.0 in safe zone"):
            EnchantmentConfig.model_validate(payload)

    # ------------ blessed[max_level - 1].success_2 == 0 ----------------------

    def test_blessed_last_level_success_2_must_be_zero(self) -> None:
        payload = self._payload()
        payload["blessed_outcomes_per_level"]["29"] = {
            "success_1": 0.005,
            "success_2": 0.005,  # ← нарушение ГДД §2.8.4
            "no_effect": 0.150,
            "drop_1": 0.420,
            "drop_2": 0.420,
        }
        with pytest.raises(ValidationError, match="success_2 must be 0.0"):
            EnchantmentConfig.model_validate(payload)

    # ------------ tiers cover range ----------------------------------------

    def test_tiers_must_start_at_zero(self) -> None:
        payload = self._payload()
        payload["tiers"][0] = {
            "name": "starter",
            "from": 1,  # ← должна быть 0
            "to": 3,
            "description_key": "tier-starter",
            "emoji": "🟢",
        }
        with pytest.raises(ValidationError, match="must start at 0"):
            EnchantmentConfig.model_validate(payload)

    def test_tiers_must_end_at_max_level(self) -> None:
        payload = self._payload()
        payload["tiers"][-1] = {
            "name": "almost_impossible",
            "from": 25,
            "to": 28,  # ← должна быть 30
            "description_key": "tier-impossible",
            "emoji": "⚫",
        }
        with pytest.raises(ValidationError, match="must end at max_level"):
            EnchantmentConfig.model_validate(payload)

    def test_tiers_with_hole_rejected(self) -> None:
        payload = self._payload()
        # дыра: easy идёт 3..6 (вместо 3..7), hard стартует с 7
        payload["tiers"][1] = {
            "name": "easy",
            "from": 3,
            "to": 6,
            "description_key": "tier-easy",
            "emoji": "🟢",
        }
        with pytest.raises(ValidationError, match="hole/overlap"):
            EnchantmentConfig.model_validate(payload)

    def test_tiers_with_overlap_rejected(self) -> None:
        payload = self._payload()
        # overlap: easy идёт 3..8 (вместо 3..7), hard стартует с 7
        payload["tiers"][1] = {
            "name": "easy",
            "from": 3,
            "to": 8,
            "description_key": "tier-easy",
            "emoji": "🟢",
        }
        with pytest.raises(ValidationError, match="hole/overlap"):
            EnchantmentConfig.model_validate(payload)


class TestExtraFieldsForbidden:
    def test_extra_field_in_enchantment_rejected(self) -> None:
        payload = copy.deepcopy(_build_valid_enchantment())
        payload["foo"] = "bar"
        with pytest.raises(ValidationError, match="extra"):
            EnchantmentConfig.model_validate(payload)

    def test_extra_field_in_regular_weights_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RegularLevelWeights.model_validate(
                {"success": 0.85, "no_effect": 0.10, "drop": 0.04, "destroy": 0.01, "foo": 1},
            )

    def test_extra_field_in_blessed_weights_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            BlessedLevelWeights.model_validate(
                {
                    "success_1": 0.65,
                    "success_2": 0.20,
                    "no_effect": 0.10,
                    "drop_1": 0.04,
                    "drop_2": 0.01,
                    "foo": 1,
                },
            )

    def test_extra_field_in_tier_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            EnchantmentTier.model_validate(
                {
                    "name": "easy",
                    "from": 3,
                    "to": 7,
                    "description_key": "tier-easy",
                    "emoji": "🟢",
                    "foo": "bar",
                },
            )


class TestBalancePayloadIntegration:
    """`valid_balance_payload()` (фабрика) с `enchantment` парсится."""

    def test_full_balance_with_enchantment(self) -> None:
        cfg = BalanceConfig.model_validate(valid_balance_payload())
        assert cfg.enchantment.max_level == 30
        assert cfg.enchantment.safe_zone_max_level == 3

    def test_breaking_enchantment_breaks_balance(self) -> None:
        payload = valid_balance_payload()
        payload["enchantment"]["max_level"] = 25
        with pytest.raises(ValidationError, match="max_level must be 30"):
            BalanceConfig.model_validate(payload)
