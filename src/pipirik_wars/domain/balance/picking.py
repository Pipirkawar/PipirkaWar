"""Розыгрыш предмета дропа из `items_catalog` (Спринт 3.1-C, ГДД §2.6).

Общая логика для `domain/forest/services.py` и `domain/pve/services.py`:

1. Слот предмета — `weighted_choice` среди слотов с весом `> 0`
   в `slot_weights` (per-location). Слоты с весом `0` не дропают
   в этой локации (например, `right_hand`/`left_hand` в лесу).
2. Редкость — `weighted_choice` на 3 редкостях через `rarity_weights`.
3. Конкретная позиция — `random.choice` из `items_catalog`,
   отфильтрованного по `(slot, rarity)`.

Пред-условие, гарантированное `BalanceConfig._validate_drop_slot_rarity_coverage`:
для каждой `(slot, rarity)`-пары, где `slot_weights[slot] > 0`,
в каталоге `≥ 1` предмет — `random.choice` никогда не получит
пустой pool на проверенном балансе.

Каждый из forest и pve сам отвечает за внешний контур (Bernoulli по
`probability_percent`, обёртка результата в свой `ItemDrop` /
`PveItemDrop` / `Item`-сущность).

Никаких side-эффектов: чистая функция от `BalanceConfig` и
детерминированного `IRandom`. Подходит для unit-тестов на
`ScriptedRandom` / `FakeRandom(seed=...)`.
"""

from __future__ import annotations

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    ForestRarityWeights,
    ItemEntry,
    Rarity,
    Slot,
    SlotWeights,
)
from pipirik_wars.domain.shared.ports import IRandom


def pick_drop_item_entry(
    *,
    balance: BalanceConfig,
    slot_weights: SlotWeights,
    rarity_weights: ForestRarityWeights,
    random: IRandom,
) -> ItemEntry:
    """Выбрать `ItemEntry` для одного дропа: слот → редкость → конкретная позиция.

    Шаги:

    - **Слот**: `random.weighted_choice` среди слотов с `slot_weights[slot] > 0`.
      `IRandom.weighted_choice` требует `weights > 0`, так что нулевые веса
      отфильтровываются здесь (они означают «слот не дропает в этой локации»).
    - **Редкость**: `random.weighted_choice` на `(Rarity.COMMON, RARE, EPIC)`
      с весами `rarity_weights.common/.rare/.epic`.
    - **Позиция**: `random.choice` из `items_catalog`, отфильтрованного
      по `(slot, rarity)`. Pool гарантированно непуст благодаря кросс-валидации
      `BalanceConfig._validate_drop_slot_rarity_coverage`.

    Pre: `slot_weights` имеет `>0` хотя бы у одного слота
    (`SlotWeights._validate_sum_positive`); `balance` — провалидированный
    `BalanceConfig` (cross-coverage уже проверена).
    """
    slot_pairs = tuple((s, w) for s, w in slot_weights.as_pairs() if w > 0)
    slots = [pair[0] for pair in slot_pairs]
    weights = [pair[1] for pair in slot_pairs]
    slot: Slot = random.weighted_choice(slots, weights)

    rarities: list[Rarity] = [Rarity.COMMON, Rarity.RARE, Rarity.EPIC]
    rarity_w = [rarity_weights.common, rarity_weights.rare, rarity_weights.epic]
    rarity: Rarity = random.weighted_choice(rarities, rarity_w)

    pool = [e for e in balance.items_catalog if e.rarity is rarity and e.slot is slot]
    # Pre-условие, гарантированное `_validate_drop_slot_rarity_coverage`: pool непуст.
    return random.choice(pool)


__all__ = ["pick_drop_item_entry"]
