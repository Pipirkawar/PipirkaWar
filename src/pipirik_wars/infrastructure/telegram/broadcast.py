"""Production-имплементации `IBroadcastSender` / `IBroadcastTaskSpawner`.

`/announce`-flow (Спринт 2.5-D.4) живёт в application/-слое и работает
через два abstract-порта:

* `IBroadcastSender` — отправка одного сообщения; `aiogram`-зависимость
  вынесена сюда (`AiogramBroadcastSender`). Все сетевые/Telegram-ошибки
  (`TelegramRetryAfter`, `TelegramForbiddenError`,
  `TelegramBadRequest`, любые сетевые) приводятся к
  `BroadcastSendResult` — `"sent"`, `"failed"` или `"blocked"`.
  Контракт use-case-а — никогда не падать наружу.
* `IBroadcastTaskSpawner` — non-blocking запуск coro фоновой задачи;
  `AsyncIOBroadcastTaskSpawner` использует `asyncio.create_task(...)`.

Эти адаптеры держат собственные ссылки на запущенные task-и, чтобы
GC не стёр их раньше времени (Python 3.12, `asyncio.create_task`-ловушка).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import Final

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from pipirik_wars.application.admin import (
    BroadcastSendResult,
    IBroadcastSender,
    IBroadcastTaskSpawner,
)

_LOGGER: Final = logging.getLogger(__name__)


class AiogramBroadcastSender(IBroadcastSender):
    """Отправка через `aiogram.Bot.send_message(...)`.

    На любую `TelegramForbiddenError` (бот заблокирован пользователем
    или удалён из чата) возвращает `"blocked"` — это нормальный кейс
    для `/announce` и не должен считаться ошибкой. На любую другую
    ошибку (сетевую, `TelegramBadRequest`, `TelegramRetryAfter`) —
    `"failed"`. Контракт use-case-а — никаких throw-ов наружу.
    """

    __slots__ = ("_bot",)

    def __init__(self, *, bot: Bot) -> None:
        self._bot = bot

    async def send(self, *, tg_id: int, text: str) -> BroadcastSendResult:
        try:
            await self._bot.send_message(chat_id=tg_id, text=text)
        except TelegramForbiddenError:
            # Юзер заблокировал бота → нормальный кейс, считаем blocked.
            return "blocked"
        except (TelegramRetryAfter, TelegramBadRequest):
            _LOGGER.warning(
                "broadcast_send_failed_telegram",
                extra={"tg_id": tg_id},
                exc_info=True,
            )
            return "failed"
        except Exception:
            _LOGGER.warning(
                "broadcast_send_failed_unknown",
                extra={"tg_id": tg_id},
                exc_info=True,
            )
            return "failed"
        return "sent"


class AsyncIOBroadcastTaskSpawner(IBroadcastTaskSpawner):
    """Запускает coro фоновой задачи через `asyncio.create_task(...)`.

    Хранит сильную ссылку на задачу до её завершения — иначе сборщик
    мусора может закрыть task-у до её выполнения (Python 3.12+).
    """

    __slots__ = ("_tasks",)

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.create_task(_swallow_exceptions(coro))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


async def _swallow_exceptions(coro: Awaitable[None]) -> None:
    """Логируем любое необработанное исключение, чтобы оно не утопало.

    `IBroadcastTaskSpawner.spawn` обещает не бросать; внутренний
    `_run_broadcast_and_report` в handler-е сам ловит ошибки и шлёт
    «прогресс failed»-сообщение, так что эта обёртка — финальная
    подушка от unobserved exception в asyncio.
    """
    try:
        await coro
    except Exception:
        _LOGGER.exception("broadcast_background_task_unhandled")


class NoopBroadcastSender(IBroadcastSender):
    """Заглушка для режимов без `aiogram.Bot` (CLI-скрипты, scheduler-only).

    Возвращает `"failed"` для каждого вызова, чтобы `RunBroadcastAnnouncement`
    отчитался, что доставка невозможна, а не молча наврал «всё отправилось».
    """

    async def send(self, *, tg_id: int, text: str) -> BroadcastSendResult:
        _LOGGER.warning(
            "broadcast_send_skipped_no_bot",
            extra={"tg_id": tg_id, "text_len": len(text)},
        )
        return "failed"


__all__ = [
    "AiogramBroadcastSender",
    "AsyncIOBroadcastTaskSpawner",
    "NoopBroadcastSender",
]
