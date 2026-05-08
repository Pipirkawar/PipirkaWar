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
from apscheduler.triggers.cron import CronTrigger

from pipirik_wars.application.caravans import CloseCaravanLobby
from pipirik_wars.application.daily_head import (
    RunDailyHeadCron,
    ScheduleDailyHeadCronJobs,
)
from pipirik_wars.application.dto.inputs import (
    CloseCaravanLobbyInput,
    EscalateChatToGlobalInput,
    ExpireLobbyEntryInput,
    FinishDungeonRunInput,
    FinishForestRunInput,
    FinishMountainRunInput,
    ForceResolveMassDuelInput,
    ResolveAfkRoundInput,
    RunDailyHeadCronInput,
    RunWeeklyClanReferralSummaryInput,
)
from pipirik_wars.application.dungeon import (
    DungeonRunFinished,
    FinishDungeonRun,
    IDungeonFinishNotifier,
)
from pipirik_wars.application.forest import (
    FinishForestRun,
    ForestRunFinished,
    IForestFinishNotifier,
)
from pipirik_wars.application.mountains import (
    FinishMountainRun,
    IMountainFinishNotifier,
    MountainRunFinished,
)
from pipirik_wars.application.pvp import (
    EscalateChatToGlobal,
    ExpireLobbyEntry,
    ForceResolveMassDuel,
    ResolveAfkRound,
)
from pipirik_wars.application.referral import (
    IWeeklyClanReferralSummaryNotifier,
    RunWeeklyClanReferralSummary,
)
from pipirik_wars.domain.clan import IClanRepository
from pipirik_wars.domain.dungeon import DungeonRunNotFoundError
from pipirik_wars.domain.forest import ForestRunNotFoundError
from pipirik_wars.domain.mountains import MountainRunNotFoundError
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import IDelayedJobScheduler

_FINISH_JOB_PREFIX: Final[str] = "forest_run_finish:"
_ESCALATE_JOB_PREFIX: Final[str] = "pvp_chat_to_global:"
_EXPIRE_JOB_PREFIX: Final[str] = "pvp_global_lobby_expire:"
_ROUND_AFK_JOB_PREFIX: Final[str] = "pvp_round_afk:"
_MASS_DUEL_AFK_JOB_PREFIX: Final[str] = "pvp_mass_duel_afk:"
_DAILY_HEAD_CRON_PREFIX: Final[str] = "daily_head_cron:"
# 3.1-B (PvE: горы и данжон, ГДД §8). Те же контракты, что у леса.
_MOUNTAIN_FINISH_JOB_PREFIX: Final[str] = "mountain_run_finish:"
_DUNGEON_FINISH_JOB_PREFIX: Final[str] = "dungeon_run_finish:"
# 3.2-B (Караваны, ГДД §9). Lobby-close-job переводит караван LOBBY → IN_BATTLE.
_CARAVAN_LOBBY_CLOSE_JOB_PREFIX: Final[str] = "caravan_lobby_close:"
# 3.2-C (Караваны, ГДД §9.5–§9.6). Battle-finish-job резолвит бой и выдаёт награды.
_CARAVAN_BATTLE_FINISH_JOB_PREFIX: Final[str] = "caravan_battle_finish:"
_DAILY_HEAD_RESCHEDULE_JOB_ID: Final[str] = "daily_head_reschedule_cron"
_WEEKLY_REFERRAL_SUMMARY_JOB_ID: Final[str] = "weekly_clan_referral_summary_cron"
#: Расписание weekly-сводки рефералов клана: вс. 18:00 UTC (ГДД §13.3).
_WEEKLY_REFERRAL_SUMMARY_DAY_OF_WEEK: Final[str] = "sun"
_WEEKLY_REFERRAL_SUMMARY_HOUR: Final[int] = 18
_WEEKLY_REFERRAL_SUMMARY_MINUTE: Final[int] = 0
_WEEKLY_REFERRAL_SUMMARY_TIMEZONE: Final[str] = "UTC"


def _job_id(run_id: int) -> str:
    return f"{_FINISH_JOB_PREFIX}{run_id}"


def _escalate_job_id(duel_id: int) -> str:
    return f"{_ESCALATE_JOB_PREFIX}{duel_id}"


def _expire_job_id(duel_id: int) -> str:
    return f"{_EXPIRE_JOB_PREFIX}{duel_id}"


def _round_afk_job_id(duel_id: int, round_num: int) -> str:
    return f"{_ROUND_AFK_JOB_PREFIX}{duel_id}:{round_num}"


def _mass_duel_afk_job_id(duel_id: int) -> str:
    return f"{_MASS_DUEL_AFK_JOB_PREFIX}{duel_id}"


def _daily_head_cron_job_id(clan_id: int) -> str:
    return f"{_DAILY_HEAD_CRON_PREFIX}{clan_id}"


def _mountain_finish_job_id(run_id: int) -> str:
    return f"{_MOUNTAIN_FINISH_JOB_PREFIX}{run_id}"


def _dungeon_finish_job_id(run_id: int) -> str:
    return f"{_DUNGEON_FINISH_JOB_PREFIX}{run_id}"


def _caravan_lobby_close_job_id(caravan_id: int) -> str:
    return f"{_CARAVAN_LOBBY_CLOSE_JOB_PREFIX}{caravan_id}"


def _caravan_battle_finish_job_id(caravan_id: int) -> str:
    return f"{_CARAVAN_BATTLE_FINISH_JOB_PREFIX}{caravan_id}"


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

    `afk_resolution_factory` (Спринт 2.1.G, опциональна) — фабрика
    `ResolveAfkRound`-use-case-а; вызывается из job-callback-а
    `_run_round_afk_job` для добивания pending-раунда случайными
    выборами через `IRandom`. Если фабрика не подвязана — лог + skip.

    `mass_duel_afk_factory` (Спринт 2.2.F, опциональна) — фабрика
    `ForceResolveMassDuel`-use-case-а; вызывается из job-callback-а
    `_run_mass_duel_afk_job` для добивания масс-боя случайными
    выборами для AFK-участников. Use-case сам идемпотентен: если
    бой уже завершён вручную — отрабатывает no-op-ветка с
    `was_already_resolved=True`. Если фабрика не подвязана — лог + skip.

    `daily_head_cron_factory` (Спринт 2.3.F.2, опциональна) — фабрика
    `RunDailyHeadCron`-use-case-а; вызывается из job-callback-а
    `_run_daily_head_cron_job` ровно в `00:00 МСК + per-clan offset`.
    Use-case сам идемпотентен: если кнопка `/clan_head` уже сработала
    раньше cron-а — `RequestDailyHead` вернёт существующего главу,
    `RunDailyHeadCron` через общий хелпер `_resolve_or_create_assignment`
    тоже корректно отработает no-op. Если фабрика не подвязана —
    лог + skip.
    """

    __slots__ = (
        "_afk_resolution_factory",
        "_caravan_lobby_close_factory",
        "_clans",
        "_daily_head_cron_factory",
        "_daily_reschedule_factory",
        "_dungeon_finish_factory",
        "_dungeon_notifier",
        "_escalate_factory",
        "_expire_factory",
        "_finish_factory",
        "_logger",
        "_mass_duel_afk_factory",
        "_mountain_finish_factory",
        "_mountain_notifier",
        "_notifier",
        "_scheduler",
        "_weekly_referral_summary_factory",
        "_weekly_referral_summary_notifier",
    )

    def __init__(
        self,
        *,
        scheduler: AsyncIOScheduler,
        finish_factory: Callable[[], FinishForestRun],
        notifier: IForestFinishNotifier | None = None,
        escalate_factory: Callable[[], EscalateChatToGlobal] | None = None,
        expire_factory: Callable[[], ExpireLobbyEntry] | None = None,
        afk_resolution_factory: Callable[[], ResolveAfkRound] | None = None,
        mass_duel_afk_factory: Callable[[], ForceResolveMassDuel] | None = None,
        daily_head_cron_factory: Callable[[], RunDailyHeadCron] | None = None,
        daily_reschedule_factory: (Callable[[], ScheduleDailyHeadCronJobs] | None) = None,
        weekly_referral_summary_factory: (Callable[[], RunWeeklyClanReferralSummary] | None) = None,
        weekly_referral_summary_notifier: (IWeeklyClanReferralSummaryNotifier | None) = None,
        mountain_finish_factory: Callable[[], FinishMountainRun] | None = None,
        mountain_notifier: IMountainFinishNotifier | None = None,
        dungeon_finish_factory: Callable[[], FinishDungeonRun] | None = None,
        dungeon_notifier: IDungeonFinishNotifier | None = None,
        caravan_lobby_close_factory: Callable[[], CloseCaravanLobby] | None = None,
        clans: IClanRepository | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._finish_factory = finish_factory
        self._notifier = notifier
        self._escalate_factory = escalate_factory
        self._expire_factory = expire_factory
        self._afk_resolution_factory = afk_resolution_factory
        self._mass_duel_afk_factory = mass_duel_afk_factory
        self._daily_head_cron_factory = daily_head_cron_factory
        self._daily_reschedule_factory = daily_reschedule_factory
        self._weekly_referral_summary_factory = weekly_referral_summary_factory
        self._weekly_referral_summary_notifier = weekly_referral_summary_notifier
        self._mountain_finish_factory = mountain_finish_factory
        self._mountain_notifier = mountain_notifier
        self._dungeon_finish_factory = dungeon_finish_factory
        self._dungeon_notifier = dungeon_notifier
        self._caravan_lobby_close_factory = caravan_lobby_close_factory
        self._clans = clans
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

    async def schedule_round_afk_resolution(
        self,
        *,
        duel_id: int,
        round_num: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_round_afk_job,
            trigger="date",
            run_date=run_at,
            args=(duel_id, round_num),
            id=_round_afk_job_id(duel_id, round_num),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_round_afk_resolution(
        self,
        *,
        duel_id: int,
        round_num: int,
    ) -> None:
        try:
            self._scheduler.remove_job(_round_afk_job_id(duel_id, round_num))
        except Exception:
            return

    async def schedule_mass_duel_afk_resolution(
        self,
        *,
        duel_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_mass_duel_afk_job,
            trigger="date",
            run_date=run_at,
            args=(duel_id,),
            id=_mass_duel_afk_job_id(duel_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_mass_duel_afk_resolution(
        self,
        *,
        duel_id: int,
    ) -> None:
        try:
            self._scheduler.remove_job(_mass_duel_afk_job_id(duel_id))
        except Exception:
            return

    async def schedule_daily_head_cron(
        self,
        *,
        clan_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_daily_head_cron_job,
            trigger="date",
            run_date=run_at,
            args=(clan_id,),
            id=_daily_head_cron_job_id(clan_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_daily_head_cron(self, *, clan_id: int) -> None:
        try:
            self._scheduler.remove_job(_daily_head_cron_job_id(clan_id))
        except Exception:
            return

    # ── Спринт 3.1-B: PvE-походы (горы и данжон, ГДД §8) ──
    #
    # Регистрируем date-job-ы, callback-и которых ловят `factory not wired`
    # (полный wiring `mountain_finish_factory` / `dungeon_finish_factory` —
    # в Спринте 3.1-E, когда появятся bot-handler-ы `/mountains` /
    # `/dungeon`). До этого callback логирует «factory not wired» и
    # тихо выходит.

    async def schedule_finish_mountain_run(
        self,
        *,
        run_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_mountain_finish_job,
            trigger="date",
            run_date=run_at,
            args=(run_id,),
            id=_mountain_finish_job_id(run_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_finish_mountain_run(self, *, run_id: int) -> None:
        try:
            self._scheduler.remove_job(_mountain_finish_job_id(run_id))
        except Exception:
            return

    async def schedule_finish_dungeon_run(
        self,
        *,
        run_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_dungeon_finish_job,
            trigger="date",
            run_date=run_at,
            args=(run_id,),
            id=_dungeon_finish_job_id(run_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_finish_dungeon_run(self, *, run_id: int) -> None:
        try:
            self._scheduler.remove_job(_dungeon_finish_job_id(run_id))
        except Exception:
            return

    async def _run_mountain_finish_job(self, run_id: int) -> None:
        """Callback `FinishMountainRun`-job-а (Спринт 3.1-E).

        Зеркалит `_run_finish_job` (лес). Если `mountain_finish_factory`
        не подвязана (recovery / unit-тесты APScheduler-а отдельно) —
        пишем warning и тихо выходим. Идемпотентность по
        `was_already_finished` валидирует use-case сам;
        notifier дополнительно фильтрует повторы.
        """
        if self._mountain_finish_factory is None:
            self._logger.warning(
                "mountain_run_finish: factory not wired",
                extra={"run_id": run_id},
            )
            return
        result: MountainRunFinished | None = None
        try:
            use_case = self._mountain_finish_factory()
            result = await use_case.execute(FinishMountainRunInput(run_id=run_id))
        except (MountainRunNotFoundError, PlayerNotFoundError) as exc:
            self._logger.warning(
                "mountain_run_finish: domain error",
                extra={"run_id": run_id, "error": type(exc).__name__},
            )
            return
        except Exception as exc:
            self._logger.exception(
                "mountain_run_finish: unexpected error",
                extra={"run_id": run_id, "error": type(exc).__name__},
            )
            return

        if self._mountain_notifier is None or result is None:
            return
        try:
            await self._mountain_notifier.notify(result)
        except Exception as exc:
            self._logger.exception(
                "mountain_run_finish: notifier failed",
                extra={"run_id": run_id, "error": type(exc).__name__},
            )

    # ── Спринт 3.2-B: караван (lobby-close, ГДД §9) ──

    async def schedule_caravan_lobby_close(
        self,
        *,
        caravan_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_caravan_lobby_close_job,
            trigger="date",
            run_date=run_at,
            args=(caravan_id,),
            id=_caravan_lobby_close_job_id(caravan_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_caravan_lobby_close(self, *, caravan_id: int) -> None:
        try:
            self._scheduler.remove_job(_caravan_lobby_close_job_id(caravan_id))
        except Exception:
            return

    async def _run_caravan_lobby_close_job(self, caravan_id: int) -> None:
        """Callback `CloseCaravanLobby`-job-а (Спринт 3.2-B).

        Срабатывает в `caravan.lobby_ends_at` и переводит караван
        `LOBBY → IN_BATTLE`. Если фабрика не подвязана (полный
        DI-wiring появится в Спринте 3.2-D bot-handler-ах) — пишем
        warning и тихо выходим. Use-case сам идемпотентен: повторный
        вызов на уже не-`LOBBY` караване вернёт `was_already_closed=True`.
        """
        if self._caravan_lobby_close_factory is None:
            self._logger.warning(
                "caravan_lobby_close: factory not wired",
                extra={"caravan_id": caravan_id},
            )
            return
        try:
            use_case = self._caravan_lobby_close_factory()
            await use_case.execute(CloseCaravanLobbyInput(caravan_id=caravan_id))
        except Exception as exc:
            self._logger.exception(
                "caravan_lobby_close: unexpected error",
                extra={"caravan_id": caravan_id, "error": type(exc).__name__},
            )
            return

    # ── Спринт 3.2-C: караван (battle-finish, ГДД §9.5–§9.6) ──

    async def schedule_caravan_battle_finish(
        self,
        *,
        caravan_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_caravan_battle_finish_job,
            trigger="date",
            run_date=run_at,
            args=(caravan_id,),
            id=_caravan_battle_finish_job_id(caravan_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_caravan_battle_finish(self, *, caravan_id: int) -> None:
        try:
            self._scheduler.remove_job(_caravan_battle_finish_job_id(caravan_id))
        except Exception:
            return

    async def _run_caravan_battle_finish_job(self, caravan_id: int) -> None:
        """Callback `FinishCaravanBattle`-job-а (Спринт 3.2-C).

        Срабатывает в `caravan.battle_ends_at` и резолвит бой
        (детерминистично от `random_seed`), выдаёт награды,
        начисляет Атаман-роль лидеру при победе. Полный wiring
        `caravan_battle_finish_factory` придёт вместе с use-case-ом
        `FinishCaravanBattle` (шаг C.7); до этого callback логирует
        warning «factory not wired» и тихо выходит. Use-case будет
        идемпотентен: повторный вызов на `FINISHED`-каравану вернёт
        `was_already_finished=True`.
        """
        self._logger.warning(
            "caravan_battle_finish: factory not wired",
            extra={"caravan_id": caravan_id},
        )

    async def _run_dungeon_finish_job(self, run_id: int) -> None:
        """Callback `FinishDungeonRun`-job-а (Спринт 3.1-E).

        Зеркалит `_run_mountain_finish_job`.
        """
        if self._dungeon_finish_factory is None:
            self._logger.warning(
                "dungeon_run_finish: factory not wired",
                extra={"run_id": run_id},
            )
            return
        result: DungeonRunFinished | None = None
        try:
            use_case = self._dungeon_finish_factory()
            result = await use_case.execute(FinishDungeonRunInput(run_id=run_id))
        except (DungeonRunNotFoundError, PlayerNotFoundError) as exc:
            self._logger.warning(
                "dungeon_run_finish: domain error",
                extra={"run_id": run_id, "error": type(exc).__name__},
            )
            return
        except Exception as exc:
            self._logger.exception(
                "dungeon_run_finish: unexpected error",
                extra={"run_id": run_id, "error": type(exc).__name__},
            )
            return

        if self._dungeon_notifier is None or result is None:
            return
        try:
            await self._dungeon_notifier.notify(result)
        except Exception as exc:
            self._logger.exception(
                "dungeon_run_finish: notifier failed",
                extra={"run_id": run_id, "error": type(exc).__name__},
            )

    async def schedule_weekly_clan_referral_summary_cron(self) -> None:
        """Зарегистрировать глобальный cron weekly-сводки рефералов (Спринт 2.4.E).

        Вс. 18:00 UTC. Идемпотентен (`replace_existing=True`).
        При отсутствии `weekly_referral_summary_factory` или
        `clans` в конструкторе журнал логируется и каллбэк тихо
        выходит (для recovery / тестов).
        """
        self._scheduler.add_job(
            self._run_weekly_clan_referral_summary_cron_job,
            trigger=CronTrigger(
                day_of_week=_WEEKLY_REFERRAL_SUMMARY_DAY_OF_WEEK,
                hour=_WEEKLY_REFERRAL_SUMMARY_HOUR,
                minute=_WEEKLY_REFERRAL_SUMMARY_MINUTE,
                timezone=_WEEKLY_REFERRAL_SUMMARY_TIMEZONE,
            ),
            id=_WEEKLY_REFERRAL_SUMMARY_JOB_ID,
            replace_existing=True,
            misfire_grace_time=None,
        )

    def start(self) -> None:
        """Запустить APScheduler. Вызывается из `run()` после `build_container`."""
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self, *, wait: bool = True) -> None:
        """Остановить APScheduler. Вызывается из `run()` в `finally`-блоке."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

    def schedule_daily_head_reschedule_cron(self) -> None:
        """Зарегистрировать ежедневный cron `00:01 МСК` для перепланирования
        per-clan daily-head-cron-job-ов на новые сутки (Спринт 2.3.F.2).

        Зовётся из `run()` после `start()`. Идемпотентен (`replace_existing=True`).
        Срабатывает в `00:01 Europe/Moscow` (минутный лаг от полуночи нужен,
        чтобы `IClock.moscow_date()` гарантированно вернул новую дату).

        Если фабрика `ScheduleDailyHeadCronJobs` не подвязана — пишем
        warning и не регистрируем триггер (полезно в unit-тестах).
        """
        if self._daily_reschedule_factory is None:
            self._logger.warning(
                "daily_head_reschedule_cron: factory not wired",
            )
            return
        self._scheduler.add_job(
            self._run_daily_head_reschedule_job,
            trigger=CronTrigger(
                hour=0,
                minute=1,
                timezone="Europe/Moscow",
            ),
            id=_DAILY_HEAD_RESCHEDULE_JOB_ID,
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def _run_daily_head_reschedule_job(self) -> None:
        """Callback ежедневного cron-а перепланирования per-clan daily-head-job-ов.

        Зовёт `ScheduleDailyHeadCronJobs.execute()`. Все исключения логируются
        и проглатываются — иначе APScheduler пометит cron как failed.
        """
        if self._daily_reschedule_factory is None:
            return
        try:
            use_case = self._daily_reschedule_factory()
            await use_case.execute()
        except Exception as exc:
            self._logger.exception(
                "daily_head_reschedule_cron: unexpected error",
                extra={"error": type(exc).__name__},
            )
            return

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

    async def _run_round_afk_job(self, duel_id: int, round_num: int) -> None:
        """Callback AFK-таймера раунда (Спринт 2.1.G).

        Зовёт `ResolveAfkRound(duel_id=..., round_num=...)`. Если
        фабрика не подвязана — лог + skip; любая другая ошибка
        логируется (APScheduler иначе пометит job-у как failed).
        Use-case сам проверяет, действителен ли таймер: если игрок
        успел отправить ход и раунд закрылся — `ResolveAfkRound`
        идёт через no-op-ветку с `was_already_resolved=True`.
        """
        if self._afk_resolution_factory is None:
            self._logger.warning(
                "pvp_round_afk: factory not wired",
                extra={"duel_id": duel_id, "round_num": round_num},
            )
            return
        try:
            use_case = self._afk_resolution_factory()
            await use_case.execute(
                ResolveAfkRoundInput(duel_id=duel_id, round_num=round_num),
            )
        except Exception as exc:
            self._logger.exception(
                "pvp_round_afk: unexpected error",
                extra={
                    "duel_id": duel_id,
                    "round_num": round_num,
                    "error": type(exc).__name__,
                },
            )
            return

    async def _run_mass_duel_afk_job(self, duel_id: int) -> None:
        """Callback AFK-таймера масс-боя (Спринт 2.2.F).

        Зовёт `ForceResolveMassDuel(duel_id=...)`. Если фабрика не
        подвязана — лог + skip; любая другая ошибка логируется
        (APScheduler иначе пометит job-у как failed).
        Use-case сам идемпотентен: если бой уже завершён вручную
        (`COMPLETED`) или отменён (`CANCELLED`) — отрабатывает
        no-op-ветка с `was_already_resolved=True`.
        """
        if self._mass_duel_afk_factory is None:
            self._logger.warning(
                "pvp_mass_duel_afk: factory not wired",
                extra={"duel_id": duel_id},
            )
            return
        try:
            use_case = self._mass_duel_afk_factory()
            await use_case.execute(ForceResolveMassDuelInput(duel_id=duel_id))
        except Exception as exc:
            self._logger.exception(
                "pvp_mass_duel_afk: unexpected error",
                extra={"duel_id": duel_id, "error": type(exc).__name__},
            )
            return

    async def _run_daily_head_cron_job(self, clan_id: int) -> None:
        """Callback per-clan cron-а «Главы клана дня» (Спринт 2.3.F.2).

        Зовёт `RunDailyHeadCron(clan_id=...)`. Если фабрика не
        подвязана — лог + skip. Все исключения use-case-а логируются
        и проглатываются — иначе APScheduler пометит job-у как failed
        и оставит её в job-store. Use-case сам идемпотентен: если
        кнопка `/clan_head` уже сработала раньше — будет no-op
        с `was_new=False`.

        Если клан заморожен (`is_frozen`), `RunDailyHeadCron` вернёт
        `None` без ошибки — это корректное поведение для frozen-клана.
        """
        if self._daily_head_cron_factory is None:
            self._logger.warning(
                "daily_head_cron: factory not wired",
                extra={"clan_id": clan_id},
            )
            return
        try:
            use_case = self._daily_head_cron_factory()
            await use_case.execute(RunDailyHeadCronInput(clan_id=clan_id))
        except Exception as exc:
            self._logger.exception(
                "daily_head_cron: unexpected error",
                extra={"clan_id": clan_id, "error": type(exc).__name__},
            )
            return

    async def _run_weekly_clan_referral_summary_cron_job(self) -> None:
        """Callback глобального cron-а weekly-сводки рефералов клана (Спринт 2.4.E).

        Срабатывает в воскресенье 18:00 UTC. Алгоритм:

        1. Если фабрика, репо кланов или нотификатор не подвязаны —
           лог + skip (для recovery / тестов APScheduler-а самого по себе).
        2. Получает список ACTIVE-кланов через `IClanRepository.list_active()`.
        3. По каждому клану зовёт `RunWeeklyClanReferralSummary(clan_id=...)`
           — отдельный use-case-инстанс на клан, чтобы UoW открывался /
           закрывался изолированно (если один клан упал, остальные
           обработаются).
        4. Если use-case вернул ненулевой `WeeklyClanReferralSummary` —
           зовёт `notifier.notify(summary)` после транзакции (нотификатор
           сам поглощает свои ошибки доставки).

        Все исключения use-case-а / нотификатора логируются и
        проглатываются. APScheduler не должен пометить cron как failed
        и снять его — карточка должна снова отстреляться через неделю.
        """
        if (
            self._weekly_referral_summary_factory is None
            or self._weekly_referral_summary_notifier is None
            or self._clans is None
        ):
            self._logger.warning(
                "weekly_clan_referral_summary_cron: dependencies not wired",
            )
            return
        try:
            clans = await self._clans.list_active()
        except Exception as exc:
            self._logger.exception(
                "weekly_clan_referral_summary_cron: list_active failed",
                extra={"error": type(exc).__name__},
            )
            return
        for clan in clans:
            if clan.id is None:
                # Clan-snapshot из репо обязан иметь id; defensive skip.
                continue
            try:
                use_case = self._weekly_referral_summary_factory()
                summary = await use_case.execute(
                    RunWeeklyClanReferralSummaryInput(clan_id=clan.id),
                )
            except Exception as exc:
                self._logger.exception(
                    "weekly_clan_referral_summary_cron: use-case failed",
                    extra={"clan_id": clan.id, "error": type(exc).__name__},
                )
                continue
            if summary is None:
                continue
            try:
                await self._weekly_referral_summary_notifier.notify(summary)
            except Exception as exc:
                # Нотификатор обязан сам поглощать TelegramAPIError; защищаемся.
                self._logger.exception(
                    "weekly_clan_referral_summary_cron: notifier failed",
                    extra={"clan_id": clan.id, "error": type(exc).__name__},
                )


__all__ = ["APSchedulerDelayedJobScheduler"]
