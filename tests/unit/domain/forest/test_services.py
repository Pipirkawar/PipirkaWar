"""Тесты `compute_forest_outcome` (Спринт 1.3.A).

Стратегия проверки:
- **Точные кейсы**: `ScriptedRandom` отдаёт заранее заготовленные
  значения по каждому методу `IRandom` — можно покапилярно
  проверить, какая ветка выбрана, какая длина, какой дроп. Это
  быстрее и устойчивее, чем подбирать seed.
- **Стресс-сэмплинг (smoke)**: `FakeRandom(seed=...)` — несколько
  тысяч прогонов, проверка инвариантов (длина в диапазоне ветки,
  не выходим за каталог, дроп — один из трёх ADT-конструкторов).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.forest import (
    ItemDrop,
    NameDrop,
    NoDrop,
    Rarity,
    Slot,
    compute_forest_outcome,
)
from pipirik_wars.domain.shared.ports import IRandom
from pipirik_wars.infrastructure.balance.loader import YamlBalanceLoader
from tests.fakes.random import FakeRandom
from tests.unit.domain.balance.factories import (
    build_valid_balance,
    valid_balance_payload,
)

T = TypeVar("T")


class ScriptedRandom(IRandom):
    """RNG со скриптом: каждый метод тянет из своей FIFO-очереди.

    Если очередь для метода пуста — `IndexError`. Такой стиль
    делает тест явным: видно ровно те значения, на которых
    основан вывод.
    """

    __slots__ = (
        "_choices",
        "_randints",
        "_uniforms",
        "_weighted_indexes",
    )

    def __init__(
        self,
        *,
        randints: Sequence[int] = (),
        uniforms: Sequence[float] = (),
        choices: Sequence[object] = (),
        weighted_indexes: Sequence[int] = (),
    ) -> None:
        self._randints: deque[int] = deque(randints)
        self._uniforms: deque[float] = deque(uniforms)
        self._choices: deque[object] = deque(choices)
        # `weighted_choice` запоминаем как индексы (порядок-устойчиво):
        # service-код вызывает с разными последовательностями.
        self._weighted_indexes: deque[int] = deque(weighted_indexes)

    def randint(self, low: int, high: int) -> int:
        value = self._randints.popleft()
        if not (low <= value <= high):
            raise AssertionError(f"scripted randint {value} out of [{low}, {high}]")
        return value

    def uniform(self, low: float, high: float) -> float:
        return self._uniforms.popleft()

    def choice(self, items: Sequence[T]) -> T:
        scripted = self._choices.popleft()
        # Поддерживаем 2 формата подсказок: либо сам item (для names),
        # либо индекс в Sequence (для items_pool, который зависит от
        # каталога и редкости).
        if isinstance(scripted, int):
            return items[scripted]
        # mypy: ignore — scripted задан тестом и совпадает по типу.
        return scripted  # type: ignore[return-value]

    def weighted_choice(self, items: Sequence[T], weights: Sequence[int]) -> T:
        idx = self._weighted_indexes.popleft()
        return items[idx]

    def deterministic_uint(self, seed: str, modulo: int) -> int:  # pragma: no cover
        raise NotImplementedError("not used by forest service")

    def shuffle(self, items: Sequence[T]) -> tuple[T, ...]:  # pragma: no cover
        raise NotImplementedError("not used by forest service")


def _balance() -> BalanceConfig:
    return build_valid_balance()


class TestBranchSelection:
    def test_scarce_branch_selected_at_min_length(self) -> None:
        cfg = _balance()
        scripted = ScriptedRandom(
            weighted_indexes=[0],  # scarce
            randints=[
                cfg.forest.outcomes[0].min,  # length
                100,  # drop probability roll → выше 50 → no drop
            ],
        )
        outcome = compute_forest_outcome(balance=cfg, random=scripted)
        assert outcome.branch.name == "scarce"
        assert outcome.length_cm == cfg.forest.outcomes[0].min
        assert isinstance(outcome.drop, NoDrop)

    def test_normal_branch_selected_at_max_length(self) -> None:
        cfg = _balance()
        scripted = ScriptedRandom(
            weighted_indexes=[1],  # normal
            randints=[
                cfg.forest.outcomes[1].max,
                100,  # no drop
            ],
        )
        outcome = compute_forest_outcome(balance=cfg, random=scripted)
        assert outcome.branch.name == "normal"
        assert outcome.length_cm == cfg.forest.outcomes[1].max

    def test_abundant_branch_selected(self) -> None:
        cfg = _balance()
        scripted = ScriptedRandom(
            weighted_indexes=[2],
            randints=[cfg.forest.outcomes[2].min, 100],
        )
        outcome = compute_forest_outcome(balance=cfg, random=scripted)
        assert outcome.branch.name == "abundant"


class TestDropProbability:
    def test_drop_skipped_when_roll_above_threshold(self) -> None:
        cfg = _balance()
        # probability_percent = 50 → roll 51 → нет дропа.
        scripted = ScriptedRandom(
            weighted_indexes=[0],
            randints=[cfg.forest.outcomes[0].min, 51],
        )
        outcome = compute_forest_outcome(balance=cfg, random=scripted)
        assert isinstance(outcome.drop, NoDrop)

    def test_drop_taken_when_roll_at_threshold(self) -> None:
        # probability_percent = 50 → roll 50 → дроп. И 100 → не имя → предмет.
        # rarity_weights idx 0 = common; choice(0) — первый предмет каталога.
        cfg = _balance()
        scripted = ScriptedRandom(
            weighted_indexes=[
                0,  # branch=scarce
                0,  # rarity=common
            ],
            randints=[
                cfg.forest.outcomes[0].min,  # length
                50,  # drop hits (== probability_percent)
                100,  # name_share roll (> 5) → предмет
            ],
            choices=[0],  # первый предмет в pool
        )
        outcome = compute_forest_outcome(balance=cfg, random=scripted)
        assert isinstance(outcome.drop, ItemDrop)
        assert outcome.drop.item.rarity is Rarity.COMMON

    def test_zero_probability_means_never_drops(self) -> None:
        # probability_percent = 0 → любой roll [1..100] > 0 → no drop.
        payload = valid_balance_payload()
        payload["forest"]["drop"]["probability_percent"] = 0
        cfg = BalanceConfig.model_validate(payload)
        scripted = ScriptedRandom(
            weighted_indexes=[0],
            randints=[cfg.forest.outcomes[0].min, 1],
        )
        outcome = compute_forest_outcome(balance=cfg, random=scripted)
        assert isinstance(outcome.drop, NoDrop)


class TestNameVsItemSplit:
    def test_name_drop_when_share_roll_at_threshold(self) -> None:
        cfg = _balance()
        scripted = ScriptedRandom(
            weighted_indexes=[0],  # scarce
            randints=[
                cfg.forest.outcomes[0].min,
                1,  # drop hits
                cfg.forest.drop.name_share_percent,  # имя (== threshold)
            ],
            choices=["Колян"],  # имя из каталога — подменим
        )
        outcome = compute_forest_outcome(balance=cfg, random=scripted)
        assert isinstance(outcome.drop, NameDrop)
        assert outcome.drop.name.value == "Колян"

    def test_item_drop_when_share_roll_above_threshold(self) -> None:
        cfg = _balance()
        scripted = ScriptedRandom(
            weighted_indexes=[0, 1],  # branch=scarce, rarity=rare
            randints=[
                cfg.forest.outcomes[0].min,
                1,  # drop hits
                cfg.forest.drop.name_share_percent + 1,  # предмет
            ],
            choices=[0],
        )
        outcome = compute_forest_outcome(balance=cfg, random=scripted)
        assert isinstance(outcome.drop, ItemDrop)
        assert outcome.drop.item.rarity is Rarity.RARE


class TestRaritySelection:
    def test_each_rarity_uses_its_own_pool(self) -> None:
        cfg = _balance()
        rarities = (Rarity.COMMON, Rarity.RARE, Rarity.EPIC)
        for rarity_idx, rarity in enumerate(rarities):
            scripted = ScriptedRandom(
                weighted_indexes=[0, rarity_idx],
                randints=[
                    cfg.forest.outcomes[0].min,
                    1,
                    cfg.forest.drop.name_share_percent + 1,
                ],
                choices=[0],
            )
            outcome = compute_forest_outcome(balance=cfg, random=scripted)
            assert isinstance(outcome.drop, ItemDrop)
            assert outcome.drop.item.rarity is rarity


class TestStressSampling:
    def test_invariants_hold_over_5000_runs(self) -> None:
        cfg = _balance()
        rng = FakeRandom(seed=12345)
        names_set = set(cfg.names_catalog)
        item_ids = {e.id for e in cfg.items_catalog}

        for _ in range(5000):
            outcome = compute_forest_outcome(balance=cfg, random=rng)
            # Длина в диапазоне выбранной ветки.
            cfg_branch = next(o for o in cfg.forest.outcomes if o.name == outcome.branch.name)
            assert cfg_branch.min <= outcome.length_cm <= cfg_branch.max
            assert outcome.length_cm == outcome.branch.length_cm

            match outcome.drop:
                case NoDrop():
                    pass
                case ItemDrop(item=item):
                    assert item.id in item_ids
                    assert isinstance(item.slot, Slot)
                    assert isinstance(item.rarity, Rarity)
                case NameDrop(name=name):
                    assert name.value in names_set

    def test_real_balance_yaml_distribution_smoke(self) -> None:
        """Sanity-check на реальном `config/balance.yaml` (не fixture)."""
        path = Path(__file__).resolve().parents[4] / "config" / "balance.yaml"
        cfg = YamlBalanceLoader(path).get()
        rng = FakeRandom(seed=42)
        seen_branches: set[str] = set()
        seen_drop_kinds: set[str] = set()
        for _ in range(2000):
            o = compute_forest_outcome(balance=cfg, random=rng)
            seen_branches.add(o.branch.name)
            seen_drop_kinds.add(type(o.drop).__name__)
        # На 2000 прогонах должны увидеть все 3 ветки и хотя бы 2 типа дропа.
        assert seen_branches == {"scarce", "normal", "abundant"}
        assert "NoDrop" in seen_drop_kinds
        assert "ItemDrop" in seen_drop_kinds
