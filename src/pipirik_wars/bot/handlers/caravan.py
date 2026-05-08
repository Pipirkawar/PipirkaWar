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
from typing import Final, Literal

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.caravans import (
    CancelCaravan,
    CreateCaravan,
    JoinCaravanLobby,
    LeaveCaravanLobby,
)
from pipirik_wars.application.dto.inputs import (
    CancelCaravanInput,
    CreateCaravanInput,
    JoinCaravanLobbyInput,
    LeaveCaravanLobbyInput,
)
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import CaravanPresenter
from pipirik_wars.bot.presenters.caravans import parse_caravan_callback_data
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.caravan import (
    AlreadyInCaravanError,
    CaravanCapacityExceededError,
    CaravanCooldownError,
    CaravanLobbyClosedError,
    CaravanNotFoundError,
    CaravanRequirementError,
    CaravanRoleConflictError,
    ICaravanParticipantRepository,
    ICaravanRepository,
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
from pipirik_wars.domain.shared.ports import IClock
from pipirik_wars.shared.errors import IntegrityError

router = Router(name="caravan")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_EXPECTED_ARG_COUNT: Final[int] = 2


@dataclass(frozen=True, slots=True)
class _ParsedArgs:
    receiver_chat_id: int
    contribution_cm: int


@dataclass(frozen=True, slots=True)
class _ParsedJoinArgs:
    caravan_id: int
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


@router.message(Command("caravan_join"))
async def handle_caravan_join(
    message: Message,
    tg_identity: TgIdentity | None,
    join_caravan_lobby: JoinCaravanLobby,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/caravan_join <caravan_id> <contribution_cm>` — вступить как
    `CARAVANEER` со взносом.

    Личка-only (как `/caravan`). Для `DEFENDER`/`RAIDER`-роли инлайн-кнопки
    в lobby-сообщении достаточно (без `contribution`); для `CARAVANEER`
    нужна явная сумма взноса, поэтому отдельная команда.
    """
    presenter = CaravanPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    args = await _parse_and_validate_join_args(
        message=message,
        presenter=presenter,
        locale=effective_locale,
    )
    if args is None:
        return

    try:
        await join_caravan_lobby.execute(
            JoinCaravanLobbyInput(
                tg_id=tg_identity.tg_user_id,
                caravan_id=args.caravan_id,
                role="caravaneer",
                contribution_cm=args.contribution_cm,
            ),
        )
    except (
        PlayerNotFoundError,
        PlayerFrozenError,
        CaravanNotFoundError,
        CaravanLobbyClosedError,
        AlreadyInCaravanError,
        CaravanRoleConflictError,
        CaravanRequirementError,
    ) as exc:
        await _answer_join_caravaneer_error(
            message=message,
            exc=exc,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    await message.answer(
        presenter.join_success_caravaneer(
            contribution_cm=args.contribution_cm,
            locale=effective_locale,
        ),
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


async def _parse_and_validate_join_args(
    *,
    message: Message,
    presenter: CaravanPresenter,
    locale: Locale,
) -> _ParsedJoinArgs | None:
    """Распарсить и провалидировать аргументы `/caravan_join`.

    Отвечает игроку локализованной ошибкой и возвращает None, если
    аргументов не два / любой из них не int / любой ≤ 0. Используем
    тот же `_split_args` (он не привязан к конкретной команде —
    проверяет только число позиционных аргументов).
    """
    parsed = _split_args(message.text)
    if parsed is None:
        await message.answer(presenter.join_usage(locale=locale))
        return None
    caravan_id_raw, contribution_raw = parsed

    try:
        caravan_id = int(caravan_id_raw)
    except ValueError:
        await message.answer(
            presenter.join_caravan_id_invalid(value=caravan_id_raw, locale=locale),
        )
        return None
    if caravan_id <= 0:
        await message.answer(
            presenter.join_caravan_id_invalid(value=caravan_id_raw, locale=locale),
        )
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
    return _ParsedJoinArgs(caravan_id=caravan_id, contribution_cm=contribution_cm)


async def _answer_join_caravaneer_error(  # noqa: PLR0911 — единая точка маппинга доменных ошибок use-case в локали
    *,
    message: Message,
    exc: Exception,
    presenter: CaravanPresenter,
    locale: Locale,
) -> None:
    """Маппинг доменных ошибок `JoinCaravanLobby` (роль `caravaneer`) в
    локализованные ответы для команды `/caravan_join`.
    """
    if isinstance(exc, PlayerNotFoundError):
        await message.answer(presenter.not_registered(locale=locale))
        return
    if isinstance(exc, PlayerFrozenError):
        await message.answer(presenter.player_frozen(locale=locale))
        return
    if isinstance(exc, CaravanNotFoundError):
        await message.answer(presenter.callback_toast_caravan_not_found(locale=locale))
        return
    if isinstance(exc, CaravanLobbyClosedError):
        await message.answer(presenter.callback_toast_lobby_closed(locale=locale))
        return
    if isinstance(exc, AlreadyInCaravanError):
        await message.answer(presenter.callback_toast_already_in_caravan(locale=locale))
        return
    if isinstance(exc, CaravanRoleConflictError):
        # Для `/caravan_join` единственная возможная причина — игрок
        # не в клане-отправителе (use-case проверяет это первым,
        # см. `_ensure_role_allowed`).
        await message.answer(presenter.join_role_conflict_caravaneer(locale=locale))
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


@router.callback_query(F.data.startswith("caravan:"))
async def handle_caravan_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    cancel_caravan: CancelCaravan,
    join_caravan_lobby: JoinCaravanLobby,
    leave_caravan_lobby: LeaveCaravanLobby,
    caravans: ICaravanRepository,
    caravan_participants: ICaravanParticipantRepository,
    clans: IClanRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    clock: IClock,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Маршрутизатор инлайн-кнопок каравана (D.3).

    Поддержанные `action`-ы:

    - `cancel` — отменить караван (только лидер, D.3a/b).
    - `show_lobby` — обновить сообщение лобби (актуальное состояние
      + клавиатура с join/leave/cancel; D.3c).
    - `join_defender` / `join_raider` — вступить в лобби как защитник
      / рейдер (D.3d). На успех — refresh lobby UI (re-render
      `lobby_state_text` + клавиатура).
    - `leave` — выйти из лобби каравана (для не-лидеров, D.3e). На
      успех — toast + refresh lobby UI.
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

    if parsed.action == "show_lobby":
        await _handle_show_lobby_callback(
            callback=callback,
            caravan_id=parsed.caravan_id,
            caravans=caravans,
            caravan_participants=caravan_participants,
            clans=clans,
            players=players,
            get_profile=get_profile,
            balance=balance,
            clock=clock,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    if parsed.action in ("join_defender", "join_raider"):
        role: Literal["defender", "raider"] = (
            "defender" if parsed.action == "join_defender" else "raider"
        )
        await _handle_join_callback(
            callback=callback,
            tg_identity=tg_identity,
            caravan_id=parsed.caravan_id,
            role=role,
            join_caravan_lobby=join_caravan_lobby,
            caravans=caravans,
            caravan_participants=caravan_participants,
            clans=clans,
            players=players,
            get_profile=get_profile,
            balance=balance,
            clock=clock,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    if parsed.action == "leave":
        await _handle_leave_callback(
            callback=callback,
            tg_identity=tg_identity,
            caravan_id=parsed.caravan_id,
            leave_caravan_lobby=leave_caravan_lobby,
            caravans=caravans,
            caravan_participants=caravan_participants,
            clans=clans,
            players=players,
            get_profile=get_profile,
            balance=balance,
            clock=clock,
            presenter=presenter,
            locale=effective_locale,
        )
        return

    # На текущей итерации все действия (cancel/show_lobby/join_*/leave)
    # уже обработаны выше. Этот защитный ack — на случай рассинхронизации
    # `_VALID_ACTIONS` в presenter и dispatch-цепочки (catch-all для
    # «канонических» actions, которые мы пропустили в роутере).
    await callback.answer()  # pragma: no cover — все ветки покрыты выше


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


async def _handle_show_lobby_callback(
    *,
    callback: CallbackQuery,
    caravan_id: int,
    caravans: ICaravanRepository,
    caravan_participants: ICaravanParticipantRepository,
    clans: IClanRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    clock: IClock,
    presenter: CaravanPresenter,
    locale: Locale,
) -> None:
    """Логика callback-а «Показать лобби» (`caravan:show_lobby:<id>`).

    Read-only: грузит караван + участников + лидера + клан-получатель,
    рендерит актуальный текст лобби и клавиатуру с join/leave/cancel,
    редактирует сообщение в чате (best-effort).

    Если караван не найден / больше не в лобби — toast без edit-а.
    """
    caravan = await caravans.get_by_id(caravan_id=caravan_id)
    if caravan is None:
        await callback.answer(
            presenter.callback_toast_caravan_not_found(locale=locale),
            show_alert=False,
        )
        return
    if not caravan.is_in_lobby:
        await callback.answer(
            presenter.callback_toast_invalid_state(locale=locale),
            show_alert=False,
        )
        return

    leader = await players.get_by_id(player_id=caravan.leader_player_id)
    if leader is None:  # pragma: no cover — битая FK, защитный путь
        _LOGGER.error(
            "caravan.show_lobby: leader_player_id not found",
            extra={"caravan_id": caravan_id, "leader_player_id": caravan.leader_player_id},
        )
        await callback.answer(
            presenter.callback_toast_generic_error(locale=locale),
            show_alert=False,
        )
        return
    leader_view = await get_profile.execute(tg_id=leader.tg_id)
    if leader_view is None:  # pragma: no cover — лидер только что был в БД
        _LOGGER.error(
            "caravan.show_lobby: leader profile vanished",
            extra={"caravan_id": caravan_id, "leader_tg_id": leader.tg_id},
        )
        await callback.answer(
            presenter.callback_toast_generic_error(locale=locale),
            show_alert=False,
        )
        return

    receiver_clan = await clans.get_by_id(caravan.receiver_clan_id)
    if receiver_clan is None:  # pragma: no cover — битая FK
        _LOGGER.error(
            "caravan.show_lobby: receiver_clan vanished",
            extra={"caravan_id": caravan_id, "receiver_clan_id": caravan.receiver_clan_id},
        )
        await callback.answer(
            presenter.callback_toast_generic_error(locale=locale),
            show_alert=False,
        )
        return

    participants = await caravan_participants.list_by_caravan(caravan_id=caravan_id)
    cfg = balance.get().caravans
    now = clock.now()

    text = presenter.lobby_state_text(
        caravan=caravan,
        participants=participants,
        leader=leader_view.player,
        leader_display_name=leader_view.display_name,
        receiver_clan_name=receiver_clan.title.value,
        cfg=cfg,
        now=now,
        locale=locale,
    )
    keyboard = presenter.lobby_keyboard(caravan_id=caravan_id, locale=locale)

    await callback.answer()
    msg = callback.message
    if msg is None:
        return
    with contextlib.suppress(Exception):
        await msg.edit_text(text=text, reply_markup=keyboard)  # type: ignore[union-attr]


async def _handle_join_callback(  # noqa: PLR0911, PLR0912 — единая точка маппинга доменных ошибок use-case в локали
    *,
    callback: CallbackQuery,
    tg_identity: TgIdentity,
    caravan_id: int,
    role: Literal["defender", "raider"],
    join_caravan_lobby: JoinCaravanLobby,
    caravans: ICaravanRepository,
    caravan_participants: ICaravanParticipantRepository,
    clans: IClanRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    clock: IClock,
    presenter: CaravanPresenter,
    locale: Locale,
) -> None:
    """Логика callback-а «Вступить как защитник/рейдер»
    (`caravan:join_defender:<id>` / `caravan:join_raider:<id>`, D.3d).

    Зовёт `JoinCaravanLobby` use-case (он сам проверит лобби-статус,
    роль, толщину/длину и capacity). На каждый доменный отказ —
    локализованный toast. На успех — toast + refresh lobby UI
    (`lobby_state_text` + `lobby_keyboard`).
    """
    try:
        await join_caravan_lobby.execute(
            JoinCaravanLobbyInput(
                tg_id=tg_identity.tg_user_id,
                caravan_id=caravan_id,
                role=role,
                contribution_cm=None,
            ),
        )
    except CaravanNotFoundError:
        await callback.answer(
            presenter.callback_toast_caravan_not_found(locale=locale),
            show_alert=False,
        )
        return
    except CaravanLobbyClosedError:
        await callback.answer(
            presenter.callback_toast_lobby_closed(locale=locale),
            show_alert=False,
        )
        return
    except PlayerNotFoundError:
        await callback.answer(
            presenter.callback_toast_player_not_found(locale=locale),
            show_alert=False,
        )
        return
    except PlayerFrozenError:
        await callback.answer(
            presenter.callback_toast_player_frozen(locale=locale),
            show_alert=False,
        )
        return
    except AlreadyInCaravanError:
        await callback.answer(
            presenter.callback_toast_already_in_caravan(locale=locale),
            show_alert=False,
        )
        return
    except CaravanRoleConflictError:
        if role == "defender":
            text = presenter.callback_toast_role_conflict_defender(locale=locale)
        else:
            text = presenter.callback_toast_role_conflict_raider(locale=locale)
        await callback.answer(text, show_alert=False)
        return
    except CaravanRequirementError as exc:
        if exc.requirement == "thickness":
            text = presenter.callback_toast_requirement_thickness(
                required=exc.required,
                actual=exc.actual,
                locale=locale,
            )
        else:
            # `length_total` (DEFENDER/RAIDER) — единственная ветка длины,
            # доступная join-callback-у; `length_after_contribution` зашит
            # только в CARAVANEER-пути (он идёт через /caravan_join, D.3f).
            text = presenter.callback_toast_requirement_length(
                required_cm=exc.required,
                actual_cm=exc.actual,
                locale=locale,
            )
        await callback.answer(text, show_alert=False)
        return
    except CaravanCapacityExceededError as exc:
        if role == "defender":
            text = presenter.callback_toast_capacity_defender(
                limit=exc.limit,
                locale=locale,
            )
        else:
            text = presenter.callback_toast_capacity_raider(
                limit=exc.limit,
                locale=locale,
            )
        await callback.answer(text, show_alert=False)
        return

    await callback.answer(
        presenter.join_toast_success(role=role, locale=locale),
        show_alert=False,
    )
    await _refresh_lobby_message(
        callback=callback,
        caravan_id=caravan_id,
        caravans=caravans,
        caravan_participants=caravan_participants,
        clans=clans,
        players=players,
        get_profile=get_profile,
        balance=balance,
        clock=clock,
        presenter=presenter,
        locale=locale,
    )


_LEAVE_LEADER_REASON_PREFIX: Final[str] = "leader cannot leave"


async def _handle_leave_callback(
    *,
    callback: CallbackQuery,
    tg_identity: TgIdentity,
    caravan_id: int,
    leave_caravan_lobby: LeaveCaravanLobby,
    caravans: ICaravanRepository,
    caravan_participants: ICaravanParticipantRepository,
    clans: IClanRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    clock: IClock,
    presenter: CaravanPresenter,
    locale: Locale,
) -> None:
    """Логика callback-а «Покинуть» (`caravan:leave:<id>`, D.3e).

    Зовёт `LeaveCaravanLobby` use-case (он сам проверит `status==LOBBY`,
    участие игрока, не-лидерство). Маппинг доменных ошибок:

    - `CaravanNotFoundError` → toast «караван не найден».
    - `CaravanLobbyClosedError` → toast «лобби закрыто».
    - `PlayerNotFoundError` → toast «нажми /start».
    - `CaravanRoleConflictError(reason="leader cannot leave...")` →
      toast «лидер не может выйти, нажми Отменить».
    - `CaravanRoleConflictError(reason="player is not a participant...")` →
      toast «ты не участник этого каравана».

    На успех — toast (с возвратом взноса для CARAVANEER-а или короткий
    для DEFENDER/RAIDER) + refresh lobby UI (re-render `lobby_state_text`
    + клавиатура).
    """
    try:
        result = await leave_caravan_lobby.execute(
            LeaveCaravanLobbyInput(
                tg_id=tg_identity.tg_user_id,
                caravan_id=caravan_id,
            ),
        )
    except CaravanNotFoundError:
        await callback.answer(
            presenter.callback_toast_caravan_not_found(locale=locale),
            show_alert=False,
        )
        return
    except CaravanLobbyClosedError:
        await callback.answer(
            presenter.callback_toast_lobby_closed(locale=locale),
            show_alert=False,
        )
        return
    except PlayerNotFoundError:
        await callback.answer(
            presenter.callback_toast_player_not_found(locale=locale),
            show_alert=False,
        )
        return
    except CaravanRoleConflictError as exc:
        # `LeaveCaravanLobby` бросает `CaravanRoleConflictError` в двух
        # сценариях: лидер пытается выйти и игрок не участник. Различаем
        # по `reason`, чтобы дать точечный toast.
        if exc.reason.startswith(_LEAVE_LEADER_REASON_PREFIX):
            text = presenter.leave_toast_leader_cannot_leave(locale=locale)
        else:
            text = presenter.leave_toast_not_a_participant(locale=locale)
        await callback.answer(text, show_alert=False)
        return

    await callback.answer(
        presenter.leave_toast_success(
            returned_contribution_cm=result.returned_contribution_cm,
            locale=locale,
        ),
        show_alert=False,
    )
    await _refresh_lobby_message(
        callback=callback,
        caravan_id=caravan_id,
        caravans=caravans,
        caravan_participants=caravan_participants,
        clans=clans,
        players=players,
        get_profile=get_profile,
        balance=balance,
        clock=clock,
        presenter=presenter,
        locale=locale,
    )


async def _refresh_lobby_message(
    *,
    callback: CallbackQuery,
    caravan_id: int,
    caravans: ICaravanRepository,
    caravan_participants: ICaravanParticipantRepository,
    clans: IClanRepository,
    players: IPlayerRepository,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    clock: IClock,
    presenter: CaravanPresenter,
    locale: Locale,
) -> None:
    """Перерендерить lobby-сообщение после mut-callback-а (join/leave).

    Best-effort: если что-то пошло не так на read-side (битая FK,
    караван внезапно закрылся между join-ом и refresh-ем) — молчим,
    use-case уже отработал, toast пользователю отдан.
    """
    caravan = await caravans.get_by_id(caravan_id=caravan_id)
    if caravan is None or not caravan.is_in_lobby:
        return

    leader = await players.get_by_id(player_id=caravan.leader_player_id)
    if leader is None:  # pragma: no cover — битая FK
        return
    leader_view = await get_profile.execute(tg_id=leader.tg_id)
    if leader_view is None:  # pragma: no cover — лидер только что был в БД
        return

    receiver_clan = await clans.get_by_id(caravan.receiver_clan_id)
    if receiver_clan is None:  # pragma: no cover — битая FK
        return

    participants = await caravan_participants.list_by_caravan(caravan_id=caravan_id)
    cfg = balance.get().caravans
    now = clock.now()

    text = presenter.lobby_state_text(
        caravan=caravan,
        participants=participants,
        leader=leader_view.player,
        leader_display_name=leader_view.display_name,
        receiver_clan_name=receiver_clan.title.value,
        cfg=cfg,
        now=now,
        locale=locale,
    )
    keyboard = presenter.lobby_keyboard(caravan_id=caravan_id, locale=locale)
    msg = callback.message
    if msg is None:
        return
    with contextlib.suppress(Exception):
        await msg.edit_text(text=text, reply_markup=keyboard)  # type: ignore[union-attr]


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
