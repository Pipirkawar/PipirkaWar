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

Спринт 2.1.C добавляет порт `IDuelRepository` для persistence-слоя
(реализуется поверх таблиц `pvp_duels` + `pvp_duel_rounds`,
см. `infrastructure/db/repositories/pvp_duel.py`).

Будущие расширения (Спринты 2.1.D–H, 2.2):

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
    DuelNotFoundError,
    InvalidDuelStateError,
    InvalidLengthError,
    InvalidRoundCountError,
    MoveAlreadySubmittedError,
    NoMissingMovesError,
    NotADuelParticipantError,
    PvpError,
    PvpRequirementsNotMetError,
    SelfChallengeError,
)
from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository, LobbyEntry
from pipirik_wars.domain.pvp.repositories import IDuelRepository
from pipirik_wars.domain.pvp.services import (
    DEFAULT_DUEL_ROUNDS,
    resolve_duel,
    resolve_round,
)

__all__ = [
    "DEFAULT_DUEL_ROUNDS",
    "Duel",
    "DuelMode",
    "DuelNotFoundError",
    "DuelOutcome",
    "DuelState",
    "DuelWinner",
    "IDuelRepository",
    "IGlobalLobbyRepository",
    "InvalidDuelStateError",
    "InvalidLengthError",
    "InvalidRoundCountError",
    "LobbyEntry",
    "MoveAlreadySubmittedError",
    "NoMissingMovesError",
    "NotADuelParticipantError",
    "PendingRound",
    "Position",
    "PvpError",
    "PvpRequirementsNotMetError",
    "RoundChoice",
    "RoundOutcome",
    "SelfChallengeError",
    "resolve_duel",
    "resolve_round",
]
