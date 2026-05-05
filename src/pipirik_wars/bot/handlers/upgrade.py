"""Handler команды `/upgrade` (Спринт 1.4.A, ГДД §3.2).

`/upgrade` (1.4.2) в ЛС:

1. Зовёт `GetProfile` use-case → берёт текущего игрока и его длину.
2. Считает стоимость следующего уровня по
   `progression.cost_for_upgrade(...)` через snapshot баланса.
3. Если списать нельзя по правилу 20 см (Спринт 1.2.1) — отвечает
   шаблоном «нужно ещё N см».
4. Иначе — отвечает карточкой «прокачать с N до N+1, стоимость X
   см / у тебя Y / останется Z» с инлайн-парой
   `[Подтвердить ХХХХ см] [Отменить]`.

Кнопки `[Подтвердить ХХХХ см]` / `[Отменить]`:

- `confirm` — зовёт `UpgradeThickness` use-case с тем же
  `expected_cost_cm`, что был в callback_data. Если использован
  устаревший снимок баланса (между показом и нажатием был перегружен
  YAML), use-case бросает `ConcurrencyError`, handler шлёт
  `RENDER_UPGRADE_RACE_RU`.
- `cancel` — handler снимает клавиатуру и отвечает короткой
  строкой `RENDER_UPGRADE_CANCELLED`.

В группе/супергруппе — инструкция «открой ЛС» (как у `/forest` и
`/profile`).
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.dto.inputs import UpgradeThicknessInput
from pipirik_wars.application.player import GetProfile
from pipirik_wars.application.progression import UpgradeThickness
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import (
    RENDER_UPGRADE_CANCELLED,
    RENDER_UPGRADE_RACE_RU,
    build_upgrade_proposal_keyboard,
    parse_upgrade_callback_data,
    render_upgrade_insufficient,
    render_upgrade_proposal,
    render_upgrade_success,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.progression import (
    MIN_LENGTH_AFTER_SPEND_CM,
    InsufficientLengthError,
    cost_for_upgrade,
)
from pipirik_wars.shared.errors import ConcurrencyError

router = Router(name="upgrade")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

REPLY_GROUP_RU = "🍆 Команда /upgrade доступна только в личке бота. Открой приватный чат и повтори."
REPLY_OTHER_RU = "🍆 Команда /upgrade доступна только в личке бота."
REPLY_NOT_REGISTERED_RU = (
    "🍆 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда можно будет качаться."
)

# Callback-toast-ы (≤ 200 символов, как и в forest-handler-е).
TOAST_UPGRADED = "Толщина прокачана."
TOAST_CANCELLED = "Прокачка отменена."
TOAST_PLAYER_NOT_FOUND = "Сначала нажми /start."
TOAST_INSUFFICIENT = "Недостаточно длины."
TOAST_RACE = "Стоимость изменилась."


@router.message(Command("upgrade"))
async def handle_upgrade(
    message: Message,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    balance: IBalanceConfig,
) -> None:
    """Команда `/upgrade` — показать карточку подтверждения прокачки."""
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(REPLY_GROUP_RU)
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_OTHER_RU)
        return

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:
        await message.answer(REPLY_NOT_REGISTERED_RU)
        return

    player = view.player
    cfg = balance.get()
    cost_cm = cost_for_upgrade(
        current_thickness=player.thickness.level,
        cost_base=cfg.thickness.cost_base,
        cost_exponent=cfg.thickness.cost_exponent,
    )

    if player.length.cm - cost_cm < MIN_LENGTH_AFTER_SPEND_CM:
        deficit = MIN_LENGTH_AFTER_SPEND_CM - (player.length.cm - cost_cm)
        await message.answer(
            render_upgrade_insufficient(
                current_thickness=player.thickness.level,
                cost_cm=cost_cm,
                current_length_cm=player.length.cm,
                deficit_cm=max(deficit, 1),
                min_after_spend_cm=MIN_LENGTH_AFTER_SPEND_CM,
            )
        )
        return

    text = render_upgrade_proposal(
        current_thickness=player.thickness.level,
        cost_cm=cost_cm,
        current_length_cm=player.length.cm,
        min_after_spend_cm=MIN_LENGTH_AFTER_SPEND_CM,
    )
    await message.answer(
        text,
        reply_markup=build_upgrade_proposal_keyboard(expected_cost_cm=cost_cm),
    )


@router.callback_query(F.data.startswith("upgrade:"))
async def handle_upgrade_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    upgrade_thickness: UpgradeThickness,
) -> None:
    """Обработчик инлайн-кнопок `[Подтвердить] / [Отменить]` под /upgrade."""
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    try:
        parsed = parse_upgrade_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "upgrade.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(TOAST_RACE, show_alert=False)
        await _strip_keyboard(callback)
        return

    if parsed.action == "cancel":
        await callback.answer(TOAST_CANCELLED, show_alert=False)
        await _strip_keyboard(callback)
        await _set_message_text(callback, RENDER_UPGRADE_CANCELLED)
        return

    # action == "confirm"
    try:
        result = await upgrade_thickness.execute(
            UpgradeThicknessInput(
                tg_id=tg_identity.tg_user_id,
                expected_cost_cm=parsed.expected_cost_cm,
            )
        )
    except PlayerNotFoundError:
        await callback.answer(TOAST_PLAYER_NOT_FOUND, show_alert=True)
        await _strip_keyboard(callback)
        return
    except InsufficientLengthError as exc:
        # Между показом карточки и нажатием Подтвердить игрок успел
        # потратить длину (другая активность). Показываем текст без
        # полной карточки — handler не знает свежий thickness без
        # повторного `GetProfile`, а делать второй запрос ради
        # сообщения избыточно.
        await callback.answer(TOAST_INSUFFICIENT, show_alert=False)
        await _strip_keyboard(callback)
        await _set_message_text(
            callback,
            (
                f"❌ Недостаточно длины.\n"
                f"Стоимость: {exc.cost_cm} см\n"
                f"У тебя: {exc.length_cm} см\n"
                f"Минимальный остаток: {exc.min_after_spend_cm} см\n"
                f"Не хватает: {exc.deficit_cm} см"
            ),
        )
        return
    except ConcurrencyError:
        await callback.answer(TOAST_RACE, show_alert=False)
        await _strip_keyboard(callback)
        await _set_message_text(callback, RENDER_UPGRADE_RACE_RU)
        return

    await callback.answer(TOAST_UPGRADED, show_alert=False)
    await _strip_keyboard(callback)
    await _set_message_text(
        callback,
        render_upgrade_success(
            new_thickness=result.new_thickness,
            cost_cm=result.cost_cm,
            new_length_cm=result.player_after.length.cm,
        ),
    )


async def _strip_keyboard(callback: CallbackQuery) -> None:
    """Снять inline-клавиатуру у сообщения, к которому привязан callback.

    Делает повторное нажатие невозможным со стороны UI. Любые ошибки
    edit-а (старое сообщение, недоступное `InaccessibleMessage`)
    поглощаем — это не критично для UX.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug(
            "upgrade.callback: failed to strip keyboard",
            extra={"chat_id": msg.chat.id if hasattr(msg, "chat") else None},
        )


async def _set_message_text(callback: CallbackQuery, text: str) -> None:
    """Заменить текст сообщения, к которому привязан callback.

    Аналогично `_strip_keyboard`: ошибки edit-а поглощаем, чтобы не
    падать на старых сообщениях.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_text(text)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug(
            "upgrade.callback: failed to edit message text",
            extra={"chat_id": msg.chat.id if hasattr(msg, "chat") else None},
        )


__all__ = ["handle_upgrade", "handle_upgrade_callback", "router"]
