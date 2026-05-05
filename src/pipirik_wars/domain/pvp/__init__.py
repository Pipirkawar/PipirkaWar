"""Доменный пакет PvP (ГДД §7.1).

Содержит чистый движок боя 1×1 (Спринт 2.1.A): value-objects
`Position` / `RoundChoice` / `RoundOutcome` / `DuelOutcome` и
функции-резолверы `resolve_round(...)` / `resolve_duel(...)`. Любая
инфраструктура (БД, AFK-таймер, инлайн-кнопки) лежит выше доменного
слоя.

Будущие расширения (Спринты 2.1.B–F, 2.2):

* `entities.py` — добавятся агрегаты вызова (`DuelChallenge`) и боя
  (`Duel`) для persistence-слоя.
* `repositories.py` — порт `IDuelRepository`.
* `services.py` — `pick_random_choice` (AFK-фоллбэк) и `mass_pvp_resolver`
  для клановых N×M-битв.
"""

from pipirik_wars.domain.pvp.entities import (
    DuelOutcome,
    DuelWinner,
    Position,
    RoundChoice,
    RoundOutcome,
)
from pipirik_wars.domain.pvp.errors import (
    InvalidLengthError,
    InvalidRoundCountError,
    PvpError,
)
from pipirik_wars.domain.pvp.services import (
    DEFAULT_DUEL_ROUNDS,
    resolve_duel,
    resolve_round,
)

__all__ = [
    "DEFAULT_DUEL_ROUNDS",
    "DuelOutcome",
    "DuelWinner",
    "InvalidLengthError",
    "InvalidRoundCountError",
    "Position",
    "PvpError",
    "RoundChoice",
    "RoundOutcome",
    "resolve_duel",
    "resolve_round",
]
