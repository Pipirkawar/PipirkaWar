"""Handler-ы похода в лес (Спринт 1.3.D, ГДД §8.2).

Команда `/forest` (1.3.1) в ЛС:
- Зовёт `StartForestRun` use-case (Спринт 1.3.B).
- При успехе шлёт сообщение «🌲 N ушёл в лес на M минут...» (1.3.2).
- Ловит:
    - `PlayerNotFoundError` → инструкция нажать `/start`.
    - `AlreadyInForestError` → «вы уже в лесу, дождитесь возвращения».

В группе/супергруппе — инструкция «открой ЛС» (как у `/profile`/`/start`).
Это совпадает с MVP-контрактом регистрации: лес идёт через личку,
позже broadcast в чат клана появится через отдельный порт.

Callback-handler-ы инлайн-кнопок «вернулся из леса» (1.3.6, ГДД §8.2):
- `forest:apply_name:<run_id>` (только для `NameDrop` при существующем
  имени) → `ApplyForestNameDrop` заменяет имя.
- `forest:drop_name:<run_id>`, `forest:drop_item:<run_id>`,
  `forest:equip_item:<run_id>` — без мутации состояния (выбросить /
  пока не реализованная экипировка). Handler только убирает клавиатуру
  и шлёт `callback_query.answer(...)` с пояснительным toast-ом.

Идемпотентность повторного нажатия:
- После первого клика handler `edit_reply_markup(reply_markup=None)` —
  кнопок больше нет, второй клик в Telegram-UI невозможен.
- `ApplyForestNameDrop` сам идемпотентен (проверка `player.name == new_name`),
  так что race-конфликт двух quick-кликов разрешается без мутации.
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.dto.inputs import (
    ApplyForestNameDropInput,
    StartForestRunInput,
)
from pipirik_wars.application.forest import ApplyForestNameDrop, StartForestRun
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import (
    ForestCallbackData,
    parse_forest_callback_data,
    render_forest_started,
)
from pipirik_wars.domain.forest import (
    AlreadyInForestError,
    ForestDropMismatchError,
    ForestRunNotFoundError,
    ForestRunOwnershipError,
)
from pipirik_wars.domain.player import PlayerNotFoundError

router = Router(name="forest")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

REPLY_GROUP_RU = "🍆 Команда /forest доступна только в личке бота. Открой приватный чат и повтори."
REPLY_OTHER_RU = "🍆 Команда /forest доступна только в личке бота."
REPLY_NOT_REGISTERED_RU = (
    "🍆 Похоже, ты ещё не зарегистрирован. Нажми /start в этом чате — и тогда сможешь идти в лес."
)
REPLY_ALREADY_IN_FOREST_RU = (
    "🌲 Ты уже в лесу — дождись возвращения. Бот пришлёт сообщение, когда поход закончится."
)

# Callback-toast-ы (`answer(text)`). Telegram ограничивает 200 символов;
# этого достаточно для коротких ack-ов.
TOAST_NAME_APPLIED = "Имя заменено."
TOAST_NAME_ALREADY_APPLIED = "Имя уже было применено."
TOAST_NAME_DROPPED = "Имя выброшено."
TOAST_ITEM_DROPPED = "Предмет выброшен."
TOAST_ITEM_EQUIPPED_PLACEHOLDER = "Экипировка появится позже — предмет пока в инвентаре."
TOAST_FOREIGN_BUTTON = "Эта кнопка не для тебя."
TOAST_RUN_NOT_FOUND = "Этот лес уже неактивен."
TOAST_DROP_MISMATCH = "Кнопка устарела."
TOAST_PLAYER_NOT_FOUND = "Сначала нажми /start."


@router.message(Command("forest"))
async def handle_forest(
    message: Message,
    tg_identity: TgIdentity | None,
    start_forest_run: StartForestRun,
    get_profile: GetProfile,
) -> None:
    """Команда `/forest` — отправить игрока в лес.

    `get_profile` нужен для рендера полного ника (с актуальным
    `DisplayName` по балансу) в сообщении «ушёл в лес». Это держит
    handler в синхронизации с тем, что покажет `/profile` — единая
    точка вычисления `DisplayName` (`IBalanceConfig.display_name_for`).
    """
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(REPLY_GROUP_RU)
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_OTHER_RU)
        return

    try:
        started = await start_forest_run.execute(StartForestRunInput(tg_id=tg_identity.tg_user_id))
    except PlayerNotFoundError:
        await message.answer(REPLY_NOT_REGISTERED_RU)
        return
    except AlreadyInForestError:
        await message.answer(REPLY_ALREADY_IN_FOREST_RU)
        return

    # Полный ник = текущая длина игрока (новая длина начисляется только
    # после `FinishForestRun`). Поэтому `GetProfile` после `StartForestRun`
    # отдаёт актуальный для этого момента `DisplayName`.
    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:
        # Игрок только что прошёл `StartForestRun` — `GetProfile` его обязан
        # увидеть. Защитный fallback — без полного ника, чтобы не потерять
        # сообщение игроку.
        _LOGGER.warning(
            "forest.start: profile not found right after start",
            extra={"tg_id": tg_identity.tg_user_id, "run_id": started.run.id},
        )
        await message.answer(f"🌲 Ты ушёл в лес на {started.cooldown_minutes} минут...")
        return

    text = render_forest_started(
        player=view.player,
        display_name=view.display_name,
        cooldown_minutes=started.cooldown_minutes,
    )
    await message.answer(text)


@router.callback_query(F.data.startswith("forest:"))
async def handle_forest_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    apply_forest_name_drop: ApplyForestNameDrop,
) -> None:
    """Обработчик инлайн-кнопок под сообщением «вернулся из леса»."""
    if tg_identity is None or callback.data is None or callback.message is None:
        # `tg_identity` нет — middleware пропустил event без `from_user`.
        # `data`/`message` нет — это служебный callback (Telegram такого
        # не шлёт для inline-кнопок, но защищаемся). Никакого ack — пусть
        # клиент таймаутит сам.
        return

    try:
        parsed = parse_forest_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "forest.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(TOAST_DROP_MISMATCH, show_alert=False)
        await _strip_keyboard(callback)
        return

    action = parsed.action
    if action == "apply_name":
        await _handle_apply_name(callback, tg_identity, parsed, apply_forest_name_drop)
    elif action == "drop_name":
        await callback.answer(TOAST_NAME_DROPPED, show_alert=False)
        await _strip_keyboard(callback)
    elif action == "equip_item":
        await callback.answer(TOAST_ITEM_EQUIPPED_PLACEHOLDER, show_alert=False)
        await _strip_keyboard(callback)
    elif action == "drop_item":
        await callback.answer(TOAST_ITEM_DROPPED, show_alert=False)
        await _strip_keyboard(callback)


async def _handle_apply_name(
    callback: CallbackQuery,
    tg_identity: TgIdentity,
    parsed: ForestCallbackData,
    apply_forest_name_drop: ApplyForestNameDrop,
) -> None:
    """Обработать клик «Заменить» — заменить имя через `ApplyForestNameDrop`."""
    try:
        result = await apply_forest_name_drop.execute(
            ApplyForestNameDropInput(
                run_id=parsed.run_id,
                tg_id=tg_identity.tg_user_id,
            )
        )
    except ForestRunNotFoundError:
        await callback.answer(TOAST_RUN_NOT_FOUND, show_alert=False)
        await _strip_keyboard(callback)
        return
    except PlayerNotFoundError:
        await callback.answer(TOAST_PLAYER_NOT_FOUND, show_alert=True)
        return
    except ForestRunOwnershipError:
        # Чужой `tg_id` тыкает в чужую кнопку — это аномалия (callback
        # форварднут или сериализован), пишем audit-warning и тихо
        # игнорируем для пользователя.
        _LOGGER.warning(
            "forest.callback: ownership mismatch",
            extra={
                "run_id": parsed.run_id,
                "tg_id": tg_identity.tg_user_id,
            },
        )
        await callback.answer(TOAST_FOREIGN_BUTTON, show_alert=False)
        return
    except ForestDropMismatchError:
        # Кнопка `apply_name` пришла на `ItemDrop`/`NoDrop` — формат
        # callback_data сменился между релизами. Снимаем клавиатуру.
        _LOGGER.warning(
            "forest.callback: drop mismatch",
            extra={"run_id": parsed.run_id, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(TOAST_DROP_MISMATCH, show_alert=False)
        await _strip_keyboard(callback)
        return

    if result.was_already_applied:
        await callback.answer(TOAST_NAME_ALREADY_APPLIED, show_alert=False)
    else:
        await callback.answer(TOAST_NAME_APPLIED, show_alert=False)
    await _strip_keyboard(callback)


async def _strip_keyboard(callback: CallbackQuery) -> None:
    """Снять inline-клавиатуру у сообщения, к которому привязан callback.

    Делает повторное нажатие невозможным со стороны UI (см. acceptance
    1.3.6 «повторное нажатие игнорируется»). Любые ошибки edit-а
    (сообщение слишком старое / уже отредактировано) поглощаем — это не
    критично для UX.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        # CallbackQuery.message — `Message | InaccessibleMessage`; у обоих
        # есть `edit_reply_markup`, но у InaccessibleMessage он бросит
        # `TelegramAPIError("message inaccessible")` — поэтому ловим всё.
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug(
            "forest.callback: failed to strip keyboard",
            extra={"chat_id": msg.chat.id if hasattr(msg, "chat") else None},
        )


__all__ = ["handle_forest", "handle_forest_callback", "router"]
