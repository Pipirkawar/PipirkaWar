"""Презентер для команды `/clantop` (Спринт 2.2.A / ПД 2.2.1).

`ClanTopPresenter` берёт `Sequence[ClanTopEntry]` из use-case-а и
`Locale` из middleware-а, отдаёт строку для `message.answer(...)`.
Формат строки одного ряда — «<rank>. {title} — {N} см ({M} 👥)»
(ПД 2.2.1), сам шаблон лежит в `.ftl` под ключом `clantop-entry`.

Аналог `TopPresenter` (1.4.C) — тот же паттерн «тонкий класс с
`__init__(*, bundle: IMessageBundle)` + методами, принимающими
`locale: Locale` keyword-only».
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.top import ClanTopEntry

_KEY_HEADER: Final[MessageKey] = MessageKey("clantop-header")
_KEY_EMPTY: Final[MessageKey] = MessageKey("clantop-empty")
_KEY_ENTRY: Final[MessageKey] = MessageKey("clantop-entry")


class ClanTopPresenter:
    """Локализованный рендер `/clantop` через `IMessageBundle`."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def render(
        self,
        entries: Sequence[ClanTopEntry],
        *,
        locale: Locale,
    ) -> str:
        """Полный текст ответа на `/clantop`.

        Пустой список → дружелюбное приглашение зарегистрировать клан
        (ключ `clantop-empty`).
        """
        if not entries:
            return self._bundle.format(_KEY_EMPTY, locale=locale)
        lines = [self._bundle.format(_KEY_HEADER, locale=locale), ""]
        for index, entry in enumerate(entries, start=1):
            lines.append(self._render_entry(entry, rank=index, locale=locale))
        return "\n".join(lines)

    def _render_entry(
        self,
        entry: ClanTopEntry,
        *,
        rank: int,
        locale: Locale,
    ) -> str:
        return self._bundle.format(
            _KEY_ENTRY,
            locale=locale,
            rank=rank,
            clan_title=entry.clan_title.value,
            total_length_cm=entry.total_length_cm,
            member_count=entry.member_count,
        )


__all__ = ["ClanTopPresenter"]
