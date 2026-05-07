"""Презентер `/audit` (Спринт 2.5-D.5, ГДД §18.6.4).

Локализует листинг `admin_audit_log`. Один логический ответ —
`render(...)` — собирает заголовок + тело из строк. Без I/O,
форматирование `datetime` локалью-нейтральное (UTC ISO-8601, как и
`/anticheat_history`); русский/английский текст приходит из
`IMessageBundle`-а.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.domain.admin import AdminAuditAction, AdminAuditRecord, AdminAuditSource

_KEY_USAGE: Final[MessageKey] = MessageKey("admin-audit-usage")
_KEY_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-audit-not-authorized")
_KEY_BAD_TG_ID: Final[MessageKey] = MessageKey("admin-audit-bad-tg-id")
_KEY_BAD_LIMIT: Final[MessageKey] = MessageKey("admin-audit-bad-limit")
_KEY_UNKNOWN_ACTION: Final[MessageKey] = MessageKey("admin-audit-unknown-action")
_KEY_TARGET_NOT_FOUND: Final[MessageKey] = MessageKey("admin-audit-target-not-found")
_KEY_EMPTY: Final[MessageKey] = MessageKey("admin-audit-empty")
_KEY_HEADER_ALL: Final[MessageKey] = MessageKey("admin-audit-header-all")
_KEY_HEADER_TARGET: Final[MessageKey] = MessageKey("admin-audit-header-target")
_KEY_FILTER_ACTION_SUFFIX: Final[MessageKey] = MessageKey("admin-audit-filter-action-suffix")
_KEY_ROW: Final[MessageKey] = MessageKey("admin-audit-row")

_DASH = "—"


def _format_iso(ts: datetime) -> str:
    """UTC, без микросекунд, с суффиксом `Z`. Кроссплатформенно для логов."""
    return ts.astimezone(tz=ts.tzinfo).replace(microsecond=0).isoformat()


def _format_source(source: AdminAuditSource) -> str:
    return source.value


class AuditTrailPresenter:
    """Локализованные ответы `/audit`."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_AUTHORIZED, locale=locale)

    def bad_tg_id(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_BAD_TG_ID, locale=locale, value=value)

    def bad_limit(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_BAD_LIMIT, locale=locale, value=value)

    def unknown_action(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_UNKNOWN_ACTION, locale=locale, value=value)

    def target_not_found(self, *, locale: Locale, tg_id: int) -> str:
        return self._bundle.format(_KEY_TARGET_NOT_FOUND, locale=locale, tg_id=str(tg_id))

    def empty(
        self,
        *,
        locale: Locale,
        target_admin_tg_id: int | None,
        action: AdminAuditAction | None,
    ) -> str:
        target = str(target_admin_tg_id) if target_admin_tg_id is not None else _DASH
        action_label = action.value if action is not None else _DASH
        return self._bundle.format(
            _KEY_EMPTY,
            locale=locale,
            target=target,
            action=action_label,
        )

    def render(
        self,
        *,
        locale: Locale,
        target_admin_tg_id: int | None,
        action: AdminAuditAction | None,
        limit: int,
        records: Iterable[AdminAuditRecord],
    ) -> str:
        rows = list(records)
        if target_admin_tg_id is None:
            header = self._bundle.format(
                _KEY_HEADER_ALL,
                locale=locale,
                count=len(rows),
                limit=limit,
            )
        else:
            header = self._bundle.format(
                _KEY_HEADER_TARGET,
                locale=locale,
                count=len(rows),
                limit=limit,
                target_tg_id=str(target_admin_tg_id),
            )
        if action is not None:
            header += " " + self._bundle.format(
                _KEY_FILTER_ACTION_SUFFIX,
                locale=locale,
                action=action.value,
            )
        body_lines = [
            self._bundle.format(
                _KEY_ROW,
                locale=locale,
                **{
                    "id": row.id,
                    "occurred_at": _format_iso(row.occurred_at),
                    "actor_tg_id": str(row.actor_tg_id),
                    "action": row.action.value,
                    "target_kind": row.target_kind,
                    "target_id": row.target_id,
                    "source": _format_source(row.source),
                    "reason": row.reason,
                },
            )
            for row in rows
        ]
        return "\n".join([header, *body_lines])


__all__ = ["AuditTrailPresenter"]
