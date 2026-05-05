"""Handler команды `/oracle` (Спринт 1.4.B, ГДД §11).

`/oracle` (ПД 1.4.4) в ЛС:

1. Зовёт `InvokeOracle` use-case с `tg_id` игрока и локалью `"ru"`
   (Спринт 1.5 заменит хардкод на язык из `LocaleMiddleware`).
2. На успех — рендерит «🔮 предсказание + N см» через
   `render_oracle_success(...)` и шлёт игроку.
3. На `OracleAlreadyUsedTodayError` — рендерит «возвращайся завтра»
   через `render_oracle_already_used(...)` с временем до сброса.
4. На `PlayerNotFoundError` — отдаёт текст «нажми /start».

В группе/супергруппе — короткая инструкция «открой ЛС».
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.dto.inputs import InvokeOracleInput
from pipirik_wars.application.oracle import InvokeOracle
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import (
    RENDER_ORACLE_GROUP_RU,
    RENDER_ORACLE_NOT_REGISTERED_RU,
    RENDER_ORACLE_OTHER_RU,
    render_oracle_already_used,
    render_oracle_success,
)
from pipirik_wars.domain.oracle import OracleAlreadyUsedTodayError
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import IClock

router = Router(name="oracle")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

# Локаль каталога предсказаний (Спринт 1.5 — i18n).
_DEFAULT_LOCALE: Final[str] = "ru"


def _user_display(message: Message) -> str:
    """Имя игрока для подстановки в шаблон `{user}` — first_name либо username."""
    user = message.from_user
    if user is None:
        return "друг"
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return "друг"


@router.message(Command("oracle"))
async def handle_oracle(
    message: Message,
    tg_identity: TgIdentity | None,
    invoke_oracle: InvokeOracle,
    clock: IClock,
) -> None:
    """Команда `/oracle` — получить предсказание + случайную прибавку длины."""
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(RENDER_ORACLE_GROUP_RU)
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(RENDER_ORACLE_OTHER_RU)
        return

    try:
        result = await invoke_oracle.execute(
            InvokeOracleInput(
                tg_id=tg_identity.tg_user_id,
                locale=_DEFAULT_LOCALE,
            )
        )
    except PlayerNotFoundError:
        await message.answer(RENDER_ORACLE_NOT_REGISTERED_RU)
        return
    except OracleAlreadyUsedTodayError as exc:
        await message.answer(
            render_oracle_already_used(
                moscow_date=exc.moscow_date,
                now=clock.now(),
            )
        )
        return

    await message.answer(
        render_oracle_success(
            template_text=result.result.template.text,
            bonus_cm=result.result.bonus_cm,
            new_length_cm=result.player_after.length.cm,
            user_display=_user_display(message),
        )
    )
