"""Адаптер `IDelayedJobScheduler` поверх APScheduler 3.x.

Использует `AsyncIOScheduler` со стандартным in-memory job-store.
В production (Спринт 1.3.D + 1.3.4 ConfigurePersistentJobStore) можно
будет подменить на `SQLAlchemyJobStore`, чтобы задачи переживали
рестарт процесса. На уровне 1.3.C мы держим планировщик в памяти —
после рестарта бот должен делать recovery: пройтись по `forest_runs`
со `status='in_progress'` и пере-запланировать `finish`-job-ы (это
будет в 1.3.D, hook на старте процесса).

`AsyncIOScheduler.start()` запускает внутренний планировщик в текущем
event-loop-е. `shutdown()` дожидается завершения уже выполняющихся
job-ов (`wait=True` — поведение по умолчанию). И то и другое —
ответственность композиционного root-а (`bot/main.py`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Final

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pipirik_wars.application.dto.inputs import (
    EscalateChatToGlobalInput,
    ExpireLobbyEntryInput,
    FinishForestRunInput,
)
from pipirik_wars.application.forest import (
    FinishForestRun,
    ForestRunFinished,
    IForestFinishNotifier,
)
from pipirik_wars.application.pvp import EscalateChatToGlobal, ExpireLobbyEntry
from pipirik_wars.domain.forest import ForestRunNotFoundError
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import IDelayedJobScheduler

_FINISH_JOB_PREFIX: Final[str] = "forest_run_finish:"
_ESCALATE_JOB_PREFIX: Final[str] = "pvp_chat_to_global:"
_EXPIRE_JOB_PREFIX: Final[str] = "pvp_global_lobby_expire:"


def _job_id(run_id: int) -> str:
    return f"{_FINISH_JOB_PREFIX}{run_id}"


def _escalate_job_id(duel_id: int) -> str:
    return f"{_ESCALATE_JOB_PREFIX}{duel_id}"


def _expire_job_id(duel_id: int) -> str:
    return f"{_EXPIRE_JOB_PREFIX}{duel_id}"


class APSchedulerDelayedJobScheduler(IDelayedJobScheduler):
    """Production-адаптер: APScheduler `AsyncIOScheduler`.

    `finish_factory` — фабрика, которая возвращает свежий
    `FinishForestRun`-use-case (с активной транзакцией / зависимостями).
    Это нужно потому, что job исполняется в фоне и **не** должен
    повторно использовать сессию текущего bot-handler-а.

    `notifier` (Спринт 1.3.D, опционален) — `IForestFinishNotifier`,
    который зовётся **после** успешного `FinishForestRun.execute(...)`,
    чтобы отправить игроку Telegram-сообщение «вернулся из леса»
    (ГДД §8.2). Зовётся вне транзакции — ошибки доставки игнорируются
    самим notifier-ом.

    `escalate_factory` / `expire_factory` (Спринт 2.1.F.2, опциональны
    до полной DI-провязки в F.3) — фабрики `EscalateChatToGlobal` /
    `ExpireLobbyEntry`-use-case-ов; если `None`, `schedule_*` всё равно
    регистрирует job в APScheduler (для recovery / тестов APScheduler-а
    самого по себе), но при срабатывании job-а callback логирует
    «factory not wired» и тихо выходит.
    """

    __slots__ = (
        "_escalate_factory",
        "_expire_factory",
        "_finish_factory",
        "_logger",
        "_notifier",
        "_scheduler",
    )

    def __init__(
        self,
        *,
        scheduler: AsyncIOScheduler,
        finish_factory: Callable[[], FinishForestRun],
        notifier: IForestFinishNotifier | None = None,
        escalate_factory: Callable[[], EscalateChatToGlobal] | None = None,
        expire_factory: Callable[[], ExpireLobbyEntry] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._finish_factory = finish_factory
        self._notifier = notifier
        self._escalate_factory = escalate_factory
        self._expire_factory = expire_factory
        self._logger = logger or logging.getLogger(__name__)

    async def schedule_finish_forest_run(
        self,
        *,
        run_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_finish_job,
            trigger="date",
            run_date=run_at,
            args=(run_id,),
            id=_job_id(run_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_finish_forest_run(self, *, run_id: int) -> None:
        try:
            self._scheduler.remove_job(_job_id(run_id))
        except Exception:
            # APScheduler.JobLookupError; конкретный класс зависит от версии.
            # Cancel — best-effort: если job-ы нет, цели достигнуты.
            return

    async def schedule_chat_to_global_escalation(
        self,
        *,
        duel_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_escalation_job,
            trigger="date",
            run_date=run_at,
            args=(duel_id,),
            id=_escalate_job_id(duel_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_chat_to_global_escalation(self, *, duel_id: int) -> None:
        try:
            self._scheduler.remove_job(_escalate_job_id(duel_id))
        except Exception:
            return

    async def schedule_global_lobby_expiration(
        self,
        *,
        duel_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_expiration_job,
            trigger="date",
            run_date=run_at,
            args=(duel_id,),
            id=_expire_job_id(duel_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_global_lobby_expiration(self, *, duel_id: int) -> None:
        try:
            self._scheduler.remove_job(_expire_job_id(duel_id))
        except Exception:
            return

    def start(self) -> None:
        """Запустить APScheduler. Вызывается из `run()` после `build_container`."""
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self, *, wait: bool = True) -> None:
        """Остановить APScheduler. Вызывается из `run()` в `finally`-блоке."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

    async def _run_finish_job(self, run_id: int) -> None:
        """Callback, который APScheduler вызывает в `run_at`.

        Любые доменные ошибки логируем и проглатываем — APScheduler
        иначе пометит job-у как «failed» и оставит её в job-store-е.
        После успешного `FinishForestRun.execute(...)` зовём notifier
        (если он есть) — это шлёт игроку «вернулся из леса» (ГДД §8.2).
        """
        result: ForestRunFinished | None = None
        try:
            use_case = self._finish_factory()
            result = await use_case.execute(FinishForestRunInput(run_id=run_id))
        except (ForestRunNotFoundError, PlayerNotFoundError) as exc:
            self._logger.warning(
                "forest_run_finish: domain error",
                extra={"run_id": run_id, "error": type(exc).__name__},
            )
            return
        except Exception as exc:  # последний барьер — APScheduler иначе пометит job-у «failed»
            self._logger.exception(
                "forest_run_finish: unexpected error",
                extra={"run_id": run_id, "error": type(exc).__name__},
            )
            return

        if self._notifier is None or result is None:
            return
        try:
            await self._notifier.notify(result)
        except Exception as exc:  # notifier обязан сам ловить TelegramAPIError, но защищаемся
            self._logger.exception(
                "forest_run_finish: notifier failed",
                extra={"run_id": run_id, "error": type(exc).__name__},
            )

    async def _run_escalation_job(self, duel_id: int) -> None:
        """Callback `EscalateChatToGlobal`-job-а (Спринт 2.1.F.2).

        Если фабрика не подвязана (до полной DI-провязки в F.3) —
        логируем и тихо выходим, чтобы APScheduler не помечал job-у
        «failed».
        """
        if self._escalate_factory is None:
            self._logger.warning(
                "pvp_chat_to_global: factory not wired",
                extra={"duel_id": duel_id},
            )
            return
        try:
            use_case = self._escalate_factory()
            await use_case.execute(EscalateChatToGlobalInput(duel_id=duel_id))
        except Exception as exc:
            self._logger.exception(
                "pvp_chat_to_global: unexpected error",
                extra={"duel_id": duel_id, "error": type(exc).__name__},
            )
            return

    async def _run_expiration_job(self, duel_id: int) -> None:
        """Callback `ExpireLobbyEntry`-job-а (Спринт 2.1.F.2).

        Если фабрика не подвязана — логируем и тихо выходим.
        """
        if self._expire_factory is None:
            self._logger.warning(
                "pvp_global_lobby_expire: factory not wired",
                extra={"duel_id": duel_id},
            )
            return
        try:
            use_case = self._expire_factory()
            await use_case.execute(ExpireLobbyEntryInput(duel_id=duel_id))
        except Exception as exc:
            self._logger.exception(
                "pvp_global_lobby_expire: unexpected error",
                extra={"duel_id": duel_id, "error": type(exc).__name__},
            )
            return


__all__ = ["APSchedulerDelayedJobScheduler"]
