"""Чистая функция расчёта исхода PvE-похода с ±-механикой (ГДД §8).

`pick_pve_outcome(*, location, balance, random)` — единственная точка,
где разыгрывается:

1. Ветка исхода (`scarce_gain` / `normal_gain` / ... / `heavy_loss`) —
   `random.weighted_choice` на `outcomes` локации.
2. Абсолютная величина прибавки/потери — `random.randint(branch.min,
   branch.max)`. Знак применяется по `branch.sign`.
3. Дроп — независимо для каждого из `drop.max_drops` слотов
   (Bernoulli per slot с `p = drop.probability_percent / 100`).
   Если выпал дроп в слоте — разыгрывается редкость через
   `random.weighted_choice` на `drop.rarity_weights`, затем
   `random.choice` среди предметов нужной редкости из `items_catalog`.

Семантика «0..max_drops предметов за поход» (ГДД §8: «горы 0–1»,
«данжон 0–3») реализуется именно так: распределение числа дропов —
`Binomial(max_drops, p)`, что **не равно** «равномерно по 0..max_drops».
Это намеренно: pulling 3 редких предметов в данжоне должно быть
заметно реже, чем 1, и `Binomial(3, 0.5)` даёт 12.5% / 37.5% / 37.5% / 12.5%
для 0/1/2/3 дропов — приемлемая «лестница».

Никаких side-эффектов. Имена не дропаются (ГДД §2.5 — только лес).
Оружие (`right_hand`/`left_hand`) автоматически начнёт дропать, как
только эти слоты появятся в `items_catalog` (Спринт 3.1-C).

Параметры передаются явно — функция тривиально тестируется на
`FakeRandom(seed=...)` + валидном `BalanceConfig` (см. `factories.py`).
"""

from __future__ import annotations

from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    PveSign,
    _PveLocationConfig,
)
from pipirik_wars.domain.forest.entities import Item, Rarity, Slot
from pipirik_wars.domain.pve.entities import (
    PveItemDrop,
    PveLocationKind,
    PveOutcomeBranch,
    PveRunOutcome,
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

    length_delta_cm = branch.length_cm if branch.sign is PveSign.GAIN else -branch.length_cm
    return PveRunOutcome(branch=branch, length_delta_cm=length_delta_cm, drops=drops)


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
    rarity_cfg = cfg.drop.rarity_weights
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
    return PveItemDrop(item=item)


__all__ = ["pick_pve_outcome"]
