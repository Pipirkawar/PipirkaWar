"""Порт нотификации финиша похода в лес (Спринт 1.3.D, ПД §1.3.2 / ГДД §8.2).

`FinishForestRun` (Спринт 1.3.C) применяет результат и возвращает
`ForestRunFinished`. Само же сообщение «вернулся из леса» отправляется
**после** коммита транзакции — поэтому нотификатор живёт в отдельном
порту и зовётся из APScheduler-callback-а (`infrastructure/scheduler/aps.py`)
сразу после успешного `execute(...)`.

Почему отдельный порт, а не аргумент `FinishForestRun`:

- Use-case (application-слой) не должен знать про Telegram (нет I/O
  внутри транзакции, см. ГДД §0.3).
- Если нотификация упадёт — игровое состояние всё равно консистентно
  (длина начислена, лок снят, аудит записан). Notifier — best-effort.
- `notify(...)` вызывается **только** при `was_already_finished=False`
  (повторный finish-job не спамит игрока).

Реализация (`TelegramForestFinishNotifier`,
`infrastructure/telegram/forest_notifier.py`) знает про aiogram `Bot`
и про `IBalanceConfig` (нужен для расчёта `DisplayName` в момент
отправки), но сам контракт здесь — чистый: один метод `notify(...)`.
"""

from __future__ import annotations

import abc

from pipirik_wars.application.forest.finish_run import ForestRunFinished


class IForestFinishNotifier(abc.ABC):
    """Контракт «прислать игроку сообщение о возвращении из леса»."""

    @abc.abstractmethod
    async def notify(self, result: ForestRunFinished) -> None:
        """Отправить сообщение «вернулся из леса» (ГДД §8.2).

        Вызывается **только** при `result.was_already_finished is False`
        (повторные стрельбы finish-job-а игнорируются вызывающей стороной).

        Любые ошибки доставки (`TelegramAPIError`, network) реализация
        обязана поглотить и залогировать — нотификация best-effort, она
        не должна приводить к повторному запуску finish-job-а.
        """


__all__ = ["IForestFinishNotifier"]
