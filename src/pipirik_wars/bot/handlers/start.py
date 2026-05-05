"""`/start` handler (Спринт 1.1.C → 1.1.D → 1.2.4 DAU Gate → 1.5.B i18n).

Acceptance criteria из `development_plan.md`:
- Спринт 1.1.1: `/start` отвечает в ЛС, в группе и в супергруппе.
- Спринт 1.1.3: регистрация игрока **только через ЛС** (`chat_type == "private"`).
- Спринт 1.2.4: при `DAU >= MAX_DAU` показываем «серверы переполнены,
  позиция #N».
- Спринт 1.5.B: все ответы — через `StartPresenter`/`IMessageBundle`,
  никаких hardcoded-строк в handler-е.

В ЛС handler вызывает `RegisterPlayer` (с `locale = data["locale"].code`,
полученным из `LocaleMiddleware` — ПД 1.5.2). В группе/супергруппе —
выводит инструкцию (бот сам не регистрирует игрока в группе, чтобы не
плодить случайных новичков из соседних чатов). В прочих типах
(`channel` и т.п.) шлём нейтральное сообщение.

Все технические ошибки use-case-а ловит `ErrorHandlerMiddleware`;
handler ловит только три бизнес-кейса: уже зарегистрирован
(`PlayerAlreadyRegisteredError`), уже стоит в очереди (`AlreadyQueuedError`),
и discriminated union `RegisterPlayerResult` для развилки registered/queued.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from pipirik_wars.application.dto.inputs import RegisterPlayerInput
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.player import (
    PlayerQueued,
    PlayerRegistered,
    RegisterPlayer,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.start import StartPresenter
from pipirik_wars.domain.player import PlayerAlreadyRegisteredError
from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    ISignupQueueRepository,
)

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    tg_identity: TgIdentity | None,
    register_player: RegisterPlayer,
    signup_queue: ISignupQueueRepository,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Отвечает на `/start`.

    В ЛС — регистрирует игрока ИЛИ ставит в очередь (DAU Gate);
    в группе/супергруппе — отдаёт инструкцию; в прочих типах — нейтрально.

    `tg_identity`, `register_player`, `signup_queue` и `bundle` приходят
    через aiogram workflow-data DI. `locale` приходит из
    `LocaleMiddleware` (там же ключ `data["locale"]`); `None` означает,
    что middleware не сработал (в тестах допустимо) — берём fallback EN.
    """
    presenter = StartPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind == "private":
        if tg_identity is None:
            await message.answer(presenter.other(locale=effective_locale))
            return
        try:
            result = await register_player.execute(
                RegisterPlayerInput(
                    tg_id=tg_identity.tg_user_id,
                    username=_username_of(message),
                    locale=effective_locale.code,
                )
            )
        except PlayerAlreadyRegisteredError:
            await message.answer(presenter.already(locale=effective_locale))
            return
        except AlreadyQueuedError:
            existing = await signup_queue.get_by_tg_id(tg_identity.tg_user_id)
            position = existing.position if existing is not None else 0
            await message.answer(
                presenter.queued(locale=effective_locale, position=position),
            )
            return
        if isinstance(result, PlayerRegistered):
            await message.answer(presenter.registered(locale=effective_locale))
        elif isinstance(result, PlayerQueued):
            await message.answer(
                presenter.queued(
                    locale=effective_locale,
                    position=result.entry.position,
                ),
            )
        return

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return

    await message.answer(presenter.other(locale=effective_locale))


def _username_of(message: Message) -> str | None:
    """Достаёт `@username` отправителя без `@`. None, если username не задан."""
    if message.from_user is None:
        return None
    name = message.from_user.username
    return name if name else None
