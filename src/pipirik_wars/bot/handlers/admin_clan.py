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
    FreezeClanAdmin,
    FreezeClanAdminInput,
    GetClanCard,
    GetClanCardInput,
    UnfreezeClanAdmin,
    UnfreezeClanAdminInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_clan import (
    FreezeClanAdminPresenter,
    GetClanCardPresenter,
    UnfreezeClanAdminPresenter,
)

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


@router.message(Command("freeze_clan"))
async def handle_freeze_clan(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    freeze_clan_admin: FreezeClanAdmin,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/freeze_clan <id|chat_id> [reason]` — ручная заморозка клана (Спринт 2.5-D.2).

    Идемпотентна (повторная заморозка → friendly «уже заморожен»).
    Без TOTP. Локализованные ответы — `admin-freeze-clan-*`.
    """
    presenter = FreezeClanAdminPresenter(bundle=bundle)
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
        query = int(parts[0])
    except ValueError:
        await message.answer(presenter.bad_id(locale=effective_locale, value=parts[0]))
        return
    reason = parts[1].strip() if len(parts) == 2 else None

    try:
        result = await freeze_clan_admin.execute(
            FreezeClanAdminInput(
                actor_tg_id=tg_identity.tg_user_id,
                query=query,
                reason=reason,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return

    if result.outcome == "not_found":
        await message.answer(presenter.not_found(locale=effective_locale, query=query))
        return

    # Доменный invariant: на «already_frozen» / «frozen» clan не None.
    assert result.clan is not None
    assert result.clan.id is not None
    if result.outcome == "already_frozen":
        await message.answer(
            presenter.already(locale=effective_locale, clan_id=result.clan.id),
        )
        return

    await message.answer(
        presenter.ok(locale=effective_locale, clan_id=result.clan.id, reason=reason),
    )


@router.message(Command("unfreeze_clan"))
async def handle_unfreeze_clan(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    unfreeze_clan_admin: UnfreezeClanAdmin,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/unfreeze_clan <id|chat_id>` — ручная разморозка клана (Спринт 2.5-D.2).

    Идемпотентна. Без TOTP. Локализованные ответы — `admin-unfreeze-clan-*`.
    """
    presenter = UnfreezeClanAdminPresenter(bundle=bundle)
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
        result = await unfreeze_clan_admin.execute(
            UnfreezeClanAdminInput(
                actor_tg_id=tg_identity.tg_user_id,
                query=query,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return

    if result.outcome == "not_found":
        await message.answer(presenter.not_found(locale=effective_locale, query=query))
        return

    assert result.clan is not None
    assert result.clan.id is not None
    if result.outcome == "already_active":
        await message.answer(
            presenter.already(locale=effective_locale, clan_id=result.clan.id),
        )
        return

    await message.answer(
        presenter.ok(locale=effective_locale, clan_id=result.clan.id),
    )


__all__ = [
    "REPLY_NON_PRIVATE_RU",
    "handle_clan",
    "handle_freeze_clan",
    "handle_unfreeze_clan",
    "router",
]
