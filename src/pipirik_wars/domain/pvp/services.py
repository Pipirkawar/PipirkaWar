"""Чистый движок боя PvP 1×1 (ГДД §7.1).

Модуль не знает про БД, aiogram, шедулер или таймеры — это **чистая
функциональная композиция** value-objects из `entities.py`.

Архитектурные решения:

* **Damage formula** — `damage = floor(defender_length_cm * hit_pct / 100)`
  на целочисленном делении (без `Decimal`/`float`). 100 см защитника при
  `hit_pct=10` → 10 см за попадание. На 20 см (минимум для PvP, ГДД §7.1)
  → 2 см за попадание. Целочисленное `floor`-деление гарантирует, что у
  тестов нет проблем с округлением.
* **Path-independent резолв** — все 3 раунда используют ОДНИ И ТЕ ЖЕ
  начальные длины `p1_length_cm` / `p2_length_cm`. Если после раунда 1
  у p2 «осталось бы» меньше длины, во раунде 2 это не учитывается. Так
  проще тестировать: общий нанесённый урон = сумма по 9 потенциальным
  парам в матрице (atk × block). Конечный delta-cm не превышает 30%
  начальной длины (3 раунда × 10% максимум).
* **Zero-sum** — каждый сантиметр, потерянный одной стороной, идёт
  плюсом другой. Фактическое начисление ±длины игрокам делается
  use-case-ом 2.1.E через `progression.add_length(...)` (с anti-cheat-cap-ом),
  чистый домен только считает «кому сколько причитается».
* **Без `random`** — выбор атаки/блока приходит «снаружи» как
  `RoundChoice` (от игрока через ЛС либо от AFK-фоллбэка через
  `IRandom` use-case-а). Чистая функция → детерминированная,
  повторяемая в snapshot-тестах.
"""

from __future__ import annotations

from collections.abc import Sequence

from pipirik_wars.domain.pvp.entities import (
    DuelOutcome,
    DuelWinner,
    Position,
    RoundChoice,
    RoundOutcome,
)
from pipirik_wars.domain.pvp.errors import InvalidLengthError, InvalidRoundCountError

__all__ = [
    "DEFAULT_DUEL_ROUNDS",
    "resolve_duel",
    "resolve_round",
]


DEFAULT_DUEL_ROUNDS: int = 3
"""Количество раундов в дуэли 1×1 по ГДД §7.1.

Параметр движка, чтобы тесты могли симулировать «короткие» (1-2 раунда)
и «длинные» (5+) дуэли без правок чистой функции. Боевой код всегда
передаёт `expected_rounds=balance.pvp.duel_1v1.rounds`.
"""


def _hit_blocked(*, attack: Position, block: Position) -> bool:
    """Атака блокируется только при совпадении позиций.

    `attack=HIGH` ∧ `block=HIGH` ⇒ blocked. Любое другое — пробитие.
    Симметрия осей (3×3 = 9 пар, диагональ — блок, остальные 6 — пробитие).
    """

    return attack == block


def _damage_cm(*, defender_length_cm: int, hit_pct: int) -> int:
    """Нанесённый урон в см при удачном пробитии — `floor(L * pct / 100)`.

    Целочисленное деление гарантирует det-результат и идеальные тесты:
    10% от 23 см = 2 см (а не 2.3); 10% от 7 см = 0 см (защитник
    почти ничего не теряет — это OK для контента, ниже хардкап-cap-а
    1.6 точно поместится).
    """

    return (defender_length_cm * hit_pct) // 100


def resolve_round(
    *,
    p1: RoundChoice,
    p2: RoundChoice,
    p1_length_cm: int,
    p2_length_cm: int,
    hit_pct: int,
) -> RoundOutcome:
    """Разрешить один раунд боя 1×1.

    Аргументы:

    * `p1`, `p2` — выборы сторон (атака + блок) в этом раунде.
    * `p1_length_cm`, `p2_length_cm` — длины игроков на момент НАЧАЛА
      ВСЕГО БОЯ (path-independent). Должны быть `>= 0`, иначе
      `InvalidLengthError`.
    * `hit_pct` — целочисленный процент урона от длины защитника при
      успешном попадании (`0..100`). Источник — балансовый конфиг
      `BalanceConfig.pvp.duel_1v1.hit_pct`.

    Алгоритм:

    1. Проверить, заблокированы ли атаки на этом раунде:
       `p1_attack_blocked = (p1.attack == p2.block)` и симметрично.
    2. Если атака не заблокирована — нанесён урон
       `floor(defender_length * hit_pct / 100)` см. Иначе — 0.

    Возвращает `RoundOutcome` со всеми флагами и нанесёнными суммами.
    """

    if p1_length_cm < 0:
        raise InvalidLengthError(side="p1", length_cm=p1_length_cm)
    if p2_length_cm < 0:
        raise InvalidLengthError(side="p2", length_cm=p2_length_cm)

    p1_attack_blocked = _hit_blocked(attack=p1.attack, block=p2.block)
    p2_attack_blocked = _hit_blocked(attack=p2.attack, block=p1.block)

    p1_damage_to_p2 = (
        0 if p1_attack_blocked else _damage_cm(defender_length_cm=p2_length_cm, hit_pct=hit_pct)
    )
    p2_damage_to_p1 = (
        0 if p2_attack_blocked else _damage_cm(defender_length_cm=p1_length_cm, hit_pct=hit_pct)
    )

    return RoundOutcome(
        p1_choice=p1,
        p2_choice=p2,
        p1_attack_blocked=p1_attack_blocked,
        p2_attack_blocked=p2_attack_blocked,
        p1_damage_to_p2=p1_damage_to_p2,
        p2_damage_to_p1=p2_damage_to_p1,
    )


def resolve_duel(
    *,
    rounds: Sequence[tuple[RoundChoice, RoundChoice]],
    p1_length_cm: int,
    p2_length_cm: int,
    hit_pct: int,
    expected_rounds: int = DEFAULT_DUEL_ROUNDS,
) -> DuelOutcome:
    """Разрешить полный 3-раундовый PvP-бой (ГДД §7.1).

    Аргументы:

    * `rounds` — последовательность пар `(p1_choice, p2_choice)` ровно
      длины `expected_rounds` (по умолчанию 3). Иначе
      `InvalidRoundCountError`.
    * `p1_length_cm`, `p2_length_cm` — длины на момент НАЧАЛА БОЯ.
      Используются на всех раундах (path-independent).
    * `hit_pct` — балансовый процент урона.
    * `expected_rounds` — параметр движка, по умолчанию `3`.

    Алгоритм:

    1. Проверить `len(rounds) == expected_rounds`.
    2. Для каждого раунда вызвать `resolve_round(...)`.
    3. Сумма `p1_total_dealt = Σ p1_damage_to_p2`, аналогично p2.
    4. Zero-sum дельты: `p1_delta_cm = p1_total_dealt - p2_total_dealt`,
       `p2_delta_cm = -p1_delta_cm`.
    5. `winner` определяется знаком дельты.

    Возвращает `DuelOutcome` с полным журналом раундов и итогом.
    """

    if len(rounds) != expected_rounds:
        raise InvalidRoundCountError(expected=expected_rounds, got=len(rounds))

    resolved = tuple(
        resolve_round(
            p1=p1,
            p2=p2,
            p1_length_cm=p1_length_cm,
            p2_length_cm=p2_length_cm,
            hit_pct=hit_pct,
        )
        for p1, p2 in rounds
    )

    p1_total_dealt = sum(r.p1_damage_to_p2 for r in resolved)
    p2_total_dealt = sum(r.p2_damage_to_p1 for r in resolved)

    p1_delta = p1_total_dealt - p2_total_dealt
    p2_delta = -p1_delta

    if p1_delta > 0:
        winner = DuelWinner.P1
    elif p1_delta < 0:
        winner = DuelWinner.P2
    else:
        winner = DuelWinner.DRAW

    return DuelOutcome(
        rounds=resolved,
        p1_total_dealt=p1_total_dealt,
        p2_total_dealt=p2_total_dealt,
        p1_delta_cm=p1_delta,
        p2_delta_cm=p2_delta,
        winner=winner,
    )
