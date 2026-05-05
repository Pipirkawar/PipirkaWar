"""Презентер ответов `/anticheat_unban` (Спринт 1.6.G).

Локализованный рендер по ключам `anticheat-unban-*`. Ключи заданы в
`locales/{ru,en}.ftl`. Никакого I/O.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

_KEY_USAGE: Final[MessageKey] = MessageKey("anticheat-unban-usage")
_KEY_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("anticheat-unban-not-authorized")
_KEY_PLAYER_NOT_FOUND: Final[MessageKey] = MessageKey("anticheat-unban-player-not-found")
_KEY_NOT_BANNED: Final[MessageKey] = MessageKey("anticheat-unban-not-banned")
_KEY_SUCCESS: Final[MessageKey] = MessageKey("anticheat-unban-success")


class AnticheatUnbanPresenter:
    """Локализованный рендер ответов `/anticheat_unban`."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_AUTHORIZED, locale=locale)

    def player_not_found(self, *, locale: Locale, tg_id: int) -> str:
        return self._bundle.format(_KEY_PLAYER_NOT_FOUND, locale=locale, tg_id=tg_id)

    def not_banned(self, *, locale: Locale, tg_id: int) -> str:
        return self._bundle.format(_KEY_NOT_BANNED, locale=locale, tg_id=tg_id)

    def success(
        self,
        *,
        locale: Locale,
        tg_id: int,
        banned_until_before: datetime,
        reason: str,
    ) -> str:
        return self._bundle.format(
            _KEY_SUCCESS,
            locale=locale,
            tg_id=tg_id,
            **{"banned-until-before": banned_until_before.isoformat()},
            reason=reason,
        )


__all__ = ["AnticheatUnbanPresenter"]
