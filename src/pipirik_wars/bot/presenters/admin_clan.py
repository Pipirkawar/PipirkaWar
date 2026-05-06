"""Презентеры команд поддержки кланов (Спринт 2.5-D.1+).

Локализованный рендер ответов `/clan` (read-only карточка клана).
Никакого I/O — только формат + `IMessageBundle.format(...)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from pipirik_wars.application.admin import (
    ClanCard,
    ClanMemberCardInfo,
)
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.domain.clan import ClanMemberRole, ClanStatus
from pipirik_wars.domain.player import PlayerStatus

# ── /clan ────────────────────────────────────────────────────────────────────

_KEY_USAGE: Final[MessageKey] = MessageKey("admin-clan-usage")
_KEY_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-clan-not-authorized")
_KEY_BAD_ID: Final[MessageKey] = MessageKey("admin-clan-bad-id")
_KEY_NOT_FOUND: Final[MessageKey] = MessageKey("admin-clan-not-found")
_KEY_CARD_SUMMARY: Final[MessageKey] = MessageKey("admin-clan-card-summary")
_KEY_CARD_LEADER: Final[MessageKey] = MessageKey("admin-clan-card-leader")
_KEY_CARD_NO_LEADER: Final[MessageKey] = MessageKey("admin-clan-card-no-leader")
_KEY_CARD_MEMBER_ROW: Final[MessageKey] = MessageKey("admin-clan-card-member-row")
_KEY_CARD_NO_MEMBERS: Final[MessageKey] = MessageKey("admin-clan-card-no-members")

_DASH = "—"


def _clan_status_label(status: ClanStatus, *, locale: Locale) -> str:
    if status is ClanStatus.ACTIVE:
        return "active" if locale.code == "en" else "активен"
    return "frozen" if locale.code == "en" else "заморожен"


def _player_status_label(status: PlayerStatus, *, locale: Locale) -> str:
    if status is PlayerStatus.ACTIVE:
        return "active" if locale.code == "en" else "активен"
    return "frozen" if locale.code == "en" else "заморожен"


def _role_label(role: ClanMemberRole, *, locale: Locale) -> str:
    if role is ClanMemberRole.LEADER:
        return "leader" if locale.code == "en" else "лидер"
    return "member" if locale.code == "en" else "участник"


def _fmt_dt(dt: datetime) -> str:
    """ISO-8601 без миллисекунд — формат, понятный и логам, и админу."""
    return dt.replace(microsecond=0).isoformat()


class GetClanCardPresenter:
    """Локализованные ответы `/clan`."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_AUTHORIZED, locale=locale)

    def bad_id(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_BAD_ID, locale=locale, value=value)

    def not_found(self, *, locale: Locale, query: int) -> str:
        return self._bundle.format(_KEY_NOT_FOUND, locale=locale, query=str(query))

    def render(self, *, locale: Locale, card: ClanCard) -> str:
        lines: list[str] = [
            self._bundle.format(
                _KEY_CARD_SUMMARY,
                locale=locale,
                clan_id=card.clan_id,
                chat_id=str(card.chat_id),
                chat_kind=card.chat_kind,
                title=card.title,
                status=_clan_status_label(card.status, locale=locale),
                created_at=_fmt_dt(card.created_at),
                updated_at=_fmt_dt(card.updated_at),
                member_count=card.member_count,
                active_member_count=card.active_member_count,
                total_length_cm=card.total_length_cm,
            ),
        ]
        if card.leader is not None:
            lines.append(self._render_leader(locale=locale, leader=card.leader))
        else:
            lines.append(self._bundle.format(_KEY_CARD_NO_LEADER, locale=locale))

        if card.members:
            lines.extend(self._render_member(locale=locale, member=m) for m in card.members)
        else:
            lines.append(self._bundle.format(_KEY_CARD_NO_MEMBERS, locale=locale))

        return "\n".join(lines)

    def _render_leader(
        self,
        *,
        locale: Locale,
        leader: ClanMemberCardInfo,
    ) -> str:
        s = leader.summary
        return self._bundle.format(
            _KEY_CARD_LEADER,
            locale=locale,
            tg_id=str(s.tg_id),
            username=s.username if s.username is not None else _DASH,
            name=s.name if s.name is not None else _DASH,
            length_cm=s.length_cm,
            joined_at=_fmt_dt(leader.joined_at),
        )

    def _render_member(
        self,
        *,
        locale: Locale,
        member: ClanMemberCardInfo,
    ) -> str:
        s = member.summary
        return self._bundle.format(
            _KEY_CARD_MEMBER_ROW,
            locale=locale,
            tg_id=str(s.tg_id),
            username=s.username if s.username is not None else _DASH,
            name=s.name if s.name is not None else _DASH,
            length_cm=s.length_cm,
            thickness_level=s.thickness_level,
            status=_player_status_label(s.status, locale=locale),
            role=_role_label(member.role, locale=locale),
            joined_at=_fmt_dt(member.joined_at),
        )


__all__ = ["GetClanCardPresenter"]
