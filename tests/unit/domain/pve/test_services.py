"""Тесты `pick_pve_outcome` (Спринт 3.1-A).

Стратегия:
- **Точные кейсы** через `ScriptedRandom` — какая ветка выбрана,
  какой знак `length_delta_cm`, сколько слотов дропа.
- **Стресс-сэмплинг** на `FakeRandom(seed=...)` — 1000+ прогонов
  на каждую локацию (горы / данжон), проверка инвариантов
  (диапазон длины по знаку ветки, число дропов в `[0, max_drops]`,
  все дропы — из `items_catalog`).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from typing import TypeVar

from pipirik_wars.domain.balance.config import BalanceConfig, PveSign
from pipirik_wars.domain.pve import (
    PveItemDrop,
    PveLocationKind,
    PveOutcomeBranch,
    PveRunOutcome,
    pick_pve_outcome,
)
from pipirik_wars.domain.shared.ports import IRandom
from tests.fakes.random import FakeRandom
from tests.unit.domain.balance.factories import build_valid_balance

T = TypeVar("T")


class ScriptedRandom(IRandom):
    """RNG со скриптом FIFO-очередей по каждому методу.

    Используем тот же стиль, что в `tests/unit/domain/forest/test_services.py`.
    """

    __slots__ = ("_choices", "_randints", "_uniforms", "_weighted_indexes")

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
        if isinstance(scripted, int):
            return items[scripted]
        return scripted  # type: ignore[return-value]

    def weighted_choice(self, items: Sequence[T], weights: Sequence[int]) -> T:
        idx = self._weighted_indexes.popleft()
        return items[idx]

    def deterministic_uint(self, seed: str, modulo: int) -> int:  # pragma: no cover
        raise NotImplementedError("not used by pve service")

    def shuffle(self, items: Sequence[T]) -> tuple[T, ...]:  # pragma: no cover
        raise NotImplementedError("not used by pve service")


def _balance() -> BalanceConfig:
    return build_valid_balance()


# -- Mountains ----------------------------------------------------------------


class TestMountainsScripted:
    def test_first_gain_branch_min_length_no_drop(self) -> None:
        cfg = _balance()
        scripted = ScriptedRandom(
            weighted_indexes=[0],  # outcomes[0] = scarce_gain
            randints=[
                cfg.mountains.outcomes[0].min,  # length
                100,  # drop slot 0: 100 > 25 → no drop
            ],
        )
        outcome = pick_pve_outcome(
            location=PveLocationKind.MOUNTAINS,
            balance=cfg,
            random=scripted,
        )
        assert outcome.branch.name == "scarce_gain"
        assert outcome.branch.sign is PveSign.GAIN
        assert outcome.length_delta_cm == cfg.mountains.outcomes[0].min
        assert outcome.length_delta_cm > 0
        assert outcome.drops == ()

    def test_loss_branch_negative_delta(self) -> None:
        cfg = _balance()
        # outcomes[3] = scarce_loss (sign=loss, min=1, max=8)
        scripted = ScriptedRandom(
            weighted_indexes=[3],
            randints=[
                cfg.mountains.outcomes[3].max,  # length=8
                100,  # no drop
            ],
        )
        outcome = pick_pve_outcome(
            location=PveLocationKind.MOUNTAINS,
            balance=cfg,
            random=scripted,
        )
        assert outcome.branch.sign is PveSign.LOSS
        assert outcome.length_delta_cm == -cfg.mountains.outcomes[3].max
        assert outcome.length_delta_cm < 0

    def test_drop_taken_at_threshold(self) -> None:
        cfg = _balance()
        # mountains: probability_percent=25, max_drops=1. Roll 25 → дроп.
        # Спринт 3.1-C: перед rarity катится слот через `slot_weights`.
        # Для гор все 8 весов > 0; индекс 0 = HAT.
        scripted = ScriptedRandom(
            weighted_indexes=[
                0,  # branch=scarce_gain
                0,  # slot=HAT
                0,  # rarity=common
            ],
            randints=[
                cfg.mountains.outcomes[0].min,  # length
                25,  # drop slot 0: 25 <= 25 → дроп
            ],
            choices=[0],  # первый предмет в pool (HAT, COMMON)
        )
        outcome = pick_pve_outcome(
            location=PveLocationKind.MOUNTAINS,
            balance=cfg,
            random=scripted,
        )
        assert len(outcome.drops) == 1
        assert isinstance(outcome.drops[0], PveItemDrop)

    def test_max_drops_one_for_mountains(self) -> None:
        # mountains.drop.max_drops=1 → даже если probability=100%, не более 1 дропа.
        cfg = _balance()
        scripted = ScriptedRandom(
            weighted_indexes=[0, 0, 0],  # branch, slot=HAT, rarity=common
            randints=[cfg.mountains.outcomes[0].min, 1],  # 1 ≤ 25 → дроп
            choices=[0],
        )
        outcome = pick_pve_outcome(
            location=PveLocationKind.MOUNTAINS,
            balance=cfg,
            random=scripted,
        )
        assert len(outcome.drops) == 1


# -- Dungeon ------------------------------------------------------------------


class TestDungeonScripted:
    def test_gain_branch_positive_delta(self) -> None:
        cfg = _balance()
        # outcomes[0] = scarce_gain (sign=gain).
        scripted = ScriptedRandom(
            weighted_indexes=[0],
            randints=[
                cfg.dungeon.outcomes[0].min,  # length=5
                100,
                100,
                100,  # 3 drop rolls, все > 50 → no drops
            ],
        )
        outcome = pick_pve_outcome(
            location=PveLocationKind.DUNGEON,
            balance=cfg,
            random=scripted,
        )
        assert outcome.branch.sign is PveSign.GAIN
        assert outcome.length_delta_cm > 0
        assert outcome.drops == ()

    def test_loss_branch_negative_delta(self) -> None:
        cfg = _balance()
        # outcomes[4] = heavy_loss
        scripted = ScriptedRandom(
            weighted_indexes=[4],
            randints=[cfg.dungeon.outcomes[4].max, 100, 100, 100],
        )
        outcome = pick_pve_outcome(
            location=PveLocationKind.DUNGEON,
            balance=cfg,
            random=scripted,
        )
        assert outcome.branch.sign is PveSign.LOSS
        assert outcome.length_delta_cm == -cfg.dungeon.outcomes[4].max

    def test_three_drops_when_all_slots_hit(self) -> None:
        cfg = _balance()
        # dungeon.drop.max_drops=3, probability_percent=50. Все 3 ролла = 1 → 3 дропа.
        # Спринт 3.1-C: на каждый из 3 дропов добавлен weighted_choice на
        # слот перед weighted_choice на rarity.
        scripted = ScriptedRandom(
            weighted_indexes=[
                0,  # branch=scarce_gain
                0,
                0,  # drop1: slot=HAT, rarity=common
                0,
                0,  # drop2: slot=HAT, rarity=common
                0,
                0,  # drop3: slot=HAT, rarity=common
            ],
            randints=[
                cfg.dungeon.outcomes[0].min,  # length
                1,
                1,
                1,  # 3 drop rolls, all <= 50 → 3 дропа
            ],
            choices=[0, 0, 0],  # 3 предмета из (HAT, COMMON) pool
        )
        outcome = pick_pve_outcome(
            location=PveLocationKind.DUNGEON,
            balance=cfg,
            random=scripted,
        )
        assert len(outcome.drops) == 3

    def test_partial_drops(self) -> None:
        # dungeon: probability=50. 1 ≤ 50 → дроп; 100 > 50 → нет; 1 ≤ 50 → дроп.
        cfg = _balance()
        scripted = ScriptedRandom(
            # branch + 2 × (slot, rarity) для 2 реальных дропов.
            weighted_indexes=[0, 0, 0, 0, 0],
            randints=[
                cfg.dungeon.outcomes[0].min,
                1,  # slot 0: drop
                100,  # slot 1: skip
                1,  # slot 2: drop
            ],
            choices=[0, 0],
        )
        outcome = pick_pve_outcome(
            location=PveLocationKind.DUNGEON,
            balance=cfg,
            random=scripted,
        )
        assert len(outcome.drops) == 2


# -- Stress (smoke) -----------------------------------------------------------


class TestStressMountains:
    def test_1000_rolls_invariants(self) -> None:
        cfg = _balance()
        rng = FakeRandom(seed=12345)
        max_abs_length = max(o.max for o in cfg.mountains.outcomes)
        max_drops = cfg.mountains.drop.max_drops
        valid_branch_names = {o.name for o in cfg.mountains.outcomes}

        gain_count = 0
        loss_count = 0
        drop_counts: list[int] = []

        for _ in range(1000):
            outcome = pick_pve_outcome(
                location=PveLocationKind.MOUNTAINS,
                balance=cfg,
                random=rng,
            )
            assert outcome.branch.name in valid_branch_names
            assert -max_abs_length <= outcome.length_delta_cm <= max_abs_length
            assert 0 <= len(outcome.drops) <= max_drops
            for drop in outcome.drops:
                assert isinstance(drop, PveItemDrop)
                assert drop.item.id  # non-empty
            if outcome.branch.sign is PveSign.GAIN:
                assert outcome.length_delta_cm >= 0
                gain_count += 1
            else:
                assert outcome.length_delta_cm <= 0
                loss_count += 1
            drop_counts.append(len(outcome.drops))

        # Распределение знаков: gain-веса 60, loss-веса 40 → ~60/40.
        # Допуск ±10% (на 1000 rolls дисперсия ~1.5%).
        assert 500 <= gain_count <= 700, f"gain_count={gain_count}"
        assert 300 <= loss_count <= 500, f"loss_count={loss_count}"


class TestStressDungeon:
    def test_1000_rolls_invariants(self) -> None:
        cfg = _balance()
        rng = FakeRandom(seed=54321)
        max_abs_length = max(o.max for o in cfg.dungeon.outcomes)
        max_drops = cfg.dungeon.drop.max_drops

        for _ in range(1000):
            outcome = pick_pve_outcome(
                location=PveLocationKind.DUNGEON,
                balance=cfg,
                random=rng,
            )
            assert -max_abs_length <= outcome.length_delta_cm <= max_abs_length
            assert 0 <= len(outcome.drops) <= max_drops
            if outcome.branch.sign is PveSign.GAIN:
                assert outcome.length_delta_cm >= 0
            else:
                assert outcome.length_delta_cm <= 0


class TestPickerOutcomeShape:
    def test_returns_pve_run_outcome(self) -> None:
        cfg = _balance()
        outcome = pick_pve_outcome(
            location=PveLocationKind.MOUNTAINS,
            balance=cfg,
            random=FakeRandom(seed=1),
        )
        assert isinstance(outcome, PveRunOutcome)
        assert isinstance(outcome.branch, PveOutcomeBranch)

    def test_drops_is_tuple(self) -> None:
        cfg = _balance()
        outcome = pick_pve_outcome(
            location=PveLocationKind.DUNGEON,
            balance=cfg,
            random=FakeRandom(seed=1),
        )
        # Tuple, чтобы исход был immutable.
        assert isinstance(outcome.drops, tuple)
