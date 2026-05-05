"""Доменный пакет PvP (ГДД §7.1).

Содержит чистый движок боя 1×1 (Спринт 2.1.A): value-objects
`Position` / `RoundChoice` / `RoundOutcome` / `DuelOutcome` и
функции-резолверы `resolve_round(...)` / `resolve_duel(...)`.

Спринт 2.1.B добавляет агрегат `Duel` — жизненный цикл боя
(PENDING_ACCEPT → IN_PROGRESS → COMPLETED/CANCELLED) с lifecycle-
методами `accept` / `cancel` / `submit_move` / `force_complete_round`,
а также сопутствующие enum-ы `DuelState` / `DuelMode` и value-object
`PendingRound`. Любая инфраструктура (БД, AFK-таймер, инлайн-кнопки)
лежит выше доменного слоя.

Будущие расширения (Спринты 2.1.C–F, 2.2):

* `repositories.py` — порт `IDuelRepository`.
* Дополнительные сервисы — `pick_random_choice` (AFK-фоллбэк) и
  `mass_pvp_resolver` для клановых N×M-битв.
"""

from pipirik_wars.domain.pvp.duel import (
    Duel,
    DuelMode,
    DuelState,
    PendingRound,
)
from pipirik_wars.domain.pvp.entities import (
    DuelOutcome,
    DuelWinner,
    Position,
    RoundChoice,
    RoundOutcome,
)
from pipirik_wars.domain.pvp.errors import (
    InvalidDuelStateError,
    InvalidLengthError,
    InvalidRoundCountError,
    MoveAlreadySubmittedError,
    NoMissingMovesError,
    NotADuelParticipantError,
    PvpError,
    SelfChallengeError,
)
from pipirik_wars.domain.pvp.services import (
    DEFAULT_DUEL_ROUNDS,
    resolve_duel,
    resolve_round,
)

__all__ = [
    "DEFAULT_DUEL_ROUNDS",
    "Duel",
    "DuelMode",
    "DuelOutcome",
    "DuelState",
    "DuelWinner",
    "InvalidDuelStateError",
    "InvalidLengthError",
    "InvalidRoundCountError",
    "MoveAlreadySubmittedError",
    "NoMissingMovesError",
    "NotADuelParticipantError",
    "PendingRound",
    "Position",
    "PvpError",
    "RoundChoice",
    "RoundOutcome",
    "SelfChallengeError",
    "resolve_duel",
    "resolve_round",
]
