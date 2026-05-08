"""bot/notifications package — outgoing-side Telegram-нотификаторы.

Адаптеры implements портов из `application/` для исходящих сообщений
бота, которые **не** инициированы пользователем (т.е. не через `dp.message`).
Например, нотификатор «вернулся из леса» (`TelegramForestFinishNotifier`)
шлёт сообщение игроку по событию APScheduler-job-а.

Живут в `bot/`, а не `infrastructure/telegram/`, потому что используют
презентеры из `bot/presenters/` (которые знают про aiogram-keyboard-ы).
Импорт-контракт `bot → application` соблюдается.
"""

from pipirik_wars.bot.notifications.bosses import (
    TelegramBossFightFinishNotifier,
    TelegramBossLobbyCloseNotifier,
    TelegramBossRoundTickNotifier,
)
from pipirik_wars.bot.notifications.caravans import (
    TelegramCaravanBattleFinishNotifier,
    TelegramCaravanLobbyCloseNotifier,
)
from pipirik_wars.bot.notifications.dungeon import TelegramDungeonFinishNotifier
from pipirik_wars.bot.notifications.forest import TelegramForestFinishNotifier
from pipirik_wars.bot.notifications.mountains import TelegramMountainFinishNotifier
from pipirik_wars.bot.notifications.weekly_referral_summary import (
    TelegramWeeklyClanReferralSummaryNotifier,
)

__all__ = [
    "TelegramBossFightFinishNotifier",
    "TelegramBossLobbyCloseNotifier",
    "TelegramBossRoundTickNotifier",
    "TelegramCaravanBattleFinishNotifier",
    "TelegramCaravanLobbyCloseNotifier",
    "TelegramDungeonFinishNotifier",
    "TelegramForestFinishNotifier",
    "TelegramMountainFinishNotifier",
    "TelegramWeeklyClanReferralSummaryNotifier",
]
