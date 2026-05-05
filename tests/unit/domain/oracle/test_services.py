"""Unit-тесты `roll_oracle(...)` (Спринт 1.4.B, ПД 1.4.4).

Acceptance из плана: «статистика на 10000 прогонов: средняя ≈ 10.5 см
±0.5; всегда + длина».
"""

from __future__ import annotations

import statistics

import pytest

from pipirik_wars.domain.oracle import (
    OracleNoTemplatesError,
    OracleTemplate,
    roll_oracle,
)
from tests.fakes import FakeRandom
from tests.unit.domain.balance.factories import build_valid_balance


def _build_templates(n: int = 10) -> list[OracleTemplate]:
    return [OracleTemplate(id=f"oracle.ru.{i:04d}", text=f"text {i}") for i in range(n)]


class TestRollOracleHappyPath:
    def test_returns_template_and_bonus(self) -> None:
        balance = build_valid_balance()
        random = FakeRandom(seed=42)
        templates = _build_templates(5)

        result = roll_oracle(balance=balance, random=random, templates=templates)

        assert result.template in templates
        assert balance.oracle.bonus_min <= result.bonus_cm <= balance.oracle.bonus_max

    def test_deterministic_with_same_seed(self) -> None:
        balance = build_valid_balance()
        templates = _build_templates(5)

        a = roll_oracle(balance=balance, random=FakeRandom(seed=7), templates=templates)
        b = roll_oracle(balance=balance, random=FakeRandom(seed=7), templates=templates)

        assert a == b


class TestRollOracleEmptyCatalog:
    def test_empty_templates_raises(self) -> None:
        balance = build_valid_balance()
        random = FakeRandom(seed=0)
        with pytest.raises(OracleNoTemplatesError):
            roll_oracle(balance=balance, random=random, templates=[])


class TestRollOracleStatistics:
    """Acceptance ПД 1.4.4: 10000 прогонов uniform(1,20) — среднее ≈ 10.5."""

    def test_mean_is_around_10_5(self) -> None:
        balance = build_valid_balance()
        templates = _build_templates(20)
        random = FakeRandom(seed=12345)

        bonuses: list[int] = []
        for _ in range(10_000):
            res = roll_oracle(balance=balance, random=random, templates=templates)
            bonuses.append(res.bonus_cm)

        mean = statistics.fmean(bonuses)
        # uniform(1, 20) → ожидание = (1+20)/2 = 10.5; на 10k прогонах
        # стандартная ошибка среднего ≈ 0.058, поэтому коридор ±0.5 даёт
        # вероятность ложного провала пренебрежимо малой.
        assert 10.0 <= mean <= 11.0, f"unexpected mean: {mean}"

    def test_all_bonuses_positive_and_in_range(self) -> None:
        balance = build_valid_balance()
        templates = _build_templates(20)
        random = FakeRandom(seed=98765)

        for _ in range(2_000):
            res = roll_oracle(balance=balance, random=random, templates=templates)
            assert res.bonus_cm >= 1
            assert res.bonus_cm >= balance.oracle.bonus_min
            assert res.bonus_cm <= balance.oracle.bonus_max
