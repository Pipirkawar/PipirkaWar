"""Порты нотификаций каравана (Спринт 3.2-D, ГДД §9.3 / §9.5–§9.6).

Зеркалят :class:`IMountainFinishNotifier` / :class:`IForestFinishNotifier`:
use-case-ы каравана (`CloseCaravanLobby`, `FinishCaravanBattle`) применяют
доменные изменения внутри `IUnitOfWork` и возвращают результат-DTO
(`ClosedCaravanLobby`, `CaravanBattleFinished`). Само сообщение в
Telegram-чаты (отправителя и получателя) шлётся **после** коммита
транзакции — поэтому нотификаторы живут в отдельных портах и зовутся
из APScheduler-callback-ов
(`infrastructure/scheduler/aps.py::_run_caravan_lobby_close_job`,
`..._run_caravan_battle_finish_job`) сразу после успешного `execute(...)`.

Контракт:

- `notify(...)` зовётся **только** при «новом» исходе:
    * `ICaravanLobbyCloseNotifier.notify` — только если
      `result.was_already_closed is False` (повторный close-job не
      спамит чат);
    * `ICaravanBattleFinishNotifier.notify` — только если
      `result.was_already_finished is False` и `result.result is not None`.
- Любые ошибки доставки (`TelegramAPIError`, network) реализация
  обязана поглотить и залогировать — нотификация best-effort.
"""

from __future__ import annotations

import abc

from pipirik_wars.application.caravans.close_caravan_lobby import ClosedCaravanLobby
from pipirik_wars.application.caravans.finish_caravan_battle import CaravanBattleFinished


class ICaravanLobbyCloseNotifier(abc.ABC):
    """Контракт «оповестить чаты sender/receiver о старте боя каравана»."""

    @abc.abstractmethod
    async def notify(self, result: ClosedCaravanLobby) -> None:
        """Отправить «лобби закрыто, бой начался» в чат-отправитель и
        чат-получатель (ГДД §9.3).

        Best-effort: ошибки доставки логируются, не пробрасываются.
        """


class ICaravanBattleFinishNotifier(abc.ABC):
    """Контракт «оповестить чаты sender/receiver об исходе боя каравана»."""

    @abc.abstractmethod
    async def notify(self, result: CaravanBattleFinished) -> None:
        """Отправить «караван доставлен» (или «караван разграблен»)
        в чат-отправитель и чат-получатель (ГДД §9.5–§9.6).

        Best-effort: ошибки доставки логируются, не пробрасываются.
        """


__all__ = [
    "ICaravanBattleFinishNotifier",
    "ICaravanLobbyCloseNotifier",
]
