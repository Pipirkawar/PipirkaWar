"""Use-cases подсистемы «Игрок» (Спринт 1.1 + 1.2.4 + 1.5.F)."""

from pipirik_wars.application.player.get_profile import GetProfile, ProfileView
from pipirik_wars.application.player.register import (
    PlayerQueued,
    PlayerRegistered,
    RegisterPlayer,
    RegisterPlayerResult,
)
from pipirik_wars.application.player.set_locale import (
    SetPlayerLocale,
    SetPlayerLocaleResult,
)

__all__ = [
    "GetProfile",
    "PlayerQueued",
    "PlayerRegistered",
    "ProfileView",
    "RegisterPlayer",
    "RegisterPlayerResult",
    "SetPlayerLocale",
    "SetPlayerLocaleResult",
]
