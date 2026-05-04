"""Домен «Игрок» (ГДД §2, Спринт 1.1)."""

from pipirik_wars.domain.player.entities import Player, PlayerStatus
from pipirik_wars.domain.player.errors import (
    PlayerAlreadyRegisteredError,
    PlayerFrozenError,
    PlayerNotFoundError,
)
from pipirik_wars.domain.player.repositories import IPlayerRepository
from pipirik_wars.domain.player.value_objects import (
    DisplayName,
    Length,
    PlayerName,
    Thickness,
    Title,
    Username,
)

__all__ = [
    "DisplayName",
    "IPlayerRepository",
    "Length",
    "Player",
    "PlayerAlreadyRegisteredError",
    "PlayerFrozenError",
    "PlayerName",
    "PlayerNotFoundError",
    "PlayerStatus",
    "Thickness",
    "Title",
    "Username",
]
