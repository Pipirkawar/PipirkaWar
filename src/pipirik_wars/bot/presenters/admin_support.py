"""Презентеры команд поддержки админ-интерфейса (Спринт 2.5-B).

Каждый презентер локализует один логический ответ handler-а. Никакого
I/O — только формат + `IMessageBundle.format(...)`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Final

from pipirik_wars.application.admin import PlayerCard, PlayerSummary
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.domain.clan import ClanMemberRole, ClanStatus
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


# ── /player ──────────────────────────────────────────────────────────────────

_KEY_PLAYER_USAGE: Final[MessageKey] = MessageKey("admin-player-usage")
_KEY_PLAYER_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-player-not-authorized")
_KEY_PLAYER_BAD_ID: Final[MessageKey] = MessageKey("admin-player-bad-id")
_KEY_PLAYER_NOT_FOUND: Final[MessageKey] = MessageKey("admin-player-not-found")
_KEY_PLAYER_CARD_SUMMARY: Final[MessageKey] = MessageKey("admin-player-card-summary")
_KEY_PLAYER_CARD_CLAN: Final[MessageKey] = MessageKey("admin-player-card-clan")
_KEY_PLAYER_CARD_NO_CLAN: Final[MessageKey] = MessageKey("admin-player-card-no-clan")
_KEY_PLAYER_CARD_FOREST_ACTIVE: Final[MessageKey] = MessageKey(
    "admin-player-card-forest-active",
)
_KEY_PLAYER_CARD_NO_FOREST: Final[MessageKey] = MessageKey("admin-player-card-no-forest")
_KEY_PLAYER_CARD_ANTICHEAT: Final[MessageKey] = MessageKey("admin-player-card-anticheat")
_KEY_PLAYER_CARD_NO_ANTICHEAT: Final[MessageKey] = MessageKey(
    "admin-player-card-no-anticheat",
)


def _clan_status_label(status: ClanStatus, *, locale: Locale) -> str:
    if status is ClanStatus.ACTIVE:
        return "active" if locale.code == "en" else "активен"
    return "frozen" if locale.code == "en" else "заморожен"


def _role_label(role: ClanMemberRole, *, locale: Locale) -> str:
    if role is ClanMemberRole.LEADER:
        return "leader" if locale.code == "en" else "лидер"
    return "member" if locale.code == "en" else "участник"


def _fmt_dt(dt: datetime) -> str:
    """ISO-8601 без миллисекунд — формат, понятный и логам, и админу."""
    return dt.replace(microsecond=0).isoformat()


class GetPlayerCardPresenter:
    """Локализованные ответы `/player`."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_PLAYER_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_PLAYER_NOT_AUTHORIZED, locale=locale)

    def bad_id(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_PLAYER_BAD_ID, locale=locale, value=value)

    def not_found(self, *, locale: Locale, tg_id: int) -> str:
        return self._bundle.format(_KEY_PLAYER_NOT_FOUND, locale=locale, tg_id=str(tg_id))

    def render(self, *, locale: Locale, card: PlayerCard) -> str:
        s = card.summary
        lines: list[str] = []
        lines.append(
            self._bundle.format(
                _KEY_PLAYER_CARD_SUMMARY,
                locale=locale,
                **{
                    "tg_id": str(s.tg_id),
                    "username": s.username if s.username is not None else _DASH,
                    "name": s.name if s.name is not None else _DASH,
                    "title": s.title if s.title is not None else _DASH,
                    "length_cm": s.length_cm,
                    "thickness_level": s.thickness_level,
                    "status": _status_label(s.status, locale=locale),
                },
            ),
        )
        if card.clan is not None:
            lines.append(
                self._bundle.format(
                    _KEY_PLAYER_CARD_CLAN,
                    locale=locale,
                    title=card.clan.title,
                    clan_status=_clan_status_label(card.clan.status, locale=locale),
                    role=_role_label(card.clan.role, locale=locale),
                    joined_at=_fmt_dt(card.clan.joined_at),
                ),
            )
        else:
            lines.append(self._bundle.format(_KEY_PLAYER_CARD_NO_CLAN, locale=locale))

        if card.forest_active_run is not None:
            lines.append(
                self._bundle.format(
                    _KEY_PLAYER_CARD_FOREST_ACTIVE,
                    locale=locale,
                    run_id=card.forest_active_run.run_id,
                    started_at=_fmt_dt(card.forest_active_run.started_at),
                    ends_at=_fmt_dt(card.forest_active_run.ends_at),
                ),
            )
        else:
            lines.append(self._bundle.format(_KEY_PLAYER_CARD_NO_FOREST, locale=locale))

        if s.anticheat_ban_until is not None:
            lines.append(
                self._bundle.format(
                    _KEY_PLAYER_CARD_ANTICHEAT,
                    locale=locale,
                    until=_fmt_dt(s.anticheat_ban_until),
                ),
            )
        else:
            lines.append(
                self._bundle.format(_KEY_PLAYER_CARD_NO_ANTICHEAT, locale=locale),
            )

        return "\n".join(lines)


__all__ = [
    "FindPlayerPresenter",
    "GetPlayerCardPresenter",
]
