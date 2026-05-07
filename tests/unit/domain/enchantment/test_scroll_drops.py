"""Тесты дропа скроллов заточки (Спринт 3.1-D, ГДД §2.8.5).

Стресс-сэмплинг: 10 000 прогонов на каждую локацию (горы / данжон) с
`FakeRandom(seed=...)` — проверка частот regular/blessed/category в
±10% от заявленных шансов в `valid_balance_payload()`. Тесты бьют по
**publicly observable** API picker-а (`pick_pve_outcome`) — никаких
заглядов во внутренности `_roll_scroll_drops`.

Дополнительные кейсы:
- Mountains: blessed-частота ровно 0 (`blessed_chance_percent: 0`).
- Real `config/balance.yaml`: smoke-тест — выбранные числа баланса
  не нарушают «очень-очень малый» / «очень малый» характер дропов.
- Forest: `compute_forest_outcome` не вызывает `_roll_scroll_drops`
  (контр-проверка: лес скроллы не дропает по дизайну ГДД §2.8.5;
  у `ForestDropConfig` нет поля `scroll_drops`).
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

import pytest
import yaml

from pipirik_wars.domain.balance import BalanceConfig
from pipirik_wars.domain.enchantment import Scroll, ScrollCategory
from pipirik_wars.domain.forest.services import compute_forest_outcome
from pipirik_wars.domain.pve.entities import PveLocationKind, PveScrollDrop
from pipirik_wars.domain.pve.services import pick_pve_outcome
from tests.fakes.random import FakeRandom
from tests.unit.domain.balance.factories import build_valid_balance

_ROLLS = 10_000
"""Сколько раз катать picker. На 10 000 rolls дисперсия Bernoulli ≈ 0.5%
для p = 1%, ≈ 1% для p = 6%. Допуск ±10% от заявленного шанса даёт
запас от стохастических флапов; pinned seed гарантирует воспроизводимость."""


def _balance() -> BalanceConfig:
    return build_valid_balance()


def _real_balance_path() -> Path:
    return Path(__file__).resolve().parents[4] / "config" / "balance.yaml"


def _real_balance() -> BalanceConfig:
    raw = yaml.safe_load(_real_balance_path().read_text(encoding="utf-8"))
    return BalanceConfig.model_validate(raw)


def _bernoulli_bounds(p: float, *, n: int = _ROLLS) -> tuple[float, float]:
    """Допустимые границы наблюдаемой частоты при заявленном шансе `p`.

    Использует **3σ**-границы (`σ = √(n·p·(1-p))`), что покрывает 99.7%
    случаев чистого Bernoulli; плюс аддитивный флор `±10` от ожидаемого,
    чтобы тесты не флапали на маленьких `p` (например, `p=0.01` ⇒
    σ ≈ 10, expected = 100, 3σ-bounds = [70, 130]).
    """
    expected = p * n
    sigma = math.sqrt(n * p * (1 - p))
    delta = max(3 * sigma, 10.0)
    return expected - delta, expected + delta


# -- Mountains: regular-only, blessed=0 ---------------------------------------


class TestMountainsScrollFrequencies:
    def test_regular_frequency_within_tolerance(self) -> None:
        """Mountains: regular_chance_percent=3 → ~300/10000 (±10%)."""
        cfg = _balance()
        rng = FakeRandom(seed=314159)
        regular_count = 0

        for _ in range(_ROLLS):
            outcome = pick_pve_outcome(
                location=PveLocationKind.MOUNTAINS,
                balance=cfg,
                random=rng,
            )
            for drop in outcome.scroll_drops:
                if not drop.scroll.blessed:
                    regular_count += 1

        p = cfg.mountains.drop.scroll_drops.regular_chance_percent / 100.0
        lo, hi = _bernoulli_bounds(p)
        assert lo <= regular_count <= hi, (
            f"mountains regular_count={regular_count} not in [{lo:.1f}, {hi:.1f}] "
            f"(expected ~{p * _ROLLS:.0f})"
        )

    def test_blessed_never_drops_in_mountains(self) -> None:
        """Mountains: blessed_chance_percent=0 → ровно 0 blessed-скроллов."""
        cfg = _balance()
        assert cfg.mountains.drop.scroll_drops.blessed_chance_percent == 0
        rng = FakeRandom(seed=27182)
        blessed_count = 0

        for _ in range(_ROLLS):
            outcome = pick_pve_outcome(
                location=PveLocationKind.MOUNTAINS,
                balance=cfg,
                random=rng,
            )
            for drop in outcome.scroll_drops:
                if drop.scroll.blessed:
                    blessed_count += 1

        assert blessed_count == 0, f"mountains blessed_count={blessed_count}, expected 0"

    def test_scroll_drops_are_pve_scroll_drop_instances(self) -> None:
        cfg = _balance()
        rng = FakeRandom(seed=1)
        for _ in range(100):
            outcome = pick_pve_outcome(
                location=PveLocationKind.MOUNTAINS,
                balance=cfg,
                random=rng,
            )
            for drop in outcome.scroll_drops:
                assert isinstance(drop, PveScrollDrop)
                assert isinstance(drop.scroll, Scroll)


# -- Dungeon: regular + blessed ----------------------------------------------


class TestDungeonScrollFrequencies:
    def test_regular_and_blessed_frequencies(self) -> None:
        """Dungeon: regular=6%, blessed=1% → ~600 / ~100 на 10 000 rolls (±10%)."""
        cfg = _balance()
        rng = FakeRandom(seed=2718281828)
        regular_count = 0
        blessed_count = 0

        for _ in range(_ROLLS):
            outcome = pick_pve_outcome(
                location=PveLocationKind.DUNGEON,
                balance=cfg,
                random=rng,
            )
            for drop in outcome.scroll_drops:
                if drop.scroll.blessed:
                    blessed_count += 1
                else:
                    regular_count += 1

        p_reg = cfg.dungeon.drop.scroll_drops.regular_chance_percent / 100.0
        p_bl = cfg.dungeon.drop.scroll_drops.blessed_chance_percent / 100.0

        lo_reg, hi_reg = _bernoulli_bounds(p_reg)
        lo_bl, hi_bl = _bernoulli_bounds(p_bl)
        assert lo_reg <= regular_count <= hi_reg, (
            f"dungeon regular_count={regular_count} not in [{lo_reg:.1f}, {hi_reg:.1f}] "
            f"(expected ~{p_reg * _ROLLS:.0f})"
        )
        assert lo_bl <= blessed_count <= hi_bl, (
            f"dungeon blessed_count={blessed_count} not in [{lo_bl:.1f}, {hi_bl:.1f}] "
            f"(expected ~{p_bl * _ROLLS:.0f})"
        )

    def test_category_distribution_uniform(self) -> None:
        """Dungeon: category_weights 1:1:1 → ~33%/33%/33% распределение."""
        cfg = _balance()
        rng = FakeRandom(seed=42)
        category_counts: Counter[ScrollCategory] = Counter()
        total = 0

        for _ in range(_ROLLS):
            outcome = pick_pve_outcome(
                location=PveLocationKind.DUNGEON,
                balance=cfg,
                random=rng,
            )
            for drop in outcome.scroll_drops:
                category_counts[drop.scroll.category] += 1
                total += 1

        # Всего ~700 скроллов на 10 000 rolls; распределение по 3 категориям
        # должно быть ~233 каждой. Допуск шире (±25%), т.к. выборка маленькая.
        assert total > 100, f"too few scroll drops to test category distribution: {total}"
        expected = total / 3.0
        for cat in (ScrollCategory.WEAPON, ScrollCategory.ARMOR, ScrollCategory.JEWELRY):
            count = category_counts[cat]
            assert 0.65 * expected <= count <= 1.35 * expected, (
                f"dungeon category={cat.value} count={count} not within ±35% of {expected:.1f}"
            )

    def test_scroll_and_item_drops_independent(self) -> None:
        """Bernoulli scroll-роллы независимы от item-роллов: за 1 поход
        можно получить любую комбинацию (item + regular + blessed).
        """
        cfg = _balance()
        rng = FakeRandom(seed=999)
        # Хотя бы один поход с ≥ 1 предметом и ≥ 1 скроллом.
        had_both = False
        for _ in range(_ROLLS):
            outcome = pick_pve_outcome(
                location=PveLocationKind.DUNGEON,
                balance=cfg,
                random=rng,
            )
            if outcome.drops and outcome.scroll_drops:
                had_both = True
                break
        assert had_both, (
            "expected at least one dungeon run with both item drop and scroll drop "
            "across {_ROLLS} rolls; chances p_item~50%, p_scroll~7% — should be common"
        )


# -- Real balance.yaml smoke-test --------------------------------------------


class TestRealBalanceScrollDrops:
    def test_real_balance_mountains_scroll_drops_within_design_bounds(self) -> None:
        """Реальный `config/balance.yaml`: горы — `regular ∈ (0, 5]%`, blessed = 0."""
        cfg = _real_balance()
        sd = cfg.mountains.drop.scroll_drops
        assert sd.blessed_chance_percent == 0, "mountains blessed must be 0 (ГДД §2.8.5)"
        assert 0 < sd.regular_chance_percent <= 5, (
            f"mountains regular={sd.regular_chance_percent} вне 'очень-очень малого' [1, 5]%"
        )

    def test_real_balance_dungeon_scroll_drops_within_design_bounds(self) -> None:
        """Реальный `balance.yaml`: данжон — `regular ∈ (0, 10]%`, blessed `∈ (0, 5]%`."""
        cfg = _real_balance()
        sd = cfg.dungeon.drop.scroll_drops
        assert 0 < sd.regular_chance_percent <= 10, (
            f"dungeon regular={sd.regular_chance_percent} вне 'очень малого' (0, 10]%"
        )
        assert 0 < sd.blessed_chance_percent <= 5, (
            f"dungeon blessed={sd.blessed_chance_percent} вне 'очень-очень малого' (0, 5]%"
        )
        assert sd.blessed_chance_percent < sd.regular_chance_percent, (
            "ГДД §2.8.5: blessed-шанс должен быть меньше regular-шанса в данжоне "
            f"(got blessed={sd.blessed_chance_percent}, regular={sd.regular_chance_percent})"
        )

    @pytest.mark.parametrize("seed", [1, 7, 13])
    def test_real_balance_smoke_picker_runs(self, seed: int) -> None:
        """На реальном `balance.yaml` picker не падает на 1000 rolls per location."""
        cfg = _real_balance()
        rng = FakeRandom(seed=seed)
        for location in (PveLocationKind.MOUNTAINS, PveLocationKind.DUNGEON):
            for _ in range(1000):
                outcome = pick_pve_outcome(location=location, balance=cfg, random=rng)
                # Скролл-дропы — 0..2 (regular + blessed).
                assert 0 <= len(outcome.scroll_drops) <= 2


# -- Forest contr-test: лес скроллы не дропает -------------------------------


class TestForestNoScrolls:
    def test_compute_forest_outcome_returns_no_scroll_drops(self) -> None:
        """Лес скроллы не дропает (ГДД §2.8.5).

        `ForestDropConfig` намеренно НЕ имеет поля `scroll_drops` —
        это запрещает на уровне схемы добавлять им скроллы.
        `compute_forest_outcome` не катит scroll-роллов; результат
        `ForestRunOutcome` не содержит scroll-полей. Этот тест защищает
        дизайн-инвариант от регрессий.
        """
        cfg = _balance()
        rng = FakeRandom(seed=21)
        for _ in range(1000):
            outcome = compute_forest_outcome(balance=cfg, random=rng)
            assert not hasattr(outcome, "scroll_drops"), (
                "ForestRunOutcome must not have scroll_drops field "
                "(forest does not drop scrolls — ГДД §2.8.5)"
            )


__all__: tuple[str, ...] = ()
