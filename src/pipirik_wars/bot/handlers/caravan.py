"""Handler команды `/caravan` (Спринт 3.2-D, ГДД §9).

Команда `/caravan <receiver_chat_id> <contribution_cm>` (личка-only):

1. Парсим два аргумента из `message.text`. Любой не-int / число ≤ 0 →
   локализованный usage / argument-error.
2. Резолвим клан-отправитель: игрок → его membership → клан.
   Если игрок не в клане → `caravans-no-clan`. Если не лидер →
   `caravans-not-a-leader` (`CreateCaravan` всё равно бросит
   `CaravanRoleConflictError`, но handler-ный pre-check экономит
   круговую транзакцию и даёт точечное локализованное сообщение).
3. Зовём `CreateCaravan` use-case (он сам проверит толщину/длину/
   кулдаун/заморозку/двойной клан и т.д.).
4. На успехе — два сообщения: подтверждение лидеру в личке +
   объявление в чате клана-отправителя с инлайн-кнопкой
   «Показать лобби» (полное lobby UI с join/leave/cancel — D.3).

Все локали — через `CaravanPresenter` + `IMessageBundle`. Префикс
ключей `caravans-*` (множественное — исторический выбор).
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import Final

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.caravans import CancelCaravan, CreateCaravan
from pipirik_wars.application.dto.inputs import (
    CancelCaravanInput,
    CreateCaravanInput,
)
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import CaravanPresenter
from pipirik_wars.bot.presenters.caravans import parse_caravan_callback_data
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.caravan import (
    AlreadyInCaravanError,
    CaravanCooldownError,
    CaravanNotFoundError,
    CaravanRequirementError,
    CaravanRoleConflictError,
    InvalidCaravanStateError,
)
from pipirik_wars.domain.clan import (
    Clan,
    ClanFrozenError,
    ClanMemberRole,
    IClanMembershipRepository,
    IClanRepository,
)
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.player.errors import (
    PlayerFrozenError,
    PlayerNotFoundError,
)
from pipirik_wars.shared.errors import IntegrityError

router = Router(name="caravan")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_EXPECTED_ARG_COUNT: Final[int] = 2


@dataclass(frozen=True, slots=True)
class _ParsedArgs:
    receiver_chat_id: int
    contribution_cm: int


@router.message(Command("caravan"))
async def handle_caravan(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    message: Message,
    tg_identity: TgIdentity | None,
    create_caravan: CreateCaravan,
    get_profile: GetProfile,
    players: IPlayerRepository,
    clan_members: IClanMembershipRepository,
    clans: IClanRepository,
    balance: IBalanceConfig,
    bot: Bot,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/caravan <receiver_chat_id> <contribution_cm>` — собрать караван."""
    presenter = CaravanPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    args = await _parse_and_validate_args(
        message=message,
        presenter=presenter,
        locale=effective_locale,
    )
    if args is None:
        return

    sender_clan = await _resolve_sender_clan(
        message=message,
        tg_identity=tg_identity,
        players=players,
        clan_members=clan_members,
        clans=clans,
        presenter=presenter,
        locale=effective_locale,
    )
    if sender_clan is None:
        return

    if sender_clan.chat_id == args.receiver_chat_id:
        await message.answer(presenter.receiver_same_as_sender(locale=effective_locale))
        return

    try:
        result = await create_caravan.execute(
            CreateCaravanInput(
                initiator_tg_id=tg_identity.tg_user_id,
                sender_chat_id=sender_clan.chat_id,
                receiver_chat_id=args.receiver_chat_id,
                contribution_cm=args.contribution_cm,
            )
        )
    except (
        PlayerNotFoundError,
        PlayerFrozenError,
        IntegrityError,
        ClanFrozenError,
        CaravanRoleConflictError,
        AlreadyInCaravanError,
        CaravanCooldownError,
        CaravanRequirementError,
    ) as exc:
        await _answer_create_caravan_error(
            message=message,
            exc=exc,
            sender_clan=sender_clan,
            receiver_chat_id=args.receiver_chat_id,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    receiver_clan = await clans.get_by_chat_id(args.receiver_chat_id)
    if receiver_clan is None:  # pragma: no cover — `CreateCaravan` упал бы IntegrityError выше
        _LOGGER.error(
            "caravan: receiver_clan vanished after CreateCaravan — chat_id=%s",
            args.receiver_chat_id,
        )
        return
    cfg = balance.get().caravans
    receiver_name = receiver_clan.title.value

    await message.answer(
        presenter.created_private(
            receiver_clan_name=receiver_name,
            contribution_cm=args.contribution_cm,
            lobby_minutes=cfg.lobby_minutes,
            locale=effective_locale,
        ),
    )

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:  # pragma: no cover — игрок только что прошёл use-case
        _LOGGER.warning(
            "caravan: profile not found right after CreateCaravan",
            extra={"tg_id": tg_identity.tg_user_id, "caravan_id": result.caravan.id},
        )
        return

    assert result.caravan.id is not None
    announcement_text = presenter.created_announcement(
        leader=view.player,
        leader_display_name=view.display_name,
        receiver_clan_name=receiver_name,
        contribution_cm=args.contribution_cm,
        lobby_minutes=cfg.lobby_minutes,
        locale=effective_locale,
    )
    keyboard = presenter.announcement_keyboard(
        caravan_id=result.caravan.id,
        locale=effective_locale,
    )
    try:
        await bot.send_message(
            chat_id=sender_clan.chat_id,
            text=announcement_text,
            reply_markup=keyboard,
        )
    except TelegramAPIError as exc:
        _LOGGER.warning(
            "caravan: failed to post announcement to sender chat",
            extra={
                "sender_chat_id": sender_clan.chat_id,
                "caravan_id": result.caravan.id,
                "error": str(exc),
            },
        )


async def _parse_and_validate_args(
    *,
    message: Message,
    presenter: CaravanPresenter,
    locale: Locale,
) -> _ParsedArgs | None:
    """Распарсить и провалидировать аргументы команды.

    Отвечает игроку локализованной ошибкой и возвращает None, если
    аргументов не два / любой из них не int / contribution ≤ 0.
    """
    parsed = _split_args(message.text)
    if parsed is None:
        await message.answer(presenter.usage(locale=locale))
        return None
    receiver_raw, contribution_raw = parsed

    try:
        receiver_chat_id = int(receiver_raw)
    except ValueError:
        await message.answer(presenter.receiver_invalid(value=receiver_raw, locale=locale))
        return None

    try:
        contribution_cm = int(contribution_raw)
    except ValueError:
        await message.answer(
            presenter.contribution_invalid(value=contribution_raw, locale=locale),
        )
        return None
    if contribution_cm <= 0:
        await message.answer(
            presenter.contribution_invalid(value=contribution_raw, locale=locale),
        )
        return None
    return _ParsedArgs(receiver_chat_id=receiver_chat_id, contribution_cm=contribution_cm)


async def _resolve_sender_clan(
    *,
    message: Message,
    tg_identity: TgIdentity,
    players: IPlayerRepository,
    clan_members: IClanMembershipRepository,
    clans: IClanRepository,
    presenter: CaravanPresenter,
    locale: Locale,
) -> Clan | None:
    """Pre-check: игрок зарегистрирован, состоит в клане и он — лидер.

    `CreateCaravan` сам бросит соответствующие ошибки, но без знания
    `sender_chat_id` мы не можем его позвать (личка не даёт нам
    клана-отправителя). Заодно даём пользователю точечное сообщение
    «не лидер» вместо общего «role conflict».
    """
    player = await players.get_by_tg_id(tg_identity.tg_user_id)
    if player is None:
        await message.answer(presenter.not_registered(locale=locale))
        return None
    assert player.id is not None
    membership = await clan_members.get_by_player(player.id)
    if membership is None:
        await message.answer(presenter.no_clan(locale=locale))
        return None
    if membership.role is not ClanMemberRole.LEADER:
        await message.answer(presenter.not_a_leader(locale=locale))
        return None
    sender_clan = await clans.get_by_id(membership.clan_id)
    if sender_clan is None:  # pragma: no cover — битая FK в БД, не должно случаться
        _LOGGER.error(
            "caravan: dangling membership — clan_id=%s missing for player_id=%s",
            membership.clan_id,
            player.id,
        )
        await message.answer(presenter.no_clan(locale=locale))
        return None
    return sender_clan


async def _answer_create_caravan_error(  # noqa: PLR0911 — единая точка маппинга доменных ошибок use-case в локали
    *,
    message: Message,
    exc: Exception,
    sender_clan: Clan,
    receiver_chat_id: int,
    presenter: CaravanPresenter,
    locale: Locale,
) -> None:
    """Маппинг доменных ошибок `CreateCaravan` в локализованные ответы."""
    if isinstance(exc, PlayerNotFoundError):
        await message.answer(presenter.not_registered(locale=locale))
        return
    if isinstance(exc, PlayerFrozenError):
        await message.answer(presenter.player_frozen(locale=locale))
        return
    if isinstance(exc, IntegrityError):
        # Receiver-клан не зарегистрирован (sender мы уже резолвили
        # сами выше — он точно есть).
        await message.answer(
            presenter.receiver_not_found(chat_id=receiver_chat_id, locale=locale),
        )
        return
    if isinstance(exc, ClanFrozenError):
        if exc.chat_id == sender_clan.chat_id:
            await message.answer(presenter.clan_frozen_sender(locale=locale))
        else:
            await message.answer(presenter.clan_frozen_receiver(locale=locale))
        return
    if isinstance(exc, CaravanRoleConflictError):
        # Между моментом нашего pre-check-а и коммитом транзакции
        # лидерство могло пересесть. Возвращаем общий «не лидер».
        await message.answer(presenter.not_a_leader(locale=locale))
        return
    if isinstance(exc, AlreadyInCaravanError):
        await message.answer(presenter.already_in(locale=locale))
        return
    if isinstance(exc, CaravanCooldownError):
        await message.answer(
            presenter.cooldown(
                remaining_seconds=exc.actual_remaining_seconds,
                locale=locale,
            ),
        )
        return
    if isinstance(exc, CaravanRequirementError):
        if exc.requirement == "thickness":
            await message.answer(
                presenter.requirement_thickness(
                    required=exc.required,
                    actual=exc.actual,
                    locale=locale,
                ),
            )
            return
        await message.answer(
            presenter.requirement_length(
                required_cm=exc.required,
                actual_cm=exc.actual,
                locale=locale,
            ),
        )
        return
    raise exc  # pragma: no cover — все ветки покрыты except-блоком в handler-е


def _split_args(text: str | None) -> tuple[str, str] | None:
    """Распарсить хвост `/caravan <receiver_chat_id> <contribution_cm>`.

    Возвращает кортеж сырых строк или `None`, если аргументов не
    ровно два. Сами строки — без приведения к int (handler сам решит,
    что делать при ошибке).

    Используем `split()` без `maxsplit=` (чистое разбиение по пробелам):
    это даёт «жёсткую» проверку числа аргументов — `/caravan a b c`
    вернёт `None` (usage), а не молча «прицепит c к b».
    """
    if not text:
        return None
    parts = text.strip().split()
    # parts[0] — `/caravan` (или `/caravan@bot_username`); далее ровно
    # два позиционных аргумента.
    if len(parts) != _EXPECTED_ARG_COUNT + 1:
        return None
    return parts[1], parts[2]


@router.callback_query(F.data.startswith("caravan:"))
async def handle_caravan_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    cancel_caravan: CancelCaravan,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Маршрутизатор инлайн-кнопок каравана (D.3).

    Сейчас поддержан `cancel`. Остальные действия (`show_lobby` /
    `join_defender` / `join_raider` / `leave`) будут добавлены в
    последующих под-коммитах D.3 — пока для них защитный ack без
    мутации, чтобы кнопка не «висела» с loading-индикатором.
    """
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    presenter = CaravanPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_caravan_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "caravan.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.callback_toast_generic_error(locale=effective_locale),
            show_alert=False,
        )
        return

    if parsed.action == "cancel":
        await _handle_cancel_callback(
            callback=callback,
            tg_identity=tg_identity,
            caravan_id=parsed.caravan_id,
            cancel_caravan=cancel_caravan,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    # show_lobby / join_defender / join_raider / leave — реализация
    # в следующих под-коммитах D.3. Защитный ack, чтобы UI у клиента
    # не «висел» loading-индикатором на нажатой кнопке.
    await callback.answer()


async def _handle_cancel_callback(
    *,
    callback: CallbackQuery,
    tg_identity: TgIdentity,
    caravan_id: int,
    cancel_caravan: CancelCaravan,
    presenter: CaravanPresenter,
    locale: Locale,
) -> None:
    """Логика callback-а отмены каравана (`caravan:cancel:<id>`).

    Зовёт `CancelCaravan` use-case (он сам проверит лидерство и
    статус). На каждый доменный отказ — локализованный toast. На
    успех — toast + замена сообщения текстом «караван отменён» +
    снятие клавиатуры.
    """
    try:
        result = await cancel_caravan.execute(
            CancelCaravanInput(
                caravan_id=caravan_id,
                tg_id=tg_identity.tg_user_id,
            ),
        )
    except CaravanNotFoundError:
        await callback.answer(
            presenter.callback_toast_caravan_not_found(locale=locale),
            show_alert=False,
        )
        return
    except InvalidCaravanStateError:
        await callback.answer(
            presenter.callback_toast_invalid_state(locale=locale),
            show_alert=False,
        )
        return
    except CaravanRoleConflictError:
        await callback.answer(
            presenter.callback_toast_not_a_leader(locale=locale),
            show_alert=False,
        )
        return
    except PlayerNotFoundError:
        await callback.answer(
            presenter.callback_toast_player_not_found(locale=locale),
            show_alert=False,
        )
        return

    if result.was_already_cancelled:
        await callback.answer(
            presenter.cancel_toast_already_cancelled(locale=locale),
            show_alert=False,
        )
    else:
        await callback.answer(
            presenter.cancel_toast_success(locale=locale),
            show_alert=False,
        )

    await _replace_with_cancelled(
        callback=callback,
        text=presenter.cancel_message_text(locale=locale),
    )


async def _replace_with_cancelled(*, callback: CallbackQuery, text: str) -> None:
    """Заменить сообщение с кнопкой на «караван отменён» и снять клавиатуру.

    Best-effort: ошибки edit-а (старое сообщение, недоступно, уже
    отредактировано) поглощаем — они не критичны для UX, главное,
    что use-case уже успешно завершился.
    """
    msg = callback.message
    if msg is None:
        return
    # CallbackQuery.message — `Message | InaccessibleMessage`; у обоих есть
    # `edit_text`, но у `InaccessibleMessage` он бросит TelegramAPIError,
    # которое мы поглотим.
    with contextlib.suppress(Exception):
        await msg.edit_text(text=text, reply_markup=None)  # type: ignore[union-attr]


__all__ = ["handle_caravan", "handle_caravan_callback", "router"]
