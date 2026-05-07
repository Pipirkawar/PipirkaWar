"""Порт нотификации финиша похода в горы (Спринт 3.1-E, ГДД §8.2).

Зеркалит `IForestFinishNotifier` (см. `application/forest/notifier.py`).
Use-case `FinishMountainRun` (3.1-B) применяет результат и возвращает
`MountainRunFinished`. Само сообщение «вернулся из гор» отправляется
**после** коммита транзакции — поэтому нотификатор живёт в отдельном
порту и зовётся из APScheduler-callback-а
(`infrastructure/scheduler/aps.py::_run_mountain_finish_job`) сразу
после успешного `execute(...)`.

Контракт:
- `notify(...)` зовётся **только** при `result.was_already_finished is False`
  (повторный finish-job не спамит игрока).
- Любые ошибки доставки (`TelegramAPIError`, network) реализация обязана
  поглотить и залогировать — нотификация best-effort.
"""

from __future__ import annotations

import abc

from pipirik_wars.application.mountains.finish_run import MountainRunFinished


class IMountainFinishNotifier(abc.ABC):
    """Контракт «прислать игроку сообщение о возвращении из гор»."""

    @abc.abstractmethod
    async def notify(self, result: MountainRunFinished) -> None:
        """Отправить сообщение «вернулся из гор» (ГДД §8.2)."""


__all__ = ["IMountainFinishNotifier"]
