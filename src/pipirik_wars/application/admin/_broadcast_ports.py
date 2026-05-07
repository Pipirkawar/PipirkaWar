"""Внутренние порты для broadcast-команд (Спринт 2.5-D.4, ГДД §18.6.5).

Два output-порта, которые `RunBroadcastAnnouncement` использует для
доставки сообщений и для запуска фоновой задачи:

* `IBroadcastSender` — абстракция «отправить одно текстовое сообщение
  игроку и классифицировать результат». Production-реализация
  (`bot/notifications/admin_broadcast.py::TelegramBroadcastSender`)
  оборачивает aiogram `Bot.send_message`, ловит `TelegramForbiddenError`
  (игрок забанил бота) → `"blocked"`, любые другие `TelegramAPIError` /
  network-ошибки → `"failed"`. Тестовая реализация
  (`tests/fakes/broadcast_sender.py::FakeBroadcastSender`) детерминирует
  ответы по таблице, чтобы покрыть все три исхода без сети.

* `IBroadcastTaskSpawner` — абстракция «запустить корутину рассылки в
  фоне, чтобы handler `/confirm` ответил быстро». Production-реализация
  оборачивает `asyncio.create_task(...)`; тестовая
  (`tests/fakes/broadcast_task_spawner.py::InlineBroadcastTaskSpawner`)
  await-ит coro синхронно — это даёт детерминированный порядок и
  упрощает assert-ы поверх audit-записей в unit-тестах.

Префикс `_` в названии модуля помечает его как внутренний для
`application/admin/`: контракты не реэкспортируются из
`application/admin/__init__.py` (handler-у достаточно конкретных
классов из `bot/notifications/admin_broadcast.py`, чтобы не плодить
импорты в DI-провязке). Если в Спринте 4.5 появится web-панель админа,
которая тоже захочет рассылать через тот же sender — порт всё равно
останется тут, а web-handler получит его через DI.
"""

from __future__ import annotations

import abc
from collections.abc import Awaitable
from typing import Literal

#: Возможные исходы доставки одного сообщения. Не Enum, а Literal —
#: проще и для логов, и для `audit-after`-словарей: значение само себе
#: ключ статистики (`{"sent": ..., "failed": ..., "blocked": ...}`).
BroadcastSendResult = Literal["sent", "failed", "blocked"]


class IBroadcastSender(abc.ABC):
    """Контракт «отправить одно сообщение в личный чат игрока».

    Реализация **обязана** возвращать строковый литерал из
    `BroadcastSendResult`, а не бросать исключение, чтобы цикл рассылки
    в `RunBroadcastAnnouncement` не прерывался на одном недоставленном
    адресате. Любые транспортные ошибки нормализуются в `"failed"`;
    `TelegramForbiddenError` (игрок остановил бота / закрыл чат) — в
    `"blocked"`, чтобы super-admin в `/audit` видел, сколько игроков
    «выпали» из адресной базы и можно было планировать reactivation-кампанию.
    """

    @abc.abstractmethod
    async def send(self, *, tg_id: int, text: str) -> BroadcastSendResult:
        """Отправить `text` игроку с `tg_id`. Возвращает исход доставки.

        Реализация обязана:

        * не бросать исключений — все ошибки превращать в `"failed"` /
          `"blocked"`. Внешний цикл рассылки иначе остановится на первой
          ошибке, и оставшиеся адресаты не получат сообщение;
        * логировать тело ошибки (на стороне самой реализации), чтобы
          super-admin мог разобраться, что именно сломалось у конкретного
          адресата;
        * быть стабильно async-безопасной: вызывающий уже throttle-ит
          частоту вызовов, sender внутри ничего дополнительно не ждёт.
        """


class IBroadcastTaskSpawner(abc.ABC):
    """Контракт «запустить фоновую задачу рассылки».

    Нужен, чтобы `_dispatch_announce` (handler фазы-2 после `/confirm`)
    смог ответить админу «отправляю N игрокам» и сразу вернуть управление,
    а сама рассылка дороботала параллельно. Production-реализация —
    `asyncio.create_task(...)`; в тестах используется
    `InlineBroadcastTaskSpawner`, который await-ит coro немедленно, чтобы
    тест-кейсы могли проверить итоговое состояние audit-лога без
    `asyncio.sleep`-ов.

    Контракт намеренно тонкий: один метод `spawn(coro)` без id-возврата.
    Если когда-нибудь понадобится отслеживать «активные broadcast-job-ы»
    или их отменять — будет добавлен отдельный порт уровня инфраструктуры
    (а не тут, в application).
    """

    @abc.abstractmethod
    def spawn(self, coro: Awaitable[None]) -> None:
        """Запустить coro в фоне. Реализация обязана не блокировать вызов.

        Production-`asyncio.create_task(...)` сохраняет ссылку на task в
        coro-планировщике — садится поверх event-loop-а и может быть
        отменена при `loop.shutdown()`. Это допустимое поведение: при
        рестарте бота недозавершённая рассылка просто прекратится, на
        старте recovery-механизма для broadcast-а не предусмотрено
        (recipients-список меняется быстро, повторная посылка спустя
        час неуместна).
        """


__all__ = [
    "BroadcastSendResult",
    "IBroadcastSender",
    "IBroadcastTaskSpawner",
]
