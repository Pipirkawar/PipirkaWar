"""Handler-ы команд поддержки админ-интерфейса (Спринт 2.5-B, ГДД §18.6.5).

В этом router-е лежат `/find_player`, `/player`, `/freeze`, `/unfreeze`,
`/ban`, `/confirm`. Все доступны **только** в ЛС, фильтр `is_admin`
(на уровне регистрации router-а) тихо игнорирует чужих — чтобы по
«не отвечает» нельзя было перебрать список команд. См. ГДД §18.6.4.

Авторизация — на стороне use-case-ов: handler ловит `AuthorizationError`
и шлёт friendly-сообщение из локали. Все мутации/lookup-ы пишутся в
`admin_audit_log` use-case-ом (handler сам в audit не пишет).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.admin import (
    FindPlayers,
    FindPlayersInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_support import FindPlayerPresenter

router = Router(name="admin_support")

REPLY_NON_PRIVATE_RU = "🍆 Админ-команды доступны только в ЛС бота."


@router.message(Command("find_player"))
async def handle_find_player(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    find_players: FindPlayers,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/find_player <text>` — поиск игрока по `tg_id` / `@username` / подстроке.

    Ответы локализованы (`admin-find-player-*`). Не из ЛС → стандартное
    «только в ЛС». Пустой запрос → usage-подсказка. Авторизация — в
    `FindPlayers.execute()`; при `AuthorizationError` шлём friendly-текст.
    """
    presenter = FindPlayerPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw_query = (command.args or "").strip()
    if not raw_query:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    try:
        result = await find_players.execute(
            FindPlayersInput(
                actor_tg_id=tg_identity.tg_user_id,
                query=raw_query,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return

    if not result.results:
        await message.answer(presenter.empty(locale=effective_locale, query=result.query))
        return

    await message.answer(
        presenter.render(
            locale=effective_locale,
            query=result.query,
            results=result.results,
        ),
    )
