"""Презентеры команд поддержки админ-интерфейса (Спринт 2.5-B).

Каждый презентер локализует один логический ответ handler-а. Никакого
I/O — только формат + `IMessageBundle.format(...)`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from pipirik_wars.application.admin import PlayerSummary
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.domain.player import PlayerStatus

# ── /find_player ─────────────────────────────────────────────────────────────

_KEY_FIND_USAGE: Final[MessageKey] = MessageKey("admin-find-player-usage")
_KEY_FIND_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-find-player-not-authorized")
_KEY_FIND_EMPTY: Final[MessageKey] = MessageKey("admin-find-player-empty")
_KEY_FIND_HEADER: Final[MessageKey] = MessageKey("admin-find-player-header")
_KEY_FIND_ROW: Final[MessageKey] = MessageKey("admin-find-player-row")

_DASH = "—"


def _status_label(status: PlayerStatus, *, locale: Locale) -> str:
    """Текстовая метка статуса для локали (ru/en)."""
    if status is PlayerStatus.ACTIVE:
        return "active" if locale.code == "en" else "активен"
    return "frozen" if locale.code == "en" else "заморожен"


class FindPlayerPresenter:
    """Локализованные ответы `/find_player`."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_FIND_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_FIND_NOT_AUTHORIZED, locale=locale)

    def empty(self, *, locale: Locale, query: str) -> str:
        return self._bundle.format(_KEY_FIND_EMPTY, locale=locale, query=query)

    def render(
        self,
        *,
        locale: Locale,
        query: str,
        results: Iterable[PlayerSummary],
    ) -> str:
        rows = list(results)
        header = self._bundle.format(
            _KEY_FIND_HEADER,
            locale=locale,
            count=len(rows),
            query=query,
        )
        body_lines = [
            self._bundle.format(
                _KEY_FIND_ROW,
                locale=locale,
                **{
                    "tg_id": str(row.tg_id),
                    "username": row.username if row.username is not None else _DASH,
                    "name": row.name if row.name is not None else _DASH,
                    "title": row.title if row.title is not None else _DASH,
                    "length_cm": row.length_cm,
                    "thickness_level": row.thickness_level,
                    "status": _status_label(row.status, locale=locale),
                },
            )
            for row in rows
        ]
        return "\n".join([header, *body_lines])


__all__ = ["FindPlayerPresenter"]
