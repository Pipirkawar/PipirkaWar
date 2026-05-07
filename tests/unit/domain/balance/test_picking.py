"""Тесты `pick_drop_item_entry` (Спринт 3.1-C).

Стратегия:
- **ScriptedRandom**: точные кейсы — что слот выбирается через
  `weighted_choice`, что нулевые веса слотов отбрасываются и не
  попадают в `weighted_choice`-вызов, что финальный pool корректно
  фильтруется по `(slot, rarity)`.
- **FakeRandom-стресс (1000+ rolls per location)**: гарантии
  на распределение слотов (±10% от `slot_weights`) — это и есть
  ключевой инвариант 3.1-C; и инвариант «оружие не дропает в лесу».
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import TypeVar

from pipirik_wars.domain.balance.config import (
    Rarity,
    Slot,
)
from pipirik_wars.domain.balance.picking import pick_drop_item_entry
from pipirik_wars.domain.forest.entities import ItemDrop
from pipirik_wars.domain.forest.services import compute_forest_outcome
from pipirik_wars.domain.pve.entities import PveLocationKind
from pipirik_wars.domain.pve.services import pick_pve_outcome
from pipirik_wars.domain.shared.ports import IRandom
from tests.fakes.random import FakeRandom
from tests.unit.domain.balance.factories import build_valid_balance

T = TypeVar("T")

_WEAPON_SLOTS: frozenset[Slot] = frozenset({Slot.RIGHT_HAND, Slot.LEFT_HAND})


class _ScriptedPickerRandom(IRandom):
    """Минимальный `IRandom` для unit-тестов `pick_drop_item_entry`.

    Очереди для `weighted_choice` (FIFO индексов) и `choice` (FIFO элементов
    или индексов в pool). Остальные методы — `NotImplementedError`,
    т.к. picker их не использует.
    """

    __slots__ = ("_choices", "_weighted_indexes")

    def __init__(
        self,
        *,
        weighted_indexes: Sequence[int] = (),
        choices: Sequence[object] = (),
    ) -> None:
        self._weighted_indexes: list[int] = list(weighted_indexes)
        self._choices: list[object] = list(choices)

    def randint(self, low: int, high: int) -> int:  # pragma: no cover
        raise NotImplementedError

    def uniform(self, low: float, high: float) -> float:  # pragma: no cover
        raise NotImplementedError

    def choice(self, items: Sequence[T]) -> T:
        scripted = self._choices.pop(0)
        if isinstance(scripted, int):
            return items[scripted]
        return scripted  # type: ignore[return-value]

    def weighted_choice(self, items: Sequence[T], weights: Sequence[int]) -> T:
        idx = self._weighted_indexes.pop(0)
        return items[idx]

    def deterministic_uint(self, seed: str, modulo: int) -> int:  # pragma: no cover
        raise NotImplementedError

    def shuffle(self, items: Sequence[T]) -> tuple[T, ...]:  # pragma: no cover
        raise NotImplementedError


class TestPickerScripted:
    """Точные кейсы: проверка правильной диспетчеризации `(slot, rarity)`."""

    def test_zero_weight_slots_are_filtered(self) -> None:
        # forest.drop.slot_weights в фикстуре: right_hand=0, left_hand=0.
        # Picker должен выкинуть их перед `weighted_choice` (т.к. RealRandom
        # требует все веса > 0). На 6 ненулевых слотов индекс 0 = HAT.
        cfg = build_valid_balance()
        scripted = _ScriptedPickerRandom(
            weighted_indexes=[0, 0],  # slot=HAT, rarity=common
            choices=[0],
        )
        entry = pick_drop_item_entry(
            balance=cfg,
            slot_weights=cfg.forest.drop.slot_weights,
            rarity_weights=cfg.forest.drop.rarity_weights,
            random=scripted,
        )
        assert entry.slot is Slot.HAT
        assert entry.rarity is Rarity.COMMON

    def test_picks_weapon_when_only_weapon_slot_is_active(self) -> None:
        # mountains.drop.slot_weights в фикстуре: оружие активно
        # (right_hand>0, left_hand>0). На полном списке all-positive
        # 8 слотов индекс 6 = RIGHT_HAND, 7 = LEFT_HAND.
        cfg = build_valid_balance()
        scripted = _ScriptedPickerRandom(
            weighted_indexes=[6, 0],  # slot=RIGHT_HAND, rarity=common
            choices=[0],
        )
        entry = pick_drop_item_entry(
            balance=cfg,
            slot_weights=cfg.mountains.drop.slot_weights,
            rarity_weights=cfg.mountains.drop.rarity_weights,
            random=scripted,
        )
        assert entry.slot is Slot.RIGHT_HAND
        assert entry.rarity is Rarity.COMMON

    def test_pool_filtered_by_slot_and_rarity(self) -> None:
        # Просим picker выдать (LEFT_HAND, EPIC) — в каталоге фикстуры
        # на каждый (slot, rarity) ровно 1 предмет с epic, поэтому
        # pool из 1 элемента и `random.choice` обязан его вернуть.
        cfg = build_valid_balance()
        scripted = _ScriptedPickerRandom(
            weighted_indexes=[7, 2],  # slot=LEFT_HAND, rarity=epic
            choices=[0],
        )
        entry = pick_drop_item_entry(
            balance=cfg,
            slot_weights=cfg.mountains.drop.slot_weights,
            rarity_weights=cfg.mountains.drop.rarity_weights,
            random=scripted,
        )
        assert entry.slot is Slot.LEFT_HAND
        assert entry.rarity is Rarity.EPIC


class TestSlotDistributionStress:
    """1000+ rolls per location: эмпирическое распределение слотов
    должно быть в ±10% от заявленных `slot_weights` (для слотов
    с положительным весом).
    """

    @staticmethod
    def _expected_share(slot_weights_pairs: tuple[tuple[Slot, int], ...]) -> dict[Slot, float]:
        total = sum(w for _, w in slot_weights_pairs if w > 0)
        return {s: w / total for s, w in slot_weights_pairs if w > 0}

    def test_forest_slot_distribution_within_tolerance(self) -> None:
        # 5000 принудительных дропов: probability=100%, share=0 (никогда имена).
        # Так получаем чистое распределение по слотам через picker.
        cfg = build_valid_balance()
        rng = FakeRandom(seed=11111)
        counts: Counter[Slot] = Counter()
        rolls = 5000
        for _ in range(rolls):
            entry = pick_drop_item_entry(
                balance=cfg,
                slot_weights=cfg.forest.drop.slot_weights,
                rarity_weights=cfg.forest.drop.rarity_weights,
                random=rng,
            )
            counts[entry.slot] += 1
        # Веса по slot_weights:
        expected = self._expected_share(cfg.forest.drop.slot_weights.as_pairs())
        # Активные слоты (вес>0) должны быть в ±10% от ожидаемой доли.
        for slot, exp_share in expected.items():
            actual_share = counts[slot] / rolls
            assert abs(actual_share - exp_share) <= 0.10, (
                f"forest slot={slot.value}: expected≈{exp_share:.3f}, actual={actual_share:.3f}"
            )
        # Слоты с весом=0 в forest НЕ должны быть выбраны ни разу
        # (right_hand/left_hand — оружие).
        assert counts[Slot.RIGHT_HAND] == 0
        assert counts[Slot.LEFT_HAND] == 0

    def test_mountains_slot_distribution_within_tolerance(self) -> None:
        cfg = build_valid_balance()
        rng = FakeRandom(seed=22222)
        counts: Counter[Slot] = Counter()
        rolls = 5000
        for _ in range(rolls):
            entry = pick_drop_item_entry(
                balance=cfg,
                slot_weights=cfg.mountains.drop.slot_weights,
                rarity_weights=cfg.mountains.drop.rarity_weights,
                random=rng,
            )
            counts[entry.slot] += 1
        expected = self._expected_share(cfg.mountains.drop.slot_weights.as_pairs())
        for slot, exp_share in expected.items():
            actual_share = counts[slot] / rolls
            assert abs(actual_share - exp_share) <= 0.10, (
                f"mountains slot={slot.value}: expected≈{exp_share:.3f}, actual={actual_share:.3f}"
            )
        # Все 8 слотов должны быть видны в горах (включая оружие).
        for slot in Slot:
            assert counts[slot] > 0, f"mountains: slot {slot.value} never seen"

    def test_dungeon_slot_distribution_within_tolerance(self) -> None:
        cfg = build_valid_balance()
        rng = FakeRandom(seed=33333)
        counts: Counter[Slot] = Counter()
        rolls = 5000
        for _ in range(rolls):
            entry = pick_drop_item_entry(
                balance=cfg,
                slot_weights=cfg.dungeon.drop.slot_weights,
                rarity_weights=cfg.dungeon.drop.rarity_weights,
                random=rng,
            )
            counts[entry.slot] += 1
        expected = self._expected_share(cfg.dungeon.drop.slot_weights.as_pairs())
        for slot, exp_share in expected.items():
            actual_share = counts[slot] / rolls
            assert abs(actual_share - exp_share) <= 0.10, (
                f"dungeon slot={slot.value}: expected≈{exp_share:.3f}, actual={actual_share:.3f}"
            )
        for slot in Slot:
            assert counts[slot] > 0, f"dungeon: slot {slot.value} never seen"


class TestForestNoWeapons:
    """Контр-проверка: при `slot_weights[right_hand]=left_hand=0` лес
    никогда не дропает оружие (даже на 5000 прогонах при 100%-вероятности
    дропа предмета вместо имени).
    """

    def test_forest_never_drops_weapons_over_5000_runs(self) -> None:
        cfg = build_valid_balance()
        rng = FakeRandom(seed=44444)
        seen_slots: set[Slot] = set()
        weapon_drop_count = 0
        for _ in range(5000):
            outcome = compute_forest_outcome(balance=cfg, random=rng)
            if isinstance(outcome.drop, ItemDrop):
                item = outcome.drop.item
                seen_slots.add(item.slot)
                if item.slot in _WEAPON_SLOTS:
                    weapon_drop_count += 1
        # Хотя бы один не-оружейный слот должен встретиться (вероятность
        # дропа предмета в лесу ≈ 50% × (1 − name_share/100), за 5000 прогонов
        # каталог 6 слотов точно покроется).
        assert seen_slots, "forest never produced any item drop in 5000 runs"
        assert weapon_drop_count == 0, (
            f"forest dropped weapon {weapon_drop_count} times — "
            "ожидался 0, т.к. slot_weights[right_hand]=left_hand=0"
        )


class TestPveWeaponsAndUniqueness:
    """В горах/данжоне оружие должно дропать; за 1000+ прогонов
    ожидается, что и `right_hand`, и `left_hand` окажутся в выдаче.
    """

    def test_mountains_drops_both_weapon_slots_over_2000_runs(self) -> None:
        cfg = build_valid_balance()
        rng = FakeRandom(seed=55555)
        seen_weapon_slots: set[Slot] = set()
        for _ in range(2000):
            outcome = pick_pve_outcome(
                location=PveLocationKind.MOUNTAINS,
                balance=cfg,
                random=rng,
            )
            for drop in outcome.drops:
                if drop.item.slot in _WEAPON_SLOTS:
                    seen_weapon_slots.add(drop.item.slot)
        assert seen_weapon_slots == _WEAPON_SLOTS, (
            f"mountains: ожидали оба слота оружия, увидели {seen_weapon_slots!r}"
        )

    def test_dungeon_drops_both_weapon_slots_over_2000_runs(self) -> None:
        cfg = build_valid_balance()
        rng = FakeRandom(seed=66666)
        seen_weapon_slots: set[Slot] = set()
        for _ in range(2000):
            outcome = pick_pve_outcome(
                location=PveLocationKind.DUNGEON,
                balance=cfg,
                random=rng,
            )
            for drop in outcome.drops:
                if drop.item.slot in _WEAPON_SLOTS:
                    seen_weapon_slots.add(drop.item.slot)
        assert seen_weapon_slots == _WEAPON_SLOTS

    def test_dungeon_all_rarities_seen_for_both_weapon_slots(self) -> None:
        # Контр-проверка _validate_drop_slot_rarity_coverage: если на каждой
        # (slot, rarity) есть хотя бы 1 предмет, то на 5000 прогонах
        # с probability=50%/max_drops=3 мы увидим все 6 (slot×rarity)
        # комбинаций для оружия.
        cfg = build_valid_balance()
        rng = FakeRandom(seed=77777)
        seen: set[tuple[Slot, Rarity]] = set()
        for _ in range(5000):
            outcome = pick_pve_outcome(
                location=PveLocationKind.DUNGEON,
                balance=cfg,
                random=rng,
            )
            for drop in outcome.drops:
                if drop.item.slot in _WEAPON_SLOTS:
                    seen.add((drop.item.slot, drop.item.rarity))
        all_rarities = (Rarity.COMMON, Rarity.RARE, Rarity.EPIC)
        expected = {(slot, rarity) for slot in _WEAPON_SLOTS for rarity in all_rarities}
        assert seen == expected, f"missing weapon (slot, rarity): {expected - seen!r}"
