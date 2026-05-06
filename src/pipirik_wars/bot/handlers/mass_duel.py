"""Handler-ы команды `/clan_attack` и масс-PvP-callback-ов (Спринт 2.2.F, ГДД §7.2).

UX-схема:

* `/clan_attack <chat_id>` в групповом чате клана → старт массового PvP-боя
  клан×клан. Без аргументов — usage-сообщение, с reply на forwarded-сообщение
  из чата защищающегося клана — `chat_id` берётся из `forward_from_chat`.
* После успешного старта в групповой чат публикуется `started_card`, а каждому
  eligible-участнику обоих кланов в ЛС уходит `prompt_attack` + 3-кнопочная
  клавиатура атаки.

Inline-кнопки (callback_data префикс — `pvpm-`):

* `pvpm-attack:<duel_id>:<position>` — выбор атаки. Без вызова use-case-а:
  только редактирование текста + замена клавиатуры на блок-выбор (атака зашита
  в новый callback_data).
* `pvpm-block:<duel_id>:<attack>:<position>` — выбор блока. Handler зовёт
  `SubmitMassMove`. По возвращении проверяет:

  - если `is_ready_to_resolve` — зовёт `ResolveMassDuel`, рассылает финал
    обоим кланам (DM участникам + публичная карточка в чаты-участники);
  - иначе — кладёт «жди остальных».

DM в Telegram = `bot.send_message(chat_id=tg_id, ...)` (chat_id личного чата
равен user_id). Идемпотентность: после клика handler стирает inline-клавиатуру
через `_strip_keyboard`; повторный клик в UI становится невозможен. Use-case
сам идемпотентен на уровне доменных проверок (`MassMoveAlreadySubmittedError`,
`InvalidMassDuelStateError`).
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.dto.inputs import (
    ResolveMassDuelInput,
    StartMassDuelInput,
    SubmitMassMoveInput,
)
from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    IMessageBundle,
    IPlayerLocaleResolver,
    Locale,
)
from pipirik_wars.application.pvp import (
    ResolveMassDuel,
    StartMassDuel,
    SubmitMassMove,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import (
    MassDuelPresenter,
    parse_mass_attack_callback_data,
    parse_mass_block_callback_data,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.clan import (
    ClanFrozenError,
    IClanRepository,
)
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.pvp import (
    InvalidMassDuelStateError,
    MassDuel,
    MassDuelCooldownError,
    MassDuelNoParticipantsError,
    MassDuelNotFoundError,
    MassDuelWinner,
    MassMoveAlreadySubmittedError,
    NotAMassDuelParticipantError,
    Position,
)
from pipirik_wars.domain.security import LockAlreadyHeldError
from pipirik_wars.shared.errors import IntegrityError

router = Router(name="mass_duel")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


# ---------------------------- /clan_attack ----------------------------


@router.message(Command("clan_attack"))
async def handle_clan_attack(  # noqa: PLR0911 — каждая ветка-возврат = отдельная UX-ошибка use-case
    message: Message,
    command: CommandObject,
    bot: Bot,
    tg_identity: TgIdentity | None,
    start_mass_duel: StartMassDuel,
    clans: IClanRepository,
    players: IPlayerRepository,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    player_locale_resolver: IPlayerLocaleResolver,
    locale: Locale | None = None,
) -> None:
    """Команда `/clan_attack` — старт массового PvP-боя клан×клан."""
    presenter = MassDuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    if tg_identity is None:
        return

    chat_kind = tg_identity.chat_kind
    if chat_kind not in ("group", "supergroup"):
        await message.answer(presenter.needs_group_chat(locale=effective_locale))
        return

    attacker_chat_id = tg_identity.chat_id
    defender_chat_id = _resolve_defender_chat_id(message=message, command=command)
    if defender_chat_id is None:
        await message.answer(presenter.target_needed(locale=effective_locale))
        return

    if defender_chat_id == attacker_chat_id:
        await message.answer(presenter.self_attack(locale=effective_locale))
        return

    cfg = balance.get().pvp.mass_duel

    try:
        result = await start_mass_duel.execute(
            StartMassDuelInput(
                initiator_tg_id=tg_identity.tg_user_id,
                attacker_chat_id=attacker_chat_id,
                defender_chat_id=defender_chat_id,
            )
        )
    except IntegrityError:
        # Один из кланов не зарегистрирован (нет в БД).
        await message.answer(presenter.target_not_found(locale=effective_locale))
        return
    except ClanFrozenError:
        await message.answer(presenter.clan_frozen(locale=effective_locale))
        return
    except MassDuelCooldownError as exc:
        await message.answer(
            presenter.cooldown(
                cooldown_hours=exc.cooldown_hours,
                locale=effective_locale,
            )
        )
        return
    except MassDuelNoParticipantsError:
        await message.answer(
            presenter.no_participants(
                min_length_cm=cfg.min_length_cm,
                min_thickness_level=cfg.min_thickness_level,
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
        _LOGGER.warning("mass_duel.start: result.duel.id is None")
        return

    attacker_clan = await clans.get_by_id(duel.clan1_id)
    defender_clan = await clans.get_by_id(duel.clan2_id)
    if attacker_clan is None or defender_clan is None:
        _LOGGER.warning(
            "mass_duel.start: clans missing after start",
            extra={
                "duel_id": duel_id,
                "clan1_id": duel.clan1_id,
                "clan2_id": duel.clan2_id,
            },
        )
        return

    await message.answer(
        presenter.started_card(
            attacker_title=attacker_clan.title.value,
            defender_title=defender_clan.title.value,
            attacker_size=len(duel.clan1_member_ids),
            defender_size=len(duel.clan2_member_ids),
            timer_seconds=cfg.move_timer_seconds,
            locale=effective_locale,
        )
    )

    await _broadcast_attack_prompt(
        bot=bot,
        players=players,
        presenter=presenter,
        duel=duel,
        locale_resolver=player_locale_resolver,
        fallback_locale=effective_locale,
    )


# ---------------------------- pvpm-attack ----------------------------


@router.callback_query(F.data.startswith("pvpm-attack:"))
async def handle_mass_attack(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Callback «Атака» — без мутации; показываем block-клавиатуру."""
    if tg_identity is None or callback.data is None:
        return
    presenter = MassDuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_mass_attack_callback_data(callback.data)
    except ValueError:
        await callback.answer(
            presenter.toast_outdated(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    attack = Position(parsed.position)
    await callback.answer(
        presenter.toast_attack_selected(locale=effective_locale),
        show_alert=False,
    )
    await _set_message_text(
        callback,
        presenter.prompt_block(attack=attack, locale=effective_locale),
    )
    await _set_message_keyboard(
        callback,
        presenter.block_keyboard(
            duel_id=parsed.duel_id,
            attack=attack,
            locale=effective_locale,
        ),
    )


# ---------------------------- pvpm-block ----------------------------


@router.callback_query(F.data.startswith("pvpm-block:"))
async def handle_mass_block(  # noqa: PLR0911 — каждая ветка = отдельный toast/ошибка
    callback: CallbackQuery,
    bot: Bot,
    tg_identity: TgIdentity | None,
    submit_mass_move: SubmitMassMove,
    resolve_mass_duel: ResolveMassDuel,
    clans: IClanRepository,
    players: IPlayerRepository,
    bundle: IMessageBundle,
    player_locale_resolver: IPlayerLocaleResolver,
    locale: Locale | None = None,
) -> None:
    """Callback «Блок» — отправить ход (атака+блок) через `SubmitMassMove`."""
    if tg_identity is None or callback.data is None:
        return
    presenter = MassDuelPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_mass_block_callback_data(callback.data)
    except ValueError:
        await callback.answer(
            presenter.toast_outdated(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    try:
        submitted = await submit_mass_move.execute(
            SubmitMassMoveInput(
                duel_id=parsed.duel_id,
                tg_id=tg_identity.tg_user_id,
                attack=parsed.attack,
                block=parsed.position,
            )
        )
    except MassDuelNotFoundError:
        await callback.answer(
            presenter.toast_not_found(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return
    except NotAMassDuelParticipantError:
        await callback.answer(
            presenter.toast_not_participant(locale=effective_locale),
            show_alert=True,
        )
        return
    except InvalidMassDuelStateError:
        await callback.answer(
            presenter.toast_invalid_state(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return
    except MassMoveAlreadySubmittedError:
        await callback.answer(
            presenter.toast_already_submitted(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    await callback.answer(
        presenter.toast_move_accepted(locale=effective_locale),
        show_alert=False,
    )
    await _strip_keyboard(callback)
    await _set_message_text(
        callback,
        presenter.waiting(locale=effective_locale),
    )

    if not submitted.is_ready_to_resolve:
        return

    # Все участники отправили ходы — резолвим бой и рассылаем итог.
    try:
        resolved = await resolve_mass_duel.execute(ResolveMassDuelInput(duel_id=parsed.duel_id))
    except MassDuelNotFoundError:
        _LOGGER.warning(
            "mass_duel.resolve: duel disappeared after submit",
            extra={"duel_id": parsed.duel_id},
        )
        return
    except InvalidMassDuelStateError:
        # Кто-то другой (шедулер) уже резолвнул бой — это идемпотентный no-op.
        _LOGGER.debug(
            "mass_duel.resolve: state already non-IN_PROGRESS",
            extra={"duel_id": parsed.duel_id},
        )
        return

    await _broadcast_result(
        bot=bot,
        clans=clans,
        players=players,
        presenter=presenter,
        duel=resolved.duel,
        locale_resolver=player_locale_resolver,
        fallback_locale=effective_locale,
    )


# ---------------------------- helpers ----------------------------


def _resolve_defender_chat_id(
    *,
    message: Message,
    command: CommandObject,
) -> int | None:
    """Резолвит `defender_chat_id` из аргумента команды или forward-reply.

    Приоритет:
    1. Числовой `command.args` (отрицательное `chat_id` для group/supergroup).
    2. `message.reply_to_message.forward_from_chat.id` — пользователь
       зафорвардил сообщение из целевого клан-чата и ответил `/clan_attack`.

    Возвращает `None`, если ни один способ не сработал.
    """
    arg = (command.args or "").strip()
    if arg:
        try:
            return int(arg)
        except ValueError:
            return None

    reply = message.reply_to_message
    if reply is None:
        return None
    forward_chat = reply.forward_from_chat
    if forward_chat is None:
        return None
    return forward_chat.id


async def _broadcast_attack_prompt(
    *,
    bot: Bot,
    players: IPlayerRepository,
    presenter: MassDuelPresenter,
    duel: MassDuel,
    locale_resolver: IPlayerLocaleResolver,
    fallback_locale: Locale,
) -> None:
    """Шлёт DM-промпт «выбери атаку» каждому участнику в его локали."""
    duel_id = duel.id
    if duel_id is None:
        return
    all_member_ids = (*duel.clan1_member_ids, *duel.clan2_member_ids)
    for pid in all_member_ids:
        player = await players.get_by_id(player_id=pid)
        if player is None:
            continue
        player_locale = await locale_resolver.resolve_for_tg_id(player.tg_id) or fallback_locale
        try:
            await bot.send_message(
                chat_id=player.tg_id,
                text=presenter.prompt_attack(locale=player_locale),
                reply_markup=presenter.attack_keyboard(
                    duel_id=duel_id,
                    locale=player_locale,
                ),
            )
        except Exception:
            _LOGGER.warning(
                "mass_duel.broadcast_attack: failed to DM player",
                extra={"duel_id": duel_id, "tg_id": player.tg_id},
            )


async def _broadcast_result(
    *,
    bot: Bot,
    clans: IClanRepository,
    players: IPlayerRepository,
    presenter: MassDuelPresenter,
    duel: MassDuel,
    locale_resolver: IPlayerLocaleResolver,
    fallback_locale: Locale,
) -> None:
    """Шлёт DM-итог обоим сторонам + публичную карточку в каждый клан-чат."""
    duel_id = duel.id
    outcome = duel.final_outcome
    if duel_id is None or outcome is None:
        return

    clan1 = await clans.get_by_id(duel.clan1_id)
    clan2 = await clans.get_by_id(duel.clan2_id)
    if clan1 is None or clan2 is None:
        _LOGGER.warning(
            "mass_duel.broadcast_result: clans missing after resolve",
            extra={"duel_id": duel_id},
        )
        return

    clan1_title = clan1.title.value
    clan2_title = clan2.title.value
    winner = outcome.winner

    # DM каждому участнику персональную карточку победы/поражения/ничьей.
    for pid, side in _iter_participants(duel):
        player = await players.get_by_id(player_id=pid)
        if player is None:
            continue
        player_locale = await locale_resolver.resolve_for_tg_id(player.tg_id) or fallback_locale
        text = _build_personal_result(
            presenter=presenter,
            outcome_winner=winner,
            side=side,
            clan1_title=clan1_title,
            clan2_title=clan2_title,
            clan1_total_dealt=outcome.clan1_total_dealt,
            clan2_total_dealt=outcome.clan2_total_dealt,
            clan1_delta_cm=outcome.clan1_delta_cm,
            clan2_delta_cm=outcome.clan2_delta_cm,
            locale=player_locale,
        )
        try:
            await bot.send_message(chat_id=player.tg_id, text=text)
        except Exception:
            _LOGGER.warning(
                "mass_duel.broadcast_result: failed to DM player",
                extra={"duel_id": duel_id, "tg_id": player.tg_id},
            )

    # Публичная карточка в оба клан-чата.
    if winner is MassDuelWinner.DRAW:
        winner_clan_title = ""
        total_dealt = outcome.clan1_total_dealt
    elif winner is MassDuelWinner.CLAN1:
        winner_clan_title = clan1_title
        total_dealt = outcome.clan1_total_dealt
    else:
        winner_clan_title = clan2_title
        total_dealt = outcome.clan2_total_dealt

    chat_text = presenter.result_chat(
        winner=winner,
        winner_clan_title=winner_clan_title,
        total_dealt=total_dealt,
        locale=fallback_locale,
    )
    for chat_id in (clan1.chat_id, clan2.chat_id):
        try:
            await bot.send_message(chat_id=chat_id, text=chat_text)
        except Exception:
            _LOGGER.warning(
                "mass_duel.broadcast_result_chat: failed to send",
                extra={"duel_id": duel_id, "chat_id": chat_id},
            )


def _iter_participants(duel: MassDuel) -> list[tuple[int, str]]:
    """Возвращает `[(player_id, "clan1"|"clan2"), ...]` для всех участников."""
    out: list[tuple[int, str]] = []
    for pid in duel.clan1_member_ids:
        out.append((pid, "clan1"))
    for pid in duel.clan2_member_ids:
        out.append((pid, "clan2"))
    return out


def _build_personal_result(
    *,
    presenter: MassDuelPresenter,
    outcome_winner: MassDuelWinner,
    side: str,
    clan1_title: str,
    clan2_title: str,
    clan1_total_dealt: int,
    clan2_total_dealt: int,
    clan1_delta_cm: int,
    clan2_delta_cm: int,
    locale: Locale,
) -> str:
    """Подобрать персональный шаблон победы/поражения/ничьей."""
    if outcome_winner is MassDuelWinner.DRAW:
        delta_cm = clan1_delta_cm if side == "clan1" else clan2_delta_cm
        return presenter.result_draw_dm(delta_cm=delta_cm, locale=locale)

    winning_side = "clan1" if outcome_winner is MassDuelWinner.CLAN1 else "clan2"
    if side == winning_side:
        winner_clan_title = clan1_title if winning_side == "clan1" else clan2_title
        total_dealt = clan1_total_dealt if winning_side == "clan1" else clan2_total_dealt
        delta_cm = clan1_delta_cm if winning_side == "clan1" else clan2_delta_cm
        return presenter.result_victory_dm(
            winner_clan_title=winner_clan_title,
            total_dealt=total_dealt,
            delta_cm=delta_cm,
            locale=locale,
        )
    loser_clan_title = clan1_title if side == "clan1" else clan2_title
    total_lost = clan1_total_dealt if side != "clan1" else clan2_total_dealt
    delta_cm = clan1_delta_cm if side == "clan1" else clan2_delta_cm
    return presenter.result_defeat_dm(
        loser_clan_title=loser_clan_title,
        total_lost=total_lost,
        delta_cm=delta_cm,
        locale=locale,
    )


async def _strip_keyboard(callback: CallbackQuery) -> None:
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug("mass_duel.callback: failed to strip keyboard")


async def _set_message_text(callback: CallbackQuery, text: str) -> None:
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_text(text)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug("mass_duel.callback: failed to edit message text")


async def _set_message_keyboard(callback: CallbackQuery, keyboard: object) -> None:
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_reply_markup(reply_markup=keyboard)  # type: ignore[union-attr,arg-type]
    except Exception:
        _LOGGER.debug("mass_duel.callback: failed to edit reply_markup")


__all__ = [
    "handle_clan_attack",
    "handle_mass_attack",
    "handle_mass_block",
    "router",
]
