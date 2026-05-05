"""Презентер для команды `/top` (Спринт 1.4.C → 1.5.C, ПД 1.4.6).

`TopPresenter` берёт `Sequence[TopPlayerEntry]` из use-case-а и `Locale`
из middleware-а, отдаёт строку для `message.answer(...)`. Формат
строки одного ряда — «`<rank>. Титул Название Имя — N см`» (ПД 1.4.6),
сам шаблон лежит в `.ftl` под ключом `top-entry`.

Локализация титулов делается через `ProfilePresenter.title_message_key`,
чтобы /top и /profile использовали один и тот же набор ключей
`profile-title-*` — это упрощает жизнь переводчика.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.top import TopPlayerEntry
from pipirik_wars.bot.presenters.profile import (
    _render_full_nick,
    title_message_key,
)

_KEY_HEADER: Final[MessageKey] = MessageKey("top-header")
_KEY_EMPTY: Final[MessageKey] = MessageKey("top-empty")
_KEY_ENTRY: Final[MessageKey] = MessageKey("top-entry")


class TopPresenter:
    """Локализованный рендер `/top` через `IMessageBundle`."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def render(
        self,
        entries: Sequence[TopPlayerEntry],
        *,
        locale: Locale,
    ) -> str:
        """Полный текст ответа на `/top`.

        Пустой список → дружелюбное приглашение позвать игроков
        (ключ `top-empty`).
        """
        if not entries:
            return self._bundle.format(_KEY_EMPTY, locale=locale)
        lines = [self._bundle.format(_KEY_HEADER, locale=locale), ""]
        for index, entry in enumerate(entries, start=1):
            lines.append(self._render_entry(entry, rank=index, locale=locale))
        return "\n".join(lines)

    def _render_entry(
        self,
        entry: TopPlayerEntry,
        *,
        rank: int,
        locale: Locale,
    ) -> str:
        title_str: str | None = None
        if entry.title is not None:
            title_str = self._bundle.format(
                title_message_key(entry.title),
                locale=locale,
            )
        nick = _render_full_nick(
            title_str=title_str,
            display_name=entry.display_name,
            name=entry.name,
        )
        return self._bundle.format(
            _KEY_ENTRY,
            locale=locale,
            rank=rank,
            nick=nick,
            length_cm=entry.length_cm,
        )


__all__ = ["TopPresenter"]
