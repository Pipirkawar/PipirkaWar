"""Use-cases подсистемы «Игрок» (Спринт 1.1 + 1.2.4)."""

from pipirik_wars.application.player.get_profile import GetProfile, ProfileView
from pipirik_wars.application.player.register import (
    PlayerQueued,
    PlayerRegistered,
    RegisterPlayer,
    RegisterPlayerResult,
)

__all__ = [
    "GetProfile",
    "PlayerQueued",
    "PlayerRegistered",
    "ProfileView",
    "RegisterPlayer",
    "RegisterPlayerResult",
]
