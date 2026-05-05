"""Презентер для команды `/top` (Спринт 1.4.C, ПД 1.4.6).

Чистые функции рендеринга. На входе — `Sequence[TopPlayerEntry]` из
use-case-а, на выходе — строка для `message.answer(...)`. Формат
строки одного ряда — «`Титул Название Имя — N см`» (ПД 1.4.6).
Локализация титулов уже инкапсулирована в `render_full_nick`
(переиспользуем из `bot.presenters.profile`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from pipirik_wars.application.top import TopPlayerEntry
from pipirik_wars.bot.presenters.profile import render_full_nick

REPLY_TOP_HEADER_RU: Final[str] = "🏆 <b>Топ пипириков</b>"
REPLY_TOP_EMPTY_RU: Final[str] = "🏆 Пока в топе никого нет. Стань первым — нажми /start!"


def render_top_entry(entry: TopPlayerEntry, *, rank: int) -> str:
    """Один ряд топа: «<rank>. Титул Название Имя — N см»."""
    nick = render_full_nick(
        title=entry.title,
        display_name=entry.display_name,
        name=entry.name,
    )
    return f"{rank}. {nick} — {entry.length_cm} см"


def render_top(entries: Sequence[TopPlayerEntry]) -> str:
    """Полный текст ответа на `/top`.

    Пустой список → дружелюбное приглашение позвать игроков.
    """
    if not entries:
        return REPLY_TOP_EMPTY_RU
    lines = [REPLY_TOP_HEADER_RU, ""]
    for index, entry in enumerate(entries, start=1):
        lines.append(render_top_entry(entry, rank=index))
    return "\n".join(lines)


__all__ = [
    "REPLY_TOP_EMPTY_RU",
    "REPLY_TOP_HEADER_RU",
    "render_top",
    "render_top_entry",
]
