"""Чистый движок массового PvP клан×клан (ГДД §7.2, Спринт 2.2.B).

Зависит **только** от чистых VO (`mass.py`, `entities.py`) и порта
:class:`IRandom`. Никаких импортов из `application/` / `infrastructure/`
/ `bot/`. Никакого `random.*` напрямую — только через
`IRandom.shuffle` / `_hit_blocked` / `_damage_cm` (последние две —
переиспользуем 1×1-движок: атака и блок ходят по одной 3×3-матрице
позиций в любом режиме PvP, см. §7.1 и §7.2).

Бой — **один тик** (ГДД §7.2 / 2.2.4):

* Каждый участник заявляет 1 атаку + 1 блок (`MassRoundChoice`).
* RNG строит две независимые перестановки атакующих → защитников
  (clan1→clan2 и clan2→clan1; направления симметричны и независимы).
* Все удары разрешаются одновременно по той же матрице атака×блок,
  что и в 1×1: совпадение ⇒ блок, иначе пробитие на
  `floor(L_def * hit_pct / 100)` см.
* Длины защитников зафиксированы на старте боя (path-independent),
  никаких HP-пулов «во время удара».

Pure-функции, без побочных эффектов. Все ошибки контракта поднимаются
как ``ValueError`` синхронно — никаких ``InvalidLengthError`` или
``InvalidRoundCountError`` (1×1-специфичные исключения), потому что
у массового боя нет понятия «количество раундов» (всегда 1 тик), а
длины приходят как dict `player_id → length_cm` без ограничения «p1/p2».
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pipirik_wars.domain.pvp.mass import (
    MassDamageEntry,
    MassDuelOutcome,
    MassDuelWinner,
    MassRoundChoice,
    MassRoundOutcome,
)
from pipirik_wars.domain.pvp.services import _damage_cm, _hit_blocked
from pipirik_wars.domain.shared.ports import IRandom

__all__ = [
    "pair_attackers",
    "resolve_mass_duel",
    "resolve_mass_round",
]


def pair_attackers(
    *,
    attackers: Sequence[int],
    defenders: Sequence[int],
    random: IRandom,
) -> tuple[tuple[int, int], ...]:
    """Назначить пары «атакующий → защитник» в одном направлении.

    Контракт:

    * `attackers` / `defenders` — непустые последовательности
      `player_id` (`> 0`). Иначе `ValueError`.
    * Длина выхода = ``max(|attackers|, |defenders|)``. Если стороны
      разной длины, **меньшая сторона переиспользует свои элементы по
      mod-cycle** на УЖЕ перетасованных списках:
      ``output[i] = (atks_shuffled[i % |A|], defs_shuffled[i % |B|])``.
      Это гарантирует, что (а) каждый игрок большей стороны получает
      ровно одну позицию в выходе, (б) каждый игрок меньшей стороны
      также участвует, повторяясь циклически.
    * Самопары (``attacker_id == defender_id``) не запрещены **этой**
      функцией — она ничего не знает про структуру кланов; защитой от
      «один игрок в обоих кланах» занимается use-case (ГДД §7.2 / 2.2.3).
      Если такая ситуация всё же дошла до `pair_attackers` — пара
      `(X, X)` будет проигнорирована вызывающим (`resolve_mass_round`).
    * Детерминированность по seed-у :class:`IRandom`: при одних и тех
      же входах RNG возвращает одну и ту же перестановку. Тестируется
      через :class:`tests.fakes.random.FakeRandom` с фиксированным seed.

    Возвращает ``tuple[tuple[int, int], ...]`` — пары
    ``(attacker_id, defender_id)``. Не ``tuple[MassPairing, ...]``,
    потому что :class:`MassPairing` валидирует ``attacker_id != defender_id``,
    а здесь это контролирует уже use-case (см. выше).
    """

    if not attackers:
        raise ValueError("pair_attackers: attackers is empty")
    if not defenders:
        raise ValueError("pair_attackers: defenders is empty")
    if any(a <= 0 for a in attackers):
        raise ValueError(f"pair_attackers: attacker_id must be > 0, got {list(attackers)}")
    if any(d <= 0 for d in defenders):
        raise ValueError(f"pair_attackers: defender_id must be > 0, got {list(defenders)}")

    atks_shuffled = random.shuffle(attackers)
    defs_shuffled = random.shuffle(defenders)

    n = max(len(attackers), len(defenders))
    return tuple(
        (atks_shuffled[i % len(atks_shuffled)], defs_shuffled[i % len(defs_shuffled)])
        for i in range(n)
    )


def _resolve_one_direction(
    *,
    pairs: Sequence[tuple[int, int]],
    attacker_choices: Mapping[int, MassRoundChoice],
    defender_choices: Mapping[int, MassRoundChoice],
    defender_initial_lengths: Mapping[int, int],
    hit_pct: int,
) -> tuple[tuple[MassDamageEntry, ...], int]:
    """Разрешить все атаки в одном направлении (А→Б).

    Внутренний хелпер: применяет :func:`_hit_blocked` / :func:`_damage_cm`
    из 1×1-движка к каждой паре, складывает суммарный нанесённый ущерб.
    Самопары (``attacker_id == defender_id``) пропускаются —
    :class:`MassDamageEntry.__post_init__` запрещает их (см. ГДД §7.2 / 2.2.3).

    Возвращает кортеж (`damage_entries`, `total_dealt`).
    """

    entries: list[MassDamageEntry] = []
    total_dealt = 0
    for attacker_id, defender_id in pairs:
        if attacker_id == defender_id:
            continue  # ГДД §7.2 / 2.2.3 — игрок в обоих кланах пропускается
        a_choice = attacker_choices[attacker_id]
        d_choice = defender_choices[defender_id]
        defender_length = defender_initial_lengths[defender_id]
        if defender_length < 0:
            raise ValueError(
                f"defender_initial_lengths[{defender_id}]={defender_length} must be >= 0"
            )
        blocked = _hit_blocked(attack=a_choice.attack, block=d_choice.block)
        damage = 0 if blocked else _damage_cm(defender_length_cm=defender_length, hit_pct=hit_pct)
        entries.append(
            MassDamageEntry(
                attacker_id=attacker_id,
                defender_id=defender_id,
                attacker_attack=a_choice.attack,
                defender_block=d_choice.block,
                blocked=blocked,
                damage_cm=damage,
            )
        )
        total_dealt += damage
    return tuple(entries), total_dealt


def _validate_choices(
    *,
    side: str,
    choices: Sequence[MassRoundChoice],
) -> dict[int, MassRoundChoice]:
    """Привести `Sequence[MassRoundChoice]` → `dict[player_id, choice]` с валидацией.

    Контракт:

    * `choices` непуст;
    * нет дублей по `player_id` (один игрок не может заявить два выбора
      на тот же тик).
    """

    if not choices:
        raise ValueError(f"{side}: choices is empty")
    by_id = {c.player_id: c for c in choices}
    if len(by_id) != len(choices):
        raise ValueError(f"{side}: duplicate player_id in choices")
    return by_id


def _validate_lengths(
    *,
    side: str,
    expected_ids: Sequence[int],
    lengths: Mapping[int, int],
) -> None:
    """Гарантирует, что `lengths` покрывает ровно ``expected_ids`` и все ``>= 0``."""

    if set(lengths) != set(expected_ids):
        raise ValueError(
            f"{side}: lengths keys {sorted(lengths)} != expected {sorted(expected_ids)}"
        )
    for player_id, length_cm in lengths.items():
        if length_cm < 0:
            raise ValueError(f"{side}: lengths[{player_id}]={length_cm} must be >= 0")


def resolve_mass_round(
    *,
    clan1_choices: Sequence[MassRoundChoice],
    clan2_choices: Sequence[MassRoundChoice],
    clan1_initial_lengths: Mapping[int, int],
    clan2_initial_lengths: Mapping[int, int],
    hit_pct: int,
    random: IRandom,
) -> MassRoundOutcome:
    """Разрешить один тик массового PvP-боя (ГДД §7.2 / 2.2.4).

    Аргументы:

    * `clan1_choices` / `clan2_choices` — выборы каждого участника
      (атака+блок). Длина >= 1, без дублей по `player_id`.
    * `clan1_initial_lengths` / `clan2_initial_lengths` — длины
      участников на момент старта боя (path-independent). Должны
      покрывать ровно те же `player_id`-ы, что и `*_choices`.
    * `hit_pct` — балансовый процент урона (`balance.pvp.duel_1v1.hit_pct`,
      ГДД §7.1: 10%). По принципу 5 из HANDOFF используется общий с 1×1.
    * `random` — :class:`IRandom`, источник перестановок для pair_attackers.

    Алгоритм:

    1. Собрать `dict[player_id, choice]` для обеих сторон (валидируем
       совпадение множеств с `lengths`).
    2. Двумя независимыми вызовами :func:`pair_attackers` сформировать
       пары для атак clan1→clan2 и clan2→clan1.
    3. Через :func:`_resolve_one_direction` разрешить каждую сторону:
       вычислить по 3×3-матрице, заблокирована ли атака; если нет —
       добавить ``floor(L_def * hit_pct / 100)`` см на счётчик нанесённого.
    4. Собрать итоговый :class:`MassRoundOutcome` с сцеплённым списком
       `damage_entries` (сначала clan1→clan2, потом clan2→clan1).

    Возвращает :class:`MassRoundOutcome`.
    """

    if hit_pct < 0 or hit_pct > 100:
        raise ValueError(f"hit_pct must be in [0, 100], got {hit_pct}")

    by_id_1 = _validate_choices(side="clan1", choices=clan1_choices)
    by_id_2 = _validate_choices(side="clan2", choices=clan2_choices)
    clan1_ids = list(by_id_1)
    clan2_ids = list(by_id_2)
    _validate_lengths(side="clan1", expected_ids=clan1_ids, lengths=clan1_initial_lengths)
    _validate_lengths(side="clan2", expected_ids=clan2_ids, lengths=clan2_initial_lengths)

    pairs_1_to_2 = pair_attackers(attackers=clan1_ids, defenders=clan2_ids, random=random)
    pairs_2_to_1 = pair_attackers(attackers=clan2_ids, defenders=clan1_ids, random=random)

    entries_1, dealt_1 = _resolve_one_direction(
        pairs=pairs_1_to_2,
        attacker_choices=by_id_1,
        defender_choices=by_id_2,
        defender_initial_lengths=clan2_initial_lengths,
        hit_pct=hit_pct,
    )
    entries_2, dealt_2 = _resolve_one_direction(
        pairs=pairs_2_to_1,
        attacker_choices=by_id_2,
        defender_choices=by_id_1,
        defender_initial_lengths=clan1_initial_lengths,
        hit_pct=hit_pct,
    )

    return MassRoundOutcome(
        damage_entries=entries_1 + entries_2,
        clan1_total_dealt=dealt_1,
        clan2_total_dealt=dealt_2,
    )


def resolve_mass_duel(
    *,
    clan1_choices: Sequence[MassRoundChoice],
    clan2_choices: Sequence[MassRoundChoice],
    clan1_initial_lengths: Mapping[int, int],
    clan2_initial_lengths: Mapping[int, int],
    hit_pct: int,
    random: IRandom,
) -> MassDuelOutcome:
    """Разрешить полный массовый PvP-бой (ГДД §7.2 / 2.2.4).

    Текущий формат боя — **один тик** (см. `resolve_mass_round`),
    поэтому функция тонко оборачивает один вызов с расчётом zero-sum
    дельт и определением победителя:

    * `clan1_delta_cm = clan1_total_dealt - clan2_total_dealt`,
      `clan2_delta_cm = -clan1_delta_cm` (зеркальный zero-sum).
    * `winner = CLAN1` ⇔ `clan1_delta > 0`,
      `winner = CLAN2` ⇔ `clan1_delta < 0`,
      `winner = DRAW`  ⇔ `clan1_delta == 0` (включая случаи, когда
      обе стороны нанесли по нулям).

    Дальнейшее начисление ±длины участникам — забота use-case-а 2.2.D
    (через `progression.add_length(...)` с anti-cheat-cap-ом, см. 1.6).
    """

    outcome = resolve_mass_round(
        clan1_choices=clan1_choices,
        clan2_choices=clan2_choices,
        clan1_initial_lengths=clan1_initial_lengths,
        clan2_initial_lengths=clan2_initial_lengths,
        hit_pct=hit_pct,
        random=random,
    )

    delta = outcome.clan1_total_dealt - outcome.clan2_total_dealt
    if delta > 0:
        winner = MassDuelWinner.CLAN1
    elif delta < 0:
        winner = MassDuelWinner.CLAN2
    else:
        winner = MassDuelWinner.DRAW

    return MassDuelOutcome(
        outcome=outcome,
        clan1_total_dealt=outcome.clan1_total_dealt,
        clan2_total_dealt=outcome.clan2_total_dealt,
        clan1_delta_cm=delta,
        clan2_delta_cm=-delta,
        winner=winner,
    )
