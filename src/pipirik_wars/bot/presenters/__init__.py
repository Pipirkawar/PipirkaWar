"""bot/presenters package.

Тонкие функции рендеринга `ProfileView`/`ClanCard`/… в строки
для `message.answer(...)`. Не содержат I/O и не работают с aiogram-объектами
напрямую — это делает handler. Тестируются как чистые функции.
"""

from pipirik_wars.bot.presenters.profile import (
    render_full_nick,
    render_profile_card,
)

__all__ = ["render_full_nick", "render_profile_card"]
