"""bot/presenters package.

Тонкие классы/функции рендеринга `ProfileView`/`ClanCard`/… в строки
для `message.answer(...)`. Не содержат I/O и не работают с aiogram-объектами
напрямую — это делает handler.

С 1.5.E все презентеры — `*Presenter`-классы с DI `IMessageBundle`
(см. `application/i18n/`). Pure-функции остались только для
`callback_data`-сериализации (она не зависит от локали — см.
`forest_callback_data` / `upgrade_callback_data`).
"""

from pipirik_wars.bot.presenters.forest import (
    ForestCallbackAction,
    ForestCallbackData,
    ForestPresenter,
    forest_callback_data,
    parse_forest_callback_data,
)
from pipirik_wars.bot.presenters.oracle import OraclePresenter
from pipirik_wars.bot.presenters.profile import ProfilePresenter
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
    "ForestPresenter",
    "OraclePresenter",
    "ProfilePresenter",
    "TopPresenter",
    "UpgradeCallbackAction",
    "UpgradeCallbackData",
    "UpgradePresenter",
    "forest_callback_data",
    "parse_forest_callback_data",
    "parse_upgrade_callback_data",
    "upgrade_callback_data",
]
