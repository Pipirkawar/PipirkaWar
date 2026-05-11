"""Презентер ответов `/link_wallet` и `/link_wallet_confirm` (Спринт 4.1-D).

Команды живут в личке игрока: `/link_wallet` рисует подсказку с
выбором валюты (TON / USDT) + URL-кнопки на популярные TON-Connect-
кошельки + инлайн-кнопку выбора валюты; после клика на валюту
показываются инструкции по подписи кошелька через TON Connect.

Реальный обмен `tonconnect_proof`-ом между кошельком и ботом
выполняет TON-Connect-bridge (подключается на D.10 вместе с
композиционным корнем); D.6 ограничивается:

1. UX-разводкой `/link_wallet` → выбор валюты → инструкции.
2. Командой `/link_wallet_confirm <ton|usdt> <address> <proof>`, которая
   напрямую вызывает `LinkWallet.execute(...)`. Её будет дергать
   TC-bridge на D.10; для D.6 она пригодна как ручная точка входа
   (для теста и интеграционной проверки).

Все строки лежат в `locales/{ru,en}.ftl` (раздел `link-wallet-*`),
поэтому презентер чистый — только склейка через `IMessageBundle`.
"""

from __future__ import annotations

from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.domain.monetization.value_objects import Currency

__all__ = [
    "LinkWalletCallbackData",
    "LinkWalletCurrencyKey",
    "LinkWalletPresenter",
    "link_wallet_callback_data",
    "parse_link_wallet_callback_data",
]

# Telegram callback_data hard-cap = 64 байта. Префикс короткий —
# хватает с большим запасом.
_CALLBACK_PREFIX: Final[str] = "link_wallet"

LinkWalletCurrencyKey = Literal["ton", "usdt"]
_VALID_CURRENCY_KEYS: Final[frozenset[LinkWalletCurrencyKey]] = frozenset({"ton", "usdt"})

# Маппинг между «короткими» CLI-ключами валют и доменным `Currency`.
_CURRENCY_BY_KEY: Final[dict[LinkWalletCurrencyKey, Currency]] = {
    "ton": Currency.TON_NANO,
    "usdt": Currency.USDT_DECIMAL,
}

_KEY_PROMPT_GROUP: Final[MessageKey] = MessageKey("link-wallet-group")
_KEY_PROMPT_OTHER: Final[MessageKey] = MessageKey("link-wallet-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("link-wallet-not-registered")
_KEY_PROMPT: Final[MessageKey] = MessageKey("link-wallet-prompt")
_KEY_BUTTON_TON: Final[MessageKey] = MessageKey("link-wallet-button-ton")
_KEY_BUTTON_USDT: Final[MessageKey] = MessageKey("link-wallet-button-usdt")
_KEY_INSTRUCTIONS_TON: Final[MessageKey] = MessageKey("link-wallet-instructions-ton")
_KEY_INSTRUCTIONS_USDT: Final[MessageKey] = MessageKey("link-wallet-instructions-usdt")
_KEY_INVALID_CALLBACK: Final[MessageKey] = MessageKey("link-wallet-invalid-callback")
_KEY_TOAST_INVALID: Final[MessageKey] = MessageKey("link-wallet-toast-invalid")

_KEY_CONFIRM_GROUP: Final[MessageKey] = MessageKey("link-wallet-confirm-group")
_KEY_CONFIRM_OTHER: Final[MessageKey] = MessageKey("link-wallet-confirm-other")
_KEY_CONFIRM_NOT_REGISTERED: Final[MessageKey] = MessageKey(
    "link-wallet-confirm-not-registered",
)
_KEY_CONFIRM_USAGE: Final[MessageKey] = MessageKey("link-wallet-confirm-usage")
_KEY_CONFIRM_UNSUPPORTED: Final[MessageKey] = MessageKey(
    "link-wallet-confirm-unsupported",
)
_KEY_CONFIRM_INVALID_PROOF: Final[MessageKey] = MessageKey(
    "link-wallet-confirm-invalid-proof",
)
_KEY_CONFIRM_ALREADY_LINKED: Final[MessageKey] = MessageKey(
    "link-wallet-confirm-already-linked",
)
_KEY_CONFIRM_LINKED: Final[MessageKey] = MessageKey("link-wallet-confirm-linked")
_KEY_CONFIRM_RELINKED: Final[MessageKey] = MessageKey("link-wallet-confirm-relinked")


class LinkWalletCallbackData:
    """DTO для `callback_data` инлайн-кнопок `/link_wallet`."""

    __slots__ = ("action", "currency_key")

    def __init__(
        self,
        *,
        action: Literal["select"],
        currency_key: LinkWalletCurrencyKey,
    ) -> None:
        self.action = action
        self.currency_key = currency_key

    def to_currency(self) -> Currency:
        """Расширить short-ключ до доменного `Currency`."""
        return _CURRENCY_BY_KEY[self.currency_key]


def link_wallet_callback_data(currency_key: LinkWalletCurrencyKey) -> str:
    """Сериализовать `callback_data` для инлайн-кнопки выбора валюты.

    Формат: ``"link_wallet:select:<ton|usdt>"`` ≤ 64 байта.
    Бросает `ValueError` для неизвестного ключа.
    """
    if currency_key not in _VALID_CURRENCY_KEYS:
        raise ValueError(f"unknown link_wallet currency key: {currency_key!r}")
    return f"{_CALLBACK_PREFIX}:select:{currency_key}"


def parse_link_wallet_callback_data(raw: str) -> LinkWalletCallbackData:
    """Распарсить `callback_data` инлайн-кнопки `/link_wallet`.

    Бросает `ValueError`, если формат не совпадает (старый клиент,
    форвард чужого сообщения, повреждённые данные).
    """
    parts = raw.split(":")
    expected_parts = 3
    if len(parts) != expected_parts:
        raise ValueError(f"invalid link_wallet callback_data: {raw!r}")
    prefix, action, currency_raw = parts
    if prefix != _CALLBACK_PREFIX:
        raise ValueError(f"invalid link_wallet callback_data prefix: {prefix!r}")
    if action != "select":
        raise ValueError(f"unknown link_wallet action: {action!r}")
    if currency_raw not in _VALID_CURRENCY_KEYS:
        raise ValueError(f"unknown link_wallet currency key: {currency_raw!r}")
    return LinkWalletCallbackData(
        action="select",
        currency_key=_as_currency_key(currency_raw),
    )


def _as_currency_key(raw: str) -> LinkWalletCurrencyKey:
    """Сузить строку до union-типа `LinkWalletCurrencyKey` без `type: ignore`."""
    if raw == "ton":
        return "ton"
    if raw == "usdt":
        return "usdt"
    raise ValueError(f"unknown link_wallet currency key: {raw!r}")


class LinkWalletPresenter:
    """Локализованный рендер ответов `/link_wallet` через `IMessageBundle`."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- `/link_wallet` -----------------------------------------------

    def group(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_PROMPT_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_PROMPT_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def prompt(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_PROMPT, locale=locale)

    def prompt_keyboard(self, *, locale: Locale) -> InlineKeyboardMarkup:
        ton_label = self._bundle.format(_KEY_BUTTON_TON, locale=locale)
        usdt_label = self._bundle.format(_KEY_BUTTON_USDT, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=ton_label,
                        callback_data=link_wallet_callback_data("ton"),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=usdt_label,
                        callback_data=link_wallet_callback_data("usdt"),
                    ),
                ],
            ],
        )

    def instructions(self, *, currency_key: LinkWalletCurrencyKey, locale: Locale) -> str:
        key = _KEY_INSTRUCTIONS_TON if currency_key == "ton" else _KEY_INSTRUCTIONS_USDT
        return self._bundle.format(key, locale=locale)

    def invalid_callback(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_INVALID_CALLBACK, locale=locale)

    def toast_invalid(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_INVALID, locale=locale)

    # --- `/link_wallet_confirm` ---------------------------------------

    def confirm_group(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_CONFIRM_GROUP, locale=locale)

    def confirm_other(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_CONFIRM_OTHER, locale=locale)

    def confirm_not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_CONFIRM_NOT_REGISTERED, locale=locale)

    def confirm_usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_CONFIRM_USAGE, locale=locale)

    def confirm_unsupported_currency(self, *, locale: Locale, code: str) -> str:
        return self._bundle.format(_KEY_CONFIRM_UNSUPPORTED, locale=locale, code=code)

    def confirm_invalid_proof(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_CONFIRM_INVALID_PROOF, locale=locale)

    def confirm_already_linked(
        self,
        *,
        locale: Locale,
        address: str,
        currency_code: str,
    ) -> str:
        return self._bundle.format(
            _KEY_CONFIRM_ALREADY_LINKED,
            locale=locale,
            address=address,
            currency=currency_code,
        )

    def confirm_linked(
        self,
        *,
        locale: Locale,
        address: str,
        currency_code: str,
    ) -> str:
        return self._bundle.format(
            _KEY_CONFIRM_LINKED,
            locale=locale,
            address=address,
            currency=currency_code,
        )

    def confirm_relinked(
        self,
        *,
        locale: Locale,
        address: str,
        currency_code: str,
    ) -> str:
        return self._bundle.format(
            _KEY_CONFIRM_RELINKED,
            locale=locale,
            address=address,
            currency=currency_code,
        )
