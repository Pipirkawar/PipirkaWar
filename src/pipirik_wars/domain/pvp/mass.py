"""Доменные value-objects массового PvP клан×клан (ГДД §7.2, Спринт 2.2.B).

Чистые данные, без I/O и без знания инфраструктуры. Все классы —
``frozen=True, slots=True``. Архитектура полностью симметрична 1×1
(`domain/pvp/entities.py`):

* Уровень удара/блока — общий enum :class:`Position` из
  `domain/pvp/entities.py` (HIGH/MID/LOW). Никакого дублирования.
* Бой — **один тик** (ГДД §7.2 / 2.2.4): каждый участник заявляет
  одну атаку и один блок, RNG строит пары «атакующий → защитник»,
  все удары разрешаются одновременно по той же 3×3 матрице
  `attack == block ⇒ blocked`.
* Path-independent: длины игроков фиксируются на старте боя, и весь
  ущерб считается от этих фиксированных значений. После применения
  результата длины могут уйти в 0 — победитель определяется по
  суммарному dealt'у (а не по «выживаемости»), что даёт стабильный
  ничейный результат при равном суммарном уроне.
* Без ``random`` — pairing-функция (`domain/pvp/mass_services.py`)
  принимает :class:`IRandom` извне; чистые VO в этом модуле никаких
  RNG-вызовов не делают.

Терминология «clan1 / clan2» (а не «p1/p2», как в 1×1) — потому что
с каждой стороны может быть несколько игроков. Конкретные участники
адресуются через ``player_id: int`` (ID пользователя в БД).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pipirik_wars.domain.pvp.entities import Position

__all__ = [
    "MassDamageEntry",
    "MassDuelOutcome",
    "MassDuelWinner",
    "MassPairing",
    "MassRoundChoice",
    "MassRoundOutcome",
]


class MassDuelWinner(StrEnum):
    """Итог массового PvP-боя по сумме нанесённого урона (ГДД §7.2).

    Симметричный аналог :class:`DuelWinner` для 1×1.
    """

    CLAN1 = "clan1"
    CLAN2 = "clan2"
    DRAW = "draw"


@dataclass(frozen=True, slots=True)
class MassRoundChoice:
    """Выбор одного участника массового боя — 1 атака + 1 блок (ГДД §7.2).

    `player_id` нужен, чтобы связать выбор с конкретным участником
    клана: в массовом бою у каждой стороны несколько игроков, и pair-
    funktion должна знать, кто кого атакует.

    Контракт: `player_id > 0` (ID игрока всегда положительный, см.
    `User.id` в БД). Проверяется в ``__post_init__``.
    """

    player_id: int
    attack: Position
    block: Position

    def __post_init__(self) -> None:
        if self.player_id <= 0:
            raise ValueError(f"player_id must be > 0, got {self.player_id}")


@dataclass(frozen=True, slots=True)
class MassPairing:
    """Одна назначенная пара «атакующий → защитник» внутри массового боя.

    Pair'инг строится pure-функцией ``pair_attackers(...)`` поверх
    :class:`IRandom`. Пары формируются в обе стороны независимо
    (clan1→clan2 и clan2→clan1), так как атаки симметричные: один и
    тот же игрок может одновременно быть атакующим (по своей
    перестановке) и защитником (по перестановке оппонента).

    Контракт: `attacker_id != defender_id` (атаковать самого себя
    бессмысленно), оба ID > 0.
    """

    attacker_id: int
    defender_id: int

    def __post_init__(self) -> None:
        if self.attacker_id <= 0:
            raise ValueError(f"attacker_id must be > 0, got {self.attacker_id}")
        if self.defender_id <= 0:
            raise ValueError(f"defender_id must be > 0, got {self.defender_id}")
        if self.attacker_id == self.defender_id:
            raise ValueError(f"attacker_id and defender_id must differ, got {self.attacker_id}")


@dataclass(frozen=True, slots=True)
class MassDamageEntry:
    """Один разрешённый удар внутри массового тика (ГДД §7.2).

    * `attacker_id` атакует `defender_id` своей `attack: Position`.
    * Защитник в это время держит блок `defender_block: Position`.
    * Если позиции совпадают — `blocked = True`, `damage_cm = 0`.
      Иначе `blocked = False`, `damage_cm = floor(L * hit_pct / 100)`,
      где `L` — длина защитника на момент СТАРТА БОЯ (path-independent).

    Используется для аудита и UI: каждый раз, когда мы рендерим
    «карточку результата» массового боя, мы знаем точную пошаговую
    разбивку «кто кого ударил, кого заблокировал, на сколько см».
    """

    attacker_id: int
    defender_id: int
    attacker_attack: Position
    defender_block: Position
    blocked: bool
    damage_cm: int

    def __post_init__(self) -> None:
        if self.attacker_id <= 0:
            raise ValueError(f"attacker_id must be > 0, got {self.attacker_id}")
        if self.defender_id <= 0:
            raise ValueError(f"defender_id must be > 0, got {self.defender_id}")
        if self.attacker_id == self.defender_id:
            raise ValueError(f"attacker_id and defender_id must differ, got {self.attacker_id}")
        if self.damage_cm < 0:
            raise ValueError(f"damage_cm must be >= 0, got {self.damage_cm}")
        if self.blocked and self.damage_cm != 0:
            raise ValueError(f"blocked hit must have damage_cm == 0, got {self.damage_cm}")


@dataclass(frozen=True, slots=True)
class MassRoundOutcome:
    """Результат одного «тика» массового PvP-боя (= одного раунда).

    Семантика полей:

    * `damage_entries` — все разрешённые в этом тике удары (включая
      заблокированные), независимо в каком направлении (clan1→clan2
      или clan2→clan1). Порядок повторяет порядок pairing'а; стабилен
      по seed-у RNG.
    * `clan1_total_dealt` / `clan2_total_dealt` — сумма успешного
      урона, нанесённого каждой стороной. По определению,
      `clan1_total_dealt == sum(damage_cm for e in damage_entries
      if e.attacker_id ∈ clan1_player_ids)`.
    """

    damage_entries: tuple[MassDamageEntry, ...]
    clan1_total_dealt: int
    clan2_total_dealt: int

    def __post_init__(self) -> None:
        if self.clan1_total_dealt < 0:
            raise ValueError(f"clan1_total_dealt must be >= 0, got {self.clan1_total_dealt}")
        if self.clan2_total_dealt < 0:
            raise ValueError(f"clan2_total_dealt must be >= 0, got {self.clan2_total_dealt}")


@dataclass(frozen=True, slots=True)
class MassDuelOutcome:
    """Итог массового PvP-боя клан×клан (ГДД §7.2).

    Свойства:

    * Бой — **zero-sum** по сумме длины:
      `clan1_delta_cm + clan2_delta_cm == 0`. Каждый см, потерянный
      одной стороной (`damage_entries`), прибавляется к длине другой
      (anti-cheat-cap из 1.6 применяется в use-case-е через
      `progression.add_length`, не в чистом домене).
    * `winner == DRAW` ⇔ `clan1_total_dealt == clan2_total_dealt`.
      Иначе — сторона с большим суммарным dealt-ом.
    * `outcome` (один тик) — снапшот всех ударов; на текущий момент в
      масс-PvP **только один тик** (ГДД §7.2 / 2.2.4 — «все удары за
      один тик»), поэтому здесь хранится одно :class:`MassRoundOutcome`,
      а не tuple. Если в будущем появится «multi-tick mass-PvP»
      (резерв на 2.2.K и далее), достаточно заменить тип на
      `tuple[MassRoundOutcome, ...]` и обновить :func:`resolve_mass_duel`.
    """

    outcome: MassRoundOutcome
    clan1_total_dealt: int
    clan2_total_dealt: int
    clan1_delta_cm: int
    clan2_delta_cm: int
    winner: MassDuelWinner

    def __post_init__(self) -> None:
        if self.clan1_total_dealt < 0:
            raise ValueError(f"clan1_total_dealt must be >= 0, got {self.clan1_total_dealt}")
        if self.clan2_total_dealt < 0:
            raise ValueError(f"clan2_total_dealt must be >= 0, got {self.clan2_total_dealt}")
        if self.clan1_delta_cm + self.clan2_delta_cm != 0:
            raise ValueError(
                "mass duel outcome must be zero-sum: "
                f"clan1_delta_cm={self.clan1_delta_cm}, "
                f"clan2_delta_cm={self.clan2_delta_cm}"
            )
