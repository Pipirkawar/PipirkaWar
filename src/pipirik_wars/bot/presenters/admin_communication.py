"""Презентеры команды `/announce` админ-интерфейса (Спринт 2.5-D.4).

Локализуют ответы handler-а (фаза 1: usage / not-authorized /
confirm-issued) и фоновой рассылки (фаза 2: progress-start /
progress-final). Никакого I/O — только формат + `IMessageBundle`.
"""

from __future__ import annotations

from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

_KEY_USAGE: Final[MessageKey] = MessageKey("admin-announce-usage")
_KEY_NON_PRIVATE: Final[MessageKey] = MessageKey("admin-announce-non-private")
_KEY_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-announce-not-authorized")
_KEY_TOTP_NOT_CONFIGURED: Final[MessageKey] = MessageKey(
    "admin-announce-totp-not-configured",
)
_KEY_BAD_LOCALE: Final[MessageKey] = MessageKey("admin-announce-bad-locale")
_KEY_EMPTY_MESSAGE: Final[MessageKey] = MessageKey("admin-announce-empty-message")
_KEY_TOO_LONG: Final[MessageKey] = MessageKey("admin-announce-too-long")
_KEY_CONFIRM_ISSUED: Final[MessageKey] = MessageKey("admin-announce-confirm-issued")
_KEY_PROGRESS_START: Final[MessageKey] = MessageKey("admin-announce-progress-start")
_KEY_PROGRESS_FINAL: Final[MessageKey] = MessageKey("admin-announce-progress-final")
_KEY_PROGRESS_FAILED: Final[MessageKey] = MessageKey("admin-announce-progress-failed")


class AnnouncePresenter:
    """Локализованные ответы `/announce`-flow-а."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_USAGE, locale=locale)

    def non_private(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NON_PRIVATE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_AUTHORIZED, locale=locale)

    def totp_not_configured(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOTP_NOT_CONFIGURED, locale=locale)

    def bad_locale(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_BAD_LOCALE, locale=locale, value=value)

    def empty_message(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_EMPTY_MESSAGE, locale=locale)

    def too_long(self, *, locale: Locale, length: int, max_length: int) -> str:
        return self._bundle.format(
            _KEY_TOO_LONG,
            locale=locale,
            length=length,
            max_length=max_length,
        )

    def confirm_issued(
        self,
        *,
        locale: Locale,
        token: str,
        ttl_seconds: int,
        recipient_count: int,
        locale_filter: str,
    ) -> str:
        return self._bundle.format(
            _KEY_CONFIRM_ISSUED,
            locale=locale,
            token=token,
            ttl_seconds=ttl_seconds,
            recipient_count=recipient_count,
            locale_filter=locale_filter,
        )

    def progress_start(
        self,
        *,
        locale: Locale,
        recipient_count: int,
        locale_filter: str,
    ) -> str:
        return self._bundle.format(
            _KEY_PROGRESS_START,
            locale=locale,
            recipient_count=recipient_count,
            locale_filter=locale_filter,
        )

    def progress_final(
        self,
        *,
        locale: Locale,
        recipient_count: int,
        sent_count: int,
        failed_count: int,
        blocked_count: int,
    ) -> str:
        return self._bundle.format(
            _KEY_PROGRESS_FINAL,
            locale=locale,
            recipient_count=recipient_count,
            sent_count=sent_count,
            failed_count=failed_count,
            blocked_count=blocked_count,
        )

    def progress_failed(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_PROGRESS_FAILED, locale=locale)


__all__ = ["AnnouncePresenter"]
