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

from pipirik_wars.application.admin._broadcast_ports import (
    BroadcastSendResult,
    IBroadcastSender,
    IBroadcastTaskSpawner,
)
from pipirik_wars.application.admin.ban_player import (
    BanPlayer,
    BanPlayerInput,
    BanPlayerOutput,
)
from pipirik_wars.application.admin.broadcast_announcement import (
    BROADCAST_MESSAGE_MAX_LEN,
    BROADCAST_MESSAGE_MIN_LEN,
    BroadcastAnnouncement,
    BroadcastAnnouncementInput,
    BroadcastAnnouncementOutput,
    BroadcastLocaleFilter,
    BroadcastLocaleFilterInvalidError,
    BroadcastMessageEmptyError,
    BroadcastMessageTooLongError,
    BroadcastValidationError,
    normalize_broadcast_message,
    parse_locale_filter,
)
from pipirik_wars.application.admin.find_players import (
    DEFAULT_FIND_PLAYERS_LIMIT,
    FindPlayers,
    FindPlayersInput,
    FindPlayersOutput,
    PlayerSummary,
    player_to_summary,
)
from pipirik_wars.application.admin.freeze_clan import (
    FreezeClanAdmin,
    FreezeClanAdminInput,
    FreezeClanAdminOutput,
)
from pipirik_wars.application.admin.freeze_player import (
    FreezePlayer,
    FreezePlayerInput,
    FreezePlayerOutput,
)
from pipirik_wars.application.admin.get_admin_audit_trail import (
    DEFAULT_AUDIT_LIMIT,
    MAX_AUDIT_LIMIT,
    AdminAuditActionUnknownError,
    GetAdminAuditTrail,
    GetAdminAuditTrailInput,
    GetAdminAuditTrailOutput,
)
from pipirik_wars.application.admin.get_balance_value import (
    GetBalanceValue,
    GetBalanceValueInput,
    GetBalanceValueOutput,
)
from pipirik_wars.application.admin.get_clan_card import (
    ClanCard,
    ClanMemberCardInfo,
    GetClanCard,
    GetClanCardInput,
    GetClanCardOutput,
)
from pipirik_wars.application.admin.get_clan_daily_head_history import (
    DailyHeadHistoryEntry,
    GetClanDailyHeadHistory,
    GetClanDailyHeadHistoryInput,
    GetClanDailyHeadHistoryOutput,
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
from pipirik_wars.application.admin.run_broadcast_announcement import (
    BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN,
    BROADCAST_BATCH_INTERVAL_SECONDS,
    BROADCAST_BATCH_SIZE,
    RunBroadcastAnnouncement,
    RunBroadcastAnnouncementInput,
    RunBroadcastAnnouncementOutput,
    SleepFn,
)
from pipirik_wars.application.admin.set_balance_value import (
    SetBalanceValue,
    SetBalanceValueInput,
    SetBalanceValueOutput,
)
from pipirik_wars.application.admin.setup_totp import (
    PROVISIONING_ALGORITHM,
    PROVISIONING_DIGITS,
    PROVISIONING_ISSUER,
    PROVISIONING_PERIOD,
    SetupAdminTotp,
    SetupAdminTotpInput,
    SetupAdminTotpOutput,
    build_provisioning_uri,
)
from pipirik_wars.application.admin.unfreeze_clan import (
    UnfreezeClanAdmin,
    UnfreezeClanAdminInput,
    UnfreezeClanAdminOutput,
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
from pipirik_wars.domain.balance.errors import BalanceKeyError

__all__ = [
    "BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN",
    "BROADCAST_BATCH_INTERVAL_SECONDS",
    "BROADCAST_BATCH_SIZE",
    "BROADCAST_MESSAGE_MAX_LEN",
    "BROADCAST_MESSAGE_MIN_LEN",
    "DEFAULT_AUDIT_LIMIT",
    "DEFAULT_FIND_PLAYERS_LIMIT",
    "MAX_AUDIT_LIMIT",
    "PROVISIONING_ALGORITHM",
    "PROVISIONING_DIGITS",
    "PROVISIONING_ISSUER",
    "PROVISIONING_PERIOD",
    "AdminAuditActionUnknownError",
    "BalanceKeyError",
    "BanPlayer",
    "BanPlayerInput",
    "BanPlayerOutput",
    "BroadcastAnnouncement",
    "BroadcastAnnouncementInput",
    "BroadcastAnnouncementOutput",
    "BroadcastLocaleFilter",
    "BroadcastLocaleFilterInvalidError",
    "BroadcastMessageEmptyError",
    "BroadcastMessageTooLongError",
    "BroadcastSendResult",
    "BroadcastValidationError",
    "ClanCard",
    "ClanCardInfo",
    "ClanMemberCardInfo",
    "DailyHeadHistoryEntry",
    "FindPlayers",
    "FindPlayersInput",
    "FindPlayersOutput",
    "ForestCardInfo",
    "FreezeClanAdmin",
    "FreezeClanAdminInput",
    "FreezeClanAdminOutput",
    "FreezePlayer",
    "FreezePlayerInput",
    "FreezePlayerOutput",
    "GetAdminAuditTrail",
    "GetAdminAuditTrailInput",
    "GetAdminAuditTrailOutput",
    "GetBalanceValue",
    "GetBalanceValueInput",
    "GetBalanceValueOutput",
    "GetClanCard",
    "GetClanCardInput",
    "GetClanCardOutput",
    "GetClanDailyHeadHistory",
    "GetClanDailyHeadHistoryInput",
    "GetClanDailyHeadHistoryOutput",
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
    "IBroadcastSender",
    "IBroadcastTaskSpawner",
    "PlayerCard",
    "PlayerSummary",
    "RequestAdminConfirm",
    "RequestAdminConfirmInput",
    "RequestAdminConfirmOutput",
    "RunBroadcastAnnouncement",
    "RunBroadcastAnnouncementInput",
    "RunBroadcastAnnouncementOutput",
    "SetBalanceValue",
    "SetBalanceValueInput",
    "SetBalanceValueOutput",
    "SetupAdminTotp",
    "SetupAdminTotpInput",
    "SetupAdminTotpOutput",
    "SleepFn",
    "ThicknessLevelInvalidError",
    "TokenFactory",
    "UnfreezeClanAdmin",
    "UnfreezeClanAdminInput",
    "UnfreezeClanAdminOutput",
    "UnfreezePlayer",
    "UnfreezePlayerInput",
    "UnfreezePlayerOutput",
    "VerifyAdminConfirm",
    "VerifyAdminConfirmInput",
    "VerifyAdminConfirmOutput",
    "build_provisioning_uri",
    "normalize_broadcast_message",
    "parse_locale_filter",
    "player_to_summary",
]
