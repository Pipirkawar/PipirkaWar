"""bot/presenters package.

Тонкие функции рендеринга `ProfileView`/`ClanCard`/… в строки
для `message.answer(...)`. Не содержат I/O и не работают с aiogram-объектами
напрямую — это делает handler. Тестируются как чистые функции.
"""

from pipirik_wars.bot.presenters.forest import (
    ForestCallbackAction,
    ForestCallbackData,
    build_finish_keyboard,
    forest_callback_data,
    parse_forest_callback_data,
    render_forest_finished,
    render_forest_started,
)
from pipirik_wars.bot.presenters.oracle import (
    REPLY_GROUP_RU as RENDER_ORACLE_GROUP_RU,
    REPLY_NOT_REGISTERED_RU as RENDER_ORACLE_NOT_REGISTERED_RU,
    REPLY_OTHER_RU as RENDER_ORACLE_OTHER_RU,
    render_oracle_already_used,
    render_oracle_success,
)
from pipirik_wars.bot.presenters.profile import (
    render_full_nick,
    render_profile_card,
)
from pipirik_wars.bot.presenters.upgrade import (
    RENDER_UPGRADE_CANCELLED,
    RENDER_UPGRADE_RACE_RU,
    UpgradeCallbackAction,
    UpgradeCallbackData,
    build_upgrade_proposal_keyboard,
    parse_upgrade_callback_data,
    render_upgrade_insufficient,
    render_upgrade_proposal,
    render_upgrade_success,
    upgrade_callback_data,
)

__all__ = [
    "RENDER_ORACLE_GROUP_RU",
    "RENDER_ORACLE_NOT_REGISTERED_RU",
    "RENDER_ORACLE_OTHER_RU",
    "RENDER_UPGRADE_CANCELLED",
    "RENDER_UPGRADE_RACE_RU",
    "ForestCallbackAction",
    "ForestCallbackData",
    "UpgradeCallbackAction",
    "UpgradeCallbackData",
    "build_finish_keyboard",
    "build_upgrade_proposal_keyboard",
    "forest_callback_data",
    "parse_forest_callback_data",
    "parse_upgrade_callback_data",
    "render_forest_finished",
    "render_forest_started",
    "render_full_nick",
    "render_oracle_already_used",
    "render_oracle_success",
    "render_profile_card",
    "render_upgrade_insufficient",
    "render_upgrade_proposal",
    "render_upgrade_success",
    "upgrade_callback_data",
]
