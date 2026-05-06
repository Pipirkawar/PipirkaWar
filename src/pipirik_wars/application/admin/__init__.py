"""Application-слой расширенного админ-интерфейса (Спринт 2.5).

Use-case-ы, общие для всех опасных команд:

* `RequestAdminConfirm` — выдаёт одноразовый `token` и регистрирует
  ожидание TOTP-кода в `IAdminConfirmStore` (TTL 60 секунд).
* `VerifyAdminConfirm` — забирает токен из store-а, проверяет
  6-значный код через `ITotpVerifier`, возвращает payload команды
  для продолжения работы.

Сами целевые команды (`/ban`, `/grant_*`, `/balance_set`, `/announce`)
живут в `application/admin/<command>/` и появятся в Спринтах 2.5-B/C/D.
"""

from pipirik_wars.application.admin.ban_player import (
    BanPlayer,
    BanPlayerInput,
    BanPlayerOutput,
)
from pipirik_wars.application.admin.find_players import (
    DEFAULT_FIND_PLAYERS_LIMIT,
    FindPlayers,
    FindPlayersInput,
    FindPlayersOutput,
    PlayerSummary,
    player_to_summary,
)
from pipirik_wars.application.admin.freeze_player import (
    FreezePlayer,
    FreezePlayerInput,
    FreezePlayerOutput,
)
from pipirik_wars.application.admin.get_player_card import (
    ClanCardInfo,
    ForestCardInfo,
    GetPlayerCard,
    GetPlayerCardInput,
    GetPlayerCardOutput,
    PlayerCard,
)
from pipirik_wars.application.admin.grant_length import (
    GrantLength,
    GrantLengthBlockedError,
    GrantLengthInput,
    GrantLengthOutput,
)
from pipirik_wars.application.admin.grant_thickness import (
    GrantThickness,
    GrantThicknessBlockedError,
    GrantThicknessInput,
    GrantThicknessOutput,
    ThicknessLevelInvalidError,
)
from pipirik_wars.application.admin.request_confirm import (
    RequestAdminConfirm,
    RequestAdminConfirmInput,
    RequestAdminConfirmOutput,
    TokenFactory,
)
from pipirik_wars.application.admin.unfreeze_player import (
    UnfreezePlayer,
    UnfreezePlayerInput,
    UnfreezePlayerOutput,
)
from pipirik_wars.application.admin.verify_confirm import (
    VerifyAdminConfirm,
    VerifyAdminConfirmInput,
    VerifyAdminConfirmOutput,
)

__all__ = [
    "DEFAULT_FIND_PLAYERS_LIMIT",
    "BanPlayer",
    "BanPlayerInput",
    "BanPlayerOutput",
    "ClanCardInfo",
    "FindPlayers",
    "FindPlayersInput",
    "FindPlayersOutput",
    "ForestCardInfo",
    "FreezePlayer",
    "FreezePlayerInput",
    "FreezePlayerOutput",
    "GetPlayerCard",
    "GetPlayerCardInput",
    "GetPlayerCardOutput",
    "GrantLength",
    "GrantLengthBlockedError",
    "GrantLengthInput",
    "GrantLengthOutput",
    "GrantThickness",
    "GrantThicknessBlockedError",
    "GrantThicknessInput",
    "GrantThicknessOutput",
    "PlayerCard",
    "PlayerSummary",
    "RequestAdminConfirm",
    "RequestAdminConfirmInput",
    "RequestAdminConfirmOutput",
    "ThicknessLevelInvalidError",
    "TokenFactory",
    "UnfreezePlayer",
    "UnfreezePlayerInput",
    "UnfreezePlayerOutput",
    "VerifyAdminConfirm",
    "VerifyAdminConfirmInput",
    "VerifyAdminConfirmOutput",
    "player_to_summary",
]
