"""Доменные value-objects PvP 1×1 (ГДД §7.1).

Чистые данные без I/O и без знания инфраструктуры. Все классы —
`frozen=True, slots=True` (нельзя мутировать, нельзя добавлять
неизвестные атрибуты на лету).

Архитектурное решение: атаки и блоки моделируются единым enum-ом
`Position` (HIGH/MID/LOW) с тонкой обёрткой `RoundChoice(attack, block)`,
а не двумя отдельными enum-ами `Attack` / `Block`. Причины:

* В ГДД §7.1 «6 кнопок (3 атаки + 3 блока)» — это 3 уровня нанесения и
  3 уровня защиты ОДНОЙ И ТОЙ ЖЕ оси (верх/середина/низ). Введение
  отдельных типов `Attack.HIGH` ≠ `Block.HIGH` потребовало бы кастов
  при сравнении в `resolve_round` (`attack.position == block.position`)
  и порождало бы тривиальные баги.
* Локализация подписей кнопок (`pvp-attack-high` / `pvp-block-high`) —
  забота i18n-слоя в 2.1.C, а не доменных типов.

`DuelWinner` — отдельный enum (а не `Optional[Position]`), потому что
он ортогонален позициям и имеет осмысленное значение `DRAW` — победа
по сумме нанесённого урона, а не по выбранным кнопкам.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "DuelOutcome",
    "DuelWinner",
    "Position",
    "RoundChoice",
    "RoundOutcome",
]


class Position(StrEnum):
    """Уровень удара / защиты — общая ось для атаки и блока (ГДД §7.1).

    Семантика: атака `HIGH` пробивает любой блок, кроме `HIGH`. Блок
    `HIGH` отражает только атаку `HIGH`. Совпадение позиций ⇒
    `attack_blocked = True`.

    Имена `HIGH`/`MID`/`LOW` нейтральны: их локализованные подписи
    («голова/корпус/ноги», «башка/брюхо/щиколотки» и т. п.) живут в
    `locales/{ru,en}.ftl` и подбираются в Спринте 2.1.C, без правок
    доменных типов.
    """

    HIGH = "high"
    MID = "mid"
    LOW = "low"


class DuelWinner(StrEnum):
    """Итог боя по сумме нанесённого урона (ГДД §7.1)."""

    P1 = "p1"
    P2 = "p2"
    DRAW = "draw"


@dataclass(frozen=True, slots=True)
class RoundChoice:
    """Выбор игрока на раунд: 1 атака + 1 блок (ГДД §7.1).

    Игрок отправляет ОБА выбора одновременно (через ЛС-бота, см.
    Спринт 2.1.E). В чистом домене раунд — функция от пары
    `(p1: RoundChoice, p2: RoundChoice)`, без понятия «времени» —
    AFK-таймер и автовыбор живут в `application/`.
    """

    attack: Position
    block: Position


@dataclass(frozen=True, slots=True)
class RoundOutcome:
    """Результат одного раунда (ГДД §7.1).

    Семантика полей:

    * `p1_attack_blocked` — атака p1 попала в блок p2 (`p1.attack == p2.block`).
      При `True` — `p1_damage_to_p2 == 0`.
    * `p2_attack_blocked` — симметрично.
    * `p1_damage_to_p2` / `p2_damage_to_p1` — нанесённые сантиметры
      (всегда `>= 0`). Считается как `floor(defender_initial_length * hit_pct / 100)` —
      см. `resolve_round(...)`.

    Раунд НЕ владеет состоянием длин игроков на момент удара: длины
    переданы внутрь `resolve_round` снаружи (`p1_length_cm`/`p2_length_cm`),
    и одни и те же значения используются на все 3 раунда (path-independent
    модель). Это упрощает тесты и убирает порядок-зависимые квирки.
    """

    p1_choice: RoundChoice
    p2_choice: RoundChoice
    p1_attack_blocked: bool
    p2_attack_blocked: bool
    p1_damage_to_p2: int
    p2_damage_to_p1: int


@dataclass(frozen=True, slots=True)
class DuelOutcome:
    """Итог 3-раундового PvP-боя 1×1 (ГДД §7.1).

    Свойства:

    * Бой — zero-sum по длине: `p1_delta_cm + p2_delta_cm == 0`.
      Каждый сантиметр, потерянный одной стороной, прибавляется к
      длине другой (лимит anti-cheat-cap из 1.6 применяется в
      use-case-е через `progression.add_length`, не в чистом домене).
    * `winner == DRAW` ⇔ `p1_total_dealt == p2_total_dealt`. Иначе
      побеждает сторона с большим суммарным dealt-ом.
    * `rounds` — кортеж из ровно 3 элементов (валидируется в
      `resolve_duel(...)`).
    """

    rounds: tuple[RoundOutcome, ...]
    p1_total_dealt: int
    p2_total_dealt: int
    p1_delta_cm: int
    p2_delta_cm: int
    winner: DuelWinner
