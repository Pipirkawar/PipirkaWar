"""Презентеры `/freeze_payouts` + `/unfreeze_payouts` (Спринт 4.1-E, E.14, ГДД §12.6.6).

Локализуют ответы handler-ов двухфазных admin-команд «(раз)заморозить
крипто-выплаты глобально» (super-admin + TOTP-confirm). Без I/O, без
обращения к БД.

Фаза 1 (handler-ы `/freeze_payouts <reason>` / `/unfreeze_payouts`) вызывает
`RequestAdminConfirm` и отвечает админу:

* `usage` (только freeze) — некорректный синтаксис команды;
* `not_authorized` — `IsAdminFilter` пропустил, но `RequestAdminConfirm`
  поднял `AuthorizationError` (например, админ деактивирован);
* `totp_not_configured` — у админа нет `totp_secret` (см. `/admin_setup_totp`);
* `no_reason` (только freeze) — `reason`-аргумент пустой;
* `confirm_issued` — успешный запрос подтверждения (выдан токен).

Фаза 2 (dispatcher-ы `dispatch_freeze_payouts` / `dispatch_unfreeze_payouts`,
`/confirm <token> <code>`) вызывает соответствующий use-case и отвечает админу:

* `success` — выплаты (раз)заморожены;
* `already_frozen` / `already_unfrozen` — состояние не менялось (idempotent
  no-op: тот же admin + та же причина для freeze; уже unfrozen для unfreeze).

Use-case-ы `FreezePayouts` / `UnfreezePayouts` (см.
`application/monetization/freeze_payouts.py`) не возвращают доменных
ошибок кроме `AuthorizationError` (RBAC, мапится на `not_authorized`).
"""

from __future__ import annotations

from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

_KEY_FREEZE_USAGE: Final[MessageKey] = MessageKey("admin-freeze-payouts-usage")
_KEY_FREEZE_NOT_AUTHORIZED: Final[MessageKey] = MessageKey(
    "admin-freeze-payouts-not-authorized",
)
_KEY_FREEZE_TOTP_NOT_CONFIGURED: Final[MessageKey] = MessageKey(
    "admin-freeze-payouts-totp-not-configured",
)
_KEY_FREEZE_NO_REASON: Final[MessageKey] = MessageKey("admin-freeze-payouts-no-reason")
_KEY_FREEZE_CONFIRM_ISSUED: Final[MessageKey] = MessageKey(
    "admin-freeze-payouts-confirm-issued",
)
_KEY_FREEZE_SUCCESS: Final[MessageKey] = MessageKey("admin-freeze-payouts-success")
_KEY_FREEZE_ALREADY_FROZEN: Final[MessageKey] = MessageKey(
    "admin-freeze-payouts-already-frozen",
)

_KEY_UNFREEZE_NOT_AUTHORIZED: Final[MessageKey] = MessageKey(
    "admin-unfreeze-payouts-not-authorized",
)
_KEY_UNFREEZE_TOTP_NOT_CONFIGURED: Final[MessageKey] = MessageKey(
    "admin-unfreeze-payouts-totp-not-configured",
)
_KEY_UNFREEZE_CONFIRM_ISSUED: Final[MessageKey] = MessageKey(
    "admin-unfreeze-payouts-confirm-issued",
)
_KEY_UNFREEZE_SUCCESS: Final[MessageKey] = MessageKey("admin-unfreeze-payouts-success")
_KEY_UNFREEZE_ALREADY_UNFROZEN: Final[MessageKey] = MessageKey(
    "admin-unfreeze-payouts-already-unfrozen",
)


class FreezePayoutsPresenter:
    """Локализованные ответы `/freeze_payouts` (фаза 1 + фаза 2)."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # ── Фаза 1 (handle_freeze_payouts) ───────────────────────────────

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_FREEZE_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_FREEZE_NOT_AUTHORIZED, locale=locale)

    def totp_not_configured(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_FREEZE_TOTP_NOT_CONFIGURED, locale=locale)

    def no_reason(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_FREEZE_NO_REASON, locale=locale)

    def confirm_issued(self, *, locale: Locale, token: str, ttl_seconds: int) -> str:
        return self._bundle.format(
            _KEY_FREEZE_CONFIRM_ISSUED,
            locale=locale,
            token=token,
            ttl_seconds=ttl_seconds,
        )

    # ── Фаза 2 (dispatch_freeze_payouts) ─────────────────────────────

    def success(self, *, locale: Locale, reason: str) -> str:
        return self._bundle.format(_KEY_FREEZE_SUCCESS, locale=locale, reason=reason)

    def already_frozen(self, *, locale: Locale, reason: str) -> str:
        return self._bundle.format(
            _KEY_FREEZE_ALREADY_FROZEN,
            locale=locale,
            reason=reason,
        )


class UnfreezePayoutsPresenter:
    """Локализованные ответы `/unfreeze_payouts` (фаза 1 + фаза 2)."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # ── Фаза 1 (handle_unfreeze_payouts) ─────────────────────────────

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_UNFREEZE_NOT_AUTHORIZED, locale=locale)

    def totp_not_configured(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_UNFREEZE_TOTP_NOT_CONFIGURED, locale=locale)

    def confirm_issued(self, *, locale: Locale, token: str, ttl_seconds: int) -> str:
        return self._bundle.format(
            _KEY_UNFREEZE_CONFIRM_ISSUED,
            locale=locale,
            token=token,
            ttl_seconds=ttl_seconds,
        )

    # ── Фаза 2 (dispatch_unfreeze_payouts) ───────────────────────────

    def success(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_UNFREEZE_SUCCESS, locale=locale)

    def already_unfrozen(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_UNFREEZE_ALREADY_UNFROZEN, locale=locale)


__all__ = ["FreezePayoutsPresenter", "UnfreezePayoutsPresenter"]
