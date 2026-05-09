"""`/inventory` handler (Спринт 3.4-D, ГДД §2.6 + §2.8).

Acceptance:
- Только в ЛС: в группе/супергруппе бот шлёт инструкцию «открой ЛС»;
  в любых других типах чата (channel и т. п.) — `inventory-other`.
  Это тот же контракт, что и у `/profile`/`/start` — клановые чаты
  не место для приватных данных.
- Если игрок не зарегистрирован — handler шлёт текст-инструкцию с
  напоминанием нажать `/start` в ЛС.
- Если инвентарь пуст — `inventory-empty` (мотивационный текст).
- Иначе — рендерит карточку через `InventoryPresenter` с inline-
  клавиатурой кнопок «Заточить» (по одной на каждый предмет).

Все ошибки use-case-а ловит `ErrorHandlerMiddleware`; здесь handler
не пытается обрабатывать `DomainError`-ы вручную.

Локаль берётся из `LocaleMiddleware.data["locale"]`, `IMessageBundle`
— из workflow-data контейнера (DI выставляется в `bot/main.py`).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.inventory import GetInventory
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.inventory import InventoryPresenter

router = Router(name="inventory")


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
