"""`/profile` handler (Спринт 1.1.E → 1.5.C, ГДД §2.2).

Acceptance:
- Только в ЛС: в группе/супергруппе бот шлёт инструкцию «открой ЛС».
  Это тот же контракт, что и у `/start` — клановые чаты не место
  для просмотра карточки игрока (UX + privacy).
- Если игрок не зарегистрирован — handler шлёт текст-инструкцию
  с напоминанием нажать `/start` в ЛС.
- Иначе — рендерит карточку через `ProfilePresenter`.

Все ошибки use-case-а ловит `ErrorHandlerMiddleware`; здесь handler
не пытается обрабатывать `DomainError`-ы вручную.

С 1.5.C handler берёт `Locale` из `LocaleMiddleware.data["locale"]`
и `IMessageBundle` из workflow-data. Hardcoded RU-строки удалены.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.profile import ProfilePresenter

router = Router(name="profile")


@router.message(Command("profile"))
async def handle_profile(
    message: Message,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Отвечает на `/profile` — рисует карточку персонажа в ЛС."""
    presenter = ProfilePresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    await message.answer(presenter.card(view, locale=effective_locale))
