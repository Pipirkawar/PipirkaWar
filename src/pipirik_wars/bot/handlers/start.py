"""`/start` handler (Спринт 1.1.C → расширен в 1.1.D).

Acceptance criteria из `development_plan.md`:
- Спринт 1.1.1: `/start` отвечает в ЛС, в группе и в супергруппе.
- Спринт 1.1.3: регистрация игрока **только через ЛС** (`chat_type == "private"`).

В ЛС handler вызывает `RegisterPlayer`. В группе/супергруппе — выводит
инструкцию (бот сам не регистрирует игрока в группе, чтобы не плодить
случайных новичков из соседних чатов). В прочих типах (`channel` и т.п.)
шлём нейтральное сообщение.

Все ошибки use-case-а ловит `ErrorHandlerMiddleware`
(см. `bot/middlewares/error_handler.py`); здесь handler не пытается
обрабатывать `DomainError`-ы вручную, кроме одной business-as-usual
ситуации — `PlayerAlreadyRegisteredError` (она ожидаема при повторном
`/start` и заслуживает отдельного дружелюбного текста).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from pipirik_wars.application.dto.inputs import RegisterPlayerInput
from pipirik_wars.application.player import RegisterPlayer
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.domain.player import PlayerAlreadyRegisteredError

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


@router.message(CommandStart())
async def handle_start(
    message: Message,
    tg_identity: TgIdentity | None,
    register_player: RegisterPlayer,
) -> None:
    """Отвечает на `/start`.

    В ЛС — регистрирует игрока (или возвращает «уже зарегистрирован»);
    в группе/супергруппе — отдаёт инструкцию; в прочих типах — нейтрально.

    `tg_identity` и `register_player` приходят через aiogram
    workflow-data DI (`dispatcher["register_player"] = ...`).
    """
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind == "private":
        if tg_identity is None:
            # Странная ситуация — `/start` в ЛС без user_id. На всякий
            # случай отвечаем нейтрально и не регистрируем «никого».
            await message.answer(REPLY_OTHER_RU)
            return
        try:
            await register_player.execute(
                RegisterPlayerInput(
                    tg_id=tg_identity.tg_user_id,
                    username=_username_of(message),
                    locale="ru",
                )
            )
        except PlayerAlreadyRegisteredError:
            await message.answer(REPLY_ALREADY_RU)
            return
        await message.answer(REPLY_REGISTERED_RU)
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
