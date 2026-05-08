"""Порты нотификаций рейд-боссов (Спринт 3.3-D, ГДД §10).

Зеркалят :class:`ICaravanLobbyCloseNotifier` /
:class:`ICaravanBattleFinishNotifier`: use-case-ы рейд-босса
(`CloseBossLobby`, `RunBossRound`, `FinishBossFight`) применяют
доменные изменения внутри `IUnitOfWork` и возвращают результат-DTO
(`BossLobbyClosed`, `BossRoundResolved`, `BossFightFinished`). Само
сообщение в Telegram-чат саммонера / рейдеров шлётся **после** коммита
транзакции — поэтому нотификаторы живут в отдельных портах и зовутся
из APScheduler-callback-ов
(`infrastructure/scheduler/aps.py::_run_boss_lobby_close_job`,
`..._run_boss_round_tick_job`, `..._run_boss_fight_finish_job`)
сразу после успешного `execute(...)`.

Контракт:

- `notify(...)` зовётся **только** при «новом» исходе:
    * `IBossLobbyCloseNotifier.notify` — только если
      `result.was_already_closed is False` (повторный close-job не
      спамит чат);
    * `IBossRoundTickNotifier.notify` — только если
      `result.was_already_finished is False` и `result.result is not None`
      (есть что показать: per-raider-исходы, урон боссу, выбывшие);
    * `IBossFightFinishNotifier.notify` — только если
      `result.was_already_finished is False`.
- Любые ошибки доставки (`TelegramAPIError`, network) реализация
  обязана поглотить и залогировать — нотификация best-effort.
"""

from __future__ import annotations

import abc

from pipirik_wars.application.bosses.close_boss_lobby import BossLobbyClosed
from pipirik_wars.application.bosses.finish_boss_fight import BossFightFinished
from pipirik_wars.application.bosses.run_boss_round import BossRoundResolved


class IBossLobbyCloseNotifier(abc.ABC):
    """Контракт «оповестить чат саммонера о старте боя с боссом» (ГДД §10.3)."""

    @abc.abstractmethod
    async def notify(self, result: BossLobbyClosed) -> None:
        """Отправить «лобби закрыто, бой начался» в чат, где был
        вызов `/boss summon` (или личный чат саммонера).

        Best-effort: ошибки доставки логируются, не пробрасываются.
        """


class IBossRoundTickNotifier(abc.ABC):
    """Контракт «оповестить участников об итогах прошедшего раунда» (ГДД §10.4)."""

    @abc.abstractmethod
    async def notify(self, result: BossRoundResolved) -> None:
        """Отправить карточку раунда: урон боссу, попадания / промахи /
        выбытия рейдеров, текущая «длина босса». Если `is_finished=True`
        — это последний раунд (победа рейдеров или поражение); сама
        выдача наград идёт через :class:`IBossFightFinishNotifier`.

        Best-effort: ошибки доставки логируются, не пробрасываются.
        """


class IBossFightFinishNotifier(abc.ABC):
    """Контракт «оповестить участников об исходе боя с боссом» (ГДД §10.5)."""

    @abc.abstractmethod
    async def notify(self, result: BossFightFinished) -> None:
        """Отправить «бой закончен» — победа рейдеров (раздача длин и
        свитков) или поражение (босс получил +Σlength_at_join, рейдеры
        потеряли Δ).

        Best-effort: ошибки доставки логируются, не пробрасываются.
        """


__all__ = [
    "IBossFightFinishNotifier",
    "IBossLobbyCloseNotifier",
    "IBossRoundTickNotifier",
]
