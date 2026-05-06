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
    BanPlayer,
    FindPlayers,
    FindPlayersInput,
    FreezePlayer,
    FreezePlayerInput,
    GetPlayerCard,
    GetPlayerCardInput,
    GrantLength,
    GrantThickness,
    RequestAdminConfirm,
    RequestAdminConfirmInput,
    SetBalanceValue,
    UnfreezePlayer,
    UnfreezePlayerInput,
    VerifyAdminConfirm,
    VerifyAdminConfirmInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.handlers.admin_economy import (
    COMMAND_KIND_BAN,
    CONFIRM_DISPATCHERS,
    ConfirmDispatchDeps,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_support import (
    BanPlayerPresenter,
    ConfirmPresenter,
    FindPlayerPresenter,
    FreezePlayerPresenter,
    GetPlayerCardPresenter,
    UnfreezePlayerPresenter,
)
from pipirik_wars.domain.admin import (
    ConfirmAdminMismatchError,
    ConfirmCodeInvalidError,
    ConfirmTokenExpiredError,
    ConfirmTokenNotFoundError,
    TotpNotConfiguredError,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import IClock

router = Router(name="admin_support")
# Тихий игнор не-админских апдейтов на уровне router-а (ГДД §18.6.4):
# фильтр применяется ко всем observer-ам `Router`-а — message + callback.
# `data["admin"]` кладётся `AdminGuard`-middleware-ом (Спринт 2.5-A.2);
# если этот middleware не подключён в dispatcher-е, фильтр считает
# актора не-админом и пропускает апдейт мимо router-а.
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

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


# ── /ban (B.4) — TOTP-двухфазный ────────────────────────────────────────────


@router.message(Command("ban"))
async def handle_ban(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    request_admin_confirm: RequestAdminConfirm,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/ban <tg_id> <reason>` — первая фаза: запрос TOTP-подтверждения."""
    presenter = BanPlayerPresenter(bundle=bundle)
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

    reason = parts[1].strip() if len(parts) == 2 else ""
    if not reason:
        await message.answer(presenter.no_reason(locale=effective_locale))
        return

    try:
        result = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_BAN,
                target_kind="player",
                target_id=str(target_tg_id),
                payload={"target_tg_id": target_tg_id, "reason": reason},
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except TotpNotConfiguredError:
        await message.answer(presenter.totp_not_configured(locale=effective_locale))
        return

    await message.answer(
        presenter.confirm_issued(
            locale=effective_locale,
            token=result.token,
            ttl_seconds=result.ttl_seconds,
        ),
    )


# ── /confirm (B.5) — общий handler 2-й фазы ─────────────────────────────────


@router.message(Command("confirm"))
async def handle_confirm(  # noqa: PLR0911 — каждая ветка-возврат = отдельная UX-ошибка
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    verify_admin_confirm: VerifyAdminConfirm,
    ban_player: BanPlayer,
    grant_length: GrantLength,
    grant_thickness: GrantThickness,
    set_balance_value: SetBalanceValue,
    clock: IClock,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/confirm <token> <code>` — второй шаг для всех опасных admin-команд.

    Регистр-диспетчер: `command_kind` → `dispatch_*`-функция (см.
    `bot/handlers/admin_economy.py::CONFIRM_DISPATCHERS`).
    """
    presenter = ConfirmPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.usage(locale=effective_locale))
        return
    parts = raw.split()
    if len(parts) != 2:
        await message.answer(presenter.usage(locale=effective_locale))
        return
    token, code = parts[0], parts[1]

    try:
        result = await verify_admin_confirm.execute(
            VerifyAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                token=token,
                code=code,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except TotpNotConfiguredError:
        await message.answer(presenter.totp_not_configured(locale=effective_locale))
        return
    except ConfirmTokenNotFoundError:
        await message.answer(
            presenter.token_not_found(locale=effective_locale, token=token),
        )
        return
    except ConfirmTokenExpiredError:
        await message.answer(presenter.token_expired(locale=effective_locale))
        return
    except ConfirmAdminMismatchError:
        await message.answer(presenter.admin_mismatch(locale=effective_locale))
        return
    except ConfirmCodeInvalidError:
        await message.answer(presenter.code_invalid(locale=effective_locale))
        return

    dispatcher = CONFIRM_DISPATCHERS.get(result.command_kind)
    if dispatcher is not None:
        deps = ConfirmDispatchDeps(
            grant_length=grant_length,
            grant_thickness=grant_thickness,
            set_balance_value=set_balance_value,
            ban_player=ban_player,
            clock=clock,
        )
        await dispatcher(result, message, tg_identity, effective_locale, bundle, deps)
        return

    # Если прилетел неизвестный command_kind — не знаем, что делать.
    await message.answer(
        presenter.unknown_command_kind(
            locale=effective_locale,
            command_kind=result.command_kind,
        ),
    )
