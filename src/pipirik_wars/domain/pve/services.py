"""Чистая функция расчёта исхода PvE-похода с ±-механикой (ГДД §8).

`pick_pve_outcome(*, location, balance, random)` — единственная точка,
где разыгрывается:

1. Ветка исхода (`scarce_gain` / `normal_gain` / ... / `heavy_loss`) —
   `random.weighted_choice` на `outcomes` локации.
2. Абсолютная величина прибавки/потери — `random.randint(branch.min,
   branch.max)`. Знак применяется по `branch.sign`.
3. Дроп — независимо для каждого из `drop.max_drops` слотов
   (Bernoulli per slot с `p = drop.probability_percent / 100`).
   Если выпал дроп — передаём в `pick_drop_item_entry` (общий хелпер
   с forest, `domain/balance/picking.py`): слот через `weighted_choice`
   на `drop.slot_weights` → редкость через `weighted_choice` на
   `drop.rarity_weights` → `random.choice` из `items_catalog`,
   отфильтрованного по `(slot, rarity)`.

Семантика «0..max_drops предметов за поход» (ГДД §8: «горы 0–1»,
«данжон 0–3») реализуется именно так: распределение числа дропов —
`Binomial(max_drops, p)`, что **не равно** «равномерно по 0..max_drops».
Это намеренно: pulling 3 редких предметов в данжоне должно быть
заметно реже, чем 1, и `Binomial(3, 0.5)` даёт 12.5% / 37.5% / 37.5% / 12.5%
для 0/1/2/3 дропов — приемлемая «лестница».

Никаких side-эффектов. Имена не дропаются (ГДД §2.5 — только лес).
Оружие (`right_hand`/`left_hand`) дропает в горах/данжоне согласно
весам `slot_weights` per-location (Спринт 3.1-C); в лесу веса этих
слотов = 0.

Параметры передаются явно — функция тривиально тестируется на
`FakeRandom(seed=...)` + валидном `BalanceConfig` (см. `factories.py`).
"""

from __future__ import annotations

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    PveSign,
    ScrollCategoryWeights,
    ScrollDropConfig,
    _PveLocationConfig,
)
from pipirik_wars.domain.balance.picking import pick_drop_item_entry
from pipirik_wars.domain.enchantment.entities import Scroll, ScrollCategory
from pipirik_wars.domain.forest.entities import Item, Rarity, Slot
from pipirik_wars.domain.pve.entities import (
    PveItemDrop,
    PveLocationKind,
    PveOutcomeBranch,
    PveRunOutcome,
    PveScrollDrop,
)
from pipirik_wars.domain.shared.ports import IRandom


def pick_pve_outcome(
    *,
    location: PveLocationKind,
    balance: BalanceConfig,
    random: IRandom,
) -> PveRunOutcome:
    """Разыграть исход одного похода в горы / данжон.

    Pre: `balance` — провалидированный `BalanceConfig` (`items_catalog`
    непуст; для каждой редкости, попавшей в `rarity_weights` локации,
    в каталоге есть ≥ 1 предмет).
    """
    cfg = _resolve_location_config(balance=balance, location=location)

    branch = _roll_branch(cfg=cfg, random=random)
    drops = tuple(_roll_drops(cfg=cfg, balance=balance, random=random))
    scroll_drops = tuple(_roll_scroll_drops(cfg=cfg.drop.scroll_drops, random=random))

    length_delta_cm = branch.length_cm if branch.sign is PveSign.GAIN else -branch.length_cm
    return PveRunOutcome(
        branch=branch,
        length_delta_cm=length_delta_cm,
        drops=drops,
        scroll_drops=scroll_drops,
    )


def _resolve_location_config(
    *,
    balance: BalanceConfig,
    location: PveLocationKind,
) -> _PveLocationConfig:
    if location is PveLocationKind.MOUNTAINS:
        return balance.mountains
    if location is PveLocationKind.DUNGEON:
        return balance.dungeon
    raise ValueError(f"unknown PveLocationKind: {location!r}")


def _roll_branch(*, cfg: _PveLocationConfig, random: IRandom) -> PveOutcomeBranch:
    outcomes = cfg.outcomes
    branch_idx = random.weighted_choice(
        list(range(len(outcomes))),
        [o.weight for o in outcomes],
    )
    branch_cfg = outcomes[branch_idx]
    length_cm = random.randint(branch_cfg.min, branch_cfg.max)
    return PveOutcomeBranch(
        name=branch_cfg.name,
        sign=branch_cfg.sign,
        length_cm=length_cm,
    )


def _roll_drops(
    *,
    cfg: _PveLocationConfig,
    balance: BalanceConfig,
    random: IRandom,
) -> list[PveItemDrop]:
    drops: list[PveItemDrop] = []
    drop_cfg = cfg.drop
    for _ in range(drop_cfg.max_drops):
        if random.randint(1, 100) > drop_cfg.probability_percent:
            continue
        drops.append(_roll_item_drop(balance=balance, random=random, cfg=cfg))
    return drops


def _roll_item_drop(
    *,
    cfg: _PveLocationConfig,
    balance: BalanceConfig,
    random: IRandom,
) -> PveItemDrop:
    entry = pick_drop_item_entry(
        balance=balance,
        slot_weights=cfg.drop.slot_weights,
        rarity_weights=cfg.drop.rarity_weights,
        random=random,
    )
    item = Item(
        id=entry.id,
        slot=Slot(entry.slot),
        display_name=entry.display_name,
        rarity=Rarity(entry.rarity),
    )
    return PveItemDrop(item=item)


def _roll_scroll_drops(
    *,
    cfg: ScrollDropConfig,
    random: IRandom,
) -> list[PveScrollDrop]:
    """Разыграть дроп скроллов заточки за один поход (Спринт 3.1-D, ГДД §2.8.5).

    Две **независимые** Bernoulli-попытки:
    - `regular` (`blessed=False`) с шансом `cfg.regular_chance_percent`;
    - `blessed` (`blessed=True`) с шансом `cfg.blessed_chance_percent`.

    Если попытка успешна — категория (weapon/armor/jewelry) выбирается
    `weighted_choice` на `cfg.category_weights`. За один поход можно
    получить 0 / 1 / 2 скролла (regular и blessed не взаимоисключающие).
    """
    drops: list[PveScrollDrop] = []
    if random.randint(1, 100) <= cfg.regular_chance_percent:
        drops.append(
            PveScrollDrop(
                scroll=Scroll(
                    category=_pick_scroll_category(weights=cfg.category_weights, random=random),
                    blessed=False,
                ),
            )
        )
    if random.randint(1, 100) <= cfg.blessed_chance_percent:
        drops.append(
            PveScrollDrop(
                scroll=Scroll(
                    category=_pick_scroll_category(weights=cfg.category_weights, random=random),
                    blessed=True,
                ),
            )
        )
    return drops


def _pick_scroll_category(
    *,
    weights: ScrollCategoryWeights,
    random: IRandom,
) -> ScrollCategory:
    """Выбрать категорию скролла через `weighted_choice`.

    Категории с весом `0` отфильтровываются (`weighted_choice` требует
    `weight > 0`). Pre: сумма весов > 0 (гарантирует
    `ScrollCategoryWeights._validate_sum_positive`).
    """
    pairs: tuple[tuple[ScrollCategory, int], ...] = (
        (ScrollCategory.WEAPON, weights.weapon),
        (ScrollCategory.ARMOR, weights.armor),
        (ScrollCategory.JEWELRY, weights.jewelry),
    )
    non_zero = tuple((c, w) for c, w in pairs if w > 0)
    categories = [c for c, _ in non_zero]
    ws = [w for _, w in non_zero]
    return random.weighted_choice(categories, ws)


__all__ = ["pick_pve_outcome"]
