"""Тесты доменного picker-а заточки `pick_enchant_outcome` (Спринт 3.4-A, A.5).

Структура аналогична `tests/unit/domain/enchantment/test_scroll_drops.py`
(Спринт 3.1-D) — тот же `_bernoulli_bounds`-приём (3σ + аддитивный
флор `±10` от ожидаемого), та же интуиция «много прогонов на каждый
тир, проверяем частоты в Bernoulli-границах».

Покрытие:

* **Safe-zone** (`level < safe_zone_max_level == 3`) — forced-success
  на всех 30 прогонах ровно (без roll-ов): `SUCCESS` для regular,
  `SUCCESS_1` для blessed. `IRandom` не дёргается (если бы дёргался,
  тест с пустым `FakeRandom` всё равно бы прошёл, но мы дополнительно
  проверяем счётчик через `CountingRandom`-обёртку).
* **Все 4 regular-исхода** (success / no_effect / drop / destroy) на
  каждом тире (`safe_zone_max..29`) c `n=10_000` прогонов на тир —
  частоты в 3σ-границах от заявленных весов.
* **Все 5 blessed-исходов** (success_1 / success_2 / no_effect /
  drop_1 / drop_2) на каждом тире — то же.
* **`level == 29`** для blessed — `SUCCESS_2` **никогда** не выпадает
  (`weights.success_2 == 0.0` по ГДД §2.8.4).
* **Граничные значения `level`** — `pick_enchant_outcome(level=-1)` и
  `level=30` бросают `ValueError` (defence-in-depth: `EnchantItem`-use-case
  должен отфильтровать раньше, но picker не должен пропускать).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from typing import TypeVar

import pytest

from pipirik_wars.domain.balance.config import EnchantmentConfig
from pipirik_wars.domain.inventory import (
    BlessedEnchantOutcome,
    RegularEnchantOutcome,
    pick_enchant_outcome,
)
from pipirik_wars.domain.inventory.entities import MAX_ENCHANT_LEVEL
from pipirik_wars.domain.shared.ports import IRandom
from tests.fakes.random import FakeRandom
from tests.unit.domain.balance.factories import build_valid_balance

_ROLLS = 10_000

T = TypeVar("T")


def _bernoulli_bounds(p: float, *, n: int = _ROLLS) -> tuple[float, float]:
    """3σ-границы Bernoulli с аддитивным флором `±10` от ожидаемого.

    Идентично `tests/unit/domain/enchantment/test_scroll_drops.py`
    — копия специально (тесты в разных доменах не должны делить
    test-utility между собой по соглашению проекта).
    """
    expected = p * n
    sigma = math.sqrt(n * p * (1 - p))
    delta = max(3 * sigma, 10.0)
    return expected - delta, expected + delta


def _enchantment() -> EnchantmentConfig:
    return build_valid_balance().enchantment


# --------------------------------------------------------------------------- #
# Safe-zone forced-success
# --------------------------------------------------------------------------- #


class _CountingRandom(IRandom):
    """Обёртка над `FakeRandom`, считающая вызовы каждого метода.

    Нужна, чтобы доказать: в safe-zone picker `IRandom` **не дёргает**
    (никаких `weighted_choice`-ов / `uniform`-ов). Тест без обёртки
    тоже бы прошёл (forced-success), но без неё нельзя отличить
    «picker всегда возвращает SUCCESS, потому что safe-zone» от
    «picker всегда возвращает SUCCESS, потому что seed-у так совпало».
    """

    __slots__ = ("_inner", "calls")

    def __init__(self, inner: IRandom) -> None:
        self._inner = inner
        self.calls: Counter[str] = Counter()

    def randint(self, low: int, high: int) -> int:
        self.calls["randint"] += 1
        return self._inner.randint(low, high)

    def uniform(self, low: float, high: float) -> float:
        self.calls["uniform"] += 1
        return self._inner.uniform(low, high)

    def choice(self, items: Sequence[T]) -> T:
        self.calls["choice"] += 1
        return self._inner.choice(items)

    def weighted_choice(self, items: Sequence[T], weights: Sequence[int]) -> T:
        self.calls["weighted_choice"] += 1
        return self._inner.weighted_choice(items, weights)

    def deterministic_uint(self, seed: str, modulo: int) -> int:
        self.calls["deterministic_uint"] += 1
        return self._inner.deterministic_uint(seed, modulo)

    def shuffle(self, items: Sequence[T]) -> tuple[T, ...]:
        self.calls["shuffle"] += 1
        return self._inner.shuffle(items)


class TestSafeZoneForcedSuccess:
    """Уровни `0..safe_zone_max_level-1` — гарантированный успех без roll-ов."""

    def test_regular_safe_zone_always_success(self) -> None:
        cfg = _enchantment()
        rng = _CountingRandom(FakeRandom(seed=1))
        for level in range(cfg.safe_zone_max_level):
            for _ in range(30):
                outcome = pick_enchant_outcome(
                    level=level,
                    blessed=False,
                    config=cfg,
                    random=rng,
                )
                assert outcome is RegularEnchantOutcome.SUCCESS
        assert rng.calls == Counter()

    def test_blessed_safe_zone_always_success_1(self) -> None:
        cfg = _enchantment()
        rng = _CountingRandom(FakeRandom(seed=2))
        for level in range(cfg.safe_zone_max_level):
            for _ in range(30):
                outcome = pick_enchant_outcome(
                    level=level,
                    blessed=True,
                    config=cfg,
                    random=rng,
                )
                assert outcome is BlessedEnchantOutcome.SUCCESS_1
        assert rng.calls == Counter()


# --------------------------------------------------------------------------- #
# Regular: 3σ-Bernoulli частоты на каждом уровне за safe-zone
# --------------------------------------------------------------------------- #


class TestRegularFrequenciesAcrossTiers:
    """Для каждого тира (`safe_zone_max..29`) частоты 4 исходов в 3σ-границах."""

    @pytest.mark.parametrize("level", [3, 7, 12, 18, 25, 29])
    def test_regular_outcomes_within_bernoulli_bounds(self, level: int) -> None:
        cfg = _enchantment()
        weights = cfg.regular_outcomes_per_level[level]
        rng = FakeRandom(seed=42 + level)
        counter: Counter[RegularEnchantOutcome] = Counter()

        for _ in range(_ROLLS):
            outcome = pick_enchant_outcome(
                level=level,
                blessed=False,
                config=cfg,
                random=rng,
            )
            assert isinstance(outcome, RegularEnchantOutcome)
            counter[outcome] += 1

        for outcome, p in (
            (RegularEnchantOutcome.SUCCESS, weights.success),
            (RegularEnchantOutcome.NO_EFFECT, weights.no_effect),
            (RegularEnchantOutcome.DROP, weights.drop),
            (RegularEnchantOutcome.DESTROY, weights.destroy),
        ):
            observed = counter[outcome]
            if p == 0.0:
                assert observed == 0, (
                    f"regular[{level}] {outcome.name}: zero-weight outcome "
                    f"observed {observed} times"
                )
                continue
            lo, hi = _bernoulli_bounds(p)
            assert lo <= observed <= hi, (
                f"regular[{level}] {outcome.name}: observed={observed} "
                f"not in [{lo:.1f}, {hi:.1f}] (expected ~{p * _ROLLS:.0f})"
            )

    def test_regular_total_count_equals_rolls(self) -> None:
        """Sanity: на каждом ролле picker возвращает ровно один outcome."""
        cfg = _enchantment()
        rng = FakeRandom(seed=7)
        counter: Counter[RegularEnchantOutcome] = Counter()
        for _ in range(_ROLLS):
            counter[pick_enchant_outcome(level=15, blessed=False, config=cfg, random=rng)] += 1  # type: ignore[index]
        assert sum(counter.values()) == _ROLLS


# --------------------------------------------------------------------------- #
# Blessed: 3σ-Bernoulli частоты на каждом тире
# --------------------------------------------------------------------------- #


class TestBlessedFrequenciesAcrossTiers:
    """Для каждого тира (`safe_zone_max..29`) частоты 5 blessed-исходов в 3σ-границах."""

    @pytest.mark.parametrize("level", [3, 7, 12, 18, 25, 29])
    def test_blessed_outcomes_within_bernoulli_bounds(self, level: int) -> None:
        cfg = _enchantment()
        weights = cfg.blessed_outcomes_per_level[level]
        rng = FakeRandom(seed=137 + level)
        counter: Counter[BlessedEnchantOutcome] = Counter()

        for _ in range(_ROLLS):
            outcome = pick_enchant_outcome(
                level=level,
                blessed=True,
                config=cfg,
                random=rng,
            )
            assert isinstance(outcome, BlessedEnchantOutcome)
            counter[outcome] += 1

        for outcome, p in (
            (BlessedEnchantOutcome.SUCCESS_1, weights.success_1),
            (BlessedEnchantOutcome.SUCCESS_2, weights.success_2),
            (BlessedEnchantOutcome.NO_EFFECT, weights.no_effect),
            (BlessedEnchantOutcome.DROP_1, weights.drop_1),
            (BlessedEnchantOutcome.DROP_2, weights.drop_2),
        ):
            observed = counter[outcome]
            if p == 0.0:
                assert observed == 0, (
                    f"blessed[{level}] {outcome.name}: zero-weight outcome "
                    f"observed {observed} times"
                )
                continue
            lo, hi = _bernoulli_bounds(p)
            assert lo <= observed <= hi, (
                f"blessed[{level}] {outcome.name}: observed={observed} "
                f"not in [{lo:.1f}, {hi:.1f}] (expected ~{p * _ROLLS:.0f})"
            )

    def test_blessed_last_level_never_success_2(self) -> None:
        """На `level == max_level - 1` `SUCCESS_2` запрещён (ГДД §2.8.4)."""
        cfg = _enchantment()
        last_level = cfg.max_level - 1
        assert cfg.blessed_outcomes_per_level[last_level].success_2 == 0.0
        rng = FakeRandom(seed=271828)
        for _ in range(_ROLLS):
            outcome = pick_enchant_outcome(
                level=last_level,
                blessed=True,
                config=cfg,
                random=rng,
            )
            assert outcome is not BlessedEnchantOutcome.SUCCESS_2


# --------------------------------------------------------------------------- #
# Граничные значения `level` (defence-in-depth)
# --------------------------------------------------------------------------- #


class TestPickerLevelBoundsValueError:
    """`pick_enchant_outcome` валидирует `level ∈ [0, max_level - 1]`."""

    @pytest.mark.parametrize("level", [-1, -10, MAX_ENCHANT_LEVEL, MAX_ENCHANT_LEVEL + 1])
    def test_out_of_range_level_raises_value_error(self, level: int) -> None:
        cfg = _enchantment()
        with pytest.raises(ValueError, match="level must be in"):
            pick_enchant_outcome(level=level, blessed=False, config=cfg, random=FakeRandom(seed=0))

    @pytest.mark.parametrize("level", [-1, MAX_ENCHANT_LEVEL])
    def test_out_of_range_level_blessed_raises(self, level: int) -> None:
        cfg = _enchantment()
        with pytest.raises(ValueError, match="level must be in"):
            pick_enchant_outcome(level=level, blessed=True, config=cfg, random=FakeRandom(seed=0))

    def test_level_zero_inside_safe_zone_no_error(self) -> None:
        cfg = _enchantment()
        outcome = pick_enchant_outcome(
            level=0,
            blessed=False,
            config=cfg,
            random=FakeRandom(seed=0),
        )
        assert outcome is RegularEnchantOutcome.SUCCESS

    def test_level_max_minus_one_blessed_no_error(self) -> None:
        cfg = _enchantment()
        outcome = pick_enchant_outcome(
            level=cfg.max_level - 1,
            blessed=True,
            config=cfg,
            random=FakeRandom(seed=0),
        )
        assert isinstance(outcome, BlessedEnchantOutcome)
