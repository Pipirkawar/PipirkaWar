"""Доменный пакет «Free-to-play рулетка» (ГДД §12.4, Спринт 3.5-A/B).

Содержит чистые сущности (`RouletteOutcomeKind`, `RouletteOutcome`,
`RouletteSpin`), доменные ошибки (`RouletteDomainError`,
`InvalidRouletteConfigError`), picker-сервис (`pick_roulette_outcome`)
и порт persistence-слоя (`IRouletteSpinRepository`, Спринт 3.5-B).
Без use-case-а и без bot-UI — это слои 3.5-C / 3.5-D.
"""

from __future__ import annotations

from pipirik_wars.domain.roulette.entities import (
    RouletteOutcome,
    RouletteSpin,
)
from pipirik_wars.domain.roulette.errors import (
    InvalidRouletteConfigError,
    RouletteDomainError,
)
from pipirik_wars.domain.roulette.ports import IRouletteSpinRepository
from pipirik_wars.domain.roulette.services import pick_roulette_outcome

__all__ = [
    "IRouletteSpinRepository",
    "InvalidRouletteConfigError",
    "RouletteDomainError",
    "RouletteOutcome",
    "RouletteSpin",
    "pick_roulette_outcome",
]
