"""Презентер `/refund_lot` (Спринт 4.1-E, E.13, ГДД §12.6.6).

Локализует ответы handler-а `/refund_lot <lot_id> <reason>` — двухфазной
admin-команды «принудительно вернуть лот в крипто-пул» (super-admin +
TOTP-confirm). Без I/O, без обращения к БД.

Фаза 1 (handler `/refund_lot <lot_id> <reason>`) вызывает
`RequestAdminConfirm` и отвечает админу:

* `usage` — некорректный синтаксис команды;
* `not_authorized` — `IsAdminFilter` пропустил, но `RequestAdminConfirm`
  поднял `AuthorizationError` (например, админ деактивирован);
* `totp_not_configured` — у админа нет `totp_secret` (см. `/admin_setup_totp`);
* `bad_lot_id` — `lot_id` не парсится в `int > 0`;
* `no_reason` — `reason`-аргумент пустой;
* `confirm_issued` — успешный запрос подтверждения (выдан токен).

Фаза 2 (dispatcher `dispatch_refund_lot`, `/confirm <token> <code>`)
вызывает `RefundLot.execute(...)` и отвечает админу:

* `success` — лот возвращён в пул;
* `already_refunded` — лот уже был в статусе `REFUNDED` (no-op);
* `not_found` — лот не существует;
* `bad_transition` — лот в статусе `CLAIMED` (`PrizeLotStatusTransitionError`),
  возврат через `RefundLot` запрещён доменом.

Формат сумм — `int` в native-единицах валюты (см. `Currency.STARS` /
`TON_NANO` / `USDT_DECIMAL`); конвертация в человекочитаемые TON/USDT
делается на стороне читателя (admin) — мы не хотим терять точность в UI.
"""

from __future__ import annotations

from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

_KEY_USAGE: Final[MessageKey] = MessageKey("admin-refund-lot-usage")
_KEY_NOT_AUTHORIZED: Final[MessageKey] = MessageKey("admin-refund-lot-not-authorized")
_KEY_TOTP_NOT_CONFIGURED: Final[MessageKey] = MessageKey(
    "admin-refund-lot-totp-not-configured",
)
_KEY_BAD_LOT_ID: Final[MessageKey] = MessageKey("admin-refund-lot-bad-lot-id")
_KEY_NO_REASON: Final[MessageKey] = MessageKey("admin-refund-lot-no-reason")
_KEY_CONFIRM_ISSUED: Final[MessageKey] = MessageKey("admin-refund-lot-confirm-issued")
_KEY_SUCCESS: Final[MessageKey] = MessageKey("admin-refund-lot-success")
_KEY_ALREADY_REFUNDED: Final[MessageKey] = MessageKey("admin-refund-lot-already-refunded")
_KEY_NOT_FOUND: Final[MessageKey] = MessageKey("admin-refund-lot-not-found")
_KEY_BAD_TRANSITION: Final[MessageKey] = MessageKey("admin-refund-lot-bad-transition")


class RefundLotPresenter:
    """Локализованные ответы `/refund_lot` (фаза 1 + фаза 2)."""

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # ── Фаза 1 (handle_refund_lot) ───────────────────────────────────

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_USAGE, locale=locale)

    def not_authorized(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_AUTHORIZED, locale=locale)

    def totp_not_configured(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOTP_NOT_CONFIGURED, locale=locale)

    def bad_lot_id(self, *, locale: Locale, value: str) -> str:
        return self._bundle.format(_KEY_BAD_LOT_ID, locale=locale, value=value)

    def no_reason(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NO_REASON, locale=locale)

    def confirm_issued(self, *, locale: Locale, token: str, ttl_seconds: int) -> str:
        return self._bundle.format(
            _KEY_CONFIRM_ISSUED,
            locale=locale,
            token=token,
            ttl_seconds=ttl_seconds,
        )

    # ── Фаза 2 (dispatch_refund_lot) ─────────────────────────────────

    def success(
        self,
        *,
        locale: Locale,
        lot_id: int,
        currency: str,
        amount_native: int,
        pool_after_native: int,
    ) -> str:
        return self._bundle.format(
            _KEY_SUCCESS,
            locale=locale,
            lot_id=str(lot_id),
            currency=currency,
            amount=str(amount_native),
            pool_after=str(pool_after_native),
        )

    def already_refunded(
        self,
        *,
        locale: Locale,
        lot_id: int,
        pool_after_native: int,
    ) -> str:
        return self._bundle.format(
            _KEY_ALREADY_REFUNDED,
            locale=locale,
            lot_id=str(lot_id),
            pool_after=str(pool_after_native),
        )

    def not_found(self, *, locale: Locale, lot_id: int) -> str:
        return self._bundle.format(
            _KEY_NOT_FOUND,
            locale=locale,
            lot_id=str(lot_id),
        )

    def bad_transition(
        self,
        *,
        locale: Locale,
        lot_id: int,
        current_status: str,
    ) -> str:
        return self._bundle.format(
            _KEY_BAD_TRANSITION,
            locale=locale,
            lot_id=str(lot_id),
            status=current_status,
        )


__all__ = ["RefundLotPresenter"]
