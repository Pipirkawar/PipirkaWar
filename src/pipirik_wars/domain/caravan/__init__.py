"""Домен «Караван» (Спринт 3.2, ГДД §9).

Каркас доменных VO/сущностей/портов. Use-case-ы и боевая механика —
Спринты 3.2-B (создание + лобби + persistence) и 3.2-C (бой +
resolve + награды).
"""

from pipirik_wars.domain.caravan.entities import Caravan, CaravanParticipant
from pipirik_wars.domain.caravan.errors import (
    AlreadyInCaravanError,
    CaravanCapacityExceededError,
    CaravanCooldownError,
    CaravanError,
    CaravanLobbyClosedError,
    CaravanNotFoundError,
    CaravanRequirementError,
    CaravanRoleConflictError,
)
from pipirik_wars.domain.caravan.repositories import (
    ICaravanParticipantRepository,
    ICaravanRepository,
)
from pipirik_wars.domain.caravan.services import (
    CaravanBattleResult,
    CaravanParticipantOutcome,
    resolve_caravan_battle,
)
from pipirik_wars.domain.caravan.value_objects import (
    CaravanContribution,
    CaravanRole,
    CaravanStatus,
)

__all__ = [
    "AlreadyInCaravanError",
    "Caravan",
    "CaravanBattleResult",
    "CaravanCapacityExceededError",
    "CaravanContribution",
    "CaravanCooldownError",
    "CaravanError",
    "CaravanLobbyClosedError",
    "CaravanNotFoundError",
    "CaravanParticipant",
    "CaravanParticipantOutcome",
    "CaravanRequirementError",
    "CaravanRole",
    "CaravanRoleConflictError",
    "CaravanStatus",
    "ICaravanParticipantRepository",
    "ICaravanRepository",
    "resolve_caravan_battle",
]
