"""Презентер `/admin_setup_totp` (Спринт 2.5-D.6, ГДД §18.6.5).

Локализует все UX-ответы команды self-service-выдачи TOTP-секрета.
Тексты — RU/EN, ключи `admin-setup-totp-*` в `locales/{ru,en}.ftl`.
Сам секрет и `otpauth://`-URI handler не отдаёт в чат целиком (их
видит только сервер в `structlog`-логах с явным маркером); пользователь
получает короткое подтверждение «настроено, см. логи» и инструкции.

Никаких I/O — только формат-операции через `IMessageBundle`.
"""

from __future__ import annotations

from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

_KEY_USAGE: Final[MessageKey] = MessageKey("admin-setup-totp-usage")
_KEY_NON_PRIVATE: Final[MessageKey] = MessageKey("admin-setup-totp-non-private")
_KEY_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-setup-totp-not-authorized")
_KEY_PASSWORD_NOT_CONFIGURED: Final[MessageKey] = MessageKey(
    "admin-setup-totp-password-not-configured",
)
_KEY_PASSWORD_INVALID: Final[MessageKey] = MessageKey("admin-setup-totp-password-invalid")
_KEY_ALREADY_CONFIGURED: Final[MessageKey] = MessageKey("admin-setup-totp-already-configured")
_KEY_SUCCESS: Final[MessageKey] = MessageKey("admin-setup-totp-success")


class SetupAdminTotpPresenter:
    """Локализованные ответы `/admin_setup_totp`."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_USAGE, locale=locale)

    def non_private(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NON_PRIVATE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_AUTHORIZED, locale=locale)

    def password_not_configured(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_PASSWORD_NOT_CONFIGURED, locale=locale)

    def password_invalid(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_PASSWORD_INVALID, locale=locale)

    def already_configured(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ALREADY_CONFIGURED, locale=locale)

    def success(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_SUCCESS, locale=locale)


__all__ = ["SetupAdminTotpPresenter"]
