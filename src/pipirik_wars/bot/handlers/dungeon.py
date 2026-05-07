"""Handler-ы похода в данжон (Спринт 3.1-E, ГДД §8).

Зеркалит `bot/handlers/mountains.py` — отличия только в use-case-е
(`StartDungeonRun`), доменных ошибках (`AlreadyInDungeonError`,
`DungeonRequirementError`) и kind-е presenter-а
(`PveLocationKind.DUNGEON`). Гейт входа: 6-я толщина (`unlock_levels.dungeon`)
и ≥ 20 см длины (`pve.min_length_cm`).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.dto.inputs import StartDungeonRunInput
from pipirik_wars.application.dungeon import StartDungeonRun
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import DungeonPresenter, parse_pve_callback_data
from pipirik_wars.domain.dungeon import (
    AlreadyInDungeonError,
    DungeonRequirementError,
)
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.pve import PveLocationKind

router = Router(name="dungeon")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@router.message(Command("dungeon"))
async def handle_dungeon(
    message: Message,
    tg_identity: TgIdentity | None,
    start_dungeon_run: StartDungeonRun,
    get_profile: GetProfile,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/dungeon` — отправить игрока в данжон (ГДД §8)."""
    presenter = DungeonPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    try:
        started = await start_dungeon_run.execute(
            StartDungeonRunInput(tg_id=tg_identity.tg_user_id)
        )
    except PlayerNotFoundError:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    except AlreadyInDungeonError:
        await message.answer(presenter.already_in(locale=effective_locale))
        return
    except DungeonRequirementError as exc:
        if exc.requirement == "thickness":
            await message.answer(
                presenter.requirement_thickness(
                    required=exc.required,
                    actual=exc.actual,
                    locale=effective_locale,
                )
            )
        else:
            await message.answer(
                presenter.requirement_length(
                    required_cm=exc.required,
                    actual_cm=exc.actual,
                    locale=effective_locale,
                )
            )
        return

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:
        _LOGGER.warning(
            "dungeon.start: profile not found right after start",
            extra={"tg_id": tg_identity.tg_user_id, "run_id": started.run.id},
        )
        await message.answer(
            presenter.started_fallback(
                cooldown_minutes=started.cooldown_minutes,
                locale=effective_locale,
            )
        )
        return

    text = presenter.started(
        player=view.player,
        display_name=view.display_name,
        cooldown_minutes=started.cooldown_minutes,
        locale=effective_locale,
    )
    await message.answer(text)


@router.callback_query(F.data.startswith("dungeon:"))
async def handle_dungeon_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Обработчик инлайн-кнопок «надеть / выбросить» под карточкой возврата."""
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    presenter = DungeonPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_pve_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "dungeon.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.toast_drop_mismatch(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    if parsed.kind is not PveLocationKind.DUNGEON:
        await callback.answer(
            presenter.toast_drop_mismatch(locale=effective_locale),
            show_alert=False,
        )
        return

    if parsed.action == "equip_item":
        await callback.answer(
            presenter.toast_item_equipped_placeholder(locale=effective_locale),
            show_alert=False,
        )
    else:
        await callback.answer(
            presenter.toast_item_dropped(locale=effective_locale),
            show_alert=False,
        )
    await _strip_keyboard(callback)


async def _strip_keyboard(callback: CallbackQuery) -> None:
    msg = callback.message
    if msg is None:
        return
    with contextlib.suppress(Exception):
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]


__all__ = ["router"]
