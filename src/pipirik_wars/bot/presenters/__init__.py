"""bot/presenters package.

Тонкие классы/функции рендеринга `ProfileView`/`ClanCard`/… в строки
для `message.answer(...)`. Не содержат I/O и не работают с aiogram-объектами
напрямую — это делает handler.

С 1.5.D публичный API почти полностью переехал на `*Presenter`-классы
с DI `IMessageBundle` (см. `application/i18n/`). Презентер `forest`
ещё держит pure-функции `render_forest_*` — его миграция в Спринте 1.5.E.
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
from pipirik_wars.bot.presenters.oracle import OraclePresenter
from pipirik_wars.bot.presenters.profile import (
    ProfilePresenter,
    render_full_nick,
)
from pipirik_wars.bot.presenters.top import TopPresenter
from pipirik_wars.bot.presenters.upgrade import (
    UpgradeCallbackAction,
    UpgradeCallbackData,
    UpgradePresenter,
    parse_upgrade_callback_data,
    upgrade_callback_data,
)

__all__ = [
    "ForestCallbackAction",
    "ForestCallbackData",
    "OraclePresenter",
    "ProfilePresenter",
    "TopPresenter",
    "UpgradeCallbackAction",
    "UpgradeCallbackData",
    "UpgradePresenter",
    "build_finish_keyboard",
    "forest_callback_data",
    "parse_forest_callback_data",
    "parse_upgrade_callback_data",
    "render_forest_finished",
    "render_forest_started",
    "render_full_nick",
    "upgrade_callback_data",
]
