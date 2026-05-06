"""Доменный пакет PvP (ГДД §7.1, §7.2).

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

Спринт 2.2.B добавляет чистые value-objects массового PvP клан×клан
(`MassRoundChoice` / `MassPairing` / `MassDamageEntry` /
`MassRoundOutcome` / `MassDuelOutcome` / `MassDuelWinner`,
см. `mass.py`) и pure-функции движка
(`pair_attackers` / `resolve_mass_round` / `resolve_mass_duel`,
см. `mass_services.py`). RNG для pairing инжектится через
:class:`IRandom.shuffle`.

Спринт 2.2.C добавляет агрегат `MassDuel` — жизненный цикл массового
PvP-боя клан×клан (`IN_PROGRESS` → `COMPLETED` / `CANCELLED`) с
lifecycle-методами `submit_move` / `force_submit_missing` / `resolve` /
`cancel`, см. `mass_duel.py`. Symmetricaly to 1×1-`Duel`.
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
    DuelLogNoTemplatesError,
    DuelNotFoundError,
    InvalidDuelStateError,
    InvalidLengthError,
    InvalidMassDuelStateError,
    InvalidRoundCountError,
    MassDuelNotReadyError,
    MassMoveAlreadySubmittedError,
    MoveAlreadySubmittedError,
    NoMissingMassMovesError,
    NoMissingMovesError,
    NotADuelParticipantError,
    NotAMassDuelParticipantError,
    PvpError,
    PvpRequirementsNotMetError,
    SelfChallengeError,
)
from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository, LobbyEntry
from pipirik_wars.domain.pvp.log_template import (
    DuelLogTemplate,
    RoundOutcomeKind,
    classify_round_outcome,
    pick_duel_log_template,
)
from pipirik_wars.domain.pvp.mass import (
    MassDamageEntry,
    MassDuelOutcome,
    MassDuelWinner,
    MassPairing,
    MassRoundChoice,
    MassRoundOutcome,
)
from pipirik_wars.domain.pvp.mass_duel import (
    MassDuel,
    MassDuelState,
)
from pipirik_wars.domain.pvp.mass_services import (
    pair_attackers,
    resolve_mass_duel,
    resolve_mass_round,
)
from pipirik_wars.domain.pvp.repositories import IDuelRepository
from pipirik_wars.domain.pvp.services import (
    DEFAULT_DUEL_ROUNDS,
    resolve_duel,
    resolve_round,
)

__all__ = [
    "DEFAULT_DUEL_ROUNDS",
    "Duel",
    "DuelLogNoTemplatesError",
    "DuelLogTemplate",
    "DuelMode",
    "DuelNotFoundError",
    "DuelOutcome",
    "DuelState",
    "DuelWinner",
    "IDuelRepository",
    "IGlobalLobbyRepository",
    "InvalidDuelStateError",
    "InvalidLengthError",
    "InvalidMassDuelStateError",
    "InvalidRoundCountError",
    "LobbyEntry",
    "MassDamageEntry",
    "MassDuel",
    "MassDuelNotReadyError",
    "MassDuelOutcome",
    "MassDuelState",
    "MassDuelWinner",
    "MassMoveAlreadySubmittedError",
    "MassPairing",
    "MassRoundChoice",
    "MassRoundOutcome",
    "MoveAlreadySubmittedError",
    "NoMissingMassMovesError",
    "NoMissingMovesError",
    "NotADuelParticipantError",
    "NotAMassDuelParticipantError",
    "PendingRound",
    "Position",
    "PvpError",
    "PvpRequirementsNotMetError",
    "RoundChoice",
    "RoundOutcome",
    "RoundOutcomeKind",
    "SelfChallengeError",
    "classify_round_outcome",
    "pair_attackers",
    "pick_duel_log_template",
    "resolve_duel",
    "resolve_mass_duel",
    "resolve_mass_round",
    "resolve_round",
]
