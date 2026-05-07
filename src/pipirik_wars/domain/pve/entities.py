"""Общие domain-сущности PvE-локаций с ±-исходами (горы, данжон) — ГДД §8.

В отличие от леса (`domain/forest/`), где исход всегда положительный
(`+Δ длины`), горы и данжон имеют ветки и `gain` (награда), и `loss`
(потеря). Структурно обе локации идентичны (5 веток исхода: 3 gain +
2 loss, кулдаун-границы, drop-конфиг с `max_drops`), отличаются только
балансовыми числами в `config/balance.yaml`. Поэтому VO исхода и
picker — общие, см. `domain/pve/services.py`.

Имена в горах/данжоне **не дропаются** (ГДД §2.5 — имена только из
леса). Скроллы заточки (Спринт 3.1-D) и оружие в `right_hand`/`left_hand`
(Спринт 3.1-C) подключатся к этому VO позже без ломающих изменений.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from pipirik_wars.domain.balance.config import PveSign, Rarity, Slot
from pipirik_wars.domain.forest.entities import Item

__all__ = [
    "Item",
    "PveItemDrop",
    "PveLocationKind",
    "PveOutcomeBranch",
    "PveRunOutcome",
    "PveSign",
    "Rarity",
    "Slot",
]


class PveLocationKind(str, enum.Enum):
    """Какая PvE-локация с ±-механикой разыгрывается.

    Используется picker-ом `pick_pve_outcome` для выбора секции
    `BalanceConfig.mountains` или `BalanceConfig.dungeon`.
    """

    MOUNTAINS = "mountains"
    DUNGEON = "dungeon"


@dataclass(frozen=True, slots=True)
class PveOutcomeBranch:
    """Ветка исхода PvE-локации.

    `name` — стабильный машинный идентификатор ветки в `balance.yaml`
    (`scarce_gain` / `normal_gain` / ... / `heavy_loss`); презентер
    подбирает локализованную метку отдельно. `sign` — знак ветки
    (`gain`/`loss`). `length_cm` — фактическое **абсолютное** значение
    `Δ длины` (без знака), реальный знак применяет use-case при
    начислении (`progression.add_length(...)` для `gain`,
    `progression.subtract_length(...)` для `loss`).
    """

    name: str
    sign: PveSign
    length_cm: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("PveOutcomeBranch.name must be non-empty")
        if self.length_cm < 0:
            raise ValueError(
                f"PveOutcomeBranch.length_cm must be >= 0 (sign-less abs value), "
                f"got {self.length_cm}"
            )


@dataclass(frozen=True, slots=True)
class PveItemDrop:
    """Один дроп предмета из PvE-локации.

    Reuse `Item` из `domain/forest/entities.py` — каталог предметов
    общий (`balance.items_catalog`). Спринт 3.1-C расширит каталог
    оружием (`right_hand`/`left_hand`) — picker автоматически начнёт
    дропать его, как только эти слоты появятся в `slot_weights`-конфиге
    локации.
    """

    item: Item


@dataclass(frozen=True, slots=True)
class PveRunOutcome:
    """Результат расчёта PvE-похода (без I/O).

    `branch` — какая из веток сработала; `length_delta_cm` —
    **знаковое** значение прибавки/потери длины (применяется как есть:
    положительное → `add_length`, отрицательное → `subtract_length`).
    `drops` — упорядоченный список дропов (от 0 до `drop.max_drops`),
    каждый — `PveItemDrop`. Имена в этой локации не дропаются.

    Use-case `Finish*Run` (Спринт 3.1-B) превратит этот VO в side-эффекты:
    запись в `mountain_runs`/`dungeon_runs`, прибавку/списание длины,
    добавление предметов в инвентарь, audit-лог.
    """

    branch: PveOutcomeBranch
    length_delta_cm: int
    drops: tuple[PveItemDrop, ...]

    def __post_init__(self) -> None:
        if self.branch.sign is PveSign.GAIN and self.length_delta_cm < 0:
            raise ValueError(
                f"PveRunOutcome: gain-branch must have length_delta_cm >= 0, "
                f"got {self.length_delta_cm}"
            )
        if self.branch.sign is PveSign.LOSS and self.length_delta_cm > 0:
            raise ValueError(
                f"PveRunOutcome: loss-branch must have length_delta_cm <= 0, "
                f"got {self.length_delta_cm}"
            )
        if abs(self.length_delta_cm) != self.branch.length_cm:
            raise ValueError(
                f"PveRunOutcome: |length_delta_cm| ({abs(self.length_delta_cm)}) "
                f"must equal branch.length_cm ({self.branch.length_cm})"
            )
