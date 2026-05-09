"""Тесты pydantic-инвариантов `RouletteFreeConfig` (Спринт 3.5-A, A.2).

Структурно копия `test_enchantment_config.py` (Спринт 3.4-A): сначала
smoke-тест на парсинг реального `config/balance.yaml::roulette.free`,
затем точечные тесты на каждый model_validator (`mode="after"`).

Покрытие (ГДД §12.4.2):

* реальный `config/balance.yaml::roulette` парсится без ошибок;
* `_validate_outcome_weights_sum_to_one` — сумма весов == 1.0 ± ε;
* `_validate_outcome_kinds_unique` — без дублей по kind;
* `_validate_outcome_kinds_full` — все 5 RouletteOutcomeKind присутствуют;
* `_validate_bucket_weights_sum_to_one` — сумма весов бакетов == 1.0 ± ε;
* `_validate_bucket_names_unique` — без дублей по имени бакета;
* `RouletteLengthBucket._validate_min_max` — `min_cm <= max_cm`;
* `extra="forbid"` — лишние поля отвергаются.
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
    RouletteConfig,
    RouletteFreeConfig,
    RouletteLengthBucket,
    RouletteOutcomeKind,
    RouletteOutcomeWeight,
)
from tests.unit.domain.balance.factories import (
    _build_valid_roulette,
    valid_balance_payload,
)

_REAL_BALANCE_YAML = Path(__file__).resolve().parents[4] / "config" / "balance.yaml"


class TestRealBalanceYamlParses:
    """Реальный `config/balance.yaml::roulette` парсится без ошибок (smoke)."""

    def test_balance_yaml_parses(self) -> None:
        raw = yaml.safe_load(_REAL_BALANCE_YAML.read_text(encoding="utf-8"))
        cfg = BalanceConfig.model_validate(raw)
        assert cfg.roulette.free.cost_cm == 100
        assert cfg.roulette.free.min_thickness_level == 2
        assert len(cfg.roulette.free.outcomes) == 5
        assert {o.kind for o in cfg.roulette.free.outcomes} == set(RouletteOutcomeKind)
        assert len(cfg.roulette.free.length_buckets) == 4

    def test_roulette_block_alone_parses(self) -> None:
        cfg = RouletteConfig.model_validate(_build_valid_roulette())
        assert cfg.free.cost_cm == 100


class TestOutcomeWeightsSumToOne:
    @staticmethod
    def _payload(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = copy.deepcopy(_build_valid_roulette()["free"])
        base.update(overrides)
        return base

    def test_default_passes(self) -> None:
        cfg = RouletteFreeConfig.model_validate(self._payload())
        total = sum(o.weight for o in cfg.outcomes)
        assert abs(total - 1.0) <= 1e-9

    def test_sum_below_one_rejected(self) -> None:
        bad = self._payload(
            outcomes=[
                {"kind": "length", "weight": 0.5},
                {"kind": "item", "weight": 0.1},
                {"kind": "scroll_regular", "weight": 0.04},
                {"kind": "scroll_blessed", "weight": 0.005},
                {"kind": "crypto_lot", "weight": 0.005},
            ],
        )
        with pytest.raises(ValidationError, match="must sum to 1.0"):
            RouletteFreeConfig.model_validate(bad)

    def test_sum_above_one_rejected(self) -> None:
        bad = self._payload(
            outcomes=[
                {"kind": "length", "weight": 0.95},
                {"kind": "item", "weight": 0.1},
                {"kind": "scroll_regular", "weight": 0.04},
                {"kind": "scroll_blessed", "weight": 0.005},
                {"kind": "crypto_lot", "weight": 0.005},
            ],
        )
        with pytest.raises(ValidationError, match="must sum to 1.0"):
            RouletteFreeConfig.model_validate(bad)

    def test_within_epsilon_passes(self) -> None:
        # Small float drift below 1e-6 stays valid.
        ok = self._payload(
            outcomes=[
                {"kind": "length", "weight": 0.8500001},
                {"kind": "item", "weight": 0.1},
                {"kind": "scroll_regular", "weight": 0.04},
                {"kind": "scroll_blessed", "weight": 0.005},
                {"kind": "crypto_lot", "weight": 0.0049999},
            ],
        )
        cfg = RouletteFreeConfig.model_validate(ok)
        assert cfg.cost_cm == 100


class TestOutcomeKindsUnique:
    def test_duplicate_kinds_rejected(self) -> None:
        bad = copy.deepcopy(_build_valid_roulette()["free"])
        bad["outcomes"] = [
            {"kind": "length", "weight": 0.5},
            {"kind": "length", "weight": 0.350},
            {"kind": "item", "weight": 0.1},
            {"kind": "scroll_regular", "weight": 0.04},
            {"kind": "scroll_blessed", "weight": 0.005},
            {"kind": "crypto_lot", "weight": 0.005},
        ]
        with pytest.raises(ValidationError, match="duplicate kinds"):
            RouletteFreeConfig.model_validate(bad)


class TestOutcomeKindsFull:
    def test_missing_kind_rejected(self) -> None:
        # Убираем `crypto_lot`, переносим его вес на `length` —
        # сумма == 1.0, но не все 5 типов представлены.
        bad = copy.deepcopy(_build_valid_roulette()["free"])
        bad["outcomes"] = [
            {"kind": "length", "weight": 0.855},
            {"kind": "item", "weight": 0.1},
            {"kind": "scroll_regular", "weight": 0.04},
            {"kind": "scroll_blessed", "weight": 0.005},
        ]
        with pytest.raises(ValidationError, match="must list all 5 RouletteOutcomeKind"):
            RouletteFreeConfig.model_validate(bad)


class TestBucketWeightsSumToOne:
    def test_below_one_rejected(self) -> None:
        bad = copy.deepcopy(_build_valid_roulette()["free"])
        bad["length_buckets"] = [
            {"name": "small", "min_cm": 10, "max_cm": 50, "weight": 0.5},
            {"name": "medium", "min_cm": 50, "max_cm": 150, "weight": 0.25},
        ]
        with pytest.raises(ValidationError, match="length_buckets weights must sum to 1.0"):
            RouletteFreeConfig.model_validate(bad)

    def test_above_one_rejected(self) -> None:
        bad = copy.deepcopy(_build_valid_roulette()["free"])
        bad["length_buckets"] = [
            {"name": "small", "min_cm": 10, "max_cm": 50, "weight": 0.7},
            {"name": "medium", "min_cm": 50, "max_cm": 150, "weight": 0.4},
        ]
        with pytest.raises(ValidationError, match="length_buckets weights must sum to 1.0"):
            RouletteFreeConfig.model_validate(bad)


class TestBucketNamesUnique:
    def test_duplicate_names_rejected(self) -> None:
        bad = copy.deepcopy(_build_valid_roulette()["free"])
        bad["length_buckets"] = [
            {"name": "small", "min_cm": 10, "max_cm": 50, "weight": 0.5},
            {"name": "small", "min_cm": 50, "max_cm": 150, "weight": 0.5},
        ]
        with pytest.raises(ValidationError, match="duplicate names"):
            RouletteFreeConfig.model_validate(bad)


class TestLengthBucketRange:
    def test_min_greater_than_max_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be <= max_cm"):
            RouletteLengthBucket.model_validate(
                {"name": "broken", "min_cm": 100, "max_cm": 10, "weight": 1.0},
            )

    def test_min_equals_max_passes(self) -> None:
        bucket = RouletteLengthBucket.model_validate(
            {"name": "tight", "min_cm": 10, "max_cm": 10, "weight": 1.0},
        )
        assert bucket.min_cm == bucket.max_cm == 10


class TestExtraFieldsForbidden:
    def test_extra_field_in_free_rejected(self) -> None:
        bad = copy.deepcopy(_build_valid_roulette()["free"])
        bad["extra_field"] = 42
        with pytest.raises(ValidationError, match="extra"):
            RouletteFreeConfig.model_validate(bad)

    def test_extra_field_in_outcome_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RouletteOutcomeWeight.model_validate(
                {"kind": "length", "weight": 1.0, "rogue": "x"},
            )

    def test_extra_field_in_bucket_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RouletteLengthBucket.model_validate(
                {
                    "name": "small",
                    "min_cm": 10,
                    "max_cm": 50,
                    "weight": 1.0,
                    "rogue": "x",
                },
            )


class TestBalancePayloadIntegration:
    def test_full_balance_with_roulette(self) -> None:
        cfg = BalanceConfig.model_validate(valid_balance_payload())
        assert cfg.roulette.free.cost_cm == 100

    def test_breaking_roulette_breaks_balance(self) -> None:
        payload = valid_balance_payload()
        payload["roulette"]["free"]["outcomes"][0]["weight"] = 0.99  # ломаем сумму
        with pytest.raises(ValidationError, match="must sum to 1.0"):
            BalanceConfig.model_validate(payload)
