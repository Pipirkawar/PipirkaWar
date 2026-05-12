"""Handler команды `/prize_pool` (Спринт 4.1-E, E.12, ГДД §12.6.6).

`/prize_pool` — read-only снимок крипто-пула + freeze-состояния.
Доступ — `SUPER_ADMIN` (через `IAdminAuthorizationPolicy` на use-case-е,
сам факт обращения логируется в `admin_audit_log` как
`ADMIN_PRIZE_POOL_VIEWED`).

Команда живёт только в ЛС бота (как и остальные admin-команды).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.monetization import (
    GetPrizePoolStatus,
    GetPrizePoolStatusInput,
)
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_prize_pool import PrizePoolStatusPresenter

router = Router(name="admin_prize_pool")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

REPLY_NON_PRIVATE_RU = "🍆 Админ-команды доступны только в ЛС бота."


@router.message(Command("prize_pool"))
async def handle_prize_pool(
    message: Message,
    tg_identity: TgIdentity | None,
    get_prize_pool_status: GetPrizePoolStatus,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/prize_pool` — снимок крипто-пула (super-admin only)."""
    presenter = PrizePoolStatusPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    try:
        output = await get_prize_pool_status.execute(
            GetPrizePoolStatusInput(
                actor_tg_id=tg_identity.tg_user_id,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return

    await message.answer(presenter.render(locale=effective_locale, output=output))
