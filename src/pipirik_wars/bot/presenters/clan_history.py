"""Презентер для команды `/clan_history` (Спринт 2.2.G / ПД 2.2.5).

`ClanHistoryPresenter` берёт `Sequence[ClanMassDuelHistoryEntry]` из
use-case-а и `Locale` из middleware-а, отдаёт строку для
`message.answer(...)`.

Формат строки одного ряда — «<idx>. ⚔ {opponent_title} — <emoji> <result>
({our_count}×{opponent_count}, {when})», где `<emoji>/<result>`
зависят от `outcome` (`VICTORY`/`DEFEAT`/`DRAW`/`CANCELLED`). Шаблоны
лежат в `.ftl` под ключами `clan-history-entry-{victory,defeat,draw,cancelled}`.

`{when}` форматируется как `dd.mm HH:MM` (UTC) — компактно для
группового чата. Берём `completed_at`, а для `CANCELLED`-боёв
`created_at` (там нет `completed_at`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.domain.pvp import (
    ClanMassDuelHistoryEntry,
    ClanMassDuelOutcomeForUs,
)

_KEY_HEADER: Final[MessageKey] = MessageKey("clan-history-header")
_KEY_EMPTY: Final[MessageKey] = MessageKey("clan-history-empty")
_KEY_NEEDS_GROUP: Final[MessageKey] = MessageKey("clan-history-needs-group-chat")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("clan-history-not-registered")
_KEY_ENTRY_VICTORY: Final[MessageKey] = MessageKey("clan-history-entry-victory")
_KEY_ENTRY_DEFEAT: Final[MessageKey] = MessageKey("clan-history-entry-defeat")
_KEY_ENTRY_DRAW: Final[MessageKey] = MessageKey("clan-history-entry-draw")
_KEY_ENTRY_CANCELLED: Final[MessageKey] = MessageKey("clan-history-entry-cancelled")

_ENTRY_KEY_BY_OUTCOME: Final[dict[ClanMassDuelOutcomeForUs, MessageKey]] = {
    ClanMassDuelOutcomeForUs.VICTORY: _KEY_ENTRY_VICTORY,
    ClanMassDuelOutcomeForUs.DEFEAT: _KEY_ENTRY_DEFEAT,
    ClanMassDuelOutcomeForUs.DRAW: _KEY_ENTRY_DRAW,
    ClanMassDuelOutcomeForUs.CANCELLED: _KEY_ENTRY_CANCELLED,
}


class ClanHistoryPresenter:
    """Локализованный рендер `/clan_history` через `IMessageBundle`."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def needs_group_chat(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NEEDS_GROUP, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def render(
        self,
        entries: Sequence[ClanMassDuelHistoryEntry],
        *,
        clan_title: str,
        locale: Locale,
    ) -> str:
        """Полный текст ответа на `/clan_history`.

        Пустой список → дружелюбное сообщение, что у клана пока нет
        боёв (ключ `clan-history-empty`).
        """
        if not entries:
            return self._bundle.format(_KEY_EMPTY, locale=locale, clan_title=clan_title)
        lines = [
            self._bundle.format(_KEY_HEADER, locale=locale, clan_title=clan_title),
            "",
        ]
        for index, entry in enumerate(entries, start=1):
            lines.append(self._render_entry(entry, idx=index, locale=locale))
        return "\n".join(lines)

    def _render_entry(
        self,
        entry: ClanMassDuelHistoryEntry,
        *,
        idx: int,
        locale: Locale,
    ) -> str:
        key = _ENTRY_KEY_BY_OUTCOME[entry.outcome]
        when = _format_when(entry)
        if entry.outcome is ClanMassDuelOutcomeForUs.CANCELLED:
            return self._bundle.format(
                key,
                locale=locale,
                idx=idx,
                opponent_clan_title=entry.opponent_clan_title.value,
                when=when,
            )
        return self._bundle.format(
            key,
            locale=locale,
            idx=idx,
            opponent_clan_title=entry.opponent_clan_title.value,
            our_delta_cm=entry.our_delta_cm,
            our_count=entry.our_participants_count,
            opponent_count=entry.opponent_participants_count,
            when=when,
        )


def _format_when(entry: ClanMassDuelHistoryEntry) -> str:
    """Форматирует timestamp боя как `dd.mm HH:MM` (UTC).

    Для COMPLETED-боя берём `completed_at`, для CANCELLED — `created_at`.
    """
    ts = entry.completed_at if entry.completed_at is not None else entry.created_at
    return ts.strftime("%d.%m %H:%M")


__all__ = ["ClanHistoryPresenter"]
