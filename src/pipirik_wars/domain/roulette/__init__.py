"""Доменный пакет рулеток (ГДД §12.4 free + §12.5 paid, Спринт 3.5-A → 4.1-A).

Содержит чистые сущности (`RouletteOutcomeKind`, `RouletteOutcome`,
`RouletteSpin`, `RouletteVariant`), доменные ошибки
(`RouletteDomainError`, `InvalidRouletteConfigError`), picker-сервисы
(`pick_roulette_outcome` — free, `pick_paid_outcome` — paid, Спринт
4.1-A) и порт persistence-слоя (`IRouletteSpinRepository`, Спринт
3.5-B). Без use-case-а и без bot-UI — это слои 3.5-C / 3.5-D / 4.1-A.
"""

from __future__ import annotations

from pipirik_wars.domain.roulette.entities import (
    RouletteOutcome,
    RouletteOutcomeKind,
    RouletteSpin,
    RouletteVariant,
)
from pipirik_wars.domain.roulette.errors import (
    InsufficientLengthForRouletteError,
    InvalidRouletteConfigError,
    RouletteDomainError,
    RouletteThicknessGateError,
)
from pipirik_wars.domain.roulette.ports import IRouletteSpinRepository
from pipirik_wars.domain.roulette.services import (
    pick_paid_outcome,
    pick_roulette_outcome,
)

__all__ = [
    "IRouletteSpinRepository",
    "InsufficientLengthForRouletteError",
    "InvalidRouletteConfigError",
    "RouletteDomainError",
    "RouletteOutcome",
    "RouletteOutcomeKind",
    "RouletteSpin",
    "RouletteThicknessGateError",
    "RouletteVariant",
    "pick_paid_outcome",
    "pick_roulette_outcome",
]
