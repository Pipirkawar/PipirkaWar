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
    FreezePlayer,
    FreezePlayerInput,
    GetPlayerCard,
    GetPlayerCardInput,
    UnfreezePlayer,
    UnfreezePlayerInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_support import (
    FindPlayerPresenter,
    FreezePlayerPresenter,
    GetPlayerCardPresenter,
    UnfreezePlayerPresenter,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError

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


@router.message(Command("player"))
async def handle_player(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    get_player_card: GetPlayerCard,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/player <tg_id>` — карточка игрока (Спринт 2.5-B.2).

    Аргумент строго целое число. Локализованные ответы — `admin-player-*`.
    """
    presenter = GetPlayerCardPresenter(bundle=bundle)
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
        target_tg_id = int(raw)
    except ValueError:
        await message.answer(presenter.bad_id(locale=effective_locale, value=raw))
        return

    try:
        result = await get_player_card.execute(
            GetPlayerCardInput(
                actor_tg_id=tg_identity.tg_user_id,
                target_tg_id=target_tg_id,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return

    if result.card is None:
        await message.answer(
            presenter.not_found(locale=effective_locale, tg_id=target_tg_id),
        )
        return

    await message.answer(
        presenter.render(locale=effective_locale, card=result.card),
    )


@router.message(Command("freeze"))
async def handle_freeze(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    freeze_player: FreezePlayer,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/freeze <tg_id> [reason]` — обратимая заморозка (Спринт 2.5-B.3)."""
    presenter = FreezePlayerPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    parts = raw.split(maxsplit=1)
    try:
        target_tg_id = int(parts[0])
    except ValueError:
        await message.answer(presenter.bad_id(locale=effective_locale, value=parts[0]))
        return
    reason = parts[1].strip() if len(parts) == 2 else None

    try:
        result = await freeze_player.execute(
            FreezePlayerInput(
                actor_tg_id=tg_identity.tg_user_id,
                target_tg_id=target_tg_id,
                reason=reason,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except PlayerNotFoundError:
        await message.answer(
            presenter.not_found(locale=effective_locale, tg_id=target_tg_id),
        )
        return

    if result.was_already_frozen:
        await message.answer(
            presenter.already(locale=effective_locale, tg_id=target_tg_id),
        )
        return

    await message.answer(
        presenter.ok(locale=effective_locale, tg_id=target_tg_id, reason=reason),
    )


@router.message(Command("unfreeze"))
async def handle_unfreeze(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    unfreeze_player: UnfreezePlayer,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/unfreeze <tg_id> [reason]` — снятие заморозки (Спринт 2.5-B.3)."""
    presenter = UnfreezePlayerPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    parts = raw.split(maxsplit=1)
    try:
        target_tg_id = int(parts[0])
    except ValueError:
        await message.answer(presenter.bad_id(locale=effective_locale, value=parts[0]))
        return
    reason = parts[1].strip() if len(parts) == 2 else None

    try:
        result = await unfreeze_player.execute(
            UnfreezePlayerInput(
                actor_tg_id=tg_identity.tg_user_id,
                target_tg_id=target_tg_id,
                reason=reason,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except PlayerNotFoundError:
        await message.answer(
            presenter.not_found(locale=effective_locale, tg_id=target_tg_id),
        )
        return

    if result.was_already_active:
        await message.answer(
            presenter.already(locale=effective_locale, tg_id=target_tg_id),
        )
        return

    await message.answer(
        presenter.ok(locale=effective_locale, tg_id=target_tg_id, reason=reason),
    )
