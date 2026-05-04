"""Domain-сущности леса (ГДД §8.2, ГДД §2.6, ГДД §2.5).

`Slot` и `Rarity` живут в `domain/balance/config.py` (ими типизирован
сам каталог `items_catalog`); здесь они только реэкспортируются для
короткого импорта `from pipirik_wars.domain.forest import Slot`.

`Drop` — алгебраический тип результата дропа: либо ничего
(`NoDrop`), либо предмет (`ItemDrop`), либо имя (`NameDrop`).
Использование Python-pattern-matching на `Drop` остаётся
единственным способом «развернуть» дроп в use-case-ах /
handler-ах слоёв выше.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.balance.config import Rarity, Slot

__all__ = [
    "Drop",
    "ForestRunOutcome",
    "Item",
    "ItemDrop",
    "Name",
    "NameDrop",
    "NoDrop",
    "OutcomeBranch",
    "Rarity",
    "Slot",
]


@dataclass(frozen=True, slots=True)
class Item:
    """Конкретный предмет экипировки из каталога.

    `id` — стабильный машинный идентификатор каталога
    (`item.<slot>.<short>`). `display_name` показывается игроку.
    """

    id: str
    slot: Slot
    display_name: str
    rarity: Rarity


@dataclass(frozen=True, slots=True)
class Name:
    """Имя — отдельная сущность, «7-й слот» (ГДД §2.5).

    Не несёт редкости. Дропается из `names_catalog`.
    """

    value: str


@dataclass(frozen=True, slots=True)
class OutcomeBranch:
    """Одна из веток исхода леса (`scarce` / `normal` / `abundant`)."""

    name: str
    length_cm: int


@dataclass(frozen=True, slots=True)
class NoDrop:
    """Лес ничего не дропнул (вероятность `1 - drop.probability_percent / 100`)."""


@dataclass(frozen=True, slots=True)
class ItemDrop:
    """Лес дропнул предмет экипировки."""

    item: Item


@dataclass(frozen=True, slots=True)
class NameDrop:
    """Лес дропнул имя (единственный путь его получить, ГДД §2.5)."""

    name: Name


Drop = NoDrop | ItemDrop | NameDrop


@dataclass(frozen=True, slots=True)
class ForestRunOutcome:
    """Результат расчёта похода в лес (без I/O).

    `branch` — какая из 3 веток сработала; `length_cm` — фактическая
    прибавка длины, ∈ `[branch.min, branch.max]`; `drop` — результат
    дропа (один из `NoDrop` / `ItemDrop` / `NameDrop`).

    Use-case `FinishForestRun` (Спринт 1.3.C) превратит этот объект в
    side-эффекты: запись в `forest_runs`, начисление длины через
    `progression.add_length`, добавление предмета в `inventory`,
    смену активного имени, audit-лог и т. д.
    """

    branch: OutcomeBranch
    length_cm: int
    drop: Drop
