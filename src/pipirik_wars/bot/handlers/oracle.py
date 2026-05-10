"""Handler команды `/oracle` (Спринт 1.4.B → 1.5.D, ГДД §11).

`/oracle` (ПД 1.4.4) в ЛС:

1. Зовёт `InvokeOracle` use-case с `tg_id` игрока и текущей `Locale`
   (резолвенной `LocaleMiddleware`-ом — из `tg.language_code` или
   из `player.locale_override` после Спринта 1.5.E).
2. На успех — рендерит «🔮 предсказание + N см» через
   `OraclePresenter.success(...)` и шлёт игроку.
3. На `OracleAlreadyUsedTodayError` — рендерит «возвращайся завтра»
   через `OraclePresenter.already_used(...)` с временем до сброса.
4. На `PlayerNotFoundError` — отдаёт `OraclePresenter.not_registered(...)`.

В группе/супергруппе — короткая инструкция «открой ЛС». 1.5.D убрал
hardcoded `RENDER_ORACLE_*_RU`-константы и `_DEFAULT_LOCALE = "ru"`:
теперь каталог предсказаний и тексты ответов идут на одной локали
из `IMessageBundle`.
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.dto.inputs import InvokeOracleInput
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.oracle import InvokeOracle
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import OraclePresenter
from pipirik_wars.domain.oracle import OracleAlreadyUsedTodayError
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import IClock

router = Router(name="oracle")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


def _user_display(message: Message) -> str:
    """Имя игрока для подстановки в шаблон `{user}` — first_name либо username.

    Fallback `"друг"` остаётся RU-only — это запасной путь для случая,
    когда у Telegram-сообщения нет `from_user`. По факту такого не
    бывает у обычных handler-ов; шаблон каталога предсказаний почти
    всегда содержит `{ user }` и подменяет фактическим именем.
    """
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
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/oracle` — получить предсказание + случайную прибавку длины."""
    presenter = OraclePresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    try:
        result = await invoke_oracle.execute(
            InvokeOracleInput(
                tg_id=tg_identity.tg_user_id,
                locale=effective_locale.code,
            )
        )
    except PlayerNotFoundError:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    except OracleAlreadyUsedTodayError as exc:
        await message.answer(
            presenter.already_used(
                moscow_date=exc.moscow_date,
                now=clock.now(),
                locale=effective_locale,
            )
        )
        return

    await message.answer(
        presenter.success(
            template_text=result.result.template.text,
            base_cm=result.base_cm,
            tribe_bonus_cm=result.tribe_bonus_cm,
            n_active_tribes=result.n_active_tribes,
            new_length_cm=result.player_after.length.cm,
            user_display=_user_display(message),
            locale=effective_locale,
        )
    )
