"""Презентер `/inventory`-handler-а (Спринт 3.4-D, ГДД §2.6 + §2.8).

Тонкий слой между use-case-ом `GetInventory` и Telegram-handler-ом.
Не делает I/O, не зависит от инфраструктуры — берёт `InventoryView`
(items + scrolls с обогащёнными display-метаданными из каталога) и
`Locale` из middleware-а, на выход даёт строку для `message.answer(...)`
плюс `InlineKeyboardMarkup` с кнопками «Заточить» для D.1d.

i18n идёт через `IMessageBundle` (handler никогда не клеит строки сам);
все ключи — `inventory-*` в `locales/{ru,en}.ftl`.

`callback_data` инлайн-кнопок — отдельный free-form helper
(`inventory_callback_data` / `parse_inventory_callback_data`) рядом с
презентером по тому же паттерну, что у каравана: одна точка истины
для префикса `inv:` и форматов событий. Префикс короткий («inv» вместо
«inventory») — чтобы вместе с длинным `item_id` уложиться в лимит
Telegram callback_data в 64 байта (`item_id` ≤ 64 chars + `inv:enchant:`
≈ 76 байт; чуть тесно, но `item_id` каталога обычно куда короче).
"""

from __future__ import annotations

from typing import Final, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.inventory import InventoryView, ItemView, ScrollView
from pipirik_wars.domain.balance.config import Rarity, Slot

_INVENTORY_CALLBACK_PREFIX: Final[str] = "inv"

InventoryCallbackAction = Literal["enchant", "pick", "pickcancel"]
_VALID_ACTIONS: Final[frozenset[InventoryCallbackAction]] = frozenset(
    {"enchant", "pick", "pickcancel"},
)

_KEY_GROUP: Final[MessageKey] = MessageKey("inventory-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("inventory-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("inventory-not-registered")
_KEY_EMPTY: Final[MessageKey] = MessageKey("inventory-empty")
_KEY_CARD: Final[MessageKey] = MessageKey("inventory-card")
_KEY_SECTION_ITEMS: Final[MessageKey] = MessageKey("inventory-section-items")
_KEY_SECTION_SCROLLS: Final[MessageKey] = MessageKey("inventory-section-scrolls")
_KEY_ITEM_LINE: Final[MessageKey] = MessageKey("inventory-item-line")
_KEY_SCROLL_LINE: Final[MessageKey] = MessageKey("inventory-scroll-line")
_KEY_BUTTON_ENCHANT: Final[MessageKey] = MessageKey("inventory-button-enchant")
_KEY_SCROLL_REGULAR: Final[MessageKey] = MessageKey("inventory-scroll-display-regular")
_KEY_SCROLL_BLESSED: Final[MessageKey] = MessageKey("inventory-scroll-display-blessed")
_KEY_PICKER_CARD: Final[MessageKey] = MessageKey("inventory-picker-card")
_KEY_PICKER_BUTTON_REGULAR: Final[MessageKey] = MessageKey("inventory-picker-button-regular")
_KEY_PICKER_BUTTON_BLESSED: Final[MessageKey] = MessageKey("inventory-picker-button-blessed")
_KEY_PICKER_BUTTON_CANCEL: Final[MessageKey] = MessageKey("inventory-picker-button-cancel")
_KEY_PICKER_CANCELLED: Final[MessageKey] = MessageKey("inventory-picker-cancelled")
_KEY_PICKER_TOAST_CANCELLED: Final[MessageKey] = MessageKey(
    "inventory-picker-toast-cancelled",
)
_KEY_TOAST_NO_SCROLL: Final[MessageKey] = MessageKey("inventory-toast-no-scroll")


def inventory_callback_data(
    *,
    action: InventoryCallbackAction,
    item_id: str,
    scroll_id: str | None = None,
) -> str:
    """Сериализовать `callback_data` инлайн-кнопки инвентаря.

    Форматы:

    - `inv:enchant:<item_id>` — кнопка «Заточить» в карточке инвентаря
      (handler сам определит, сколько подходящих свитков у игрока:
      0/1/2 → toast / автозаточка / picker).
    - `inv:pick:<item_id>:<scroll_id>` — кнопка picker-а («обычный» /
      «благословлённый») когда у игрока есть оба варианта свитка.
    - `inv:pickcancel:<item_id>` — кнопка «Отмена» picker-а (закрывает
      picker-карточку без выбора свитка).

    На запас в лимите 64 байт: `inv:pick:` = 9 байт, `<item_id>` ≤ 24
    байт, `<scroll_id>` ≤ 21 байт (`weapon_scroll:blessed`) — итого
    ≤ 55 байт, влезает с запасом.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"unknown inventory callback action: {action!r}")
    if not item_id:
        raise ValueError("item_id must be non-empty")
    if ":" in item_id:
        raise ValueError(f"item_id must not contain ':' (got {item_id!r})")
    if action == "pick":
        if not scroll_id:
            raise ValueError("scroll_id must be non-empty for action 'pick'")
        payload = f"{_INVENTORY_CALLBACK_PREFIX}:pick:{item_id}:{scroll_id}"
    else:
        if scroll_id is not None:
            raise ValueError(f"scroll_id must be omitted for action {action!r}")
        payload = f"{_INVENTORY_CALLBACK_PREFIX}:{action}:{item_id}"
    if len(payload.encode("utf-8")) > 64:
        raise ValueError(
            f"callback_data exceeds 64-byte Telegram limit: {payload!r} "
            f"({len(payload.encode('utf-8'))} bytes)"
        )
    return payload


def parse_inventory_callback_data(
    data: str,
) -> tuple[InventoryCallbackAction, str, str | None]:
    """Распарсить `callback_data` инвентаря; на любой мусор — `ValueError`.

    Возвращает кортеж `(action, item_id, scroll_id)`. Для действия
    `enchant` `scroll_id` = `None`; для `pick` — непустая строка
    (`scroll_id` сам содержит `:`, поэтому парсим через
    `split(":", maxsplit=3)`).
    """
    parts = data.split(":", maxsplit=3)
    if not parts or parts[0] != _INVENTORY_CALLBACK_PREFIX:
        raise ValueError(
            "inventory callback_data must start with 'inv:', "
            f"got {data!r}",
        )
    if len(parts) < 2:
        raise ValueError(f"inventory callback_data missing action: {data!r}")
    action_raw = parts[1]
    if action_raw == "enchant":
        if len(parts) != 3 or not parts[2]:
            raise ValueError(
                "inventory callback_data must be 'inv:enchant:<item_id>', "
                f"got {data!r}",
            )
        return "enchant", parts[2], None
    if action_raw == "pick":
        if len(parts) != 4 or not parts[2] or not parts[3]:
            raise ValueError(
                "inventory callback_data must be "
                "'inv:pick:<item_id>:<scroll_id>', "
                f"got {data!r}",
            )
        return "pick", parts[2], parts[3]
    if action_raw == "pickcancel":
        if len(parts) != 3 or not parts[2]:
            raise ValueError(
                "inventory callback_data must be 'inv:pickcancel:<item_id>', "
                f"got {data!r}",
            )
        return "pickcancel", parts[2], None
    raise ValueError(f"unknown inventory action: {action_raw!r}")


def is_inventory_callback(data: str | None) -> bool:
    """Filter helper — это callback инвентаря?

    Используется handler-ом через `F.data.startswith(...)`-фильтр, чтобы
    не пересекаться с другими callback-ами (`caravan:`, `boss:` и т.д.).
    """
    if data is None:
        return False
    return data.startswith(f"{_INVENTORY_CALLBACK_PREFIX}:")


def _slot_message_key(slot: Slot) -> MessageKey:
    """Ключ `IMessageBundle` для локализованного имени слота.

    `Slot.RIGHT_HAND = "right_hand"` → `inventory-slot-right-hand`
    (дефис в .ftl-ключе — конвенция Fluent: ASCII-only без `_`).
    """
    return MessageKey(f"inventory-slot-{slot.value.replace('_', '-')}")


def _rarity_message_key(rarity: Rarity) -> MessageKey:
    """Ключ `IMessageBundle` для локализованного имени редкости."""
    return MessageKey(f"inventory-rarity-{rarity.value}")


def _scroll_category_label_key(category_value: str) -> MessageKey:
    """Ключ для локализованного имени категории скролла.

    `ScrollCategory` хранит значения с суффиксом `_scroll`
    (`weapon_scroll`, `armor_scroll`, `jewelry_scroll`); UI-ключи
    — без суффикса (`inventory-scroll-category-weapon` и т.д.).
    """
    if category_value.endswith("_scroll"):
        category_value = category_value[: -len("_scroll")]
    return MessageKey(f"inventory-scroll-category-{category_value}")


def enchant_suffix(enchant_level: int) -> str:
    """Префиксованный с пробелом суффикс «+N», или пусто для `+0`.

    Унесено модуль-уровневой функцией, чтобы D.3-задача (показ `+N` в
    `/profile`-карточке и нотификациях о дропе) могла переиспользовать
    тот же формат и не плодить копии.
    """
    if enchant_level <= 0:
        return ""
    return f" +{enchant_level}"


class InventoryPresenter:
    """Локализованный рендер ответов `/inventory`-handler-а через `IMessageBundle`.

    Использует префикс ключей `inventory-*` (множественное число —
    исторический выбор файла локалей, как у `caravans-*`).
    """

    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    # --- Где можно вызывать `/inventory` ---

    def group(self, *, locale: Locale) -> str:
        """Команда вызвана в групповом чате — инструкция «открой ЛС»."""
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        """Команда вызвана не в групповом и не в приватном (channel и т.п.)."""
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        """Игрок не нажимал /start — нет записи в `players`."""
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    # --- Карточка инвентаря ---

    def empty(self, *, locale: Locale) -> str:
        """Инвентарь пуст — мотивационная подсказка, куда сходить."""
        return self._bundle.format(_KEY_EMPTY, locale=locale)

    def card(self, view: InventoryView, *, locale: Locale) -> str:
        """Полная карточка `/inventory` (ГДД §2.6 + §2.8).

        Структура:
        - заголовок с количествами (`inventory-card`),
        - секция предметов (`inventory-section-items` + строки),
        - секция свитков (`inventory-section-scrolls` + строки).

        Если предметов 0 — секция предметов скрывается (но если
        предметы есть, а свитков 0 — секция свитков всё равно
        скрывается; пустая секция бесполезна для UX).

        Полностью пустой инвентарь рендерится через `empty(...)` —
        handler сам решает, какой метод позвать.
        """
        header = self._bundle.format(
            _KEY_CARD,
            locale=locale,
            items_count=len(view.items),
            scrolls_count=len(view.scrolls),
        )
        sections: list[str] = [header]

        if view.items:
            sections.append(self._bundle.format(_KEY_SECTION_ITEMS, locale=locale))
            for item in view.items:
                sections.append(self._render_item_line(item, locale=locale))

        if view.scrolls:
            sections.append(self._bundle.format(_KEY_SECTION_SCROLLS, locale=locale))
            for scroll in view.scrolls:
                sections.append(self._render_scroll_line(scroll, locale=locale))

        return "\n\n".join(_group_lines(sections))

    def keyboard(self, view: InventoryView, *, locale: Locale) -> InlineKeyboardMarkup | None:
        """Inline-клавиатура карточки инвентаря.

        По одной кнопке `⚒ Заточить` на каждый предмет (callback
        `inv:enchant:<item_id>`). Если предметов нет — клавиатура
        не нужна (возвращает `None`, handler шлёт сообщение без
        `reply_markup`).

        В D.1d handler по этому callback откроет confirm-диалог
        `EnchantPresenter`-а; в D.1b кнопки видны, но нажатие
        ещё не обработано — handler-у этого callback ещё нет.
        """
        if not view.items:
            return None
        button_label = self._bundle.format(_KEY_BUTTON_ENCHANT, locale=locale)
        rows: list[list[InlineKeyboardButton]] = []
        for item in view.items:
            text = f"{button_label} — {item.display_name}{enchant_suffix(item.enchant_level)}"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=text,
                        callback_data=inventory_callback_data(
                            action="enchant",
                            item_id=item.item_id,
                        ),
                    ),
                ],
            )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    # --- Picker свитка (regular vs blessed) для D.1d ---

    def picker(self, *, item: ItemView, locale: Locale) -> str:
        """Текст picker-карточки «выберите свиток для заточки».

        Показывается, когда у игрока есть и обычный, и благословлённый
        свитки нужной категории — handler не может однозначно выбрать
        за игрока, потому что у этих свитков разные исходы (regular
        может уничтожить и сбросить уровень предмета; blessed — нет).
        """
        item_display = f"{item.display_name}{enchant_suffix(item.enchant_level)}"
        return self._bundle.format(
            _KEY_PICKER_CARD,
            locale=locale,
            item_display=item_display,
        )

    def keyboard_picker(
        self,
        *,
        item: ItemView,
        locale: Locale,
    ) -> InlineKeyboardMarkup:
        """Inline-клавиатура picker-а (3 кнопки: обычный / благословлённый / отмена).

        `scroll_id` для каждой кнопки строится из `item.category` —
        категории `ItemCategory` и `ScrollCategory` имеют общие имена
        (`WEAPON` / `ARMOR` / `JEWELRY`), а формат `scroll_id` —
        `<category>_scroll:<regular|blessed>`.
        """
        regular_label = self._bundle.format(_KEY_PICKER_BUTTON_REGULAR, locale=locale)
        blessed_label = self._bundle.format(_KEY_PICKER_BUTTON_BLESSED, locale=locale)
        cancel_label = self._bundle.format(_KEY_PICKER_BUTTON_CANCEL, locale=locale)
        regular_scroll_id = f"{item.category.value}_scroll:regular"
        blessed_scroll_id = f"{item.category.value}_scroll:blessed"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=regular_label,
                        callback_data=inventory_callback_data(
                            action="pick",
                            item_id=item.item_id,
                            scroll_id=regular_scroll_id,
                        ),
                    ),
                    InlineKeyboardButton(
                        text=blessed_label,
                        callback_data=inventory_callback_data(
                            action="pick",
                            item_id=item.item_id,
                            scroll_id=blessed_scroll_id,
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=cancel_label,
                        callback_data=inventory_callback_data(
                            action="pickcancel",
                            item_id=item.item_id,
                        ),
                    ),
                ],
            ],
        )

    def picker_cancelled(self, *, locale: Locale) -> str:
        """Текст в picker-сообщении после нажатия «Отмена»."""
        return self._bundle.format(_KEY_PICKER_CANCELLED, locale=locale)

    # --- Toasts (callback.answer(...)) для D.1d ---

    def toast_no_scroll(self, *, locale: Locale) -> str:
        """Toast «нет подходящих свитков» — нажата `/inventory`-кнопка
        «Заточить» для предмета, к которому игроку нечем."""
        return self._bundle.format(_KEY_TOAST_NO_SCROLL, locale=locale)

    def toast_picker_cancelled(self, *, locale: Locale) -> str:
        """Toast после отмены picker-а."""
        return self._bundle.format(_KEY_PICKER_TOAST_CANCELLED, locale=locale)

    # --- Внутренние рендереры ---

    def _render_item_line(self, item: ItemView, *, locale: Locale) -> str:
        slot_label = self._bundle.format(_slot_message_key(item.slot), locale=locale)
        rarity_label = self._bundle.format(_rarity_message_key(item.rarity), locale=locale)
        return self._bundle.format(
            _KEY_ITEM_LINE,
            locale=locale,
            display_name=item.display_name,
            enchant_suffix=enchant_suffix(item.enchant_level),
            slot_label=slot_label,
            rarity_label=rarity_label,
        )

    def _render_scroll_line(self, scroll: ScrollView, *, locale: Locale) -> str:
        category_label = self._bundle.format(
            _scroll_category_label_key(scroll.category),
            locale=locale,
        )
        scroll_label = self._bundle.format(
            _KEY_SCROLL_BLESSED if scroll.blessed else _KEY_SCROLL_REGULAR,
            locale=locale,
            category_label=category_label,
        )
        return self._bundle.format(
            _KEY_SCROLL_LINE,
            locale=locale,
            scroll_label=scroll_label,
            qty=scroll.qty,
        )


def _group_lines(blocks: list[str]) -> list[str]:
    """Склеивает соседние «section-header + строки» в один блок.

    Внутри одного блока — `\\n` между строками; между блоками —
    `\\n\\n` (двойной перенос). Заголовки секций (`inventory-section-*`)
    выступают разделителями.
    """
    grouped: list[str] = []
    current: list[str] = []
    for block in blocks:
        if block.startswith("📦") or block.startswith("📜"):
            if current:
                grouped.append("\n".join(current))
                current = []
            current.append(block)
        else:
            current.append(block)
    if current:
        grouped.append("\n".join(current))
    return grouped


__all__ = [
    "InventoryCallbackAction",
    "InventoryPresenter",
    "enchant_suffix",
    "inventory_callback_data",
    "is_inventory_callback",
    "parse_inventory_callback_data",
]
