"""Презентеры команд экономики админ-интерфейса (Спринт 2.5-C).

`/grant_length`, `/grant_thickness`, `/balance_get`, `/balance_set` —
форматирование локализованных ответов через `IMessageBundle`. Никакого
I/O.
"""

from __future__ import annotations

import json
from typing import Any, Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey


def _render_value(value: Any) -> str:
    """Сериализовать `raw_value` для пользователя."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# ── /grant_length ────────────────────────────────────────────────────────────

_KEY_GL_USAGE: Final[MessageKey] = MessageKey("admin-grant-length-usage")
_KEY_GL_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-grant-length-not-authorized")
_KEY_GL_TOTP_NOT_CONFIGURED: Final[MessageKey] = MessageKey(
    "admin-grant-length-totp-not-configured",
)
_KEY_GL_BAD_ID: Final[MessageKey] = MessageKey("admin-grant-length-bad-id")
_KEY_GL_BAD_DELTA: Final[MessageKey] = MessageKey("admin-grant-length-bad-delta")
_KEY_GL_NO_REASON: Final[MessageKey] = MessageKey("admin-grant-length-no-reason")
_KEY_GL_NOT_FOUND: Final[MessageKey] = MessageKey("admin-grant-length-not-found")
_KEY_GL_BLOCKED: Final[MessageKey] = MessageKey("admin-grant-length-blocked")
_KEY_GL_CONFIRM_ISSUED: Final[MessageKey] = MessageKey("admin-grant-length-confirm-issued")
_KEY_GL_SUCCESS: Final[MessageKey] = MessageKey("admin-grant-length-success")
_KEY_GL_SUCCESS_CLAMPED: Final[MessageKey] = MessageKey("admin-grant-length-success-clamped")
_KEY_GL_SOFT_BAN: Final[MessageKey] = MessageKey("admin-grant-length-soft-ban")


class GrantLengthPresenter:
    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GL_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GL_NOT_AUTHORIZED, locale=locale)

    def totp_not_configured(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GL_TOTP_NOT_CONFIGURED, locale=locale)

    def bad_id(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_GL_BAD_ID, locale=locale, value=value)

    def bad_delta(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_GL_BAD_DELTA, locale=locale, value=value)

    def no_reason(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GL_NO_REASON, locale=locale)

    def not_found(self, *, locale: Locale, tg_id: int) -> str:
        return self._bundle.format(_KEY_GL_NOT_FOUND, locale=locale, tg_id=str(tg_id))

    def blocked(self, *, locale: Locale, tg_id: int, reason: str) -> str:
        return self._bundle.format(
            _KEY_GL_BLOCKED,
            locale=locale,
            tg_id=str(tg_id),
            reason=reason,
        )

    def confirm_issued(self, *, locale: Locale, token: str, ttl_seconds: int) -> str:
        return self._bundle.format(
            _KEY_GL_CONFIRM_ISSUED,
            locale=locale,
            token=token,
            ttl_seconds=str(ttl_seconds),
        )

    def success(
        self,
        *,
        locale: Locale,
        tg_id: int,
        applied_delta_cm: int,
        new_length_cm: int,
    ) -> str:
        return self._bundle.format(
            _KEY_GL_SUCCESS,
            locale=locale,
            tg_id=str(tg_id),
            delta=str(applied_delta_cm),
            new_length_cm=str(new_length_cm),
        )

    def success_clamped(
        self,
        *,
        locale: Locale,
        tg_id: int,
        requested_delta_cm: int,
        applied_delta_cm: int,
        new_length_cm: int,
    ) -> str:
        return self._bundle.format(
            _KEY_GL_SUCCESS_CLAMPED,
            locale=locale,
            tg_id=str(tg_id),
            requested=str(requested_delta_cm),
            applied=str(applied_delta_cm),
            new_length_cm=str(new_length_cm),
        )

    def soft_ban(self, *, locale: Locale, tg_id: int) -> str:
        return self._bundle.format(_KEY_GL_SOFT_BAN, locale=locale, tg_id=str(tg_id))


# ── /grant_thickness ─────────────────────────────────────────────────────────

_KEY_GT_USAGE: Final[MessageKey] = MessageKey("admin-grant-thickness-usage")
_KEY_GT_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-grant-thickness-not-authorized")
_KEY_GT_TOTP_NOT_CONFIGURED: Final[MessageKey] = MessageKey(
    "admin-grant-thickness-totp-not-configured",
)
_KEY_GT_BAD_ID: Final[MessageKey] = MessageKey("admin-grant-thickness-bad-id")
_KEY_GT_BAD_LEVEL: Final[MessageKey] = MessageKey("admin-grant-thickness-bad-level")
_KEY_GT_NO_REASON: Final[MessageKey] = MessageKey("admin-grant-thickness-no-reason")
_KEY_GT_NOT_FOUND: Final[MessageKey] = MessageKey("admin-grant-thickness-not-found")
_KEY_GT_BLOCKED: Final[MessageKey] = MessageKey("admin-grant-thickness-blocked")
_KEY_GT_LEVEL_INVALID: Final[MessageKey] = MessageKey("admin-grant-thickness-level-invalid")
_KEY_GT_CONFIRM_ISSUED: Final[MessageKey] = MessageKey("admin-grant-thickness-confirm-issued")
_KEY_GT_SUCCESS: Final[MessageKey] = MessageKey("admin-grant-thickness-success")
_KEY_GT_ALREADY_AT_LEVEL: Final[MessageKey] = MessageKey(
    "admin-grant-thickness-already-at-level",
)


class GrantThicknessPresenter:
    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GT_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GT_NOT_AUTHORIZED, locale=locale)

    def totp_not_configured(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GT_TOTP_NOT_CONFIGURED, locale=locale)

    def bad_id(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_GT_BAD_ID, locale=locale, value=value)

    def bad_level(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_GT_BAD_LEVEL, locale=locale, value=value)

    def no_reason(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GT_NO_REASON, locale=locale)

    def not_found(self, *, locale: Locale, tg_id: int) -> str:
        return self._bundle.format(_KEY_GT_NOT_FOUND, locale=locale, tg_id=str(tg_id))

    def blocked(self, *, locale: Locale, tg_id: int, reason: str) -> str:
        return self._bundle.format(
            _KEY_GT_BLOCKED,
            locale=locale,
            tg_id=str(tg_id),
            reason=reason,
        )

    def level_invalid(
        self,
        *,
        locale: Locale,
        level: int,
        max_level: int,
        reason_code: str,
    ) -> str:
        return self._bundle.format(
            _KEY_GT_LEVEL_INVALID,
            locale=locale,
            level=str(level),
            max_level=str(max_level),
            reason_code=reason_code,
        )

    def confirm_issued(self, *, locale: Locale, token: str, ttl_seconds: int) -> str:
        return self._bundle.format(
            _KEY_GT_CONFIRM_ISSUED,
            locale=locale,
            token=token,
            ttl_seconds=str(ttl_seconds),
        )

    def success(
        self,
        *,
        locale: Locale,
        tg_id: int,
        previous_level: int,
        new_level: int,
    ) -> str:
        return self._bundle.format(
            _KEY_GT_SUCCESS,
            locale=locale,
            tg_id=str(tg_id),
            previous_level=str(previous_level),
            new_level=str(new_level),
        )

    def already_at_level(self, *, locale: Locale, tg_id: int, level: int) -> str:
        return self._bundle.format(
            _KEY_GT_ALREADY_AT_LEVEL,
            locale=locale,
            tg_id=str(tg_id),
            level=str(level),
        )


# ── /balance_get ─────────────────────────────────────────────────────────────

_KEY_BG_USAGE: Final[MessageKey] = MessageKey("admin-balance-get-usage")
_KEY_BG_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-balance-get-not-authorized")
_KEY_BG_KEY_NOT_FOUND: Final[MessageKey] = MessageKey("admin-balance-get-key-not-found")
_KEY_BG_RESULT: Final[MessageKey] = MessageKey("admin-balance-get-result")


class GetBalanceValuePresenter:
    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_BG_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_BG_NOT_AUTHORIZED, locale=locale)

    def key_not_found(self, *, locale: Locale, key: str, segment: str, reason: str) -> str:
        return self._bundle.format(
            _KEY_BG_KEY_NOT_FOUND,
            locale=locale,
            path=key,
            segment=segment,
            reason=reason,
        )

    def result(self, *, locale: Locale, key: str, value: Any, version: int) -> str:
        return self._bundle.format(
            _KEY_BG_RESULT,
            locale=locale,
            path=key,
            value=_render_value(value),
            version=str(version),
        )


# ── /balance_set ─────────────────────────────────────────────────────────────

_KEY_BS_USAGE: Final[MessageKey] = MessageKey("admin-balance-set-usage")
_KEY_BS_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-balance-set-not-authorized")
_KEY_BS_TOTP_NOT_CONFIGURED: Final[MessageKey] = MessageKey(
    "admin-balance-set-totp-not-configured",
)
_KEY_BS_NO_REASON: Final[MessageKey] = MessageKey("admin-balance-set-no-reason")
_KEY_BS_BAD_VALUE: Final[MessageKey] = MessageKey("admin-balance-set-bad-value")
_KEY_BS_KEY_NOT_FOUND: Final[MessageKey] = MessageKey("admin-balance-set-key-not-found")
_KEY_BS_VALIDATION_ERROR: Final[MessageKey] = MessageKey(
    "admin-balance-set-validation-error",
)
_KEY_BS_CONFIRM_ISSUED: Final[MessageKey] = MessageKey("admin-balance-set-confirm-issued")
_KEY_BS_SUCCESS: Final[MessageKey] = MessageKey("admin-balance-set-success")
_KEY_BS_ALREADY_AT_VALUE: Final[MessageKey] = MessageKey(
    "admin-balance-set-already-at-value",
)


class SetBalanceValuePresenter:
    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_BS_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_BS_NOT_AUTHORIZED, locale=locale)

    def totp_not_configured(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_BS_TOTP_NOT_CONFIGURED, locale=locale)

    def no_reason(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_BS_NO_REASON, locale=locale)

    def bad_value(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_BS_BAD_VALUE, locale=locale, value=value)

    def key_not_found(self, *, locale: Locale, key: str, segment: str, reason: str) -> str:
        return self._bundle.format(
            _KEY_BS_KEY_NOT_FOUND,
            locale=locale,
            path=key,
            segment=segment,
            reason=reason,
        )

    def validation_error(self, *, locale: Locale, key: str, error: str) -> str:
        return self._bundle.format(
            _KEY_BS_VALIDATION_ERROR,
            locale=locale,
            path=key,
            error=error,
        )

    def confirm_issued(self, *, locale: Locale, token: str, ttl_seconds: int) -> str:
        return self._bundle.format(
            _KEY_BS_CONFIRM_ISSUED,
            locale=locale,
            token=token,
            ttl_seconds=str(ttl_seconds),
        )

    def success(
        self,
        *,
        locale: Locale,
        key: str,
        previous_value: Any,
        new_value: Any,
        new_version: int,
    ) -> str:
        return self._bundle.format(
            _KEY_BS_SUCCESS,
            locale=locale,
            path=key,
            previous=_render_value(previous_value),
            new=_render_value(new_value),
            version=str(new_version),
        )

    def already_at_value(self, *, locale: Locale, key: str, value: Any) -> str:
        return self._bundle.format(
            _KEY_BS_ALREADY_AT_VALUE,
            locale=locale,
            path=key,
            value=_render_value(value),
        )


# ── общий /confirm: idempotency replay ──────────────────────────────────────

_KEY_IDEMPOTENCY_REPLAY: Final[MessageKey] = MessageKey("admin-idempotency-replay")


class IdempotencyReplayPresenter:
    """Универсальное сообщение «эта команда уже выполнялась»."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def replay(self, *, locale: Locale, command_kind: str) -> str:
        return self._bundle.format(
            _KEY_IDEMPOTENCY_REPLAY,
            locale=locale,
            command_kind=command_kind,
        )


__all__ = [
    "GetBalanceValuePresenter",
    "GrantLengthPresenter",
    "GrantThicknessPresenter",
    "IdempotencyReplayPresenter",
    "SetBalanceValuePresenter",
]
