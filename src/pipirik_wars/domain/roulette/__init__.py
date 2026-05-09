"""Доменный пакет «Free-to-play рулетка» (ГДД §12.4, Спринт 3.5-A).

Содержит чистые сущности (`RouletteOutcomeKind`, `RouletteOutcome`),
доменные ошибки (`RouletteDomainError`, `InvalidRouletteConfigError`)
и picker-сервис (`pick_roulette_outcome`). Без use-case-а и persistence —
это слои 3.5-B / 3.5-C / 3.5-D.
"""

from __future__ import annotations

from pipirik_wars.domain.roulette.entities import (
    RouletteOutcome,
)
from pipirik_wars.domain.roulette.errors import (
    InvalidRouletteConfigError,
    RouletteDomainError,
)
from pipirik_wars.domain.roulette.services import pick_roulette_outcome

__all__ = [
    "InvalidRouletteConfigError",
    "RouletteDomainError",
    "RouletteOutcome",
    "pick_roulette_outcome",
]
