"""Чистый picker заточки `pick_enchant_outcome` (ГДД §2.8.3, §2.8.4, §2.8.6).

Единственная точка домена, где разыгрывается исход одной попытки
заточки: возвращает один из `RegularEnchantOutcome` (4 значения)
или `BlessedEnchantOutcome` (5 значений) **детерминировано**
относительно `IRandom`.

Логика:

1. **Safe-zone** (level < `safe_zone_max_level` из конфига) — forced
   `SUCCESS` для regular / `SUCCESS_1` для blessed. Никаких roll-ов
   не делается, `IRandom` не дёргается. ГДД §2.8.6: «до `+3`
   разрушений и падений нет» — это и реализуется тут.
2. **Иначе** — `weighted_choice` на исходах текущего level-а.
   Веса берутся из `regular_outcomes_per_level[level]` или
   `blessed_outcomes_per_level[level]` (см. `EnchantmentConfig`,
   ГДД §2.8.6 — полные таблицы для всех уровней `0..29`).

Picker сам **не** применяет исход к `Item`. Это делает use-case
`EnchantItem` (3.4-C): после ролла он зовёт `item.with_enchant_level(
new_level)` (с `clamp(0, 30)` для `DROP`/`DROP_1`/`DROP_2`),
списывает скролл, пишет audit. Picker — чистая функция от
`(level, blessed, weights, random)`.

`clamp(0, 30)` на нижней границе для `DROP` — ответственность
**use-case-а 3.4-C**, не picker-а: picker возвращает enum-исход,
а new_level вычисляется в use-case-е (`max(0, level - delta)`).
Тут (в picker-е) clamp не нужен — мы возвращаем только enum,
не int. Тест A.5 (c) проверяет, что при `level=0` и
`outcome=DROP` use-case 3.4-C уйдёт в `level=0` (не в `-1`).

В тестах picker гоняется на `FakeRandom(seed=...)` с зафиксированным
seed-ом — так получаем 3σ-Bernoulli-проверку частот всех 4/5
исходов на каждом тире (см. `tests/unit/domain/inventory/
test_enchant_picker.py`).
"""

from __future__ import annotations

from typing import TypeVar

from pipirik_wars.domain.balance.config import (
    BlessedLevelWeights,
    EnchantmentConfig,
    RegularLevelWeights,
)
from pipirik_wars.domain.inventory.entities import (
    MAX_ENCHANT_LEVEL,
    BlessedEnchantOutcome,
    EnchantOutcome,
    RegularEnchantOutcome,
)
from pipirik_wars.domain.shared.ports import IRandom

__all__ = ["pick_enchant_outcome"]

_T = TypeVar("_T")

# Грубое целочисленное представление весов для `IRandom.weighted_choice`.
# Все веса в `EnchantmentConfig` — `float` в `[0.0, 1.0]` с шагом ~0.001
# (см. ГДД §2.8.6 — три знака после запятой). Умножение на `_WEIGHT_SCALE`
# гарантирует, что `weighted_choice(int weights)` соответствует исходным
# `float`-долям с погрешностью ≤ 1 / `_WEIGHT_SCALE`. На 3σ-Bernoulli
# тестах (n=10 000 трайлов на тир) это не вносит видимого смещения.
_WEIGHT_SCALE: int = 100_000


def pick_enchant_outcome(
    *,
    level: int,
    blessed: bool,
    config: EnchantmentConfig,
    random: IRandom,
) -> EnchantOutcome:
    """Разыграть один исход заточки.

    Pre:
    - `0 <= level <= MAX_ENCHANT_LEVEL - 1` (т. е. `[0, 29]`):
      попытка заточить `+30 → +31` логически невозможна и должна
      быть отсечена use-case-ом `EnchantItem` (3.4-C) raising
      `MaxLevelReachedError`. Если она всё же сюда дошла —
      `ValueError` (defence-in-depth).
    - `config` — провалидированный `EnchantmentConfig` (pydantic-инвариант
      гарантирует: сумма весов = 1.0 ± ε для каждой строки;
      `safe-zone-zero` для drop/destroy; `blessed_outcomes_per_level
      ["29"].success_2 == 0.0`).

    Returns:
    - `RegularEnchantOutcome` (4 значения) если `blessed=False`;
    - `BlessedEnchantOutcome` (5 значений) если `blessed=True`.

    Семантика safe-zone (ГДД §2.8.6 «до `+3` разрушений и падений нет»):

    - `level < config.safe_zone_max_level` → forced `SUCCESS` /
      `SUCCESS_1`. `IRandom` не вызывается — детерминированный путь
      без roll-а.
    """
    if not 0 <= level <= MAX_ENCHANT_LEVEL - 1:
        raise ValueError(
            f"pick_enchant_outcome: level must be in [0, {MAX_ENCHANT_LEVEL - 1}], got {level}",
        )

    if level < config.safe_zone_max_level:
        return BlessedEnchantOutcome.SUCCESS_1 if blessed else RegularEnchantOutcome.SUCCESS

    if blessed:
        return _roll_blessed(
            weights=config.blessed_outcomes_per_level[level],
            random=random,
        )
    return _roll_regular(
        weights=config.regular_outcomes_per_level[level],
        random=random,
    )


def _roll_regular(
    *,
    weights: RegularLevelWeights,
    random: IRandom,
) -> RegularEnchantOutcome:
    """Взвешенный выбор из 4 regular-исходов.

    Веса с `0.0` отфильтровываются (`IRandom.weighted_choice` требует
    `weight > 0`); если за safe-zone-ой `drop`/`destroy` стали `0.0`,
    они тоже выпадут из пула — но `EnchantmentConfig`-инвариант
    «safe-zone-zero **только** для уровней < `safe_zone_max_level`»
    гарантирует, что для `level >= safe_zone_max_level` хотя бы
    один из `drop`/`destroy` ненулевой (иначе сумма не сошлась бы
    к 1.0 после `success + no_effect`).
    """
    pairs: tuple[tuple[RegularEnchantOutcome, float], ...] = (
        (RegularEnchantOutcome.SUCCESS, weights.success),
        (RegularEnchantOutcome.NO_EFFECT, weights.no_effect),
        (RegularEnchantOutcome.DROP, weights.drop),
        (RegularEnchantOutcome.DESTROY, weights.destroy),
    )
    return _weighted_choice(pairs=pairs, random=random)


def _roll_blessed(
    *,
    weights: BlessedLevelWeights,
    random: IRandom,
) -> BlessedEnchantOutcome:
    """Взвешенный выбор из 5 blessed-исходов.

    На `level == 29` `weights.success_2 == 0.0` (pydantic-инвариант
    `EnchantmentConfig`, ГДД §2.8.4) — этот вариант просто выпадает
    из пула.
    """
    pairs: tuple[tuple[BlessedEnchantOutcome, float], ...] = (
        (BlessedEnchantOutcome.SUCCESS_1, weights.success_1),
        (BlessedEnchantOutcome.SUCCESS_2, weights.success_2),
        (BlessedEnchantOutcome.NO_EFFECT, weights.no_effect),
        (BlessedEnchantOutcome.DROP_1, weights.drop_1),
        (BlessedEnchantOutcome.DROP_2, weights.drop_2),
    )
    return _weighted_choice(pairs=pairs, random=random)


def _weighted_choice(
    *,
    pairs: tuple[tuple[_T, float], ...],
    random: IRandom,
) -> _T:
    """`IRandom.weighted_choice` на парах `(outcome, float-weight)`.

    Пары с весом `0.0` отфильтровываются (требование `IRandom`).
    Float-веса масштабируются в `int` через `_WEIGHT_SCALE` —
    это нужно потому, что `IRandom.weighted_choice` принимает
    `Sequence[int]`. Погрешность округления ≤ `1 / _WEIGHT_SCALE`
    = `0.00001` — на 3σ-Bernoulli тестах не различима.
    """
    non_zero = tuple((c, w) for c, w in pairs if w > 0.0)
    items = [c for c, _ in non_zero]
    int_weights = [round(w * _WEIGHT_SCALE) for _, w in non_zero]
    return random.weighted_choice(items, int_weights)
