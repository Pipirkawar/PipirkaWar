"""Домен «Рейд-боссы» (Спринт 3.3, ГДД §10).

Каркас доменных VO/сущностей/портов/ошибок. Use-case-ы и боевая
механика — Спринты 3.3-B (призыв + лобби + persistence) и 3.3-C
(раунды + resolve + награды).
"""

from pipirik_wars.domain.bosses.entities import BossFight, BossParticipant
from pipirik_wars.domain.bosses.errors import (
    AlreadyInBossFightError,
    BossError,
    BossFightLobbyClosedError,
    BossFightNotFoundError,
    BossFightRequirementError,
    BossPlayerPoolEmptyError,
    BossSummonOnGlobalCooldownError,
    InvalidBossFightStateError,
    NotInBossFightError,
)
from pipirik_wars.domain.bosses.repositories import (
    IBossFightRepository,
    IBossParticipantRepository,
)
from pipirik_wars.domain.bosses.value_objects import (
    BossDamage,
    BossFightStatus,
    BossKind,
)

__all__ = [
    "AlreadyInBossFightError",
    "BossDamage",
    "BossError",
    "BossFight",
    "BossFightLobbyClosedError",
    "BossFightNotFoundError",
    "BossFightRequirementError",
    "BossFightStatus",
    "BossKind",
    "BossParticipant",
    "BossPlayerPoolEmptyError",
    "BossSummonOnGlobalCooldownError",
    "IBossFightRepository",
    "IBossParticipantRepository",
    "InvalidBossFightStateError",
    "NotInBossFightError",
]
