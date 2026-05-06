"""Handler-ы команд поддержки кланов (Спринт 2.5-D.1+, ГДД §18.6.5).

В этом router-е лежат `/clan` (read-only карточка), а в дальнейших
подспринтах — `/freeze_clan`, `/unfreeze_clan`, `/clan_daily_head_history`.
Все доступны **только** в ЛС, фильтр `is_admin` (на уровне регистрации
router-а) тихо игнорирует чужих — чтобы по «не отвечает» нельзя было
перебрать список команд.

Авторизация — на стороне use-case-а: handler ловит `AuthorizationError`
и шлёт friendly-сообщение из локали. Audit-запись пишется самим
use-case-ом (handler не дёргает `IAdminAuditLogger` напрямую).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.admin import (
    GetClanCard,
    GetClanCardInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_clan import GetClanCardPresenter

router = Router(name="admin_clan")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

REPLY_NON_PRIVATE_RU = "🍆 Админ-команды доступны только в ЛС бота."


@router.message(Command("clan"))
async def handle_clan(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    get_clan_card: GetClanCard,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/clan <id|chat_id>` — карточка клана (Спринт 2.5-D.1).

    Аргумент строго целое число — внутренний `Clan.id` или Telegram
    `chat_id`. Use-case сам выбирает, как искать (сначала по `id`,
    потом по `chat_id`). Локализованные ответы — `admin-clan-*`.
    """
    presenter = GetClanCardPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.usage(locale=effective_locale))
        return
    try:
        query = int(raw)
    except ValueError:
        await message.answer(presenter.bad_id(locale=effective_locale, value=raw))
        return

    try:
        result = await get_clan_card.execute(
            GetClanCardInput(
                actor_tg_id=tg_identity.tg_user_id,
                query=query,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return

    if result.card is None:
        await message.answer(presenter.not_found(locale=effective_locale, query=query))
        return

    await message.answer(presenter.render(locale=effective_locale, card=result.card))


__all__ = ["REPLY_NON_PRIVATE_RU", "handle_clan", "router"]
