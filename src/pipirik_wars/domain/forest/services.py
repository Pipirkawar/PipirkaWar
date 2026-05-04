"""Чистая функция расчёта исхода похода в лес (ГДД §8.2, ГДД §1.3.4-§1.3.5).

`compute_forest_outcome(*, balance, random)` — единственная точка, где
розыгрывается:

1. Ветка исхода (`scarce` / `normal` / `abundant`) — `random.weighted_choice`
   на `forest.outcomes`.
2. Прибавка длины — `random.randint(branch.min, branch.max)`.
3. Дроп — `random.randint(1, 100)` против `forest.drop.probability_percent`.
   Если выпал дроп — `random.randint(1, 100)` против `name_share_percent`
   решает «имя или предмет». Для предмета сначала разыгрывается редкость
   через `random.weighted_choice` на `forest.drop.rarity_weights`,
   затем `random.choice` среди предметов нужной редкости.

Никаких side-эффектов: запись в БД / начисление длины / смена ника
будут в use-case-е `FinishForestRun` (Спринт 1.3.C).

Параметры передаются явно, без внутреннего состояния — функция тривиально
тестируется на детерминированном `FakeRandom(seed=...)` и валидном
`BalanceConfig`.
"""

from __future__ import annotations

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.forest.entities import (
    Drop,
    ForestRunOutcome,
    Item,
    ItemDrop,
    Name,
    NameDrop,
    NoDrop,
    OutcomeBranch,
    Rarity,
    Slot,
)
from pipirik_wars.domain.shared.ports import IRandom


def compute_forest_outcome(*, balance: BalanceConfig, random: IRandom) -> ForestRunOutcome:
    """Разыграть исход одного похода в лес.

    Не пишет ничего наружу. Возвращает `ForestRunOutcome`, который
    use-case `FinishForestRun` уже превратит в БД-операции.

    Pre: `balance` — провалидированный `BalanceConfig` (items_catalog
    непуст, у каждой редкости ≥ 1 предмет, names_catalog ≥ 30 имён).
    """
    forest = balance.forest

    # 1. Ветка исхода.
    outcomes = forest.outcomes
    branch_idx = random.weighted_choice(
        list(range(len(outcomes))),
        [o.weight for o in outcomes],
    )
    branch_cfg = outcomes[branch_idx]
    length_cm = random.randint(branch_cfg.min, branch_cfg.max)
    branch = OutcomeBranch(name=branch_cfg.name, length_cm=length_cm)

    # 2. Дроп (общий шанс).
    drop = _roll_drop(balance=balance, random=random)

    return ForestRunOutcome(branch=branch, length_cm=length_cm, drop=drop)


def _roll_drop(*, balance: BalanceConfig, random: IRandom) -> Drop:
    drop_cfg = balance.forest.drop

    if random.randint(1, 100) > drop_cfg.probability_percent:
        return NoDrop()

    if random.randint(1, 100) <= drop_cfg.name_share_percent:
        return _roll_name_drop(balance=balance, random=random)

    return _roll_item_drop(balance=balance, random=random)


def _roll_name_drop(*, balance: BalanceConfig, random: IRandom) -> NameDrop:
    value = random.choice(list(balance.names_catalog))
    return NameDrop(name=Name(value=value))


def _roll_item_drop(*, balance: BalanceConfig, random: IRandom) -> ItemDrop:
    rarity_cfg = balance.forest.drop.rarity_weights
    rarities: list[Rarity] = [Rarity.COMMON, Rarity.RARE, Rarity.EPIC]
    weights = [rarity_cfg.common, rarity_cfg.rare, rarity_cfg.epic]
    rarity = random.weighted_choice(rarities, weights)

    pool = [e for e in balance.items_catalog if e.rarity is rarity]
    # Pre-условие, гарантированное pydantic-валидатором: pool непуст.
    entry = random.choice(pool)
    item = Item(
        id=entry.id,
        slot=Slot(entry.slot),
        display_name=entry.display_name,
        rarity=Rarity(entry.rarity),
    )
    return ItemDrop(item=item)
