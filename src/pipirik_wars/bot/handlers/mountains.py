"""Handler-ы похода в горы (Спринт 3.1-E, ГДД §8).

Тонкий aiogram-слой по образцу `bot/handlers/forest.py`. Ключевые
отличия от леса:

- Гейт входа: `MountainsRequirementError` (`requirement="thickness"` —
  нужна 3-я толщина / `requirement="length"` — нужно ≥ 20 см длины).
- Дроп — только предметы (`PveItemDrop`), имена не дропаются (ГДД §2.5).
- Callback-кнопки «надеть / выбросить» — placeholder-toast-ы без мутации
  (механика экипировки прибудет в Спринте 3.4); handler снимает
  inline-клавиатуру после первого клика, чтобы повторное нажатие
  фактически заблокировано на UI-стороне.

Сообщение «вернулся из гор» отправляется не handler-ом, а нотификатором
`TelegramMountainFinishNotifier`, который зовёт APScheduler-callback
после успешного `FinishMountainRun.execute(...)` (см.
`infrastructure/scheduler/aps.py::_run_mountain_finish_job`).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.dto.inputs import StartMountainRunInput
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.mountains import StartMountainRun
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import MountainsPresenter, parse_pve_callback_data
from pipirik_wars.domain.mountains import (
    AlreadyInMountainsError,
    MountainsRequirementError,
)
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.pve import PveLocationKind

router = Router(name="mountains")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@router.message(Command("mountains"))
async def handle_mountains(
    message: Message,
    tg_identity: TgIdentity | None,
    start_mountain_run: StartMountainRun,
    get_profile: GetProfile,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/mountains` — отправить игрока в горы (ГДД §8)."""
    presenter = MountainsPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    try:
        started = await start_mountain_run.execute(
            StartMountainRunInput(tg_id=tg_identity.tg_user_id)
        )
    except PlayerNotFoundError:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    except AlreadyInMountainsError:
        await message.answer(presenter.already_in(locale=effective_locale))
        return
    except MountainsRequirementError as exc:
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
            "mountains.start: profile not found right after start",
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


@router.callback_query(F.data.startswith("mountains:"))
async def handle_mountains_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Обработчик инлайн-кнопок «надеть / выбросить» под карточкой возврата.

    Реальной мутации нет (механика экипировки и инвентаря — Спринт 3.4),
    handler шлёт placeholder-toast и снимает клавиатуру, чтобы повторный
    клик на стороне UI был невозможен.
    """
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    presenter = MountainsPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_pve_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "mountains.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.toast_drop_mismatch(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    if parsed.kind is not PveLocationKind.MOUNTAINS:
        # Промах роутинга (callback на dungeon-кнопку прилетел в горный
        # router из-за более общего префикс-фильтра в будущем). Защитный
        # ack без мутации.
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
    else:  # drop_item
        await callback.answer(
            presenter.toast_item_dropped(locale=effective_locale),
            show_alert=False,
        )
    await _strip_keyboard(callback)


async def _strip_keyboard(callback: CallbackQuery) -> None:
    """Снять inline-клавиатуру у сообщения, к которому привязан callback.

    Делает повторное нажатие невозможным со стороны UI. Любые ошибки
    edit-а (сообщение слишком старое, уже отредактировано) поглощаем —
    это не критично для UX.
    """
    msg = callback.message
    if msg is None:
        return
    # CallbackQuery.message — `Message | InaccessibleMessage`; у обоих есть
    # `edit_reply_markup`, но у InaccessibleMessage он бросит
    # `TelegramAPIError`, которое мы поглотим ниже (best-effort).
    with contextlib.suppress(Exception):
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]


__all__ = ["router"]
