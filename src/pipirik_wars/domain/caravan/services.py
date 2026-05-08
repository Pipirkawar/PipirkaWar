"""Чистый движок боя каравана (ГДД §9.5–§9.6, Спринт 3.2-C).

`resolve_caravan_battle(*, caravan, participants, balance, random)` —
единственная точка резолва боя. Зависит только от чистых VO/сущностей
домена и порта :class:`IRandom`. Никаких импортов из `application/` /
`infrastructure/` / `bot/`. Никаких side-эффектов: возвращает
:class:`CaravanBattleResult` со списком per-player дельт; `FinishCaravanBattle`
use-case (Спринт 3.2-C, шаг C.5) применяет их в одной транзакции.

Боевая механика (ГДД §9.5):

* Каждый караванщик «выбирает» 2 блок-позиции из 3 (`A/B/C`),
  каждый защитник — 1 блок-позицию. В 3.2-C выбор делается
  детерминистично от `random` (UI выбора блоков придёт в 3.2-D).
* Каждый рейдер делает 1 удар по случайному выжившему караванщику
  или защитнику в случайную позицию.
* Удар не в блок: цель погибает + теряет
  `unblocked_strike_damage_cm` см (ГДД §9.5 «немного −длины»).
* Удар в блок: рейдер теряет `blocked_strike_damage_cm` см. Цель
  жива.

Завершение (ГДД §9.6):

* Рейдеры победили (все караванщики и защитники мертвы):
    * Делят `total_cargo_cm` поровну, округление вверх (`ceil`).
    * Один случайный рейдер — Атаман: получает дополнительно
      `base_share × ataman_bonus_share` от системы и `Title.ATAMAN`.
* Караван дошёл (≥ 1 караванщик/защитник выжил):
    * Лидер: `leader_multiplier × contribution_cm` (выживший).
    * Караванщики (не лидер, выжившие): `caravaneer_multiplier × contribution_cm`.
    * Защитники (выжившие): `defender_multiplier × base_reward_cm`.
    * Все игроки обоих кланов: `clan_bonus_cm` к суммарной длине клана
      (это уже клан-уровень, не per-player; учитывается use-case-ом
      отдельно от `participant_outcomes`).
    * Погибшие караванщики/защитники получают только урон, без награды.
    * Рейдеры — только потери от блоков.

Детерминированность: при одинаковом seed-е :class:`IRandom` (через
:class:`tests.fakes.random.FakeRandom`) тот же исход. Это нужно для
аудита: бой воспроизводим post-mortem (см. `caravan.random_seed`).
"""

from __future__ import annotations

import enum
import math
from collections.abc import Sequence
from dataclasses import dataclass

from pipirik_wars.domain.balance.config import CaravansConfig
from pipirik_wars.domain.caravan.entities import Caravan, CaravanParticipant
from pipirik_wars.domain.caravan.value_objects import CaravanRole
from pipirik_wars.domain.shared.ports import IRandom


class _BlockPosition(enum.IntEnum):
    """Три абстрактных позиции удара/блока (ГДД §9.5).

    Имена `A/B/C` условны — это просто три равновероятных слота,
    в которые рейдер может бить и которые караванщик/защитник может
    блокировать. UI и баланс не зависят от конкретных названий.
    """

    A = 0
    B = 1
    C = 2


_ALL_BLOCKS: tuple[_BlockPosition, ...] = (
    _BlockPosition.A,
    _BlockPosition.B,
    _BlockPosition.C,
)


@dataclass(frozen=True, slots=True)
class CaravanParticipantOutcome:
    """Per-player исход боя каравана (Спринт 3.2-C, ГДД §9.5–§9.6).

    `length_delta_cm` — итоговое изменение длины игрока (положительное
    = награда, отрицательное = потеря). Use-case `FinishCaravanBattle`
    применит его через `IPlayerProgressionService.add_length` (с anti-cheat
    cap-ом и audit-логом). Может быть `0` (например, рейдер без
    заблокированных ударов в успешной атаке).

    `gets_ataman_title` — `True` ровно у одного рейдера, и только если
    `raiders_won=True`. Use-case присвоит `Title.ATAMAN` через
    `Player.with_title(Title.ATAMAN)`.

    `is_alive` — для караванщика/защитника отражает реальный исход
    (мёртв → `False`); для рейдера всегда `True` (рейдер не погибает,
    максимум теряет длину от блоков).
    """

    participant: CaravanParticipant
    is_alive: bool
    length_delta_cm: int
    gets_ataman_title: bool


@dataclass(frozen=True, slots=True)
class CaravanBattleResult:
    """Полный исход боя каравана (Спринт 3.2-C, ГДД §9.5–§9.6).

    `raiders_won`:
        * `True` — все караванщики и защитники мертвы → рейдеры
          разграбили караван.
        * `False` — ≥ 1 караванщик или защитник выжил → караван дошёл.

    `participant_outcomes` — по одному на каждого участника, в том же
    порядке, в котором они пришли в `resolve_caravan_battle(participants=...)`.

    `clan_bonus_cm_sender` / `clan_bonus_cm_receiver` — `+1 см` (балансово)
    к суммарной длине каждого клана при доставке каравана. При победе
    рейдеров оба = `0`. Применяется use-case-ом отдельно от
    per-player длин (это клан-уровень, ГДД §9.6).
    """

    raiders_won: bool
    participant_outcomes: tuple[CaravanParticipantOutcome, ...]
    clan_bonus_cm_sender: int
    clan_bonus_cm_receiver: int


def resolve_caravan_battle(
    *,
    caravan: Caravan,
    participants: Sequence[CaravanParticipant],
    balance: CaravansConfig,
    random: IRandom,
) -> CaravanBattleResult:
    """Резолв боя каравана (детерминистично от `random`).

    Pre:
        * `caravan` находится в `IN_BATTLE` (инвариант use-case-а,
          здесь не проверяется).
        * `participants` непуст и содержит ≥ 1 `CARAVANEER` (лидер
          обязателен по доменному инварианту `Caravan`).

    Возвращаемый `CaravanBattleResult` не имеет side-эффектов —
    use-case `FinishCaravanBattle` применит длины + клан-бонусы +
    `Title.ATAMAN` в одной транзакции.

    Raises:
        ValueError: если `participants` пуст или не содержит караванщиков.
    """

    del caravan  # сейчас не используется (random_seed уже инкапсулирован
    #  в IRandom через FakeRandom/SeededRandom-обёртку use-case-а);
    #  оставлен в сигнатуре для будущей расширяемости (например, чтобы
    #  resolve мог посмотреть `caravan.battle_ends_at` для расчёта
    #  таймаут-эффектов).

    if not participants:
        raise ValueError("resolve_caravan_battle: participants is empty")

    caravaneers = [p for p in participants if p.role is CaravanRole.CARAVANEER]
    defenders = [p for p in participants if p.role is CaravanRole.DEFENDER]
    raiders = [p for p in participants if p.role is CaravanRole.RAIDER]

    if not caravaneers:
        raise ValueError(
            "resolve_caravan_battle: caravan must have at least 1 CARAVANEER (the leader)"
        )

    # 1. «Выбор» блоков (детерминистично от `random`).
    blocks_by_player: dict[int, frozenset[_BlockPosition]] = {}
    for c in caravaneers:
        blocks_by_player[c.player_id] = _roll_blocks(num_blocks=2, random=random)
    for d in defenders:
        blocks_by_player[d.player_id] = _roll_blocks(num_blocks=1, random=random)

    # 2. Резолв ударов рейдеров.
    alive_targets: list[CaravanParticipant] = list(caravaneers) + list(defenders)
    dead_target_ids: set[int] = set()
    raider_self_damage: dict[int, int] = {r.player_id: 0 for r in raiders}

    for raider in raiders:
        if not alive_targets:
            # Все цели уже мертвы; оставшиеся рейдеры бить некого.
            # На практике редкий case (по ГДД §9.5 предельное 4× раидеров
            # на 1× караванщика, цели обычно не кончаются), но defensive.
            break
        target = random.choice(alive_targets)
        strike_position = random.choice(_ALL_BLOCKS)
        target_blocks = blocks_by_player[target.player_id]
        if strike_position in target_blocks:
            # Заблокирован: рейдер теряет «немного длины».
            raider_self_damage[raider.player_id] += balance.blocked_strike_damage_cm
        else:
            # Не в блок: цель погибает + теряет «немного длины».
            dead_target_ids.add(target.player_id)
            alive_targets = [t for t in alive_targets if t.player_id != target.player_id]

    # 3. Победитель.
    raiders_won = all(c.player_id in dead_target_ids for c in caravaneers) and all(
        d.player_id in dead_target_ids for d in defenders
    )

    # 4. Подсчёт outcome-ов.
    if raiders_won:
        return _build_raiders_victory(
            participants=participants,
            caravaneers=caravaneers,
            defenders=defenders,
            raiders=raiders,
            raider_self_damage=raider_self_damage,
            balance=balance,
            random=random,
        )

    return _build_caravan_delivery(
        participants=participants,
        dead_target_ids=dead_target_ids,
        raider_self_damage=raider_self_damage,
        balance=balance,
    )


def _roll_blocks(*, num_blocks: int, random: IRandom) -> frozenset[_BlockPosition]:
    """Случайный набор `num_blocks` блок-позиций (без повторов, из 3).

    `num_blocks` ∈ {1, 2}: караванщик блокирует 2/3, защитник 1/3.
    Реализация: `random.shuffle` на всех 3 позициях, берём префикс.
    """

    if num_blocks not in (1, 2):
        raise ValueError(f"_roll_blocks: num_blocks must be 1 or 2, got {num_blocks}")
    shuffled = random.shuffle(_ALL_BLOCKS)
    return frozenset(shuffled[:num_blocks])


def _build_raiders_victory(
    *,
    participants: Sequence[CaravanParticipant],
    caravaneers: list[CaravanParticipant],
    defenders: list[CaravanParticipant],
    raiders: list[CaravanParticipant],
    raider_self_damage: dict[int, int],
    balance: CaravansConfig,
    random: IRandom,
) -> CaravanBattleResult:
    """Победа рейдеров: делят cargo поровну, один — Атаман.

    Все караванщики/защитники погибли — каждый теряет
    `unblocked_strike_damage_cm`. Кланы не получают `clan_bonus_cm`.

    `total_cargo_cm` — сумма `contribution.cm` по всем караванщикам
    (включая лидера). `base_share = ceil(total / N_raiders)` — система
    округляет в пользу рейдеров (ГДД §9.6). Атаман дополнительно
    получает `base_share × ataman_bonus_share` от системы.
    """

    total_cargo_cm = sum(c.contribution.cm for c in caravaneers if c.contribution is not None)

    if raiders:
        # Делёжка поровну (round-up).
        base_share_per_raider_cm = math.ceil(total_cargo_cm / len(raiders))
        ataman_idx = random.randint(0, len(raiders) - 1)
        ataman_player_id: int | None = raiders[ataman_idx].player_id
    else:
        # Странный сценарий: 0 раидеров и при этом рейдеры «победили».
        # На практике невозможен (без раидеров мы попадаем в delivery-ветку),
        # но defensive: возвращаем пустые награды.
        base_share_per_raider_cm = 0
        ataman_player_id = None

    outcomes_map: dict[int, CaravanParticipantOutcome] = {}

    for c in caravaneers:
        outcomes_map[c.player_id] = CaravanParticipantOutcome(
            participant=c,
            is_alive=False,
            length_delta_cm=-balance.unblocked_strike_damage_cm,
            gets_ataman_title=False,
        )
    for d in defenders:
        outcomes_map[d.player_id] = CaravanParticipantOutcome(
            participant=d,
            is_alive=False,
            length_delta_cm=-balance.unblocked_strike_damage_cm,
            gets_ataman_title=False,
        )
    for r in raiders:
        is_ataman = r.player_id == ataman_player_id
        ataman_bonus_cm = (
            base_share_per_raider_cm * balance.reward_multipliers.ataman_bonus_share
            if is_ataman
            else 0
        )
        delta = base_share_per_raider_cm + ataman_bonus_cm - raider_self_damage.get(r.player_id, 0)
        outcomes_map[r.player_id] = CaravanParticipantOutcome(
            participant=r,
            is_alive=True,
            length_delta_cm=delta,
            gets_ataman_title=is_ataman,
        )

    # Сохраняем порядок входа.
    outcomes = tuple(outcomes_map[p.player_id] for p in participants)
    return CaravanBattleResult(
        raiders_won=True,
        participant_outcomes=outcomes,
        clan_bonus_cm_sender=0,
        clan_bonus_cm_receiver=0,
    )


def _build_caravan_delivery(
    *,
    participants: Sequence[CaravanParticipant],
    dead_target_ids: set[int],
    raider_self_damage: dict[int, int],
    balance: CaravansConfig,
) -> CaravanBattleResult:
    """Караван дошёл: лидер ×4, караванщики ×3, защитники ×1, +1 см клану.

    Погибшие караванщики/защитники получают только урон, без награды.
    Рейдеры — только потери от блоков (если есть).
    """

    outcomes_map: dict[int, CaravanParticipantOutcome] = {}
    multipliers = balance.reward_multipliers

    for p in participants:
        if p.role is CaravanRole.CARAVANEER:
            assert p.contribution is not None  # инвариант сущности
            if p.player_id in dead_target_ids:
                outcomes_map[p.player_id] = CaravanParticipantOutcome(
                    participant=p,
                    is_alive=False,
                    length_delta_cm=-balance.unblocked_strike_damage_cm,
                    gets_ataman_title=False,
                )
            else:
                multiplier = multipliers.leader if p.is_leader else multipliers.caravaneer
                outcomes_map[p.player_id] = CaravanParticipantOutcome(
                    participant=p,
                    is_alive=True,
                    length_delta_cm=multiplier * p.contribution.cm,
                    gets_ataman_title=False,
                )
        elif p.role is CaravanRole.DEFENDER:
            if p.player_id in dead_target_ids:
                outcomes_map[p.player_id] = CaravanParticipantOutcome(
                    participant=p,
                    is_alive=False,
                    length_delta_cm=-balance.unblocked_strike_damage_cm,
                    gets_ataman_title=False,
                )
            else:
                outcomes_map[p.player_id] = CaravanParticipantOutcome(
                    participant=p,
                    is_alive=True,
                    length_delta_cm=multipliers.defender * balance.base_reward_cm,
                    gets_ataman_title=False,
                )
        elif p.role is CaravanRole.RAIDER:
            outcomes_map[p.player_id] = CaravanParticipantOutcome(
                participant=p,
                is_alive=True,
                length_delta_cm=-raider_self_damage.get(p.player_id, 0),
                gets_ataman_title=False,
            )
        else:
            # CaravanRole.LEADER не используется в `participants` (у нас
            # лидер хранится как CARAVANEER + is_leader=True). Но
            # defensive — на будущее.
            raise ValueError(f"resolve_caravan_battle: unexpected role {p.role.value!r}")

    outcomes = tuple(outcomes_map[p.player_id] for p in participants)
    return CaravanBattleResult(
        raiders_won=False,
        participant_outcomes=outcomes,
        clan_bonus_cm_sender=balance.clan_bonus_cm,
        clan_bonus_cm_receiver=balance.clan_bonus_cm,
    )


__all__ = [
    "CaravanBattleResult",
    "CaravanParticipantOutcome",
    "resolve_caravan_battle",
]
