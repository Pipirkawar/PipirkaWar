"""Презентер `/enchant`-handler-а (Спринт 3.4-D, ГДД §2.8).

Тонкий слой между use-case-ом `EnchantItem` и Telegram-handler-ом.
Не делает I/O, не зависит от инфраструктуры — берёт `Item` (из репо или
`ItemView`-DTO `GetInventory`-use-case-а), `Scroll`-VO и `EnchantmentConfig`
из `IBalanceConfig`, на выход даёт строку для `message.answer(...)` плюс
`InlineKeyboardMarkup` с кнопками «Подтвердить» / «Отмена» для confirm-flow.

i18n идёт через `IMessageBundle` (handler никогда не клеит строки сам);
все ключи — `enchant-*` в `locales/{ru,en}.ftl`. Для скролла переиспользуются
ключи `inventory-scroll-display-*` / `inventory-scroll-category-*` (одна и
та же сущность — нет смысла плодить копии). Для `+N`-суффикса —
`enchant_suffix(...)`-helper из `bot.presenters.inventory` (та же история).

`callback_data` инлайн-кнопок confirm/cancel — отдельный free-form helper
(`enchant_callback_data` / `parse_enchant_callback_data`) рядом с презентером:
формат `enc:<action>:<item_id>:<scroll_id>` (где `scroll_id` сам содержит `:`,
поэтому парсим через `split(":", maxsplit=3)`). Префикс короткий («enc»
вместо «enchant») — чтобы вместе с `item_id` (~30 символов) и `scroll_id`
(~21 символов) уложиться в 64-байтовый лимит Telegram callback_data.

Идемпотентность: handler-у достаточно `callback_query.id` (Telegram-ный
короткий id длиной ~13 символов — гарантированно стабилен и уникален
на одно нажатие); презентер про idempotency-ключ ничего не знает —
он только показывает результат и `enchant-idempotent`-fallback при
повторном клике.
"""

from __future__ import annotations

from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.inventory import EnchantAttemptResult, ItemView
from pipirik_wars.bot.presenters.inventory import enchant_suffix
from pipirik_wars.domain.balance.config import EnchantmentConfig, EnchantmentTier
from pipirik_wars.domain.enchantment import Scroll
from pipirik_wars.domain.inventory import (
    BlessedEnchantOutcome,
    RegularEnchantOutcome,
)

_ENCHANT_CALLBACK_PREFIX: Final[str] = "enc"

EnchantCallbackAction = Literal["confirm", "cancel"]
_VALID_ACTIONS: Final[frozenset[EnchantCallbackAction]] = frozenset({"confirm", "cancel"})

_KEY_GROUP: Final[MessageKey] = MessageKey("enchant-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("enchant-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("enchant-not-registered")
_KEY_USAGE: Final[MessageKey] = MessageKey("enchant-usage")
_KEY_WARNING_REGULAR: Final[MessageKey] = MessageKey("enchant-warning-regular")
_KEY_WARNING_BLESSED: Final[MessageKey] = MessageKey("enchant-warning-blessed")
_KEY_BUTTON_CONFIRM: Final[MessageKey] = MessageKey("enchant-button-confirm")
_KEY_BUTTON_CANCEL: Final[MessageKey] = MessageKey("enchant-button-cancel")
_KEY_SUCCESS: Final[MessageKey] = MessageKey("enchant-success")
_KEY_NO_EFFECT: Final[MessageKey] = MessageKey("enchant-no-effect")
_KEY_DROP: Final[MessageKey] = MessageKey("enchant-drop")
_KEY_DESTROY: Final[MessageKey] = MessageKey("enchant-destroy")
_KEY_CANCELLED: Final[MessageKey] = MessageKey("enchant-cancelled")
_KEY_IDEMPOTENT: Final[MessageKey] = MessageKey("enchant-idempotent")
_KEY_ERROR_WRONG_CATEGORY: Final[MessageKey] = MessageKey("enchant-error-wrong-category")
_KEY_ERROR_ITEM_NOT_FOUND: Final[MessageKey] = MessageKey("enchant-error-item-not-found")
_KEY_ERROR_SCROLL_NOT_FOUND: Final[MessageKey] = MessageKey("enchant-error-scroll-not-found")
_KEY_ERROR_OUT_OF_STOCK: Final[MessageKey] = MessageKey("enchant-error-out-of-stock")
_KEY_ERROR_BAD_ARGS: Final[MessageKey] = MessageKey("enchant-error-bad-args")
_KEY_TOAST_CONFIRMED: Final[MessageKey] = MessageKey("enchant-toast-confirmed")
_KEY_TOAST_CANCELLED: Final[MessageKey] = MessageKey("enchant-toast-cancelled")
_KEY_TOAST_ALREADY_PROCESSED: Final[MessageKey] = MessageKey("enchant-toast-already-processed")
_KEY_TOAST_ERROR: Final[MessageKey] = MessageKey("enchant-toast-error")
_KEY_SCROLL_REGULAR: Final[MessageKey] = MessageKey("inventory-scroll-display-regular")
_KEY_SCROLL_BLESSED: Final[MessageKey] = MessageKey("inventory-scroll-display-blessed")


def enchant_callback_data(
    *,
    action: EnchantCallbackAction,
    item_id: str,
    scroll_id: str,
) -> str:
    """Сериализовать `callback_data` confirm/cancel-кнопок заточки.

    Формат: `enc:<action>:<item_id>:<scroll_id>`. `scroll_id` сам содержит
    `:` (например, `weapon_scroll:regular`), но это безопасно, потому что
    обратный парсер использует `split(":", maxsplit=3)` — первые три части
    жёстко фиксированы (префикс / action / item_id), остальное — `scroll_id`.

    Проверки:
    - `action` ∈ `{confirm, cancel}` — чтобы handler не диспатчил мусор;
    - `item_id` непустой и без `:` (иначе сломается парсинг);
    - итоговая длина ≤ 64 байт — лимит Telegram callback_data.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown enchant callback action: {action!r}")
    if not item_id:
        raise ValueError("item_id must be non-empty")
    if ":" in item_id:
        raise ValueError(f"item_id must not contain ':' (got {item_id!r})")
    if not scroll_id:
        raise ValueError("scroll_id must be non-empty")
    payload = f"{_ENCHANT_CALLBACK_PREFIX}:{action}:{item_id}:{scroll_id}"
    if len(payload.encode("utf-8")) > 64:
        raise ValueError(
            f"callback_data exceeds 64-byte Telegram limit: {payload!r} "
            f"({len(payload.encode('utf-8'))} bytes)"
        )
    return payload


def parse_enchant_callback_data(data: str) -> tuple[EnchantCallbackAction, str, str]:
    """Распарсить `callback_data` заточки; на любой мусор — `ValueError`.

    Возвращает кортеж `(action, item_id, scroll_id)`.
    """
    parts = data.split(":", maxsplit=3)
    if len(parts) != 4 or parts[0] != _ENCHANT_CALLBACK_PREFIX:
        raise ValueError(
            f"enchant callback_data must be 'enc:<action>:<item_id>:<scroll_id>', got {data!r}"
        )
    _, action_raw, item_id, scroll_id = parts
    if action_raw == "confirm":
        action: EnchantCallbackAction = "confirm"
    elif action_raw == "cancel":
        action = "cancel"
    else:
        raise ValueError(f"unknown enchant action: {action_raw!r}")
    if not item_id:
        raise ValueError(f"item_id must be non-empty in enchant callback_data {data!r}")
    if not scroll_id:
        raise ValueError(f"scroll_id must be non-empty in enchant callback_data {data!r}")
    return action, item_id, scroll_id


def is_enchant_callback(data: str | None) -> bool:
    """Filter helper — это callback заточки?

    Используется handler-ом через `F.data.startswith(...)`-фильтр, чтобы
    не пересекаться с другими callback-ами (`caravan:`, `inv:` и т.д.).
    """
    if data is None:
        return False
    return data.startswith(f"{_ENCHANT_CALLBACK_PREFIX}:")


def tier_for_level(config: EnchantmentConfig, level: int) -> EnchantmentTier:
    """Найти тир, диапазон которого `[from_level, to_level)` покрывает `level`.

    `EnchantmentConfig._validate_tiers_cover_range` гарантирует, что тиры
    покрывают `[0, max_level]` без дыр и пересечений, поэтому ровно один
    тир матчит каждый валидный уровень. На уровне `>= max_level` — тир
    с верхним диапазоном (последний).

    `RuntimeError` при пустом `tiers` (теоретически невозможно — `Field(min_length=1)`,
    но защита для mypy/runtime).
    """
    for tier in config.tiers:
        if tier.from_level <= level < tier.to_level:
            return tier
    # Уровень >= max_level — берём последний тир (уровень за верхней границей —
    # граничный случай для UI; use-case-ом такой level не должен прийти, так
    # как нельзя точить уже-максимальный предмет).
    if config.tiers:
        return config.tiers[-1]
    raise RuntimeError("EnchantmentConfig.tiers must not be empty")


def _scroll_category_label_key(category_value: str) -> MessageKey:
    """Ключ для локализованного имени категории скролла (повтор `inventory.py`)."""
    if category_value.endswith("_scroll"):
        category_value = category_value[: -len("_scroll")]
    return MessageKey(f"inventory-scroll-category-{category_value}")


class EnchantPresenter:
    """Локализованный рендер ответов `/enchant`-handler-а через `IMessageBundle`.

    Использует префикс ключей `enchant-*` (плюс заимствует
    `inventory-scroll-display-*` / `inventory-scroll-category-*` для имени
    скролла — одна и та же сущность в обеих карточках).
    """

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- Где можно вызывать `/enchant` ---

    def group(self, *, locale: Locale) -> str:
        """Команда вызвана в групповом чате — инструкция «открой ЛС»."""
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        """Команда вызвана не в групповом и не в приватном (channel и т.п.)."""
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        """Игрок не нажимал /start — нет записи в `players`."""
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def usage(self, *, locale: Locale) -> str:
        """`/enchant` без аргументов или с одним — показываем usage."""
        return self._bundle.format(_KEY_USAGE, locale=locale)

    # --- Warning-карточка (перед confirm-кнопкой) ---

    def warning(
        self,
        *,
        item: ItemView,
        scroll: Scroll,
        config: EnchantmentConfig,
        locale: Locale,
    ) -> str:
        """Карточка-предупреждение: предмет, свиток, тир, возможные исходы.

        Шаблон отличается для regular/blessed (разный набор исходов и
        последняя строка про «не уничтожает»).
        """
        tier = tier_for_level(config, item.enchant_level)
        item_display = f"{item.display_name}{enchant_suffix(item.enchant_level)}"
        scroll_display = self._render_scroll_display(scroll, locale=locale)
        tier_label = self._bundle.format(
            MessageKey(f"enchant-{tier.description_key}"),
            locale=locale,
        )
        key = _KEY_WARNING_BLESSED if scroll.blessed else _KEY_WARNING_REGULAR
        return self._bundle.format(
            key,
            locale=locale,
            item_display=item_display,
            scroll_display=scroll_display,
            tier_label=tier_label,
            tier_emoji=tier.emoji,
        )

    def keyboard_confirm(
        self,
        *,
        item_id: str,
        scroll_id: str,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """Inline-клавиатура «Подтвердить» / «Отмена» под warning-карточкой."""
        confirm_label = self._bundle.format(_KEY_BUTTON_CONFIRM, locale=locale)
        cancel_label = self._bundle.format(_KEY_BUTTON_CANCEL, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=confirm_label,
                        callback_data=enchant_callback_data(
                            action="confirm",
                            item_id=item_id,
                            scroll_id=scroll_id,
                        ),
                    ),
                    InlineKeyboardButton(
                        text=cancel_label,
                        callback_data=enchant_callback_data(
                            action="cancel",
                            item_id=item_id,
                            scroll_id=scroll_id,
                        ),
                    ),
                ],
            ],
        )

    # --- Result-карточки (после confirm-кнопки) ---

    def result(
        self,
        *,
        result: EnchantAttemptResult,
        item_display_name: str,
        locale: Locale,
    ) -> str:
        """Карточка результата заточки.

        `idempotent` → `enchant-idempotent`. Иначе — выбор по `outcome`:
        `success_*` / `no_effect` / `drop_*` / `destroy`.

        `item_display_name` — голое имя предмета (без `+N`); суффикс с
        новым уровнем формируется здесь, т.к. в шаблоне `enchant-success`
        и `enchant-drop` участвуют оба уровня (`old_level` → `new_level`).
        """
        if result.idempotent:
            return self._bundle.format(_KEY_IDEMPOTENT, locale=locale)

        outcome = result.outcome
        new_display = f"{item_display_name}{enchant_suffix(result.new_level)}"

        if outcome is RegularEnchantOutcome.DESTROY:
            return self._bundle.format(
                _KEY_DESTROY,
                locale=locale,
                item_display=item_display_name,
            )

        if outcome in (
            RegularEnchantOutcome.SUCCESS,
            BlessedEnchantOutcome.SUCCESS_1,
            BlessedEnchantOutcome.SUCCESS_2,
        ):
            return self._bundle.format(
                _KEY_SUCCESS,
                locale=locale,
                item_display=new_display,
                old_level=result.old_level,
                new_level=result.new_level,
            )

        if outcome in (RegularEnchantOutcome.NO_EFFECT, BlessedEnchantOutcome.NO_EFFECT):
            return self._bundle.format(
                _KEY_NO_EFFECT,
                locale=locale,
                item_display=new_display,
                old_level=result.old_level,
            )

        # Падения (`DROP`, `DROP_1`, `DROP_2`).
        return self._bundle.format(
            _KEY_DROP,
            locale=locale,
            item_display=new_display,
            old_level=result.old_level,
            new_level=result.new_level,
        )

    def cancelled(self, *, locale: Locale) -> str:
        """Игрок нажал «Отмена» — заточка не выполнена."""
        return self._bundle.format(_KEY_CANCELLED, locale=locale)

    def idempotent(self, *, locale: Locale) -> str:
        """Сообщение «уже обработано» — fallback на повторный клик confirm."""
        return self._bundle.format(_KEY_IDEMPOTENT, locale=locale)

    # --- Сообщения об ошибках ---

    def error_wrong_category(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ERROR_WRONG_CATEGORY, locale=locale)

    def error_item_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ERROR_ITEM_NOT_FOUND, locale=locale)

    def error_scroll_not_found(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ERROR_SCROLL_NOT_FOUND, locale=locale)

    def error_out_of_stock(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ERROR_OUT_OF_STOCK, locale=locale)

    def error_bad_args(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ERROR_BAD_ARGS, locale=locale)

    # --- Тосты для callback-ответов (≤ 200 символов) ---

    def toast_confirmed(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_CONFIRMED, locale=locale)

    def toast_cancelled(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_CANCELLED, locale=locale)

    def toast_already_processed(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_ALREADY_PROCESSED, locale=locale)

    def toast_error(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_TOAST_ERROR, locale=locale)

    # --- Внутренние рендереры ---

    def _render_scroll_display(self, scroll: Scroll, *, locale: Locale) -> str:
        category_label = self._bundle.format(
            _scroll_category_label_key(scroll.category.value),
            locale=locale,
        )
        return self._bundle.format(
            _KEY_SCROLL_BLESSED if scroll.blessed else _KEY_SCROLL_REGULAR,
            locale=locale,
            category_label=category_label,
        )


__all__ = [
    "EnchantCallbackAction",
    "EnchantPresenter",
    "enchant_callback_data",
    "is_enchant_callback",
    "parse_enchant_callback_data",
    "tier_for_level",
]
