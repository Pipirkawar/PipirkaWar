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
from datetime import UTC, datetime
from typing import Final

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pipirik_wars.application.bosses import (
    BossFightFinished,
    BossLobbyClosed,
    BossRoundResolved,
    CloseBossLobby,
    FinishBossFight,
    IBossFightFinishNotifier,
    IBossLobbyCloseNotifier,
    IBossRoundTickNotifier,
    RunBossRound,
)
from pipirik_wars.application.caravans import (
    CaravanBattleFinished,
    CloseCaravanLobby,
    ClosedCaravanLobby,
    FinishCaravanBattle,
    ICaravanBattleFinishNotifier,
    ICaravanLobbyCloseNotifier,
)
from pipirik_wars.application.daily_head import (
    RunDailyHeadCron,
    ScheduleDailyHeadCronJobs,
)
from pipirik_wars.application.dto.inputs import (
    CloseBossLobbyInput,
    CloseCaravanLobbyInput,
    EscalateChatToGlobalInput,
    ExpireLobbyEntryInput,
    FinishBossFightInput,
    FinishCaravanBattleInput,
    FinishDungeonRunInput,
    FinishForestRunInput,
    FinishMountainRunInput,
    ForceResolveMassDuelInput,
    ResolveAfkRoundInput,
    RunBossRoundInput,
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
from pipirik_wars.application.monetization import (
    GeneratePrizeLots,
    GeneratePrizeLotsCommand,
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
from pipirik_wars.domain.monetization.value_objects import Currency, IdempotencyKey
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
# 3.3-B (Рейд-боссы, ГДД §10). Lobby-close → IN_BATTLE; round-tick — pending-раунд;
# fight-finish — safety-net на случай зависшего боя.
_BOSS_LOBBY_CLOSE_JOB_PREFIX: Final[str] = "boss_lobby_close:"
_BOSS_ROUND_TICK_JOB_PREFIX: Final[str] = "boss_round_tick:"
_BOSS_FIGHT_FINISH_JOB_PREFIX: Final[str] = "boss_fight_finish:"
_DAILY_HEAD_RESCHEDULE_JOB_ID: Final[str] = "daily_head_reschedule_cron"
_WEEKLY_REFERRAL_SUMMARY_JOB_ID: Final[str] = "weekly_clan_referral_summary_cron"
#: Расписание weekly-сводки рефералов клана: вс. 18:00 UTC (ГДД §13.3).
_WEEKLY_REFERRAL_SUMMARY_DAY_OF_WEEK: Final[str] = "sun"
_WEEKLY_REFERRAL_SUMMARY_HOUR: Final[int] = 18
_WEEKLY_REFERRAL_SUMMARY_MINUTE: Final[int] = 0
_WEEKLY_REFERRAL_SUMMARY_TIMEZONE: Final[str] = "UTC"
# 4.1-C / C.7.b: cron-entry `GeneratePrizeLots` per currency (1×/час).
# 3 параллельных job-а (STARS / TON_NANO / USDT_DECIMAL) — каждый 1×/час
# режет свой баланс пула на лоты. Idempotency-key привязан к UTC-часу:
# повторный fire в тот же час → `GeneratePrizeLots` выходит no-op через ranged
# `IIdempotencyKey.is_seen`-проверку.
_PRIZE_LOT_GENERATOR_CRON_JOB_PREFIX: Final[str] = "prize_lot_generator_cron:"
_PRIZE_LOT_GENERATOR_CRON_INTERVAL_HOURS: Final[int] = 1


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


def _boss_lobby_close_job_id(boss_fight_id: int) -> str:
    return f"{_BOSS_LOBBY_CLOSE_JOB_PREFIX}{boss_fight_id}"


def _boss_round_tick_job_id(boss_fight_id: int) -> str:
    return f"{_BOSS_ROUND_TICK_JOB_PREFIX}{boss_fight_id}"


def _boss_fight_finish_job_id(boss_fight_id: int) -> str:
    return f"{_BOSS_FIGHT_FINISH_JOB_PREFIX}{boss_fight_id}"


def _prize_lot_generator_cron_job_id(currency: Currency) -> str:
    """Стабильный APScheduler-id per currency (4.1-C / C.7.b).

    Префикс + `currency.value` (`stars` / `ton_nano` / `usdt_decimal`).
    Алфанумерический + `_` — валидный APScheduler-id. Нужен для
    `replace_existing=True`-идемпотентности при recovery-вызовах.
    """
    return f"{_PRIZE_LOT_GENERATOR_CRON_JOB_PREFIX}{currency.value}"


def _prize_lot_generator_period_id(now: datetime) -> str:
    """`period_id` для cron-idempotency-key-а (4.1-C / C.7.b).

    Формат `YYYY-MM-DDTHH` — UTC-час-бакет (`strftime("%Y-%m-%dT%H")`).
    Два fire-а в тот же час (напр. APScheduler misfire-recovery + grace-time)
    → одини `period_id` → один и тот же `IdempotencyKey` → `GeneratePrizeLots`
    повторно выйдет с `idempotent=True` (без побочных эффектов).

    Никаких точек / пробелов: символы `0-9 - T` все входят в
    вайтлист `IdempotencyKey.value` `[A-Za-z0-9_\\-:]{1,64}`.
    """
    return now.strftime("%Y-%m-%dT%H")


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
        "_boss_fight_finish_factory",
        "_boss_fight_finish_notifier",
        "_boss_lobby_close_factory",
        "_boss_lobby_close_notifier",
        "_boss_round_tick_factory",
        "_boss_round_tick_notifier",
        "_caravan_battle_finish_factory",
        "_caravan_battle_finish_notifier",
        "_caravan_lobby_close_factory",
        "_caravan_lobby_close_notifier",
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
        "_prize_lot_generator_factory",
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
        caravan_battle_finish_factory: Callable[[], FinishCaravanBattle] | None = None,
        caravan_lobby_close_notifier: ICaravanLobbyCloseNotifier | None = None,
        caravan_battle_finish_notifier: ICaravanBattleFinishNotifier | None = None,
        boss_lobby_close_factory: Callable[[], CloseBossLobby] | None = None,
        boss_round_tick_factory: Callable[[], RunBossRound] | None = None,
        boss_fight_finish_factory: Callable[[], FinishBossFight] | None = None,
        boss_lobby_close_notifier: IBossLobbyCloseNotifier | None = None,
        boss_round_tick_notifier: IBossRoundTickNotifier | None = None,
        boss_fight_finish_notifier: IBossFightFinishNotifier | None = None,
        clans: IClanRepository | None = None,
        prize_lot_generator_factory: Callable[[], GeneratePrizeLots] | None = None,
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
        self._caravan_battle_finish_factory = caravan_battle_finish_factory
        self._caravan_lobby_close_notifier = caravan_lobby_close_notifier
        self._caravan_battle_finish_notifier = caravan_battle_finish_notifier
        self._boss_lobby_close_factory = boss_lobby_close_factory
        self._boss_round_tick_factory = boss_round_tick_factory
        self._boss_fight_finish_factory = boss_fight_finish_factory
        self._boss_lobby_close_notifier = boss_lobby_close_notifier
        self._boss_round_tick_notifier = boss_round_tick_notifier
        self._boss_fight_finish_notifier = boss_fight_finish_notifier
        self._clans = clans
        self._prize_lot_generator_factory = prize_lot_generator_factory
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
        """Callback `CloseCaravanLobby`-job-а (Спринт 3.2-B + 3.2-D D.6).

        Срабатывает в `caravan.lobby_ends_at` и переводит караван
        `LOBBY → IN_BATTLE`. Если фабрика не подвязана (recovery /
        тесты APScheduler-а самого по себе) — пишем warning и тихо
        выходим. Use-case сам идемпотентен: повторный вызов на
        уже не-`LOBBY` караване вернёт `was_already_closed=True`.

        После успешного `execute(...)` — best-effort `notifier.notify(result)`,
        который шлёт сообщение «лобби закрыто, бой начался» в чаты
        обоих кланов (ГДД §9.3, Спринт 3.2-D D.6).
        """
        if self._caravan_lobby_close_factory is None:
            self._logger.warning(
                "caravan_lobby_close: factory not wired",
                extra={"caravan_id": caravan_id},
            )
            return
        result: ClosedCaravanLobby | None = None
        try:
            use_case = self._caravan_lobby_close_factory()
            result = await use_case.execute(CloseCaravanLobbyInput(caravan_id=caravan_id))
        except Exception as exc:
            self._logger.exception(
                "caravan_lobby_close: unexpected error",
                extra={"caravan_id": caravan_id, "error": type(exc).__name__},
            )
            return

        if self._caravan_lobby_close_notifier is None or result is None:
            return
        try:
            await self._caravan_lobby_close_notifier.notify(result)
        except Exception as exc:
            self._logger.exception(
                "caravan_lobby_close: notifier failed",
                extra={"caravan_id": caravan_id, "error": type(exc).__name__},
            )

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
        """Callback `FinishCaravanBattle`-job-а (Спринт 3.2-C + 3.2-D D.6).

        Срабатывает в `caravan.battle_ends_at`, резолвит бой
        (детерминистично от `random_seed`), выдаёт награды,
        начисляет Атаман-роль рейдеру-победителю. Use-case
        идемпотентен: повторный вызов на `FINISHED`-каравану вернёт
        `was_already_finished=True`. Если фабрика не подвязана
        (recovery / тесты APScheduler-а самого по себе) — лог + skip.

        После успешного `execute(...)` — best-effort `notifier.notify(result)`,
        который шлёт сообщение «караван доставлен» / «караван разграблен»
        в чаты обоих кланов (ГДД §9.5–§9.6, Спринт 3.2-D D.6).
        """
        if self._caravan_battle_finish_factory is None:
            self._logger.warning(
                "caravan_battle_finish: factory not wired",
                extra={"caravan_id": caravan_id},
            )
            return
        result: CaravanBattleFinished | None = None
        try:
            use_case = self._caravan_battle_finish_factory()
            result = await use_case.execute(FinishCaravanBattleInput(caravan_id=caravan_id))
        except Exception as exc:
            self._logger.exception(
                "caravan_battle_finish: unexpected error",
                extra={"caravan_id": caravan_id, "error": type(exc).__name__},
            )
            return

        if self._caravan_battle_finish_notifier is None or result is None:
            return
        try:
            await self._caravan_battle_finish_notifier.notify(result)
        except Exception as exc:
            self._logger.exception(
                "caravan_battle_finish: notifier failed",
                extra={"caravan_id": caravan_id, "error": type(exc).__name__},
            )

    # ── Спринт 3.3-B: рейд-боссы (lobby-close + round-tick + fight-finish, ГДД §10) ──
    #
    # На уровне 3.3-B регистрируем date-job-ы; callback-и логируют
    # «factory not wired» и тихо выходят, потому что use-case-ы
    # `CloseBossLobby` / `RunBossRound` / `FinishBossFight` подвязываются
    # в `bot/main.py` отдельным шагом B.11 (factory-параметры на
    # конструкторе адаптера) и Спринтом 3.3-D (notifier-ы).
    # Регистрация job-а в APScheduler-е нужна уже сейчас, чтобы
    # `SummonBoss` / `CloseBossLobby` (B.4 / B.7) могли вызывать
    # `schedule_boss_*`-методы порта.

    async def schedule_boss_lobby_close(
        self,
        *,
        boss_fight_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_boss_lobby_close_job,
            trigger="date",
            run_date=run_at,
            args=(boss_fight_id,),
            id=_boss_lobby_close_job_id(boss_fight_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_boss_lobby_close(self, *, boss_fight_id: int) -> None:
        try:
            self._scheduler.remove_job(_boss_lobby_close_job_id(boss_fight_id))
        except Exception:
            return

    async def schedule_boss_round_tick(
        self,
        *,
        boss_fight_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_boss_round_tick_job,
            trigger="date",
            run_date=run_at,
            args=(boss_fight_id,),
            id=_boss_round_tick_job_id(boss_fight_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_boss_round_tick(self, *, boss_fight_id: int) -> None:
        try:
            self._scheduler.remove_job(_boss_round_tick_job_id(boss_fight_id))
        except Exception:
            return

    async def schedule_boss_fight_finish(
        self,
        *,
        boss_fight_id: int,
        run_at: datetime,
    ) -> None:
        self._scheduler.add_job(
            self._run_boss_fight_finish_job,
            trigger="date",
            run_date=run_at,
            args=(boss_fight_id,),
            id=_boss_fight_finish_job_id(boss_fight_id),
            replace_existing=True,
            misfire_grace_time=None,
        )

    async def cancel_boss_fight_finish(self, *, boss_fight_id: int) -> None:
        try:
            self._scheduler.remove_job(_boss_fight_finish_job_id(boss_fight_id))
        except Exception:
            return

    async def _run_boss_lobby_close_job(self, boss_fight_id: int) -> None:
        """Callback `CloseBossLobby`-job-а (Спринт 3.3-B B.11 + 3.3-D D.3 / D.7).

        Срабатывает в `boss_fight.lobby_ends_at` и переводит рейд-бой
        `LOBBY → IN_BATTLE`. Если фабрика не подвязана (recovery /
        тесты APScheduler-а самого по себе) — пишем warning и тихо
        выходим. Use-case сам идемпотентен: повторный вызов на
        уже не-`LOBBY` рейд-бое вернёт `was_already_closed=True`.

        После успешного `execute(...)` — best-effort
        `notifier.notify(result)`, который шлёт сообщение «лобби
        закрыто, бой начался» (ГДД §10.3, Спринт 3.3-D D.7).
        """
        if self._boss_lobby_close_factory is None:
            self._logger.warning(
                "boss_lobby_close: factory not wired",
                extra={"boss_fight_id": boss_fight_id},
            )
            return
        result: BossLobbyClosed | None = None
        try:
            use_case = self._boss_lobby_close_factory()
            result = await use_case.execute(CloseBossLobbyInput(boss_fight_id=boss_fight_id))
        except Exception as exc:
            self._logger.exception(
                "boss_lobby_close: unexpected error",
                extra={"boss_fight_id": boss_fight_id, "error": type(exc).__name__},
            )
            return

        if self._boss_lobby_close_notifier is None or result is None:
            return
        try:
            await self._boss_lobby_close_notifier.notify(result)
        except Exception as exc:
            self._logger.exception(
                "boss_lobby_close: notifier failed",
                extra={"boss_fight_id": boss_fight_id, "error": type(exc).__name__},
            )

    async def _run_boss_round_tick_job(self, boss_fight_id: int) -> None:
        """Callback `RunBossRound`-job-а (Спринт 3.3-B B.3 stub →
        3.3-D D.3 / D.7 full impl).

        Срабатывает каждые `bosses.round_max_seconds` после `LOBBY →
        IN_BATTLE`. Резолвит один раунд боя, применяет урон боссу и
        выбытия рейдеров (детерминистично от `random_seed * 1_000_003 +
        current_round`). Если рейдеры победили или все выбыли —
        `is_finished=True`, бой переводится в FINISHED. Сама раздача
        наград идёт отдельным `boss_fight_finish` job-ом
        (`_run_boss_fight_finish_job`), который use-case `RunBossRound`
        НЕ шедулит — это контракт на 3.3-D D.3 (или, на recovery, на
        safety-net job-е, который ставит `CloseBossLobby`).

        Use-case сам идемпотентен: повторный вызов на уже терминальном
        бое вернёт `was_already_finished=True`. Если фабрика не
        подвязана (тесты APScheduler-а самого по себе) — лог + skip.

        После успешного `execute(...)` — best-effort
        `notifier.notify(result)`, который шлёт карточку раунда
        участникам (ГДД §10.4, Спринт 3.3-D D.7).
        """
        if self._boss_round_tick_factory is None:
            self._logger.warning(
                "boss_round_tick: factory not wired",
                extra={"boss_fight_id": boss_fight_id},
            )
            return
        result: BossRoundResolved | None = None
        try:
            use_case = self._boss_round_tick_factory()
            result = await use_case.execute(RunBossRoundInput(boss_fight_id=boss_fight_id))
        except Exception as exc:
            self._logger.exception(
                "boss_round_tick: unexpected error",
                extra={"boss_fight_id": boss_fight_id, "error": type(exc).__name__},
            )
            return

        if self._boss_round_tick_notifier is None or result is None:
            return
        try:
            await self._boss_round_tick_notifier.notify(result)
        except Exception as exc:
            self._logger.exception(
                "boss_round_tick: notifier failed",
                extra={"boss_fight_id": boss_fight_id, "error": type(exc).__name__},
            )

    async def _run_boss_fight_finish_job(self, boss_fight_id: int) -> None:
        """Callback `FinishBossFight`-job-а (Спринт 3.3-B B.3 stub →
        3.3-D D.3 / D.7 full impl).

        Срабатывает либо как safety-net (поставлен `CloseBossLobby`-job-ом
        на `lobby_ends_at + max_battle_duration`), либо как немедленный
        finish (поставленный bot-handler-ом / `RunBossRound`-use-case-ом
        в момент `is_finished=True`, чтобы карточки наград улетели до
        окончания текущего event-loop-а). Use-case сам идемпотентен:
        повторный вызов на FINISHED/CANCELLED — `was_already_finished=True`.

        Раздаёт длины и свитки рейдерам (победа), либо `+sum(length_at_join)`
        боссу + `Δ`-deduction рейдерам (поражение). Подробности —
        `application.bosses.finish_boss_fight.FinishBossFight` (3.3-C / 3.3-D D.2).

        Если фабрика не подвязана (тесты APScheduler-а самого по себе) —
        лог + skip. После успешного `execute(...)` — best-effort
        `notifier.notify(result)`, который шлёт карточку «бой завершён»
        участникам (ГДД §10.5, Спринт 3.3-D D.7).
        """
        if self._boss_fight_finish_factory is None:
            self._logger.warning(
                "boss_fight_finish: factory not wired",
                extra={"boss_fight_id": boss_fight_id},
            )
            return
        result: BossFightFinished | None = None
        try:
            use_case = self._boss_fight_finish_factory()
            result = await use_case.execute(FinishBossFightInput(boss_fight_id=boss_fight_id))
        except Exception as exc:
            self._logger.exception(
                "boss_fight_finish: unexpected error",
                extra={"boss_fight_id": boss_fight_id, "error": type(exc).__name__},
            )
            return

        if self._boss_fight_finish_notifier is None or result is None:
            return
        try:
            await self._boss_fight_finish_notifier.notify(result)
        except Exception as exc:
            self._logger.exception(
                "boss_fight_finish: notifier failed",
                extra={"boss_fight_id": boss_fight_id, "error": type(exc).__name__},
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

    def schedule_prize_lot_generator_cron(self) -> None:
        """Зарегистрировать cron `GeneratePrizeLots` per currency 1×/час (4.1-C / C.7.b).

        3 параллельных `IntervalTrigger(hours=1)`-job-а — по одному на
        `STARS` / `TON_NANO` / `USDT_DECIMAL`. Каждый дёргает свежий
        `GeneratePrizeLots`-инстанс через `prize_lot_generator_factory`
        (late-bound: фабрика резолвится в момент срабатывания job-а, поэтому
        Container к этому моменту уже собран) и зовёт `execute(...)` с
        `GeneratePrizeLotsCommand(currency=..., idempotency_key=...)`.

        Idempotency-key привязан к UTC-часу (`prize_lot_generator:cron:<currency>:<period_id>`,
        где `period_id = strftime("%Y-%m-%dT%H")`): повторный fire в тот же
        час (misfire-recovery / grace-time) → `GeneratePrizeLots` выйдет
        no-op-ом через `is_seen`-проверку.

        Идемпотентен на регистрацию (`replace_existing=True`): можно
        дёргать сколько угодно раз, в job-store-е останется один job
        per currency.

        Если `prize_lot_generator_factory` не подвязана (например, в
        unit-тестах самого APScheduler-а) — логируем warning и тихо
        выходим без регистрации.

        Триггер `RecordDonation` после крупного зачисления — отдельный
        механизм (C.7.d), не покрывается этим методом.
        """
        if self._prize_lot_generator_factory is None:
            self._logger.warning(
                "prize_lot_generator_cron: factory not wired",
            )
            return
        for currency in Currency:
            self._scheduler.add_job(
                self._run_prize_lot_generator_cron_job,
                trigger=IntervalTrigger(
                    hours=_PRIZE_LOT_GENERATOR_CRON_INTERVAL_HOURS,
                ),
                args=(currency.value,),
                id=_prize_lot_generator_cron_job_id(currency),
                replace_existing=True,
                misfire_grace_time=None,
            )

    async def _run_prize_lot_generator_cron_job(self, currency_value: str) -> None:
        """Callback hourly-cron-а `GeneratePrizeLots` per currency (4.1-C / C.7.b).

        APScheduler передаёт `currency_value` как `str` (а не как `Currency`-
        enum), потому что in-memory `JobStore` сериализует аргументы; на
        случай миграции в `SQLAlchemyJobStore` (Спринт 1.3.D) — пара
        `(str, IdempotencyKey)` остаётся pickle-safe.

        Алгоритм:
        1. Resolve `Currency(currency_value)` (`StrEnum`); невалидное
           значение → `ValueError`, проглатывается общим `except`-блоком.
        2. Построить `period_id` от текущего UTC-часа
           (`strftime("%Y-%m-%dT%H")`).
        3. Построить `IdempotencyKey(f"prize_lot_generator:cron:<currency>:<period_id>")`.
           Whitelist VO (`[A-Za-z0-9_\\-:]{1,64}`) допускает все символы.
        4. Дёрнуть use-case через `prize_lot_generator_factory()` и
           `execute(GeneratePrizeLotsCommand(currency, idempotency_key))`.

        Любые исключения логируются и проглатываются — иначе APScheduler
        пометит job-у как `failed` и оставит её в job-store-е.
        """
        if self._prize_lot_generator_factory is None:
            self._logger.warning(
                "prize_lot_generator_cron: factory not wired",
                extra={"currency": currency_value},
            )
            return
        try:
            currency = Currency(currency_value)
            period_id = _prize_lot_generator_period_id(datetime.now(UTC))
            idempotency_key = IdempotencyKey(
                f"prize_lot_generator:cron:{currency.value}:{period_id}",
            )
            use_case = self._prize_lot_generator_factory()
            await use_case.execute(
                GeneratePrizeLotsCommand(
                    currency=currency,
                    idempotency_key=idempotency_key,
                ),
            )
        except Exception as exc:
            self._logger.exception(
                "prize_lot_generator_cron: unexpected error",
                extra={
                    "currency": currency_value,
                    "error": type(exc).__name__,
                },
            )
            return

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
