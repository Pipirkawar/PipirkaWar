"""`/enchant`-handler + confirm/cancel-callbacks (Спринт 3.4-D, ГДД §2.8).

Три точки входа:

1. **`/enchant <item_id> <scroll_id>`** (команда, личка-only):
   парсит аргументы, валидирует чат / регистрацию / наличие предмета +
   скролла в инвентаре, рендерит warning-карточку через
   `EnchantPresenter.warning(...)` с inline-клавиатурой
   confirm/cancel. На любую ошибку — точечный локализованный ответ
   (предмет/скролл не найден, категория не совпадает, нет в стэке).

2. **Callback `enc:confirm:<item_id>:<scroll_id>`**: открывает ambient
   `IUnitOfWork`, зовёт `EnchantItem` use-case с `idempotency_key`-ом
   формата `f"{tg_user_id}:{message_id}"` (стабилен на одно нажатие
   confirm-кнопки одного warning-сообщения), рендерит result-карточку.
   Повторный клик той же кнопки → use-case возвращает
   `EnchantAttemptResult(idempotent=True)` → `enchant-idempotent` +
   toast `enchant-toast-already-processed`.

3. **Callback `enc:cancel:<item_id>:<scroll_id>`**: редактирует
   warning-сообщение в `enchant-cancelled`, снимает клавиатуру, шлёт
   `enchant-toast-cancelled` toast.

Все доменные ошибки use-case-а (`ItemNotFoundError`,
`WrongScrollCategoryError`, `ScrollNotFoundError`,
`ScrollOutOfStockError`) маппятся в локализованные сообщения через
`EnchantPresenter`. Прочие ошибки — глотаются `ErrorHandlerMiddleware`,
toast `enchant-toast-error` отдаётся на callback-фейл (best-effort).

Локаль берётся из `LocaleMiddleware.data["locale"]`, `IMessageBundle`
+ use-case-ы + репо — из workflow-data контейнера (DI выставляется в
`bot/main.py`).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.inventory import EnchantItem, GetInventory, ItemView
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.enchant import (
    EnchantPresenter,
    parse_enchant_callback_data,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.enchantment import Scroll
from pipirik_wars.domain.inventory import (
    ItemNotFoundError,
    ScrollNotFoundError,
    ScrollOutOfStockError,
    WrongScrollCategoryError,
)
from pipirik_wars.domain.shared.ports import IUnitOfWork

router = Router(name="enchant")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_EXPECTED_ARG_COUNT: Final[int] = 2


@router.message(Command("enchant"))
async def handle_enchant(  # noqa: PLR0911 — каждое условие = отдельная ветка ответа handler-у
    message: Message,
    tg_identity: TgIdentity | None,
    get_inventory: GetInventory,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/enchant <item_id> <scroll_id>` — warning-карточка перед заточкой.

    Контракт:
    - Группа/супергруппа → `enchant-group` («открой ЛС»).
    - Прочие чаты (`channel`, no-identity) → `enchant-other`.
    - В ЛС, не зарегистрирован → `enchant-not-registered`.
    - Аргументов не ровно 2 → `enchant-usage`.
    - Невалидный `scroll_id` (не парсится в `Scroll`-VO) →
      `enchant-error-bad-args`.
    - Предмета нет в инвентаре игрока → `enchant-error-item-not-found`.
    - Скролла нет в стэке (или `qty == 0`) →
      `enchant-error-scroll-not-found`.
    - Категория скролла ≠ категории предмета →
      `enchant-error-wrong-category`.
    - Иначе — рендерим `warning(...)` + клавиатуру `keyboard_confirm(...)`.
    """
    presenter = EnchantPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    args = _parse_args(message.text)
    if args is None:
        await message.answer(presenter.usage(locale=effective_locale))
        return
    item_id, scroll_id = args

    profile = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if profile is None:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    assert profile.player.id is not None

    try:
        scroll = Scroll.from_scroll_id(scroll_id)
    except ValueError:
        await message.answer(presenter.error_bad_args(locale=effective_locale))
        return

    inventory = await get_inventory(player_id=profile.player.id)
    item = _find_item(inventory.items, item_id=item_id)
    if item is None:
        await message.answer(presenter.error_item_not_found(locale=effective_locale))
        return
    if not _has_scroll_in_stock(inventory.scrolls, scroll_id=scroll_id):
        await message.answer(presenter.error_scroll_not_found(locale=effective_locale))
        return
    if item.category.name != scroll.category.name:
        await message.answer(presenter.error_wrong_category(locale=effective_locale))
        return

    config = balance.get().enchantment
    text = presenter.warning(
        item=item,
        scroll=scroll,
        config=config,
        locale=effective_locale,
    )
    keyboard = presenter.keyboard_confirm(
        item_id=item_id,
        scroll_id=scroll_id,
        locale=effective_locale,
    )
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("enc:"))
async def handle_enchant_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    enchant_item: EnchantItem,
    get_inventory: GetInventory,
    get_profile: GetProfile,
    uow: IUnitOfWork,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Маршрутизатор inline-кнопок warning-карточки заточки.

    Поддерживаемые `action`-ы (см. `parse_enchant_callback_data`):
    - `confirm` — зовёт `EnchantItem` use-case + рендерит result-карточку;
    - `cancel`  — редактирует сообщение в «отмена», шлёт toast.

    Любой невалидный `callback_data` → toast `enchant-toast-error` +
    предупреждение в лог (без падения, чтобы Telegram не ретраил).
    """
    if tg_identity is None or callback.data is None:
        return

    presenter = EnchantPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        action, item_id, scroll_id = parse_enchant_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "enchant.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.toast_error(locale=effective_locale),
            show_alert=False,
        )
        return

    if action == "cancel":
        await _handle_cancel_callback(
            callback=callback,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    await _handle_confirm_callback(
        callback=callback,
        tg_identity=tg_identity,
        item_id=item_id,
        scroll_id=scroll_id,
        enchant_item=enchant_item,
        get_inventory=get_inventory,
        get_profile=get_profile,
        uow=uow,
        presenter=presenter,
        locale=effective_locale,
    )


async def _handle_cancel_callback(
    *,
    callback: CallbackQuery,
    presenter: EnchantPresenter,
    locale: Locale,
) -> None:
    """Логика «Отмена» (`enc:cancel:<item_id>:<scroll_id>`).

    Редактирует сообщение в `enchant-cancelled`-текст, снимает
    клавиатуру (best-effort: если Telegram отказал — молчим, ack-ом
    callback-у уже отдали).
    """
    await callback.answer(
        presenter.toast_cancelled(locale=locale),
        show_alert=False,
    )
    msg = callback.message
    if msg is None:
        return
    with contextlib.suppress(Exception):
        await msg.edit_text(text=presenter.cancelled(locale=locale))  # type: ignore[union-attr]


async def _handle_confirm_callback(  # noqa: PLR0911 — доменные ошибки → точечные toast-ветки
    *,
    callback: CallbackQuery,
    tg_identity: TgIdentity,
    item_id: str,
    scroll_id: str,
    enchant_item: EnchantItem,
    get_inventory: GetInventory,
    get_profile: GetProfile,
    uow: IUnitOfWork,
    presenter: EnchantPresenter,
    locale: Locale,
) -> None:
    """Логика «Подтвердить» (`enc:confirm:<item_id>:<scroll_id>`).

    Open ambient `IUnitOfWork`, зовёт `EnchantItem` use-case с
    стабильным `idempotency_key`, рендерит result-карточку (success /
    no_effect / drop / destroy / idempotent). На доменные ошибки —
    локализованный toast.

    `idempotency_key` = `f"{tg_user_id}:{message_id}"` — стабилен
    относительно одной warning-карточки; повторный клик confirm-а
    того же сообщения → no-op (use-case вернёт `idempotent=True`).
    """
    msg = callback.message
    if msg is None:
        # Сообщение слишком старое (>48 ч) — Telegram не даст ничего сделать;
        # ack-ом отвязываем callback и выходим.
        await callback.answer(
            presenter.toast_error(locale=locale),
            show_alert=False,
        )
        return

    profile = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if profile is None:
        await callback.answer(
            presenter.not_registered(locale=locale),
            show_alert=False,
        )
        return
    assert profile.player.id is not None

    # `display_name` нужен для рендера result-карточки; берём из inventory
    # ДО use-case-а (после `DESTROY` предмета в инвентаре уже не будет).
    inventory = await get_inventory(player_id=profile.player.id)
    item = _find_item(inventory.items, item_id=item_id)
    if item is None:
        await callback.answer(
            presenter.error_item_not_found(locale=locale),
            show_alert=False,
        )
        return
    item_display_name = item.display_name

    idempotency_key = f"{tg_identity.tg_user_id}:{msg.message_id}"

    try:
        async with uow:
            result = await enchant_item(
                player_id=profile.player.id,
                item_id=item_id,
                scroll_id=scroll_id,
                idempotency_key=idempotency_key,
            )
    except ItemNotFoundError:
        await callback.answer(
            presenter.error_item_not_found(locale=locale),
            show_alert=False,
        )
        return
    except WrongScrollCategoryError:
        await callback.answer(
            presenter.error_wrong_category(locale=locale),
            show_alert=False,
        )
        return
    except ScrollNotFoundError:
        await callback.answer(
            presenter.error_scroll_not_found(locale=locale),
            show_alert=False,
        )
        return
    except ScrollOutOfStockError:
        await callback.answer(
            presenter.error_out_of_stock(locale=locale),
            show_alert=False,
        )
        return
    except ValueError:
        # Невалидный `scroll_id` — теоретически отрезано на /enchant-handler-е,
        # но на всякий случай защищаемся (guard от прямого вызова callback).
        await callback.answer(
            presenter.error_bad_args(locale=locale),
            show_alert=False,
        )
        return

    if result.idempotent:
        await callback.answer(
            presenter.toast_already_processed(locale=locale),
            show_alert=False,
        )
    else:
        await callback.answer(
            presenter.toast_confirmed(locale=locale),
            show_alert=False,
        )

    text = presenter.result(
        result=result,
        item_display_name=item_display_name,
        locale=locale,
    )
    with contextlib.suppress(Exception):
        await msg.edit_text(text=text)  # type: ignore[union-attr]


def _parse_args(text: str | None) -> tuple[str, str] | None:
    """Распарсить аргументы `/enchant <item_id> <scroll_id>`.

    Возвращает `(item_id, scroll_id)` или `None`, если аргументов не
    ровно два. Telegram кладёт в `message.text` всю команду целиком
    (включая `/enchant` или `/enchant@bot_username`), поэтому отсекаем
    первую часть.
    """
    if not text:
        return None
    parts = text.strip().split()
    if len(parts) != _EXPECTED_ARG_COUNT + 1:
        return None
    return parts[1], parts[2]


def _find_item(items: tuple[ItemView, ...], *, item_id: str) -> ItemView | None:
    """Найти `ItemView` по `item_id` или `None`."""
    for item in items:
        if item.item_id == item_id:
            return item
    return None


def _has_scroll_in_stock(
    scrolls: tuple[object, ...],
    *,
    scroll_id: str,
) -> bool:
    """Проверить, что у игрока в инвентаре есть стэк такого скролла с `qty > 0`.

    Принимает кортеж `ScrollView`-DTO; `qty == 0`-стэки `GetInventory`
    уже отфильтровывает на уровне репо, но защитный фильтр здесь —
    дешёвый и читаемый.
    """
    for scroll in scrolls:
        # `ScrollView`-duck-typing — не импортируем сам тип, чтобы избежать
        # циклической зависимости handler ↔ application/inventory DTO.
        sid = getattr(scroll, "scroll_id", None)
        qty = getattr(scroll, "qty", 0)
        if sid == scroll_id and qty > 0:
            return True
    return False
