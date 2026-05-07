"""Тестовые реализации портов broadcast-а (Спринт 2.5-D.4).

`FakeBroadcastSender` — детерминирует исход доставки по таблице
`results_by_tg_id` и фиксирует список отправленных сообщений в
`sent_log`, чтобы тест мог assert-нуть «отправили N штук с таким
текстом».

`InlineBroadcastTaskSpawner` — синхронный спавнер: вместо
`asyncio.create_task(coro)` await-ит coro немедленно. Это даёт
детерминированный порядок «handler вернул управление, audit-запись
уже легла в фейковый аудит» в unit-тестах handler-а, без необходимости
spinning the event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass, field

from pipirik_wars.application.admin._broadcast_ports import (
    BroadcastSendResult,
    IBroadcastSender,
    IBroadcastTaskSpawner,
)


@dataclass
class FakeBroadcastSender(IBroadcastSender):
    """In-memory `IBroadcastSender` с программируемыми исходами."""

    #: Что вернуть для конкретного `tg_id`. Если не задано — `default_result`.
    results_by_tg_id: dict[int, BroadcastSendResult] = field(default_factory=dict)
    default_result: BroadcastSendResult = "sent"
    #: История вызовов: `(tg_id, text, result)`.
    sent_log: list[tuple[int, str, BroadcastSendResult]] = field(default_factory=list)

    async def send(self, *, tg_id: int, text: str) -> BroadcastSendResult:
        result = self.results_by_tg_id.get(tg_id, self.default_result)
        self.sent_log.append((tg_id, text, result))
        return result


@dataclass
class InlineBroadcastTaskSpawner(IBroadcastTaskSpawner):
    """Синхронный `IBroadcastTaskSpawner` для unit-тестов.

    `spawn(coro)` вместо `asyncio.create_task(coro)` запускает coro
    немедленно через `asyncio.get_event_loop().run_until_complete`-style,
    но в тестах под `pytest-asyncio` мы внутри уже работаем в loop-е,
    поэтому используем хитрый трюк: складываем coro в `pending` и
    тест сам await-ит их через `await spawner.run_pending()`.

    Это даёт детерминизм: тест явно знает, в какой момент рассылка
    стартует, и assert-ы аудита можно делать ДО или ПОСЛЕ запуска.
    """

    pending: list[Awaitable[None]] = field(default_factory=list)

    def spawn(self, coro: Awaitable[None]) -> None:
        self.pending.append(coro)

    async def run_pending(self) -> None:
        """Запустить все накопленные coro по порядку и очистить очередь."""
        coros = self.pending[:]
        self.pending.clear()
        for coro in coros:
            await coro


@dataclass
class TaskGroupBroadcastTaskSpawner(IBroadcastTaskSpawner):
    """Альтернатива на основе `asyncio.create_task`-list-а.

    Используется в integration-тесте throttle-а, где нужно реально
    отдать управление scheduler-у между батчами. Отличается от
    `InlineBroadcastTaskSpawner` тем, что spawn действительно создаёт
    background-task; вызывающий должен в конце await-нуть `wait_all()`.
    """

    tasks: list[asyncio.Task[None]] = field(default_factory=list)

    def spawn(self, coro: Awaitable[None]) -> None:
        # mypy не знает, что Awaitable можно прокинуть в create_task —
        # на практике production-coro всегда `Coroutine`-формы; в тестах
        # тоже передаём корутины, не raw `Awaitable`.
        task: asyncio.Task[None] = asyncio.create_task(coro)  # type: ignore[arg-type]
        self.tasks.append(task)

    async def wait_all(self) -> None:
        if self.tasks:
            await asyncio.gather(*self.tasks)
            self.tasks.clear()


__all__ = [
    "FakeBroadcastSender",
    "InlineBroadcastTaskSpawner",
    "TaskGroupBroadcastTaskSpawner",
]
