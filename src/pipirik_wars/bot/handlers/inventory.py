"""`/inventory` handler + inline-button callbacks (Спринт 3.4-D, ГДД §2.6 + §2.8).

Две точки входа:

1. **`/inventory`** (команда, личка-only): рендерит карточку инвентаря
   через `InventoryPresenter` с inline-клавиатурой кнопок «Заточить»
   (по одной на каждый предмет — `callback_data` `inv:enchant:<item_id>`).
2. **Callback `inv:enchant:<item_id>`** (D.1d): обрабатывает нажатие
   «Заточить» на конкретном предмете:
   - 0 подходящих свитков (по категории + `qty > 0`) → toast
     `inventory-toast-no-scroll` (без редактирования сообщения).
   - 1 подходящий свиток → шлёт **новое** сообщение с warning-карточкой
     `EnchantPresenter`-а + confirm/cancel-клавиатура (далее flow
     обрабатывает `enc:`-callback в `bot/handlers/enchant.py`).
   - 2 подходящих свитка (regular + blessed) → шлёт **новое**
     сообщение с picker-карточкой + клавиатурой выбора скролла +
     кнопкой «Отмена».
3. **Callback `inv:pick:<item_id>:<scroll_id>`** (D.1d): пользователь
   выбрал конкретный свиток в picker-е → handler редактирует
   picker-сообщение **на месте** в warning-карточку + confirm/cancel.
4. **Callback `inv:pickcancel:<item_id>`** (D.1d): пользователь нажал
   «Отмена» в picker-е → handler редактирует picker-сообщение в
   `inventory-picker-cancelled`-текст + toast.

Все ошибки use-case-ов ловит `ErrorHandlerMiddleware`; здесь handler
не пытается обрабатывать `DomainError`-ы вручную (use-case-ы не
вызываются на стадии picker-а — только `GetInventory`-readonly).

Локаль берётся из `LocaleMiddleware.data["locale"]`, `IMessageBundle`
— из workflow-data контейнера (DI выставляется в `bot/main.py`).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.inventory import GetInventory, ItemView, ScrollView
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.enchant import EnchantPresenter
from pipirik_wars.bot.presenters.inventory import (
    InventoryPresenter,
    parse_inventory_callback_data,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.enchantment import Scroll

router = Router(name="inventory")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@router.message(Command("inventory"))
async def handle_inventory(
    message: Message,
    tg_identity: TgIdentity | None,
    get_inventory: GetInventory,
    get_profile: GetProfile,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Отвечает на `/inventory` — рисует карточку инвентаря в ЛС.

    Сначала проверяет регистрацию через `GetProfile` (как `/profile`-handler
    делает это для самой команды) — если игрока нет в `players`, шлём
    `not_registered`-текст без обращения к `GetInventory`. Иначе — читаем
    инвентарь и рендерим карточку (или `empty`-текст для пустого).
    """
    presenter = InventoryPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    profile = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if profile is None:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return

    # `Player.id` объявлен `int | None` (новый-нерегистрированный игрок не имеет id),
    # но `GetProfile.execute(tg_id=...)` всегда возвращает уже-сохранённого игрока,
    # т.е. `profile.player.id is not None` инвариантно. Narrowing для mypy.
    assert profile.player.id is not None
    view = await get_inventory(player_id=profile.player.id)
    if not view.items and not view.scrolls:
        await message.answer(presenter.empty(locale=effective_locale))
        return

    await message.answer(
        presenter.card(view, locale=effective_locale),
        reply_markup=presenter.keyboard(view, locale=effective_locale),
    )


@router.callback_query(F.data.startswith("inv:"))
async def handle_inventory_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    get_inventory: GetInventory,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Маршрутизатор inline-кнопок инвентаря (D.1d).

    Поддерживаемые `action`-ы (см. `parse_inventory_callback_data`):

    - `enchant`  — нажата кнопка «Заточить» в карточке `/inventory`;
      handler сам решает, сколько подходящих свитков у игрока, и
      выбирает между toast `inventory-toast-no-scroll` (0 свитков),
      авто-открытием warning-карточки `EnchantPresenter`-а (1 свиток)
      или picker-карточкой выбора (2 свитка: regular + blessed).
    - `pick`     — нажата кнопка picker-а («обычный» / «благословлённый»);
      handler редактирует picker-сообщение в warning-карточку.
    - `pickcancel` — нажата кнопка «Отмена» в picker-е; handler
      редактирует сообщение в `inventory-picker-cancelled`-текст +
      шлёт toast.

    Любой невалидный `callback_data` или невозможный для текущего
    игрока запрос (нет identity / нет регистрации / предмет не
    найден) → toast `enchant-toast-error` или точечный локализованный
    text (`enchant-error-*`) + лог-warning. Падать молча — нельзя:
    Telegram будет ретраить апдейт.
    """
    if tg_identity is None or callback.data is None:
        return

    inv_presenter = InventoryPresenter(bundle=bundle)
    enc_presenter = EnchantPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        action, item_id, scroll_id = parse_inventory_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "inventory.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            enc_presenter.toast_error(locale=effective_locale),
            show_alert=False,
        )
        return

    if action == "pickcancel":
        await _handle_pickcancel(
            callback=callback,
            inv_presenter=inv_presenter,
            locale=effective_locale,
        )
        return

    profile = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if profile is None:
        await callback.answer(
            inv_presenter.not_registered(locale=effective_locale),
            show_alert=False,
        )
        return
    assert profile.player.id is not None
    inventory = await get_inventory(player_id=profile.player.id)

    item = _find_item(inventory.items, item_id=item_id)
    if item is None:
        await callback.answer(
            enc_presenter.error_item_not_found(locale=effective_locale),
            show_alert=False,
        )
        return

    if action == "pick":
        # Telegram гарантирует, что `scroll_id` непустой —
        # `parse_inventory_callback_data` поднимает `ValueError`,
        # если parts[3] пустой; mypy-narrowing для type-checker-а.
        assert scroll_id is not None
        await _handle_pick(
            callback=callback,
            item=item,
            scroll_id=scroll_id,
            inventory_scrolls=inventory.scrolls,
            balance=balance,
            enc_presenter=enc_presenter,
            locale=effective_locale,
        )
        return

    # action == "enchant" — нажата кнопка «Заточить» в карточке инвентаря.
    await _handle_enchant_button(
        callback=callback,
        item=item,
        inventory_scrolls=inventory.scrolls,
        balance=balance,
        inv_presenter=inv_presenter,
        enc_presenter=enc_presenter,
        locale=effective_locale,
    )


async def _handle_pickcancel(
    *,
    callback: CallbackQuery,
    inv_presenter: InventoryPresenter,
    locale: Locale,
) -> None:
    """Логика «Отмена» picker-а (`inv:pickcancel:<item_id>`).

    Редактирует picker-сообщение в `inventory-picker-cancelled`-текст,
    снимает клавиатуру (best-effort: если Telegram отказал — молчим,
    ack-ом callback-у уже отдали).
    """
    await callback.answer(
        inv_presenter.toast_picker_cancelled(locale=locale),
        show_alert=False,
    )
    msg = callback.message
    if msg is None:
        return
    with contextlib.suppress(Exception):
        await msg.edit_text(text=inv_presenter.picker_cancelled(locale=locale))  # type: ignore[union-attr]


async def _handle_enchant_button(
    *,
    callback: CallbackQuery,
    item: ItemView,
    inventory_scrolls: tuple[ScrollView, ...],
    balance: IBalanceConfig,
    inv_presenter: InventoryPresenter,
    enc_presenter: EnchantPresenter,
    locale: Locale,
) -> None:
    """Логика нажатия «Заточить» в карточке `/inventory`.

    По количеству подходящих свитков:

    - 0 → toast `inventory-toast-no-scroll` (карточка инвентаря не
      меняется — пусть игрок сам решит, что делать).
    - 1 → answer-toast пустой + send новое сообщение с warning-карточкой
      `EnchantPresenter`-а; далее `enc:`-callback-handler в
      `bot/handlers/enchant.py` обрабатывает confirm/cancel.
    - 2 (есть и regular, и blessed) → answer-toast пустой + send новое
      сообщение с picker-карточкой; далее `inv:pick:`-callback редактирует
      picker в warning-карточку.

    «Новое сообщение» (а не edit карточки инвентаря) — намеренно: не
    хочется терять список предметов после одного клика; пусть карточка
    инвентаря живёт отдельно.
    """
    matching = _matching_scrolls_for_item(inventory_scrolls, item=item)
    msg = callback.message

    if not matching:
        await callback.answer(
            inv_presenter.toast_no_scroll(locale=locale),
            show_alert=False,
        )
        return

    if msg is None:
        await callback.answer(
            enc_presenter.toast_error(locale=locale),
            show_alert=False,
        )
        return

    if len(matching) == 1:
        scroll_view = matching[0]
        try:
            scroll = Scroll.from_scroll_id(scroll_view.scroll_id)
        except ValueError:
            await callback.answer(
                enc_presenter.error_bad_args(locale=locale),
                show_alert=False,
            )
            return
        await callback.answer()
        text = enc_presenter.warning(
            item=item,
            scroll=scroll,
            config=balance.get().enchantment,
            locale=locale,
        )
        keyboard = enc_presenter.keyboard_confirm(
            item_id=item.item_id,
            scroll_id=scroll_view.scroll_id,
            locale=locale,
        )
        with contextlib.suppress(Exception):
            await msg.answer(text, reply_markup=keyboard)
        return

    # Два варианта (regular + blessed) — picker.
    await callback.answer()
    picker_text = inv_presenter.picker(item=item, locale=locale)
    picker_kb = inv_presenter.keyboard_picker(item=item, locale=locale)
    with contextlib.suppress(Exception):
        await msg.answer(picker_text, reply_markup=picker_kb)


async def _handle_pick(
    *,
    callback: CallbackQuery,
    item: ItemView,
    scroll_id: str,
    inventory_scrolls: tuple[ScrollView, ...],
    balance: IBalanceConfig,
    enc_presenter: EnchantPresenter,
    locale: Locale,
) -> None:
    """Логика выбора свитка в picker-е (`inv:pick:<item_id>:<scroll_id>`).

    Player выбрал конкретный `scroll_id` (regular или blessed) →
    handler редактирует picker-сообщение **на месте** в
    warning-карточку `EnchantPresenter`-а с confirm/cancel-кнопками.

    Перед редактированием проверяем, что свиток всё ещё в стэке
    игрока (`qty > 0`) и что категория совпадает — между показом
    picker-а и нажатием pick-а игрок мог израсходовать стэк (или
    получить новый предмет другой категории), и handler не должен
    показывать warning по уже-несуществующему свитку.
    """
    if not _has_scroll_in_stock(inventory_scrolls, scroll_id=scroll_id):
        await callback.answer(
            enc_presenter.error_scroll_not_found(locale=locale),
            show_alert=False,
        )
        return
    try:
        scroll = Scroll.from_scroll_id(scroll_id)
    except ValueError:
        await callback.answer(
            enc_presenter.error_bad_args(locale=locale),
            show_alert=False,
        )
        return
    if item.category.name != scroll.category.name:
        await callback.answer(
            enc_presenter.error_wrong_category(locale=locale),
            show_alert=False,
        )
        return

    await callback.answer()
    msg = callback.message
    if msg is None:
        return
    text = enc_presenter.warning(
        item=item,
        scroll=scroll,
        config=balance.get().enchantment,
        locale=locale,
    )
    keyboard = enc_presenter.keyboard_confirm(
        item_id=item.item_id,
        scroll_id=scroll_id,
        locale=locale,
    )
    with contextlib.suppress(Exception):
        await msg.edit_text(text=text, reply_markup=keyboard)  # type: ignore[union-attr]


def _find_item(items: tuple[ItemView, ...], *, item_id: str) -> ItemView | None:
    """Найти `ItemView` по `item_id` или `None` (повтор `enchant.py`)."""
    for item in items:
        if item.item_id == item_id:
            return item
    return None


def _matching_scrolls_for_item(
    scrolls: tuple[ScrollView, ...],
    *,
    item: ItemView,
) -> list[ScrollView]:
    """Свитки в инвентаре, подходящие для заточки данного предмета.

    Свиток подходит, если его категория (без суффикса `_scroll`) ==
    `item.category.value` (например, `weapon_scroll` ↔ `WEAPON`) и
    `qty > 0`. Возвращает список длиной 0, 1 или 2 (regular + blessed).
    """
    expected_category = f"{item.category.value}_scroll"
    return [s for s in scrolls if s.category == expected_category and s.qty > 0]


def _has_scroll_in_stock(
    scrolls: tuple[ScrollView, ...],
    *,
    scroll_id: str,
) -> bool:
    """Проверить, что у игрока в инвентаре есть стэк такого скролла с `qty > 0`."""
    return any(scroll.scroll_id == scroll_id and scroll.qty > 0 for scroll in scrolls)
