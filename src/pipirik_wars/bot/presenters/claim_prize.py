"""Презентер ответов `/claim_prize <lot_id>` (Спринт 4.1-D, D.7).

Команда живёт в личке игрока: `/claim_prize <lot_id>` берёт привязанный
кошелёк по валюте лота и вызывает `ClaimPrize.execute(...)`. По
результату — три основных исхода:

1. ``success`` — выплата прошла, лот в статусе ``CLAIMED``, виден
   ``tx_hash``.
2. ``refund`` — ``actual_fee > fee_buffer``, лот вернулся в пул
   (статус ``REFUNDED``), выплата не состоялась.
3. Ошибочные ветки: ``not-found``, ``already-claimed``, ``not-reserved``,
   ``wallet-not-linked``, ``not-owner``, ``invalid-lot-id``.

Также рендерим inline-кнопку «Забрать приз» с
``callback_data='claim_prize:<lot_id>'`` — её показывают presenter-ы
результата рулетки при выпадении крипто-лота (D.7.c).

Все строки лежат в ``locales/{ru,en}.ftl`` (раздел ``claim-prize-*``),
поэтому презентер чистый — только склейка через `IMessageBundle`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

__all__ = [
    "ClaimPrizeCallbackData",
    "ClaimPrizePresenter",
    "claim_prize_callback_data",
    "parse_claim_prize_callback_data",
]

# Telegram callback_data hard-cap = 64 байта. Префикс короткий —
# хватает с большим запасом (даже под `int` lot_id-ы до 10**52).
_CALLBACK_PREFIX: Final[str] = "claim_prize"
_CALLBACK_MAX_BYTES: Final[int] = 64

_KEY_GROUP: Final[MessageKey] = MessageKey("claim-prize-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("claim-prize-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("claim-prize-not-registered")
_KEY_USAGE: Final[MessageKey] = MessageKey("claim-prize-usage")
_KEY_INVALID_LOT_ID: Final[MessageKey] = MessageKey("claim-prize-invalid-lot-id")
_KEY_PROMPT: Final[MessageKey] = MessageKey("claim-prize-prompt")
_KEY_BUTTON: Final[MessageKey] = MessageKey("claim-prize-button")
_KEY_NOT_FOUND: Final[MessageKey] = MessageKey("claim-prize-not-found")
_KEY_ALREADY_CLAIMED: Final[MessageKey] = MessageKey("claim-prize-already-claimed")
_KEY_NOT_RESERVED: Final[MessageKey] = MessageKey("claim-prize-not-reserved")
_KEY_WALLET_NOT_LINKED: Final[MessageKey] = MessageKey("claim-prize-wallet-not-linked")
_KEY_NOT_OWNER: Final[MessageKey] = MessageKey("claim-prize-not-owner")
_KEY_SUCCESS: Final[MessageKey] = MessageKey("claim-prize-success")
_KEY_REFUND: Final[MessageKey] = MessageKey("claim-prize-refund")
_KEY_INVALID_CALLBACK: Final[MessageKey] = MessageKey("claim-prize-invalid-callback")
_KEY_TOAST_INVALID: Final[MessageKey] = MessageKey("claim-prize-toast-invalid")


@dataclass(frozen=True, slots=True)
class ClaimPrizeCallbackData:
    """DTO для `callback_data` инлайн-кнопок `/claim_prize`."""

    lot_id: int


def claim_prize_callback_data(lot_id: int) -> str:
    """Сериализовать `callback_data` для инлайн-кнопки «Забрать приз».

    Формат: ``"claim_prize:<lot_id>"`` (≤ 64 байта).
    `lot_id` должен быть положительным целым; иначе `ValueError`.
    """
    if lot_id < 1:
        raise ValueError(f"claim_prize lot_id must be >= 1, got {lot_id!r}")
    data = f"{_CALLBACK_PREFIX}:{lot_id}"
    # Telegram-инвариант: callback_data ≤ 64 байта (UTF-8). lot_id из
    # DB-PK на int64 — всегда влезает, но защитимся от случая
    # «передали int за границей» из внутреннего API.
    if len(data.encode("utf-8")) > _CALLBACK_MAX_BYTES:
        raise ValueError(
            f"claim_prize callback_data exceeds {_CALLBACK_MAX_BYTES} bytes: {data!r}",
        )
    return data


def parse_claim_prize_callback_data(raw: str) -> ClaimPrizeCallbackData:
    """Распарсить `callback_data` инлайн-кнопки `/claim_prize`.

    Бросает `ValueError`, если формат не совпадает (старый клиент,
    форвард чужого сообщения, повреждённые данные).
    """
    parts = raw.split(":")
    expected_parts = 2
    if len(parts) != expected_parts:
        raise ValueError(f"invalid claim_prize callback_data: {raw!r}")
    prefix, lot_id_raw = parts
    if prefix != _CALLBACK_PREFIX:
        raise ValueError(f"invalid claim_prize callback_data prefix: {prefix!r}")
    try:
        lot_id = int(lot_id_raw)
    except ValueError as exc:
        raise ValueError(f"invalid claim_prize lot_id: {lot_id_raw!r}") from exc
    if lot_id < 1:
        raise ValueError(f"claim_prize lot_id must be >= 1, got {lot_id!r}")
    return ClaimPrizeCallbackData(lot_id=lot_id)


class ClaimPrizePresenter:
    """Локализованный рендер ответов `/claim_prize` через `IMessageBundle`."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- Чат-гарды ----------------------------------------------------

    def group(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    # --- Парсинг команды ---------------------------------------------

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_USAGE, locale=locale)

    def invalid_lot_id(self, *, locale: Locale, raw: str) -> str:
        return self._bundle.format(_KEY_INVALID_LOT_ID, locale=locale, raw=raw)

    # --- Prompt + inline-кнопка для roulette-result -------------------

    def prompt(
        self,
        *,
        locale: Locale,
        lot_id: int,
        currency_code: str,
        amount_native: int,
    ) -> str:
        return self._bundle.format(
            _KEY_PROMPT,
            locale=locale,
            lot_id=lot_id,
            currency=currency_code,
            amount=amount_native,
        )

    def prompt_keyboard(self, *, locale: Locale, lot_id: int) -> InlineKeyboardMarkup:
        button_label = self._bundle.format(_KEY_BUTTON, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=button_label,
                        callback_data=claim_prize_callback_data(lot_id),
                    ),
                ],
            ],
        )

    # --- Ошибки -------------------------------------------------------

    def not_found(self, *, locale: Locale, lot_id: int) -> str:
        return self._bundle.format(_KEY_NOT_FOUND, locale=locale, lot_id=lot_id)

    def already_claimed(self, *, locale: Locale, lot_id: int) -> str:
        return self._bundle.format(_KEY_ALREADY_CLAIMED, locale=locale, lot_id=lot_id)

    def not_reserved(self, *, locale: Locale, lot_id: int, status: str) -> str:
        return self._bundle.format(
            _KEY_NOT_RESERVED,
            locale=locale,
            lot_id=lot_id,
            status=status,
        )

    def wallet_not_linked(self, *, locale: Locale, currency_code: str) -> str:
        return self._bundle.format(
            _KEY_WALLET_NOT_LINKED,
            locale=locale,
            currency=currency_code,
        )

    def not_owner(self, *, locale: Locale, lot_id: int) -> str:
        return self._bundle.format(_KEY_NOT_OWNER, locale=locale, lot_id=lot_id)

    # --- Финальные исходы --------------------------------------------

    def success(
        self,
        *,
        locale: Locale,
        lot_id: int,
        currency_code: str,
        amount_native: int,
        actual_fee_native: int,
        tx_hash: str,
        recipient_address: str,
    ) -> str:
        return self._bundle.format(
            _KEY_SUCCESS,
            locale=locale,
            lot_id=lot_id,
            currency=currency_code,
            amount=amount_native,
            actual_fee=actual_fee_native,
            tx_hash=tx_hash,
            address=recipient_address,
        )

    def refund(
        self,
        *,
        locale: Locale,
        lot_id: int,
        currency_code: str,
        amount_native: int,
        actual_fee_native: int,
        fee_buffer_native: int,
    ) -> str:
        return self._bundle.format(
            _KEY_REFUND,
            locale=locale,
            lot_id=lot_id,
            currency=currency_code,
            amount=amount_native,
            actual_fee=actual_fee_native,
            fee_buffer=fee_buffer_native,
        )

    # --- Callback-error ----------------------------------------------

    def invalid_callback(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_INVALID_CALLBACK, locale=locale)

    def toast_invalid(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_INVALID, locale=locale)
