"""Чистый движок боя рейд-босса (ГДД §10.4–§10.5, Спринт 3.3-C).

`resolve_boss_round(*, boss_fight, alive_raiders, balance, random)` —
домен-сервис **одного раунда** боя с боссом. Зависит только от
чистых VO/сущностей домена и порта :class:`IRandom`. Никаких импортов
из `application/` / `infrastructure/` / `bot/`. Никаких side-эффектов:
возвращает :class:`BossRoundResult`, который use-case `RunBossRound`
(шаг C.2) применяет в одной транзакции.

Боевая механика (ГДД §10.4):

* Босс делает **3 атаки за раунд** (`_BOSS_ATTACKS_PER_ROUND=3`).
  Каждая атака — это «удар по случайному выжившему рейдеру в
  случайную позицию A/B/C». Если все рейдеры выбыли в середине
  раунда, оставшиеся атаки пропадают (defensive — практически
  невозможно при 3 атаках, но безопаснее чем падать).
* Каждый рейдер блокирует **2 из 3 позиций** (как караванщик в ГДД
  §9.5). В 3.3-C блоки катаются детерминистично от `random` (UI выбора
  блоков придёт в 3.3-D).
* Удар в блок: рейдер цел, **босс теряет** `base_damage_cm` см
  (рейдер «отбил атаку и забрал у босса немного длины»).
* Удар не в блок: рейдер **выбывает** из боя и теряет
  `base_damage_cm` см. После выбывания этот рейдер не цель
  для оставшихся атак этого раунда.

Завершение боя (ГДД §10.5) — на уровне `RunBossRound`-use-case-а
после применения этого раунда:

* `current_boss_length_cm < victory_threshold_cm` — рейдеры
  победили (`FinishBossFight` раздаёт награды + scroll-drops).
* Все рейдеры выбыли (`list_by_boss_fight` пуст после удаления
  выбывших) — босс победил (`FinishBossFight` без раидерских наград).
* Иначе — `RunBossRound` шедулит следующий тик через
  `IDelayedJobScheduler.schedule_boss_round_tick`.

Детерминированность: при одинаковом `IRandom`-seed-е тот же исход.
Это нужно для аудита: бой воспроизводим post-mortem (см.
`boss_fight.random_seed` + `current_round` — обёртка use-case-а
комбинирует их перед вызовом resolve-а, чтобы каждый раунд был
независимо воспроизводим).
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass

from pipirik_wars.domain.balance.config import BossesConfig
from pipirik_wars.domain.bosses.entities import BossFight, BossParticipant
from pipirik_wars.domain.shared.ports import IRandom

_BOSS_ATTACKS_PER_ROUND: int = 3
"""Сколько атак делает босс за раунд (ГДД §10.4: «босс — 3 атаки»)."""

_RAIDER_BLOCKS_PER_ROUND: int = 2
"""Сколько позиций блокирует каждый рейдер за раунд (из 3).

ГДД §10.4 говорит «рейдер — 3 блока», что трактуется как «3 защитных
слота» (по одному на каждую боссову атаку). Раз позиций атаки всего
три (A/B/C), а атак за раунд тоже три — рейдер выбирает 2 из 3
позиций для блоков (полное покрытие сделало бы боя невозможным,
0 покрытие — мгновенный wipe). Это даёт block-rate ≈ 2/3, hit-rate
≈ 1/3, что балансово сходно с караванной формулой (ГДД §9.5).
"""


class _BlockPosition(enum.IntEnum):
    """Три абстрактных позиции удара/блока (ГДД §10.4).

    Имена `A/B/C` условны — это просто три равновероятных слота,
    в которые босс может бить и которые рейдер может блокировать.
    UI и баланс не зависят от конкретных названий.
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
class BossRaiderRoundOutcome:
    """Per-raider исход одного раунда боя с боссом (Спринт 3.3-C, ГДД §10.4).

    `participant` — сам рейдер (snapshot на момент входа в раунд).
    Use-case `RunBossRound` использует `participant.player_id` для
    `IBossParticipantRepository.remove(...)` в случае выбывания, и
    для аудит-эвента `BOSS_FIGHT_ROUND_RESOLVED`.

    `is_eliminated`:
        * `True` — рейдера ударили в незаблокированную позицию, он
          выбывает из боя. Use-case удалит его запись из
          `boss_participants` и снимет activity-lock.
        * `False` — рейдер либо заблокировал (бил, но не пробил), либо
          в этом раунде по нему вообще не били.

    `damage_taken_cm` — урон, полученный в раунде. `0` если
    `is_eliminated=False`, иначе равен `balance.base_damage_cm` (ГДД
    §10.4: «5 см» по умолчанию). Use-case применит его как часть
    финального length-delta при `FinishBossFight` — внутри-раундовых
    `add_length` нет, чтобы упростить транзакционность.
    """

    participant: BossParticipant
    is_eliminated: bool
    damage_taken_cm: int

    def __post_init__(self) -> None:
        if self.damage_taken_cm < 0:
            raise ValueError(
                f"BossRaiderRoundOutcome: damage_taken_cm ({self.damage_taken_cm}) must be >= 0"
            )
        if self.is_eliminated and self.damage_taken_cm == 0:
            raise ValueError(
                "BossRaiderRoundOutcome: is_eliminated=True требует damage_taken_cm > 0"
            )
        if not self.is_eliminated and self.damage_taken_cm != 0:
            raise ValueError(
                "BossRaiderRoundOutcome: is_eliminated=False требует damage_taken_cm == 0"
            )


@dataclass(frozen=True, slots=True)
class BossRoundResult:
    """Полный исход одного раунда боя с боссом (Спринт 3.3-C, ГДД §10.4–§10.5).

    Никаких side-эффектов (frozen-VO). Use-case `RunBossRound` применит:

    1. `boss_fight.with_boss_length(max(0, current - boss_damage_taken_cm))`
       — обновит HP босса.
    2. Удалит из `boss_participants` всех рейдеров с
       `BossRaiderRoundOutcome.is_eliminated=True`.
    3. Снимет activity-locks с выбывших рейдеров.
    4. `boss_fight.with_round_advanced()` — инкремент счётчика раунда.
    5. Записает `AuditAction.BOSS_FIGHT_ROUND_RESOLVED` с этим
       `BossRoundResult` в `before/after`.

    Поля:
    - `raider_outcomes` — по одному per `alive_raider`, в том же
      порядке. Не пустой по pre-условию.
    - `boss_damage_taken_cm` — суммарный урон боссу в раунде. Это
      `_BOSS_ATTACKS_PER_ROUND × base_damage_cm` в самом плохом для
      босса случае (все 3 атаки заблокированы). `0` — в самом лучшем
      (все 3 пробили блок, 3 рейдера выбыли).
    - `eliminated_player_ids` — отдельный кортеж для удобства
      use-case-а. Эквивалентно `tuple(o.participant.player_id for o in
      raider_outcomes if o.is_eliminated)`. Хранится отдельно, чтобы
      не пересчитывать в use-case-е и audit-е.
    """

    raider_outcomes: tuple[BossRaiderRoundOutcome, ...]
    boss_damage_taken_cm: int
    eliminated_player_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.boss_damage_taken_cm < 0:
            raise ValueError(
                f"BossRoundResult: boss_damage_taken_cm ({self.boss_damage_taken_cm}) must be >= 0"
            )
        # Инвариант согласованности: eliminated_player_ids должен
        # точно совпадать с подмножеством raider_outcomes-ов с
        # is_eliminated=True (в том же порядке).
        expected_eliminated = tuple(
            o.participant.player_id for o in self.raider_outcomes if o.is_eliminated
        )
        if self.eliminated_player_ids != expected_eliminated:
            raise ValueError(
                f"BossRoundResult: eliminated_player_ids "
                f"({self.eliminated_player_ids}) inconsistent with "
                f"raider_outcomes (expected {expected_eliminated})"
            )


def resolve_boss_round(
    *,
    boss_fight: BossFight,
    alive_raiders: Sequence[BossParticipant],
    balance: BossesConfig,
    random: IRandom,
) -> BossRoundResult:
    """Резолв одного раунда боя с боссом (детерминистично от `random`).

    Pre:
        * `boss_fight` находится в `IN_BATTLE` (инвариант use-case-а,
          здесь не проверяется).
        * `alive_raiders` непуст. Если все рейдеры уже выбыли — это
          terminal-состояние, и `RunBossRound`-use-case должен
          напрямую вызвать `FinishBossFight`, а не звать этот сервис.

    Возвращаемый `BossRoundResult` не имеет side-эффектов —
    use-case `RunBossRound` применит boss-HP / удаление выбывших /
    инкремент раунда / audit в одной транзакции.

    Raises:
        ValueError: если `alive_raiders` пуст.
    """

    del boss_fight  # сейчас не используется (random_seed уже инкапсулирован
    #  в IRandom через SeededRandom-обёртку use-case-а); оставлен в
    #  сигнатуре для будущей расширяемости (например, чтобы resolve мог
    #  посмотреть `current_round` для round-зависимых модификаторов).

    if not alive_raiders:
        raise ValueError("resolve_boss_round: alive_raiders is empty")

    # 1. «Выбор» блоков каждым рейдером (детерминистично от `random`).
    blocks_by_player: dict[int, frozenset[_BlockPosition]] = {
        r.player_id: _roll_blocks(num_blocks=_RAIDER_BLOCKS_PER_ROUND, random=random)
        for r in alive_raiders
    }

    # 2. Резолв атак босса. Рейдер выбывает = удаляется из target-pool-а
    #    и помечается в `eliminated_ids`. Каждый удар наносит ровно
    #    `base_damage_cm` либо боссу (block), либо рейдеру (hit).
    eliminated_ids: set[int] = set()
    boss_damage_taken_cm = 0

    for _ in range(_BOSS_ATTACKS_PER_ROUND):
        live_targets = [r for r in alive_raiders if r.player_id not in eliminated_ids]
        if not live_targets:
            # Все рейдеры выбили в этом раунде — оставшиеся атаки босса
            # «бьют по воздуху» (defensive: при 3 атаках и 3+ рейдерах
            # это редкий corner-case).
            break
        target = random.choice(live_targets)
        attack_position = random.choice(_ALL_BLOCKS)
        target_blocks = blocks_by_player[target.player_id]
        if attack_position in target_blocks:
            # Заблокирован: босс теряет «немного длины».
            boss_damage_taken_cm += balance.base_damage_cm
        else:
            # Не в блок: рейдер выбывает + теряет «немного длины».
            eliminated_ids.add(target.player_id)

    # 3. Сбор per-raider outcome-ов в том же порядке, что и `alive_raiders`.
    raider_outcomes_list: list[BossRaiderRoundOutcome] = []
    eliminated_in_order: list[int] = []
    for r in alive_raiders:
        is_eliminated = r.player_id in eliminated_ids
        raider_outcomes_list.append(
            BossRaiderRoundOutcome(
                participant=r,
                is_eliminated=is_eliminated,
                damage_taken_cm=balance.base_damage_cm if is_eliminated else 0,
            )
        )
        if is_eliminated:
            eliminated_in_order.append(r.player_id)

    return BossRoundResult(
        raider_outcomes=tuple(raider_outcomes_list),
        boss_damage_taken_cm=boss_damage_taken_cm,
        eliminated_player_ids=tuple(eliminated_in_order),
    )


def _roll_blocks(*, num_blocks: int, random: IRandom) -> frozenset[_BlockPosition]:
    """Случайный набор `num_blocks` блок-позиций (без повторов, из 3).

    `num_blocks` ∈ {1, 2, 3}: в 3.3-C каждый рейдер блокирует 2/3
    (см. модуль-докстринг). Реализация: `random.shuffle` на всех
    3 позициях, берём префикс.
    """

    if num_blocks not in (1, 2, 3):
        raise ValueError(f"_roll_blocks: num_blocks must be 1, 2 or 3, got {num_blocks}")
    shuffled = random.shuffle(_ALL_BLOCKS)
    return frozenset(shuffled[:num_blocks])


__all__ = [
    "BossRaiderRoundOutcome",
    "BossRoundResult",
    "resolve_boss_round",
]
