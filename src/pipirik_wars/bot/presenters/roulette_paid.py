"""Презентер `/roulette_paid`-ветки (Спринт 4.1-A, ГДД §12.5).

Тонкий локализационный фасад над `IMessageBundle` для всех текстов
платной (Telegram Stars) рулетки:

* pre-spin карточка (личка) с двумя inline-кнопками
  `[Купить 1⭐]` / `[Купить 9⭐ × 10]`,
* warning-карточки группового / channel-чата (рулетка только в личке),
* warning-карточки на `not_registered` / `thickness`-gate-фейле,
* invoice payload-сериализация (`paid_roulette:single` /
  `paid_roulette:pack_10`) — handler передаёт это в
  `bot.send_invoice(payload=...)` и читает из
  `successful_payment.invoice_payload`,
* invoice title / description / label per-pack (RU+EN),
* result-карточки `SpinPaidRouletteResult`:
  - SINGLE — один outcome, рендерится как у `/roulette_free` через
    общую `_format_outcome_line(...)` (LENGTH с дельтой, ITEM /
    SCROLL_REGULAR / SCROLL_BLESSED как заглушки до 4.1-C);
  - PACK_10 — агрегированная сводка по `pack10_spins` outcome-ам:
    суммарный `+CM`, разбивка по kind-ам;
* `result_idempotent(...)` — handler не должен звать use-case при
  отказе ретрая, но если всё-таки придёт duplicate-payment-callback
  с тем же `tg_payment_charge_id` — карточка-no-op,
* toast-ы (gate-фейлы, retry, generic-error).

Сериализация `callback_data` (`roulette_paid:<action>`) живёт в этом
же модуле — одна точка истины для префикса. Действия — `buy_single`
(invoice 1 ⭐) и `buy_pack_10` (invoice 9 ⭐).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.monetization import PaidRoulettePack, SpinPaidRouletteResult
from pipirik_wars.domain.roulette import RouletteOutcome, RouletteOutcomeKind

_ROULETTE_PAID_CALLBACK_PREFIX: Final[str] = "roulette_paid"
_INVOICE_PAYLOAD_PREFIX: Final[str] = "paid_roulette"

# Telegram Stars currency code в `bot.send_invoice(currency=...)`.
TG_STARS_CURRENCY: Final[str] = "XTR"

RoulettePaidCallbackAction = Literal["buy_single", "buy_pack_10"]
_VALID_CALLBACK_ACTIONS: Final[frozenset[RoulettePaidCallbackAction]] = frozenset(
    {"buy_single", "buy_pack_10"}
)

_KEY_GROUP: Final[MessageKey] = MessageKey("roulette-paid-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("roulette-paid-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("roulette-paid-not-registered")
_KEY_REQUIREMENT_THICKNESS: Final[MessageKey] = MessageKey("roulette-paid-requirement-thickness")
_KEY_PROMPT: Final[MessageKey] = MessageKey("roulette-paid-prompt")
_KEY_BUTTON_BUY_SINGLE: Final[MessageKey] = MessageKey("roulette-paid-button-buy-single")
_KEY_BUTTON_BUY_PACK10: Final[MessageKey] = MessageKey("roulette-paid-button-buy-pack-10")
_KEY_INVOICE_TITLE_SINGLE: Final[MessageKey] = MessageKey("roulette-paid-invoice-title-single")
_KEY_INVOICE_TITLE_PACK10: Final[MessageKey] = MessageKey("roulette-paid-invoice-title-pack-10")
_KEY_INVOICE_DESCRIPTION_SINGLE: Final[MessageKey] = MessageKey(
    "roulette-paid-invoice-description-single"
)
_KEY_INVOICE_DESCRIPTION_PACK10: Final[MessageKey] = MessageKey(
    "roulette-paid-invoice-description-pack-10"
)
_KEY_INVOICE_LABEL_SINGLE: Final[MessageKey] = MessageKey("roulette-paid-invoice-label-single")
_KEY_INVOICE_LABEL_PACK10: Final[MessageKey] = MessageKey("roulette-paid-invoice-label-pack-10")
_KEY_RESULT_SINGLE_LENGTH: Final[MessageKey] = MessageKey("roulette-paid-result-single-length")
_KEY_RESULT_SINGLE_ITEM: Final[MessageKey] = MessageKey("roulette-paid-result-single-item")
_KEY_RESULT_SINGLE_SCROLL_REGULAR: Final[MessageKey] = MessageKey(
    "roulette-paid-result-single-scroll-regular"
)
_KEY_RESULT_SINGLE_SCROLL_BLESSED: Final[MessageKey] = MessageKey(
    "roulette-paid-result-single-scroll-blessed"
)
_KEY_RESULT_SINGLE_CRYPTO_LOT: Final[MessageKey] = MessageKey(
    "roulette-paid-result-single-crypto-lot"
)
_KEY_RESULT_PACK10_HEADER: Final[MessageKey] = MessageKey("roulette-paid-result-pack-10")
_KEY_RESULT_IDEMPOTENT: Final[MessageKey] = MessageKey("roulette-paid-result-idempotent")
_KEY_TOAST_THICKNESS: Final[MessageKey] = MessageKey("roulette-paid-toast-thickness-gate")
_KEY_TOAST_NOT_REGISTERED: Final[MessageKey] = MessageKey("roulette-paid-toast-not-registered")
_KEY_TOAST_PAYMENT_OK: Final[MessageKey] = MessageKey("roulette-paid-toast-payment-ok")
_KEY_TOAST_ALREADY_PROCESSED: Final[MessageKey] = MessageKey(
    "roulette-paid-toast-already-processed"
)
_KEY_TOAST_ERROR: Final[MessageKey] = MessageKey("roulette-paid-toast-error")


@dataclass(frozen=True, slots=True)
class RoulettePaidCallbackData:
    """Распаршенный `callback_data` инлайн-кнопки платной рулетки.

    Формат: `roulette_paid:<action>`. На 4.1-A `action` —
    `buy_single` (отправить invoice на 1 ⭐) либо `buy_pack_10`
    (отправить invoice на 9 ⭐).
    """

    action: RoulettePaidCallbackAction


def roulette_paid_callback_data(*, action: RoulettePaidCallbackAction) -> str:
    """Сериализовать `callback_data` инлайн-кнопки платной рулетки.

    Формат: `roulette_paid:<action>` (≤ 64 байт; самая длинная форма
    `roulette_paid:buy_pack_10` — 25 байт). Бросает `ValueError` на
    неизвестный action.
    """
    if action not in _VALID_CALLBACK_ACTIONS:
        raise ValueError(f"unknown roulette_paid callback action: {action!r}")
    return f"{_ROULETTE_PAID_CALLBACK_PREFIX}:{action}"


def parse_roulette_paid_callback_data(data: str) -> RoulettePaidCallbackData:
    """Распарсить `callback_data` платной рулетки. На любой мусор — `ValueError`."""
    parts = data.split(":")
    if len(parts) != 2 or parts[0] != _ROULETTE_PAID_CALLBACK_PREFIX:
        raise ValueError(
            f"roulette_paid callback_data must be 'roulette_paid:<action>', got {data!r}",
        )
    _, action_raw = parts
    if action_raw == "buy_single":
        return RoulettePaidCallbackData(action="buy_single")
    if action_raw == "buy_pack_10":
        return RoulettePaidCallbackData(action="buy_pack_10")
    raise ValueError(f"unknown roulette_paid action: {action_raw!r}")


def is_roulette_paid_callback(data: str | None) -> bool:
    """Filter helper — это callback платной рулетки?

    Используется handler-ом через `F.data.startswith(...)`-фильтр,
    чтобы не пересекаться с `roulette_free:` / `boss:` / `caravan:` /
    `enc:` / etc.
    """
    if data is None:
        return False
    return data.startswith(f"{_ROULETTE_PAID_CALLBACK_PREFIX}:")


def invoice_payload_for(pack: PaidRoulettePack) -> str:
    """Сериализовать `invoice_payload` для `bot.send_invoice(payload=...)`.

    Формат: `paid_roulette:<pack-value>` (либо `paid_roulette:single`,
    либо `paid_roulette:pack_10`). Telegram возвращает этот payload
    обратно в `pre_checkout_query.invoice_payload` и в
    `successful_payment.invoice_payload` — handler парсит его, чтобы
    выяснить, какой именно pack оплачен.

    Длина ≤ 128 байт (Telegram limit для invoice_payload), реально
    ≤ 22 байт.
    """
    return f"{_INVOICE_PAYLOAD_PREFIX}:{pack.value}"


def parse_invoice_payload(payload: str) -> PaidRoulettePack:
    """Распарсить `invoice_payload` обратно в `PaidRoulettePack`.

    Бросает `ValueError` на любой формат отличный от
    `paid_roulette:<pack-value>` или на неизвестный `pack-value`.
    Это критично с точки зрения антифрода — handler не должен
    проводить платёж по непонятному payload-у.
    """
    parts = payload.split(":")
    if len(parts) != 2 or parts[0] != _INVOICE_PAYLOAD_PREFIX:
        raise ValueError(
            f"invoice_payload must be 'paid_roulette:<pack>', got {payload!r}",
        )
    _, pack_raw = parts
    for pack in PaidRoulettePack:
        if pack.value == pack_raw:
            return pack
    raise ValueError(f"unknown PaidRoulettePack value in invoice_payload: {pack_raw!r}")


class RoulettePaidPresenter:
    """Локализованный рендер ответов `/roulette_paid`-handler-а через `IMessageBundle`.

    Префикс ключей — `roulette-paid-*`. Все методы — pure: ничего не
    пишут, не зовут I/O, только зовут `bundle.format(...)`.
    """

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- Команда `/roulette_paid` — где её пускать / парсинг ---

    def group(self, *, locale: Locale) -> str:
        """Команда вызвана в групповом чате — направляем в личку."""
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        """Команда вызвана в канале / без identity — директива «только в личке»."""
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        """Игрок не нажимал /start — `PlayerNotFoundError`."""
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    # --- Команда `/roulette_paid` — gate-warning-карточка в личке ---

    def requirement_thickness(
        self,
        *,
        required: int,
        actual: int,
        locale: Locale,
    ) -> str:
        """Толщина < `min_thickness_level` (ГДД §12.5.1; default = 1)."""
        return self._bundle.format(
            _KEY_REQUIREMENT_THICKNESS,
            locale=locale,
            required=required,
            actual=actual,
        )

    # --- Pre-spin карточка с двумя inline-кнопками (single / pack_10) ---

    def prompt(
        self,
        *,
        single_cost_stars: int,
        pack10_cost_stars: int,
        pack10_spins: int,
        locale: Locale,
    ) -> str:
        """Карточка-приглашение: цены single и 10-pack-а в Stars."""
        return self._bundle.format(
            _KEY_PROMPT,
            locale=locale,
            single_cost_stars=single_cost_stars,
            pack10_cost_stars=pack10_cost_stars,
            pack10_spins=pack10_spins,
        )

    def pack_keyboard(
        self,
        *,
        single_cost_stars: int,
        pack10_cost_stars: int,
        pack10_spins: int,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """Inline-клавиатура pre-spin карточки: две кнопки `[Купить 1⭐]` / `[Купить 9⭐ × 10]`.

        Каждая кнопка несёт `callback_data="roulette_paid:buy_single"` или
        `"roulette_paid:buy_pack_10"`. Handler по callback-у читает текущие
        цены из `IBalanceConfig.get().roulette.paid` (race не страшен —
        invoice со старой ценой просто не пройдёт через `pre_checkout_query`,
        если сумма перестанет матчить конфиг).
        """
        button_single = InlineKeyboardButton(
            text=self._bundle.format(
                _KEY_BUTTON_BUY_SINGLE,
                locale=locale,
                cost_stars=single_cost_stars,
            ),
            callback_data=roulette_paid_callback_data(action="buy_single"),
        )
        button_pack10 = InlineKeyboardButton(
            text=self._bundle.format(
                _KEY_BUTTON_BUY_PACK10,
                locale=locale,
                cost_stars=pack10_cost_stars,
                pack10_spins=pack10_spins,
            ),
            callback_data=roulette_paid_callback_data(action="buy_pack_10"),
        )
        return InlineKeyboardMarkup(inline_keyboard=[[button_single], [button_pack10]])

    # --- Invoice (Telegram Stars) — title / description / label / prices ---

    def invoice_title(self, *, pack: PaidRoulettePack, locale: Locale) -> str:
        """Title invoice-а (показывается в Telegram-карточке оплаты)."""
        if pack is PaidRoulettePack.SINGLE:
            return self._bundle.format(_KEY_INVOICE_TITLE_SINGLE, locale=locale)
        return self._bundle.format(_KEY_INVOICE_TITLE_PACK10, locale=locale)

    def invoice_description(
        self,
        *,
        pack: PaidRoulettePack,
        cost_stars: int,
        pack10_spins: int,
        locale: Locale,
    ) -> str:
        """Description invoice-а (вторая строка в Telegram-карточке оплаты)."""
        if pack is PaidRoulettePack.SINGLE:
            return self._bundle.format(
                _KEY_INVOICE_DESCRIPTION_SINGLE,
                locale=locale,
                cost_stars=cost_stars,
            )
        return self._bundle.format(
            _KEY_INVOICE_DESCRIPTION_PACK10,
            locale=locale,
            cost_stars=cost_stars,
            pack10_spins=pack10_spins,
        )

    def invoice_prices(
        self,
        *,
        pack: PaidRoulettePack,
        cost_stars: int,
        pack10_spins: int,
        locale: Locale,
    ) -> list[LabeledPrice]:
        """`prices` invoice-а — одна `LabeledPrice` с label-ом и amount=cost_stars.

        Telegram Stars currency (`XTR`) принимает `amount` в целых
        Stars (не в копейках, как в фиате) — поэтому `LabeledPrice.amount
        == cost_stars`.
        """
        if pack is PaidRoulettePack.SINGLE:
            label = self._bundle.format(_KEY_INVOICE_LABEL_SINGLE, locale=locale)
        else:
            label = self._bundle.format(
                _KEY_INVOICE_LABEL_PACK10,
                locale=locale,
                pack10_spins=pack10_spins,
            )
        return [LabeledPrice(label=label, amount=cost_stars)]

    # --- Result-карточки `SpinPaidRouletteResult` ---

    def render_result(
        self,
        *,
        result: SpinPaidRouletteResult,
        locale: Locale,
    ) -> str:
        """Главный диспетчер: `SpinPaidRouletteResult` → текст result-карточки.

        Идемпотентный retry (`result.idempotent=True`) → `result_idempotent`.
        Иначе — `result_single(...)` (1 outcome) либо
        `result_pack10(...)` (агрегация по `pack10_spins` outcome-ам).
        """
        if result.idempotent:
            return self.result_idempotent(locale=locale)
        if result.pack is PaidRoulettePack.SINGLE:
            (outcome,) = result.outcomes
            return self.result_single(
                outcome=outcome,
                spent_stars=result.spent_stars,
                locale=locale,
            )
        return self.result_pack10(
            outcomes=result.outcomes,
            spent_stars=result.spent_stars,
            locale=locale,
        )

    def result_single(
        self,
        *,
        outcome: RouletteOutcome,
        spent_stars: int,
        locale: Locale,
    ) -> str:
        """Один outcome (SINGLE-pack) — карточка по `outcome.kind`."""
        if outcome.kind is RouletteOutcomeKind.LENGTH:
            assert outcome.length_cm is not None
            return self._bundle.format(
                _KEY_RESULT_SINGLE_LENGTH,
                locale=locale,
                length_cm=outcome.length_cm,
                spent_stars=spent_stars,
            )
        if outcome.kind is RouletteOutcomeKind.ITEM:
            return self._bundle.format(
                _KEY_RESULT_SINGLE_ITEM,
                locale=locale,
                spent_stars=spent_stars,
            )
        if outcome.kind is RouletteOutcomeKind.SCROLL_REGULAR:
            return self._bundle.format(
                _KEY_RESULT_SINGLE_SCROLL_REGULAR,
                locale=locale,
                spent_stars=spent_stars,
            )
        if outcome.kind is RouletteOutcomeKind.SCROLL_BLESSED:
            return self._bundle.format(
                _KEY_RESULT_SINGLE_SCROLL_BLESSED,
                locale=locale,
                spent_stars=spent_stars,
            )
        if outcome.kind is RouletteOutcomeKind.CRYPTO_LOT:
            return self._bundle.format(
                _KEY_RESULT_SINGLE_CRYPTO_LOT,
                locale=locale,
                spent_stars=spent_stars,
            )
        # mypy исчерпал union — недостижимо, но guard для будущих kind-ов.
        raise ValueError(f"unknown RouletteOutcomeKind: {outcome.kind!r}")

    def result_pack10(
        self,
        *,
        outcomes: tuple[RouletteOutcome, ...],
        spent_stars: int,
        locale: Locale,
    ) -> str:
        """`pack10_spins` outcome-ов — агрегированная сводка.

        Считает `total_length_cm` (сумма см по всем LENGTH-исходам) и
        счётчики по каждому kind-у. Локаль-ключ `roulette-paid-result-pack-10`
        получает все 6 счётчиков как именованные параметры (Fluent-плюрал
        формы решат, какие строки показать).
        """
        counts = Counter(o.kind for o in outcomes)
        total_length_cm = sum((o.length_cm or 0) for o in outcomes)
        return self._bundle.format(
            _KEY_RESULT_PACK10_HEADER,
            locale=locale,
            spent_stars=spent_stars,
            n_spins=len(outcomes),
            total_length_cm=total_length_cm,
            n_length=counts.get(RouletteOutcomeKind.LENGTH, 0),
            n_item=counts.get(RouletteOutcomeKind.ITEM, 0),
            n_scroll_regular=counts.get(RouletteOutcomeKind.SCROLL_REGULAR, 0),
            n_scroll_blessed=counts.get(RouletteOutcomeKind.SCROLL_BLESSED, 0),
            n_crypto_lot=counts.get(RouletteOutcomeKind.CRYPTO_LOT, 0),
        )

    def result_idempotent(self, *, locale: Locale) -> str:
        """Идемпотентный retry (повторный `successful_payment` от Telegram)."""
        return self._bundle.format(_KEY_RESULT_IDEMPOTENT, locale=locale)

    # --- Toast-ы (короткие inline-сообщения над callback-кнопкой) ---

    def toast_thickness_gate(
        self,
        *,
        required: int,
        actual: int,
        locale: Locale,
    ) -> str:
        """Toast: толщина < `min_thickness_level` (gate в callback-fire-flow)."""
        return self._bundle.format(
            _KEY_TOAST_THICKNESS,
            locale=locale,
            required=required,
            actual=actual,
        )

    def toast_not_registered(self, *, locale: Locale) -> str:
        """Toast: игрок не зарегистрирован — нажми /start."""
        return self._bundle.format(_KEY_TOAST_NOT_REGISTERED, locale=locale)

    def toast_payment_ok(self, *, locale: Locale) -> str:
        """Toast: платёж успешно проведён, рулетка прокручена."""
        return self._bundle.format(_KEY_TOAST_PAYMENT_OK, locale=locale)

    def toast_already_processed(self, *, locale: Locale) -> str:
        """Toast: повторный `successful_payment` — уже обработано."""
        return self._bundle.format(_KEY_TOAST_ALREADY_PROCESSED, locale=locale)

    def toast_error(self, *, locale: Locale) -> str:
        """Toast: общая ошибка (мусорный callback_data, неизвестная action)."""
        return self._bundle.format(_KEY_TOAST_ERROR, locale=locale)


__all__ = [
    "TG_STARS_CURRENCY",
    "RoulettePaidCallbackAction",
    "RoulettePaidCallbackData",
    "RoulettePaidPresenter",
    "invoice_payload_for",
    "is_roulette_paid_callback",
    "parse_invoice_payload",
    "parse_roulette_paid_callback_data",
    "roulette_paid_callback_data",
]
