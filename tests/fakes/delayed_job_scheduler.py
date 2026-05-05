"""In-memory реализация `IDelayedJobScheduler` для unit-тестов."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pipirik_wars.domain.shared.ports import IDelayedJobScheduler


@dataclass(frozen=True, slots=True)
class ScheduledFinish:
    """Запись «что и на когда было запланировано»."""

    run_id: int
    run_at: datetime


@dataclass(frozen=True, slots=True)
class ScheduledLobbyJob:
    """Запись «что и на когда» для PvP-lobby-job-ов (Спринт 2.1.F.2)."""

    duel_id: int
    run_at: datetime


@dataclass(frozen=True, slots=True)
class ScheduledRoundAfkJob:
    """Запись «что и на когда» для AFK-таймера раунда (Спринт 2.1.G)."""

    duel_id: int
    round_num: int
    run_at: datetime


@dataclass
class FakeDelayedJobScheduler(IDelayedJobScheduler):
    """Фиксирует все вызовы `schedule_*` / `cancel_*`."""

    scheduled: dict[int, ScheduledFinish] = field(default_factory=dict)
    cancelled: list[int] = field(default_factory=list)
    scheduled_escalations: dict[int, ScheduledLobbyJob] = field(default_factory=dict)
    cancelled_escalations: list[int] = field(default_factory=list)
    scheduled_expirations: dict[int, ScheduledLobbyJob] = field(default_factory=dict)
    cancelled_expirations: list[int] = field(default_factory=list)
    # 2.1.G: per-(duel_id, round_num) AFK-таймеры. Ключ — кортеж,
    # т. к. в одной дуэли может быть несколько раундов, и cancel
    # должен попадать в конкретный раунд (см. SubmitMove на смене
    # раунда: cancel предыдущего + schedule нового).
    scheduled_round_afk: dict[tuple[int, int], ScheduledRoundAfkJob] = field(default_factory=dict)
    cancelled_round_afk: list[tuple[int, int]] = field(default_factory=list)

    async def schedule_finish_forest_run(
        self,
        *,
        run_id: int,
        run_at: datetime,
    ) -> None:
        self.scheduled[run_id] = ScheduledFinish(run_id=run_id, run_at=run_at)

    async def cancel_finish_forest_run(self, *, run_id: int) -> None:
        self.cancelled.append(run_id)
        self.scheduled.pop(run_id, None)

    async def schedule_chat_to_global_escalation(
        self,
        *,
        duel_id: int,
        run_at: datetime,
    ) -> None:
        self.scheduled_escalations[duel_id] = ScheduledLobbyJob(duel_id=duel_id, run_at=run_at)

    async def cancel_chat_to_global_escalation(self, *, duel_id: int) -> None:
        self.cancelled_escalations.append(duel_id)
        self.scheduled_escalations.pop(duel_id, None)

    async def schedule_global_lobby_expiration(
        self,
        *,
        duel_id: int,
        run_at: datetime,
    ) -> None:
        self.scheduled_expirations[duel_id] = ScheduledLobbyJob(duel_id=duel_id, run_at=run_at)

    async def cancel_global_lobby_expiration(self, *, duel_id: int) -> None:
        self.cancelled_expirations.append(duel_id)
        self.scheduled_expirations.pop(duel_id, None)

    async def schedule_round_afk_resolution(
        self,
        *,
        duel_id: int,
        round_num: int,
        run_at: datetime,
    ) -> None:
        self.scheduled_round_afk[(duel_id, round_num)] = ScheduledRoundAfkJob(
            duel_id=duel_id,
            round_num=round_num,
            run_at=run_at,
        )

    async def cancel_round_afk_resolution(
        self,
        *,
        duel_id: int,
        round_num: int,
    ) -> None:
        self.cancelled_round_afk.append((duel_id, round_num))
        self.scheduled_round_afk.pop((duel_id, round_num), None)
