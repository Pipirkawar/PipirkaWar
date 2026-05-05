"""Handler-ы команды `/duel` и PvP-callback-ов (Спринт 2.1.E, ГДД §7.1).

UX-схема:

* `/duel` (без reply) в ЛС или группе → `global_only` (вызов уходит в
  глобальное лобби; реальное лобби запускается в 2.1.F).
* `/duel` как reply на сообщение оппонента в группе → `chat_then_global`
  (default per ГДД §7.1: «Чат → Глобал»).
* `/duel chat` как reply → `chat_only` (никаких эскалаций в глобал).
* `/cancel_duel <duel_id>` → отменить pending-вызов (только челленджер).

Inline-кнопки (callback_data префикс — `pvp-`):

* `pvp-accept:<duel_id>` — оппонент принимает вызов. Handler зовёт
  `AcceptDuel`, шлёт обоим игрокам в DM первый раунд-промпт (атака).
* `pvp-reject:<duel_id>` — отказ; ничего не мутирует, только toast.
  Pending-дуэль будет почищена шедулером 2.1.F при истечении TTL.
* `pvp-attack:<duel_id>:<round>:<position>` — выбор атаки. Без вызова
  use-case — только редактирование сообщения и показ блок-клавиатуры
  (атака зашита в новый callback_data).
* `pvp-block:<duel_id>:<round>:<attack>:<position>` — выбор блока.
  Handler зовёт `SubmitMove`. По возвращении проверяет:
    - дуэль завершена → result-DM обоим игрокам;
    - раунд закрыт и продвинулся → следующий attack-промпт обоим;
    - раунд ещё открыт → текущему игроку «ждём оппонента».

DM в Telegram = `bot.send_message(chat_id=tg_id, ...)` (chat_id личного
чата равен user_id).

Идемпотентность: после клика handler стирает inline-клавиатуру (через
`_strip_keyboard`); повторный клик в UI становится невозможен. Use-case
сам идемпотентен на уровне доменных проверок (`MoveAlreadySubmittedError`,
`InvalidDuelStateError`).
"""

from __future__ import annotations

import logging
from typing import Final, Literal

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.dto.inputs import (
    AcceptDuelInput,
    CancelDuelInput,
    ChallengeDuelInput,
    MatchFromLobbyInput,
    SubmitMoveInput,
)
from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    IMessageBundle,
    IPlayerLocaleResolver,
    Locale,
)
from pipirik_wars.application.pvp import (
    AcceptDuel,
    CancelDuel,
    ChallengeDuel,
    DuelMatched,
    EmptyLobby,
    LobbyEntryStale,
    MatchFromLobby,
    SubmitMove,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import (
    DuelPresenter,
    parse_accept_callback_data,
    parse_attack_callback_data,
    parse_block_callback_data,
    parse_reject_callback_data,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository, PlayerNotFoundError
from pipirik_wars.domain.progression import AnticheatSoftBanError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelNotFoundError,
    InvalidDuelStateError,
    MoveAlreadySubmittedError,
    NotADuelParticipantError,
    Position,
    PvpRequirementsNotMetError,
    SelfChallengeError,
)
from pipirik_wars.domain.security import LockAlreadyHeldError

router = Router(name="duel")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


# ---------------------------- /duel-команда ----------------------------


@router.message(Command("duel"))
async def handle_duel(  # noqa: PLR0911,PLR0912
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    challenge_duel: ChallengeDuel,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/duel` — бросить вызов на дуэль 1×1."""
    presenter = DuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    if tg_identity is None:
        return

    chat_kind = tg_identity.chat_kind
    reply = message.reply_to_message

    # Парсим режим из аргумента (по умолчанию `chat_then_global`).
    mode_arg = (command.args or "").strip().lower()
    requested_chat_only = mode_arg == "chat"

    if reply is None or reply.from_user is None:
        # Без reply: в группе показываем usage; в ЛС — global_only-вариант (Спринт 2.1.F.3).
        if chat_kind in ("group", "supergroup"):
            await message.answer(presenter.usage(locale=effective_locale))
            return
        if chat_kind != "private":
            await message.answer(presenter.usage(locale=effective_locale))
            return
        await _challenge_global_from_private(
            message=message,
            tg_identity=tg_identity,
            challenge_duel=challenge_duel,
            balance=balance,
            presenter=presenter,
            effective_locale=effective_locale,
        )
        return

    # Reply на чьё-то сообщение. Допускаем только в группе/супергруппе.
    if chat_kind not in ("group", "supergroup"):
        await message.answer(presenter.usage(locale=effective_locale))
        return

    target_user = reply.from_user
    if target_user.is_bot:
        await message.answer(presenter.target_is_bot(locale=effective_locale))
        return
    if target_user.id == tg_identity.tg_user_id:
        await message.answer(presenter.self_challenge(locale=effective_locale))
        return

    mode: Literal["chat_only", "chat_then_global"] = (
        "chat_only" if requested_chat_only else "chat_then_global"
    )
    challenger_username = _format_username(
        message.from_user.username if message.from_user else None
    )
    challenged_username = _format_username(target_user.username)

    try:
        result = await challenge_duel.execute(
            ChallengeDuelInput(
                challenger_tg_id=tg_identity.tg_user_id,
                challenged_tg_id=target_user.id,
                mode=mode,
            )
        )
    except SelfChallengeError:
        await message.answer(presenter.self_challenge(locale=effective_locale))
        return
    except PlayerNotFoundError as exc:
        # Различаем «не зарегистрирован сам челленджер» vs «не зарегистрирован оппонент».
        if exc.tg_id == tg_identity.tg_user_id:
            await message.answer(presenter.not_registered(locale=effective_locale))
        else:
            await message.answer(presenter.target_not_registered(locale=effective_locale))
        return
    except PvpRequirementsNotMetError as exc:
        await message.answer(
            presenter.requirements_not_met(
                min_length_cm=exc.required if exc.requirement == "length" else 20,
                min_thickness_level=exc.required if exc.requirement == "thickness" else 2,
                locale=effective_locale,
            )
        )
        return
    except AnticheatSoftBanError as exc:
        await message.answer(
            presenter.anticheat_blocked(
                banned_until=exc.banned_until.isoformat(),
                locale=effective_locale,
            )
        )
        return
    except LockAlreadyHeldError:
        await message.answer(presenter.lock_already_held(locale=effective_locale))
        return

    duel = result.duel
    duel_id = duel.id
    if duel_id is None:
        # Use-case всегда возвращает persisted duel; защитный fallback.
        _LOGGER.warning("duel.challenge: result.duel.id is None — skipping keyboard")
        return

    if mode == "chat_only":
        text = presenter.challenge_chat_only(
            challenger_username=challenger_username,
            challenged_username=challenged_username,
            locale=effective_locale,
        )
    else:
        text = presenter.challenge_chat_then_global(
            challenger_username=challenger_username,
            challenged_username=challenged_username,
            locale=effective_locale,
        )
    await message.answer(
        text,
        reply_markup=presenter.challenge_keyboard(
            duel_id=duel_id,
            locale=effective_locale,
        ),
    )


# ---------------------------- /duel_global-команда ----------------------------


@router.message(Command("duel_global"))
async def handle_duel_global(  # noqa: PLR0911
    message: Message,
    bot: Bot,
    tg_identity: TgIdentity | None,
    match_from_lobby: MatchFromLobby,
    players: IPlayerRepository,
    bundle: IMessageBundle,
    player_locale_resolver: IPlayerLocaleResolver,
    locale: Locale | None = None,
) -> None:
    """Команда `/duel_global` — пикап вызова из глобального FIFO-лобби (Спринт 2.1.F.3).

    Работает только в ЛС. В случае успеха разсылает attack-промпт обоим игрокам в их локали
    (как `pvp-accept`-callback).
    """
    presenter = DuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    if tg_identity is None:
        return

    if tg_identity.chat_kind != "private":
        await message.answer(presenter.global_only_in_private(locale=effective_locale))
        return

    try:
        result = await match_from_lobby.execute(
            MatchFromLobbyInput(accepter_tg_id=tg_identity.tg_user_id),
        )
    except PlayerNotFoundError:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    except PvpRequirementsNotMetError as exc:
        await message.answer(
            presenter.requirements_not_met(
                min_length_cm=exc.required if exc.requirement == "length" else 20,
                min_thickness_level=exc.required if exc.requirement == "thickness" else 2,
                locale=effective_locale,
            )
        )
        return
    except AnticheatSoftBanError as exc:
        await message.answer(
            presenter.anticheat_blocked(
                banned_until=exc.banned_until.isoformat(),
                locale=effective_locale,
            )
        )
        return
    except LockAlreadyHeldError:
        await message.answer(presenter.lock_already_held(locale=effective_locale))
        return

    if isinstance(result, EmptyLobby | LobbyEntryStale):
        await message.answer(presenter.global_empty(locale=effective_locale))
        return

    assert isinstance(result, DuelMatched)
    duel = result.duel
    challenger_username, _accepter_username = await _fetch_usernames(players=players, duel=duel)
    await message.answer(
        presenter.global_matched(
            challenger_username=challenger_username,
            locale=effective_locale,
        )
    )
    await _broadcast_attack_prompt(
        bot=bot,
        players=players,
        presenter=presenter,
        duel=duel,
        round_num=1,
        locale_resolver=player_locale_resolver,
        fallback_locale=effective_locale,
    )


# ---------------------------- /cancel_duel-команда ----------------------------


@router.message(Command("cancel_duel"))
async def handle_cancel_duel(  # noqa: PLR0911 — каждый ветка-возврат = отдельная UX-ошибка use-case
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    cancel_duel: CancelDuel,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/cancel_duel <duel_id>` — отменить pending-вызов (только челленджер)."""
    presenter = DuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    if tg_identity is None:
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.cancel_usage(locale=effective_locale))
        return
    try:
        duel_id = int(raw.split()[0])
    except ValueError:
        await message.answer(presenter.cancel_usage(locale=effective_locale))
        return
    if duel_id <= 0:
        await message.answer(presenter.cancel_usage(locale=effective_locale))
        return

    try:
        await cancel_duel.execute(CancelDuelInput(duel_id=duel_id, tg_id=tg_identity.tg_user_id))
    except DuelNotFoundError:
        await message.answer(presenter.cancel_usage(locale=effective_locale))
        return
    except NotADuelParticipantError:
        await message.answer(presenter.cancel_usage(locale=effective_locale))
        return
    except InvalidDuelStateError:
        await message.answer(presenter.cancel_usage(locale=effective_locale))
        return

    challenger_username = _format_username(
        message.from_user.username if message.from_user else None
    )
    await message.answer(
        presenter.cancelled(challenger_username=challenger_username, locale=effective_locale)
    )


# ---------------------------- pvp-accept ----------------------------


@router.callback_query(F.data.startswith("pvp-accept:"))
async def handle_pvp_accept(  # noqa: PLR0911 — каждая ветка = отдельный toast/ошибка
    callback: CallbackQuery,
    bot: Bot,
    tg_identity: TgIdentity | None,
    accept_duel: AcceptDuel,
    players: IPlayerRepository,
    bundle: IMessageBundle,
    player_locale_resolver: IPlayerLocaleResolver,
    locale: Locale | None = None,
) -> None:
    """Callback «Принять» — приём вызова + DM-промпт раунда 1 обоим."""
    if tg_identity is None or callback.data is None:
        return

    presenter = DuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_accept_callback_data(callback.data)
    except ValueError:
        await callback.answer(
            presenter.toast_outdated(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    try:
        result = await accept_duel.execute(
            AcceptDuelInput(duel_id=parsed.duel_id, tg_id=tg_identity.tg_user_id)
        )
    except DuelNotFoundError:
        await callback.answer(
            presenter.toast_duel_not_found(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return
    except NotADuelParticipantError:
        await callback.answer(
            presenter.toast_not_participant(locale=effective_locale),
            show_alert=True,
        )
        return
    except InvalidDuelStateError:
        await callback.answer(
            presenter.toast_invalid_state(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return
    except PvpRequirementsNotMetError as exc:
        await callback.answer(
            presenter.requirements_not_met(
                min_length_cm=exc.required if exc.requirement == "length" else 20,
                min_thickness_level=exc.required if exc.requirement == "thickness" else 2,
                locale=effective_locale,
            ),
            show_alert=True,
        )
        return
    except LockAlreadyHeldError:
        await callback.answer(
            presenter.lock_already_held(locale=effective_locale),
            show_alert=True,
        )
        return

    duel = result.duel
    duel_id = duel.id
    if duel_id is None:
        return

    # Toast + замена текста сообщения в чате на «вызов принят».
    challenger_username, challenged_username = await _fetch_usernames(players=players, duel=duel)
    await callback.answer(
        presenter.toast_accepted(locale=effective_locale),
        show_alert=False,
    )
    await _strip_keyboard(callback)
    await _set_message_text(
        callback,
        presenter.chat_accepted(
            challenger_username=challenger_username,
            challenged_username=challenged_username,
            locale=effective_locale,
        ),
    )

    # DM-промпт раунда 1 обоим игрокам — каждому в его локали.
    await _broadcast_attack_prompt(
        bot=bot,
        players=players,
        presenter=presenter,
        duel=duel,
        round_num=1,
        locale_resolver=player_locale_resolver,
        fallback_locale=effective_locale,
    )


# ---------------------------- pvp-reject ----------------------------


@router.callback_query(F.data.startswith("pvp-reject:"))
async def handle_pvp_reject(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Callback «Отклонить» — toast-only, без мутации состояния."""
    if tg_identity is None or callback.data is None:
        return
    presenter = DuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parse_reject_callback_data(callback.data)
    except ValueError:
        await callback.answer(
            presenter.toast_outdated(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    await callback.answer(
        presenter.toast_rejected(locale=effective_locale),
        show_alert=False,
    )
    await _strip_keyboard(callback)


# ---------------------------- pvp-attack ----------------------------


@router.callback_query(F.data.startswith("pvp-attack:"))
async def handle_pvp_attack(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Callback «Атака» — без мутации; показываем block-клавиатуру."""
    if tg_identity is None or callback.data is None:
        return
    presenter = DuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_attack_callback_data(callback.data)
    except ValueError:
        await callback.answer(
            presenter.toast_outdated(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    attack = Position(parsed.position)
    await callback.answer()
    await _set_message_text(
        callback,
        presenter.round_block_prompt(
            round_num=parsed.round_num,
            attack=attack,
            locale=effective_locale,
        ),
    )
    await _set_message_keyboard(
        callback,
        presenter.block_keyboard(
            duel_id=parsed.duel_id,
            round_num=parsed.round_num,
            attack=attack,
            locale=effective_locale,
        ),
    )


# ---------------------------- pvp-block ----------------------------


@router.callback_query(F.data.startswith("pvp-block:"))
async def handle_pvp_block(  # noqa: PLR0911 — каждая ветка = отдельный toast/ошибка + 3 продолжения
    callback: CallbackQuery,
    bot: Bot,
    tg_identity: TgIdentity | None,
    submit_move: SubmitMove,
    players: IPlayerRepository,
    bundle: IMessageBundle,
    player_locale_resolver: IPlayerLocaleResolver,
    locale: Locale | None = None,
) -> None:
    """Callback «Блок» — отправить ход (атака+блок) через `SubmitMove`."""
    if tg_identity is None or callback.data is None:
        return
    presenter = DuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_block_callback_data(callback.data)
    except ValueError:
        await callback.answer(
            presenter.toast_outdated(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    try:
        result = await submit_move.execute(
            SubmitMoveInput(
                duel_id=parsed.duel_id,
                tg_id=tg_identity.tg_user_id,
                attack=parsed.attack,
                block=parsed.position,
            )
        )
    except DuelNotFoundError:
        await callback.answer(
            presenter.toast_duel_not_found(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return
    except NotADuelParticipantError:
        await callback.answer(
            presenter.toast_not_participant(locale=effective_locale),
            show_alert=True,
        )
        return
    except InvalidDuelStateError:
        await callback.answer(
            presenter.toast_invalid_state(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return
    except MoveAlreadySubmittedError:
        await callback.answer(
            presenter.toast_already_submitted(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return
    except AnticheatSoftBanError as exc:
        await callback.answer(
            presenter.anticheat_blocked(
                banned_until=exc.banned_until.isoformat(),
                locale=effective_locale,
            ),
            show_alert=True,
        )
        return

    duel = result.duel
    await _strip_keyboard(callback)

    if result.duel_completed:
        # Финал боя: отправляем result-DM обоим игрокам.
        await _broadcast_result(
            bot=bot,
            players=players,
            presenter=presenter,
            duel=duel,
            locale_resolver=player_locale_resolver,
            fallback_locale=effective_locale,
        )
        return

    # Раунд может быть закрыт (сменился `pending_round.round_num`) или
    # ещё открыт (оппонент не походил).
    pending = duel.pending_round
    if pending is not None and pending.round_num > parsed.round_num:
        # Раунд закрылся → разсылаем следующий attack-промпт обоим.
        await _broadcast_attack_prompt(
            bot=bot,
            players=players,
            presenter=presenter,
            duel=duel,
            round_num=pending.round_num,
            locale_resolver=player_locale_resolver,
            fallback_locale=effective_locale,
        )
        return

    # Раунд ещё открыт — у текущего игрока редактируем сообщение.
    await _set_message_text(
        callback,
        presenter.round_waiting(
            round_num=parsed.round_num,
            locale=effective_locale,
        ),
    )


# ---------------------------- helpers ----------------------------


def _format_username(username: str | None) -> str:
    """Безопасное форматирование `@username` (или пустая строка)."""
    if username is None or not username.strip():
        return "—"
    return f"@{username}"


async def _challenge_global_from_private(
    *,
    message: Message,
    tg_identity: TgIdentity,
    challenge_duel: ChallengeDuel,
    balance: IBalanceConfig,
    presenter: DuelPresenter,
    effective_locale: Locale,
) -> None:
    """`/duel` в ЛС без аргументов — создаём global_only-вызов и сразу в лобби.

    `ChallengeDuel(mode="global_only")` внутри сам вызывает `lobby.enqueue` +
    `scheduler.schedule_global_lobby_expiration` — handler-у остаётся только отобразить
    успех/ошибку.
    """
    try:
        result = await challenge_duel.execute(
            ChallengeDuelInput(
                challenger_tg_id=tg_identity.tg_user_id,
                challenged_tg_id=None,
                mode="global_only",
            )
        )
    except PlayerNotFoundError:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    except PvpRequirementsNotMetError as exc:
        await message.answer(
            presenter.requirements_not_met(
                min_length_cm=exc.required if exc.requirement == "length" else 20,
                min_thickness_level=exc.required if exc.requirement == "thickness" else 2,
                locale=effective_locale,
            )
        )
        return
    except AnticheatSoftBanError as exc:
        await message.answer(
            presenter.anticheat_blocked(
                banned_until=exc.banned_until.isoformat(),
                locale=effective_locale,
            )
        )
        return
    except LockAlreadyHeldError:
        await message.answer(presenter.lock_already_held(locale=effective_locale))
        return

    duel_id = result.duel.id
    if duel_id is None:
        _LOGGER.warning("duel.private_global: result.duel.id is None")
        return

    ttl_minutes = balance.get().pvp.duel_1v1.global_lobby_ttl_minutes
    await message.answer(
        presenter.global_enqueued(
            duel_id=duel_id,
            ttl_minutes=ttl_minutes,
            locale=effective_locale,
        )
    )


async def _fetch_usernames(
    *,
    players: IPlayerRepository,
    duel: Duel,
) -> tuple[str, str]:
    """Достать `(challenger_username, challenged_username)` для duel.

    Если игрок не найден или нет username — возвращает «—».
    """
    challenger = await players.get_by_id(player_id=duel.challenger_id)
    challenged = (
        await players.get_by_id(player_id=duel.challenged_id)
        if duel.challenged_id is not None
        else None
    )
    challenger_name = (
        f"@{challenger.username.value}"
        if challenger is not None and challenger.username is not None
        else "—"
    )
    challenged_name = (
        f"@{challenged.username.value}"
        if challenged is not None and challenged.username is not None
        else "—"
    )
    return challenger_name, challenged_name


async def _broadcast_attack_prompt(
    *,
    bot: Bot,
    players: IPlayerRepository,
    presenter: DuelPresenter,
    duel: Duel,
    round_num: int,
    locale_resolver: IPlayerLocaleResolver,
    fallback_locale: Locale,
) -> None:
    """Шлёт DM-промпт «выбери атаку» обоим игрокам в их локалях."""
    duel_id = duel.id
    if duel_id is None or duel.challenged_id is None:
        return
    for pid in (duel.challenger_id, duel.challenged_id):
        player = await players.get_by_id(player_id=pid)
        if player is None:
            continue
        player_locale = await locale_resolver.resolve_for_tg_id(player.tg_id) or fallback_locale
        try:
            await bot.send_message(
                chat_id=player.tg_id,
                text=presenter.round_attack_prompt(
                    round_num=round_num,
                    locale=player_locale,
                ),
                reply_markup=presenter.attack_keyboard(
                    duel_id=duel_id,
                    round_num=round_num,
                    locale=player_locale,
                ),
            )
        except Exception:
            _LOGGER.warning(
                "duel.broadcast_attack: failed to DM player",
                extra={"duel_id": duel_id, "tg_id": player.tg_id},
            )


async def _broadcast_result(
    *,
    bot: Bot,
    players: IPlayerRepository,
    presenter: DuelPresenter,
    duel: Duel,
    locale_resolver: IPlayerLocaleResolver,
    fallback_locale: Locale,
) -> None:
    """Шлёт DM-результат обоим игрокам после завершения дуэли."""
    duel_id = duel.id
    outcome = duel.final_outcome
    if duel_id is None or outcome is None or duel.challenged_id is None:
        return

    for pid, delta_cm in (
        (duel.challenger_id, outcome.p1_delta_cm),
        (duel.challenged_id, outcome.p2_delta_cm),
    ):
        player = await players.get_by_id(player_id=pid)
        if player is None:
            continue
        player_locale = await locale_resolver.resolve_for_tg_id(player.tg_id) or fallback_locale
        new_length = player.length.cm
        if delta_cm > 0:
            text = presenter.result_victory(
                delta_cm=delta_cm,
                new_length_cm=new_length,
                locale=player_locale,
            )
        elif delta_cm < 0:
            text = presenter.result_defeat(
                delta_cm=delta_cm,
                new_length_cm=new_length,
                locale=player_locale,
            )
        else:
            text = presenter.result_draw(
                length_cm=new_length,
                locale=player_locale,
            )
        try:
            await bot.send_message(chat_id=player.tg_id, text=text)
        except Exception:
            _LOGGER.warning(
                "duel.broadcast_result: failed to DM player",
                extra={"duel_id": duel_id, "tg_id": player.tg_id},
            )


async def _strip_keyboard(callback: CallbackQuery) -> None:
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug("duel.callback: failed to strip keyboard")


async def _set_message_text(callback: CallbackQuery, text: str) -> None:
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_text(text)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug("duel.callback: failed to edit message text")


async def _set_message_keyboard(callback: CallbackQuery, keyboard: object) -> None:
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_reply_markup(reply_markup=keyboard)  # type: ignore[union-attr,arg-type]
    except Exception:
        _LOGGER.debug("duel.callback: failed to edit reply_markup")


__all__ = [
    "handle_cancel_duel",
    "handle_duel",
    "handle_duel_global",
    "handle_pvp_accept",
    "handle_pvp_attack",
    "handle_pvp_block",
    "handle_pvp_reject",
    "router",
]
