"""`/start` handler (Спринт 1.1.C → 1.1.D → 1.2.4 DAU Gate).

Acceptance criteria из `development_plan.md`:
- Спринт 1.1.1: `/start` отвечает в ЛС, в группе и в супергруппе.
- Спринт 1.1.3: регистрация игрока **только через ЛС** (`chat_type == "private"`).
- Спринт 1.2.4: при `DAU >= MAX_DAU` показываем «серверы переполнены,
  позиция #N».

В ЛС handler вызывает `RegisterPlayer`. В группе/супергруппе — выводит
инструкцию (бот сам не регистрирует игрока в группе, чтобы не плодить
случайных новичков из соседних чатов). В прочих типах (`channel` и т.п.)
шлём нейтральное сообщение.

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
from pipirik_wars.application.player import (
    PlayerQueued,
    PlayerRegistered,
    RegisterPlayer,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.domain.player import PlayerAlreadyRegisteredError
from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    ISignupQueueRepository,
)

router = Router(name="start")

REPLY_REGISTERED_RU = (
    "🍆 Готово! Ты зарегистрирован в Пипирик Варс.\n\n"
    "Стартовая длина — 2 см, толщина — 1 уровень. "
    "Имя и титул появятся позже — в первом походе в лес."
)
REPLY_ALREADY_RU = "🍆 Ты уже зарегистрирован. Воспользуйся /profile, чтобы посмотреть карточку."
REPLY_GROUP_RU = (
    "🍆 «Пипирик Варс» здесь!\n\n"
    "1. Сначала зарегистрируйся в личке бота: открой приватный чат и нажми /start.\n"
    "2. Потом добавь меня в группу как админа — это превратит чат в клан."
)
REPLY_OTHER_RU = "🍆 «Пипирик Варс» здесь. Команда /start доступна в ЛС или в группе."


def _format_queued(position: int) -> str:
    return (
        "🍆 Серверы переполнены — мы посадили тебя в очередь.\n\n"
        f"Твоя позиция: #{position}.\n"
        "Как только освободится место — мы тебя зарегистрируем "
        "и пришлём уведомление."
    )


@router.message(CommandStart())
async def handle_start(
    message: Message,
    tg_identity: TgIdentity | None,
    register_player: RegisterPlayer,
    signup_queue: ISignupQueueRepository,
) -> None:
    """Отвечает на `/start`.

    В ЛС — регистрирует игрока ИЛИ ставит в очередь (DAU Gate);
    в группе/супергруппе — отдаёт инструкцию; в прочих типах — нейтрально.

    `tg_identity`, `register_player` и `signup_queue` приходят через
    aiogram workflow-data DI.
    """
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind == "private":
        if tg_identity is None:
            await message.answer(REPLY_OTHER_RU)
            return
        try:
            result = await register_player.execute(
                RegisterPlayerInput(
                    tg_id=tg_identity.tg_user_id,
                    username=_username_of(message),
                    locale="ru",
                )
            )
        except PlayerAlreadyRegisteredError:
            await message.answer(REPLY_ALREADY_RU)
            return
        except AlreadyQueuedError:
            existing = await signup_queue.get_by_tg_id(tg_identity.tg_user_id)
            position = existing.position if existing is not None else 0
            await message.answer(_format_queued(position))
            return
        if isinstance(result, PlayerRegistered):
            await message.answer(REPLY_REGISTERED_RU)
        elif isinstance(result, PlayerQueued):
            await message.answer(_format_queued(result.entry.position))
        return

    if chat_kind in ("group", "supergroup"):
        await message.answer(REPLY_GROUP_RU)
        return

    await message.answer(REPLY_OTHER_RU)


def _username_of(message: Message) -> str | None:
    """Достаёт `@username` отправителя без `@`. None, если username не задан."""
    if message.from_user is None:
        return None
    name = message.from_user.username
    return name if name else None
